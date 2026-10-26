"""WonderMaker (Klipper/Moonraker) Integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import MoonrakerClient, MoonrakerError
from .const import CONF_API_KEY, DEFAULT_PORT, DOMAIN
from .coordinator import WondermakerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.LIGHT,
    Platform.CAMERA,
    Platform.IMAGE,
]

SERVICE_SEND_GCODE = "send_gcode"
SERVICE_START_PRINT = "start_print"

SEND_GCODE_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("gcode"): cv.string,
    }
)
START_PRINT_SCHEMA = vol.Schema(
    {
        vol.Optional("config_entry_id"): cv.string,
        vol.Required("filename"): cv.string,
    }
)

type WondermakerConfigEntry = ConfigEntry[WondermakerCoordinator]


def _get_coordinator(hass: HomeAssistant, call: ServiceCall) -> WondermakerCoordinator:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get("config_entry_id")
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if not entries:
        raise HomeAssistantError("Kein geladener WonderMaker gefunden")
    if len(entries) > 1:
        raise HomeAssistantError("Mehrere Drucker vorhanden – bitte config_entry_id angeben")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Services einmalig registrieren."""

    async def _send_gcode(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        try:
            await coordinator.client.gcode(call.data["gcode"], timeout=120)
        except MoonrakerError as err:
            raise HomeAssistantError(f"G-Code fehlgeschlagen: {err}") from err
        await coordinator.async_request_refresh()

    async def _start_print(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call)
        try:
            await coordinator.client.start_print(call.data["filename"])
        except MoonrakerError as err:
            raise HomeAssistantError(f"Druckstart fehlgeschlagen: {err}") from err
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_SEND_GCODE, _send_gcode, SEND_GCODE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_START_PRINT, _start_print, START_PRINT_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: WondermakerConfigEntry) -> bool:
    client = MoonrakerClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data.get(CONF_API_KEY),
    )
    coordinator = WondermakerCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: WondermakerConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: WondermakerConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
