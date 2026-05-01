"""Constants for the MotionBlinds BLE integration."""

ATTR_BATTERY = "battery"
ATTR_BRIGHTNESS = "brightness"
ATTR_CALIBRATION = "calibration"
ATTR_CONNECT = "connect"
ATTR_CONNECTION = "connection"
ATTR_DIRECTION = "direction"
ATTR_DISCONNECT = "disconnect"
ATTR_ENDPOINTS = "endpoints"
ATTR_FAVORITE = "favorite"
ATTR_ILLUMINANCE = "illuminance"
ATTR_POINT_TYPE = "point_type"
ATTR_SENSOR_STATUS = "sensor_status"
ATTR_SIGNAL_STRENGTH = "signal_strength"
ATTR_SPEED = "speed"
ATTR_TEMPERATURE = "temperature"

# Switch entities
ATTR_LIGHT = "light"
ATTR_RAIN_SENSOR = "rain_sensor"
ATTR_WIND_SENSOR = "wind_sensor"
ATTR_COMBO_SENSOR = "combo_sensor"
ATTR_SLOW_STOP = "slow_stop"

# Button entities (commands)
ATTR_POINT_UP = "point_up"
ATTR_POINT_DOWN = "point_down"
ATTR_CALIBRATION_BEGIN = "calibration_begin"
ATTR_CALIBRATION_END = "calibration_end"
ATTR_SET_ENDPOINT_UP = "set_endpoint_up"
ATTR_SET_ENDPOINT_DOWN = "set_endpoint_down"
ATTR_SET_ENDPOINT_THIRD = "set_endpoint_third"
ATTR_SET_ANGLE_BEGIN = "set_angle_begin"
ATTR_SET_ANGLE_ZERO = "set_angle_zero"
ATTR_SET_ANGLE_NINETY = "set_angle_ninety"
ATTR_SET_ANGLE_ONE_EIGHTY = "set_angle_one_eighty"
ATTR_TILT_REVERSE = "tilt_reverse"
ATTR_AUTO_POSITION = "auto_position"
ATTR_SET_DIRECTION = "set_direction"
ATTR_BACK_TOP_OPEN = "back_top_open"
ATTR_BACK_TOP_CLOSE = "back_top_close"
ATTR_BACK_BOTTOM_OPEN = "back_bottom_open"
ATTR_BACK_BOTTOM_CLOSE = "back_bottom_close"

# Select entities
ATTR_DEVICE_TYPE = "device_type"

CONF_LOCAL_NAME = "local_name"
CONF_MAC_CODE = "mac_code"
CONF_BLIND_TYPE = "blind_type"

DOMAIN = "motionblinds_ble"

ERROR_COULD_NOT_FIND_MOTOR = "could_not_find_motor"
ERROR_INVALID_MAC_CODE = "invalid_mac_code"
ERROR_NO_BLUETOOTH_ADAPTER = "no_bluetooth_adapter"
ERROR_NO_DEVICES_FOUND = "no_devices_found"

ICON_VERTICAL_BLIND = "mdi:blinds-vertical-closed"

MANUFACTURER = "MotionBlinds - Coulisse"

OPTION_DISCONNECT_TIME = "disconnect_time"
OPTION_PERMANENT_CONNECTION = "permanent_connection"
