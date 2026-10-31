"""The eco mode switch and the "eco mode possible" sensor (issue #68)."""
from homeassistant.helpers import entity_registry as er


def _entity_id(hass, entry, domain, suffix):
    registry = er.async_get(hass)
    return registry.async_get_entity_id(domain, "open_firenet", f"{entry.entry_id}_{suffix}")


async def _reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def test_the_switch_follows_the_stove_when_the_eco_mode_is_possible(hass, bridge, setup_integration):
    bridge.state["controls"].update({"eco_mode": True, "eco_mode_possible": True})
    await _reload(hass, setup_integration)
    switch = _entity_id(hass, setup_integration, "switch", "switch_eco_mode")
    assert hass.states.get(switch).state == "on"
    possible = _entity_id(hass, setup_integration, "binary_sensor", "eco_mode_possible")
    assert hass.states.get(possible).state == "on"


async def test_turning_the_switch_off_sends_the_command(hass, bridge, setup_integration):
    bridge.state["controls"].update({"eco_mode": True, "eco_mode_possible": True})
    await _reload(hass, setup_integration)
    switch = _entity_id(hass, setup_integration, "switch", "switch_eco_mode")
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert bridge.posts[-1] == {"ecoMode": False}
    assert hass.states.get(switch).state == "off"


async def test_the_switch_is_unavailable_when_the_eco_mode_is_not_possible(hass, bridge, setup_integration):
    bridge.state["controls"].update({"eco_mode": False, "eco_mode_possible": False})
    await _reload(hass, setup_integration)
    switch = _entity_id(hass, setup_integration, "switch", "switch_eco_mode")
    assert hass.states.get(switch).state == "unavailable"
    possible = _entity_id(hass, setup_integration, "binary_sensor", "eco_mode_possible")
    assert hass.states.get(possible).state == "off"


async def test_the_switch_is_available_to_turn_off_when_eco_mode_is_not_possible(hass, bridge, setup_integration):
    bridge.state["controls"].update({"eco_mode": True, "eco_mode_possible": False})
    await _reload(hass, setup_integration)
    switch = _entity_id(hass, setup_integration, "switch", "switch_eco_mode")
    assert hass.states.get(switch).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch}, blocking=True)
    assert bridge.posts[-1] == {"ecoMode": False}


async def test_an_older_bridge_without_the_values_leaves_the_switch_unavailable(hass, bridge, setup_integration):
    switch = _entity_id(hass, setup_integration, "switch", "switch_eco_mode")
    assert hass.states.get(switch).state == "unavailable"
