"""Extended MotionDevice with temperature & illuminance support.

The upstream `motionblindsble==0.1.3` library implements only the basic
movement / battery / position protocol. This subclass adds the
temperature + ambient-light query (opcode `030510FA` → response prefix
`130410fa`), as documented in the Coulisse Motionblinds BLE Android app
source (`DeviceSettingActivity.updateTemp`).

Response layout (decrypted, hex):
    13 04 10 fa  XX XX … XX  TT HH LL
        opcode                temp   lux

    TT     = temperature in °C (unsigned byte)
    HH:LL  = 16-bit big-endian raw lux value, multiplied by 10 to get lux
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any, Union

from bleak.backends.characteristic import BleakGATTCharacteristic
from motionblindsble.crypt import MotionCrypt
from motionblindsble.device import MotionDevice, requires_connection

_LOGGER = logging.getLogger(__name__)

TEMPERATURE_QUERY = "030510fa"
TEMPERATURE_RESPONSE_PREFIX = "130410fa"


class ExtendedMotionDevice(MotionDevice):
    """MotionDevice with temperature & illuminance queries."""

    _temperature: int | None
    _illuminance: int | None
    _temperature_callbacks: list[Callable[[int | None], None]]
    _illuminance_callbacks: list[Callable[[int | None], None]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._temperature = None
        self._illuminance = None
        self._temperature_callbacks = []
        self._illuminance_callbacks = []

    @requires_connection
    async def temperature_query(self) -> bool:
        """Query the motor for temperature and ambient light level."""
        return await self._send_command(TEMPERATURE_QUERY)

    def _notification_callback(
        self, char: BleakGATTCharacteristic, byte_array: bytearray
    ) -> None:
        """Intercept the temperature/lux response, then defer to base."""
        decrypted: str = MotionCrypt.decrypt(byte_array.hex())

        if decrypted.startswith(TEMPERATURE_RESPONSE_PREFIX):
            try:
                temp_c = int(decrypted[-6:-4], 16)
                lux_hi = int(decrypted[-4:-2], 16)
                lux_lo = int(decrypted[-2:], 16)
                lux = ((lux_hi << 8) | lux_lo) * 10
            except ValueError:
                _LOGGER.warning(
                    "(%s) Could not parse temperature response: %s",
                    self.ble_device.address,
                    decrypted,
                )
                return

            _LOGGER.debug(
                "(%s) Received temperature: %d°C, illuminance: %d lux",
                self.ble_device.address,
                temp_c,
                lux,
            )
            self._temperature = temp_c
            self._illuminance = lux
            for cb in self._temperature_callbacks:
                cb(temp_c)
            for cb in self._illuminance_callbacks:
                cb(lux)
            return

        super()._notification_callback(char, byte_array)

    async def establish_connection(self) -> bool:
        """Establish a connection and immediately query temperature/lux."""
        connected = await super().establish_connection()
        if connected:
            await self.temperature_query()
        return connected

    def register_temperature_callback(
        self, callback: Callable[[int | None], None]
    ) -> None:
        """Register a callback for temperature updates."""
        self._temperature_callbacks.append(callback)

    def register_illuminance_callback(
        self, callback: Callable[[int | None], None]
    ) -> None:
        """Register a callback for illuminance updates."""
        self._illuminance_callbacks.append(callback)

    def remove_temperature_callback(
        self, identifier: Union[Callable, str]
    ) -> None:
        """Remove a temperature callback."""
        self._generic_remove_callback(identifier, self._temperature_callbacks)

    def remove_illuminance_callback(
        self, identifier: Union[Callable, str]
    ) -> None:
        """Remove an illuminance callback."""
        self._generic_remove_callback(identifier, self._illuminance_callbacks)
