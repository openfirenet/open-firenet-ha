"""Buttons of the heating schedule (see schedule.py): copy a Home Assistant schedule to the stove, and, for the
per-slot time entities, send their pending changes or drop them."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SCHEDULE_ENTITY, DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        OpenFirenetScheduleButton(coordinator, entry, "schedule_copy", "mdi:calendar-arrow-right", enabled=True),
        OpenFirenetScheduleButton(coordinator, entry, "schedule_send", "mdi:calendar-check", enabled=False),
        OpenFirenetScheduleButton(coordinator, entry, "schedule_discard", "mdi:calendar-remove", enabled=False),
    ])


class OpenFirenetScheduleButton(CoordinatorEntity[OpenFirenetCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry, key: str, icon: str, enabled: bool) -> None:
        super().__init__(coordinator)
        self._attr_entity_registry_enabled_default = enabled
        self._entry = entry
        self._key = key
        self._attr_translation_key = key
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_button_{key}"

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

    async def async_press(self) -> None:
        if self._key == "schedule_copy":
            await self.coordinator.schedule_copy_from(self._entry.options.get(CONF_SCHEDULE_ENTITY))
        elif self._key == "schedule_send":
            await self.coordinator.schedule_send()
        else:
            self.coordinator.schedule_discard()
            await self.coordinator.async_request_refresh()
