"""The TRV Control integration."""

from __future__ import annotations

import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SERVICE_RESET_PERFORMANCE_STATS,
    SERVICE_SET_TRV_THRESHOLDS,
    SERVICE_SET_VALVE_POSITION,
    SERVICE_VALIDATE_TRVS,
    SERVICE_FORCE_VALVE_CONTROL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR]

SET_VALVE_POSITION_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Required("trv_entity_id"): cv.entity_id,
        vol.Required("position"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
    },
    extra=vol.ALLOW_EXTRA,
)

SET_TRV_THRESHOLDS_SCHEMA = vol.Schema(
    {
        vol.Optional("entity_id"): cv.entity_ids,
        vol.Required("trv_entity_id"): cv.entity_id,
        vol.Optional("close_threshold"): vol.Coerce(float),
        vol.Optional("open_threshold"): vol.Coerce(float),
        vol.Optional("max_valve_position"): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TRV Control from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def async_set_valve_position(call):
        """Handle set valve position service."""
        trv_entity_id = call.data["trv_entity_id"]
        position = call.data["position"]

        # Get target entity from service call data
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            entity_ids = (
                call.context.target_list if hasattr(call.context, "target_list") else []
            )
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return

        # Ensure entity_ids is a list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        # Find the climate entity using component helper
        component = hass.data.get("entity_components", {}).get("climate")
        if not component:
            _LOGGER.error("Climate component not found")
            return

        for entity_id in entity_ids:
            entity = component.get_entity(entity_id)
            if entity and hasattr(entity, "async_set_valve_position"):
                await entity.async_set_valve_position(trv_entity_id, position)
                return

    async def async_set_trv_thresholds(call):
        """Handle set TRV thresholds service."""
        trv_entity_id = call.data["trv_entity_id"]
        close_threshold = call.data.get("close_threshold")
        open_threshold = call.data.get("open_threshold")
        max_valve_position = call.data.get("max_valve_position")

        _LOGGER.info(
            "Service called: trv=%s, close=%s, open=%s, max=%s",
            trv_entity_id,
            close_threshold,
            open_threshold,
            max_valve_position,
        )

        # Get target entity from service call data
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            entity_ids = (
                call.context.target_list if hasattr(call.context, "target_list") else []
            )
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return

        # Ensure entity_ids is a list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        _LOGGER.info("Target entities: %s", entity_ids)

        # Find the climate entity using component helper
        component = hass.data.get("entity_components", {}).get("climate")
        if not component:
            _LOGGER.error("Climate component not found")
            return

        for entity_id in entity_ids:
            entity = component.get_entity(entity_id)
            if entity and hasattr(entity, "async_set_trv_thresholds"):
                _LOGGER.info(
                    "Found entity %s, calling async_set_trv_thresholds", entity_id
                )
                await entity.async_set_trv_thresholds(
                    trv_entity_id, close_threshold, open_threshold, max_valve_position
                )
                return

        _LOGGER.error("No matching climate entity found in %s", entity_ids)

    async def async_reset_performance_stats(call):
        """Handle reset performance statistics service."""
        # Get target entity from service call data
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            entity_ids = (
                call.context.target_list if hasattr(call.context, "target_list") else []
            )
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return

        # Ensure entity_ids is a list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        # Find the climate entity using component helper
        component = hass.data.get("entity_components", {}).get("climate")
        if not component:
            _LOGGER.error("Climate component not found")
            return

        for entity_id in entity_ids:
            entity = component.get_entity(entity_id)
            if entity and hasattr(entity, "async_reset_performance_stats"):
                await entity.async_reset_performance_stats()
                _LOGGER.info("Reset performance statistics for %s", entity_id)
                return

        _LOGGER.error("No matching climate entity found in %s", entity_ids)

    async def async_validate_trvs(call):
        """Handle validate TRVs service."""
        # Get target entity from service call data
        entity_ids = call.data.get("entity_id")
        if not entity_ids:
            entity_ids = (
                call.context.target_list if hasattr(call.context, "target_list") else []
            )
        if not entity_ids:
            _LOGGER.error("No target entity specified")
            return

        # Ensure entity_ids is a list
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]

        # Find the climate entity using component helper
        component = hass.data.get("entity_components", {}).get("climate")
        if not component:
            _LOGGER.error("Climate component not found")
            return

        for entity_id in entity_ids:
            entity = component.get_entity(entity_id)
            if entity and hasattr(entity, "async_validate_all_trvs"):
                validation_summary = await entity.async_validate_all_trvs()
                _LOGGER.info(
                    "TRV validation completed for %s: %s", entity_id, validation_summary
                )
                return

        _LOGGER.error("No matching climate entity found in %s", entity_ids)

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_PERFORMANCE_STATS,
        async_reset_performance_stats,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_VALIDATE_TRVS,
        async_validate_trvs,
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Safely remove from hass.data if it exists
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
