"""Beleuchtung (LED / output_pin) des WonderMaker – nur wenn in Klipper vorhanden."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MoonrakerError
from .const import LED_PREFIXES, LIGHT_PIN_HINTS, PIN_PREFIX, TOOL_LED_RE
from .coordinator import WondermakerCoordinator, get_status
from .entity import WondermakerEntity


def _light_objects(coordinator: WondermakerCoordinator) -> list[str]:
    result = [
        o
        for o in coordinator.objects_with_prefix(LED_PREFIXES)
        if not TOOL_LED_RE.search(o.split(" ", 1)[1])
    ]
    for obj in coordinator.objects_with_prefix((PIN_PREFIX,)):
        name = obj.split(" ", 1)[1].lower()
        if any(hint in name for hint in LIGHT_PIN_HINTS):
            result.append(obj)
    return result


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_dynamic() -> None:
        new = [
            WondermakerLight(coordinator, obj)
            for obj in _light_objects(coordinator)
            if obj not in known
        ]
        if new:
            known.update(l.object_name for l in new)
            async_add_entities(new)

    _add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic))


class WondermakerLight(WondermakerEntity, LightEntity):
    """LED-Streifen (dimmbar) oder schaltbarer Pin (an/aus)."""

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, f"obj_{object_name.replace(' ', '_')}")
        self.object_name = object_name
        kind, self._name = object_name.split(" ", 1)
        self._is_pin = kind == "output_pin"
        self._attr_name = self._name.replace("_", " ").title()
        if self._is_pin:
            self._attr_color_mode = ColorMode.ONOFF
            self._attr_supported_color_modes = {ColorMode.ONOFF}
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def _level(self) -> float | None:
        """Helligkeit 0..1 oder None."""
        if self._is_pin:
            return get_status(self.coordinator.data, self.object_name, "value")
        colors = get_status(self.coordinator.data, self.object_name, "color_data")
        if not colors:
            return None
        return max(max(c) for c in colors if c)

    @property
    def is_on(self) -> bool | None:
        level = self._level()
        return None if level is None else level > 0

    @property
    def brightness(self) -> int | None:
        if self._is_pin:
            return None
        level = self._level()
        return None if level is None else round(level * 255)

    async def _set(self, level: float) -> None:
        if self._is_pin:
            script = f"SET_PIN PIN={self._name} VALUE={1 if level > 0 else 0}"
        else:
            script = (
                f"SET_LED LED={self._name} RED={level:.3f} GREEN={level:.3f} "
                f"BLUE={level:.3f} WHITE={level:.3f}"
            )
        try:
            await self.coordinator.client.gcode(script)
        except MoonrakerError as err:
            raise HomeAssistantError(f"Licht schalten fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS, 255)
        await self._set(brightness / 255)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)
