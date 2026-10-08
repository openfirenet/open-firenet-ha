"""Start and end of each slot of the stove's weekly heating schedule (see schedule.py)."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator
from .schedule import DAYS, EDGES, SLOTS_PER_DAY, slot_index


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        OpenFirenetScheduleTime(coordinator, entry, day, slot, edge)
        for day in range(len(DAYS))
        for slot in range(SLOTS_PER_DAY)
        for edge in EDGES
    )


class OpenFirenetScheduleTime(CoordinatorEntity[OpenFirenetCoordinator], TimeEntity):
    """One time of the schedule. A change is kept pending until the "send" button is pressed."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False  # 28 of them: the Home Assistant schedule is the main way
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry, day: int, slot: int, edge: str) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._index = slot_index(day, slot)
        self._edge = edge
        key = f"schedule_{DAYS[day]}_{slot + 1}_{edge}"
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_time_{key}"

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
    def native_value(self) -> time | None:
        return self.coordinator.schedule_time(self._index, self._edge)

    async def async_set_value(self, value: time) -> None:
        self.coordinator.schedule_set_pending(self._index, self._edge, value)
