"""Config flow for TRV Control integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector

from .const import (
    CONF_ANTICIPATORY_OFFSET,
    CONF_MAX_VALVE_POSITION,
    CONF_RETURN_TEMP,
    CONF_RETURN_TEMP_CLOSE,
    CONF_RETURN_TEMP_OPEN,
    CONF_ROOM_NAME,
    CONF_ROOMS,
    CONF_TEMP_SENSOR,
    CONF_TRV,
    CONF_TRVS,
    CONF_WINDOW_SENSOR,
    DEFAULT_ANTICIPATORY_OFFSET,
    DEFAULT_MAX_VALVE_POSITION,
    DEFAULT_RETURN_TEMP_CLOSE,
    DEFAULT_RETURN_TEMP_OPEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def get_room_schema() -> vol.Schema:
    """Get schema for adding a room."""
    return vol.Schema(
        {
            vol.Required(CONF_ROOM_NAME): str,
            vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="binary_sensor", device_class=["window", "door", "opening"]
                )
            ),
        }
    )


def get_trv_schema() -> vol.Schema:
    """Get schema for adding a TRV to a room."""
    return vol.Schema(
        {
            vol.Required(CONF_TRV): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            vol.Required(CONF_RETURN_TEMP): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Optional(
                CONF_RETURN_TEMP_CLOSE, default=DEFAULT_RETURN_TEMP_CLOSE
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=20, max=80, step=0.5, unit_of_measurement="°C"
                )
            ),
            vol.Optional(
                CONF_RETURN_TEMP_OPEN, default=DEFAULT_RETURN_TEMP_OPEN
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=20, max=80, step=0.5, unit_of_measurement="°C"
                )
            ),
            vol.Optional(
                CONF_MAX_VALVE_POSITION, default=DEFAULT_MAX_VALVE_POSITION
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=1, unit_of_measurement="%"
                )
            ),
            vol.Optional(
                CONF_ANTICIPATORY_OFFSET, default=DEFAULT_ANTICIPATORY_OFFSET
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2.0, step=0.1, unit_of_measurement="°C", mode="box"
                )
            ),
            vol.Optional(
                "proportional_band", default=DEFAULT_PROPORTIONAL_BAND
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=10, step=0.1, unit_of_measurement="°C", mode="box"
                )
            ),
            vol.Optional(
                "pid_anticipatory_offset", default=DEFAULT_ANTICIPATORY_OFFSET
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2.0, step=0.1, unit_of_measurement="°C", mode="box"
                )
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
        super().__init__()
        self._config_entry = config_entry
        self._selected_room: str | None = None

    @property
    def config_entry(self) -> config_entries.ConfigEntry:
        """Return the config entry."""
        return self._config_entry

    def _get_rooms(self) -> list:
        """Get rooms from options or data."""
        # Always prefer options if available
        if CONF_ROOMS in self.config_entry.options:
            return self.config_entry.options[CONF_ROOMS]
        # Fall back to data
        return self.config_entry.data.get(CONF_ROOMS, [])

    def _save_rooms(self, rooms: list) -> None:
        """Save rooms to options."""
        _LOGGER.debug("Saving %d rooms to config entry options", len(rooms))
        # Make a deep copy to avoid reference issues
        rooms_copy = [dict(room) for room in rooms]
        for room in rooms_copy:
            if CONF_TRVS in room:
                room[CONF_TRVS] = [dict(trv) for trv in room[CONF_TRVS]]

        _LOGGER.debug("Calling async_update_entry with %d rooms", len(rooms_copy))
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, CONF_ROOMS: rooms_copy},
        )
        _LOGGER.debug(
            "Config entry updated - options now has %d rooms",
            len(self.config_entry.options.get(CONF_ROOMS, [])),
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_room", "manage_room", "remove_room", "list_rooms"],
        )

    async def async_step_add_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                rooms = self._get_rooms()
                room_name = user_input[CONF_ROOM_NAME]

                # Check if room already exists
                if any(room[CONF_ROOM_NAME] == room_name for room in rooms):
                    errors["base"] = "room_exists"
                else:
                    # Add the new room with empty TRV list
                    room_config = {
                        CONF_ROOM_NAME: room_name,
                        CONF_TEMP_SENSOR: user_input[CONF_TEMP_SENSOR],
                        CONF_WINDOW_SENSOR: user_input.get(CONF_WINDOW_SENSOR),
                        CONF_TRVS: [],  # Empty list of TRVs
                    }
                    rooms.append(room_config)

                    self._save_rooms(rooms)

                    # Schedule reload instead of awaiting it
                    self.hass.async_create_task(
                        self.hass.config_entries.async_reload(
                            self.config_entry.entry_id
                        )
                    )

                    return self.async_create_entry(title="", data={})

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_room",
            data_schema=get_room_schema(),
            errors=errors,
        )

    async def async_step_manage_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select a room to manage."""
        rooms = self._get_rooms()

        if not rooms:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            self._selected_room = user_input["room"]
            return await self.async_step_room_options()

        room_names = [room[CONF_ROOM_NAME] for room in rooms]

        return self.async_show_form(
            step_id="manage_room",
            data_schema=vol.Schema(
                {
                    vol.Required("room"): vol.In(room_names),
                }
            ),
        )

    async def async_step_room_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show room management options."""
        return self.async_show_menu(
            step_id="room_options",
            menu_options=["add_trv", "edit_trv", "remove_trv", "list_trvs"],
        )

    async def async_step_add_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a TRV to the selected room."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                rooms = self._get_rooms()

                # Find the selected room
                for room in rooms:
                    if room[CONF_ROOM_NAME] == self._selected_room:
                        trv_config = {
                            CONF_TRV: user_input[CONF_TRV],
                            CONF_RETURN_TEMP: user_input[CONF_RETURN_TEMP],
                            CONF_RETURN_TEMP_CLOSE: user_input.get(
                                CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
                            ),
                            CONF_RETURN_TEMP_OPEN: user_input.get(
                                CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN
                            ),
                            CONF_MAX_VALVE_POSITION: user_input.get(
                                CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                            ),
                            CONF_ANTICIPATORY_OFFSET: user_input.get(
                                CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                            ),
                        }

                        if CONF_TRVS not in room:
                            room[CONF_TRVS] = []

                        room[CONF_TRVS].append(trv_config)
                        break

                self._save_rooms(rooms)

                # Schedule reload instead of awaiting it
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )

                return self.async_create_entry(title="", data={})

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="add_trv",
            data_schema=get_trv_schema(),
            errors=errors,
            description_placeholders={"room_name": self._selected_room},
        )

    async def async_step_edit_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Edit TRV settings in the selected room."""
        rooms = self._get_rooms()

        # Find the selected room
        selected_room_config = None
        for room in rooms:
            if room[CONF_ROOM_NAME] == self._selected_room:
                selected_room_config = room
                break

        if not selected_room_config or not selected_room_config.get(CONF_TRVS):
            return self.async_abort(reason="no_trvs")

        # Step 1: Select which TRV to edit
        if not hasattr(self, "_selected_trv"):
            if user_input is not None:
                self._selected_trv = user_input["trv"]
                # Find the TRV config to get current values
                for trv in selected_room_config[CONF_TRVS]:
                    if trv[CONF_TRV] == self._selected_trv:
                        self._selected_trv_config = trv
                        break

                # Show edit form with current values
                return self.async_show_form(
                    step_id="edit_trv",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_RETURN_TEMP_CLOSE,
                                default=trv.get(
                                    CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=20, max=80, step=0.5, unit_of_measurement="°C"
                                )
                            ),
                            vol.Required(
                                CONF_RETURN_TEMP_OPEN,
                                default=trv.get(
                                    CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=20, max=80, step=0.5, unit_of_measurement="°C"
                                )
                            ),
                            vol.Required(
                                CONF_MAX_VALVE_POSITION,
                                default=trv.get(
                                    CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=0, max=100, step=1, unit_of_measurement="%"
                                )
                            ),
                            vol.Required(
                                CONF_ANTICIPATORY_OFFSET,
                                default=trv.get(
                                    CONF_ANTICIPATORY_OFFSET,
                                    DEFAULT_ANTICIPATORY_OFFSET,
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=0,
                                    max=2.0,
                                    step=0.1,
                                    unit_of_measurement="°C",
                                    mode="box",
                                )
                            ),
                        }
                    ),
                    description_placeholders={"room_name": self._selected_room},
                )

            # Show TRV selection list
            trv_ids = [trv[CONF_TRV] for trv in selected_room_config[CONF_TRVS]]

            return self.async_show_form(
                step_id="edit_trv",
                data_schema=vol.Schema(
                    {
                        vol.Required("trv"): vol.In(trv_ids),
                    }
                ),
                description_placeholders={"room_name": self._selected_room},
            )

        # Step 2: Save the edited values
        if user_input is not None:
            try:
                # Update the TRV config
                for trv in selected_room_config[CONF_TRVS]:
                    if trv[CONF_TRV] == self._selected_trv:
                        trv[CONF_RETURN_TEMP_CLOSE] = user_input.get(
                            CONF_RETURN_TEMP_CLOSE,
                            trv.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE),
                        )
                        trv[CONF_RETURN_TEMP_OPEN] = user_input.get(
                            CONF_RETURN_TEMP_OPEN,
                            trv.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN),
                        )
                        trv[CONF_MAX_VALVE_POSITION] = user_input.get(
                            CONF_MAX_VALVE_POSITION,
                            trv.get(
                                CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                            ),
                        )
                        trv[CONF_ANTICIPATORY_OFFSET] = user_input.get(
                            CONF_ANTICIPATORY_OFFSET,
                            trv.get(
                                CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                            ),
                        )
                        break

                self._save_rooms(rooms)

                # Clear selection for next time
                delattr(self, "_selected_trv")
                delattr(self, "_selected_trv_config")

                await self.hass.config_entries.async_reload(self.config_entry.entry_id)

                return self.async_create_entry(title="", data={})

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                # Clear selection
                if hasattr(self, "_selected_trv"):
                    delattr(self, "_selected_trv")
                if hasattr(self, "_selected_trv_config"):
                    delattr(self, "_selected_trv_config")
                return self.async_abort(reason="unknown")

    async def async_step_remove_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a TRV from the selected room."""
        rooms = self._get_rooms()

        # Find the selected room
        selected_room_config = None
        for room in rooms:
            if room[CONF_ROOM_NAME] == self._selected_room:
                selected_room_config = room
                break

        if not selected_room_config or not selected_room_config.get(CONF_TRVS):
            return self.async_abort(reason="no_trvs")

        if user_input is not None:
            trv_id = user_input["trv"]
            selected_room_config[CONF_TRVS] = [
                trv
                for trv in selected_room_config[CONF_TRVS]
                if trv[CONF_TRV] != trv_id
            ]

            self._save_rooms(rooms)

            await self.hass.config_entries.async_reload(self.config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        trv_ids = [trv[CONF_TRV] for trv in selected_room_config[CONF_TRVS]]

        return self.async_show_form(
            step_id="remove_trv",
            data_schema=vol.Schema(
                {
                    vol.Required("trv"): vol.In(trv_ids),
                }
            ),
            description_placeholders={"room_name": self._selected_room},
        )

    async def async_step_list_trvs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """List all TRVs in the selected room."""
        rooms = self._get_rooms()

        # Find the selected room
        selected_room_config = None
        for room in rooms:
            if room[CONF_ROOM_NAME] == self._selected_room:
                selected_room_config = room
                break

        if not selected_room_config or not selected_room_config.get(CONF_TRVS):
            return self.async_abort(reason="no_trvs")

        trv_list = "\n".join(
            [
                f"- {trv[CONF_TRV]} (Return: {trv[CONF_RETURN_TEMP]})"
                for trv in selected_room_config[CONF_TRVS]
            ]
        )

        return self.async_abort(
            reason="trvs_listed",
            description_placeholders={
                "trvs": trv_list,
                "room_name": self._selected_room,
            },
        )

    async def async_step_remove_room(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove a room."""
        rooms = self._get_rooms()

        if not rooms:
            return self.async_abort(reason="no_rooms")

        if user_input is not None:
            room_name = user_input["room"]
            _LOGGER.info("Removing room: %s", room_name)

            # Delete all entities from registry before removing the room
            entity_reg = er.async_get(self.hass)
            unique_id_prefix = (
                f"{self.config_entry.entry_id}_{room_name.lower().replace(' ', '_')}"
            )

            # Remove climate entity
            entity_id = entity_reg.async_get_entity_id(
                "climate", DOMAIN, unique_id_prefix
            )
            if entity_id:
                _LOGGER.info("Removing climate entity %s from registry", entity_id)
                entity_reg.async_remove(entity_id)

            # Remove all sensor entities for this room
            # Find all entities that start with the unique_id_prefix
            entities_to_remove = []
            for entity in entity_reg.entities.values():
                if (
                    entity.platform == DOMAIN
                    and entity.unique_id
                    and entity.unique_id.startswith(unique_id_prefix)
                ):
                    entities_to_remove.append(entity.entity_id)

            for entity_id in entities_to_remove:
                _LOGGER.info("Removing sensor entity %s from registry", entity_id)
                entity_reg.async_remove(entity_id)

            _LOGGER.info(
                "Removed %d entities for room %s",
                len(entities_to_remove) + 1,
                room_name,
            )

            rooms = [room for room in rooms if room[CONF_ROOM_NAME] != room_name]
            _LOGGER.info("Rooms after removal: %s", [r[CONF_ROOM_NAME] for r in rooms])

            self._save_rooms(rooms)

            # Reload integration to apply changes
            self.hass.async_create_task(
                self.hass.config_entries.async_reload(self.config_entry.entry_id)
            )

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
        rooms = self._get_rooms()

        if not rooms:
            return self.async_abort(reason="no_rooms")

        room_list = "\n".join([f"• {room[CONF_ROOM_NAME]}" for room in rooms])

        return self.async_abort(
            reason="rooms_listed", description_placeholders={"rooms": room_list}
        )
