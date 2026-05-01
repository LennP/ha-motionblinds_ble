"""Switch entities for the MotionBlinds BLE integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from motionblindsble.device import MotionDevice

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MotionConfigEntry
from .const import (
    ATTR_COMBO_SENSOR,
    ATTR_LIGHT,
    ATTR_RAIN_SENSOR,
    ATTR_SLOW_STOP,
    ATTR_WIND_SENSOR,
    CONF_MAC_CODE,
)
from .entity import MotionblindsBLEEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MotionblindsBLESwitchEntityDescription(SwitchEntityDescription):
    """Describes a MotionBlinds BLE switch."""

    turn_on: Callable[[MotionDevice], Coroutine[Any, Any, bool]]
    turn_off: Callable[[MotionDevice], Coroutine[Any, Any, bool]]
    register_state_callback: (
        Callable[[MotionDevice], Callable[[Callable[[bool | None], None]], None]] | None
    ) = None


SWITCH_TYPES: tuple[MotionblindsBLESwitchEntityDescription, ...] = (
    MotionblindsBLESwitchEntityDescription(
        key=ATTR_LIGHT,
        translation_key=ATTR_LIGHT,
        entity_category=EntityCategory.CONFIG,
        turn_on=lambda d: d.light_on(),
        turn_off=lambda d: d.light_off(),
    ),
    MotionblindsBLESwitchEntityDescription(
        key=ATTR_RAIN_SENSOR,
        translation_key=ATTR_RAIN_SENSOR,
        entity_category=EntityCategory.CONFIG,
        turn_on=lambda d: d.rain_sensor(True),
        turn_off=lambda d: d.rain_sensor(False),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESwitchEntityDescription(
        key=ATTR_WIND_SENSOR,
        translation_key=ATTR_WIND_SENSOR,
        entity_category=EntityCategory.CONFIG,
        turn_on=lambda d: d.wind_sensor(True),
        turn_off=lambda d: d.wind_sensor(False),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESwitchEntityDescription(
        key=ATTR_COMBO_SENSOR,
        translation_key=ATTR_COMBO_SENSOR,
        entity_category=EntityCategory.CONFIG,
        turn_on=lambda d: d.combo_sensor(True),
        turn_off=lambda d: d.combo_sensor(False),
        entity_registry_enabled_default=False,
    ),
    MotionblindsBLESwitchEntityDescription(
        key=ATTR_SLOW_STOP,
        translation_key=ATTR_SLOW_STOP,
        entity_category=EntityCategory.CONFIG,
        turn_on=lambda d: d.slow_stop(True),
        turn_off=lambda d: d.slow_stop(False),
        register_state_callback=lambda d: d.register_slow_stop_callback,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities based on a config entry."""
    device = entry.runtime_data
    async_add_entities(
        MotionblindsBLESwitchEntity(device, entry, description)
        for description in SWITCH_TYPES
    )


class MotionblindsBLESwitchEntity(MotionblindsBLEEntity, SwitchEntity):
    """A MotionBlinds BLE switch entity."""

    entity_description: MotionblindsBLESwitchEntityDescription

    def __init__(
        self,
        device: MotionDevice,
        entry: MotionConfigEntry,
        entity_description: MotionblindsBLESwitchEntityDescription,
    ) -> None:
        super().__init__(
            device, entry, entity_description, unique_id_suffix=entity_description.key
        )
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(
            "(%s) Setting up %s switch",
            self.entry.data[CONF_MAC_CODE],
            self.entity_description.key,
        )
        if self.entity_description.register_state_callback is not None:
            self.entity_description.register_state_callback(self.device)(
                self._async_update_state
            )

    @callback
    def _async_update_state(self, value: bool | None) -> None:
        self._attr_is_on = value
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self.entity_description.turn_on(self.device):
            self._attr_is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self.entity_description.turn_off(self.device):
            self._attr_is_on = False
            self.async_write_ha_state()
