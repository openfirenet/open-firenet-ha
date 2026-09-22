from __future__ import annotations

from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenFirenetScheduleSwitch(coordinator, entry)])


class OpenFirenetScheduleSwitch(
    CoordinatorEntity[OpenFirenetCoordinator], SwitchEntity
):
    """Switch to toggle the weekly heating schedule on or off."""

    _attr_has_entity_name = True
    _attr_translation_key = "heating_schedule"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_switch_heating_schedule"

    @property
    def device_info(self) -> dict:
        device = self.coordinator.data.get("device", {})
        stove = self.coordinator.data.get("stove", {})
        model_name = stove.get("model_name") or get_model_name(stove.get("model"))
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": device.get("name", "Open-Firenet"),
            "manufacturer": "Open-Firenet",
            "model": f"RIKA {model_name}",
            "sw_version": f"Firmware v{device.get('version', '2.0.0')} (MB {stove.get('mainboard_version', '')})",
            "configuration_url": f"http://{self.coordinator.host}",
        }

    @property
    def is_on(self) -> bool:
        controls = self.coordinator.data.get("controls", {})
        return bool(
            controls.get(
                "heating_times_active", controls.get("heatingTimesActive", False)
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(heatingTimesActive=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(heatingTimesActive=False)
