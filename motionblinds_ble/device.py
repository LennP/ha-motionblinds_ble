"""Device for MotionBlinds BLE."""
import logging
from asyncio import (
    CancelledError,
    Task,
    TimerHandle,
    create_task,
    get_event_loop,
    sleep,
)
from collections.abc import Callable, Coroutine
from datetime import datetime
from time import time_ns

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import (
    SETTING_DISCONNECT_TIME,
    SETTING_MAX_CONNECT_ATTEMPTS,
    MotionCharacteristic,
    MotionCommandType,
    MotionConnectionType,
    MotionNotificationType,
    MotionRunningType,
)
from .crypt import MotionCrypt

_LOGGER = logging.getLogger(__name__)


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
    # _ble_device_callback: Callable[[str], BLEDevice] = None

    # Regular callbacks
    _position_callback: Callable[[int, int], None] = None
    _running_callback: Callable[[bool], None] = None
    _connection_callback: Callable[[MotionConnectionType], None] = None
    _status_callback: Callable[[int, int, int], None] = None

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
            _fake_rssi = 0
            self._ble_device = BLEDevice(
                self._device_address, self._device_address, {}, _fake_rssi
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
            position_percentage: int = decrypted_message_bytes[6]
            angle: int = decrypted_message_bytes[7]
            angle_percentage = round(100 * angle / 180)
            self._position_callback(position_percentage, angle_percentage)
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
            self._status_callback(
                position_percentage, angle_percentage, battery_percentage
            )

    def _disconnect_callback(self, client: BleakClient) -> None:
        """Callback called by Bleak when a client disconnects."""
        _LOGGER.info("Device %s disconnected!", self._device_address)
        self.set_connection(MotionConnectionType.DISCONNECTED)

    async def connect(self) -> None:
        """Connect to the device if not connected, returns whether or not the connection was successful."""
        if not self.is_connected():
            # Connect if not connected yet and not busy connecting
            return await self._connect_if_not_connecting()
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
        """Connect if no connection is currently attempted, return True if the connection is successful and only to the last caller of this function."""
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
        except CancelledError:
            # Return False if connecting has been cancelled
            _LOGGER.info("Cancelled connecting")
            self.set_connection(MotionConnectionType.DISCONNECTED)
            return False
        self._connection_task = None
        return (
            self._last_connection_caller_time == this_connection_caller_time
        )  # Return whether or not this function was the last caller

    async def _connect(self) -> bool:
        """Connect to the device, return whether or not the connection was successful."""
        if self._connection_type is MotionConnectionType.CONNECTING:
            return False
        try:
            self.set_connection(MotionConnectionType.CONNECTING)
            _LOGGER.info("Connecting to %s", self._device_address)

            # Standard
            # bleak_client = await self._get_bleak_client()
            # await bleak_client.connect()

            # Bleak retry
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
                int(MotionCharacteristic.NOTIFICATION.value),
                self._notification_callback,
            )

            await self.set_key()
            await self.status_query()

            bleak_client.set_disconnected_callback(self._disconnect_callback)

            # There must be some delay between set_key and returning True, since the motor needs some time to process set_key
            await sleep(0.1)

            return True
        except Exception as e:
            _LOGGER.error("Could not connect to %s: %s", self._device_address, e)
            self._connection_task = None
            self.set_connection(MotionConnectionType.DISCONNECTED)
            return False

    def is_connected(self) -> bool:
        """Return whether or not the device is connected."""
        return (
            self._current_bleak_client is not None
            and self._current_bleak_client.is_connected
        )

    async def _send_command(self, command_prefix: str) -> bool:
        """Write a message to the command characteristic, return whether or not the command was successfully executed."""
        if not await self.connect():
            return False
        try:
            # Command must be generated just before sending due get_time timing
            command = MotionCrypt.encrypt(command_prefix + MotionCrypt.get_time())
            _LOGGER.warning("Sending message: %s", MotionCrypt.decrypt(command))
            # response=False to solve Unlikely Error: [org.bluez.Error.Failed] Operation failed with ATT error: 0x0e (Unlikely Error)
            await self._current_bleak_client.write_gatt_char(
                int(MotionCharacteristic.COMMAND.value),
                bytes.fromhex(command),
                response=False,
            )
            return True
        except Exception as e:
            _LOGGER.warning("Could not execute command: %s", e)
            return False

    async def user_query(self) -> bool:
        """Send user_query command."""
        command_prefix = str(MotionCommandType.USER_QUERY.value)
        return await self._send_command(command_prefix)

    async def set_key(self) -> bool:
        """Send set_key command."""
        command_prefix = str(MotionCommandType.SET_KEY.value)
        return await self._send_command(command_prefix)

    async def status_query(self) -> bool:
        """Send status_query command."""
        command_prefix = str(MotionCommandType.STATUS_QUERY.value)
        return await self._send_command(command_prefix)

    async def point_set_query(self) -> bool:
        """Send point_set_query command."""
        command_prefix = str(MotionCommandType.POINT_SET_QUERY.value)
        return await self._send_command(command_prefix)

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

    # async def stop_tilt(self) -> bool:
    #     """Stops moving the device."""
    #     command_prefix = str(MotionCommandType.STOP.value)
    #     return await self._send_command(command_prefix)

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
        self, callback: Callable[[int, int, int], None]
    ) -> None:
        """Register the callback used to update the motor status, e.g. position, tilt and battery percentage."""
        self._status_callback = callback

    # def register_get_ble_device_callback(
    #     self, callback: Callable[[str], BLEDevice]
    # ) -> None:
    #     """Register the callback used to get a BLEDevice."""
    #     self._ble_device_callback = callback
