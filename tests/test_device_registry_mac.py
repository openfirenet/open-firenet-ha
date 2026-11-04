"""The bridge's MAC address is recorded in its device registry entry.

Other integrations expose the hardware address the same way, so the bridge is identified by its MAC in device
information instead of only by the integration's identifiers.
"""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.open_firenet.const import DOMAIN

MAC = "aa:bb:cc:12:34:56"


async def _setup(hass, bridge):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_bridge_mac_is_a_device_connection(hass, bridge):
    entry = await _setup(hass, bridge)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}


async def test_mac_is_read_from_status_on_older_payloads(hass, bridge):
    del bridge.state["device"]["mac"]
    bridge.state["status"] = {"mac": "AA-BB-CC-12-34-56"}
    entry = await _setup(hass, bridge)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert devices[0].connections == {(dr.CONNECTION_NETWORK_MAC, MAC)}


async def test_missing_or_placeholder_mac_is_ignored(hass, bridge):
    bridge.state["device"]["mac"] = "00:00:00:00:00:00"
    entry = await _setup(hass, bridge)

    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 1
    assert devices[0].connections == set()


async def test_existing_device_with_the_same_mac_is_reused(hass, bridge):
    """A device already registered for this config entry with the same MAC is reused, not duplicated."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300},
    )
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    existing = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "legacy")},
        connections={(dr.CONNECTION_NETWORK_MAC, MAC)},
        name="Open Firenet (legacy)",
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(devices) == 1
    assert devices[0].id == existing.id
    assert devices[0].identifiers == {(DOMAIN, "legacy"), (DOMAIN, entry.entry_id)}
