"""The firmware update entity: tells that a newer firmware is published, and installs it on request."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components.update import UpdateEntityFeature
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.open_firenet import update as update_module
from custom_components.open_firenet.const import CONF_OTA_PASSWORD, DOMAIN
from custom_components.open_firenet.ota import OtaError

FETCH = "custom_components.open_firenet.update.async_fetch_latest_release"


async def _setup(hass, bridge, release):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300})
    entry.add_to_hass(hass)
    with patch(FETCH, return_value=release):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _entity_id(hass, entry):
    return er.async_get(hass).async_get_entity_id("update", DOMAIN, f"{entry.entry_id}_update_firmware")


async def test_newer_release_is_announced(hass, bridge):
    release = {"version": "4.0.0", "url": "https://example.org/r", "notes": "New things"}
    entry = await _setup(hass, bridge, release)

    state = hass.states.get(_entity_id(hass, entry))
    assert state.state == "on"
    assert state.attributes["installed_version"] == "2.1.0"
    assert state.attributes["latest_version"] == "4.0.0"
    assert state.attributes["release_url"] == "https://example.org/r"
    assert state.attributes["supported_features"] & UpdateEntityFeature.INSTALL


async def test_same_release_is_up_to_date(hass, bridge):
    entry = await _setup(hass, bridge, {"version": "2.1.0", "url": "https://example.org/r", "notes": ""})
    assert hass.states.get(_entity_id(hass, entry)).state == "off"


async def test_github_unreachable_claims_nothing(hass, bridge):
    entry = await _setup(hass, bridge, None)
    assert hass.states.get(_entity_id(hass, entry)).state == "off"


# --- installation ------------------------------------------------------------------------------------------------


RELEASE = {
    "version": "4.0.0",
    "url": "https://example.org/r",
    "notes": "",
    "assets": {"open-firenet-ota.bin": "u1", "SHA256SUMS": "u2", "SHA256SUMS.minisig": "u3"},
}
FIRMWARE = bytes([0xE9]) * 4096


@pytest.fixture
def ota(monkeypatch):
    """Replace the download and the transfer: they have their own tests (test_ota.py)."""

    class Fake:
        downloads = 0
        sent: list[dict] = []
        download_error = None
        bridge = None

    fake = Fake()
    fake.sent = []

    async def download(session, assets):
        fake.downloads += 1
        if fake.download_error:
            raise fake.download_error
        return FIRMWARE

    async def push(host, firmware, password, on_progress, udp_port=None):
        fake.sent.append({"host": host, "size": len(firmware), "password": password})
        on_progress(50)
        on_progress(100)
        fake.bridge.state["device"]["version"] = "4.0.0"  # the bridge restarted with the new firmware

    monkeypatch.setattr(update_module, "download_verified_firmware", download)
    monkeypatch.setattr(update_module, "push_firmware", push)
    monkeypatch.setattr(update_module, "RESTART_GRACE", 0)
    monkeypatch.setattr(update_module, "RESTART_POLL", 0)
    return fake


async def _setup_with(hass, bridge, options=None):
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_HOST: bridge.host, CONF_SCAN_INTERVAL: 300}, options=options or {}
    )
    entry.add_to_hass(hass)
    with patch(FETCH, return_value=RELEASE):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def _install(hass, entry):
    await hass.services.async_call(
        "update", "install", {"entity_id": _entity_id(hass, entry)}, blocking=True
    )


async def test_install_downloads_checks_and_sends(hass, bridge, ota):
    ota.bridge = bridge
    entry = await _setup_with(hass, bridge)

    await _install(hass, entry)

    assert ota.downloads == 1
    assert [s["size"] for s in ota.sent] == [len(FIRMWARE)]
    assert ota.sent[0]["password"] is None
    assert hass.states.get(_entity_id(hass, entry)).state == "off"


async def test_install_uses_the_password_of_the_options(hass, bridge, ota):
    ota.bridge = bridge
    bridge.state["device"]["ota_password_set"] = True
    entry = await _setup_with(hass, bridge, {CONF_OTA_PASSWORD: "correct horse"})

    await _install(hass, entry)

    assert ota.sent[0]["password"] == "correct horse"


async def test_install_without_the_password_sends_nothing(hass, bridge, ota):
    ota.bridge = bridge
    bridge.state["device"]["ota_password_set"] = True
    entry = await _setup_with(hass, bridge)

    with pytest.raises(HomeAssistantError):
        await _install(hass, entry)

    assert ota.downloads == 0 and ota.sent == []


async def test_install_refused_while_the_stove_burns(hass, bridge, ota):
    ota.bridge = bridge
    bridge.state["stove"]["is_burning"] = True
    entry = await _setup_with(hass, bridge)

    with pytest.raises(HomeAssistantError):
        await _install(hass, entry)

    assert ota.downloads == 0 and ota.sent == []


async def test_install_refused_while_the_stove_is_in_standby(hass, bridge, ota):
    ota.bridge = bridge
    bridge.state["stove"]["state"] = "standby"
    entry = await _setup_with(hass, bridge)

    with pytest.raises(HomeAssistantError):
        await _install(hass, entry)

    assert ota.downloads == 0 and ota.sent == []


async def test_install_refused_when_the_slot_is_too_small(hass, bridge, ota):
    ota.bridge = bridge
    bridge.state["device"]["ota_slot_bytes"] = 1000
    entry = await _setup_with(hass, bridge)

    with pytest.raises(HomeAssistantError):
        await _install(hass, entry)

    assert ota.sent == []


async def test_failed_check_sends_nothing(hass, bridge, ota):
    ota.bridge = bridge
    ota.download_error = OtaError("update_signature_invalid")
    entry = await _setup_with(hass, bridge)

    with pytest.raises(HomeAssistantError):
        await _install(hass, entry)

    assert ota.sent == []
    assert hass.states.get(_entity_id(hass, entry)).attributes["in_progress"] is False
