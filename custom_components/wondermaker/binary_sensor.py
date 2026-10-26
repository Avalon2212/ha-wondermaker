"""Binärsensoren des WonderMaker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BUTTON_PREFIX, FILAMENT_PREFIXES
from .coordinator import WondermakerCoordinator, get_status
from .entity import WondermakerEntity


@dataclass(frozen=True, kw_only=True)
class WMBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool | None]


BINARY_SENSORS: tuple[WMBinaryDescription, ...] = (
    WMBinaryDescription(
        key="printing",
        translation_key="printing",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda d: get_status(d, "print_stats", "state") == "printing",
    ),
    WMBinaryDescription(
        key="paused",
        translation_key="paused",
        value_fn=lambda d: get_status(d, "print_stats", "state") == "paused",
    ),
    WMBinaryDescription(
        key="error",
        translation_key="error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: (
            get_status(d, "print_stats", "state") == "error"
            or d.get("klippy_state") in ("error", "shutdown")
        ),
    ),
    WMBinaryDescription(
        key="plate_cleared",
        translation_key="plate_cleared",
        entity_registry_enabled_default=False,
        value_fn=lambda d: get_status(d, "print_stats", "plate_cleared"),
    ),
    WMBinaryDescription(
        key="klippy_connected",
        translation_key="klippy_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: bool(d.get("server", {}).get("klippy_connected")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    async_add_entities(WondermakerBinarySensor(coordinator, d) for d in BINARY_SENSORS)

    known: set[str] = set()

    @callback
    def _add_dynamic() -> None:
        new: list[WondermakerObjectBinary] = [
            WondermakerFilamentSensor(coordinator, obj)
            for obj in coordinator.objects_with_prefix(FILAMENT_PREFIXES)
            if obj not in known
        ]
        new += [
            WondermakerDoorSwitch(coordinator, obj)
            for obj in coordinator.objects_with_prefix((BUTTON_PREFIX,))
            if obj not in known
        ]
        if new:
            known.update(s.object_name for s in new)
            async_add_entities(new)

    _add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic))


class WondermakerBinarySensor(WondermakerEntity, BinarySensorEntity):
    entity_description: WMBinaryDescription

    def __init__(self, coordinator: WondermakerCoordinator, description: WMBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)


class WondermakerObjectBinary(WondermakerEntity, BinarySensorEntity):
    """Basis für automatisch entdeckte Klipper-Objekte."""

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, f"obj_{object_name.replace(' ', '_')}")
        self.object_name = object_name

    @staticmethod
    def pretty(object_name: str) -> str:
        return object_name.split(" ", 1)[-1].replace("_", " ").title()


class WondermakerFilamentSensor(WondermakerObjectBinary):
    """Filament-/Dock-Sensoren. An = Filament erkannt bzw. Werkzeug im Dock."""

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        name = object_name.split(" ", 1)[1]
        if m := re.fullmatch(r"filament(\d+)", name):
            self._attr_translation_key = "tool_filament"
            self._attr_translation_placeholders = {"tool": f"T{m.group(1)}"}
        elif m := re.fullmatch(r"docked(\d+)", name):
            self._attr_translation_key = "tool_docked"
            self._attr_translation_placeholders = {"tool": f"T{m.group(1)}"}
        elif m := re.fullmatch(r"path_(\d+)", name):
            self._attr_translation_key = "path_filament"
            self._attr_translation_placeholders = {"path": m.group(1)}
        elif m := re.fullmatch(r"sensor_([a-z])", name, re.IGNORECASE):
            self._attr_translation_key = "changer_sensor"
            self._attr_translation_placeholders = {"sensor": m.group(1).upper()}
        else:
            self._attr_name = f"Filament {self.pretty(object_name)}"

    @property
    def is_on(self) -> bool | None:
        return get_status(self.coordinator.data, self.object_name, "filament_detected")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"enabled": get_status(self.coordinator.data, self.object_name, "enabled")}


class WondermakerDoorSwitch(WondermakerObjectBinary):
    """Türschalter (gcode_button). An = gedrückt."""

    _attr_translation_key = "door_switch"

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        name = object_name.split(" ", 1)[1]
        digits = re.search(r"(\d+)$", name)
        self._attr_translation_placeholders = {
            "name": digits.group(1) if digits else self.pretty(object_name)
        }

    @property
    def is_on(self) -> bool | None:
        state = get_status(self.coordinator.data, self.object_name, "state")
        return None if state is None else str(state).upper() == "PRESSED"
