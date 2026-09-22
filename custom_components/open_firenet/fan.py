from __future__ import annotations

from typing import Any

from homeassistant.components.fan import (
    FanEntity,
    FanEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MULTIAIR_LEVELS, get_model_name, is_multiair_supported
from .coordinator import OpenFirenetCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    if is_multiair_supported(coordinator.data):
        async_add_entities(
            [
                OpenFirenetMultiAirFan(coordinator, entry, 1),
                OpenFirenetMultiAirFan(coordinator, entry, 2),
            ]
        )


class OpenFirenetMultiAirFan(
    CoordinatorEntity[OpenFirenetCoordinator], FanEntity
):
    """Representation of a MultiAir forced convection fan."""

    _attr_has_entity_name = True
    _attr_speed_count = 5
    _attr_preset_modes = MULTIAIR_LEVELS
    _attr_supported_features = (
        FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.SET_SPEED
    )

    def __init__(
        self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry, fan_index: int
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._fan_index = fan_index
        self._attr_translation_key = f"multiair_{fan_index}"
        self._attr_unique_id = f"{entry.entry_id}_fan_multiair_{fan_index}"

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
    def _controls(self) -> dict:
        return self.coordinator.data.get("controls", {})

    @property
    def is_on(self) -> bool:
        key = f"convection_fan{self._fan_index}_active"
        alt_key = f"convectionFan{self._fan_index}Active"
        return bool(self._controls.get(key, self._controls.get(alt_key, False)))

    @property
    def _fan_level(self) -> int:
        key = f"convection_fan{self._fan_index}_level"
        alt_key = f"convectionFan{self._fan_index}Level"
        val = self._controls.get(key, self._controls.get(alt_key, 0))
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    @property
    def preset_mode(self) -> str | None:
        level = self._fan_level
        return "auto" if level == 0 else str(level)

    @property
    def percentage(self) -> int | None:
        level = self._fan_level
        if level <= 0:
            return None
        return int(level * 20)

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        payload: dict[str, Any] = {f"convectionFan{self._fan_index}Active": True}
        if preset_mode is not None:
            payload[f"convectionFan{self._fan_index}Level"] = (
                0 if preset_mode.lower() == "auto" else int(preset_mode)
            )
        elif percentage is not None:
            payload[f"convectionFan{self._fan_index}Level"] = max(
                1, min(5, int(round(percentage / 20.0)))
            )
        await self.coordinator.async_set_controls(**payload)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_controls(
            **{f"convectionFan{self._fan_index}Active": False}
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        level = 0 if preset_mode.lower() == "auto" else int(preset_mode)
        await self.coordinator.async_set_controls(
            **{
                f"convectionFan{self._fan_index}Active": True,
                f"convectionFan{self._fan_index}Level": level,
            }
        )

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
        else:
            level = max(1, min(5, int(round(percentage / 20.0))))
            await self.coordinator.async_set_controls(
                **{
                    f"convectionFan{self._fan_index}Active": True,
                    f"convectionFan{self._fan_index}Level": level,
                }
            )
