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

from .const import DOMAIN
from .cover import PositionBlind

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

SENSOR_TYPES: dict[str, SensorEntityDescription] = {
    "battery": SensorEntityDescription(
        key="battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up battery sensors based on a config entry."""
    _LOGGER.info("Setting up BatterySensor")
    blind: PositionBlind = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([BatterySensor(blind)])


class BatterySensor(SensorEntity):
    """Representation of a battery sensor."""

    def __init__(self, blind: PositionBlind) -> None:
        """Initialize the battery sensor."""
        self._blind = blind
        self._attr_name = f"{blind.name} Battery"
        self._attr_unique_id = f"{blind.unique_id}_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
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
