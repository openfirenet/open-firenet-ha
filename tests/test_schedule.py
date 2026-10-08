"""Heating schedule: 28 time entities whose changes stay pending until the "send" button is pressed."""

from __future__ import annotations

from datetime import time

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.open_firenet.const import DOMAIN
from homeassistant.setup import async_setup_component

from custom_components.open_firenet.const import CONF_SCHEDULE_ENTITY
from custom_components.open_firenet.schedule import (
    TooManySlots,
    command_key,
    decode_slot,
    encode_slot,
    slots_from_ha_schedule,
    slots_from_state,
)

from .conftest import CONTROLS_POS_WITH_SCHEDULE


def _eid(hass, entry, platform: str, unique_suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, "open_firenet", f"{entry.entry_id}_{unique_suffix}")
    assert entity_id, f"{platform} {unique_suffix} not registered"
    return entity_id


async def _enable_slot_entities(hass, entry):
    """The 28 times, their two buttons and the pending indicator are disabled by default: switch them on."""
    registry = er.async_get(hass)
    for item in er.async_entries_for_config_entry(registry, entry.entry_id):
        if item.disabled_by is not None:
            registry.async_update_entity(item.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


async def _with_schedule(hass, bridge, entry, slot_entities: bool = True):
    if slot_entities:
        await _enable_slot_entities(hass, entry)
    bridge.state["controls_pos"] = list(CONTROLS_POS_WITH_SCHEDULE)
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()


async def _set(hass, entity_id: str, value: str) -> None:
    await hass.services.async_call("time", "set_value", {"entity_id": entity_id, "time": value}, blocking=True)


async def _press(hass, entity_id: str) -> None:
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


def test_slot_encoding():
    assert decode_slot(7001230) == (time(7, 0), time(12, 30))
    assert decode_slot(14302101) == (time(14, 30), time(21, 1))
    assert decode_slot(50100) == (time(0, 5), time(1, 0))
    assert decode_slot(0) == (time(0, 0), time(0, 0))
    assert decode_slot(5002400) == (time(5, 0), time(23, 59))  # the stove's 24:00 does not fit a time entity
    assert decode_slot(99999999) is None and decode_slot(-1) is None
    assert encode_slot(time(7, 0), time(12, 30)) == 7001230
    assert encode_slot(time(0, 5), time(1, 0)) == 50100
    assert encode_slot(time(8, 0), time(8, 0)) == 0  # start equal to end: slot off
    with pytest.raises(ValueError):
        encode_slot(time(14, 0), time(12, 30))
    assert [command_key(i) for i in (0, 1, 2, 13)] == ["heatTimeMon1", "heatTimeMon2", "heatTimeTue1", "heatTimeSun2"]
    assert slots_from_state({"controls_pos": []}) is None
    assert slots_from_state({"controls_pos": CONTROLS_POS_WITH_SCHEDULE})[:3] == [7001230, 14302101, 6002330]


async def test_entities_show_the_stove_schedule(hass, bridge, setup_integration):
    entry = setup_integration
    # Disabled by default: the Home Assistant schedule is the main way.
    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_mon_1_start")) is None
    assert hass.states.get(_eid(hass, entry, "button", "button_schedule_copy")) is not None
    await _enable_slot_entities(hass, entry)
    # Before the stove has given its schedule the times are unknown, not 00:00.
    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_mon_1_start")).state == "unknown"

    await _with_schedule(hass, bridge, entry)

    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_mon_1_start")).state == "07:00:00"
    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_mon_1_end")).state == "12:30:00"
    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_mon_2_end")).state == "21:01:00"
    assert hass.states.get(_eid(hass, entry, "time", "time_schedule_sun_2_start")).state == "00:00:00"
    assert hass.states.get(_eid(hass, entry, "binary_sensor", "schedule_pending")).state == "off"
    assert len([e for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id) if e.domain == "time"]) == 28


async def test_changes_wait_for_the_send_button(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry)
    start = _eid(hass, entry, "time", "time_schedule_mon_1_start")
    end = _eid(hass, entry, "time", "time_schedule_mon_1_end")
    pending = _eid(hass, entry, "binary_sensor", "schedule_pending")

    # Start first: for a moment the slot would be 14:00-12:30. Nothing goes to the stove.
    await _set(hass, start, "14:00:00")
    assert bridge.posts == []
    assert hass.states.get(start).state == "14:00:00"
    assert hass.states.get(pending).state == "on"
    # A poll in between does not bring the stove's value back over the pending one.
    await hass.data[DOMAIN][entry.entry_id].async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(start).state == "14:00:00"

    await _set(hass, end, "18:00:00")
    await _set(hass, _eid(hass, entry, "time", "time_schedule_wed_2_start"), "20:00:00")
    await _set(hass, _eid(hass, entry, "time", "time_schedule_wed_2_end"), "22:15:00")
    assert bridge.posts == []

    await _press(hass, _eid(hass, entry, "button", "button_schedule_send"))

    assert bridge.posts == [{"heatTimeMon1": 14001800, "heatTimeWed2": 20002215}]  # one command, only the changed slots
    assert bridge.state["controls_pos"][7] == 14001800
    assert hass.states.get(start).state == "14:00:00"
    assert hass.states.get(pending).state == "off"


async def test_end_before_start_is_refused(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry)
    start = _eid(hass, entry, "time", "time_schedule_mon_1_start")

    await _set(hass, start, "14:00:00")  # the end is still 12:30
    with pytest.raises(ServiceValidationError) as err:
        await _press(hass, _eid(hass, entry, "button", "button_schedule_send"))

    assert err.value.translation_key == "schedule_end_before_start"
    assert bridge.posts == []
    assert hass.states.get(start).state == "14:00:00"  # the change is kept, to be completed
    assert hass.states.get(_eid(hass, entry, "binary_sensor", "schedule_pending")).state == "on"


async def test_equal_times_switch_the_slot_off(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry)

    await _set(hass, _eid(hass, entry, "time", "time_schedule_mon_2_start"), "21:01:00")
    await _press(hass, _eid(hass, entry, "button", "button_schedule_send"))

    assert bridge.posts == [{"heatTimeMon2": 0}]


async def test_discard_brings_the_stove_schedule_back(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry)
    start = _eid(hass, entry, "time", "time_schedule_mon_1_start")

    await _set(hass, start, "09:00:00")
    await _press(hass, _eid(hass, entry, "button", "button_schedule_discard"))
    await hass.async_block_till_done()

    assert bridge.posts == []
    assert hass.states.get(start).state == "07:00:00"
    assert hass.states.get(_eid(hass, entry, "binary_sensor", "schedule_pending")).state == "off"


async def test_send_without_changes_sends_nothing(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry)

    await _press(hass, _eid(hass, entry, "button", "button_schedule_send"))

    assert bridge.posts == []


# --- a Home Assistant schedule copied to the stove ---------------------------------------------------------------


def test_ha_schedule_conversion():
    plan = {
        "monday": [{"from": time(14, 30), "to": time(21, 0)}, {"from": time(7, 0), "to": time(12, 30)}],  # any order
        "tuesday": [{"from": "06:00:00", "to": "24:00:00"}],  # texts, and an end at midnight
        "wednesday": [{"from": time(20, 0), "to": time.max}],
        "thursday": [],
    }
    slots = slots_from_ha_schedule(plan)
    assert len(slots) == 14
    assert slots[0:2] == [7001230, 14302100]
    assert slots[2:4] == [6002359, 0]
    assert slots[4:6] == [20002359, 0]
    assert slots[6:] == [0] * 8  # Thursday empty, Friday to Sunday absent
    with pytest.raises(TooManySlots) as err:
        slots_from_ha_schedule({"saturday": [{"from": time(h, 0), "to": time(h, 30)} for h in (6, 9, 12)]})
    assert err.value.weekday == "saturday" and err.value.count == 3


async def _ha_schedule(hass, **days) -> str:
    assert await async_setup_component(hass, "schedule", {"schedule": {"stove_week": {"name": "Stove week", **days}}})
    await hass.async_block_till_done()
    return "schedule.stove_week"


async def _choose(hass, entry, schedule_entity: str | None) -> None:
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_SCHEDULE_ENTITY: schedule_entity})
    await hass.async_block_till_done()


async def test_copy_a_home_assistant_schedule_to_the_stove(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry, slot_entities=False)
    schedule_entity = await _ha_schedule(
        hass,
        monday=[{"from": "06:30:00", "to": "08:00:00"}, {"from": "17:00:00", "to": "22:30:00"}],
        saturday=[{"from": "09:00:00", "to": "24:00:00"}],
    )
    await _choose(hass, entry, schedule_entity)

    await _press(hass, _eid(hass, entry, "button", "button_schedule_copy"))

    assert len(bridge.posts) == 1 and len(bridge.posts[0]) == 14  # the whole week, in one command
    assert bridge.posts[0]["heatTimeMon1"] == 6300800 and bridge.posts[0]["heatTimeMon2"] == 17002230
    assert bridge.posts[0]["heatTimeSat1"] == 9002359 and bridge.posts[0]["heatTimeSat2"] == 0
    assert bridge.posts[0]["heatTimeTue1"] == 0  # the stove's Tuesday slot is replaced: the plan is the whole week
    assert bridge.state["controls_pos"][7:9] == [6300800, 17002230]


async def test_copy_refuses_three_ranges_in_a_day(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry, slot_entities=False)
    schedule_entity = await _ha_schedule(
        hass, friday=[{"from": f"{h:02d}:00:00", "to": f"{h:02d}:30:00"} for h in (6, 9, 12)]
    )
    await _choose(hass, entry, schedule_entity)

    with pytest.raises(ServiceValidationError) as err:
        await _press(hass, _eid(hass, entry, "button", "button_schedule_copy"))

    assert err.value.translation_key == "schedule_too_many_slots"
    assert err.value.translation_placeholders == {"weekday": "friday", "count": "3"}
    assert bridge.posts == []


async def test_copy_without_a_chosen_schedule_says_what_to_do(hass, bridge, setup_integration):
    entry = setup_integration
    await _with_schedule(hass, bridge, entry, slot_entities=False)

    with pytest.raises(ServiceValidationError) as err:
        await _press(hass, _eid(hass, entry, "button", "button_schedule_copy"))
    assert err.value.translation_key == "schedule_not_chosen"

    await _choose(hass, entry, "schedule.gone")
    with pytest.raises(ServiceValidationError) as err:
        await _press(hass, _eid(hass, entry, "button", "button_schedule_copy"))
    assert err.value.translation_key == "schedule_not_found"
    assert bridge.posts == []
