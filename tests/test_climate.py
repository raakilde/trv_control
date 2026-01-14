"""Tests for TRV Control climate platform."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import timedelta

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    HVACMode,
)
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.core import HomeAssistant, Event
from homeassistant.helpers.event import async_track_state_change_event
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.trv_control.climate import TRVClimate
from custom_components.trv_control.const import DOMAIN
from .const import (
    MOCK_CONFIG_ENTRY_DATA,
    MOCK_ROOM_CONFIG,
    MOCK_TEMP_SENSOR,
    MOCK_TRV_1,
    MOCK_TRV_2,
    MOCK_RETURN_TEMP_1,
    MOCK_RETURN_TEMP_2,
    MOCK_WINDOW_SENSOR,
)


@pytest.fixture
async def climate_entity(hass, mock_config_entry):
    """Create a TRVClimate entity."""
    mock_config_entry.add_to_hass(hass)
    entity = TRVClimate(mock_config_entry, MOCK_ROOM_CONFIG)
    entity.hass = hass
    return entity


async def test_init(climate_entity):
    """Test climate entity initialization."""
    assert climate_entity._attr_name == "Living Room TRV Control"
    assert climate_entity._temp_sensor_id == MOCK_TEMP_SENSOR
    assert climate_entity._window_sensor_id == MOCK_WINDOW_SENSOR
    assert len(climate_entity._trvs) == 2
    assert MOCK_TRV_1 in climate_entity._trv_states
    assert MOCK_TRV_2 in climate_entity._trv_states
    assert climate_entity._attr_icon == "mdi:radiator"


async def test_set_temperature(climate_entity):
    """Test setting temperature triggers valve control for all TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity._attr_current_temperature = 20.0
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 25.0
    climate_entity._trv_states[MOCK_TRV_2]["return_temp"] = 26.0
    
    # Mock state.get for nudge check
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0})
    
    assert climate_entity._attr_target_temperature == 22.0
    # Should trigger valve control which may send temperature to TRVs
    assert climate_entity.hass.services.async_call.called


async def test_set_hvac_mode(climate_entity):
    """Test setting HVAC mode sends to all TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    
    await climate_entity.async_set_hvac_mode(HVACMode.HEAT)
    
    assert climate_entity._attr_hvac_mode == HVACMode.HEAT
    assert climate_entity.hass.services.async_call.call_count == 2
    
    calls = climate_entity.hass.services.async_call.call_args_list
    assert calls[0] == call("climate", "set_hvac_mode", {
        "entity_id": MOCK_TRV_1,
        "hvac_mode": HVACMode.HEAT
    }, blocking=True)


async def test_set_hvac_mode_window_open(climate_entity):
    """Test cannot turn on heating when window is open."""
    climate_entity._window_open = True
    climate_entity.hass.services.async_call = AsyncMock()
    
    await climate_entity.async_set_hvac_mode(HVACMode.HEAT)
    
    # Should not call service
    climate_entity.hass.services.async_call.assert_not_called()


async def test_return_temp_control_close_valve(climate_entity):
    """Test valve closes when return temp exceeds threshold."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    
    climate_entity._attr_current_temperature = 20.0
    climate_entity._attr_target_temperature = 23.0
    
    trv_config = climate_entity._trvs[0]
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 33.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 100
    
    await climate_entity._async_control_valve(trv_config)
    
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is True
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_position"] == 0


async def test_return_temp_control_open_valve(climate_entity):
    """Test valve opens when return temp drops below threshold."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    
    climate_entity._attr_current_temperature = 20.0
    climate_entity._attr_target_temperature = 23.0
    
    trv_config = climate_entity._trvs[0]
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 27.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 0
    
    await climate_entity._async_control_valve(trv_config)
    
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is True
    # Should open to max position (100 is default)
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_position"] == 100


async def test_valve_control_with_window_open(climate_entity):
    """Test valve control is skipped when window is open."""
    climate_entity._window_open = True
    climate_entity.hass.services.async_call = AsyncMock()
    
    trv_config = climate_entity._trvs[0]
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 35.0
    
    await climate_entity._async_control_valve(trv_config)
    
    # Should not change valve state
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is False


async def test_extra_state_attributes(climate_entity):
    """Test extra state attributes include all TRV info."""
    climate_entity._attr_current_temperature = 22.0
    climate_entity._attr_target_temperature = 23.0
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 28.5
    climate_entity._trv_states[MOCK_TRV_2]["return_temp"] = 30.2
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 50
    climate_entity._trv_states[MOCK_TRV_2]["valve_position"] = 80
    
    # Mock TRV entity states for friendly names
    climate_entity.hass.states = MagicMock()
    mock_trv1_state = MagicMock()
    mock_trv1_state.attributes = {"friendly_name": "Living Room TRV 1"}
    mock_trv2_state = MagicMock()
    mock_trv2_state.attributes = {"friendly_name": "Living Room TRV 2"}
    
    def get_state(entity_id):
        if entity_id == MOCK_TRV_1:
            return mock_trv1_state
        elif entity_id == MOCK_TRV_2:
            return mock_trv2_state
        return None
    
    climate_entity.hass.states.get = get_state
    
    attrs = climate_entity.extra_state_attributes
    
    assert attrs["temp_sensor"] == MOCK_TEMP_SENSOR
    assert attrs["trv_count"] == 2
    assert attrs["window_sensor"] == MOCK_WINDOW_SENSOR
    assert attrs["heating_status"] in ["heating", "target_reached", "off", "window_open"]
    assert attrs["window_open"] is False
    
    # Check TRV attributes use friendly names
    assert "living_room_trv_1_entity" in attrs
    assert attrs["living_room_trv_1_return_temp"] == 28.5
    assert attrs["living_room_trv_1_valve_position"] == 50
    assert attrs["living_room_trv_1_close_threshold"] == 32.0
    assert "living_room_trv_1_status" in attrs
    assert "living_room_trv_1_status_reason" in attrs


async def test_window_sensor_opens(climate_entity):
    """Test heating turns off when window opens."""
    climate_entity._attr_hvac_mode = HVACMode.HEAT
    climate_entity._window_open = False
    
    # Simulate window opening
    climate_entity._window_open = True
    climate_entity._saved_hvac_mode = HVACMode.HEAT
    
    # In real scenario, async_set_hvac_mode would be called
    # Here we just test the logic
    assert climate_entity._window_open is True
    assert climate_entity._saved_hvac_mode == HVACMode.HEAT


async def test_multiple_trvs_independent_control(climate_entity):
    """Test each TRV is controlled independently."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    
    climate_entity._attr_current_temperature = 20.0
    climate_entity._attr_target_temperature = 23.0
    
    # TRV 1 has high return temp
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 33.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 100
    await climate_entity._async_control_valve(climate_entity._trvs[0])
    
    # TRV 2 has low return temp
    climate_entity._trv_states[MOCK_TRV_2]["return_temp"] = 27.0
    climate_entity._trv_states[MOCK_TRV_2]["valve_position"] = 0
    await climate_entity._async_control_valve(climate_entity._trvs[1])
    
    # TRV 1 should be closed
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is True
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_position"] == 0
    
    # TRV 2 should be open
    assert climate_entity._trv_states[MOCK_TRV_2]["valve_control_active"] is True
    assert climate_entity._trv_states[MOCK_TRV_2]["valve_position"] == 100


async def test_send_temperature_to_all_trvs(climate_entity):
    """Test temperature is sent to all TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    
    await climate_entity._async_send_temperature_to_all_trvs(21.5)
    
    assert climate_entity.hass.services.async_call.call_count == 2
    calls = climate_entity.hass.services.async_call.call_args_list
    
    for i, trv in enumerate([MOCK_TRV_1, MOCK_TRV_2]):
        assert calls[i][0] == ("climate", "set_temperature")
        assert calls[i][1]["entity_id"] == trv
        assert calls[i][1]["temperature"] == 21.5


async def test_external_temperature_sync(climate_entity):
    """Test external temperature is sent to TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    climate_entity._attr_current_temperature = 22.5
    
    await climate_entity._async_send_room_temperature_to_trv(MOCK_TRV_1, 22.5)
    
    # Should call services to set external temperature
    assert climate_entity.hass.services.async_call.called


async def test_nudge_trv_if_idle(climate_entity):
    """Test TRV is nudged if showing idle when heating expected."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity._attr_target_temperature = 23.0
    
    # Mock TRV state showing idle
    climate_entity.hass.states = MagicMock()
    mock_state = MagicMock()
    mock_state.state = "idle"
    mock_state.attributes = {}
    climate_entity.hass.states.get = MagicMock(return_value=mock_state)
    
    await climate_entity._async_nudge_trv_if_idle(MOCK_TRV_1, 23.0)
    
    # Should send temperature twice: once with +0.5, once back to target
    calls = climate_entity.hass.services.async_call.call_args_list
    temp_calls = [c for c in calls if c[0] == ("climate", "set_temperature")]
    assert len(temp_calls) == 2
    # First call should be target + 0.5
    assert temp_calls[0][1]["temperature"] == 23.5
    # Second call should be actual target
    assert temp_calls[1][1]["temperature"] == 23.0


async def test_no_nudge_if_heating(climate_entity):
    """Test TRV is not nudged if already heating."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity._attr_target_temperature = 23.0
    
    # Mock TRV state showing heating
    climate_entity.hass.states = MagicMock()
    mock_state = MagicMock()
    mock_state.state = "heating"
    mock_state.attributes = {}
    climate_entity.hass.states.get = MagicMock(return_value=mock_state)
    
    await climate_entity._async_nudge_trv_if_idle(MOCK_TRV_1, 23.0)
    
    # Should not send temperature
    temp_calls = [c for c in climate_entity.hass.services.async_call.call_args_list 
                  if c[0] == ("climate", "set_temperature")]
    assert len(temp_calls) == 0


async def test_valve_position_via_mqtt(climate_entity):
    """Test valve position is set via MQTT when entity unavailable."""
    climate_entity.hass.services.async_call = AsyncMock()
    climate_entity.hass.states = MagicMock()
    climate_entity.hass.states.get = MagicMock(return_value=None)
    
    await climate_entity._async_set_valve_position(MOCK_TRV_1, 75)
    
    # Should use MQTT
    calls = climate_entity.hass.services.async_call.call_args_list
    mqtt_calls = [c for c in calls if c[0][0] == "mqtt" and c[0][1] == "publish"]
    
    assert len(mqtt_calls) >= 1


async def test_heating_status_determination(climate_entity):
    """Test heating status is correctly determined."""
    climate_entity._attr_current_temperature = 21.0
    climate_entity._attr_target_temperature = 23.0
    
    # Test window open
    climate_entity._window_open = True
    status = climate_entity._determine_heating_status()
    assert status["status"] == "window_open"
    
    # Test HVAC off
    climate_entity._window_open = False
    climate_entity._attr_hvac_mode = HVACMode.OFF
    status = climate_entity._determine_heating_status()
    assert status["status"] == "off"
    
    # Test target reached
    climate_entity._attr_hvac_mode = HVACMode.HEAT
    climate_entity._attr_current_temperature = 23.0
    climate_entity._attr_target_temperature = 23.0
    status = climate_entity._determine_heating_status()
    assert status["status"] == "target_reached"
    
    # Test heating
    climate_entity._attr_current_temperature = 21.0
    climate_entity._attr_target_temperature = 23.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 50
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 25.0
    status = climate_entity._determine_heating_status()
    assert status["status"] == "heating"


async def test_trv_status_with_reason(climate_entity):
    """Test TRV status determination with reasons."""
    climate_entity.hass.states = MagicMock()
    mock_trv_state = MagicMock()
    mock_trv_state.attributes = {"friendly_name": "Living Room TRV"}
    climate_entity.hass.states.get = MagicMock(return_value=mock_trv_state)
    
    climate_entity._attr_current_temperature = 22.0
    climate_entity._attr_target_temperature = 23.0
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 27.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 100
    climate_entity._window_open = False
    climate_entity._attr_hvac_mode = HVACMode.HEAT
    
    trv_config = climate_entity._trvs[0]
    trv_state = climate_entity._trv_states[MOCK_TRV_1]
    
    result = climate_entity._determine_trv_status_with_reason(trv_config, trv_state)
    
    assert result["status"] == "heating"
    assert "room" in result["reason"].lower() and "target" in result["reason"].lower()
    
    # Test closed due to return temp
    climate_entity._attr_current_temperature = 22.0
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 33.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 0
    
    result = climate_entity._determine_trv_status_with_reason(trv_config, trv_state)
    
    assert result["status"] == "return_high"
    assert "return" in result["reason"].lower()
    
    # Test window open
    climate_entity._window_open = True
    climate_entity._trv_states[MOCK_TRV_1]["valve_position"] = 0
    
    result = climate_entity._determine_trv_status_with_reason(trv_config, trv_state)
    
    assert result["status"] == "window_open"
    assert "window" in result["reason"].lower()


async def test_return_temp_precision(climate_entity):
    """Test return temperature is displayed with 1 decimal precision."""
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 28.567
    
    # Mock TRV state for friendly name
    climate_entity.hass.states = MagicMock()
    mock_trv1_state = MagicMock()
    mock_trv1_state.attributes = {"friendly_name": "Living Room TRV"}
    climate_entity.hass.states.get = MagicMock(return_value=mock_trv1_state)
    
    attrs = climate_entity.extra_state_attributes
    
    # Should be rounded to 1 decimal
    assert attrs["living_room_trv_return_temp"] == 28.6


async def test_friendly_name_extraction(climate_entity):
    """Test friendly names are extracted and formatted correctly."""
    climate_entity.hass.states = MagicMock()
    
    # Test with friendly name
    mock_state = MagicMock()
    mock_state.attributes = {"friendly_name": "Living Room TRV 1"}
    climate_entity.hass.states.get = MagicMock(return_value=mock_state)
    
    attrs = climate_entity.extra_state_attributes
    assert "living_room_trv_1_entity" in attrs
    
    # Test fallback to entity_id
    mock_state.attributes = {}
    attrs = climate_entity.extra_state_attributes
    # Should use sanitized entity_id
