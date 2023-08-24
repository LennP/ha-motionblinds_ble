"""Sensor entities for the MotionBlinds BLE integration."""

import logging

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTR_SPEED, DOMAIN, ICON_SPEED
from .cover import PositionBlind
from .motionblinds_ble.const import MotionSpeedLevel

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


SELECT_TYPES: dict[str, SelectEntityDescription] = {
    ATTR_SPEED: SelectEntityDescription(
        key=ATTR_SPEED,
        translation_key=ATTR_SPEED,
        icon=ICON_SPEED,
        entity_category=EntityCategory.CONFIG,
    )
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up speed select entities based on a config entry."""
    _LOGGER.info("Setting up SpeedSelect")
    blind: PositionBlind = hass.data[DOMAIN][entry.entry_id]

    async_add_entities([SpeedSelect(blind)])


class SpeedSelect(SelectEntity):
    """Representation of a speed select entity."""

    def __init__(self, blind: PositionBlind) -> None:
        """Initialize the speed select entity."""
        self.entity_description = SELECT_TYPES[ATTR_SPEED]
        self._blind = blind
        self._attr_name: str = f"{blind.name} Motor speed"
        self._attr_unique_id: str = f"{blind.unique_id}_speed"
        # Groups the entities together
        self._attr_device_info = blind.device_info
        self._attr_current_option: str = None
        self._attr_options: [str] = [
            str(speed_level.value) for speed_level in MotionSpeedLevel
        ]

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        self._blind.async_register_speed_callback(self.async_update_speed)
        return await super().async_added_to_hass()

    @callback
    def async_update_speed(self, speed_level: MotionSpeedLevel) -> None:
        """Update the speed level."""
        self._attr_current_option = str(speed_level.value)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected speed_level."""
        await self._blind.async_speed(MotionSpeedLevel(int(option)))
        self.async_write_ha_state()
