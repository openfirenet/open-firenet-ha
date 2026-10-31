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
    async_add_entities([
        OpenFirenetScheduleSwitch(coordinator, entry),
        OpenFirenetFrostProtectionSwitch(coordinator, entry),
        OpenFirenetEcoModeSwitch(coordinator, entry),
    ])


class OpenFirenetScheduleSwitch(
    CoordinatorEntity[OpenFirenetCoordinator], SwitchEntity
):
    """Switch to toggle the weekly heating schedule on or off."""

    _attr_has_entity_name = True
    _attr_name = "Heating Schedule"
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
            "name": device.get("name", "Open Firenet"),
            "manufacturer": "Open Firenet",
            "model": f"RIKA {model_name}",
            "sw_version": f"Firmware v{device.get('version', '2.0.0')} (MB {stove.get('mainboard_version') or '?'})",
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


class OpenFirenetFrostProtectionSwitch(
    CoordinatorEntity[OpenFirenetCoordinator], SwitchEntity
):
    """Switch to toggle frost protection mode on or off."""

    _attr_has_entity_name = True
    _attr_name = "Frost Protection"
    _attr_translation_key = "frost_protection"
    _attr_icon = "mdi:snowflake"

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_switch_frost_protection"

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
    def is_on(self) -> bool:
        controls = self.coordinator.data.get("controls", {})
        c_pos = self.coordinator.data.get("controls_pos", [])
        if "frost_protection_active" in controls:
            return bool(controls["frost_protection_active"])
        if "frostProtectionActive" in controls:
            return bool(controls["frostProtectionActive"])
        if len(c_pos) > 29:
            return bool(c_pos[29])
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(frostProtectionActive=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(frostProtectionActive=False)


class OpenFirenetEcoModeSwitch(
    CoordinatorEntity[OpenFirenetCoordinator], SwitchEntity
):
    """Switch for the eco mode of the stove, offered by the stove only when it says the mode is possible."""

    _attr_has_entity_name = True
    _attr_name = "Eco Mode"
    _attr_translation_key = "eco_mode"
    _attr_icon = "mdi:leaf"

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_switch_eco_mode"

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
    def available(self) -> bool:
        # Not available while the stove does not allow the eco mode, unless it is currently on (so it can be turned off).
        controls = self.coordinator.data.get("controls", {})
        return super().available and (self.is_on or bool(controls.get("eco_mode_possible", False)))

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("controls", {}).get("eco_mode", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(ecoMode=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(ecoMode=False)
