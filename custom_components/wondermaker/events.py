"""Ereignisse des Druckers (Druckende, Fehler, Filament leer, Tür offen).

Erkennt die Ereignisse, löst Home-Assistant-Events aus, nimmt bei Bedarf ein
Kamerafoto auf und verschickt Push-Nachrichten an die gewählten Geräte.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .api import MoonrakerError
from .const import (
    CONF_NOTIFY_DELAY,
    CONF_NOTIFY_DOOR,
    CONF_NOTIFY_ENABLED,
    CONF_NOTIFY_ERROR,
    CONF_NOTIFY_ERROR_IMAGE,
    CONF_NOTIFY_FILAMENT,
    CONF_NOTIFY_IMAGE,
    CONF_NOTIFY_TARGETS,
    DEFAULT_NOTIFY_DELAY,
    DOMAIN,
    EVENT_DOOR_OPENED,
    EVENT_ERROR,
    EVENT_FILAMENT_RUNOUT,
    EVENT_PRINT_FINISHED,
    EXTRUDER_RE,
)
from .util import format_duration, get_status

if TYPE_CHECKING:
    from .coordinator import WondermakerCoordinator

_LOGGER = logging.getLogger(__name__)

PRINT_ACTIVE = ("printing", "paused")
# Filamentsensor muss so viele Abfragen in Folge "leer" melden (verhindert Fehlalarme beim Werkzeugwechsel)
FILAMENT_DEBOUNCE_POLLS = 2
# Manche Drucker setzen den Druckstatus am Ende sofort zurück (SDCARD_RESET_FILE im
# PRINT_END-Makro): "printing" -> "standby", ohne je "complete" zu melden. Dann gilt ein
# Druck als fertig, wenn er zuletzt mindestens so weit gekommen war.
FINISH_PROGRESS = 0.95
MAX_TEXT = 300


class PrinterEvents:
    """Beobachtet die Druckerdaten und meldet Ereignisse."""

    def __init__(self, coordinator: WondermakerCoordinator) -> None:
        self.c = coordinator
        self.photos: dict[str, tuple[bytes, datetime]] = {}
        self._webcams: list[dict[str, Any]] | None = None
        self._primed = False
        self._last_print_state: str | None = None
        self._last_error_key: tuple | None = None
        self._runout_polls = 0
        self._runout_notified = False
        self._doors_open = False
        self._last_progress: float | None = None
        self._last_filename: str | None = None
        self._last_duration: float | None = None

    # ------------------------------------------------------------------
    # Hilfen
    # ------------------------------------------------------------------
    @property
    def hass(self):
        return self.c.hass

    @property
    def opts(self):
        return self.c.config_entry.options

    @property
    def _german(self) -> bool:
        return (self.hass.config.language or "en").lower().startswith("de")

    def _t(self, de: str, en: str) -> str:
        return de if self._german else en

    def _spawn(self, coro, name: str) -> None:
        self.c.config_entry.async_create_background_task(self.hass, coro, f"wondermaker_{name}")

    @staticmethod
    def _short(text: str | None) -> str:
        text = (text or "").strip()
        return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"

    def _print_name(self, filename: str | None) -> str:
        name = (filename or "").rsplit("/", 1)[-1]
        if name.lower().endswith(".gcode"):
            name = name[: -len(".gcode")]
        return name or self._t("Druck", "Print")

    # ------------------------------------------------------------------
    # Fotos
    # ------------------------------------------------------------------
    def photo_path(self, kind: str) -> Path:
        return Path(
            self.hass.config.path("wondermaker", f"{self.c.config_entry.entry_id}_last_{kind}.jpg")
        )

    def load_saved_photo(self, kind: str) -> None:
        """Beim Start das zuletzt gespeicherte Foto laden (läuft im Executor)."""
        path = self.photo_path(kind)
        if kind not in self.photos and path.is_file():
            self.photos[kind] = (
                path.read_bytes(),
                datetime.fromtimestamp(path.stat().st_mtime, dt_util.UTC),
            )

    def _save_photo(self, kind: str, photo: bytes) -> None:
        path = self.photo_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(photo)

    async def async_get_snapshot(self) -> bytes | None:
        """Aktuelles Kamerabild über die Moonraker-Webcam-Konfiguration holen."""
        client = self.c.client
        if self._webcams is None:
            try:
                self._webcams = await client.webcams()
            except MoonrakerError as err:
                _LOGGER.debug("Webcams nicht abrufbar: %s", err)
                return None
        for cam in self._webcams:
            if not cam.get("enabled", True):
                continue
            for url in client.candidate_urls(cam.get("snapshot_url")):
                try:
                    return await client.get_url_bytes(url)
                except MoonrakerError:
                    continue
        return None

    async def async_take_photo(self, kind: str) -> bool:
        photo = await self.async_get_snapshot()
        if not photo:
            _LOGGER.debug("Kein Kamerabild für das Foto '%s' verfügbar", kind)
            return False
        self.photos[kind] = (photo, dt_util.utcnow())
        await self.hass.async_add_executor_job(self._save_photo, kind, photo)
        self.c.async_update_listeners()
        return True

    # ------------------------------------------------------------------
    # Erkennung (läuft bei jeder Abfrage)
    # ------------------------------------------------------------------
    def process(self, data: dict[str, Any]) -> None:
        try:
            self._process(data)
        except Exception:  # noqa: BLE001 - darf den Coordinator nie stören
            _LOGGER.exception("Fehler bei der Ereigniserkennung")

    def _process(self, data: dict[str, Any]) -> None:
        status = data.get("status", {})
        print_state = get_status(data, "print_stats", "state")
        klippy = data.get("klippy_state")

        # 1) Druck fertig ("complete" oder – wenn das Makro zurücksetzt – "standby" nach fast voller Länge)
        if print_state is not None:
            if print_state in PRINT_ACTIVE:
                progress = get_status(data, "display_status", "progress") or get_status(
                    data, "virtual_sdcard", "progress"
                )
                if progress is not None:
                    self._last_progress = progress
                self._last_filename = get_status(data, "print_stats", "filename") or self._last_filename
                duration = get_status(data, "print_stats", "print_duration")
                if duration is not None:
                    self._last_duration = duration
            previous, self._last_print_state = self._last_print_state, print_state
            if previous in PRINT_ACTIVE and print_state in ("complete", "standby"):
                finished = print_state == "complete" or (self._last_progress or 0) >= FINISH_PROGRESS
                if finished and self._primed:
                    self._spawn(
                        self._on_finished(
                            get_status(data, "print_stats", "filename") or self._last_filename,
                            get_status(data, "print_stats", "print_duration") or self._last_duration,
                        ),
                        "print_finished",
                    )
            if print_state not in PRINT_ACTIVE:
                self._last_progress = None

        # 2) Fehler (Druckabbruch durch Fehler oder Klipper-Shutdown)
        key: tuple | None = None
        if klippy in ("shutdown", "error"):
            key = ("klippy", klippy)
        elif print_state == "error":
            key = ("print", get_status(data, "print_stats", "message") or "")
        if self._primed and key and key != self._last_error_key:
            if key[0] == "klippy":
                text = data.get("state_message") or ""
            else:
                text = key[1]
            self._spawn(
                self._on_error(key[0], text, get_status(data, "print_stats", "filename") or None),
                "error",
            )
        self._last_error_key = key

        # 3) Filament leer (nur während eines Drucks, nur Sensoren des aktiven Werkzeugs)
        tool = get_status(data, "toolhead", "extruder", "extruder")
        match = EXTRUDER_RE.match(tool)
        number = (match.group(1) or "0") if match else "0"
        missing = [
            o
            for o in self._filament_sensors(status, number)
            if status[o].get("enabled", True) and status[o].get("filament_detected") is False
        ]
        if print_state in PRINT_ACTIVE and missing:
            self._runout_polls += 1
            if (
                self._primed
                and self._runout_polls >= FILAMENT_DEBOUNCE_POLLS
                and not self._runout_notified
            ):
                self._runout_notified = True
                self._spawn(self._on_runout(number, missing), "filament")
        else:
            self._runout_polls = 0
            self._runout_notified = False

        # 4) Türen (alle Türschalter offen, nur während eines Drucks)
        doors = [o for o in status if o.startswith("gcode_button ") and "door" in o.lower()]
        if doors:
            # Schalter gedrückt = Tür zu, losgelassen = Tür offen
            all_open = all(str(status[o].get("state", "")).upper() == "RELEASED" for o in doors)
            if (
                self._primed
                and all_open
                and not self._doors_open
                and print_state in PRINT_ACTIVE
            ):
                self._spawn(self._on_door(len(doors), get_status(data, "print_stats", "filename") or None), "door")
            self._doors_open = all_open

        self._primed = True

    @staticmethod
    def _filament_sensors(status: dict[str, Any], number: str) -> list[str]:
        every = [
            o
            for o in status
            if o.startswith(("filament_switch_sensor ", "filament_motion_sensor "))
        ]
        specific = [
            o for o in every if o.split(" ", 1)[1] in (f"filament{number}", f"path_{number}")
        ]
        if specific:
            return specific
        # Andere Drucker: alle Sensoren außer Dock-/Wechsler-Sensoren
        return [
            o for o in every if not re.search(r"dock|sensor_[a-z]$", o.split(" ", 1)[1], re.I)
        ]

    # ------------------------------------------------------------------
    # Ereignisse
    # ------------------------------------------------------------------
    async def _on_finished(self, filename: str | None, duration: float | None) -> None:
        try:
            self.hass.bus.async_fire(
                EVENT_PRINT_FINISHED,
                {"entry_id": self.c.config_entry.entry_id, "filename": filename, "duration": duration},
            )
            delay = int(self.opts.get(CONF_NOTIFY_DELAY, DEFAULT_NOTIFY_DELAY))
            if delay > 0:
                await asyncio.sleep(delay)
            photo_ok = await self.async_take_photo("print")
            if self.opts.get(CONF_NOTIFY_ENABLED, False):
                title, message = self._finish_texts(filename, duration)
                await self._notify(
                    title,
                    message,
                    "wondermaker_print_finished",
                    image_kind="print" if photo_ok and self.opts.get(CONF_NOTIFY_IMAGE, True) else None,
                )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler bei der Druckende-Benachrichtigung")

    async def _on_error(self, source: str, text: str, filename: str | None) -> None:
        try:
            text = self._short(text)
            self.hass.bus.async_fire(
                EVENT_ERROR,
                {"entry_id": self.c.config_entry.entry_id, "source": source, "message": text, "filename": filename},
            )
            if not self.opts.get(CONF_NOTIFY_ERROR, False):
                return
            photo_ok = False
            if self.opts.get(CONF_NOTIFY_ERROR_IMAGE, False):
                photo_ok = await self.async_take_photo("error")
            if source == "klippy":
                title = self._t("Drucker-Fehler ⚠️", "Printer error ⚠️")
                body = text or self._t("Klipper meldet einen Fehler (Shutdown).", "Klipper reports an error (shutdown).")
            else:
                title = self._t("Druckfehler ⚠️", "Print error ⚠️")
                name = self._print_name(filename)
                body = f"{name}: {text}" if text else self._t(
                    f"{name}: Der Druck wurde wegen eines Fehlers beendet.",
                    f"{name}: The print was stopped by an error.",
                )
            await self._notify(
                title, body, "wondermaker_error", image_kind="error" if photo_ok else None, urgent=True
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler bei der Fehler-Benachrichtigung")

    async def _on_runout(self, number: str, sensors: list[str]) -> None:
        try:
            names = [s.split(" ", 1)[1] for s in sensors]
            self.hass.bus.async_fire(
                EVENT_FILAMENT_RUNOUT,
                {"entry_id": self.c.config_entry.entry_id, "tool": f"T{number}", "sensors": names},
            )
            if not self.opts.get(CONF_NOTIFY_FILAMENT, False):
                return
            await self._notify(
                self._t("Filament leer ⚠️", "Filament runout ⚠️"),
                self._t(
                    f"Werkzeug T{number}: Es wird kein Filament erkannt ({', '.join(names)}).",
                    f"Tool T{number}: no filament detected ({', '.join(names)}).",
                ),
                "wondermaker_filament",
                urgent=True,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler bei der Filament-Benachrichtigung")

    async def _on_door(self, count: int, filename: str | None) -> None:
        try:
            self.hass.bus.async_fire(
                EVENT_DOOR_OPENED,
                {"entry_id": self.c.config_entry.entry_id, "doors": count, "filename": filename},
            )
            if not self.opts.get(CONF_NOTIFY_DOOR, False):
                return
            await self._notify(
                self._t("Tür geöffnet 🚪", "Door opened 🚪"),
                self._t(
                    f"Die Türen sind offen, während {self._print_name(filename)} gedruckt wird.",
                    f"The doors are open while {self._print_name(filename)} is printing.",
                ),
                "wondermaker_door",
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Fehler bei der Tür-Benachrichtigung")

    # ------------------------------------------------------------------
    # Versand
    # ------------------------------------------------------------------
    def _finish_texts(self, filename: str | None, duration: float | None) -> tuple[str, str]:
        name = self._print_name(filename)
        dur = format_duration(duration)
        if self._german:
            msg = f"{name} ist fertig gedruckt." if not dur else f"{name} ist fertig gedruckt (Dauer: {dur})."
            return "Druck fertig ✅", msg
        msg = f"{name} has finished printing." if not dur else f"{name} has finished printing (took {dur})."
        return "Print finished ✅", msg

    async def _notify(
        self,
        title: str,
        message: str,
        tag: str,
        *,
        image_kind: str | None = None,
        urgent: bool = False,
    ) -> None:
        """Push-Nachricht an alle gewählten Geräte."""
        targets = self.opts.get(CONF_NOTIFY_TARGETS) or []
        if not targets:
            _LOGGER.debug("Benachrichtigung aktiv, aber keine Geräte gewählt")
            return

        image_url = None
        if image_kind and image_kind in self.photos:
            entity_id = er.async_get(self.hass).async_get_entity_id(
                "image", DOMAIN, f"{self.c.config_entry.entry_id}_{image_kind}_photo"
            )
            if entity_id:
                image_url = f"/api/image_proxy/{entity_id}"

        base = {"title": title, "message": message}
        for target in targets:
            if not self.hass.services.has_service("notify", target):
                _LOGGER.warning("Benachrichtigungsdienst notify.%s existiert nicht", target)
                continue
            data: dict[str, Any] = {"tag": tag, "group": "wondermaker"}
            if urgent:
                data["push"] = {"interruption-level": "time-sensitive"}
                data["ttl"] = 0
                data["priority"] = "high"
            if image_url:
                data["image"] = image_url
                data["attachment"] = {"url": image_url, "content-type": "jpeg"}
            try:
                await self.hass.services.async_call(
                    "notify", target, {**base, "data": data}, blocking=True
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("notify.%s fehlgeschlagen (%s)", target, err)
                try:  # Ziel kennt evtl. die Zusatzfelder nicht – schlicht erneut versuchen
                    await self.hass.services.async_call("notify", target, base, blocking=True)
                except Exception as err2:  # noqa: BLE001
                    _LOGGER.warning("notify.%s auch ohne Zusatzdaten fehlgeschlagen (%s)", target, err2)

    async def async_send_test(self) -> None:
        """Testnachricht (ignoriert die Schalter, nutzt Geräte und Foto-Einstellung)."""
        photo_ok = await self.async_take_photo("print")
        title, message = self._finish_texts("Testdruck.gcode", 2775)
        await self._notify(
            title,
            message,
            "wondermaker_print_finished",
            image_kind="print" if photo_ok and self.opts.get(CONF_NOTIFY_IMAGE, True) else None,
        )
