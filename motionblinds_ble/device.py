"""Device for MotionBlinds BLE."""
import logging
from asyncio import CancelledError, Task, TimerHandle, create_task, get_event_loop
from collections.abc import Callable, Coroutine
from datetime import datetime
from time import time_ns, time

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection, BleakOutOfConnectionSlotsError

from dataclasses import dataclass

from .const import (
    SETTING_DISCONNECT_TIME,
    SETTING_MAX_COMMAND_ATTEMPTS,
    SETTING_MAX_CONNECT_ATTEMPTS,
    MotionCharacteristic,
    MotionCommandType,
    MotionConnectionType,
    MotionNotificationType,
    MotionRunningType,
    MotionSpeedLevel,
)
from .crypt import MotionCrypt

_LOGGER = logging.getLogger(__name__)


@dataclass
class MotionPositionInfo:
    def __init__(self, end_positions_byte: int) -> None:
        self.UP = bool(end_positions_byte & 0x08)
        self.DOWN = bool(end_positions_byte & 0x04)

    UP: bool
    DOWN: bool


class MotionDevice:
    _device_address: str = None
    _ble_device: BLEDevice = None
    _current_bleak_client: BleakClient = None
    _connection_type: MotionConnectionType = MotionConnectionType.DISCONNECTED

    _disconnect_time: int = None
    _disconnect_timer: TimerHandle | Callable = None

    # Callbacks that are used to interface with HA
    _ha_create_task: Callable[[Coroutine], Task] = None
    _ha_call_later: Callable[[int, Coroutine], Callable] = None

    # Regular callbacks
    _position_callback: Callable[[int, int], None] = None
    _running_callback: Callable[[bool], None] = None
    _connection_callback: Callable[[MotionConnectionType], None] = None
    _status_callback: Callable[[int, int, int, MotionSpeedLevel], None] = None

    # Used to ensure the first caller connects, but the last caller's command goes through when connecting
    _connection_task: Task = None
    _last_connection_caller_time: int = None

    def __init__(self, _address: str, _ble_device: BLEDevice = None) -> None:
        self._device_address = _address
        if _ble_device:
            self._ble_device = _ble_device
        else:
            _LOGGER.warning(
                "Could not find BLEDevice, creating new BLEDevice from address"
            )
            self._ble_device = BLEDevice(
                self._device_address, self._device_address, {}, rssi=0
            )

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Set the BLEDevice for this device."""
        self._ble_device = ble_device

    def set_ha_create_task(self, ha_create_task: Callable[[Coroutine], Task]) -> None:
        """Set the create_task function to use."""
        self._ha_create_task = ha_create_task

    def set_ha_call_later(
        self, ha_call_later: Callable[[int, Coroutine], Callable]
    ) -> None:
        """Set the call_later function to use."""
        self._ha_call_later = ha_call_later

    def set_connection(self, connection_type: MotionConnectionType) -> None:
        """Set the connection to a particular connection type."""
        if self._connection_callback:
            self._connection_callback(connection_type)
        self._connection_type = connection_type

    def _cancel_disconnect_timer(self) -> None:
        if self._disconnect_timer:
            # Cancel current timer
            if callable(self._disconnect_timer):
                _LOGGER.warning("Cancel HA Later")
                self._disconnect_timer()
            else:
                _LOGGER.warning("Cancel later")
                self._disconnect_timer.cancel()

    def refresh_disconnect_timer(
        self, timeout: int = None, force: bool = False
    ) -> None:
        """Refresh the time before the device is disconnected."""
        timeout = SETTING_DISCONNECT_TIME if timeout is None else timeout
        # Don't refresh if the current disconnect timer has a larger timeout
        new_disconnect_time = time_ns() // 1e6 + timeout * 1e3
        if (
            not force
            and self._disconnect_timer is not None
            and self._disconnect_time > new_disconnect_time
        ):
            return

        self._cancel_disconnect_timer()

        _LOGGER.info(f"Refreshing disconnect timer to {timeout}s")

        async def _disconnect_later(t: datetime = None):
            _LOGGER.info(f"Disconnecting after {timeout}s")
            await self.disconnect()
            self.set_connection(MotionConnectionType.DISCONNECTED)

        self._disconnect_time = new_disconnect_time
        if self._ha_call_later:
            _LOGGER.warning("HA Later")
            self._disconnect_timer = self._ha_call_later(
                delay=timeout, action=_disconnect_later
            )
        else:
            _LOGGER.warning("Later")
            self._disconnect_timer = get_event_loop().call_later(
                timeout, create_task, _disconnect_later()
            )

    def _notification_callback(
        self, char: BleakGATTCharacteristic, byte_array: bytearray
    ) -> None:
        """Callback called by Bleak when a notification is received."""
        decrypted_message: str = MotionCrypt.decrypt(byte_array.hex())
        decrypted_message_bytes: bytes = byte_array.fromhex(decrypted_message)
        _LOGGER.info("Received message: %s", decrypted_message)

        if (
            decrypted_message.startswith(MotionNotificationType.PERCENT.value)
            and self._position_callback is not None
        ):
            _LOGGER.info("Position notification")
            end_position_info: MotionPositionInfo = MotionPositionInfo(
                decrypted_message_bytes[4]
            )
            position_percentage: int = decrypted_message_bytes[6]
            angle: int = decrypted_message_bytes[7]
            angle_percentage = round(100 * angle / 180)
            self._position_callback(
                position_percentage, angle_percentage, end_position_info
            )
        elif (
            decrypted_message.startswith(MotionNotificationType.RUNNING.value)
            and self._running_callback is not None
        ):
            _LOGGER.info("Running notification")
            running_type: bool = decrypted_message_bytes[5] == MotionRunningType.OPENING
            # Test to see if works
            # self._running_callback(running_type)
        elif (
            decrypted_message.startswith(MotionNotificationType.STATUS.value)
            and self._status_callback is not None
        ):
            _LOGGER.info("Updating status")
            position_percentage: int = decrypted_message_bytes[6]
            angle: int = decrypted_message_bytes[7]
            angle_percentage = round(100 * angle / 180)
            battery_percentage: int = decrypted_message_bytes[17]
            end_position_info = MotionPositionInfo(decrypted_message_bytes[4])
            speed_level: MotionSpeedLevel = MotionSpeedLevel(
                decrypted_message_bytes[12]
            )
            self._status_callback(
                position_percentage,
                angle_percentage,
                battery_percentage,
                speed_level,
                end_position_info,
            )

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback called by Bleak when a client disconnects."""
        _LOGGER.info("Device %s disconnected!", self._device_address)
        self.set_connection(MotionConnectionType.DISCONNECTED)

    async def connect(self) -> bool:
        """Connect to the device if not connected, return whether or not the motor is ready for a command."""
        if not self.is_connected():
            # Connect if not connected yet and not busy connecting
            return await self._connect_if_not_connecting()
        else:
            self.refresh_disconnect_timer()
        return True

    async def disconnect(self) -> None:
        """Called by Home Assistant after X time."""
        if self._connection_task is not None:
            _LOGGER.info("Cancelling connecting %s", self._device_address)
            self._connection_task.cancel()  # Indicate the connection has failed.
            self._cancel_disconnect_timer()
            self._connection_task = None
        if self._current_bleak_client is not None:
            _LOGGER.info("Disconnecting %s", self._device_address)
            await self._current_bleak_client.disconnect()
            self.set_connection(MotionConnectionType.DISCONNECTED)
            self._current_bleak_client = None

    async def _connect_if_not_connecting(self) -> bool:
        """Connect if no connection is currently attempted, return True if the motor is ready for a command and only to the last caller."""
        # Don't try to connect if we are already connecting
        this_connection_caller_time = time_ns()
        self._last_connection_caller_time = this_connection_caller_time
        if self._connection_task is None:
            _LOGGER.info("First caller connecting")
            if self._ha_create_task:
                _LOGGER.warning("HA connecting")
                self._connection_task = self._ha_create_task(target=self._connect())
            else:
                _LOGGER.warning("Normal connecting")
                self._connection_task = get_event_loop().create_task(self._connect())
        else:
            _LOGGER.info("Already connecting, waiting for connection")
        try:
            if not await self._connection_task:
                return False
        except BleakOutOfConnectionSlotsError as e:
            # Return False if connecting has been cancelled
            _LOGGER.info("Cancelled connecting due to lack of connection slots")
            self.set_connection(MotionConnectionType.DISCONNECTED)
            raise e
        except CancelledError:
            # Return False if connecting has been cancelled
            _LOGGER.info("Cancelled connecting")
            self.set_connection(MotionConnectionType.DISCONNECTED)
            return False

        self._connection_task = None
        is_last_caller = (
            self._last_connection_caller_time == this_connection_caller_time
        )
        if is_last_caller:
            self.refresh_disconnect_timer()
        return is_last_caller  # Return whether or not this function was the last caller

    async def _connect(self) -> bool:
        """Connect to the device, return whether or not the motor is ready for a command."""
        if self._connection_type is MotionConnectionType.CONNECTING:
            return False

        self.set_connection(MotionConnectionType.CONNECTING)
        _LOGGER.info("Connecting to %s", self._device_address)

        _LOGGER.info("Establishing connection")
        bleak_client = await establish_connection(
            BleakClient,
            self._ble_device,
            self._device_address,
            max_attempts=SETTING_MAX_CONNECT_ATTEMPTS,
        )

        _LOGGER.info("Connected to %s", self._device_address)
        self._current_bleak_client = bleak_client
        self.set_connection(MotionConnectionType.CONNECTED)

        await bleak_client.start_notify(
            str(MotionCharacteristic.NOTIFICATION.value),
            self._notification_callback,
        )

        # Used to initialize
        await self.set_key()
        # Set the point (used after calibrating Curtain)
        # await self.point_set_query()
        await self.status_query()

        bleak_client.set_disconnected_callback(self._disconnect_callback)

        return True

    def is_connected(self) -> bool:
        """Return whether or not the device is connected."""
        return (
            self._current_bleak_client is not None
            and self._current_bleak_client.is_connected
        )

    async def _send_command(
        self, command_prefix: str, connection_command: bool = False
    ) -> bool:
        """Write a message to the command characteristic, return whether or not the command was successfully executed."""
        if not await self.connect():
            return False
        # Command must be generated just before sending due get_time timing
        command = MotionCrypt.encrypt(command_prefix + MotionCrypt.get_time())
        _LOGGER.warning("Sending message: %s", MotionCrypt.decrypt(command))
        # response=False to solve Unlikely Error: [org.bluez.Error.Failed] Operation failed with ATT error: 0x0e (Unlikely Error)
        # response=True: 0.20s, response=False: 0.0005s
        number_of_tries = 0
        while number_of_tries < SETTING_MAX_COMMAND_ATTEMPTS:
            try:
                a = time()
                await self._current_bleak_client.write_gatt_char(
                    str(MotionCharacteristic.COMMAND.value),
                    bytes.fromhex(command),
                    response=True,
                )
                b = time()
                _LOGGER.warning("Received response in %ss", str(b - a))
                return True
            except BleakError as e:
                if number_of_tries == SETTING_MAX_COMMAND_ATTEMPTS:
                    raise e
                else:
                    _LOGGER.warning(
                        "Error sending message (try %i): %s", number_of_tries, e
                    )
                    number_of_tries += 1

    async def user_query(self) -> bool:
        """Send user_query command."""
        command_prefix = str(MotionCommandType.USER_QUERY.value)
        return await self._send_command(command_prefix, connection_command=True)

    async def set_key(self) -> bool:
        """Send set_key command."""
        command_prefix = str(MotionCommandType.SET_KEY.value)
        return await self._send_command(command_prefix, connection_command=True)

    async def status_query(self) -> bool:
        """Send status_query command."""
        command_prefix = str(MotionCommandType.STATUS_QUERY.value)
        return await self._send_command(command_prefix, connection_command=True)

    async def point_set_query(self) -> bool:
        """Send point_set_query command."""
        command_prefix = str(MotionCommandType.POINT_SET_QUERY.value)
        return await self._send_command(command_prefix, connection_command=True)

    async def percentage(self, percentage: int) -> bool:
        """Moves the device to a specific percentage."""
        assert not percentage < 0 and not percentage > 100
        command_prefix = (
            str(MotionCommandType.PERCENT.value) + hex(percentage)[2:].zfill(2) + "00"
        )
        return await self._send_command(command_prefix)

    async def open(self) -> bool:
        """Open the device."""
        command_prefix = str(MotionCommandType.OPEN.value)
        return await self._send_command(command_prefix)

    async def close(self) -> bool:
        """Close the device."""
        command_prefix = str(MotionCommandType.CLOSE.value)
        return await self._send_command(command_prefix)

    async def stop(self) -> bool:
        """Stop moving the device."""
        command_prefix = str(MotionCommandType.STOP.value)
        return await self._send_command(command_prefix)

    async def favorite(self) -> bool:
        """Move the device to the favorite position."""
        command_prefix = str(MotionCommandType.FAVORITE.value)
        return await self._send_command(command_prefix)

    async def speed(self, speed_level: MotionSpeedLevel) -> bool:
        """Change the speed level of the device."""
        command_prefix = str(MotionCommandType.SPEED.value) + hex(
            int(speed_level.value)
        )[2:].zfill(2)
        return await self._send_command(command_prefix)

    async def percentage_tilt(self, percentage: int) -> bool:
        """Tilt the device to a specific position."""
        angle = round(180 * percentage / 100)
        command_prefix = (
            str(MotionCommandType.ANGLE.value) + "00" + hex(angle)[2:].zfill(2)
        )
        return await self._send_command(command_prefix)

    async def open_tilt(self) -> bool:
        """Tilt the device open."""
        # Step or fully tilt?
        # command_prefix = str(MotionCommandType.OPEN_TILT.value)
        command_prefix = str(MotionCommandType.ANGLE.value) + "00" + hex(0)[2:].zfill(2)
        return await self._send_command(command_prefix)

    async def close_tilt(self) -> bool:
        """Tilt the device closed."""
        # Step or fully tilt?
        # command_prefix = str(MotionCommandType.CLOSE_TILT.value)
        command_prefix = (
            str(MotionCommandType.ANGLE.value) + "00" + hex(180)[2:].zfill(2)
        )
        return await self._send_command(command_prefix)

    def register_position_callback(self, callback: Callable[[int, int], None]) -> None:
        """Register the callback used to update the position."""
        self._position_callback = callback

    def register_running_callback(self, callback: Callable[[bool], None]) -> None:
        """Register the callback used to update the running type."""
        self._running_callback = callback

    def register_connection_callback(
        self, callback: Callable[[MotionConnectionType], None]
    ) -> None:
        """Register the callback used to update the connection status."""
        self._connection_callback = callback

    def register_status_callback(
        self, callback: Callable[[int, int, int, MotionSpeedLevel], None]
    ) -> None:
        """Register the callback used to update the motor status, e.g. position, tilt and battery percentage."""
        self._status_callback = callback
