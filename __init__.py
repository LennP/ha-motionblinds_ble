"""MotionBlinds BLE integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CONNECTION_TIMEOUT,
    CONF_MAC_CODE,
    DOMAIN,
    SERVICE_CONNECT,
    SERVICE_DISCONNECT,
    SERVICE_FAVORITE,
    SERVICE_STATUS,
)
from .cover import GenericBlind
from .motionblinds_ble.crypt import MotionCrypt

PLATFORMS: list[Platform] = [
    Platform.COVER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.BUTTON,
]

_LOGGER = logging.getLogger(__name__)

GENERIC_ENTITY_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.comp_entity_ids,
    }
)

CONNECT_SERVICE_SCHEMA = GENERIC_ENTITY_SERVICE_SCHEMA.extend(
    {
        vol.Required(ATTR_CONNECTION_TIMEOUT): vol.All(vol.Coerce(int)),
    }
)


@dataclass
class Service:
    service: str
    service_func: Callable
    schema: Optional[vol.Schema] = None


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up MotionBlinds BLE integration."""

    _LOGGER.info("Setting up MotionBlinds BLE integration")

    # The correct time is needed for encryption
    _LOGGER.info(f"Setting timezone for encryption: {hass.config.time_zone}")
    MotionCrypt.set_timezone(hass.config.time_zone)

    def generic_entity_service(
        callback: Callable[[GenericBlind], None]
    ) -> Callable[[ServiceCall], None]:
        async def service_func(call: ServiceCall) -> None:
            for motionblind_entity_id in call.data[ATTR_ENTITY_ID]:
                motionblind_entity: GenericBlind = hass.data[DOMAIN].get(
                    motionblind_entity_id
                )
                if motionblind_entity:
                    await callback(motionblind_entity, call)

        return service_func

    _LOGGER.info("Registering services")

    async def connect_service(blind: GenericBlind, call: ServiceCall) -> None:
        if await blind.async_connect():
            blind.async_refresh_disconnect_timer(
                timeout=call.data[ATTR_CONNECTION_TIMEOUT], force=True
            )

    async def disconnect_service(blind: GenericBlind, call: ServiceCall) -> None:
        await blind.async_disconnect()

    async def favorite_service(blind: GenericBlind, call: ServiceCall) -> None:
        await blind.async_favorite()

    async def status_service(blind: GenericBlind, call: ServiceCall) -> None:
        await blind.async_status_query()

    services = [
        Service(
            SERVICE_CONNECT,
            generic_entity_service(connect_service),
            CONNECT_SERVICE_SCHEMA,
        ),
        Service(
            SERVICE_DISCONNECT,
            generic_entity_service(disconnect_service),
            GENERIC_ENTITY_SERVICE_SCHEMA,
        ),
        Service(
            SERVICE_FAVORITE,
            generic_entity_service(favorite_service),
            GENERIC_ENTITY_SERVICE_SCHEMA,
        ),
        Service(
            SERVICE_STATUS,
            generic_entity_service(status_service),
            GENERIC_ENTITY_SERVICE_SCHEMA,
        ),
    ]

    for serv in services:
        hass.services.async_register(
            DOMAIN, serv.service, serv.service_func, schema=serv.schema
        )

    _LOGGER.info("Finished registering services")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MotionBlinds BLE device from a config entry."""

    _LOGGER.info(f"({entry.data[CONF_MAC_CODE]}) Setting up device")

    hass.data.setdefault(DOMAIN, {})

    # First setup cover since sensor, select and button entities require the cover
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.COVER])
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.SENSOR, Platform.SELECT, Platform.BUTTON],
    )

    _LOGGER.info(f"({entry.data[CONF_MAC_CODE]}) Finished setting up device")

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload MotionBlinds BLE device from a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
