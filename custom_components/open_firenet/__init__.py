from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .binary_sensor import BINARY_SENSOR_TYPES
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator
from .sensor import SENSOR_TYPES

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.FAN,
]


@callback
def _cleanup_orphaned_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove orphaned entities from older integration versions.

    Isolation guarantees:
    - Only queries entities registered under this specific entry.entry_id
    - Explicitly verifies reg_entry.platform == DOMAIN ('open_firenet')
    - Only removes entities whose unique_id is not in valid V2 unique_ids
    """
    valid_unique_ids = {
        f"{entry.entry_id}_climate",
        f"{entry.entry_id}_switch_heating_schedule",
        f"{entry.entry_id}_number_setback_temperature",
        f"{entry.entry_id}_number_multiair_1_area",
        f"{entry.entry_id}_number_multiair_2_area",
        f"{entry.entry_id}_fan_multiair_1",
        f"{entry.entry_id}_fan_multiair_2",
        *(f"{entry.entry_id}_{desc.key}" for desc in BINARY_SENSOR_TYPES),
        *(f"{entry.entry_id}_sensor_{desc.key}" for desc in SENSOR_TYPES),
    }

    entity_reg = er.async_get(hass)
    entries = er.async_entries_for_config_entry(entity_reg, entry.entry_id)

    removed_count = 0
    for reg_entry in entries:
        # Strict isolation check: must match our domain and config entry
        if reg_entry.platform != DOMAIN or reg_entry.config_entry_id != entry.entry_id:
            continue

        if reg_entry.unique_id not in valid_unique_ids:
            _LOGGER.info(
                "Removing orphaned Open-Firenet entity: %s (unique_id: %s)",
                reg_entry.entity_id,
                reg_entry.unique_id,
            )
            entity_reg.async_remove(reg_entry.entity_id)
            removed_count += 1

    if removed_count:
        _LOGGER.info("Cleaned up %d orphaned Open-Firenet entities", removed_count)

    # If uptime was given a '_2' suffix due to legacy conflict, restore clean entity_id
    uptime_uid = f"{entry.entry_id}_sensor_uptime_seconds"
    uptime_entity_id = entity_reg.async_get_entity_id(Platform.SENSOR, DOMAIN, uptime_uid)
    if uptime_entity_id and uptime_entity_id.endswith("_2"):
        clean_id = uptime_entity_id[:-2]
        if not entity_reg.async_is_registered(clean_id):
            entity_reg.async_update_entity(uptime_entity_id, new_entity_id=clean_id)
            _LOGGER.info("Restored clean entity ID %s (was %s)", clean_id, uptime_entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = OpenFirenetCoordinator(
        hass,
        host=entry.data[CONF_HOST],
        scan_interval=entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()

    # Automatically purge orphaned entities from earlier versions
    _cleanup_orphaned_entities(hass, entry)

    # Ensure device registry reflects current stove model and versions
    device_reg = dr.async_get(hass)
    device = coordinator.data.get("device", {})
    stove = coordinator.data.get("stove", {})
    model_name = stove.get("model_name") or get_model_name(stove.get("model"))
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=device.get("name", "Open-Firenet"),
        manufacturer="Open-Firenet",
        model=f"RIKA {model_name}",
        sw_version=f"Firmware v{device.get('version', '2.0.0')} (MB {stove.get('mainboard_version', '')})",
        configuration_url=f"http://{coordinator.host}",
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: OpenFirenetCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator._client.close()
        return True
    return False
