"""The split log operating time of a combined stove (issue #61): only for a stove that has burned split logs."""
from homeassistant.helpers import entity_registry as er


def _entity(hass, entry):
    registry = er.async_get(hass)
    return next(
        (e for e in er.async_entries_for_config_entry(registry, entry.entry_id) if e.unique_id == f"{entry.entry_id}_sensor_log_runtime"),
        None,
    )


async def test_a_stove_that_reports_no_split_log_time_has_no_entity(hass, bridge, setup_integration):
    assert _entity(hass, setup_integration) is None  # the fixture reports none: a pellet stove, or an older bridge
    bridge.state["sensors"]["log_runtime"] = 0
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert _entity(hass, setup_integration) is None


async def test_a_combined_stove_shows_the_split_log_time_in_hours(hass, bridge, setup_integration):
    bridge.state["sensors"]["log_runtime"] = 91007  # minutes, as the stove counts them; its screen shows 1516 h
    await hass.config_entries.async_reload(setup_integration.entry_id)
    await hass.async_block_till_done()
    entity = _entity(hass, setup_integration)
    assert entity is not None and entity.entity_category is None
    state = hass.states.get(entity.entity_id)
    assert state.attributes["unit_of_measurement"] == "h"
    assert round(float(state.state), 1) == 1516.8
