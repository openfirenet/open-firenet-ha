"""Changing the address of a bridge already added (menu "Reconfigure")."""
from aiohttp.test_utils import TestServer
from homeassistant.const import CONF_HOST
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.open_firenet.const import DOMAIN


async def _start(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )


async def test_reconfigure_moves_the_entry_to_the_new_address(hass, bridge, setup_integration):
    entry = setup_integration
    before = sorted(e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
    assert before

    # The same bridge, reachable at another address (another port stands for another IP here).
    second = TestServer(bridge.app())
    await second.start_server()
    new_host = f"{second.host}:{second.port}"
    try:
        result = await _start(hass, entry)
        assert result["type"] is FlowResultType.FORM and result["step_id"] == "reconfigure"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: new_host})
        await hass.async_block_till_done()

        assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
        assert entry.data[CONF_HOST] == new_host
        assert entry.unique_id == new_host
        assert entry.title == f"Open Firenet ({new_host})"
        # The entities are the same ones: nothing was deleted and created again.
        after = sorted(e.unique_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id))
        assert after == before
        assert hass.data[DOMAIN][entry.entry_id].host == new_host
    finally:
        await second.close()


async def test_reconfigure_keeps_the_address_when_the_new_one_does_not_answer(hass, bridge, setup_integration):
    entry = setup_integration
    old_host = entry.data[CONF_HOST]

    result = await _start(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_HOST: "127.0.0.1:1"})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data[CONF_HOST] == old_host
