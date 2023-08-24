"""Constants for MotionBlinds BLE."""
from enum import IntEnum, StrEnum

SETTING_MAX_CONNECT_ATTEMPTS = 5
SETTING_DISCONNECT_TIME = 15  # Seconds


class MotionService(StrEnum):
    CONTROL = "d973f2e0-b19e-11e2-9e96-0800200c9a66"


class MotionCharacteristic(StrEnum):
    COMMAND = "d973f2e2-b19e-11e2-9e96-0800200c9a66"  # Handle 0x15, d973f2e2-b19e-11e2-9e96-0800200c9a66
    NOTIFICATION = "d973f2e1-b19e-11e2-9e96-0800200c9a66"  # Handle 0x12, d973f2e1-b19e-11e2-9e96-0800200c9a66


class MotionCommandType(StrEnum):
    OPEN = "03020301"
    CLOSE = "03020302"
    STOP = "03020303"
    OPEN_TILT = "03020309"
    CLOSE_TILT = "0302030a"
    FAVORITE = "03020306"
    PERCENT = "05020440"
    ANGLE = "05020420"
    SPEED = "0403010a"
    SET_KEY = "02c001"
    STATUS_QUERY = "03050f02"
    USER_QUERY = "02c005"
    POINT_SET_QUERY = "03050120"


class MotionNotificationType(StrEnum):
    PERCENT = "07040402"
    RUNNING = "070404021e"
    READY = "0201c0"
    STATUS = "12040f02"


class MotionConnectionType(StrEnum):
    CONNECTED = "connected"
    CONNECTING = "connecting"
    DISCONNECTED = "disconnected"


class MotionRunningType(StrEnum):
    OPENING = "opening"
    CLOSING = "closing"
    STILL = "still"


class MotionSpeedLevel(IntEnum):
    LOW = 0x01
    MEDIUM = 0x02
    HIGH = 0x03
