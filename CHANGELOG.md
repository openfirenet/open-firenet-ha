# Changelog

## Non publié

### New
- **Eco Mode** switch, and an **Eco Mode Possible** sensor (Diagnostic), for the stoves that have an eco mode. The switch is unavailable while the stove says the mode is not possible. It needs a bridge firmware 3.0.0 or newer. (#68)

## Non publié

### Fixes
- Installing a bridge firmware update from Home Assistant is now refused unless the stove is off, like on the bridge's own page. It used to be allowed while the stove was in standby, where it can ignite at any time. (#66)

## v2.15.0 (2026-10-26)

### New
- **Split Log Operating Time** sensor for combined (pellet and split log) stoves, shown in hours. It needs a bridge firmware newer than 4.7.0, and exists only for a stove that reports some split log time: one that burns pellets alone does not get it. (#61)

## v2.14.0 (2026-10-22)

### Changes
- **Insertion Motor** and **Insertion Motor Current** now appear with the other sensors instead of under Diagnostic, and are no longer off by default (they still only exist on stoves that report them). The motor is shown in ‰ like on the stove's display, and both have an icon. If you had them disabled, enable them again in the entity list. (#57)

## v2.13.0 (2026-10-18)

### New
- Two diagnostic sensors, **Insertion Motor** and **Insertion Motor Current**, show the values the bridge reports for the insertion motor. They are off by default (enable them in the entity list) and only exist on stoves that report them. (#53)

## v2.12.0 (2026-10-15)

### New
- A **Firmware** entity tells you when a newer firmware of the bridge is published, with a link to its release notes. (#50)
- **Install the new firmware from Home Assistant**: the Install button of the Firmware entity downloads the release, checks its signature and checksum, and sends it to the bridge over Wi-Fi. If the bridge asks for an update password, enter it in the options of the integration. The bridge must be able to open a TCP connection back to Home Assistant, and the update is refused while the stove is burning. A bridge whose update slot is too small still needs one USB installation with the installer. (#50)

## v2.11.1 (2026-10-13)

### Fixes
- The logo at the top of the description shown in HACS was a broken image. (#46)

## v2.11.0 (2026-10-13)

### Breaking changes
- The **"Stove State" sensor** now gives a state key and Home Assistant shows it in your language. It used to give the English text in every language. **An automation or a template that compares its state with a text must be updated**: `Off` → `off`, `Standby` → `standby`, `Ignition` → `ignition`, `Flame Start` → `flame_start`, `Heating` → `heating`, `Grate Cleaning` → `cleaning`, `Burn Off` → `burn_off`, `Split Log` → `splitlog`, `Split Log Check` → `splitlog_check`, `Put On Split Logs` → `splitlog_refuel`, `Do Not Put Logs` → `splitlog_no_refuel`, `Unknown` → `unknown`. (openfirenet/open-firenet#105)

### New
- The states of the stove are translated in French, German and Italian.

## v2.10.0 (2026-10-13)

### New
- **Heating power** as a slider (30 to 100 %), next to the other settings of the stove. It was only reachable as the "fan mode" of the thermostat. (#43)

### Changes
- The **air flaps** sensors (position and target) are ordinary sensors and no longer filed under "Diagnostic". (#42)

## v2.9.0 (2026-10-12)

### New
- **Actual heating power**: a sensor with the power the stove really runs at. In comfort mode the stove sets it itself from the room temperature, so it differs from the power setting. It needs a bridge firmware later than 4.1.1.

## v2.8.0 (2026-10-11)

### Changes
- The MultiAir fans and their settings are now only created for a stove that has them: the models RIKA sells with MultiAir (DOMO, DOMO BACK, PARO, SONO, CONNECT, PRIMO MULTIAIR, SUMO MULTIAIR, ROCO MULTIAIR). They used to be created for every stove. **If your stove has MultiAir and is not one of these models, tick "My stove has MultiAir" in the options of the integration (Configure) to get them back.** On the other stoves they disappear at the update. (#33)

### Fixes
- The entities of the heating schedule (its times, its buttons and its pending indicator) were removed and created again each time Home Assistant started. They are now kept. (#33)

## v2.7.1 (2026-10-11)

### Fixes
- The integration could not be added, and showed "Unexpected error", with a stove on firmware 2.28: the bridge's answer carried a character that is not valid text. Such a character is now replaced by "�" and the state is read normally. The bridge itself is fixed in its next firmware. (#38)

## v2.7.0 (2026-10-09)

### Features
- The address of a bridge already added can be changed: menu ⋮ of the entry, "Reconfigure". Useful when your router gave the bridge another IP address: its entities, their history and your automations are kept. It used to require deleting the entry and adding it again.

### Fixes
- The bridge can be reached by its name `open-firenet.local` where Home Assistant runs in a container (Docker): the integration now uses Home Assistant's own connections, which resolve `.local` names. It used to answer "Cannot connect" there, and only the IP address worked.

## v2.6.0 (2026-10-08)

### Features
- Heating schedule: set the stove's weekly schedule from Home Assistant. Draw it as a Home Assistant schedule (Settings, Devices & services, Helpers, Schedule: a weekly grid), choose that schedule in the options of the integration, then press "Copy schedule to the stove" on the device page. The stove takes two time ranges per day; a day with more is refused with a message, and nothing is sent. (#31)
- Heating schedule, for automations: a start and an end time entity for each of the stove's slots, with "Send schedule to the stove" and "Discard schedule changes" buttons. These entities are disabled by default. (#31)

### Changes
- Ready for bridge firmware 4.0. A command sent while the stove is not ready yet (in the seconds after the bridge starts) is sent again once, and if it still cannot go through you get a clear message instead of a raw error. If the bridge refuses the name it is called by, the message says what to do and gives its IP address, when adding the integration as well as later. (openfirenet/open-firenet#77)

## v2.5.0 (2026-10-07)

### Features
- Italian translation (contributed by @lupin28).

## v2.4.2 (2026-10-05)

### Fixes
- The version shown by Home Assistant for the integration matches the installed release (v2.4.1 still reported 2.4.0).

## v2.4.1 (2026-10-04)

### Fixes
- The name is written "Open Firenet" everywhere, as on the logo, without the hyphen: device manufacturer and default device name, messages, documentation.
- Device info: when the bridge is not linked to the stove yet (open-firenet reports a null model and firmware version), the device shows "RIKA Unknown" and "MB ?" instead of "MB None".

## v2.4.0 (2026-09-30)

### Features
- New diagnostic sensors: error code, error sub-code and warning code.
- New air flap sensors (position and target, in %), created only on stoves that report them.
- New option (Settings > Devices & services > Open Firenet > Configure): pick a Home Assistant temperature sensor to show as the climate entity's current temperature, e.g. for a stove without a RIKA room sensor. Display only: the stove keeps regulating on its own sensor; use Home Assistant's Generic Thermostat or an automation to switch it on/off from that sensor.

### Fixes
- Stoves without a RIKA room sensor no longer report 102.4 °C: the room temperature is now unknown.

Requires open-firenet firmware with the new `/api/state` fields (`warning_code`, `air_flaps_percent`, `room_sensor_connected`) for the warning and air flap sensors.
