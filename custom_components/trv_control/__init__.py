"""The TRV Control integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_SET_VALVE_POSITION,
    SERVICE_SET_TRV_THRESHOLDS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE]

SET_VALVE_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required("trv_entity_id"): cv.entity_id,
        vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
    }
)

SET_TRV_THRESHOLDS_SCHEMA = vol.Schema(
    {
        vol.Required("trv_entity_id"): cv.entity_id,
        vol.Optional("close_threshold"): vol.Coerce(float),
        vol.Optional("open_threshold"): vol.Coerce(float),
        vol.Optional("max_valve_position"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TRV Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register update listener for options changes
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    async def async_set_valve_position(call):
        """Handle set valve position service."""
        trv_entity_id = call.data["trv_entity_id"]
        position = call.data["position"]
        
        # Get target entity from service call
        entity_ids = call.context.target_list if hasattr(call.context, 'target_list') else []
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return
        
        # Find the climate entity
        for entity in hass.data["climate"].entities:
            if entity.entity_id in entity_ids and hasattr(entity, "async_set_valve_position"):
                await entity.async_set_valve_position(trv_entity_id, position)
                break

    async def async_set_trv_thresholds(call):
        """Handle set TRV thresholds service."""
        trv_entity_id = call.data["trv_entity_id"]
        close_threshold = call.data.get("close_threshold")
        open_threshold = call.data.get("open_threshold")
        max_valve_position = call.data.get("max_valve_position")
        
        # Get target entity from service call
        entity_ids = call.context.target_list if hasattr(call.context, 'target_list') else []
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return
        
        # Find the climate entity
        for entity in hass.data["climate"].entities:
            if entity.entity_id in entity_ids and hasattr(entity, "async_set_trv_thresholds"):
                await entity.async_set_trv_thresholds(
                    trv_entity_id, close_threshold, open_threshold, max_valve_position
                )
                break

    # Register services
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_VALVE_POSITION,
        async_set_valve_position,
        schema=SET_VALVE_POSITION_SCHEMA,
    )
    
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TRV_THRESHOLDS,
        async_set_trv_thresholds,
        schema=SET_TRV_THRESHOLDS_SCHEMA,
    )

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
