<p align="center"><img src="custom_components/wondermaker/brand/logo@2x.png" alt="WonderMaker" width="420"></p>

# WonderMaker for Home Assistant

Local Home Assistant integration for **WonderMaker ZR series printers** (tested with the *ZR Ultra S*, a 4-tool Klipper toolchanger). It talks to the printer's **Moonraker API** (port 7125). No cloud, no account.

> **Unofficial community project.** Not affiliated with, endorsed by or supported by WonderMaker. "WonderMaker" is a trademark of its respective owner and is used here only to describe compatibility. The icon in this repository is an original neutral design.

*Deutsche Anleitung: [README.de.md](README.de.md)*

## Features

| Platform | What you get |
|---|---|
| Sensor | print state, progress, file name, print duration, time remaining, estimated finish, **current/total layer**, filament used, **active tool**, nozzle temperature (active tool), **temperature per tool T0–T3**, **chamber temperature**, bed, fans, speed/flow factor, Z height, host diagnostics |
| Binary sensor | printing, paused, error, Klipper connected, **filament per tool**, **tool docked**, filament paths, tool changer sensors, **door switches** |
| Button | pause, resume, cancel, home, emergency stop, firmware/Klipper restart |
| Number | target temperatures (active tool, **per tool**, bed, **chamber**), speed/flow factor, part fan, **auxiliary/air fans** |
| Light | only if Klipper exposes a chamber light (`output_pin`/`led` with "light", "led" or "lamp" in its name) |
| Camera | webcam from Moonraker (snapshot + MJPEG stream) |
| Image | thumbnail of the current print, **photo taken when the last print finished** |
| Services | `wondermaker.send_gcode`, `wondermaker.start_print` |

Entities are discovered from Klipper, so printers with a different tool count or extra sensors work too.

## Installation

### HACS (recommended)
1. HACS → ⋮ → *Custom repositories* → add this repository, category **Integration**.
2. Install **WonderMaker**, restart Home Assistant.
3. *Settings → Devices & services → Add integration → WonderMaker*.

### Manual
Copy `custom_components/wondermaker` to `/config/custom_components/`, restart, add the integration.

Enter the printer's IP and port `7125`. An API key is only needed if Moonraker rejects your Home Assistant's IP (`trusted_clients` in `moonraker.conf`).

## Notifications
*Settings → Devices & services → WonderMaker → Configure → Notifications*

Pick the `notify` services to send to (e.g. the Companion app of your phone), then switch on what you want to be told about:

| Switch | When | Photo |
|---|---|---|
| Print finished | a print ends successfully | optional switch (taken after a short delay) |
| Error | a print is aborted by an error, or Klipper goes into shutdown/error (message is included) | optional switch (taken immediately) |
| Filament runout | during a print, the sensors of the **active tool** report no filament (debounced) | no |
| Door opened | during a print, **all** door switches are open | no |

Errors and filament runout are sent as time-sensitive/high-priority messages. Door switches are read as: pressed = closed, released = open.

Every event also fires a Home Assistant event (`wondermaker_print_finished`, `wondermaker_error`, `wondermaker_filament_runout`, `wondermaker_door_opened`) for your own automations. Photos are available as the image entities *Photo of last print* and *Photo of last error*. The button *Send test notification* on the device page sends a test message with a current camera image.

## Options (per printer)
*Settings → Devices & services → WonderMaker → Configure*
- **Polling interval** (default 5 s): how often the printer is queried.
- **Show layers** (switch) and **Update interval for the layer display** (default 60 s): the current layer is shown calmly – it never jumps back, short Z-lifts are ignored, and it updates at most at this interval (immediately when a print starts or ends). Switch off and the layer sensors show no value.
- **Show estimated finish** (switch) and **Update interval for "Estimated finish"** (default 300 s): the finish time changes with every poll, which floods the history/logbook. It is now recalculated only at this interval (and immediately when a print starts or ends). Switch off and the sensor shows no value.

## Notes
- Layer numbers use the file metadata; if your slicer sends `SET_PRINT_STATS_INFO`, those values take precedence.
- Emergency stop, cancel and the temperature entities act immediately on the printer – use them carefully in automations.
- Not tested on other models yet. Feedback and logs are welcome via issues.

## License
MIT
