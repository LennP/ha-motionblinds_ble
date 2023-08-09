"""Constants for the MotionBlinds BLE integration."""

from enum import StrEnum

DOMAIN = "motionblinds_ble"

CONF_LOCAL_NAME = "local_name"
CONF_ADDRESS = "address"
CONF_MAC = "mac"
CONF_BLIND_TYPE = "blind_type"

SETTING_DISCONNECT_TIME = 15


class MotionBlindType(StrEnum):
    POSITION = "Position"
    POSITION_TILT = "Position & Tilt"
