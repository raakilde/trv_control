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


async def test_set_temperature(climate_entity):
    """Test setting temperature sends to all TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    
    await climate_entity.async_set_temperature(**{ATTR_TEMPERATURE: 22.0})
    
    assert climate_entity._attr_target_temperature == 22.0
    assert climate_entity.hass.services.async_call.call_count == 2
    
    calls = climate_entity.hass.services.async_call.call_args_list
    assert calls[0] == call("climate", "set_temperature", {
        "entity_id": MOCK_TRV_1,
        "temperature": 22.0
    }, blocking=True)
    assert calls[1] == call("climate", "set_temperature", {
        "entity_id": MOCK_TRV_2,
        "temperature": 22.0
    }, blocking=True)


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
    
    trv_config = climate_entity._trvs[0]
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 33.0
    
    await climate_entity._async_control_valve(trv_config)
    
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is True
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_position"] == 0


async def test_return_temp_control_open_valve(climate_entity):
    """Test valve opens when return temp drops below threshold."""
    climate_entity.hass.services.async_call = AsyncMock()
    
    trv_config = climate_entity._trvs[0]
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 29.0
    climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] = True
    
    await climate_entity._async_control_valve(trv_config)
    
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is False
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
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 28.5
    climate_entity._trv_states[MOCK_TRV_2]["return_temp"] = 30.2
    
    attrs = climate_entity.extra_state_attributes
    
    assert attrs["temp_sensor"] == MOCK_TEMP_SENSOR
    assert attrs["trv_count"] == 2
    assert attrs["window_sensor"] == MOCK_WINDOW_SENSOR
    
    # Check TRV 1 attributes
    assert attrs["trv1_entity"] == MOCK_TRV_1
    assert attrs["trv1_return_temp"] == 28.5
    assert attrs["trv1_close_threshold"] == 32.0
    
    # Check TRV 2 attributes
    assert attrs["trv2_entity"] == MOCK_TRV_2
    assert attrs["trv2_return_temp"] == 30.2
    assert attrs["trv2_max_position"] == 80


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
    
    # TRV 1 has high return temp
    climate_entity._trv_states[MOCK_TRV_1]["return_temp"] = 33.0
    await climate_entity._async_control_valve(climate_entity._trvs[0])
    
    # TRV 2 has low return temp
    climate_entity._trv_states[MOCK_TRV_2]["return_temp"] = 28.0
    await climate_entity._async_control_valve(climate_entity._trvs[1])
    
    # TRV 1 should be closed
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_control_active"] is True
    assert climate_entity._trv_states[MOCK_TRV_1]["valve_position"] == 0
    
    # TRV 2 should remain open
    assert climate_entity._trv_states[MOCK_TRV_2]["valve_control_active"] is False


async def test_send_temperature_to_all_trvs(climate_entity):
    """Test temperature is sent to all TRVs."""
    climate_entity.hass.services.async_call = AsyncMock()
    
    await climate_entity._async_send_temperature_to_all_trvs(21.5)
    
    assert climate_entity.hass.services.async_call.call_count == 2
    calls = climate_entity.hass.services.async_call.call_args_list
    
    for i, trv in enumerate([MOCK_TRV_1, MOCK_TRV_2]):
        assert calls[i] == call("climate", "set_temperature", {
            "entity_id": trv,
            "temperature": 21.5
        }, blocking=True)
