"""Constants for MotionBlinds BLE."""
from enum import IntEnum, StrEnum

SETTING_MAX_CONNECT_ATTEMPTS = 5
SETTING_DISCONNECT_TIME = 15  # Seconds


class MotionService(StrEnum):
    CONTROL = "d973f2e0b19e11e29e960800200c9a66"


class MotionCharacteristic(IntEnum):
    COMMAND = 0x14  # Handle 0x14, d973f2e2b19e11e29e960800200c9a66
    NOTIFICATION = 0x11  # Handle 0x11, d973f2e1b19e11e29e960800200c9a66


class MotionCommandType(StrEnum):
    OPEN = "03020301"
    CLOSE = "03020302"
    STOP = "03020303"
    OPEN_TILT = "03020309"
    CLOSE_TILT = "0302030a"
    FAVORITE = "03020306"
    PERCENT = "05020440"
    ANGLE = "05020420"
    SET_KEY = "02c001"
    STATUS_QUERY = "03050f02"
    USER_QUERY = "02c005"
    POINT_SET_QUERY = "03050120"


class MotionNotificationType(StrEnum):
    PERCENT = "07040402"
    RUNNING = "070404021e"
    STATUS = "12040f02"


class MotionRunningType(IntEnum):
    OPENING = 0x10
    CLOSING = 0x20


class MotionConnectionType(IntEnum):
    CONNECTED = 0
    CONNECTING = 1
    DISCONNECTED = 2


class MotionRunningType(StrEnum):
    OPENING = "opening"
    CLOSING = "closing"
    STILL = "still"
