"""The MotionBlinds BLE integration."""
from __future__ import annotations
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .motionblinds_ble.crypt import MotionCrypt

PLATFORMS: list[Platform] = [Platform.COVER, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType):
    """Set up MotionBlinds BLE integration."""

    _LOGGER.warning("Loading MotionBlinds BLE integration")
    _LOGGER.warning(f"Current timezone: {hass.config.time_zone}")

    # The correct time is needed for encryption
    MotionCrypt.set_timezone(hass.config.time_zone)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MotionBlinds BLE device from a config entry."""

    _LOGGER.info("Entering async_setup_entry")

    hass.data.setdefault(DOMAIN, {})

    await hass.config_entries.async_forward_entry_setups(entry, [Platform.COVER])
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    _LOGGER.info("Fully loaded entity")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload MotionBlinds BLE device from a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
