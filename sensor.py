"""Sensor entities for the MotionBlinds BLE integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .cover import PositionBlind
from .const import DOMAIN

import logging

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
    """Set up RollerBlind sensors based on a config entry."""
    entities: list[SensorEntity] = []
    _LOGGER.info("Setting up BatterySensor")

    blind: PositionBlind = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([RollerBlindBatterySensor(blind)])


class RollerBlindBatterySensor(SensorEntity):
    """Representation of a RollerBlind battery sensor."""

    def __init__(self, roller_blind: PositionBlind) -> None:
        """Initialize the battery sensor."""
        self._roller_blind = roller_blind
        self._attr_name = f"{roller_blind.name} Battery"
        self._attr_unique_id = f"{roller_blind.unique_id}_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_device_info = roller_blind.device_info
        self._attr_native_unit_of_measurement = "%"
        self._attr_native_value = None

        roller_blind.register_battery_callback(self._async_update_battery_percentage)

    @callback
    def _async_update_battery_percentage(self, battery_percentage: int) -> None:
        self._attr_native_value = str(battery_percentage)
        self.async_write_ha_state()
