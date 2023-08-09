"""Device for MotionBlinds BLE."""
from bleak.backends.device import BLEDevice
from bleak import BleakClient
from .const import (
    MotionCharacteristic,
    MotionCommandType,
    MotionNotificationType,
    MotionRunningType,
    MotionConnectionType,
    SETTING_CONNECT_ATTEMPTS,
)
from .crypt import MotionCrypt

from bleak_retry_connector import establish_connection
from collections.abc import Callable

import logging
from asyncio import Future, sleep
from time import time_ns

_LOGGER = logging.getLogger(__name__)


class MotionDevice:
    _device_address: str = None
    _current_bleak_client: BleakClient = None
    _connection_type: MotionConnectionType = MotionConnectionType.DISCONNECTED

    # Callbacks that are used to interface with HA
    _ble_device_callback: Callable[[str], BLEDevice] = None
    _position_callback: Callable[[int, int], None] = None
    _opening_callback: Callable[[bool], None] = None
    _connection_callback: Callable[[MotionConnectionType], None] = None
    _status_callback: Callable[[int], None] = None

    # Used to ensure the first caller connects, but the last callers command goes through when connecting
    connection_future: Future = None
    last_connection_caller_time: int = None

    def __init__(self, _address: str) -> None:
        self._device_address = _address

    def _get_ble_device(self) -> BLEDevice:
        return self._ble_device_callback(self._device_address)

    async def _get_bleak_client(self) -> BleakClient:
        """Gets the BleakClient either from a BLEDevice callback or otherwise from the address."""
        if self._ble_device_callback:
            ble_device = self._ble_device_callback(self._device_address)
            if ble_device:
                return BleakClient(ble_device)
        return BleakClient(self._device_address)

    def notification_callback(self, characteristic, byte_array: bytearray) -> None:
        """Called by Bleak when a client disconnects."""
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
            and self._opening_callback is not None
        ):
            _LOGGER.info("Running notification")
            is_opening: bool = decrypted_message_bytes[5] == MotionRunningType.OPENING
            self._opening_callback(is_opening)
        elif (
            decrypted_message.startswith(MotionNotificationType.STATUS.value)
            and self._status_callback is not None
        ):
            _LOGGER.info("Updating status")
            position_percentage: int = decrypted_message_bytes[6]
            battery_percentage: int = decrypted_message_bytes[17]
            self._status_callback(position_percentage, battery_percentage)

    def disconnect_callback(self, client: BleakClient) -> None:
        """Called by Bleak when a client disconnects."""
        _LOGGER.info("Device %s disconnected!", self._device_address)
        if self._connection_callback is not None:
            self._connection_callback(MotionConnectionType.DISCONNECTED)
            self._connection_type = MotionConnectionType.DISCONNECTED

    async def disconnect(self) -> None:
        """Called by Home Assistant after X time."""
        if self._current_bleak_client is not None:
            _LOGGER.info("Disconnecting %s", self._device_address)
            await self._current_bleak_client.disconnect()
            self._connection_type = MotionConnectionType.DISCONNECTED
            self._current_bleak_client = None

    async def _connect_if_not_connecting(self) -> bool:
        """Connects if no connection is currently attempted, returns True if the connection is successful and only to the last caller."""
        # Don't try to connect if we are already connecting
        this_connection_caller_time = time_ns()
        self.last_connection_caller_time = this_connection_caller_time
        if self.connection_future is not None:
            _LOGGER.info("Already connecting, waiting for connection")
            connected = await self.connection_future
        else:
            _LOGGER.info("First caller connecting")
            self.connection_future = Future()  # Indicates we are connecting
            connected = await self._connect()
            self.connection_future.set_result(connected)
            self.connection_future = None
        if not connected:
            return False
        return (
            self.last_connection_caller_time == this_connection_caller_time
        )  # Return whether or not this function was the last caller

    async def _connect(self) -> bool:
        """Connects to the device, returns whether or not the connection was successful."""
        if self._connection_type is MotionConnectionType.CONNECTING:
            return False
        try:
            self._connection_callback(MotionConnectionType.CONNECTING)
            self._connection_type = MotionConnectionType.CONNECTING
            _LOGGER.info("Connecting to %s", self._device_address)

            # Standard
            # bleak_client = await self._get_bleak_client()
            # await bleak_client.connect()

            # Bleak retry
            ble_device = self._get_ble_device()
            if ble_device is None:
                _LOGGER.warning("Could not find BLEDevice, creating new BLEDevice")
                _fake_rssi = 0
                ble_device = BLEDevice(
                    self._device_address, self._device_address, {}, _fake_rssi
                )
            bleak_client = await establish_connection(
                BleakClient,
                ble_device,
                self._device_address,
                max_attempts=SETTING_CONNECT_ATTEMPTS,
            )

            _LOGGER.info("Connected to %s", self._device_address)
            self._current_bleak_client = bleak_client
            self._connection_type = MotionConnectionType.CONNECTED
            self._connection_callback(MotionConnectionType.CONNECTED)

            await bleak_client.start_notify(
                int(MotionCharacteristic.NOTIFICATION.value), self.notification_callback
            )

            await self.set_key()
            await self.status_query()

            bleak_client.set_disconnected_callback(self.disconnect_callback)

            # There must be some delay between set_key and returning True, since the motor needs some time to process set_key
            await sleep(0.1)

            return True
        except Exception as e:
            _LOGGER.error("Could not connect to %s: %s", self._device_address, e)
            self._connection_type = MotionConnectionType.DISCONNECTED
            self._connection_callback(MotionConnectionType.DISCONNECTED)
            return False

    def _is_connected(self) -> bool:
        return (
            self._current_bleak_client is not None
            and self._current_bleak_client.is_connected
        )

    async def _send_command(self, command_prefix: str) -> bool:
        """Writes a message to the command characteristic, returns whether or not the command was successfully executed."""
        if not self._is_connected():
            # Connect if not connected yet and not busy connecting
            if not await self._connect_if_not_connecting():
                return False
        # Command must be generated just before sending due to get_time
        try:
            command = MotionCrypt.encrypt(command_prefix + MotionCrypt.get_time())
            _LOGGER.warning("Sending message: %s", MotionCrypt.decrypt(command))
            # response=False to solve Unlikely Error
            # [org.bluez.Error.Failed] Operation failed with ATT error: 0x0e (Unlikely Error)
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
        """Operation set key"""
        command_prefix = str(MotionCommandType.USER_QUERY.value)
        return await self._send_command(command_prefix)

    async def set_key(self) -> bool:
        """Operation set key"""
        command_prefix = str(MotionCommandType.SET_KEY.value)
        return await self._send_command(command_prefix)

    async def status_query(self) -> bool:
        """Operation set key"""
        command_prefix = str(MotionCommandType.STATUS_QUERY.value)
        return await self._send_command(command_prefix)

    async def point_set_query(self) -> bool:
        """Operation set key"""
        command_prefix = str(MotionCommandType.POINT_SET_QUERY.value)
        return await self._send_command(command_prefix)

    async def percentage(self, percentage: int) -> bool:
        """Makes the device move to a given percentage."""
        assert not percentage < 0 and not percentage > 100
        command_prefix = (
            str(MotionCommandType.PERCENT.value) + hex(percentage)[2:].zfill(2) + "00"
        )
        return await self._send_command(command_prefix)

    async def open(self) -> bool:
        """Opens the device."""
        command_prefix = str(MotionCommandType.OPEN.value)
        return await self._send_command(command_prefix)

    async def close(self) -> bool:
        """Closes the device."""
        command_prefix = str(MotionCommandType.CLOSE.value)
        return await self._send_command(command_prefix)

    async def stop(self) -> bool:
        """Stops moving the device."""
        command_prefix = str(MotionCommandType.STOP.value)
        return await self._send_command(command_prefix)

    async def percentage_tilt(self, percentage: int) -> bool:
        """Makes the device move to a given percentage."""
        assert not percentage < 0 and not percentage > 100
        angle = round(180 * percentage / 100)
        command_prefix = (
            str(MotionCommandType.ANGLE.value) + "00" + hex(angle)[2:].zfill(2)
        )
        return await self._send_command(command_prefix)

    async def open_tilt(self) -> bool:
        """Opens the device."""
        # Step or fully tilt?
        # command_prefix = str(MotionCommandType.OPEN_TILT.value)
        command_prefix = str(MotionCommandType.ANGLE.value) + "00" + hex(0)[2:].zfill(2)
        return await self._send_command(command_prefix)

    async def close_tilt(self) -> bool:
        """Closes the device."""
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
        _LOGGER.info("Added position callback")
        self._position_callback = callback

    def register_opening_callback(self, callback: Callable[[bool], None]) -> None:
        self._opening_callback = callback

    def register_connection_callback(
        self, callback: Callable[[MotionConnectionType], None]
    ) -> None:
        self._connection_callback = callback

    def register_status_callback(self, callback: Callable[[int, int], None]) -> None:
        self._status_callback = callback

    def register_get_ble_device_callback(
        self, callback: Callable[[str], BLEDevice]
    ) -> None:
        self._ble_device_callback = callback
