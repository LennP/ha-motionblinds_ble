"""Constants for the MotionBlinds BLE integration."""

from enum import StrEnum

DOMAIN = "motionblinds_ble"

CONF_LOCAL_NAME = "local_name"
CONF_ADDRESS = "address"
CONF_MAC = "mac"
CONF_BLIND_TYPE = "blind_type"

SERVICE_FAVORITE = "favorite"
SERVICE_CONNECT = "connect"
SERVICE_DISCONNECT = "disconnect"
SERVICE_STATUS = "status"

SETTING_DOUBLE_CLICK_TIME = 500  # Milliseconds

ATTR_CONNECTION_TIMEOUT = "timeout"


class MotionBlindType(StrEnum):
    POSITION = "position"
    POSITION_TILT = "position_tilt"


class MotionRunningType(StrEnum):
    OPENING = "opening"
    CLOSING = "closing"
    STILL = "still"
