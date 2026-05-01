"""Sensor entities for the MotionBlinds BLE integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from math import ceil

from motionblindsble.const import (
    MotionBlindType,
    MotionCalibrationType,
    MotionConnectionType,
)
from motionblindsble.device import MotionDevice

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    UnitOfTemperature,
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import MotionConfigEntry
from .const import (
    ATTR_BATTERY,
    ATTR_BRIGHTNESS,
    ATTR_CALIBRATION,
    ATTR_CONNECTION,
    ATTR_DIRECTION,
    ATTR_ENDPOINTS,
    ATTR_ILLUMINANCE,
    ATTR_POINT_TYPE,
    ATTR_SENSOR_STATUS,
    ATTR_SIGNAL_STRENGTH,
    ATTR_TEMPERATURE,
    CONF_MAC_CODE,
)
from .device import EndpointInfo, SensorStatus
from .entity import MotionblindsBLEEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MotionblindsBLESensorEntityDescription[_T](SensorEntityDescription):
    """Entity description of a sensor entity with initial_value attribute."""

    initial_value: str | None = None
    register_callback_func: Callable[
        [MotionDevice], Callable[[Callable[[_T | None], None]], None]
    ]
    value_func: Callable[[_T | None], StateType]
    is_supported: Callable[[MotionDevice], bool] = lambda device: True


SENSORS: tuple[MotionblindsBLESensorEntityDescription, ...] = (
    MotionblindsBLESensorEntityDescription[MotionConnectionType](
        key=ATTR_CONNECTION,
        translation_key=ATTR_CONNECTION,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=["connected", "connecting", "disconnected", "disconnecting"],
        initial_value=MotionConnectionType.DISCONNECTED.value,
        register_callback_func=lambda device: device.register_connection_callback,
        value_func=lambda value: value.value if value else None,
    ),
    MotionblindsBLESensorEntityDescription[MotionCalibrationType](
        key=ATTR_CALIBRATION,
        translation_key=ATTR_CALIBRATION,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=["calibrated", "uncalibrated", "calibrating"],
        register_callback_func=lambda device: device.register_calibration_callback,
        value_func=lambda value: value.value if value else None,
        is_supported=lambda device: (
            device.blind_type in {MotionBlindType.CURTAIN, MotionBlindType.VERTICAL}
        ),
    ),
    MotionblindsBLESensorEntityDescription[int](
        key=ATTR_SIGNAL_STRENGTH,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        register_callback_func=lambda device: device.register_signal_strength_callback,
        value_func=lambda value: value,
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESensorEntityDescription[int](
        key=ATTR_TEMPERATURE,
        translation_key=ATTR_TEMPERATURE,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        register_callback_func=lambda device: device.register_temperature_callback,
        value_func=lambda value: value,
    ),
    MotionblindsBLESensorEntityDescription[int](
        key=ATTR_ILLUMINANCE,
        translation_key=ATTR_ILLUMINANCE,
        device_class=SensorDeviceClass.ILLUMINANCE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=LIGHT_LUX,
        register_callback_func=lambda device: device.register_illuminance_callback,
        value_func=lambda value: value,
    ),
    MotionblindsBLESensorEntityDescription[int](
        key=ATTR_BRIGHTNESS,
        translation_key=ATTR_BRIGHTNESS,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        register_callback_func=lambda device: device.register_brightness_callback,
        value_func=lambda value: value,
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESensorEntityDescription[bool](
        key=ATTR_DIRECTION,
        translation_key=ATTR_DIRECTION,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=["normal", "reversed"],
        register_callback_func=lambda device: device.register_direction_callback,
        value_func=lambda value: (
            None if value is None else ("reversed" if value else "normal")
        ),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESensorEntityDescription[str](
        key=ATTR_POINT_TYPE,
        translation_key=ATTR_POINT_TYPE,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=["E", "ED"],
        register_callback_func=lambda device: device.register_point_type_callback,
        value_func=lambda value: value,
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESensorEntityDescription[EndpointInfo](
        key=ATTR_ENDPOINTS,
        translation_key=ATTR_ENDPOINTS,
        entity_category=EntityCategory.DIAGNOSTIC,
        register_callback_func=lambda device: device.register_endpoint_callback,
        value_func=lambda value: (
            None
            if value is None
            else "+".join(
                flag
                for flag, present in (
                    ("up", value.up),
                    ("down", value.down),
                    ("favorite", value.favorite),
                )
                if present
            )
            or "none"
        ),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESensorEntityDescription[SensorStatus](
        key=ATTR_SENSOR_STATUS,
        translation_key=ATTR_SENSOR_STATUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        register_callback_func=lambda device: device.register_sensor_status_callback,
        value_func=lambda value: (None if value is None else f"0x{value.raw:02x}"),
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities based on a config entry."""

    device = entry.runtime_data

    entities: list[SensorEntity] = [
        MotionblindsBLESensorEntity(device, entry, description)
        for description in SENSORS
        if description.is_supported(device)
    ]
    entities.append(BatterySensor(device, entry))
    async_add_entities(entities)


class MotionblindsBLESensorEntity[_T](MotionblindsBLEEntity, SensorEntity):
    """Representation of a sensor entity."""

    entity_description: MotionblindsBLESensorEntityDescription[_T]

    def __init__(
        self,
        device: MotionDevice,
        entry: MotionConfigEntry,
        entity_description: MotionblindsBLESensorEntityDescription[_T],
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(
            device, entry, entity_description, unique_id_suffix=entity_description.key
        )
        self._attr_native_value = entity_description.initial_value

    async def async_added_to_hass(self) -> None:
        """Register the device callback."""
        _LOGGER.debug(
            "(%s) Setting up %s sensor entity",
            self.entry.data[CONF_MAC_CODE],
            self.entity_description.key.replace("_", " "),
        )

        def async_callback(value: _T | None) -> None:
            """Update the sensor value."""
            self._attr_native_value = self.entity_description.value_func(value)
            self.async_write_ha_state()

        self.entity_description.register_callback_func(self.device)(async_callback)


class BatterySensor(MotionblindsBLEEntity, SensorEntity):
    """Representation of a battery sensor entity."""

    def __init__(
        self,
        device: MotionDevice,
        entry: MotionConfigEntry,
    ) -> None:
        """Initialize the sensor entity."""
        entity_description = SensorEntityDescription(
            key=ATTR_BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        super().__init__(device, entry, entity_description, unique_id_suffix=ATTR_BATTERY)

    async def async_added_to_hass(self) -> None:
        """Register device callbacks."""
        await super().async_added_to_hass()
        self.device.register_battery_callback(self.async_update_battery)

    @callback
    def async_update_battery(
        self,
        battery_percentage: int | None,
        is_charging: bool | None,
        is_wired: bool | None,
    ) -> None:
        """Update the battery sensor value and icon."""
        self._attr_native_value = battery_percentage
        if battery_percentage is None:
            self._attr_icon = "mdi:battery-unknown"
        elif is_wired:
            self._attr_icon = "mdi:power-plug-outline"
        elif battery_percentage > 90 and not is_charging:
            self._attr_icon = "mdi:battery"
        elif battery_percentage <= 5 and not is_charging:
            self._attr_icon = "mdi:battery-alert-variant-outline"
        else:
            battery_icon_prefix = (
                "mdi:battery-charging" if is_charging else "mdi:battery"
            )
            battery_percentage_multiple_ten = ceil(battery_percentage / 10) * 10
            self._attr_icon = f"{battery_icon_prefix}-{battery_percentage_multiple_ten}"
        self.async_write_ha_state()
