"""Konstanten für die WonderMaker-Integration."""

import re

DOMAIN = "wondermaker"

CONF_API_KEY = "api_key"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_FINISH_TIME_ENABLED = "finish_time_enabled"
CONF_FINISH_TIME_INTERVAL = "finish_time_interval"
CONF_LAYER_ENABLED = "layer_enabled"
CONF_LAYER_INTERVAL = "layer_interval"
CONF_NOTIFY_ENABLED = "notify_enabled"
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_NOTIFY_IMAGE = "notify_with_image"
CONF_NOTIFY_DELAY = "notify_snapshot_delay"
CONF_NOTIFY_ERROR = "notify_error"
CONF_NOTIFY_ERROR_IMAGE = "notify_error_image"
CONF_NOTIFY_FILAMENT = "notify_filament"
CONF_NOTIFY_DOOR = "notify_door"

DEFAULT_PORT = 7125
DEFAULT_SCAN_INTERVAL = 5
# Sekunden zwischen Aktualisierungen von „Voraussichtlich fertig" (0 = aus)
DEFAULT_FINISH_TIME_INTERVAL = 300
# Sekunden zwischen Aktualisierungen der Schichtanzeige (0 = aus)
DEFAULT_LAYER_INTERVAL = 60
# Sekunden Wartezeit nach Druckende bis zum Foto (Werkzeug soll erst wegfahren)
DEFAULT_NOTIFY_DELAY = 5

EVENT_PRINT_FINISHED = "wondermaker_print_finished"
EVENT_ERROR = "wondermaker_error"
EVENT_FILAMENT_RUNOUT = "wondermaker_filament_runout"
EVENT_DOOR_OPENED = "wondermaker_door_opened"

MANUFACTURER = "WonderMaker"
MODEL = "ZR Ultra S"

# Klipper-Objekte, die (wenn vorhanden) bei jedem Update abgefragt werden
BASE_OBJECTS = (
    "extruder",
    "heater_bed",
    "print_stats",
    "virtual_sdcard",
    "display_status",
    "fan",
    "gcode_move",
    "toolhead",
    "idle_timeout",
)

# extruder, extruder1, extruder2, ... (Toolchanger)
EXTRUDER_RE = re.compile(r"^extruder(\d*)$")
# Status-LEDs an den Werkzeugköpfen – keine Raumbeleuchtung, werden ignoriert
TOOL_LED_RE = re.compile(r"T\d+_RGB$", re.IGNORECASE)

CHAMBER_HEATER = "heater_generic chamber"

TEMP_PREFIXES = ("temperature_sensor ", "temperature_fan ", "heater_generic ")
FILAMENT_PREFIXES = ("filament_switch_sensor ", "filament_motion_sensor ")
BUTTON_PREFIX = "gcode_button "
FAN_PREFIXES = ("fan_generic ", "controller_fan ", "heater_fan ")
LED_PREFIXES = ("led ", "neopixel ", "dotstar ")
PIN_PREFIX = "output_pin "
LIGHT_PIN_HINTS = ("light", "led", "lamp", "licht")

DISCOVER_PREFIXES = (
    TEMP_PREFIXES
    + FILAMENT_PREFIXES
    + (BUTTON_PREFIX,)
    + FAN_PREFIXES
    + LED_PREFIXES
    + (PIN_PREFIX,)
)
