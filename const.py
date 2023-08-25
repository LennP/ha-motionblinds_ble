"""Constants for the MotionBlinds BLE integration."""

from enum import StrEnum

ATTR_CALIBRATION = "calibration"
ATTR_CONNECTION_TIMEOUT = "connection_timeout"
ATTR_CONNECTION_TYPE = "connection_type"
ATTR_SPEED = "speed"
ATTR_BATTERY = "battery"
ATTR_CONNECT = "connect"
ATTR_DISCONNECT = "disconnect"
ATTR_FAVORITE = "favorite"

CONF_LOCAL_NAME = "local_name"
CONF_ADDRESS = "address"
CONF_MAC_CODE = "mac_code"
CONF_BLIND_TYPE = "blind_type"

DOMAIN = "motionblinds_ble"

ERROR_ALREADY_CONFIGURED = "already_configured"
ERROR_COULD_NOT_FIND_MOTOR = "could_not_find_motor"
ERROR_INVALID_MAC_CODE = "invalid_mac_code"
ERROR_NO_BLUETOOTH_ADAPTER = "no_bluetooth_adapter"
ERROR_NO_DEVICES_FOUND = "no_devices_found"

ICON_CALIBRATION = "mdi:tune"
ICON_SPEED = "mdi:run-fast"
ICON_CONNECT = "mdi:bluetooth"
ICON_DISCONNECT = "mdi:bluetooth-off"
ICON_FAVORITE = "mdi:star"

MANUFACTURER = "MotionBlinds - Coulisse"

SERVICE_CONNECT = "connect"
SERVICE_DISCONNECT = "disconnect"
SERVICE_FAVORITE = "favorite"
SERVICE_STATUS = "status"

SETTING_DOUBLE_CLICK_TIME = 500  # Milliseconds


class MotionBlindType(StrEnum):
    POSITION = "position"
    TILT = "tilt"
    POSITION_TILT = "position_tilt"
    POSITION_CURTAIN = "position_curtain"


class MotionRunningType(StrEnum):
    CLOSING = "closing"
    OPENING = "opening"
    STILL = "still"
