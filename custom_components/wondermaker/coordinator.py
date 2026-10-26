"""DataUpdateCoordinator für den WonderMaker (Moonraker)."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MoonrakerAuthError,
    MoonrakerClient,
    MoonrakerConnectionError,
    MoonrakerError,
)
from .const import (
    BASE_OBJECTS,
    EXTRUDER_RE,
    TOOL_LED_RE,
    CONF_LAYER_ENABLED,
    CONF_LAYER_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_LAYER_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DISCOVER_PREFIXES,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .events import PrinterEvents
from .util import format_duration, get_status, interval_option  # noqa: F401

_LOGGER = logging.getLogger(__name__)


class WondermakerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holt zyklisch alle Daten vom Drucker."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: MoonrakerClient
    ) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.client = client
        self.objects: list[str] | None = None
        self._query_names: list[str] = []
        self._meta_name: str | None = None
        self._meta: dict[str, Any] = {}
        self.events = PrinterEvents(self)

    @property
    def device_info(self) -> DeviceInfo:
        data = self.data or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self.config_entry.entry_id)},
            name="WonderMaker ZR Ultra S",
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=data.get("printer_info", {}).get("software_version"),
            configuration_url=f"http://{self.client.host}",
        )

    def objects_with_prefix(self, prefixes: tuple[str, ...]) -> list[str]:
        return [o for o in (self.objects or []) if o.startswith(prefixes)]

    @property
    def tool_objects(self) -> list[str]:
        """extruder, extruder1, ... (nach Nummer sortiert)."""
        found = [o for o in (self.objects or []) if EXTRUDER_RE.match(o)]
        return sorted(found, key=lambda o: int(EXTRUDER_RE.match(o).group(1) or 0))

    async def _discover(self) -> None:
        self.objects = await self.client.list_objects()
        names = [o for o in BASE_OBJECTS if o in self.objects]
        names += [
            o for o in self.objects if EXTRUDER_RE.match(o) and o not in names
        ]
        names += [
            o
            for o in self.objects
            if o.startswith(DISCOVER_PREFIXES)
            and not TOOL_LED_RE.search(o.split(" ", 1)[-1])
        ]
        self._query_names = names

    async def _update_metadata(self, data: dict[str, Any]) -> None:
        """Dateimetadaten (Schichtanzahl, Schichthöhe) je Druckdatei einmal laden."""
        filename = get_status(data, "print_stats", "filename") or None
        if filename != self._meta_name:
            self._meta_name = filename
            self._meta = {}
            if filename:
                try:
                    self._meta = await self.client.file_metadata(filename)
                except MoonrakerAuthError:
                    raise
                except MoonrakerError as err:
                    _LOGGER.debug("Metadaten für %s nicht lesbar: %s", filename, err)
        data["metadata"] = self._meta

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            server = await self.client.server_info()
        except MoonrakerAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except MoonrakerConnectionError as err:
            raise UpdateFailed(f"Drucker nicht erreichbar: {err}") from err
        except MoonrakerError as err:
            raise UpdateFailed(str(err)) from err

        klippy_state = server.get("klippy_state", "disconnected")
        data: dict[str, Any] = {
            "server": server,
            "klippy_state": klippy_state,
            "printer_info": {},
            "status": {},
            "proc": {},
            "metadata": {},
            # 0 = Schichtanzeige aus
            "layer_interval": interval_option(
                self.config_entry.options,
                CONF_LAYER_ENABLED,
                CONF_LAYER_INTERVAL,
                DEFAULT_LAYER_INTERVAL,
            ),
        }

        if server.get("klippy_connected") and klippy_state == "ready":
            try:
                if self.objects is None:
                    await self._discover()
                data["printer_info"] = await self.client.printer_info()
                data["status"] = await self.client.query_objects(self._query_names)
                await self._update_metadata(data)
            except MoonrakerAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except MoonrakerError as err:
                raise UpdateFailed(str(err)) from err
        else:
            # Beim nächsten Start neu entdecken (z. B. nach Firmware-Restart)
            self.objects = None
            if server.get("klippy_connected"):
                try:  # Fehlertext von Klipper (z. B. bei Shutdown)
                    info = await self.client.printer_info()
                    data["printer_info"] = info
                except MoonrakerError:
                    info = {}
            else:
                info = {}
            data["state_message"] = info.get("state_message") if info else None

        try:
            data["proc"] = await self.client.proc_stats()
        except MoonrakerError:
            data["proc"] = {}

        if "state_message" not in data:
            data["state_message"] = data["printer_info"].get("state_message")
        self.events.process(data)
        return data
