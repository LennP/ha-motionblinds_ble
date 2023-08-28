"""Button entities for the MotionBlinds BLE integration."""

import logging

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_CONNECT,
    ATTR_DISCONNECT,
    ATTR_FAVORITE,
    DOMAIN,
    ICON_CONNECT,
    ICON_DISCONNECT,
    ICON_FAVORITE,
)
from .cover import GenericBlind
from collections.abc import Callable
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass
class CommandButtonEntityDescription(ButtonEntityDescription):
    command_callback: Callable[[GenericBlind], None] | None = None


async def command_connect(blind: GenericBlind) -> None:
    await blind.async_connect()


async def command_disconnect(blind: GenericBlind) -> None:
    await blind.async_disconnect()


async def command_favorite(blind: GenericBlind) -> None:
    await blind.async_favorite()


BUTTON_TYPES: dict[str, CommandButtonEntityDescription] = {
    ATTR_CONNECT: CommandButtonEntityDescription(
        key=ATTR_CONNECT,
        translation_key=ATTR_CONNECT,
        icon=ICON_CONNECT,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        command_callback=command_connect,
    ),
    ATTR_DISCONNECT: CommandButtonEntityDescription(
        key=ATTR_DISCONNECT,
        translation_key=ATTR_DISCONNECT,
        icon=ICON_DISCONNECT,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        command_callback=command_disconnect,
    ),
    ATTR_FAVORITE: CommandButtonEntityDescription(
        key=ATTR_FAVORITE,
        translation_key=ATTR_FAVORITE,
        icon=ICON_FAVORITE,
        entity_category=EntityCategory.CONFIG,
        has_entity_name=True,
        command_callback=command_favorite,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up buttons based on a config entry."""
    blind: GenericBlind = hass.data[DOMAIN][entry.entry_id]

    _LOGGER.info("Setting up buttons")
    async_add_entities(
        [
            GenericCommandButton(blind, entity_description)
            for entity_description in BUTTON_TYPES.values()
        ]
    )


class GenericCommandButton(ButtonEntity):
    """Representation of a command button."""

    def __init__(
        self, blind: GenericBlind, entity_description: CommandButtonEntityDescription
    ) -> None:
        """Initialize the command button."""
        _LOGGER.info(f"Setting up {entity_description.key} button")
        self.entity_description = entity_description
        self._blind = blind
        self._attr_unique_id = f"{blind.unique_id}_{entity_description.key}"
        self._attr_device_info = blind.device_info

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.entity_description.command_callback(self._blind)
