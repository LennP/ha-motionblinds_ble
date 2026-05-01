"""Select entities for the MotionBlinds BLE integration."""

from __future__ import annotations

import logging

from motionblindsble.const import MotionBlindType, MotionSpeedLevel
from motionblindsble.device import MotionDevice

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MotionConfigEntry
from .const import ATTR_DEVICE_TYPE, ATTR_SPEED, CONF_MAC_CODE
from .entity import MotionblindsBLEEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


SPEED_DESCRIPTION = SelectEntityDescription(
    key=ATTR_SPEED,
    translation_key=ATTR_SPEED,
    entity_category=EntityCategory.CONFIG,
    options=["1", "2", "3"],
)

DEVICE_TYPE_DESCRIPTION = SelectEntityDescription(
    key=ATTR_DEVICE_TYPE,
    translation_key=ATTR_DEVICE_TYPE,
    entity_category=EntityCategory.CONFIG,
    options=["E", "ED"],
    entity_registry_enabled_default=False,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MotionConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities based on a config entry."""
    device = entry.runtime_data

    entities: list[SelectEntity] = []
    if device.blind_type not in {MotionBlindType.CURTAIN, MotionBlindType.VERTICAL}:
        entities.append(SpeedSelect(device, entry, SPEED_DESCRIPTION))
    entities.append(DeviceTypeSelect(device, entry, DEVICE_TYPE_DESCRIPTION))
    async_add_entities(entities)


class SpeedSelect(MotionblindsBLEEntity, SelectEntity):
    """Speed level (1/2/3)."""

    def __init__(
        self,
        device: MotionDevice,
        entry: MotionConfigEntry,
        entity_description: SelectEntityDescription,
    ) -> None:
        super().__init__(
            device, entry, entity_description, unique_id_suffix=entity_description.key
        )
        self._attr_current_option = None

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(
            "(%s) Setting up speed select entity",
            self.entry.data[CONF_MAC_CODE],
        )
        self.device.register_speed_callback(self.async_update_speed)

    @callback
    def async_update_speed(self, speed_level: MotionSpeedLevel | None) -> None:
        self._attr_current_option = str(speed_level.value) if speed_level else None
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        speed_level = MotionSpeedLevel(int(option))
        await self.device.speed(speed_level)
        self._attr_current_option = str(speed_level.value) if speed_level else None
        self.async_write_ha_state()


class DeviceTypeSelect(MotionblindsBLEEntity, SelectEntity):
    """Device type (E / ED)."""

    def __init__(
        self,
        device: MotionDevice,
        entry: MotionConfigEntry,
        entity_description: SelectEntityDescription,
    ) -> None:
        super().__init__(
            device, entry, entity_description, unique_id_suffix=entity_description.key
        )
        self._attr_current_option = None

    async def async_added_to_hass(self) -> None:
        _LOGGER.debug(
            "(%s) Setting up device-type select entity",
            self.entry.data[CONF_MAC_CODE],
        )
        self.device.register_point_type_callback(self._async_update_point_type)

    @callback
    def _async_update_point_type(self, value: str | None) -> None:
        self._attr_current_option = value
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        if option == "E":
            await self.device.set_device_type_e()
        else:
            await self.device.set_device_type_ed()
        self._attr_current_option = option
        self.async_write_ha_state()
