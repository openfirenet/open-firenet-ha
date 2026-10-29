"""Firmware update of the bridge: tells when a newer firmware is published on GitHub, and installs it on request.

Home Assistant downloads the firmware, checks its signature and its SHA-256, then sends it to the bridge with the
wireless update protocol (see ota.py). The bridge must be able to open a TCP connection back to Home Assistant."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.components.update import UpdateDeviceClass, UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_OTA_PASSWORD, DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator
from .ota import OtaError, download_verified_firmware, push_firmware

_LOGGER = logging.getLogger(__name__)

FIRMWARE_REPO = "openfirenet/open-firenet"
LATEST_RELEASE_URL = f"https://api.github.com/repos/{FIRMWARE_REPO}/releases/latest"

# GitHub allows 60 anonymous requests an hour per address: a check every few hours is plenty.
SCAN_INTERVAL = timedelta(hours=6)

# After the transfer the bridge restarts: wait a moment, then ask it until it answers with the new version.
RESTART_GRACE = 5  # seconds
RESTART_POLL = 3  # seconds
RESTART_TRIES = 30


async def async_fetch_latest_release(hass: HomeAssistant) -> dict | None:
    """The latest published release (never a draft or a pre-release), or None when GitHub cannot be reached."""
    session = async_get_clientsession(hass)
    try:
        async with asyncio.timeout(15):
            async with session.get(LATEST_RELEASE_URL, headers={"Accept": "application/vnd.github+json"}) as resp:
                if resp.status != 200:
                    _LOGGER.debug("GitHub answered %s to the firmware release check", resp.status)
                    return None
                data = await resp.json()
    except (asyncio.TimeoutError, aiohttp.ClientError, ValueError) as err:
        _LOGGER.debug("Firmware release check failed: %s", err)
        return None
    tag = str(data.get("tag_name") or "").strip()
    if not tag:
        return None
    return {
        "version": tag.removeprefix("v"),
        "assets": {
            str(a.get("name")): a.get("browser_download_url")
            for a in data.get("assets") or []
            if a.get("name") and a.get("browser_download_url")
        },
        "url": data.get("html_url") or f"https://github.com/{FIRMWARE_REPO}/releases/tag/{tag}",
        "notes": data.get("body") or "",
    }


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenFirenetFirmwareUpdate(coordinator, entry)], update_before_add=True)


class OpenFirenetFirmwareUpdate(CoordinatorEntity[OpenFirenetCoordinator], UpdateEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "firmware"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
    )
    # The coordinator polls the bridge; the release check has its own, slower, rhythm (SCAN_INTERVAL).
    _attr_should_poll = True

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_update_firmware"
        self._release: dict | None = None

    @property
    def device_info(self) -> dict:
        device = self.coordinator.data.get("device", {})
        stove = self.coordinator.data.get("stove", {})
        model_name = stove.get("model_name") or get_model_name(stove.get("model"))
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": device.get("name", "Open Firenet"),
            "manufacturer": "Open Firenet",
            "model": f"RIKA {model_name}",
            "sw_version": f"Firmware v{device.get('version', '2.0.0')} (MB {stove.get('mainboard_version') or '?'})",
            "configuration_url": f"http://{self.coordinator.host}",
        }

    @property
    def installed_version(self) -> str | None:
        return (self.coordinator.data or {}).get("device", {}).get("version") or None

    @property
    def latest_version(self) -> str | None:
        # Without an answer from GitHub, nothing is claimed: the entity then shows no newer version.
        if self._release is None:
            return self.installed_version
        return self._release["version"]

    @property
    def release_url(self) -> str | None:
        return self._release["url"] if self._release else None

    async def async_release_notes(self) -> str | None:
        return (self._release or {}).get("notes") or None

    async def async_update(self) -> None:
        release = await async_fetch_latest_release(self.hass)
        if release is not None:
            self._release = release

    async def async_install(self, version: str | None, backup: bool, **kwargs) -> None:
        release = self._release
        if release is None or not release.get("assets"):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="update_assets_missing")
        data = self.coordinator.data or {}
        device = data.get("device") or {}
        stove = data.get("stove") or {}

        # The bridge restarts: only install while the stove is off, as the bridge's own page does. A stove in standby
        # is switched on and can ignite at any time.
        if stove.get("state") != "off" or stove.get("is_burning"):
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="update_stove_running")
        password = self._entry.options.get(CONF_OTA_PASSWORD) or None
        if device.get("ota_password_set") and not password:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="update_password_required")

        self._attr_in_progress = True
        self._attr_update_percentage = None
        self.async_write_ha_state()
        try:
            firmware = await download_verified_firmware(async_get_clientsession(self.hass), release["assets"])
            slot = device.get("ota_slot_bytes") or 0
            if slot and len(firmware) > slot:
                raise OtaError("update_slot_too_small", firmware=str(len(firmware)), slot=str(slot))

            def _progress(percent: int) -> None:
                self._attr_update_percentage = percent
                self.async_write_ha_state()

            await push_firmware(self.coordinator.host, firmware, password, _progress)
            await self._wait_for_version(release["version"])
        except OtaError as err:
            _LOGGER.warning("Firmware update of the bridge failed: %s", err.key)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders={k: str(v) for k, v in err.placeholders.items()},
            ) from err
        finally:
            self._attr_in_progress = False
            self._attr_update_percentage = None
            self.async_write_ha_state()

    async def _wait_for_version(self, version: str) -> None:
        """The bridge restarts after the transfer: wait until it answers again with the new version."""
        await asyncio.sleep(RESTART_GRACE)
        for _ in range(RESTART_TRIES):
            await self.coordinator.async_refresh()
            if self.installed_version == version:
                return
            await asyncio.sleep(RESTART_POLL)
        raise OtaError("update_not_confirmed")
