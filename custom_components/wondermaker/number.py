"""Zahlenwerte (Solltemperaturen, Faktoren) des WonderMaker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import re
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MoonrakerError
from .const import CHAMBER_HEATER
from .coordinator import WondermakerCoordinator, get_status
from .entity import WondermakerEntity


@dataclass(frozen=True, kw_only=True)
class WMNumberDescription(NumberEntityDescription):
    value_fn: Callable[[dict[str, Any]], float | None]
    command_fn: Callable[[float], str]


def _factor(obj: str, key: str) -> Callable[[dict[str, Any]], float | None]:
    def _fn(d: dict[str, Any]) -> float | None:
        value = get_status(d, obj, key)
        return None if value is None else round(value * 100)

    return _fn


NUMBERS: tuple[WMNumberDescription, ...] = (
    WMNumberDescription(
        key="nozzle_target_temp",
        translation_key="nozzle_target_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=320,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda d: get_status(
            d, get_status(d, "toolhead", "extruder", "extruder"), "target"
        ),
        command_fn=lambda v: f"M104 S{int(v)}",
    ),
    WMNumberDescription(
        key="bed_target_temp",
        translation_key="bed_target_temp",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=0,
        native_max_value=120,
        native_step=1,
        mode=NumberMode.BOX,
        value_fn=lambda d: get_status(d, "heater_bed", "target"),
        command_fn=lambda v: f"M140 S{int(v)}",
    ),
    WMNumberDescription(
        key="speed_factor_set",
        translation_key="speed_factor_set",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=10,
        native_max_value=300,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_factor("gcode_move", "speed_factor"),
        command_fn=lambda v: f"M220 S{int(v)}",
    ),
    WMNumberDescription(
        key="flow_factor_set",
        translation_key="flow_factor_set",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=50,
        native_max_value=200,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_factor("gcode_move", "extrude_factor"),
        command_fn=lambda v: f"M221 S{int(v)}",
    ),
    WMNumberDescription(
        key="part_fan_set",
        translation_key="part_fan_set",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=_factor("fan", "speed"),
        command_fn=lambda v: f"M106 S{round(v * 2.55)}",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    async_add_entities(WondermakerNumber(coordinator, d) for d in NUMBERS)

    known: set[str] = set()

    @callback
    def _add_dynamic() -> None:
        new: list[WondermakerObjectNumber] = []
        for obj in coordinator.tool_objects:
            if obj not in known:
                new.append(WondermakerToolTarget(coordinator, obj))
        if CHAMBER_HEATER in (coordinator.objects or []) and CHAMBER_HEATER not in known:
            new.append(WondermakerChamberTarget(coordinator, CHAMBER_HEATER))
        for obj in coordinator.objects_with_prefix(("fan_generic ",)):
            if obj not in known:
                new.append(WondermakerGenericFan(coordinator, obj))
        if new:
            known.update(n.object_name for n in new)
            async_add_entities(new)

    _add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic))


class WondermakerNumber(WondermakerEntity, NumberEntity):
    entity_description: WMNumberDescription

    def __init__(self, coordinator: WondermakerCoordinator, description: WMNumberDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.gcode(self.entity_description.command_fn(value))
        except MoonrakerError as err:
            raise HomeAssistantError(f"Setzen fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()


class WondermakerObjectNumber(WondermakerEntity, NumberEntity):
    """Basis für automatisch entdeckte Klipper-Objekte."""

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, f"obj_{object_name.replace(' ', '_')}_set")
        self.object_name = object_name

    async def _gcode(self, script: str) -> None:
        try:
            await self.coordinator.client.gcode(script)
        except MoonrakerError as err:
            raise HomeAssistantError(f"Setzen fehlgeschlagen: {err}") from err
        await self.coordinator.async_request_refresh()


class WondermakerToolTarget(WondermakerObjectNumber):
    """Solltemperatur eines bestimmten Werkzeugkopfes."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 320
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "tool_target_temp"

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        match = re.match(r"extruder(\d*)$", object_name)
        self._attr_translation_placeholders = {"tool": f"T{match.group(1) or 0}"}

    @property
    def native_value(self) -> float | None:
        return get_status(self.coordinator.data, self.object_name, "target")

    async def async_set_native_value(self, value: float) -> None:
        await self._gcode(
            f"SET_HEATER_TEMPERATURE HEATER={self.object_name} TARGET={int(value)}"
        )


class WondermakerChamberTarget(WondermakerObjectNumber):
    """Solltemperatur der Bauraumheizung."""

    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_min_value = 0
    _attr_native_max_value = 60
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_translation_key = "chamber_target_temp"

    @property
    def native_value(self) -> float | None:
        return get_status(self.coordinator.data, self.object_name, "target")

    async def async_set_native_value(self, value: float) -> None:
        await self._gcode(f"SET_HEATER_TEMPERATURE HEATER=chamber TARGET={int(value)}")


class WondermakerGenericFan(WondermakerObjectNumber):
    """Frei steuerbarer Lüfter (fan_generic), z. B. auxiliary_fan, air_fan."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_translation_key = "fan_set"

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        self._fan = object_name.split(" ", 1)[1]
        self._attr_translation_placeholders = {
            "name": self._fan.replace("_", " ").title()
        }

    @property
    def native_value(self) -> float | None:
        value = get_status(self.coordinator.data, self.object_name, "speed")
        return None if value is None else round(value * 100)

    async def async_set_native_value(self, value: float) -> None:
        await self._gcode(f"SET_FAN_SPEED FAN={self._fan} SPEED={value / 100:.2f}")
