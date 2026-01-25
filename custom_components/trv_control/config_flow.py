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
    CONF_PID_ANTICIPATORY_OFFSET,
    CONF_PROPORTIONAL_BAND,
    CONF_RETURN_TEMP,
    CONF_RETURN_TEMP_CLOSE,
    CONF_ROOM_NAME,
    CONF_TEMP_SENSOR,
    CONF_TRV,
    CONF_TRVS,
    CONF_WINDOW_SENSOR,
    DEFAULT_ANTICIPATORY_OFFSET,
    DEFAULT_MAX_VALVE_POSITION,
    DEFAULT_PROPORTIONAL_BAND,
    DEFAULT_RETURN_TEMP_CLOSE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


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
                CONF_PROPORTIONAL_BAND, default=DEFAULT_PROPORTIONAL_BAND
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.5, max=10, step=0.1, unit_of_measurement="°C", mode="box"
                )
            ),
            vol.Optional(
                CONF_PID_ANTICIPATORY_OFFSET, default=DEFAULT_ANTICIPATORY_OFFSET
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=2.0, step=0.1, unit_of_measurement="°C", mode="box"
                )
            ),
        }
    )


def get_trv_schema_multi() -> vol.Schema:
    """Get schema for adding TRVs with multi-TRV support."""
    base_schema = {
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
            CONF_PROPORTIONAL_BAND, default=DEFAULT_PROPORTIONAL_BAND
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0.5, max=10, step=0.1, unit_of_measurement="°C", mode="box"
            )
        ),
        vol.Optional(
            CONF_PID_ANTICIPATORY_OFFSET, default=DEFAULT_ANTICIPATORY_OFFSET
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=2.0, step=0.1, unit_of_measurement="°C", mode="box"
            )
        ),
    }

    # Add "add another TRV" option dynamically
    base_schema[vol.Optional("add_another", default=False)] = selector.BooleanSelector()

    return vol.Schema(base_schema)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TRV Control."""

    VERSION = 1

    def __init__(self):
        """Initialize flow."""
        self._room_data = {}
        self._trvs = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the room setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Store room data
            self._room_data = user_input
            room_name = user_input[CONF_ROOM_NAME]

            # Check for existing integration with same room name
            for entry in self._async_current_entries():
                if entry.title == f"{room_name} TRV Control":
                    errors["base"] = "room_exists"
                    break

            if not errors:
                # Move to TRV setup
                return await self.async_step_trv_setup()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ROOM_NAME): str,
                    vol.Required(CONF_TEMP_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                    vol.Optional(CONF_WINDOW_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="binary_sensor",
                            device_class=["window", "door", "opening"],
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_trv_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle TRV configuration step."""
        if user_input is not None:
            # Add TRV to list
            trv_data = {
                CONF_TRV: user_input[CONF_TRV],
                CONF_RETURN_TEMP: user_input[CONF_RETURN_TEMP],
                CONF_RETURN_TEMP_CLOSE: user_input.get(
                    CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
                ),
                CONF_MAX_VALVE_POSITION: user_input.get(
                    CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                ),
                CONF_ANTICIPATORY_OFFSET: user_input.get(
                    CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                ),
                CONF_PROPORTIONAL_BAND: user_input.get(
                    CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND
                ),
                CONF_PID_ANTICIPATORY_OFFSET: user_input.get(
                    CONF_PID_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                ),
            }
            self._trvs.append(trv_data)

            # Check if user wants to add more TRVs
            if user_input.get("add_another", False):
                return await self.async_step_trv_setup()

            # At least one TRV is required
            if not self._trvs:
                errors = {"base": "no_trvs"}
                return self.async_show_form(
                    step_id="trv_setup",
                    data_schema=get_trv_schema_multi(),
                    errors=errors,
                    description_placeholders={
                        "room_name": self._room_data[CONF_ROOM_NAME],
                        "trv_count": "1",
                    },
                )

            room_name = self._room_data[CONF_ROOM_NAME]

            # Create the integration entry
            return self.async_create_entry(
                title=f"{room_name} TRV Control",
                data={
                    **self._room_data,
                    CONF_TRVS: self._trvs,
                },
            )

        # Determine current TRV count for display
        trv_count = len(self._trvs)
        trv_text = f" (TRV {trv_count + 1})" if trv_count > 0 else ""

        return self.async_show_form(
            step_id="trv_setup",
            data_schema=get_trv_schema_multi(),
            description_placeholders={
                "room_name": self._room_data[CONF_ROOM_NAME],
                "trv_text": trv_text,
                "trv_count": str(trv_count + 1),
            },
        )

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
        self._room_name = config_entry.data.get(CONF_ROOM_NAME, "Room")
        self._current_trvs = config_entry.data.get(CONF_TRVS, [])

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options initialization."""
        if user_input is not None:
            selected = user_input["action"]
            if selected == "add_trv":
                return await self.async_step_add_trv()
            elif selected == "remove_trv":
                return await self.async_step_remove_trv()
            elif selected == "edit_trv":
                return await self.async_step_edit_trv()
            elif selected == "list_trvs":
                return await self.async_step_list_trvs()

        return self.async_show_menu(
            step_id="init",
            menu_options=["add_trv", "edit_trv", "remove_trv", "list_trvs"],
            description_placeholders={"room_name": self._room_name},
        )

    async def async_step_add_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a new TRV."""
        if user_input is not None:
            # Create new TRV config
            trv_data = {
                CONF_TRV: user_input[CONF_TRV],
                CONF_RETURN_TEMP: user_input[CONF_RETURN_TEMP],
                CONF_RETURN_TEMP_CLOSE: user_input.get(
                    CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
                ),
                CONF_MAX_VALVE_POSITION: user_input.get(
                    CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                ),
                CONF_ANTICIPATORY_OFFSET: user_input.get(
                    CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                ),
                CONF_PROPORTIONAL_BAND: user_input.get(
                    CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND
                ),
                CONF_PID_ANTICIPATORY_OFFSET: user_input.get(
                    CONF_PID_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
                ),
            }

            # Add to existing TRVs
            updated_trvs = self._current_trvs.copy()
            updated_trvs.append(trv_data)

            # Update config entry
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_TRVS: updated_trvs},
            )

            # Force reload
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="add_trv",
            data_schema=get_trv_schema(),
            description_placeholders={"room_name": self._room_name},
        )

    async def async_step_remove_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle removing a TRV."""
        if not self._current_trvs:
            return self.async_abort(reason="no_trvs")

        if user_input is not None:
            selected_trv = user_input[CONF_TRV]

            # Get entity registry to clean up sensor entities
            entity_registry = er.async_get(self.hass)

            # Find the TRV being removed to get its trv_name for sensor cleanup
            trv_to_remove = None
            trv_index = None
            for idx, trv in enumerate(self._current_trvs):
                if trv[CONF_TRV] == selected_trv:
                    trv_to_remove = trv
                    trv_index = idx
                    break

            if trv_to_remove:
                # Generate the same trv_name that was used when creating sensors
                trv_entity_id = selected_trv

                # Replicate the naming logic from sensor.py
                trv_name = f"TRV {trv_index + 1}"  # Default fallback

                if trv_entity_id:
                    # Try to get the actual entity name from Home Assistant
                    state = self.hass.states.get(trv_entity_id)
                    if state and hasattr(state, "attributes"):
                        # Use the friendly name directly
                        friendly_name = state.attributes.get("friendly_name", "")
                        if friendly_name:
                            trv_name = friendly_name
                        else:
                            # Fallback to entity name part
                            trv_name = (
                                trv_entity_id.replace("climate.", "")
                                .replace("_", " ")
                                .title()
                            )
                    else:
                        # Entity not found, use entity ID as name
                        trv_name = (
                            trv_entity_id.replace("climate.", "")
                            .replace("_", " ")
                            .title()
                        )

                # Build unique_id pattern for this TRV's sensors
                # The climate entity unique_id is: {config_entry.entry_id}_{room_name}
                climate_unique_id = f"{self._config_entry.entry_id}_{self._room_name.lower().replace(' ', '_')}"
                trv_unique_pattern = (
                    f"{climate_unique_id}_{trv_name.lower().replace(' ', '_')}_"
                )

                # Debug logging to see what we're looking for
                _LOGGER.info(
                    "Looking for sensor entities with pattern: %s", trv_unique_pattern
                )

                # Find and remove sensor entities associated with this specific TRV
                entities_to_remove = []
                for entity_id, entry in entity_registry.entities.items():
                    if (
                        entry.config_entry_id == self._config_entry.entry_id
                        and entry.platform == "sensor"
                        and entry.unique_id
                        and entry.unique_id.startswith(trv_unique_pattern)
                    ):
                        entities_to_remove.append(entity_id)
                        _LOGGER.info(
                            "Found sensor to remove: %s (unique_id: %s)",
                            entity_id,
                            entry.unique_id,
                        )

                # Remove the sensor entities
                for entity_id in entities_to_remove:
                    _LOGGER.info("Removing sensor entity: %s", entity_id)
                    entity_registry.async_remove(entity_id)

                if not entities_to_remove:
                    _LOGGER.warning(
                        "No sensor entities found to remove for TRV %s with pattern %s",
                        selected_trv,
                        trv_unique_pattern,
                    )
                    # List all sensor entities for this config entry for debugging
                    for entity_id, entry in entity_registry.entities.items():
                        if (
                            entry.config_entry_id == self._config_entry.entry_id
                            and entry.platform == "sensor"
                        ):
                            _LOGGER.debug(
                                "Available sensor: %s (unique_id: %s)",
                                entity_id,
                                entry.unique_id,
                            )

            # Remove the selected TRV from config
            updated_trvs = [
                trv for trv in self._current_trvs if trv[CONF_TRV] != selected_trv
            ]

            # Update config entry
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_TRVS: updated_trvs},
            )

            # Force reload
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data={})

        # Build list of TRV entity IDs for selection
        trv_entity_ids = [trv[CONF_TRV] for trv in self._current_trvs]

        return self.async_show_form(
            step_id="remove_trv",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRV): vol.In(trv_entity_ids),
                }
            ),
            description_placeholders={"room_name": self._room_name},
        )

    async def async_step_edit_trv(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle editing TRV settings."""
        if not self._current_trvs:
            return self.async_abort(reason="no_trvs")

        if user_input is not None:
            # Check if this is TRV selection or settings edit
            if CONF_TRV in user_input and len(user_input) == 1:
                # This is TRV selection step, show edit form with current values
                selected_trv = user_input[CONF_TRV]

                # Find the selected TRV config
                selected_trv_config = None
                for trv in self._current_trvs:
                    if trv[CONF_TRV] == selected_trv:
                        selected_trv_config = trv
                        break

                if not selected_trv_config:
                    return self.async_abort(reason="no_trvs")

                # Build form with current values
                return self.async_show_form(
                    step_id="edit_trv",
                    data_schema=vol.Schema(
                        {
                            vol.Required(CONF_TRV, default=selected_trv): vol.In(
                                [selected_trv]
                            ),
                            vol.Optional(
                                CONF_RETURN_TEMP_CLOSE,
                                default=selected_trv_config.get(
                                    CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=20, max=80, step=0.5, unit_of_measurement="°C"
                                )
                            ),
                            vol.Optional(
                                CONF_MAX_VALVE_POSITION,
                                default=selected_trv_config.get(
                                    CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=0, max=100, step=1, unit_of_measurement="%"
                                )
                            ),
                            vol.Optional(
                                CONF_ANTICIPATORY_OFFSET,
                                default=selected_trv_config.get(
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
                            vol.Optional(
                                CONF_PROPORTIONAL_BAND,
                                default=selected_trv_config.get(
                                    CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND
                                ),
                            ): selector.NumberSelector(
                                selector.NumberSelectorConfig(
                                    min=0.5,
                                    max=10,
                                    step=0.1,
                                    unit_of_measurement="°C",
                                    mode="box",
                                )
                            ),
                            vol.Optional(
                                CONF_PID_ANTICIPATORY_OFFSET,
                                default=selected_trv_config.get(
                                    CONF_PID_ANTICIPATORY_OFFSET,
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
                    description_placeholders={"room_name": self._room_name},
                )
            else:
                # This is settings update
                selected_trv = user_input[CONF_TRV]

                # Update the TRV settings
                updated_trvs = self._current_trvs.copy()
                for trv in updated_trvs:
                    if trv[CONF_TRV] == selected_trv:
                        # Update settings
                        trv[CONF_RETURN_TEMP_CLOSE] = user_input.get(
                            CONF_RETURN_TEMP_CLOSE,
                            trv.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE),
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
                        trv[CONF_PROPORTIONAL_BAND] = user_input.get(
                            CONF_PROPORTIONAL_BAND,
                            trv.get(CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND),
                        )
                        trv[CONF_PID_ANTICIPATORY_OFFSET] = user_input.get(
                            CONF_PID_ANTICIPATORY_OFFSET,
                            trv.get(
                                CONF_PID_ANTICIPATORY_OFFSET,
                                DEFAULT_ANTICIPATORY_OFFSET,
                            ),
                        )
                        break

                # Update config entry
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**self._config_entry.data, CONF_TRVS: updated_trvs},
                )

                # Force reload
                await self.hass.config_entries.async_reload(self._config_entry.entry_id)

                return self.async_create_entry(title="", data={})

        # Initial step: show TRV selection
        trv_entity_ids = [trv[CONF_TRV] for trv in self._current_trvs]

        return self.async_show_form(
            step_id="edit_trv",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRV): vol.In(trv_entity_ids),
                }
            ),
            description_placeholders={"room_name": self._room_name},
        )

    async def async_step_list_trvs(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """List all TRVs in the room."""
        if not self._current_trvs:
            return self.async_abort(reason="no_trvs")

        trv_list = "\n".join([f"• {trv[CONF_TRV]}" for trv in self._current_trvs])

        return self.async_abort(
            reason="trvs_listed",
            description_placeholders={
                "room_name": self._room_name,
                "trvs": trv_list,
            },
        )
