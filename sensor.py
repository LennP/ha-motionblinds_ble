"""Sensor entities for the MotionBlinds BLE integration."""

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.bluetooth.wrappers import BLEDevice

from .const import (
    ATTR_BATTERY,
    ATTR_CALIBRATION,
    ATTR_CONNECTION_TYPE,
    ATTR_SIGNAL_STRENGTH,
    CONF_BLIND_TYPE,
    DOMAIN,
    ICON_CALIBRATION,
    ICON_CONNECTION_TYPE,
    MotionBlindEntityType,
    MotionCalibrationType,
)
from .cover import GenericBlind, PositionCurtainBlind
from .motionblinds_ble.const import MotionConnectionType

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    ATTR_BATTERY: SensorEntityDescription(
        key=ATTR_BATTERY,
        translation_key=ATTR_BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    ATTR_CONNECTION_TYPE: SensorEntityDescription(
        key=ATTR_CONNECTION_TYPE,
        translation_key=ATTR_CONNECTION_TYPE,
        icon=ICON_CONNECTION_TYPE,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=[connection_type.value for connection_type in MotionConnectionType],
        has_entity_name=True,
    ),
    ATTR_CALIBRATION: SensorEntityDescription(
        key=ATTR_CALIBRATION,
        translation_key=ATTR_CALIBRATION,
        icon=ICON_CALIBRATION,
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        has_entity_name=True,
    ),
    ATTR_SIGNAL_STRENGTH: SensorEntityDescription(
        key=ATTR_SIGNAL_STRENGTH,
        translation_key=ATTR_SIGNAL_STRENGTH,
        # icon=ICON_SIGNAL_STRENGTH,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="dBm",
        has_entity_name=True,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up battery sensors based on a config entry."""
    _LOGGER.info("Setting up sensors")
    blind: GenericBlind = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        BatterySensor(blind),
        ConnectionSensor(blind),
        SignalStrengthSensor(blind),
    ]
    if (
        blind.config_entry.data[CONF_BLIND_TYPE]
        == MotionBlindEntityType.POSITION_CURTAIN
    ):
        entities.append(CalibrationSensor(blind))
    async_add_entities(entities)


class BatterySensor(SensorEntity):
    """Representation of a battery sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the battery sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_BATTERY]
        self._blind = blind
        self._attr_unique_id = f"{blind.unique_id}_{ATTR_BATTERY}"
        self._attr_device_info = blind.device_info
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_battery_callback(
            self.async_update_battery_percentage
        )
        return await super().async_added_to_hass()

    @callback
    def async_update_battery_percentage(self, battery_percentage: int) -> None:
        """Update the battery percentage sensor value."""
        self._attr_native_value = (
            str(battery_percentage) if battery_percentage else None
        )
        self.async_write_ha_state()


class ConnectionSensor(SensorEntity):
    """Representation of a connection sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the connection sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_CONNECTION_TYPE]
        self._blind = blind
        self._attr_unique_id = f"{blind.unique_id}_{ATTR_CONNECTION_TYPE}"
        self._attr_device_info = blind.device_info
        self._attr_native_value = MotionConnectionType.DISCONNECTED

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_connection_callback(self.async_update_connection)
        return await super().async_added_to_hass()

    @callback
    def async_update_connection(self, connection_type: MotionConnectionType) -> None:
        """Update the connection sensor value."""
        self._attr_native_value = connection_type.value
        self.async_write_ha_state()


class CalibrationSensor(SensorEntity):
    """Representation of a calibration sensor."""

    def __init__(self, blind: PositionCurtainBlind) -> None:
        """Initialize the calibration sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_CALIBRATION]
        self._blind = blind
        self._attr_unique_id = f"{blind.unique_id}_{ATTR_CALIBRATION}"
        self._attr_device_info = blind.device_info
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_calibration_callback(self.async_update_calibrated)
        return await super().async_added_to_hass()

    @callback
    def async_update_calibrated(self, calibration_type: MotionCalibrationType) -> None:
        """Update the calibration sensor value."""
        self._attr_native_value = calibration_type
        self.async_write_ha_state()


class SignalStrengthSensor(SensorEntity):
    """Representation of a signal strength sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the calibration sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_SIGNAL_STRENGTH]
        self._blind = blind
        self._attr_unique_id = f"{blind.unique_id}_{ATTR_SIGNAL_STRENGTH}"
        self._attr_device_info = blind.device_info
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_signal_strength_callback(
            self.async_update_signal_strength
        )
        self.async_update_signal_strength(self._blind.device_rssi)
        return await super().async_added_to_hass()

    @callback
    def async_update_signal_strength(self, signal_strength: int) -> None:
        """Update the calibration sensor value."""
        self._attr_native_value = signal_strength
        self.async_write_ha_state()
