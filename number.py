"""Number entities for the MotionBlinds BLE integration."""

from __future__ import annotations

import logging

from motionblindsble.device import MotionDevice

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MotionConfigEntry
from .const import ATTR_BRIGHTNESS, CONF_MAC_CODE
from .entity import MotionblindsBLEEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


BRIGHTNESS_DESCRIPTION = NumberEntityDescription(
    key=ATTR_BRIGHTNESS,
    translation_key=ATTR_BRIGHTNESS,
    entity_category=EntityCategory.CONFIG,
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities based on a config entry."""
    device = entry.runtime_data
    async_add_entities([BrightnessNumber(device, entry)])


class BrightnessNumber(MotionblindsBLEEntity, NumberEntity):
    """Brightness setpoint (0–100%)."""

    entity_description: NumberEntityDescription

    def __init__(self, device: MotionDevice, entry: MotionConfigEntry) -> None:
        super().__init__(
            device, entry, BRIGHTNESS_DESCRIPTION, unique_id_suffix=ATTR_BRIGHTNESS
        )
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(
            "(%s) Setting up brightness number",
            self.entry.data[CONF_MAC_CODE],
        )
        self.device.register_brightness_callback(self._async_update_brightness)

    @callback
    def _async_update_brightness(self, value: int | None) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        await self.device.set_brightness(int(value))
        self._attr_native_value = int(value)
        self.async_write_ha_state()
