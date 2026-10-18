"""Warning / error / air flap sensors, the "no room sensor" value and the external temperature option."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.open_firenet.const import CONF_EXTERNAL_TEMP_SENSOR, DOMAIN


async def _setup(hass, bridge, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass, entry, platform, unique_suffix):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{unique_suffix}")


async def test_warning_error_and_air_flap_sensors(hass, bridge):
    bridge.state["stove"].update({"error_code": 4, "error_sub": 2, "warning_code": 32})
    bridge.state["sensors"].update({"air_flaps_percent": 81.0, "air_flaps_target_percent": 50.0})
    entry = await _setup(hass, bridge)

    def value(key):
        return hass.states.get(_entity_id(hass, entry, "sensor", f"sensor_{key}")).state

    assert value("error_code") == "4"
    assert value("error_sub") == "2"
    assert value("warning_code") == "32"
    assert value("air_flaps_percent") == "81.0"
    assert value("air_flaps_target_percent") == "50.0"


async def test_air_flap_and_warning_sensors_not_created_when_not_reported(hass, bridge):
    entry = await _setup(hass, bridge)  # INITIAL_STATE has no air flaps / warning (older firmware)
    assert _entity_id(hass, entry, "sensor", "sensor_air_flaps_percent") is None
    assert _entity_id(hass, entry, "sensor", "sensor_warning_code") is None
    assert _entity_id(hass, entry, "sensor", "sensor_error_code") is not None


async def test_room_temperature_unavailable_without_room_sensor(hass, bridge):
    bridge.state["sensors"].update({"room_temperature": None, "room_sensor_connected": False})
    entry = await _setup(hass, bridge)
    room = hass.states.get(_entity_id(hass, entry, "sensor", "sensor_room_temperature"))
    climate = hass.states.get(_entity_id(hass, entry, "climate", "climate"))
    assert room.state == "unknown"
    assert climate.attributes.get("current_temperature") is None


async def test_room_temperature_102_4_from_older_firmware_is_ignored(hass, bridge):
    bridge.state["sensors"]["room_temperature"] = 102.4
    entry = await _setup(hass, bridge)
    room = hass.states.get(_entity_id(hass, entry, "sensor", "sensor_room_temperature"))
    assert room.state == "unknown"


async def test_climate_uses_external_temperature_sensor(hass, bridge):
    hass.states.async_set("sensor.living_room", "19.5", {"device_class": "temperature"})
    entry = await _setup(hass, bridge, {CONF_EXTERNAL_TEMP_SENSOR: "sensor.living_room"})
    climate_id = _entity_id(hass, entry, "climate", "climate")
    assert hass.states.get(climate_id).attributes["current_temperature"] == 19.5

    # follows the external sensor right away, without waiting for the next bridge poll
    hass.states.async_set("sensor.living_room", "20.1", {"device_class": "temperature"})
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).attributes["current_temperature"] == 20.1

    # external sensor unavailable -> falls back to the stove's own room temperature
    hass.states.async_set("sensor.living_room", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).attributes["current_temperature"] == 20.0


async def test_options_flow_sets_external_sensor(hass, bridge):
    hass.states.async_set("sensor.living_room", "19.5", {"device_class": "temperature"})
    entry = await _setup(hass, bridge)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_EXTERNAL_TEMP_SENSOR: "sensor.living_room"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_EXTERNAL_TEMP_SENSOR] == "sensor.living_room"
    climate_id = _entity_id(hass, entry, "climate", "climate")
    assert hass.states.get(climate_id).attributes["current_temperature"] == 19.5


async def test_insertion_motor_sensors_from_raw_values_and_off_by_default(hass, bridge):
    bridge.state["raw_sensors"] = {"insertionMotor": 226, "insertionCurrent": 21}
    entry = await _setup(hass, bridge)
    registry = er.async_get(hass)
    for key, expected in (("insertion_motor", "226"), ("insertion_motor_current", "21")):
        entity_id = _entity_id(hass, entry, "sensor", f"sensor_{key}")
        assert entity_id is not None
        reg_entry = registry.async_get(entity_id)
        assert reg_entry.disabled_by == er.RegistryEntryDisabler.INTEGRATION
        assert reg_entry.entity_category == "diagnostic"


async def test_insertion_motor_sensors_not_created_when_not_reported(hass, bridge):
    bridge.state["raw_sensors"] = {}
    entry = await _setup(hass, bridge)
    assert _entity_id(hass, entry, "sensor", "sensor_insertion_motor") is None
    assert _entity_id(hass, entry, "sensor", "sensor_insertion_motor_current") is None
