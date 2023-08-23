"""Cover entities for the MotionBlinds BLE integration."""

import logging
import time
from collections.abc import Callable, Mapping
from functools import partial

from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
    async_ble_device_from_address,
    async_register_callback,
)
from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from .const import (
    ATTR_CONNECTION_TYPE,
    CONF_ADDRESS,
    CONF_BLIND_TYPE,
    CONF_MAC,
    DOMAIN,
    SETTING_DOUBLE_CLICK_TIME,
    MotionBlindType,
    MotionRunningType,
)
from .motionblinds_ble.const import MotionConnectionType
from .motionblinds_ble.device import MotionDevice

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up blind based on a config entry."""
    _LOGGER.info("Setting up cover with data %s", entry.data)

    blind = None
    if entry.data[CONF_BLIND_TYPE] == MotionBlindType.POSITION:
        blind = PositionBlind(entry)
    else:
        blind = PositionTiltBlind(entry)
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
    _attr_translation_key: str = CoverDeviceClass.BLIND.value
    _attr_connection_type: MotionConnectionType = MotionConnectionType.DISCONNECTED

    _last_stop_click_time: int = None
    _allow_position_feedback: bool = False

    _battery_callback: Callable[[int], None] = None

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the blind."""
        super().__init__()
        self._config_entry: ConfigEntry = entry
        self._device_address: str = entry.data[CONF_ADDRESS]
        self._attr_name: str = f"MotionBlind {entry.data[CONF_MAC]}"
        self._attr_unique_id: str = entry.data[CONF_ADDRESS]
        self._attr_device_class: CoverDeviceClass = CoverDeviceClass.BLIND
        self._attr_device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_MAC])},
            manufacturer="MotionBlinds",
            name=self._attr_name,
        )
        self._attr_is_closed: bool = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("Blind has been added!")
        try:
            ble_device = async_ble_device_from_address(self.hass, self._device_address)
            self._device = MotionDevice(self._device_address, ble_device)
            async_register_callback(
                self.hass,
                self.async_update_ble_device,
                BluetoothCallbackMatcher(address=self._device_address),
                BluetoothScanningMode.ACTIVE,
            )
            # Pass functions used to schedule tasks
            self._device.set_ha_create_task(
                partial(
                    self._config_entry.async_create_task,
                    hass=self.hass,
                    name=self._device_address,
                )
            )
            self._device.set_ha_call_later(partial(async_call_later, hass=self.hass))
            self.hass.data[DOMAIN][self.entity_id] = self
            # Register callbacks
            # self._device.register_get_ble_device_callback(self.async_get_ble_device)
            self._device.register_position_callback(self.async_update_position)
            self._device.register_running_callback(self.async_update_running)
            self._device.register_connection_callback(self.async_set_connection)
            self._device.register_status_callback(self.async_update_status)
        except Exception as e:
            _LOGGER.warning(
                "Could not find the BLEDevice for address %s: %s",
                self._device_address,
                e,
            )
        await super().async_added_to_hass()

    def async_refresh_disconnect_timer(
        self, timeout: int = None, force: bool = False
    ) -> None:
        """Refresh the time before the blind is disconnected."""
        self._device.refresh_disconnect_timer(timeout, force)

    async def async_connect(self) -> bool:
        """Connect to the blind."""
        connected = False
        if self._device:
            connected = await self._device.connect()
        return connected

    async def async_disconnect(self, **kwargs: any) -> None:
        """Disconnect the blind."""
        if self._device:
            await self._device.disconnect()

    async def async_status_query(self, **kwargs: any) -> None:
        """Send a status query to the blind."""
        if self._device:
            self._allow_position_feedback = True
            if not await self._device.status_query():
                self._allow_position_feedback = False

    async def async_open_cover(self, **kwargs: any) -> None:
        """Open the blind."""
        _LOGGER.info("Open %s", self._device_address)
        self.async_update_running(MotionRunningType.OPENING)
        if await self._device.open():
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    async def async_close_cover(self, **kwargs: any) -> None:
        """Close the blind."""
        _LOGGER.info("Close %s", self._device_address)
        self.async_update_running(MotionRunningType.CLOSING)
        if await self._device.close():
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    async def async_stop_cover(self, **kwargs: any) -> None:
        """Stop moving the blind."""
        current_stop_click_time = time.time_ns() // 1e6

        if (
            self._last_stop_click_time
            and current_stop_click_time - self._last_stop_click_time
            < SETTING_DOUBLE_CLICK_TIME
        ):
            # Favorite
            _LOGGER.info("Favorite %s", self._device_address)
            if await self._device.favorite():
                self.async_refresh_disconnect_timer()
            self._last_stop_click_time = None
        else:
            # Stop
            _LOGGER.info("Stop %s", self._device_address)
            if await self._device.stop():
                self.async_refresh_disconnect_timer()
            self._last_stop_click_time = current_stop_click_time

    async def async_favorite(self, **kwargs: any) -> None:
        """Move the blind to the favorite position."""
        _LOGGER.info("Favorite %s", self._device_address)
        if await self._device.favorite():
            self.async_refresh_disconnect_timer()

    async def async_set_cover_position(self, **kwargs: any) -> None:
        """Move the blind to a specific position."""
        new_position = 100 - kwargs.get(ATTR_POSITION)

        _LOGGER.info("Set position to %s %s", str(new_position), self._device_address)
        self.async_update_running(
            MotionRunningType.STILL
            if self._attr_current_cover_position is None
            or new_position == 100 - self._attr_current_cover_position
            else MotionRunningType.OPENING
            if new_position < 100 - self._attr_current_cover_position
            else MotionRunningType.CLOSING
        )
        if await self._device.percentage(new_position):
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    @callback
    def async_update_position(
        self, new_position_percentage: int, new_angle_percentage: int
    ) -> None:
        """Callback used to update the position of the blind."""
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
    def async_update_running(self, running_type: MotionRunningType) -> None:
        """Callback used to update whether the blind is running (opening/closing) or not."""
        self._attr_is_opening = (
            False
            if running_type == MotionRunningType.STILL
            else running_type == MotionRunningType.OPENING
        )
        self._attr_is_closing = (
            False
            if running_type == MotionRunningType.STILL
            else running_type != MotionRunningType.OPENING
        )
        if running_type != MotionRunningType.STILL:
            self._attr_is_closed = None
        self.async_write_ha_state()

    @callback
    def async_set_connection(self, connection_type: MotionConnectionType) -> None:
        """Callback used to update the connection status."""
        self._attr_connection_type = connection_type
        # Reset states if connection is lost, since we don't know the cover position anymore
        if not connection_type == MotionConnectionType.CONNECTED:
            self._attr_is_opening = False
            self._attr_is_closing = False
            self._attr_is_closed = None
            self._attr_current_cover_position = None
            self._attr_current_cover_tilt_position = None
        self.async_write_ha_state()

    @callback
    def async_update_status(
        self, position_percentage: int, tilt_percentage: int, battery_percentage: int
    ) -> None:
        """Callback used to update motor status, e.g. position, tilt and battery percentage."""
        # Only update position based on feedback when necessary, otherwise cover UI will jump around
        if self._allow_position_feedback:
            _LOGGER.info("Using position feedback once")
            self._attr_current_cover_position = 100 - position_percentage
            self._attr_current_cover_tilt_position = 100 - tilt_percentage
            self._allow_position_feedback = False

        if self._battery_callback is not None:
            self._battery_callback(battery_percentage)
        self.async_write_ha_state()

    @callback
    def async_update_ble_device(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        _LOGGER.warning(f"New BLE device for {service_info.address}!")
        self._device.set_ble_device(service_info.device)

    def async_register_battery_callback(
        self, _battery_callback: Callable[[int], None]
    ) -> None:
        """Register the callback used to update the battery percentage."""
        self._battery_callback = _battery_callback

    @property
    def extra_state_attributes(self) -> Mapping[str, str]:
        """Return the state attributes."""
        return {ATTR_CONNECTION_TYPE: self._attr_connection_type}


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
        """Tilt the blind open."""
        _LOGGER.info("Open tilt %s", self._device_address)
        self.async_update_running(MotionRunningType.OPENING)
        if await self._device.open_tilt():
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    async def async_close_cover_tilt(self, **kwargs: any) -> None:
        """Tilt the blind closed."""
        _LOGGER.info("Close tilt %s", self._device_address)
        self.async_update_running(MotionRunningType.CLOSING)
        if await self._device.close_tilt():
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    async def async_stop_cover_tilt(self, **kwargs: any) -> None:
        """Stop tilting the blind."""
        self.async_stop_cover(**kwargs)

    async def async_set_cover_tilt_position(self, **kwargs: any) -> None:
        """Tilt the blind to a specific position."""
        new_tilt_position = 100 - kwargs.get(ATTR_TILT_POSITION)

        _LOGGER.info(
            "Set tilt position to %s %s", str(new_tilt_position), self._device_address
        )
        self.async_update_running(
            MotionRunningType.STILL
            if self._attr_current_cover_tilt_position is None
            or new_tilt_position == 100 - self._attr_current_cover_tilt_position
            else MotionRunningType.OPENING
            if new_tilt_position < 100 - self._attr_current_cover_tilt_position
            else MotionRunningType.CLOSING
        )
        if await self._device.percentage_tilt(new_tilt_position):
            self.async_refresh_disconnect_timer()
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)
