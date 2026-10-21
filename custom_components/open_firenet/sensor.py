from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfMass,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, get_model_name
from .coordinator import OpenFirenetCoordinator


@dataclass(frozen=True, kw_only=True)
class OpenFirenetSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]
    # Only create the entity when the bridge reports a value for it (e.g. air flaps, which not every stove has).
    optional: bool = False


# Without a RIKA room sensor the stove reports its "no sensor" constant (raw 1024 -> 102.4 degC). Newer bridge
# firmware publishes null and room_sensor_connected=false; 102.4 is also filtered for older firmware.
NO_ROOM_SENSOR_VALUE = 102.4


def room_temperature(data: dict[str, Any]) -> float | None:
    sensors = data.get("sensors", {})
    if sensors.get("room_sensor_connected") is False:
        return None
    value = sensors.get("room_temperature")
    if value is None or abs(float(value) - NO_ROOM_SENSOR_VALUE) < 0.05:
        return None
    return float(value)


# The states of the stove, as the bridge names them in `stove.state`. The sensor gives the key and Home Assistant
# shows its translation (issue openfirenet/open-firenet#105: it used to give the bridge's English label, in every
# language).
STOVE_STATES = [
    "off",
    "standby",
    "ignition",
    "flame_start",
    "heating",
    "cleaning",
    "burn_off",
    "splitlog",
    "splitlog_check",
    "splitlog_refuel",
    "splitlog_no_refuel",
    "unknown",
]


def _stove_state(data: dict[str, Any]) -> str | None:
    """The state key; a state a newer bridge firmware would add is given as "unknown", not as an error."""
    state = data.get("stove", {}).get("state")
    if state is None:
        return None
    return state if state in STOVE_STATES else "unknown"


SENSOR_TYPES: tuple[OpenFirenetSensorEntityDescription, ...] = (
    OpenFirenetSensorEntityDescription(
        key="room_temperature",
        name="Room Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=room_temperature,
    ),
    OpenFirenetSensorEntityDescription(
        key="combustion_temperature",
        name="Combustion Chamber Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("sensors", {}).get("combustion_temperature"),
    ),
    OpenFirenetSensorEntityDescription(
        key="board_temperature",
        name="Mainboard Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("sensors", {}).get("board_temperature"),
    ),
    OpenFirenetSensorEntityDescription(
        key="pellets_total_kg",
        name="Pellets Consumed",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("sensors", {}).get("pellets_total_kg"),
    ),
    OpenFirenetSensorEntityDescription(
        key="pellet_hours",
        name="Pellet Operating Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("sensors", {}).get("pellet_hours"),
    ),
    OpenFirenetSensorEntityDescription(
        key="service_countdown_kg",
        name="Service Countdown",
        native_unit_of_measurement=UnitOfMass.KILOGRAMS,
        device_class=SensorDeviceClass.WEIGHT,
        value_fn=lambda data: data.get("sensors", {}).get("service_countdown_kg"),
    ),
    OpenFirenetSensorEntityDescription(
        key="fan_speed_rpm",
        name="Flue Draft Fan Speed",
        native_unit_of_measurement="RPM",
        value_fn=lambda data: data.get("sensors", {}).get("fan_speed_rpm"),
    ),
    OpenFirenetSensorEntityDescription(
        key="auger_speed_rpm",
        name="Pellet Auger Speed",
        native_unit_of_measurement="RPM",
        value_fn=lambda data: data.get("sensors", {}).get("auger_speed_rpm"),
    ),
    OpenFirenetSensorEntityDescription(
        key="power_actual_percent",
        name="Actual Heating Power",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:fire",
        optional=True,  # bridge firmware after 4.1.1
        value_fn=lambda data: data.get("sensors", {}).get("power_actual_percent"),
    ),
    OpenFirenetSensorEntityDescription(
        key="air_flaps_percent",
        name="Air Flaps",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        optional=True,
        value_fn=lambda data: data.get("sensors", {}).get("air_flaps_percent"),
    ),
    OpenFirenetSensorEntityDescription(
        key="air_flaps_target_percent",
        name="Air Flaps Target",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        optional=True,
        value_fn=lambda data: data.get("sensors", {}).get("air_flaps_target_percent"),
    ),
    # The bridge gives these two only in its list of raw values. The stove's display shows the motor in per mille
    # and its current without a unit, so only the motor has a unit.
    OpenFirenetSensorEntityDescription(
        key="insertion_motor",
        name="Insertion Motor",
        native_unit_of_measurement="‰",
        state_class=SensorStateClass.MEASUREMENT,
        optional=True,
        value_fn=lambda data: data.get("raw_sensors", {}).get("insertionMotor"),
    ),
    OpenFirenetSensorEntityDescription(
        key="insertion_motor_current",
        name="Insertion Motor Current",
        state_class=SensorStateClass.MEASUREMENT,
        optional=True,
        value_fn=lambda data: data.get("raw_sensors", {}).get("insertionCurrent"),
    ),
    OpenFirenetSensorEntityDescription(
        key="error_code",
        name="Error Code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("stove", {}).get("error_code"),
    ),
    OpenFirenetSensorEntityDescription(
        key="error_sub",
        name="Error Sub-code",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("stove", {}).get("error_sub"),
    ),
    OpenFirenetSensorEntityDescription(
        key="warning_code",
        name="Warning Code",
        entity_category=EntityCategory.DIAGNOSTIC,
        optional=True,
        value_fn=lambda data: data.get("stove", {}).get("warning_code"),
    ),
    OpenFirenetSensorEntityDescription(
        key="stove_state",
        name="Stove State",
        device_class=SensorDeviceClass.ENUM,
        options=STOVE_STATES,
        value_fn=_stove_state,
    ),
    OpenFirenetSensorEntityDescription(
        key="wifi_rssi",
        name="WiFi RSSI",
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("device", {}).get(
            "rssi", data.get("device", {}).get("wifi_rssi")
        ),
    ),
    OpenFirenetSensorEntityDescription(
        key="uptime_seconds",
        name="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("device", {}).get("uptime_seconds"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenFirenetCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OpenFirenetSensor(coordinator, entry, description)
            for description in SENSOR_TYPES
            if not description.optional or description.value_fn(coordinator.data) is not None
        ]
    )


class OpenFirenetSensor(CoordinatorEntity[OpenFirenetCoordinator], SensorEntity):
    entity_description: OpenFirenetSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OpenFirenetCoordinator,
        entry: ConfigEntry,
        description: OpenFirenetSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_translation_key = description.key
        self._attr_unique_id = f"{entry.entry_id}_sensor_{description.key}"

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
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
