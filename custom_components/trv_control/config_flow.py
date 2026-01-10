"""Config flow for TRV Control integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_ROOMS,
    CONF_ROOM_NAME,
    CONF_TEMP_SENSOR,
    CONF_TRV,
    CONF_RETURN_TEMP,
    CONF_WINDOW_SENSOR,
    CONF_RETURN_TEMP_CLOSE,
    CONF_RETURN_TEMP_OPEN,
    CONF_MAX_VALVE_POSITION,
    DEFAULT_RETURN_TEMP_CLOSE,
    DEFAULT_RETURN_TEMP_OPEN,
    DEFAULT_MAX_VALVE_POSITION,
)

_LOGGER = logging.getLogger(__name__)

def get_room_schema(existing_rooms: list[str] | None = None) -> vol.Schema:
    """Get schema for adding a room."""
    existing_rooms = existing_rooms or []
    return vol.Schema(
        {
            vol.Required(CONF_ROOM_NAME): str,
            vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_TRV): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Required(CONF_RETURN_TEMP): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="binary_sensor", device_class="window")
            ),
            vol.Optional(CONF_RETURN_TEMP_CLOSE, default=DEFAULT_RETURN_TEMP_CLOSE): selector.NumberSelector(
                selector.NumberSelectorConfig(min=20, max=80, step=0.5, unit_of_measurement="°C")
            ),
            vol.Optional(CONF_RETURN_TEMP_OPEN, default=DEFAULT_RETURN_TEMP_OPEN): selector.NumberSelector(
                selector.NumberSelectorConfig(min=20, max=80, step=0.5, unit_of_measurement="°C")
            ),
            vol.Optional(CONF_MAX_VALVE_POSITION, default=DEFAULT_MAX_VALVE_POSITION): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="%")
            ),
        }
    )


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TRV Control."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Create the main integration entry with no rooms initially
            return self.async_create_entry(
                title="TRV Control",
                data={CONF_ROOMS: []},
            )

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for TRV Control."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._room_to_edit: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_room", "remove_room", "list_rooms"],
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                rooms = self.config_entry.data.get(CONF_ROOMS, [])
                room_name = user_input[CONF_ROOM_NAME]
                
                # Check if room already exists
                if any(room[CONF_ROOM_NAME] == room_name for room in rooms):
                    errors["base"] = "room_exists"
                else:
                    # Add the new room
                    rooms.append(user_input)
                    
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={CONF_ROOMS: rooms},
                    )
                    
                    await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                    
                    return self.async_create_entry(title="", data={})
                    
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        existing_rooms = [room[CONF_ROOM_NAME] for room in self.config_entry.data.get(CONF_ROOMS, [])]
        return self.async_show_form(
            step_id="add_room",
            data_schema=get_room_schema(existing_rooms),
            errors=errors,
        )

    async def async_step_remove_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a room."""
        rooms = self.config_entry.data.get(CONF_ROOMS, [])
        
        if not rooms:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            room_name = user_input["room"]
            rooms = [room for room in rooms if room[CONF_ROOM_NAME] != room_name]
            
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={CONF_ROOMS: rooms},
            )
            
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            
            return self.async_create_entry(title="", data={})

        room_names = [room[CONF_ROOM_NAME] for room in rooms]
        
        return self.async_show_form(
            step_id="remove_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): vol.In(room_names),
                }
            ),
        )

    async def async_step_list_rooms(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """List all configured rooms."""
        rooms = self.config_entry.data.get(CONF_ROOMS, [])
        
        if not rooms:
            return self.async_abort(reason="no_rooms")
        
        room_list = "\n".join([f"• {room[CONF_ROOM_NAME]}" for room in rooms])
        
        return self.async_abort(reason="rooms_listed", description_placeholders={"rooms": room_list})
