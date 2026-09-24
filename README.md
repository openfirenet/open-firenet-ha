# Open Firenet — Home Assistant Integration

<p align="center">
  <img src="custom_components/open_firenet/brand/logo.png" alt="Open Firenet Logo" width="400">
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Custom Home Assistant integration for RIKA pellet stoves controlled via the [open-firenet](https://github.com/openfirenet/open-firenet) WiFi bridge.

## Features

- **Thermostat Control**: Power on/off, target room temperature, operating mode presets (*Manual*, *Auto*, *Comfort*), and heating power (30%–100%).
- **MultiAir 1 & 2 Fan Controls**: Dedicated fan entities for MultiAir convection fans with on/off, Auto regulation, and manual speeds 1 to 5 (automatically enabled for MultiAir-equipped models).
- **MultiAir Convection Trim**: Number sliders for -30% to +30% fine tuning of convection output.
- **Weekly Heating Schedule**: Enable or disable the stove's internal weekly heating schedule via a switch, and adjust the setback temperature (10°C–25°C).
- **Hopper Lid Sensor**: Real-time detection when the pellet hopper lid is opened.
- **Full Sensor Telemetry**: Room temperature, combustion chamber temperature, mainboard temperature, pellet consumption counters, service countdown, draft and auger RPMs, operating state, and WiFi signal strength.
- **27 RIKA Stove Models**: Automatic model detection and naming in device registry (DOMO, PARO, SUMO, FILO, COMO, etc.).

---

## Requirements

- An ESP32 running [Open-Firenet firmware](https://github.com/openfirenet/open-firenet) (v2.0+ or v2.3.0+ for MultiAir & Schedule), connected to your RIKA stove and WiFi network.
- Home Assistant 2024.1 or later.
- HACS (recommended) or manual installation.

---

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations** → ⋮ (overflow menu) → **Custom repositories**.
2. Add `https://github.com/openfirenet/open-firenet-ha` with category **Integration**.
3. Search for **Open Firenet** and click **Download**.
4. Restart Home Assistant.

### Manual Installation

Copy the `custom_components/open_firenet/` directory into your Home Assistant `<config>/custom_components/` folder and restart Home Assistant.

---

## Configuration

1. In Home Assistant, go to **Settings** → **Devices & Services** → **Add Integration**.
2. Search for **Open Firenet**.
3. Enter the IP address or hostname of your Open-Firenet bridge (e.g. `192.168.1.93` or `open-firenet.local`) and the desired poll interval (default: 30 seconds).

---

## Entities

### Climate
| Entity ID | Name | Description |
|---|---|---|
| `climate.open_firenet` | Open-Firenet | Main thermostat: target temperature (14–28°C), HVAC mode (`heat`/`off`), preset mode (`manual`, `auto`, `comfort`), heating power (30–100%) |

### Fan *(MultiAir models only: DOMO, PARO, PRIMO MULTIAIR, DOMO BACK, SUMO MULTIAIR, ROCO MULTIAIR)*
| Entity ID | Name | Description |
|---|---|---|
| `fan.open_firenet_multiair_1` | MultiAir 1 | Convection fan 1: On/Off, Preset modes (`auto`, `1`..`5`), Speed percentage (20%–100%) |
| `fan.open_firenet_multiair_2` | MultiAir 2 | Convection fan 2: On/Off, Preset modes (`auto`, `1`..`5`), Speed percentage (20%–100%) |

### Switch
| Entity ID | Name | Description |
|---|---|---|
| `switch.open_firenet_heating_schedule` | Heating Schedule | Toggle the stove's internal weekly heating schedule on or off |
| `switch.open_firenet_frost_protection` | Frost Protection | Toggle stove frost protection mode on or off |

### Number
| Entity ID | Name | Description | Range |
|---|---|---|---|
| `number.open_firenet_setback_temperature` | Setback Temperature | Maintenance temperature when heating times are inactive | 10.0°C – 25.0°C (step 0.5) |
| `number.open_firenet_frost_protection_temperature` | Frost Protection Temperature | Target temperature maintained when frost protection is active | 4.0°C – 10.0°C (step 1.0) |
| `number.open_firenet_bake_target_temperature` | Bake Target Temperature | Baking oven chamber target temperature *(DOMO BACK model 23)* | 130°C – 340°C (step 5) |
| `number.open_firenet_room_temperature_offset` | Room Temperature Offset | Room temperature sensor calibration offset | -4.0°C – +4.0°C (step 0.1) |
| `number.open_firenet_multiair_1_convection_trim` | MultiAir 1 Convection Trim | Fan 1 convection speed trim *(MultiAir models)* | -30% to +30% (step 5) |
| `number.open_firenet_multiair_2_convection_trim` | MultiAir 2 Convection Trim | Fan 2 convection speed trim *(MultiAir models)* | -30% to +30% (step 5) |

### Binary Sensors
| Entity ID | Name | Device Class | Description |
|---|---|---|---|
| `binary_sensor.open_firenet_connected` | Connected | `connectivity` | Serial communication active between bridge and stove |
| `binary_sensor.open_firenet_combustion_active` | Combustion Active | — | Stove is actively burning pellets / flame present |
| `binary_sensor.open_firenet_stove_error` | Stove Error | `problem` | Stove reports an error state |
| `binary_sensor.open_firenet_pellet_hopper_lid` | Pellet Hopper Lid | `door` | Open (`on`) when pellet hopper lid is raised |

### Sensors
| Entity ID | Name | Unit | Description |
|---|---|---|---|
| `sensor.open_firenet_room_temperature` | Room Temperature | °C | Current ambient room temperature |
| `sensor.open_firenet_combustion_chamber_temperature` | Combustion Chamber Temperature | °C | Flame / combustion chamber temperature |
| `sensor.open_firenet_board_temperature` | Mainboard Temperature | °C | Stove motherboard temperature |
| `sensor.open_firenet_pellets_consumed` | Pellets Consumed | kg | Total cumulative pellets burned |
| `sensor.open_firenet_pellet_operating_hours` | Pellet Operating Hours | h | Total runtime in pellet mode |
| `sensor.open_firenet_service_countdown` | Service Countdown | kg | Remaining kg before scheduled maintenance |
| `sensor.open_firenet_flue_draft_fan_speed` | Flue Draft Fan Speed | RPM | Exhaust draft fan speed |
| `sensor.open_firenet_pellet_auger_speed` | Pellet Auger Speed | RPM | Auger feeder motor speed |
| `sensor.open_firenet_stove_state` | Stove State | — | Human-readable operating state (OFF, IGNITION, BURNING, etc.) |
| `sensor.open_firenet_wifi_signal_strength` | WiFi Signal Strength | dBm | Open-Firenet bridge RSSI |
| `sensor.open_firenet_uptime` | Uptime | s | ESP32 uptime in seconds |

---

## Supported Stove Models

Open-Firenet automatically identifies the stove model via mainboard query and displays the commercial model in Home Assistant device information:

- **MultiAir supported models**: DOMO (13), PARO (17), PRIMO MULTIAIR (29), DOMO BACK (23), SUMO MULTIAIR (25), ROCO MULTIAIR (4)
- **Natural convection models**: INDUO (1), TOPO (2), ROCO (3), ROCO RAO (5), KAPO (6), MIRO (7), COMO (8), REVO (9), INTERNO (10), FILO (11), SUMO (12), CORSO (14), INDUO II (15), REVIVO (16), LIVO (18), COMO II (19), REVO II (20), COSMO (21), SONO (22), PK E (24), CONNECT (26)

---

## License

MIT License. See [LICENSE](LICENSE) for details.
