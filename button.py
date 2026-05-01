"""Button entities for the MotionBlinds BLE integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from motionblindsble.device import MotionDevice

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MotionConfigEntry
from .const import (
    ATTR_AUTO_POSITION,
    ATTR_BACK_BOTTOM_CLOSE,
    ATTR_BACK_BOTTOM_OPEN,
    ATTR_BACK_TOP_CLOSE,
    ATTR_BACK_TOP_OPEN,
    ATTR_CALIBRATION_BEGIN,
    ATTR_CALIBRATION_END,
    ATTR_CONNECT,
    ATTR_DISCONNECT,
    ATTR_FAVORITE,
    ATTR_POINT_DOWN,
    ATTR_POINT_UP,
    ATTR_SET_ANGLE_BEGIN,
    ATTR_SET_ANGLE_NINETY,
    ATTR_SET_ANGLE_ONE_EIGHTY,
    ATTR_SET_ANGLE_ZERO,
    ATTR_SET_DIRECTION,
    ATTR_SET_ENDPOINT_DOWN,
    ATTR_SET_ENDPOINT_THIRD,
    ATTR_SET_ENDPOINT_UP,
    ATTR_TILT_REVERSE,
    CONF_MAC_CODE,
)
from .entity import MotionblindsBLEEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MotionblindsBLEButtonEntityDescription(ButtonEntityDescription):
    """A button that fires a one-shot device command."""

    command: Callable[[MotionDevice], Coroutine[Any, Any, Any]]


# Connection / favorite buttons (default visible)
CONNECTION_BUTTONS: list[MotionblindsBLEButtonEntityDescription] = [
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_CONNECT,
        translation_key=ATTR_CONNECT,
        entity_category=EntityCategory.CONFIG,
        command=lambda device: device.connect(),
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_DISCONNECT,
        translation_key=ATTR_DISCONNECT,
        entity_category=EntityCategory.CONFIG,
        command=lambda device: device.disconnect(),
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_FAVORITE,
        translation_key=ATTR_FAVORITE,
        entity_category=EntityCategory.CONFIG,
        command=lambda device: device.favorite(),
    ),
]

# Setup / calibration / extras (hidden by default — engineer enables what fits)
EXTENDED_BUTTONS: list[MotionblindsBLEButtonEntityDescription] = [
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_POINT_UP,
        translation_key=ATTR_POINT_UP,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.point_up(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_POINT_DOWN,
        translation_key=ATTR_POINT_DOWN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.point_down(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_CALIBRATION_BEGIN,
        translation_key=ATTR_CALIBRATION_BEGIN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.calibration_begin(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_CALIBRATION_END,
        translation_key=ATTR_CALIBRATION_END,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.calibration_end(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ENDPOINT_UP,
        translation_key=ATTR_SET_ENDPOINT_UP,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_endpoint_up(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ENDPOINT_DOWN,
        translation_key=ATTR_SET_ENDPOINT_DOWN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_endpoint_down(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ENDPOINT_THIRD,
        translation_key=ATTR_SET_ENDPOINT_THIRD,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_endpoint_third(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ANGLE_BEGIN,
        translation_key=ATTR_SET_ANGLE_BEGIN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_angle_begin(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ANGLE_ZERO,
        translation_key=ATTR_SET_ANGLE_ZERO,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_angle_zero(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ANGLE_NINETY,
        translation_key=ATTR_SET_ANGLE_NINETY,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_angle_ninety(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_ANGLE_ONE_EIGHTY,
        translation_key=ATTR_SET_ANGLE_ONE_EIGHTY,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_angle_one_eighty(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_TILT_REVERSE,
        translation_key=ATTR_TILT_REVERSE,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.tilt_reverse(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_AUTO_POSITION,
        translation_key=ATTR_AUTO_POSITION,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.auto_position(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_SET_DIRECTION,
        translation_key=ATTR_SET_DIRECTION,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.set_direction(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_BACK_TOP_OPEN,
        translation_key=ATTR_BACK_TOP_OPEN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.back_top_open(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_BACK_TOP_CLOSE,
        translation_key=ATTR_BACK_TOP_CLOSE,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.back_top_close(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_BACK_BOTTOM_OPEN,
        translation_key=ATTR_BACK_BOTTOM_OPEN,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.back_bottom_open(),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLEButtonEntityDescription(
        key=ATTR_BACK_BOTTOM_CLOSE,
        translation_key=ATTR_BACK_BOTTOM_CLOSE,
        entity_category=EntityCategory.CONFIG,
        command=lambda d: d.back_bottom_close(),
        entity_registry_enabled_default=False,
    ),
]

ALL_BUTTONS = CONNECTION_BUTTONS + EXTENDED_BUTTONS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities based on a config entry."""
    device = entry.runtime_data
    async_add_entities(
        MotionblindsBLEButtonEntity(
            device,
            entry,
            entity_description,
            unique_id_suffix=entity_description.key,
        )
        for entity_description in ALL_BUTTONS
    )


class MotionblindsBLEButtonEntity(MotionblindsBLEEntity, ButtonEntity):
    """A one-shot device command button."""

    entity_description: MotionblindsBLEButtonEntityDescription

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(
            "(%s) Setting up %s button entity",
            self.entry.data[CONF_MAC_CODE],
            self.entity_description.key,
        )

    async def async_press(self) -> None:
        await self.entity_description.command(self.device)
