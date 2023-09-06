"""Cover entities for the MotionBlinds BLE integration."""

import logging
import time
from asyncio import Event
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
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
    CoverEntityDescription,
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
    CONF_MAC_CODE,
    DOMAIN,
    ENTITY_NAME,
    EXCEPTION_NOT_CALIBRATED,
    MANUFACTURER,
    SETTING_DOUBLE_CLICK_TIME,
    MotionBlindType,
    MotionCalibrationType,
    MotionRunningType,
)
from .motionblinds_ble.const import (
    SETTING_CALIBRATION_DISCONNECT_TIME,
    MotionConnectionType,
    MotionSpeedLevel,
)
from .motionblinds_ble.device import MotionDevice, MotionPositionInfo

_LOGGER = logging.getLogger(__name__)


# Decorator used to perform checks before executing a command
DECORATOR_METHOD_BEFORE_RUN = "before_run_command"
DECORATOR_METHOD_AFTER_RUN = "after_run_command"
DECORATOR_METHOD_BEFORE_NO_RUN = "before_no_run_command"
DECORATOR_METHOD_AFTER_NO_RUN = "after_no_run_command"


def generic_command_decorator(
    before_method_name: str, after_method_name: str, func: Callable
) -> Callable:
    async def wrapper(self, *args, **kwargs):
        # Check if the object has an attribute named DECORATOR_FUNCTION
        if hasattr(self, before_method_name):
            # Get the attribute and call it
            before_func = getattr(self, before_method_name)
            if not await before_func(*args, **kwargs):
                return  # Don't execute function if before_func returns False
        res = await func(self, *args, **kwargs)
        if hasattr(self, after_method_name):
            # Get the attribute and call it
            after_func = getattr(self, after_method_name)
            await after_func(*args, **kwargs)
        return res

    return wrapper


# Decorator used for commands that move the motor position
def run_command(func: Callable) -> Callable:
    return generic_command_decorator(
        DECORATOR_METHOD_BEFORE_RUN, DECORATOR_METHOD_AFTER_RUN, func
    )


# Decorator used for commands that do not move the motor position
def no_run_command(func: Callable) -> Callable:
    return generic_command_decorator(
        DECORATOR_METHOD_BEFORE_NO_RUN, DECORATOR_METHOD_AFTER_NO_RUN, func
    )


@dataclass
class MotionCoverEntityDescription(CoverEntityDescription):
    key: str = field(default=CoverDeviceClass.BLIND.value, init=False)
    translation_key: str = field(default=CoverDeviceClass.BLIND.value, init=False)
    device_class: CoverDeviceClass = field(default=CoverDeviceClass.SHADE, init=True)


COVER_TYPES: dict[str, MotionCoverEntityDescription] = {
    MotionBlindType.ROLLER.value: MotionCoverEntityDescription(),
    MotionBlindType.HONEYCOMB.value: MotionCoverEntityDescription(),
    MotionBlindType.ROMAN.value: MotionCoverEntityDescription(),
    MotionBlindType.VENETIAN.value: MotionCoverEntityDescription(
        device_class=CoverDeviceClass.BLIND
    ),
    MotionBlindType.VENETIAN_TILT_ONLY.value: MotionCoverEntityDescription(
        device_class=CoverDeviceClass.BLIND
    ),
    MotionBlindType.DOUBLE_ROLLER.value: MotionCoverEntityDescription(),
    MotionBlindType.CURTAIN.value: MotionCoverEntityDescription(
        device_class=CoverDeviceClass.CURTAIN
    ),
    MotionBlindType.VERTICAL.value: MotionCoverEntityDescription(
        device_class=CoverDeviceClass.CURTAIN
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up blind based on a config entry."""
    _LOGGER.info("Setting up cover with data %s", entry.data)

    blind_type = BLIND_TO_ENTITY_TYPE[entry.data[CONF_BLIND_TYPE]]
    blind = blind_type(entry)
    hass.data[DOMAIN][entry.entry_id] = blind
    async_add_entities([blind])


class GenericBlind(CoverEntity):
    """Representation of a blind."""

    device_address: str = None
    device_rssi: int = None
    _device: MotionDevice = None
    _attr_connection_type: MotionConnectionType = MotionConnectionType.DISCONNECTED
    _running_type: MotionRunningType = None

    _last_stop_click_time: int = None
    _use_status_position_update_ui: bool = False

    _battery_callback: Callable[[int], None] = None
    _speed_callback: Callable[[MotionSpeedLevel], None] = None
    _connection_callback: Callable[[MotionConnectionType], None] = None
    _signal_strength_callback: Callable[[int], None] = None

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the blind."""
        super().__init__()
        self.entity_description = COVER_TYPES[entry.data[CONF_BLIND_TYPE]]
        self.config_entry: ConfigEntry = entry
        self.device_address: str = entry.data[CONF_ADDRESS]
        self._attr_name: str = ENTITY_NAME.format(mac_code=entry.data[CONF_MAC_CODE])
        self._attr_unique_id: str = entry.data[CONF_ADDRESS]
        self._attr_device_info: DeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_MAC_CODE])},
            manufacturer=MANUFACTURER,
            name=self._attr_name,
        )
        self._attr_is_closed: bool = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        ble_device = async_ble_device_from_address(self.hass, self.device_address)
        self._device = MotionDevice(self.device_address, ble_device)
        async_register_callback(
            self.hass,
            self.async_update_ble_device,
            BluetoothCallbackMatcher(address=self.device_address),
            BluetoothScanningMode.ACTIVE,
        )
        # Pass functions used to schedule tasks
        self._device.set_ha_create_task(
            partial(
                self.config_entry.async_create_task,
                hass=self.hass,
                name=self.device_address,
            )
        )
        self._device.set_ha_call_later(partial(async_call_later, hass=self.hass))
        self.hass.data[DOMAIN][self.entity_id] = self
        # Register callbacks
        self._device.register_running_callback(self.async_update_running)
        self._device.register_position_callback(self.async_update_position)
        self._device.register_connection_callback(self.async_update_connection)
        self._device.register_status_callback(self.async_update_status)
        await super().async_added_to_hass()

    def async_refresh_disconnect_timer(
        self, timeout: int = None, force: bool = False
    ) -> None:
        """Refresh the time before the blind is disconnected."""
        self._device.refresh_disconnect_timer(timeout, force)

    async def async_connect(self, notification_delay: bool = False) -> bool:
        """Connect to the blind."""
        self._use_status_position_update_ui = True
        return await self._device.connect(notification_delay)

    async def async_disconnect(self, **kwargs: any) -> None:
        """Disconnect the blind."""
        self._use_status_position_update_ui = False
        await self._device.disconnect()

    @no_run_command
    async def async_status_query(self, **kwargs: any) -> None:
        """Send a status query to the blind."""
        self._use_status_position_update_ui = True
        if await self._device.status_query():
            self._use_status_position_update_ui = False

    @run_command
    async def async_stop_cover(self, **kwargs: any) -> None:
        """Stop moving the blind."""
        current_stop_click_time = time.time_ns() // 1e6

        if (
            self._last_stop_click_time
            and current_stop_click_time - self._last_stop_click_time
            < SETTING_DOUBLE_CLICK_TIME
        ):
            # Favorite
            _LOGGER.info("Favorite %s", self.device_address)
            await self._device.favorite()
            self._last_stop_click_time = None
        else:
            # Stop
            _LOGGER.info("Stop %s", self.device_address)
            await self._device.stop()
            self._last_stop_click_time = current_stop_click_time

    @run_command
    async def async_favorite(self, **kwargs: any) -> None:
        """Move the blind to the favorite position."""
        self.async_update_running(MotionRunningType.UNKNOWN)
        _LOGGER.info("Favorite %s", self.device_address)
        await self._device.favorite()

    @no_run_command
    async def async_speed(self, speed_level: MotionSpeedLevel, **kwargs: any) -> None:
        """Change the speed level of the device."""
        _LOGGER.info("Speed %s", self.device_address)
        await self._device.speed(speed_level)

    def async_update_running(self, running_type: MotionRunningType) -> None:
        """Used to update whether the blind is running (opening/closing) or not."""
        self._running_type = running_type
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
    def async_update_position(
        self,
        new_position_percentage: int,
        new_angle_percentage: int,
        end_position_info: MotionPositionInfo,
    ) -> None:
        """Callback used to update the position of the blind."""
        _LOGGER.info(
            "New position %s, %s",
            str(new_position_percentage),
            str(new_angle_percentage),
        )
        if isinstance(self, PositionCalibrationBlind):
            self.async_update_calibration(end_position_info)
        self._attr_current_cover_position = 100 - new_position_percentage
        self._attr_current_cover_tilt_position = 100 - new_angle_percentage
        self._attr_is_closed = self._attr_current_cover_position == 0
        self._attr_is_opening = False
        self._attr_is_closing = False
        self.async_write_ha_state()

    @callback
    def async_update_connection(self, connection_type: MotionConnectionType) -> None:
        """Callback used to update the connection status."""
        self._attr_connection_type = connection_type
        if self._connection_callback is not None:
            self._connection_callback(connection_type)
        # Reset states if connection is lost, since we don't know the cover position anymore
        if connection_type is MotionConnectionType.DISCONNECTED:
            self._use_status_position_update_ui = False
            self._attr_is_opening = False
            self._attr_is_closing = False
            self._attr_is_closed = None
            self._attr_current_cover_position = None
            self._attr_current_cover_tilt_position = None
            if self._speed_callback is not None:
                self._speed_callback(None)
            if self._battery_callback is not None:
                self._battery_callback(None)
        self.async_write_ha_state()

    @callback
    def async_update_status(
        self,
        position_percentage: int,
        tilt_percentage: int,
        battery_percentage: int,
        speed_level: MotionSpeedLevel,
        end_position_info: MotionPositionInfo,
    ) -> None:
        """Callback used to update motor status, e.g. position, tilt and battery percentage."""
        # Only update position based on feedback when necessary, otherwise cover UI will jump around
        if self._use_status_position_update_ui:
            _LOGGER.info("Using position feedback once")
            self._attr_current_cover_position = 100 - position_percentage
            self._attr_current_cover_tilt_position = 100 - tilt_percentage
            self._use_status_position_update_ui = False

        if self._battery_callback is not None:
            self._battery_callback(battery_percentage)
        if self._speed_callback is not None:
            self._speed_callback(speed_level)
        if isinstance(self, PositionCalibrationBlind):
            self.async_update_calibration(end_position_info)
        self.async_write_ha_state()

    @callback
    def async_update_ble_device(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        _LOGGER.warning(f"New BLE device for {service_info.address}!")
        self._device.set_ble_device(service_info.device)
        self.device_rssi = service_info.advertisement.rssi
        if callable(self._signal_strength_callback):
            self._signal_strength_callback(self.device_rssi)

    def async_register_battery_callback(
        self, _battery_callback: Callable[[int], None]
    ) -> None:
        """Register the callback used to update the battery percentage."""
        self._battery_callback = _battery_callback

    def async_register_speed_callback(
        self, _speed_callback: Callable[[MotionSpeedLevel], None]
    ) -> None:
        """Register the callback used to update the speed level."""
        self._speed_callback = _speed_callback

    def async_register_connection_callback(
        self, _connection_callback: Callable[[MotionConnectionType], None]
    ) -> None:
        """Register the callback used to update the connection."""
        self._connection_callback = _connection_callback

    def async_register_signal_strength_callback(
        self, _signal_strength_callback: Callable[[int], None]
    ) -> None:
        """Register the callback used to update the signal strength."""
        self._signal_strength_callback = _signal_strength_callback

    @property
    def extra_state_attributes(self) -> Mapping[str, str]:
        """Return the state attributes."""
        return {ATTR_CONNECTION_TYPE: self._attr_connection_type}

    async def before_command(self, *args, **kwargs) -> None:
        if self._attr_connection_type is MotionConnectionType.CONNECTED:
            self.async_refresh_disconnect_timer()

    # Decorator
    async def before_run_command(self, *args, **kwargs) -> bool:
        await self.before_command(*args, **kwargs)
        if self._attr_connection_type is not MotionConnectionType.CONNECTED:
            self._use_status_position_update_ui = False
        return True

    # Decorator
    async def before_no_run_command(self, *args, **kwargs) -> bool:
        await self.before_command(*args, **kwargs)
        if self._attr_connection_type is not MotionConnectionType.CONNECTED:
            self._use_status_position_update_ui = True
        return True


class PositionBlind(GenericBlind):
    """Representation of a blind with position capability."""

    _attr_supported_features: [CoverEntityFeature] = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("PositionBlind has been added!")
        await super().async_added_to_hass()

    @run_command
    async def async_open_cover(self, **kwargs: any) -> None:
        """Open the blind."""
        _LOGGER.info("Open %s", self.device_address)
        self.async_update_running(MotionRunningType.OPENING)
        if await self._device.open():
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    @run_command
    async def async_close_cover(self, **kwargs: any) -> None:
        """Close the blind."""
        _LOGGER.info("Close %s", self.device_address)
        self.async_update_running(MotionRunningType.CLOSING)
        if await self._device.close():
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    @run_command
    async def async_set_cover_position(self, **kwargs: any) -> None:
        """Move the blind to a specific position."""
        new_position = 100 - kwargs.get(ATTR_POSITION)

        _LOGGER.info("Set position to %s %s", str(new_position), self.device_address)
        self.async_update_running(
            MotionRunningType.STILL
            if self._attr_current_cover_position is None
            or new_position == 100 - self._attr_current_cover_position
            else MotionRunningType.OPENING
            if new_position < 100 - self._attr_current_cover_position
            else MotionRunningType.CLOSING
        )
        if await self._device.percentage(new_position):
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)


class TiltBlind(GenericBlind):
    """Representation of a blind with tilt capability."""

    _attr_supported_features: [CoverEntityFeature] = (
        CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
        | CoverEntityFeature.STOP_TILT
        | CoverEntityFeature.SET_TILT_POSITION
    )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("TiltBlind has been added!")
        await super().async_added_to_hass()

    @run_command
    async def async_open_cover_tilt(self, **kwargs: any) -> None:
        """Tilt the blind open."""
        _LOGGER.info("Open tilt %s", self.device_address)
        self.async_update_running(MotionRunningType.OPENING)
        if await self._device.open_tilt():
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    @run_command
    async def async_close_cover_tilt(self, **kwargs: any) -> None:
        """Tilt the blind closed."""
        _LOGGER.info("Close tilt %s", self.device_address)
        self.async_update_running(MotionRunningType.CLOSING)
        if await self._device.close_tilt():
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)

    @run_command
    async def async_stop_cover_tilt(self, **kwargs: any) -> None:
        """Stop tilting the blind."""
        await self.async_stop_cover(**kwargs)

    @run_command
    async def async_set_cover_tilt_position(self, **kwargs: any) -> None:
        """Tilt the blind to a specific position."""
        new_tilt_position = 100 - kwargs.get(ATTR_TILT_POSITION)

        _LOGGER.info(
            "Set tilt position to %s %s", str(new_tilt_position), self.device_address
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
            self.async_write_ha_state()
        else:
            self.async_update_running(MotionRunningType.STILL)


class PositionTiltBlind(PositionBlind, TiltBlind):
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

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("PositionTiltBlind has been added!")
        await super().async_added_to_hass()


class PositionCalibrationBlind(PositionBlind):
    """Representation of a blind with position & calibration capabilities."""

    _calibration_type: MotionCalibrationType = None
    _calibration_callback: Callable[[MotionCalibrationType], None] = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("PositionCalibrationBlind has been added!")
        await super().async_added_to_hass()

    def async_update_running(self, running_type: MotionRunningType) -> None:
        if (
            self._calibration_type is MotionCalibrationType.UNCALIBRATED
            and running_type is not MotionRunningType.STILL
        ):
            # Curtain motor will calibrate if not calibrated and moved to some position
            _LOGGER.info("Starting calibration")
            self._calibration_type = MotionCalibrationType.CALIBRATING
            if callable(self._calibration_callback):
                self._calibration_callback(MotionCalibrationType.CALIBRATING)
            self.async_refresh_disconnect_timer(SETTING_CALIBRATION_DISCONNECT_TIME)
        super().async_update_running(running_type)

    @callback
    def async_update_calibration(self, end_position_info: MotionPositionInfo) -> None:
        """Update the calibration status of the motor."""
        _LOGGER.info("Calibrated: %s", end_position_info.UP)
        _LOGGER.warning("Self: %s", self._running_type)
        new_calibration_type = (
            MotionCalibrationType.CALIBRATED  # Calibrated if end positions are set
            if end_position_info.UP
            else MotionCalibrationType.CALIBRATING  # Calibrating if no end positions, and motor is running
            if self._running_type is not None
            and self._running_type is not MotionRunningType.STILL
            else MotionCalibrationType.UNCALIBRATED
        )
        _LOGGER.warning(new_calibration_type)

        if (
            self._calibration_type is MotionCalibrationType.CALIBRATING
            and new_calibration_type is not MotionCalibrationType.CALIBRATING
        ):
            # Refresh disconnect timer to default value if finished calibrating
            self.async_refresh_disconnect_timer(force=True)
        self._calibration_type = new_calibration_type
        if callable(self._calibration_callback):
            self._calibration_callback(new_calibration_type)

    def async_register_calibration_callback(
        self, _calibration_callback: Callable[[MotionCalibrationType], None]
    ) -> None:
        """Register the callback used to update the calibration."""
        self._calibration_callback = _calibration_callback

    @callback
    def async_update_connection(self, connection_type: MotionConnectionType) -> None:
        """Callback used to update the connection status."""
        if (
            self._calibration_callback is not None
            and connection_type is MotionConnectionType.DISCONNECTED
        ):
            # Set calibration to None if disconnected
            self._calibration_callback(None)
        super().async_update_connection(connection_type)

    async def async_connect(self) -> bool:
        """Connect to the blind, add a delay before sending the status query."""
        return await super().async_connect(notification_delay=True)


class PositionTiltCalibrationBlind(PositionCalibrationBlind, PositionTiltBlind):
    """Representation of a blind with position, tilt and calibration capabilities."""

    _calibration_event: Event = Event()

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        _LOGGER.info("PositionTiltCalibrationBlind has been added!")
        await super().async_added_to_hass()

    # Decorator
    async def before_run_command(self, *args, **kwargs):
        """Run before every command that moves a blind, return whether or not to proceed with the command."""
        await super().before_run_command(args, **kwargs)
        if not self._device.is_connected():
            self._calibration_event.clear()
            if not await self.async_connect():
                return False
            # Wait for calibration attribute to get a value
            await self._calibration_event.wait()
        # If motor is not calibrated, raise an exception
        if self._calibration_type is not MotionCalibrationType.CALIBRATED:
            raise NotCalibratedException(
                EXCEPTION_NOT_CALIBRATED.format(device_name=self._attr_name)
            )
        return True

    @callback
    def async_update_calibration(self, end_position_info: MotionPositionInfo) -> None:
        """Update the calibration status of the motor."""
        super().async_update_calibration(end_position_info)
        self._calibration_event.set()


class NotCalibratedException(Exception):
    """Exception to indicate the blinds are not calibrated."""


BLIND_TO_ENTITY_TYPE: dict[str, GenericBlind] = {
    MotionBlindType.ROLLER.value: PositionBlind,
    MotionBlindType.HONEYCOMB.value: PositionBlind,
    MotionBlindType.ROMAN.value: PositionBlind,
    MotionBlindType.VENETIAN.value: PositionTiltBlind,
    MotionBlindType.VENETIAN_TILT_ONLY.value: TiltBlind,
    MotionBlindType.DOUBLE_ROLLER.value: PositionTiltBlind,
    MotionBlindType.CURTAIN.value: PositionCalibrationBlind,
    MotionBlindType.VERTICAL.value: PositionTiltCalibrationBlind,
}
