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
CONF_MIN_VALVE_POSITION = "min_valve_position"
CONF_ANTICIPATORY_OFFSET = "anticipatory_offset"

# PID/Advanced TRV config constants
CONF_PROPORTIONAL_BAND = "proportional_band"
CONF_PID_ANTICIPATORY_OFFSET = "pid_anticipatory_offset"

# Night saving constants
CONF_NIGHT_SAVING_ENABLED = "night_saving_enabled"
CONF_NIGHT_SCHEDULE = "night_schedule"
CONF_NIGHT_START_TIME = "night_start_time"  # Keep for backward compatibility
CONF_NIGHT_END_TIME = "night_end_time"      # Keep for backward compatibility
CONF_NIGHT_TEMP_REDUCTION = "night_temp_reduction"

# Defaults
DEFAULT_NAME = "TRV Control"
DEFAULT_RETURN_TEMP_CLOSE = (
    32.0  # Keep low for efficiency - high return = wasted energy
)
DEFAULT_RETURN_TEMP_OPEN = 30.0  # Keep low for efficiency
DEFAULT_MAX_VALVE_POSITION = 100
DEFAULT_MIN_VALVE_POSITION = 0
DEFAULT_MIN_VALVE_POSITION_DELTA = 5  # Default delta for max open % above min
DEFAULT_ANTICIPATORY_OFFSET = 0.1  # Reduced from 0.3°C - much less aggressive anticipation

# Proportional control settings
DEFAULT_PROPORTIONAL_BAND = (
    2.0  # Reduced from 2.5°C - even tighter control for better response
)
DEFAULT_MIN_VALVE_CHANGE = (
    15  # Increased from 5% - prevents excessive cycling (main fix)
)
DEFAULT_TEMP_HISTORY_SIZE = 30  # Increased from 20 - better heating rate calculation

# Night saving defaults
DEFAULT_NIGHT_SAVING_ENABLED = False
DEFAULT_NIGHT_START_TIME = "00:00"
DEFAULT_NIGHT_END_TIME = "06:00"
DEFAULT_NIGHT_TEMP_REDUCTION = -2.0
DEFAULT_NIGHT_SCHEDULE = {
    "monday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "tuesday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "wednesday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "thursday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "friday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "saturday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
    "sunday": {"enabled": False, "start_time": "00:00", "end_time": "06:00", "temp_reduction": -2.0},
}

# Services
SERVICE_SET_VALVE_POSITION = "set_valve_position"
SERVICE_SET_TRV_THRESHOLDS = "set_trv_thresholds"
SERVICE_RESET_PERFORMANCE_STATS = "reset_performance_stats"
SERVICE_VALIDATE_TRVS = "validate_trvs"
SERVICE_FORCE_VALVE_CONTROL = "force_valve_control"
