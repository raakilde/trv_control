"""Constants for the TRV Control integration."""

DOMAIN = "trv_control"

# Configuration
CONF_ROOMS = "rooms"
CONF_ROOM_NAME = "room_name"
CONF_TEMP_SENSOR = "temp_sensor"
CONF_WINDOW_SENSOR = "window_sensor"
CONF_TRVS = "trvs"

# TRV Configuration (each TRV in a room)
CONF_TRV = "trv"
CONF_RETURN_TEMP = "return_temp"
CONF_RETURN_TEMP_CLOSE = "return_temp_close"
CONF_RETURN_TEMP_OPEN = "return_temp_open"
CONF_MAX_VALVE_POSITION = "max_valve_position"
CONF_ANTICIPATORY_OFFSET = "anticipatory_offset"

# Defaults
DEFAULT_NAME = "TRV Control"
DEFAULT_RETURN_TEMP_CLOSE = 32.0
DEFAULT_RETURN_TEMP_OPEN = 30.0
DEFAULT_MAX_VALVE_POSITION = 100
DEFAULT_ANTICIPATORY_OFFSET = 0.5  # Close valve 0.5°C before target to prevent overshoot

# Proportional control settings
DEFAULT_PROPORTIONAL_BAND = 3.0  # Temperature range for proportional control (°C)
DEFAULT_MIN_VALVE_CHANGE = 5  # Minimum valve position change to prevent flutter (%)
DEFAULT_TEMP_HISTORY_SIZE = 20  # Number of temperature readings to keep for rate calculation

# Services
SERVICE_SET_VALVE_POSITION = "set_valve_position"
SERVICE_SET_TRV_THRESHOLDS = "set_trv_thresholds"
