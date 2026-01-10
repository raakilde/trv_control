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
    SERVICE_SET_RETURN_THRESHOLDS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE]

SET_VALVE_POSITION_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
    }
)

SET_RETURN_THRESHOLDS_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("close_temp"): vol.Coerce(float),
        vol.Optional("open_temp"): vol.Coerce(float),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TRV Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_set_valve_position(call):
        """Handle set valve position service."""
        entity_id = call.data["entity_id"]
        position = call.data["position"]
        
        # Find the climate entity
        for entity in hass.data["climate"].entities:
            if entity.entity_id == entity_id and hasattr(entity, "async_set_valve_position"):
                await entity.async_set_valve_position(position)
                break

    async def async_set_return_thresholds(call):
        """Handle set return thresholds service."""
        entity_id = call.data["entity_id"]
        close_temp = call.data.get("close_temp")
        open_temp = call.data.get("open_temp")
        
        # Find the climate entity
        for entity in hass.data["climate"].entities:
            if entity.entity_id == entity_id and hasattr(entity, "async_set_return_thresholds"):
                await entity.async_set_return_thresholds(close_temp, open_temp)
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
        SERVICE_SET_RETURN_THRESHOLDS,
        async_set_return_thresholds,
        schema=SET_RETURN_THRESHOLDS_SCHEMA,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
