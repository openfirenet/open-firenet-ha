"""Issue #12: entities must reflect a command right after it, not at the next poll."""

from __future__ import annotations

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.open_firenet.coordinator import _to_snake


def _entity_id(hass, entry, platform: str, unique_suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        platform, "open_firenet", f"{entry.entry_id}_{unique_suffix}"
    )
    assert entity_id, f"{platform} {unique_suffix} not registered"
    return entity_id


@pytest.mark.parametrize(
    ("camel", "snake"),
    [
        ("convectionFan1Active", "convection_fan1_active"),
        ("convectionFan2Level", "convection_fan2_level"),
        ("heatingTimesActive", "heating_times_active"),
        ("frostProtectionActive", "frost_protection_active"),
        ("on", "on"),
        ("setBackTemp", "setback_temperature"),
        ("frostProtectionTemp", "frost_protection_temperature"),
        ("roomTempOffset", "room_temperature_offset"),
        ("bakeTarget", "bake_target_temperature"),
    ],
)
def test_to_snake(camel, snake):
    assert _to_snake(camel) == snake


async def test_fan_turn_off_reflects_immediately(hass, bridge, setup_integration):
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")
    assert hass.states.get(entity_id).state == "on"

    await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert bridge.posts == [{"convectionFan2Active": False}]
    assert hass.states.get(entity_id).state == "off"


async def test_fan_set_percentage_reflects_immediately(hass, bridge, setup_integration):
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_1")

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": entity_id, "percentage": 80}, blocking=True
    )

    assert bridge.posts[-1] == {"convectionFan1Active": True, "convectionFan1Level": 4}
    assert hass.states.get(entity_id).attributes["percentage"] == 80


async def test_switch_toggle_reflects_immediately(hass, bridge, setup_integration):
    entity_id = _entity_id(hass, setup_integration, "switch", "switch_frost_protection")
    assert hass.states.get(entity_id).state == "off"

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    assert hass.states.get(entity_id).state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert hass.states.get(entity_id).state == "off"


async def test_device_value_wins_over_requested_value(hass, bridge, setup_integration):
    """The state shown after a command comes from the bridge, not from what was asked."""
    bridge.max_fan_level = 3
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_1")

    await hass.services.async_call(
        "fan", "set_percentage", {"entity_id": entity_id, "percentage": 100}, blocking=True
    )

    assert hass.states.get(entity_id).attributes["percentage"] == 60


async def test_command_reads_state_back_from_bridge(hass, bridge, setup_integration):
    gets_before = bridge.gets
    entity_id = _entity_id(hass, setup_integration, "switch", "switch_heating_schedule")

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)

    assert bridge.gets == gets_before + 1


async def test_failed_command_leaves_state_unchanged(hass, bridge, setup_integration):
    bridge.fail_posts = True
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")

    with pytest.raises(Exception):
        await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert hass.states.get(entity_id).state == "on"


@pytest.mark.parametrize(
    ("suffix", "value", "bridge_key"),
    [
        ("number_setback_temperature", 18.5, "setback_temperature"),
        ("number_frost_protection_temperature", 7.0, "frost_protection_temperature"),
        ("number_room_temperature_offset", -1.5, "room_temperature_offset"),
        ("number_multiair_2_area", 10, "convection_fan2_area"),
    ],
)
async def test_number_reflects_immediately(hass, bridge, setup_integration, suffix, value, bridge_key):
    entity_id = _entity_id(hass, setup_integration, "number", suffix)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )

    assert bridge.state["controls"][bridge_key] == value
    assert float(hass.states.get(entity_id).state) == value


@pytest.mark.parametrize("setup_integration", ["domo_back"], indirect=True)
async def test_bake_target_reflects_immediately(hass, bridge, setup_integration):
    entity_id = _entity_id(hass, setup_integration, "number", "number_bake_target_temperature")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 200}, blocking=True
    )

    assert bridge.state["controls"]["bake_target_temperature"] == 200
    assert float(hass.states.get(entity_id).state) == 200


async def test_optimistic_value_is_visible_before_refresh(hass, bridge, setup_integration):
    """Even if the bridge did not apply the value yet, the entity shows the requested one first."""
    coordinator = hass.data["open_firenet"][setup_integration.entry_id]
    seen = []
    coordinator.async_add_listener(lambda: seen.append(dict(coordinator.data["controls"])))

    await coordinator.async_set_controls(frostProtectionTemp=9.0)

    assert seen[0]["frost_protection_temperature"] == 9.0


async def test_climate_heating_power_is_expressed_as_percentage(hass, bridge, setup_integration):
    entity_id = _entity_id(hass, setup_integration, "climate", "climate")
    state = hass.states.get(entity_id)
    assert state.attributes["fan_mode"] == "power_70"
    assert state.attributes["fan_modes"] == [f"power_{power}" for power in range(30, 101, 5)]

    await hass.services.async_call(
        "climate",
        "set_fan_mode",
        {"entity_id": entity_id, "fan_mode": "power_85"},
        blocking=True,
    )

    assert bridge.posts[-1] == {"power_percent": 85}
    assert hass.states.get(entity_id).attributes["fan_mode"] == "power_85"
