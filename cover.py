"""Cover entities for the MotionBlinds BLE integration."""

import logging

from collections.abc import Mapping
from typing import Any

from homeassistant.components.cover import (
    STATE_CLOSED,
    STATE_OPEN,
    STATE_CLOSING,
    STATE_OPENING,
    # ATTR_CURRENT_POSITION,
    # ATTR_CURRENT_TILT_POSITION,
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from .const import (
    DOMAIN,
    CONF_ADDRESS,
    CONF_MAC,
    CONF_BLIND_TYPE,
    SETTING_DISCONNECT_TIME,
    MotionBlindType,
)
from .motionblinds_ble.device import MotionDevice
from .motionblinds_ble.const import MotionConnectionType
from homeassistant.core import callback

from collections.abc import Callable

from bleak.backends.device import BLEDevice
from homeassistant.components.bluetooth import (
    async_ble_device_from_address,
    async_scanner_count,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up RollerBlind based on a config entry."""
    _LOGGER.info("Setting up cover with data %s", entry.data)

    blind = None
    if entry.data[CONF_BLIND_TYPE] == MotionBlindType.POSITION:
        blind = PositionBlind(entry.data)
    else:
        blind = PositionTiltBlind(entry.data)
    hass.data[DOMAIN][entry.entry_id] = blind
    async_add_entities([blind])


class PositionBlind(CoverEntity):
    """Representation of a blind with position capability."""

    _attr_supported_features: [CoverEntityFeature] = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    _device: MotionDevice = None
    _device_address: str = None
    _attr_connection: MotionConnectionType = MotionConnectionType.DISCONNECTED

    _battery_callback: Callable[[int], None] = None
    _disconnect_timer: Callable[[], None] = None

    def _async_refresh_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            self._disconnect_timer()  # Cancel current timer
            self._disconnect_timer = None

        _LOGGER.info("Refreshing disconnect timer")

        async def _disconnect(_):
            _LOGGER.info(f"Disconnecting after {SETTING_DISCONNECT_TIME}s")
            await self._device.disconnect()
            self._attr_connection = MotionConnectionType.DISCONNECTED
            # We don't know the cover position anymore
            self._attr_current_cover_position = None
            self.async_write_ha_state()

        self._disconnect_timer = async_call_later(
            self.hass, SETTING_DISCONNECT_TIME, _disconnect
        )

    def __init__(self, entry_data) -> None:
        """Initialize the RollerBlind."""
        super().__init__()
        self._device_address = entry_data[CONF_ADDRESS]
        self._attr_name = f"MotionBlind {entry_data[CONF_MAC]}"
        self._attr_unique_id = entry_data[CONF_ADDRESS]
        self._attr_device_class: CoverDeviceClass = CoverDeviceClass.BLIND
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_data[CONF_MAC])},
            manufacturer="MotionBlinds",
            name=self._attr_name,
        )
        self._attr_is_closed = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("RollerBlind has been added!")
        try:
            self._device = MotionDevice(self._device_address)
            # Register callbacks
            self._device.register_get_ble_device_callback(self.async_get_ble_device)
            self._device.register_position_callback(self.async_update_position)
            self._device.register_opening_callback(self.async_update_opening)
            self._device.register_connection_callback(self.async_set_connection)
            self._device.register_status_callback(self.async_update_status)
        except Exception as e:
            _LOGGER.warning(
                "Could not find the BLEDevice for address %s: %s",
                self._device_address,
                e,
            )
        await super().async_added_to_hass()

    def async_get_ble_device(self, _address: str) -> BLEDevice:
        ble_device = None
        try:
            scanner_count = async_scanner_count(self.hass)
            _LOGGER.info(
                "Getting BLEDevice for %s (%s scanners)",
                _address,
                str(scanner_count),
            )

            ble_device = async_ble_device_from_address(self.hass, _address)

        except Exception as e:
            _LOGGER.warning(
                "Could not find the BLEDevice for address %s: %s",
                self._device_address,
                e,
            )
        return ble_device

    async def async_open_cover(self, **kwargs: any) -> None:
        """Open the RollerBlind."""

        _LOGGER.info("Open %s", self._device_address)
        # if self._attr_is_closing or self._attr_is_opening:
        #     await self._device.stop()
        self.async_update_opening(True)
        if await self._device.open():
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)

    async def async_close_cover(self, **kwargs: any) -> None:
        """Close the RollerBlind."""

        _LOGGER.info("Close %s", self._device_address)
        # if self._attr_is_closing or self._attr_is_opening:
        #     await self._device.stop()
        self.async_update_opening(False)
        if await self._device.close():
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)

    async def async_stop_cover(self, **kwargs: any) -> None:
        """Stop the moving of this RollerBlind."""

        _LOGGER.info("Stop %s", self._device_address)
        if await self._device.stop():
            self._async_refresh_disconnect_timer()
        # Already updates HA state by callback
        # self.async_update_opening(None)

    async def async_set_cover_position(self, **kwargs: any) -> None:
        """Move the RollerBlind to a specific position."""
        new_position = 100 - kwargs.get(ATTR_POSITION)

        _LOGGER.info("Set position to %s %s", str(new_position), self._device_address)
        self.async_update_opening(
            None
            if self._attr_current_cover_position is None
            or new_position == 100 - self._attr_current_cover_position
            else new_position < 100 - self._attr_current_cover_position
        )
        if await self._device.percentage(new_position):
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)

    @callback
    def async_update_position(
        self, new_position_percentage: int, new_angle_percentage: int
    ) -> None:
        _LOGGER.info(
            "New position %s, %s",
            str(new_position_percentage),
            str(new_angle_percentage),
        )
        self._attr_current_cover_position = 100 - new_position_percentage
        self._attr_current_cover_tilt_position = 100 - new_angle_percentage
        self._attr_is_closed = self._attr_current_cover_position == 0
        self._attr_is_opening = False
        self._attr_is_closing = False
        self.async_write_ha_state()

    @callback
    def async_update_opening(self, is_opening: bool) -> None:
        """Only triggered by open/stop/close control."""
        self._attr_is_opening = False if is_opening is None else is_opening
        self._attr_is_closing = False if is_opening is None else not is_opening
        if is_opening is not None:
            self._attr_is_closed = None
        self.async_write_ha_state()

    @callback
    def async_set_connection(self, connection_type: MotionConnectionType) -> None:
        self._attr_connection = connection_type
        # Reset states if connection is lost
        if not connection_type == MotionConnectionType.CONNECTED:
            self._attr_is_opening = False
            self._attr_is_closing = False
            self._attr_is_closed = None
        self.async_write_ha_state()

    @callback
    def async_update_status(
        self, position_percentage: int, battery_percentage: int
    ) -> None:
        """Only triggered by open/stop/close control."""
        # Don't update otherwise cover UI will be moved
        # self._attr_current_cover_position = 100 - position_percentage
        if self._battery_callback is not None:
            self._battery_callback(battery_percentage)
        self.async_write_ha_state()

    def register_battery_callback(
        self, _battery_callback: Callable[[int], None]
    ) -> None:
        self._battery_callback = _battery_callback

    @property
    def extra_state_attributes(self) -> Mapping[Any, Any]:
        """Return the state attributes."""
        return {
            "connected": "Yes"
            if self._attr_connection == MotionConnectionType.CONNECTED
            else "Connecting..."
            if self._attr_connection == MotionConnectionType.CONNECTING
            else "No"
        }


class PositionTiltBlind(PositionBlind):
    """Representation of a blind with position & tilt capabilities."""

    _attr_supported_features: [CoverEntityFeature] = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
        | CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )

    async def async_open_cover_tilt(self, **kwargs: any) -> None:
        """Open the RollerBlind."""

        _LOGGER.info("Open tilt %s", self._device_address)
        # if self._attr_is_closing or self._attr_is_opening:
        #     await self._device.stop()
        self.async_update_opening(True)
        if await self._device.open_tilt():
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)

    async def async_close_cover_tilt(self, **kwargs: any) -> None:
        """Close the RollerBlind."""

        _LOGGER.info("Close tilt %s", self._device_address)
        # if self._attr_is_closing or self._attr_is_opening:
        #     await self._device.stop()
        self.async_update_opening(False)
        if await self._device.close_tilt():
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)

    async def async_set_cover_tilt_position(self, **kwargs: any) -> None:
        """Move the RollerBlind to a specific position."""
        new_tilt_position = 100 - kwargs.get(ATTR_TILT_POSITION)

        _LOGGER.info(
            "Set tilt position to %s %s", str(new_tilt_position), self._device_address
        )
        self.async_update_opening(
            None
            if self._attr_current_cover_tilt_position is None
            or new_tilt_position == 100 - self._attr_current_cover_tilt_position
            else new_tilt_position < 100 - self._attr_current_cover_tilt_position
        )
        if await self._device.percentage_tilt(new_tilt_position):
            self._async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_opening(None)
