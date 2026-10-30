"""Sensoren des WonderMaker."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    CHAMBER_HEATER,
    CONF_FINISH_TIME_ENABLED,
    CONF_FINISH_TIME_INTERVAL,
    DEFAULT_FINISH_TIME_INTERVAL,
    DEFAULT_LAYER_INTERVAL,
    FAN_PREFIXES,
    TEMP_PREFIXES,
)
from .coordinator import WondermakerCoordinator, get_status
from .entity import WondermakerEntity
from .util import interval_option

PRINT_STATES = ["standby", "printing", "paused", "complete", "cancelled", "error"]


def _active_tool(data: dict[str, Any]) -> str:
    return get_status(data, "toolhead", "extruder", "extruder")


def _tool_label(obj: str) -> str:
    match = re.match(r"extruder(\d*)$", obj)
    return f"T{match.group(1) or 0}" if match else obj


def _progress(data: dict[str, Any]) -> float | None:
    # display_status.progress ist 0, solange der Slicer kein M73 sendet
    value = get_status(data, "display_status", "progress")
    if not value:
        value = get_status(data, "virtual_sdcard", "progress", value)
    return value


def _total_layers(data: dict[str, Any]) -> int | None:
    if data.get("layer_interval", 1) == 0:  # Schichtanzeige ausgeschaltet
        return None
    value = (get_status(data, "print_stats", "info") or {}).get("total_layer")
    if value is None:
        value = data.get("metadata", {}).get("layer_count")
    return None if value is None else int(value)


def _current_layer(data: dict[str, Any]) -> int | None:
    """Wie Fluidd: aus Klipper, sonst aus der Z-Höhe geschätzt."""
    state = get_status(data, "print_stats", "state")
    total = _total_layers(data)
    reported = (get_status(data, "print_stats", "info") or {}).get("current_layer")
    if reported is not None:
        return int(reported)
    if state == "complete":
        return total
    if state not in ("printing", "paused"):
        return None
    meta = data.get("metadata", {})
    layer_height = meta.get("layer_height")
    if not layer_height:
        return None
    first = meta.get("first_layer_height") or layer_height
    pos = get_status(data, "gcode_move", "gcode_position")
    if not pos or len(pos) < 3 or pos[2] is None:
        return None
    layer = int((pos[2] - first) / layer_height + 1.0001)
    layer = max(layer, 0)
    return min(layer, total) if total else layer


def _remaining_seconds(data: dict[str, Any]) -> float | None:
    if get_status(data, "print_stats", "state") != "printing":
        return None
    progress = _progress(data)
    duration = get_status(data, "print_stats", "print_duration")
    if not progress or progress < 0.01 or duration is None:
        return None
    return max(0.0, duration / progress - duration)


def _finish_time(data: dict[str, Any]) -> datetime | None:
    remaining = _remaining_seconds(data)
    if remaining is None:
        return None
    return dt_util.utcnow() + timedelta(seconds=remaining)


def _non_negative(value: float | None) -> float | None:
    """Klipper zählt Rückzüge mit – am Druckanfang kann der Wert kurz negativ sein."""
    return None if value is None else max(0.0, value)


def _percent(data: dict[str, Any], obj: str, key: str) -> float | None:
    value = get_status(data, obj, key)
    return None if value is None else round(value * 100, 1)


def _mem_percent(data: dict[str, Any]) -> float | None:
    mem = data.get("proc", {}).get("system_memory")
    if not mem or not mem.get("total"):
        return None
    used = mem.get("used")
    if used is None and mem.get("available") is not None:
        used = mem["total"] - mem["available"]
    return None if used is None else round(used / mem["total"] * 100, 1)


@dataclass(frozen=True, kw_only=True)
class WMSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[WMSensorDescription, ...] = (
    WMSensorDescription(
        key="print_state",
        translation_key="print_state",
        device_class=SensorDeviceClass.ENUM,
        options=PRINT_STATES,
        value_fn=lambda d: get_status(d, "print_stats", "state"),
    ),
    WMSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: None if _progress(d) is None else round(_progress(d) * 100, 1),
    ),
    WMSensorDescription(
        key="filename",
        translation_key="filename",
        value_fn=lambda d: get_status(d, "print_stats", "filename") or None,
    ),
    WMSensorDescription(
        key="print_duration",
        translation_key="print_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=lambda d: get_status(d, "print_stats", "print_duration"),
    ),
    WMSensorDescription(
        key="time_remaining",
        translation_key="time_remaining",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value_fn=_remaining_seconds,
    ),
    WMSensorDescription(
        key="total_layers",
        translation_key="total_layers",
        value_fn=_total_layers,
    ),
    WMSensorDescription(
        key="filament_used",
        translation_key="filament_used",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        suggested_unit_of_measurement=UnitOfLength.METERS,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _non_negative(get_status(d, "print_stats", "filament_used")),
    ),
    WMSensorDescription(
        key="active_tool",
        translation_key="active_tool",
        value_fn=lambda d: _tool_label(_active_tool(d)),
    ),
    WMSensorDescription(
        key="nozzle_temperature",
        translation_key="nozzle_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: get_status(d, _active_tool(d), "temperature"),
    ),
    WMSensorDescription(
        key="nozzle_target",
        translation_key="nozzle_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: get_status(d, _active_tool(d), "target"),
    ),
    WMSensorDescription(
        key="bed_temperature",
        translation_key="bed_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: get_status(d, "heater_bed", "temperature"),
    ),
    WMSensorDescription(
        key="bed_target",
        translation_key="bed_target",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: get_status(d, "heater_bed", "target"),
    ),
    WMSensorDescription(
        key="part_fan",
        translation_key="part_fan",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: _percent(d, "fan", "speed"),
    ),
    WMSensorDescription(
        key="speed_factor",
        translation_key="speed_factor",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _percent(d, "gcode_move", "speed_factor"),
    ),
    WMSensorDescription(
        key="flow_factor",
        translation_key="flow_factor",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda d: _percent(d, "gcode_move", "extrude_factor"),
    ),
    WMSensorDescription(
        key="z_height",
        translation_key="z_height",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
        value_fn=lambda d: (
            (get_status(d, "toolhead", "position") or [None] * 3)[2]
        ),
    ),
    WMSensorDescription(
        key="klippy_state",
        translation_key="klippy_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("klippy_state"),
    ),
    WMSensorDescription(
        key="klipper_version",
        translation_key="klipper_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.get("printer_info", {}).get("software_version"),
    ),
    WMSensorDescription(
        key="host_cpu",
        translation_key="host_cpu",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: (d.get("proc", {}).get("system_cpu_usage") or {}).get("cpu"),
    ),
    WMSensorDescription(
        key="host_memory",
        translation_key="host_memory",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_mem_percent,
    ),
    WMSensorDescription(
        key="host_temperature",
        translation_key="host_temperature",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.get("proc", {}).get("cpu_temp"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: WondermakerCoordinator = entry.runtime_data
    async_add_entities(WondermakerSensor(coordinator, d) for d in SENSORS)
    async_add_entities(
        [WondermakerFinishTimeSensor(coordinator), WondermakerLayerSensor(coordinator)]
    )

    known: set[str] = set()

    @callback
    def _add_dynamic() -> None:
        new: list[WondermakerObjectSensor] = []
        for obj in coordinator.tool_objects:
            if obj not in known:
                new.append(WondermakerToolSensor(coordinator, obj))
        for obj in coordinator.objects_with_prefix(TEMP_PREFIXES):
            if obj not in known:
                new.append(WondermakerTempSensor(coordinator, obj))
        for obj in coordinator.objects_with_prefix(FAN_PREFIXES):
            if obj not in known:
                new.append(WondermakerFanSensor(coordinator, obj))
        if new:
            known.update(s.object_name for s in new)
            async_add_entities(new)

    _add_dynamic()
    entry.async_on_unload(coordinator.async_add_listener(_add_dynamic))


class WondermakerSensor(WondermakerEntity, SensorEntity):
    entity_description: WMSensorDescription

    def __init__(self, coordinator: WondermakerCoordinator, description: WMSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except (TypeError, IndexError, KeyError):
            return None


class WondermakerFinishTimeSensor(WondermakerEntity, SensorEntity):
    """Voraussichtliches Druckende – wird nur im eingestellten Intervall neu berechnet.

    Intervall (Sekunden) in den Integrationsoptionen; 0 = Sensor liefert keinen Wert.
    Sofort aktualisiert wird beim Start eines Drucks und wenn er endet.
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "finish_time"

    def __init__(self, coordinator: WondermakerCoordinator) -> None:
        super().__init__(coordinator, "finish_time")
        self._value: datetime | None = None
        self._published_at: datetime | None = None
        self._file: str | None = None
        self._recompute(coordinator.data, dt_util.utcnow())

    @property
    def _interval(self) -> int:
        return interval_option(
            self.coordinator.config_entry.options,
            CONF_FINISH_TIME_ENABLED,
            CONF_FINISH_TIME_INTERVAL,
            DEFAULT_FINISH_TIME_INTERVAL,
        )

    def _recompute(self, data: dict[str, Any], now: datetime) -> None:
        estimate = _finish_time(data) if self._interval > 0 else None
        file = get_status(data, "print_stats", "filename") or None

        if estimate is None:
            # Druck läuft nicht (oder Sensor ausgeschaltet)
            self._value = None
            self._published_at = None
        elif (
            self._value is None
            or file != self._file
            or self._published_at is None
            or (now - self._published_at).total_seconds() >= self._interval
        ):
            self._value = estimate
            self._published_at = now
        self._file = file

    @callback
    def _handle_coordinator_update(self) -> None:
        self._recompute(self.coordinator.data, dt_util.utcnow())
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> datetime | None:
        return self._value


class WondermakerLayerSensor(WondermakerEntity, SensorEntity):
    """Aktuelle Schicht – ruhig statt flackernd.

    * Z-Hub (Düse hebt kurz ab) würde sonst „Schichten“ vortäuschen: eine höhere Schicht
      muss in zwei Abfragen hintereinander gemessen werden, und der Wert sinkt nie.
    * Aktualisiert wird höchstens im eingestellten Intervall (0 = aus).
    * Beim Start eines Drucks und bei „fertig“ wird sofort aktualisiert.
    """

    _attr_translation_key = "current_layer"

    def __init__(self, coordinator: WondermakerCoordinator) -> None:
        super().__init__(coordinator, "current_layer")
        self._value: int | None = None
        self._published_at: datetime | None = None
        self._file: str | None = None
        self._pending: int | None = None
        self._pending_n = 0
        self._recompute(coordinator.data, dt_util.utcnow())

    def _recompute(self, data: dict[str, Any], now: datetime) -> None:
        interval = int(data.get("layer_interval", DEFAULT_LAYER_INTERVAL))
        raw = _current_layer(data) if interval > 0 else None
        file = get_status(data, "print_stats", "filename") or None
        state = get_status(data, "print_stats", "state")

        if raw is None or file != self._file:
            self._value = None
            self._published_at = None
            self._pending = None
            self._pending_n = 0
        self._file = file
        if raw is None:
            return

        if state == "complete" or self._value is None:
            self._value = raw
            self._published_at = now
            return
        if raw > self._value:
            if raw == self._pending:
                self._pending_n += 1
            else:
                self._pending, self._pending_n = raw, 1
            if (
                self._pending_n >= 2
                and (now - (self._published_at or now)).total_seconds() >= interval
            ):
                self._value = raw
                self._published_at = now
                self._pending, self._pending_n = None, 0
        else:
            self._pending, self._pending_n = None, 0

    @callback
    def _handle_coordinator_update(self) -> None:
        self._recompute(self.coordinator.data, dt_util.utcnow())
        super()._handle_coordinator_update()

    @property
    def native_value(self) -> int | None:
        return self._value


class WondermakerObjectSensor(WondermakerEntity, SensorEntity):
    """Basis für automatisch entdeckte Klipper-Objekte."""

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, f"obj_{object_name.replace(' ', '_')}")
        self.object_name = object_name

    @staticmethod
    def pretty(object_name: str) -> str:
        return object_name.split(" ", 1)[-1].replace("_", " ").title()


class WondermakerTempSensor(WondermakerObjectSensor):
    """Temperatursensoren und Heizer (Bauraum usw.)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        if object_name == CHAMBER_HEATER:
            self._attr_translation_key = "chamber_temperature"
        else:
            self._attr_name = self.pretty(object_name)

    @property
    def native_value(self) -> float | None:
        return get_status(self.coordinator.data, self.object_name, "temperature")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        target = get_status(self.coordinator.data, self.object_name, "target")
        return None if target is None else {"target": target}


class WondermakerToolSensor(WondermakerObjectSensor):
    """Temperatur je Werkzeugkopf (T0..T3)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_translation_key = "tool_temperature"

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        self._attr_translation_placeholders = {"tool": _tool_label(object_name)}

    @property
    def native_value(self) -> float | None:
        return get_status(self.coordinator.data, self.object_name, "temperature")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "target": get_status(data, self.object_name, "target"),
            "power": get_status(data, self.object_name, "power"),
            "active": _active_tool(data) == self.object_name,
        }


class WondermakerFanSensor(WondermakerObjectSensor):
    """Lüfterdrehzahl in Prozent."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _attr_translation_key = "fan_speed"

    def __init__(self, coordinator: WondermakerCoordinator, object_name: str) -> None:
        super().__init__(coordinator, object_name)
        self._attr_translation_placeholders = {"name": self.pretty(object_name)}
        # Nur die frei steuerbaren Lüfter standardmäßig anzeigen
        self._attr_entity_registry_enabled_default = object_name.startswith("fan_generic ")

    @property
    def native_value(self) -> float | None:
        value = get_status(self.coordinator.data, self.object_name, "speed")
        return None if value is None else round(value * 100)
