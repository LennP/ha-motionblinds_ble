"""Binary sensor entities for the MotionBlinds BLE integration."""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CALIBRATION,
    CONF_BLIND_TYPE,
    DOMAIN,
    ICON_CALIBRATION,
    MotionBlindType,
)
from .cover import GenericBlind

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

BINARY_SENSOR_TYPES: dict[str, BinarySensorEntityDescription] = {
    ATTR_CALIBRATION: BinarySensorEntityDescription(
        key=ATTR_CALIBRATION,
        translation_key=ATTR_CALIBRATION,
        icon=ICON_CALIBRATION,
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up calibration binary sensors based on a config entry."""
    blind: GenericBlind = hass.data[DOMAIN][entry.entry_id]

    if blind.config_entry.data[CONF_BLIND_TYPE] == MotionBlindType.POSITION_CURTAIN:
        _LOGGER.info("Setting up CalibrationBinarySensor")
        async_add_entities([CalibrationBinarySensor(blind)])


class CalibrationBinarySensor(BinarySensorEntity):
    """Representation of a calibration binary sensor."""

    def __init__(self, blind: GenericBlind) -> None:
        """Initialize the calibration binary sensor."""
        self.entity_description = BINARY_SENSOR_TYPES[ATTR_CALIBRATION]
        self._blind = blind
        self._attr_name = f"{blind.name} Calibration"
        self._attr_unique_id = f"{blind.unique_id}_calibration"
        self._attr_device_info = blind.device_info

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_calibrated_callback(self.async_update_calibrated)
        return await super().async_added_to_hass()

    @callback
    def async_update_calibrated(self, calibrated: bool) -> None:
        """Update the calibration binary sensor value."""
        self._attr_is_on = not calibrated
        self.async_write_ha_state()
