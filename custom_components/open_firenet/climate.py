from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HEATING_POWER_MAX,
    HEATING_POWER_MIN,
    HEATING_POWER_STEP,
    OPERATING_MODES,
    TEMP_MAX,
    TEMP_MIN,
    TEMP_STEP,
    get_model_name,
)
from .coordinator import OpenFirenetCoordinator

FAN_MODES = [str(p) for p in range(HEATING_POWER_MIN, HEATING_POWER_MAX + 1, HEATING_POWER_STEP)]
PRESET_MODES = list(OPERATING_MODES.values())


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenFirenetClimate(coordinator, entry)])


class OpenFirenetClimate(CoordinatorEntity[OpenFirenetCoordinator], ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_preset_modes = PRESET_MODES
    _attr_fan_modes = FAN_MODES
    _attr_min_temp = TEMP_MIN
    _attr_max_temp = TEMP_MAX
    _attr_target_temperature_step = TEMP_STEP
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: OpenFirenetCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_climate"

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
    def current_temperature(self) -> float | None:
        sensors = self.coordinator.data.get("sensors", {})
        val = sensors.get("room_temperature")
        if val is not None:
            return float(val)
        return None

    @property
    def target_temperature(self) -> float | None:
        val = self._controls.get("target_temperature")
        if val is not None:
            return float(val)
        return None

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self._controls.get("on") else HVACMode.OFF

    @property
    def preset_mode(self) -> str | None:
        return self._controls.get("mode", "comfort")

    @property
    def fan_mode(self) -> str | None:
        power = self._controls.get("power_percent")
        return str(power) if power is not None else "70"

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.coordinator.async_set_controls(on=(hvac_mode == HVACMode.HEAT))

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_controls(on=True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_controls(on=False)

    async def async_set_temperature(self, **kwargs) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.async_set_controls(target_temperature=float(temp))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.coordinator.async_set_controls(mode=preset_mode)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.coordinator.async_set_controls(power_percent=int(fan_mode))
