"""The power switch and the target temperature sensor (issue #81)."""
from homeassistant.helpers import entity_registry as er


def _entity_id(hass, entry, domain, suffix):
    registry = er.async_get(hass)
    return registry.async_get_entity_id(domain, "open_firenet", f"{entry.entry_id}_{suffix}")


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_the_power_switch_follows_the_stove(hass, bridge, setup_integration):
    bridge.state["controls"]["on"] = True
    await _reload(hass, setup_integration)
    switch = _entity_id(hass, setup_integration, "switch", "switch_power")
    assert hass.states.get(switch).state == "on"


async def test_the_power_switch_sends_on_and_off(hass, bridge, setup_integration):
    switch = _entity_id(hass, setup_integration, "switch", "switch_power")
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch}, blocking=True)
    assert bridge.posts[-1] == {"on": True}
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert bridge.posts[-1] == {"on": False}
    assert hass.states.get(switch).state == "off"


async def test_the_power_switch_survives_a_restart(hass, bridge, setup_integration):
    await _reload(hass, setup_integration)
    assert _entity_id(hass, setup_integration, "switch", "switch_power") is not None


async def test_the_target_temperature_sensor_gives_the_comfort_target(hass, bridge, setup_integration):
    bridge.state["controls"]["target_temperature"] = 21.5
    await _reload(hass, setup_integration)
    sensor = _entity_id(hass, setup_integration, "sensor", "sensor_target_temperature")
    state = hass.states.get(sensor)
    assert float(state.state) == 21.5
    assert state.attributes["unit_of_measurement"] == "°C"
