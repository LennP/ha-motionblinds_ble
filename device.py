"""Extended MotionDevice with the full Coulisse Motionblinds BLE protocol.

The upstream `motionblindsble==0.1.3` library implements only the basic
movement / battery / position protocol. This subclass adds the rest of
the command set documented in the Coulisse Motionblinds BLE Android app
source (Coulisse-BV/MotionblindsBLE-App), including:

  * Temperature + illuminance read (one packet)
  * Light on/off and brightness setpoint
  * Rain / wind / wind+light+rain sensor enable/disable + status
  * Slow stop on/off
  * Calibration / endpoint / angle setup
  * Auto position, set direction, tilt reverse
  * Backside (top/bottom) movement
  * Device type (E / ED) change and queries
  * Point up / down

Where the upstream library already exposes the same opcode (e.g. open,
close, stop, percent, tilt, status, set_key) we keep using its method
rather than duplicating.

Response prefixes (parsed in `_notification_callback`):
  130410fa  Temperature + Illuminance
  070404fb  Light brightness setpoint
  07040480  Slow stop on/off
  04040120  Endpoint info (up / down / favorite set)
  04040148  Direction (plug)
  04040187  Wind / light / rain combined status
  0404018b  Point type (E vs ED)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any, Union

from bleak.backends.characteristic import BleakGATTCharacteristic
from motionblindsble.crypt import MotionCrypt
from motionblindsble.device import MotionDevice, requires_connection

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command opcodes (request side, hex strings — encryption layer adds time)
# ---------------------------------------------------------------------------

# Movement extras (point up / down)
CMD_POINT_UP = "03020304"
CMD_POINT_DOWN = "03020305"

# Backside movement
CMD_BACK_TOP_OPEN = "03020382"
CMD_BACK_TOP_CLOSE = "03020383"
CMD_BACK_BOTTOM_OPEN = "03020384"
CMD_BACK_BOTTOM_CLOSE = "03020385"

# Light
CMD_LIGHT_ON = "03020371"
CMD_LIGHT_OFF = "03020372"
CMD_LIGHT_QUERY_ALONE = "03020602"
CMD_BRIGHTNESS_PREFIX = "05020711"  # +<bri_byte>+"00"
CMD_LIGHT_PERCENT_QUERY = "030501fb"

# Sensors
CMD_RAIN_ON = "03020373"
CMD_RAIN_OFF = "03020374"
CMD_RAIN_HEARTBEAT_ON = "03020375"
CMD_RAIN_HEARTBEAT_OFF = "03020376"
CMD_WIND_ON = "03020377"
CMD_WIND_OFF = "03020378"
CMD_COMBO_ON = "03020357"
CMD_COMBO_OFF = "03020358"
CMD_WIND_RAIN_QUERY = "03050187"

# Calibration / endpoints
CMD_CALIBRATION_BEGIN = "0302035c"
CMD_CALIBRATION_END = "0302035d"
CMD_SET_ENDPOINT_UP = "03020323"
CMD_SET_ENDPOINT_DOWN = "03020324"
CMD_SET_ENDPOINT_THIRD = "03020325"
CMD_SET_ANGLE_BEGIN = "03020321"
CMD_SET_ANGLE_ZERO = "03020322"
CMD_SET_ANGLE_NINETY = "0302032b"
CMD_SET_ANGLE_ONE_EIGHTY = "0302032e"
CMD_TILT_REVERSE = "03020334"
CMD_AUTO_POSITION = "0302032f"
CMD_SET_DIRECTION = "03020317"
CMD_ENDPOINTS_QUERY = "03050120"

# Slow stop
CMD_SLOW_STOP_OFF = "03020341"
CMD_SLOW_STOP_ON = "03020342"
CMD_SLOW_STOP_QUERY = "03050480"

# Device type
CMD_DEVICE_TYPE_E = "03020380"
CMD_DEVICE_TYPE_ED = "03020381"
CMD_DEVICE_TYPE_QUERY = "03050110"
CMD_POINT_TYPE_QUERY = "0305018b"
CMD_DIRECTION_QUERY = "03050148"
CMD_VERTICAL_STATE_QUERY = "03050106"

# Temperature + illuminance (one query, both values back)
CMD_TEMPERATURE_QUERY = "030510fa"


# ---------------------------------------------------------------------------
# Response prefixes (after AES-decrypt + PKCS7-unpad → hex string)
# ---------------------------------------------------------------------------

RX_TEMPERATURE = "130410fa"
RX_LIGHT_PERCENT = "070404fb"
RX_SLOW_STOP = "07040480"
RX_ENDPOINTS = "04040120"
RX_DIRECTION = "04040148"
RX_WIND_LIGHT_RAIN = "04040187"
RX_POINT_TYPE = "0404018b"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msb_bit(byte: int, n: int) -> bool:
    """Replicates `Utils.bit(i, n)` from the Android app: bit `n` from the
    MSB end (so n=0 is bit 7, n=1 is bit 6, etc.)."""
    return bool(byte & (1 << (7 - n)))


@dataclass
class EndpointInfo:
    """Endpoint configuration reported by the `04040120` response."""

    up: bool
    down: bool
    favorite: bool

    @property
    def both_set(self) -> bool:
        return self.up and self.down


@dataclass
class SensorStatus:
    """Wind / light / rain sensor status (`04040187`).

    Only the raw byte is preserved — the precise bit layout per sensor is
    not fully documented in the protocol PDF; the engineer can capture
    real values to refine the per-sensor split if needed.
    """

    raw: int


# ---------------------------------------------------------------------------
# Extended device
# ---------------------------------------------------------------------------


class ExtendedMotionDevice(MotionDevice):
    """MotionDevice with the extended Coulisse protocol surface."""

    # Read-back state
    _temperature: int | None
    _illuminance: int | None
    _brightness: int | None
    _slow_stop: bool | None
    _direction_reversed: bool | None
    _endpoint_info: EndpointInfo | None
    _sensor_status: SensorStatus | None
    _point_type: str | None  # "E" or "ED"

    # Callback lists
    _temperature_callbacks: list[Callable[[int | None], None]]
    _illuminance_callbacks: list[Callable[[int | None], None]]
    _brightness_callbacks: list[Callable[[int | None], None]]
    _slow_stop_callbacks: list[Callable[[bool | None], None]]
    _direction_callbacks: list[Callable[[bool | None], None]]
    _endpoint_callbacks: list[Callable[[EndpointInfo | None], None]]
    _sensor_status_callbacks: list[Callable[[SensorStatus | None], None]]
    _point_type_callbacks: list[Callable[[str | None], None]]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._temperature = None
        self._illuminance = None
        self._brightness = None
        self._slow_stop = None
        self._direction_reversed = None
        self._endpoint_info = None
        self._sensor_status = None
        self._point_type = None
        self._temperature_callbacks = []
        self._illuminance_callbacks = []
        self._brightness_callbacks = []
        self._slow_stop_callbacks = []
        self._direction_callbacks = []
        self._endpoint_callbacks = []
        self._sensor_status_callbacks = []
        self._point_type_callbacks = []

    # ------------------------------------------------------------------ #
    # Notification handling
    # ------------------------------------------------------------------ #

    def _notification_callback(
        self, char: BleakGATTCharacteristic, byte_array: bytearray
    ) -> None:
        """Intercept extended response prefixes, then defer to base."""
        decrypted: str = MotionCrypt.decrypt(byte_array.hex())
        _LOGGER.debug(
            "(%s) RX %s", self.ble_device.address, decrypted
        )

        if self._handle_extended_notification(decrypted):
            return

        super()._notification_callback(char, byte_array)

    def _handle_extended_notification(self, decrypted: str) -> bool:
        """Try to parse one of the extended responses. Return True if matched."""
        try:
            if decrypted.startswith(RX_TEMPERATURE):
                self._parse_temperature(decrypted)
                return True
            if decrypted.startswith(RX_LIGHT_PERCENT):
                self._parse_brightness(decrypted)
                return True
            if decrypted.startswith(RX_SLOW_STOP):
                self._parse_slow_stop(decrypted)
                return True
            if decrypted.startswith(RX_ENDPOINTS):
                self._parse_endpoints(decrypted)
                return True
            if decrypted.startswith(RX_DIRECTION):
                self._parse_direction(decrypted)
                return True
            if decrypted.startswith(RX_WIND_LIGHT_RAIN):
                self._parse_sensor_status(decrypted)
                return True
            if decrypted.startswith(RX_POINT_TYPE):
                self._parse_point_type(decrypted)
                return True
        except (ValueError, IndexError) as exc:
            _LOGGER.warning(
                "(%s) Could not parse extended response %s: %s",
                self.ble_device.address,
                decrypted,
                exc,
            )
        return False

    # Per-prefix parsers --------------------------------------------------- #

    def _parse_temperature(self, decrypted: str) -> None:
        """Last 3 bytes of `130410fa…TT HH LL` → temp °C, lux × 10."""
        temp_c = int(decrypted[-6:-4], 16)
        lux_hi = int(decrypted[-4:-2], 16)
        lux_lo = int(decrypted[-2:], 16)
        lux = ((lux_hi << 8) | lux_lo) * 10
        self._temperature = temp_c
        self._illuminance = lux
        for cb in list(self._temperature_callbacks):
            cb(temp_c)
        for cb in list(self._illuminance_callbacks):
            cb(lux)

    def _parse_brightness(self, decrypted: str) -> None:
        """`070404fb XX` → brightness percent (0–100)."""
        pct = int(decrypted[8:10], 16)
        self._brightness = pct
        for cb in list(self._brightness_callbacks):
            cb(pct)

    def _parse_slow_stop(self, decrypted: str) -> None:
        """`07040480 …` — last byte's bit 4 (from MSB-binary representation
        of the 8-bit padded value) carries the on/off state per the app code."""
        last_byte = int(decrypted[-2:], 16)
        bin_str = format(last_byte, "08b")
        on = bin_str[4] == "0"  # app: areEqual(strSubstring11, "0") => "on"
        self._slow_stop = on
        for cb in list(self._slow_stop_callbacks):
            cb(on)

    def _parse_endpoints(self, decrypted: str) -> None:
        """`04040120 BB` — bits 7,6,5 (MSB-numbered) = up, down, favorite."""
        b = int(decrypted[8:10], 16)
        info = EndpointInfo(
            up=_msb_bit(b, 0), down=_msb_bit(b, 1), favorite=_msb_bit(b, 2)
        )
        self._endpoint_info = info
        for cb in list(self._endpoint_callbacks):
            cb(info)

    def _parse_direction(self, decrypted: str) -> None:
        """`04040148 XX` — `01` = reversed, anything else = normal."""
        reversed_ = decrypted[8:10] == "01"
        self._direction_reversed = reversed_
        for cb in list(self._direction_callbacks):
            cb(reversed_)

    def _parse_sensor_status(self, decrypted: str) -> None:
        """`04040187 BB` — combined wind/light/rain status (raw byte)."""
        raw = int(decrypted[8:10], 16)
        status = SensorStatus(raw=raw)
        self._sensor_status = status
        for cb in list(self._sensor_status_callbacks):
            cb(status)

    def _parse_point_type(self, decrypted: str) -> None:
        """`0404018b BB` — bit 5 of the 8-bit binary string (MSB-padded):
        '0' → ED, '1' → E (per the Android app)."""
        b = int(decrypted[8:10], 16)
        bit5 = format(b, "08b")[5]
        kind = "E" if bit5 == "1" else "ED"
        self._point_type = kind
        for cb in list(self._point_type_callbacks):
            cb(kind)

    # ------------------------------------------------------------------ #
    # Connection hook — fire all queries once we're up
    # ------------------------------------------------------------------ #

    async def establish_connection(self) -> bool:
        connected = await super().establish_connection()
        if connected:
            for query in (
                self.temperature_query,
                self.brightness_query,
                self.slow_stop_query,
                self.endpoints_query,
                self.direction_query,
                self.wind_rain_query,
                self.point_type_query,
            ):
                try:
                    await query()
                except Exception as exc:  # noqa: BLE001 — best effort
                    _LOGGER.debug(
                        "(%s) Extended query %s failed: %s",
                        self.ble_device.address,
                        query.__name__,
                        exc,
                    )
        return connected

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    # Queries
    @requires_connection
    async def temperature_query(self) -> bool:
        return await self._send_command(CMD_TEMPERATURE_QUERY)

    @requires_connection
    async def brightness_query(self) -> bool:
        return await self._send_command(CMD_LIGHT_PERCENT_QUERY)

    @requires_connection
    async def slow_stop_query(self) -> bool:
        return await self._send_command(CMD_SLOW_STOP_QUERY)

    @requires_connection
    async def endpoints_query(self) -> bool:
        return await self._send_command(CMD_ENDPOINTS_QUERY)

    @requires_connection
    async def direction_query(self) -> bool:
        return await self._send_command(CMD_DIRECTION_QUERY)

    @requires_connection
    async def wind_rain_query(self) -> bool:
        return await self._send_command(CMD_WIND_RAIN_QUERY)

    @requires_connection
    async def point_type_query(self) -> bool:
        return await self._send_command(CMD_POINT_TYPE_QUERY)

    @requires_connection
    async def device_type_query(self) -> bool:
        return await self._send_command(CMD_DEVICE_TYPE_QUERY)

    @requires_connection
    async def vertical_state_query(self) -> bool:
        return await self._send_command(CMD_VERTICAL_STATE_QUERY)

    # Light
    @requires_connection
    async def light_on(self) -> bool:
        return await self._send_command(CMD_LIGHT_ON)

    @requires_connection
    async def light_off(self) -> bool:
        return await self._send_command(CMD_LIGHT_OFF)

    @requires_connection
    async def set_brightness(self, percentage: int) -> bool:
        if not 0 <= percentage <= 100:
            raise ValueError(f"Brightness must be 0–100, got {percentage}")
        payload = f"{CMD_BRIGHTNESS_PREFIX}{percentage:02x}00"
        result = await self._send_command(payload)
        if result:
            self._brightness = percentage
            for cb in list(self._brightness_callbacks):
                cb(percentage)
        return result

    # Sensors
    @requires_connection
    async def rain_sensor(self, enable: bool) -> bool:
        return await self._send_command(CMD_RAIN_ON if enable else CMD_RAIN_OFF)

    @requires_connection
    async def wind_sensor(self, enable: bool) -> bool:
        return await self._send_command(CMD_WIND_ON if enable else CMD_WIND_OFF)

    @requires_connection
    async def combo_sensor(self, enable: bool) -> bool:
        """Wind + light + rain combined enable/disable."""
        return await self._send_command(CMD_COMBO_ON if enable else CMD_COMBO_OFF)

    # Slow stop
    @requires_connection
    async def slow_stop(self, enable: bool) -> bool:
        result = await self._send_command(
            CMD_SLOW_STOP_ON if enable else CMD_SLOW_STOP_OFF
        )
        if result:
            self._slow_stop = enable
            for cb in list(self._slow_stop_callbacks):
                cb(enable)
        return result

    # Calibration / endpoints / angle
    @requires_connection
    async def calibration_begin(self) -> bool:
        return await self._send_command(CMD_CALIBRATION_BEGIN)

    @requires_connection
    async def calibration_end(self) -> bool:
        return await self._send_command(CMD_CALIBRATION_END)

    @requires_connection
    async def set_endpoint_up(self) -> bool:
        return await self._send_command(CMD_SET_ENDPOINT_UP)

    @requires_connection
    async def set_endpoint_down(self) -> bool:
        return await self._send_command(CMD_SET_ENDPOINT_DOWN)

    @requires_connection
    async def set_endpoint_third(self) -> bool:
        return await self._send_command(CMD_SET_ENDPOINT_THIRD)

    @requires_connection
    async def set_angle_begin(self) -> bool:
        return await self._send_command(CMD_SET_ANGLE_BEGIN)

    @requires_connection
    async def set_angle_zero(self) -> bool:
        return await self._send_command(CMD_SET_ANGLE_ZERO)

    @requires_connection
    async def set_angle_ninety(self) -> bool:
        return await self._send_command(CMD_SET_ANGLE_NINETY)

    @requires_connection
    async def set_angle_one_eighty(self) -> bool:
        return await self._send_command(CMD_SET_ANGLE_ONE_EIGHTY)

    @requires_connection
    async def tilt_reverse(self) -> bool:
        return await self._send_command(CMD_TILT_REVERSE)

    @requires_connection
    async def auto_position(self) -> bool:
        return await self._send_command(CMD_AUTO_POSITION)

    @requires_connection
    async def set_direction(self) -> bool:
        return await self._send_command(CMD_SET_DIRECTION)

    # Point movement
    @requires_connection
    async def point_up(self) -> bool:
        return await self._send_command(CMD_POINT_UP)

    @requires_connection
    async def point_down(self) -> bool:
        return await self._send_command(CMD_POINT_DOWN)

    # Backside movement
    @requires_connection
    async def back_top_open(self) -> bool:
        return await self._send_command(CMD_BACK_TOP_OPEN)

    @requires_connection
    async def back_top_close(self) -> bool:
        return await self._send_command(CMD_BACK_TOP_CLOSE)

    @requires_connection
    async def back_bottom_open(self) -> bool:
        return await self._send_command(CMD_BACK_BOTTOM_OPEN)

    @requires_connection
    async def back_bottom_close(self) -> bool:
        return await self._send_command(CMD_BACK_BOTTOM_CLOSE)

    # Device type
    @requires_connection
    async def set_device_type_e(self) -> bool:
        return await self._send_command(CMD_DEVICE_TYPE_E)

    @requires_connection
    async def set_device_type_ed(self) -> bool:
        return await self._send_command(CMD_DEVICE_TYPE_ED)

    # ------------------------------------------------------------------ #
    # Callback registration
    # ------------------------------------------------------------------ #

    def register_temperature_callback(self, cb: Callable[[int | None], None]) -> None:
        self._temperature_callbacks.append(cb)

    def register_illuminance_callback(self, cb: Callable[[int | None], None]) -> None:
        self._illuminance_callbacks.append(cb)

    def register_brightness_callback(self, cb: Callable[[int | None], None]) -> None:
        self._brightness_callbacks.append(cb)

    def register_slow_stop_callback(self, cb: Callable[[bool | None], None]) -> None:
        self._slow_stop_callbacks.append(cb)

    def register_direction_callback(self, cb: Callable[[bool | None], None]) -> None:
        self._direction_callbacks.append(cb)

    def register_endpoint_callback(
        self, cb: Callable[[EndpointInfo | None], None]
    ) -> None:
        self._endpoint_callbacks.append(cb)

    def register_sensor_status_callback(
        self, cb: Callable[[SensorStatus | None], None]
    ) -> None:
        self._sensor_status_callbacks.append(cb)

    def register_point_type_callback(self, cb: Callable[[str | None], None]) -> None:
        self._point_type_callbacks.append(cb)

    # Removal helpers
    def remove_temperature_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._temperature_callbacks)

    def remove_illuminance_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._illuminance_callbacks)

    def remove_brightness_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._brightness_callbacks)

    def remove_slow_stop_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._slow_stop_callbacks)

    def remove_direction_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._direction_callbacks)

    def remove_endpoint_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._endpoint_callbacks)

    def remove_sensor_status_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._sensor_status_callbacks)

    def remove_point_type_callback(self, identifier: Union[Callable, str]) -> None:
        self._generic_remove_callback(identifier, self._point_type_callbacks)
