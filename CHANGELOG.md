# Changelog

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
