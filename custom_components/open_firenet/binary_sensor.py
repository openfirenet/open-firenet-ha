from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator


@dataclass(frozen=True, kw_only=True)
class OpenFirenetBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSOR_TYPES: tuple[OpenFirenetBinarySensorDescription, ...] = (
    OpenFirenetBinarySensorDescription(
        key="connected",
        name="Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("device", {}).get("connected", False),
    ),
    OpenFirenetBinarySensorDescription(
        key="burning",
        name="Combustion Active",
        icon="mdi:fire",
        value_fn=lambda data: data.get("stove", {}).get("is_burning", False),
    ),
    OpenFirenetBinarySensorDescription(
        key="problem",
        name="Stove Error",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda data: data.get("stove", {}).get("has_error", False),
    ),
    OpenFirenetBinarySensorDescription(
        key="hopper_lid",
        name="Pellet Hopper Lid",
        device_class=BinarySensorDeviceClass.DOOR,
        icon="mdi:tray-arrow-up",
        value_fn=lambda data: (
            data.get("raw_sensors", {}).get("hopperLidClosed") == 0
            if "hopperLidClosed" in data.get("raw_sensors", {})
            else bool(data.get("stove", {}).get("state_mask", 0) & 2)
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OpenFirenetBinarySensor(coordinator, entry, description)
            for description in BINARY_SENSOR_TYPES
        ]
    )


class OpenFirenetBinarySensor(
    CoordinatorEntity[OpenFirenetCoordinator], BinarySensorEntity
):
    entity_description: OpenFirenetBinarySensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OpenFirenetCoordinator,
        entry: ConfigEntry,
        description: OpenFirenetBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

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
        return self.entity_description.value_fn(self.coordinator.data)
