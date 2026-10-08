"""Bridge firmware 4.0 refuses in two cases; the integration must explain them, not show a raw HTTP error.

- 503 "stove_not_ready": a command sent before the stove has given its settings. Nothing was sent to the stove.
- 403 "refused: host": the bridge was called under a name it does not know.
"""

from __future__ import annotations

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.open_firenet.const import DOMAIN


def _entity_id(hass, entry, platform: str, unique_suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, "open_firenet", f"{entry.entry_id}_{unique_suffix}")
    assert entity_id, f"{platform} {unique_suffix} not registered"
    return entity_id


async def test_command_is_sent_again_when_the_stove_was_not_ready(hass, bridge, setup_integration):
    bridge.not_ready_posts = 1
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")

    await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert len(bridge.posts) == 1  # the refused attempt wrote nothing, the second one went through
    assert hass.states.get(entity_id).state == "off"


async def test_stove_still_not_ready_gives_a_clear_message(hass, bridge, setup_integration):
    bridge.not_ready_posts = 5
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert err.value.translation_key == "stove_not_ready"
    assert bridge.posts == []
    assert bridge.not_ready_posts == 3  # two attempts, no more
    assert hass.states.get(entity_id).state == "on"


async def test_command_under_a_refused_name_says_what_to_do(hass, bridge, setup_integration):
    bridge.refuse_name = True
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert err.value.translation_key == "name_refused"
    assert err.value.translation_placeholders["ip"] == "192.168.1.93"


async def test_other_failure_is_a_message_too(hass, bridge, setup_integration):
    bridge.fail_posts = True
    entity_id = _entity_id(hass, setup_integration, "fan", "fan_multiair_2")

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call("fan", "turn_off", {"entity_id": entity_id}, blocking=True)

    assert err.value.translation_key == "command_failed"


async def test_reading_under_a_refused_name_explains_itself(hass, bridge, setup_integration):
    coordinator = hass.data[DOMAIN][setup_integration.entry_id]
    bridge.refuse_name = True

    await coordinator.async_refresh()

    assert not coordinator.last_update_success
    assert "192.168.1.93" in str(coordinator.last_exception)
    assert "section Access" in str(coordinator.last_exception)


async def test_setup_under_a_refused_name(hass, bridge):
    bridge.refuse_name = True

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 30}
    )

    assert result["errors"] == {"base": "name_refused"}
