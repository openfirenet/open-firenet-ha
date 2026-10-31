"""The heating power as a number entity (issue #43) and the air flaps as ordinary sensors (issue #42)."""
from homeassistant.helpers import entity_registry as er


def _entry_of(hass, entry, unique_suffix):
    registry = er.async_get(hass)
    return next(
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if e.unique_id == f"{entry.entry_id}_{unique_suffix}"
    )


async def test_the_heating_power_shows_the_setting_and_sends_a_change(hass, bridge, setup_integration):
    entity = _entry_of(hass, setup_integration, "number_heating_power")
    state = hass.states.get(entity.entity_id)
    assert float(state.state) == bridge.state["controls"]["power_percent"]
    assert (state.attributes["min"], state.attributes["max"], state.attributes["step"]) == (30, 100, 5)

    await hass.services.async_call("number", "set_value", {"entity_id": entity.entity_id, "value": 85}, blocking=True)
    assert bridge.posts[-1] == {"power_percent": 85}


async def test_the_heating_power_survives_a_restart(hass, bridge, setup_integration, caplog):
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert "Removing orphaned" not in caplog.text
    assert _entry_of(hass, setup_integration, "number_heating_power")


async def test_the_air_flaps_are_ordinary_sensors(hass, bridge, setup_integration):
    # They are only created for a stove that reports them.
    bridge.state["sensors"]["air_flaps_percent"] = 81.0
    bridge.state["sensors"]["air_flaps_target_percent"] = 81.0
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    for key in ("air_flaps_percent", "air_flaps_target_percent"):
        assert _entry_of(hass, setup_integration, f"sensor_{key}").entity_category is None


async def test_an_air_flaps_sensor_that_exists_stays_when_the_bridge_has_no_value_yet(hass, bridge, setup_integration):
    # After a restart of the bridge the value can be missing for a while: the sensor must not be dropped (issue #65).
    bridge.state["sensors"]["air_flaps_percent"] = 81.0
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    entity = _entry_of(hass, setup_integration, "sensor_air_flaps_percent")

    del bridge.state["sensors"]["air_flaps_percent"]
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity.entity_id)
    assert state is not None
    # A registered entity that no platform provides any more is written as "restored" (shown as no longer provided).
    assert state.attributes.get("restored") is not True


async def test_an_optional_sensor_is_not_created_without_a_value(hass, bridge, setup_integration):
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", "open_firenet", f"{setup_integration.entry_id}_sensor_insertion_motor") is None
