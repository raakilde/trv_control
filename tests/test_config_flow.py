"""Tests for TRV Control config flow."""
import pytest
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.trv_control.const import (
    DOMAIN,
    CONF_ROOMS,
    CONF_ROOM_NAME,
    CONF_TEMP_SENSOR,
    CONF_TRVS,
    CONF_TRV,
    CONF_RETURN_TEMP,
    CONF_WINDOW_SENSOR,
)
from .const import (
    MOCK_TEMP_SENSOR,
    MOCK_TRV_1,
    MOCK_RETURN_TEMP_1,
    MOCK_WINDOW_SENSOR,
)


async def test_form(hass):
    """Test we get the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_single_instance(hass, mock_config_entry):
    """Test only one instance is allowed."""
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_add_room(hass, mock_config_entry):
    """Test adding a room through options flow."""
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_room"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_room"
    
    with patch.object(hass.config_entries, 'async_reload', return_value=AsyncMock()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_ROOM_NAME: "Test Room",
                CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
                CONF_WINDOW_SENSOR: MOCK_WINDOW_SENSOR,
            }
        )
    
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_options_flow_add_trv(hass, mock_config_entry):
    """Test adding a TRV to a room through options flow."""
    # Set up a config entry with one room
    entry_data = {
        CONF_ROOMS: [
            {
                CONF_ROOM_NAME: "Test Room",
                CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
                CONF_TRVS: [],
            }
        ]
    }
    mock_config_entry.data = entry_data
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    
    # Select manage_room
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "manage_room"}
    )
    
    # Select the room
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"room": "Test Room"}
    )
    assert result["type"] == FlowResultType.MENU
    
    # Select add_trv
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_trv"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "add_trv"
    
    # Add the TRV
    with patch.object(hass.config_entries, 'async_reload', return_value=AsyncMock()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_TRV: MOCK_TRV_1,
                CONF_RETURN_TEMP: MOCK_RETURN_TEMP_1,
            }
        )
    
    assert result["type"] == FlowResultType.CREATE_ENTRY


async def test_options_flow_room_exists(hass, mock_config_entry):
    """Test error when room already exists."""
    entry_data = {
        CONF_ROOMS: [
            {
                CONF_ROOM_NAME: "Existing Room",
                CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
                CONF_TRVS: [],
            }
        ]
    }
    mock_config_entry.data = entry_data
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "add_room"}
    )
    
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_ROOM_NAME: "Existing Room",
            CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
        }
    )
    
    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "room_exists"


async def test_options_flow_edit_trv_selection(hass, mock_config_entry):
    """Test selecting a TRV to edit."""
    entry_data = {
        CONF_ROOMS: [
            {
                CONF_ROOM_NAME: "Test Room",
                CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
                CONF_TRVS: [
                    {
                        CONF_TRV: MOCK_TRV_1,
                        CONF_RETURN_TEMP: MOCK_RETURN_TEMP_1,
                        "max_valve_position": 100,
                        "close_threshold": 32.0,
                        "reopen_threshold": 28.0,
                    }
                ],
            }
        ]
    }
    mock_config_entry.options = entry_data
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    
    # Navigate to manage_room
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "manage_room"}
    )
    
    # Select the room
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"room": "Test Room"}
    )
    
    # Select edit_trv
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "edit_trv"}
    )
    
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_trv"
    # Should show TRV selection
    assert "trv_to_edit" in result["data_schema"].schema


async def test_options_flow_edit_trv_modify(hass, mock_config_entry):
    """Test modifying TRV settings."""
    entry_data = {
        CONF_ROOMS: [
            {
                CONF_ROOM_NAME: "Test Room",
                CONF_TEMP_SENSOR: MOCK_TEMP_SENSOR,
                CONF_TRVS: [
                    {
                        CONF_TRV: MOCK_TRV_1,
                        CONF_RETURN_TEMP: MOCK_RETURN_TEMP_1,
                        "max_valve_position": 100,
                        "close_threshold": 32.0,
                        "reopen_threshold": 28.0,
                    }
                ],
            }
        ]
    }
    mock_config_entry.options = entry_data
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    
    # Navigate to edit_trv
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "manage_room"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"room": "Test Room"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "edit_trv"}
    )
    
    # Select TRV to edit
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"trv_to_edit": MOCK_TRV_1}
    )
    
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "edit_trv"
    # Should show TRV settings form
    
    # Modify settings
    with patch.object(hass.config_entries, 'async_reload', return_value=AsyncMock()):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "max_valve_position": 80,
                "close_threshold": 30.0,
                "reopen_threshold": 26.0,
            }
        )
    
    assert result["type"] == FlowResultType.CREATE_ENTRY
    
    # Verify settings were saved
    updated_rooms = mock_config_entry.options.get(CONF_ROOMS, [])
    assert len(updated_rooms) == 1
    assert len(updated_rooms[0][CONF_TRVS]) == 1
    updated_trv = updated_rooms[0][CONF_TRVS][0]
    assert updated_trv["max_valve_position"] == 80
    assert updated_trv["close_threshold"] == 30.0
    assert updated_trv["reopen_threshold"] == 26.0


async def test_options_flow_no_rooms_for_edit(hass, mock_config_entry):
    """Test abort when no rooms exist for editing TRVs."""
    entry_data = {CONF_ROOMS: []}
    mock_config_entry.options = entry_data
    mock_config_entry.add_to_hass(hass)
    
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    
    # Try to edit TRV
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"next_step_id": "manage_room"}
    )
    
    # Should abort since no rooms exist
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_rooms"
