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

from .const import DOMAIN, ATTR_BATTERY, ATTR_CONNECTION_TYPE, ICON_CONNECTION_TYPE
from .cover import GenericBlind

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
    ),
    ATTR_CONNECTION_TYPE: SensorEntityDescription(
        key=ATTR_CONNECTION_TYPE,
        translation_key=ATTR_CONNECTION_TYPE,
        icon=ICON_CONNECTION_TYPE,
        device_class=SensorDeviceClass.ENUM,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up battery sensors based on a config entry."""
    _LOGGER.info("Setting up BatterySensor")
    blind: GenericBlind = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([BatterySensor(blind), ConnectionSensor(blind)])


class BatterySensor(SensorEntity):
    """Representation of a battery sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the battery sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_BATTERY]
        self._blind = blind
        self._attr_name = f"{blind.name} Battery"
        self._attr_unique_id = f"{blind.unique_id}_battery"
        self._attr_device_info = blind.device_info
        self._attr_native_unit_of_measurement = "%"
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
        self._attr_native_value = str(battery_percentage)
        self.async_write_ha_state()


class ConnectionSensor(SensorEntity):
    """Representation of a connection sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the connection sensor."""
        self.entity_description = SENSOR_TYPES[ATTR_CONNECTION_TYPE]
        self._blind = blind
        self._attr_name = f"{blind.name} Connected"
        self._attr_unique_id = f"{blind.unique_id}_connection"
        self._attr_device_info = blind.device_info
        self._attr_options = [
            connection_type.value for connection_type in MotionConnectionType
        ]
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
