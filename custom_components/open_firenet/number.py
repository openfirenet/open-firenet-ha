from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MULTIAIR_TRIM_MAX,
    MULTIAIR_TRIM_MIN,
    MULTIAIR_TRIM_STEP,
    SETBACK_TEMP_MAX,
    SETBACK_TEMP_MIN,
    SETBACK_TEMP_STEP,
    get_model_name,
    is_multiair_supported,
)
from .coordinator import OpenFirenetCoordinator


@dataclass(frozen=True, kw_only=True)
class OpenFirenetNumberDescription(NumberEntityDescription):
    value_fn: Callable[[dict[str, Any]], float | None]
    set_fn: Callable[[OpenFirenetCoordinator, float], Any]


NUMBER_TYPES: tuple[OpenFirenetNumberDescription, ...] = (
    OpenFirenetNumberDescription(
        key="setback_temperature",
        name="Setback Temperature",
        device_class=NumberDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        native_min_value=SETBACK_TEMP_MIN,
        native_max_value=SETBACK_TEMP_MAX,
        native_step=SETBACK_TEMP_STEP,
        mode=NumberMode.SLIDER,
        icon="mdi:thermometer-chevron-down",
        value_fn=lambda data: data.get("controls", {}).get(
            "setback_temperature",
            (
                data.get("controls", {}).get("setBackTemp", 160) / 10.0
                if "setBackTemp" in data.get("controls", {})
                else 16.0
            ),
        ),
        set_fn=lambda coord, val: coord.async_set_controls(
            setback_temperature=float(val)
        ),
    ),
)

MULTIAIR_NUMBER_TYPES: tuple[OpenFirenetNumberDescription, ...] = (
    OpenFirenetNumberDescription(
        key="multiair_1_area",
        name="MultiAir 1 Convection Trim",
        native_unit_of_measurement="%",
        native_min_value=MULTIAIR_TRIM_MIN,
        native_max_value=MULTIAIR_TRIM_MAX,
        native_step=MULTIAIR_TRIM_STEP,
        mode=NumberMode.SLIDER,
        icon="mdi:fan-chevron-up",
        value_fn=lambda data: data.get("controls", {}).get(
            "convection_fan1_area",
            data.get("controls", {}).get("convectionFan1Area", 0),
        ),
        set_fn=lambda coord, val: coord.async_set_controls(
            convectionFan1Area=int(val)
        ),
    ),
    OpenFirenetNumberDescription(
        key="multiair_2_area",
        name="MultiAir 2 Convection Trim",
        native_unit_of_measurement="%",
        native_min_value=MULTIAIR_TRIM_MIN,
        native_max_value=MULTIAIR_TRIM_MAX,
        native_step=MULTIAIR_TRIM_STEP,
        mode=NumberMode.SLIDER,
        icon="mdi:fan-chevron-up",
        value_fn=lambda data: data.get("controls", {}).get(
            "convection_fan2_area",
            data.get("controls", {}).get("convectionFan2Area", 0),
        ),
        set_fn=lambda coord, val: coord.async_set_controls(
            convectionFan2Area=int(val)
        ),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [OpenFirenetNumber(coordinator, entry, desc) for desc in NUMBER_TYPES]

    if is_multiair_supported(coordinator.data):
        entities.extend(
            [
                OpenFirenetNumber(coordinator, entry, desc)
                for desc in MULTIAIR_NUMBER_TYPES
            ]
        )

    async_add_entities(entities)


class OpenFirenetNumber(CoordinatorEntity[OpenFirenetCoordinator], NumberEntity):
    """Number entity for Open-Firenet controllable ranges."""

    entity_description: OpenFirenetNumberDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OpenFirenetCoordinator,
        entry: ConfigEntry,
        description: OpenFirenetNumberDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{entry.entry_id}_number_{description.key}"

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
    def native_value(self) -> float | None:
        val = self.entity_description.value_fn(self.coordinator.data)
        if val is not None:
            try:
                return float(val)
            except (ValueError, TypeError):
                pass
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self.entity_description.set_fn(self.coordinator, value)
