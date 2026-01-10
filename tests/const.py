"""Constants for tests."""
from homeassistant.const import CONF_NAME

from custom_components.trv_control.const import (
    DOMAIN,
    CONF_ROOMS,
    CONF_ROOM_NAME,
    CONF_TEMP_SENSOR,
    CONF_TRVS,
    CONF_TRV,
    CONF_RETURN_TEMP,
    CONF_WINDOW_SENSOR,
    CONF_RETURN_TEMP_CLOSE,
    CONF_RETURN_TEMP_OPEN,
    CONF_MAX_VALVE_POSITION,
)

# Mock entity IDs
MOCK_TEMP_SENSOR = "sensor.living_room_temperature"
MOCK_TRV_1 = "climate.living_room_trv_1"
MOCK_TRV_2 = "climate.living_room_trv_2"
MOCK_RETURN_TEMP_1 = "sensor.return_temp_1"
MOCK_RETURN_TEMP_2 = "sensor.return_temp_2"
MOCK_WINDOW_SENSOR = "binary_sensor.living_room_window"

# Mock room configuration
MOCK_ROOM_CONFIG = {
    CONF_ROOM_NAME: "Living Room",
    CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
    CONF_WINDOW_SENSOR: MOCK_WINDOW_SENSOR,
    CONF_TRVS: [
        {
            CONF_TRV: MOCK_TRV_1,
            CONF_RETURN_TEMP: MOCK_RETURN_TEMP_1,
            CONF_RETURN_TEMP_CLOSE: 32.0,
            CONF_RETURN_TEMP_OPEN: 30.0,
            CONF_MAX_VALVE_POSITION: 100,
        },
        {
            CONF_TRV: MOCK_TRV_2,
            CONF_RETURN_TEMP: MOCK_RETURN_TEMP_2,
            CONF_RETURN_TEMP_CLOSE: 32.0,
            CONF_RETURN_TEMP_OPEN: 30.0,
            CONF_MAX_VALVE_POSITION: 80,
        },
    ],
}

MOCK_CONFIG_ENTRY_DATA = {
    CONF_ROOMS: [MOCK_ROOM_CONFIG]
}
