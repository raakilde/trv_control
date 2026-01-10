"""Platform for climate integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform."""
    async_add_entities([TRVClimate(config_entry)])


class TRVClimate(ClimateEntity):
    """Representation of a TRV Climate device."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the climate device."""
        self._attr_unique_id = f"{config_entry.entry_id}_climate"
        self._attr_name = config_entry.data.get("name", "TRV")
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = 20.0
        self._attr_min_temp = 5.0
        self._attr_max_temp = 30.0
        self._attr_target_temperature_step = 0.5

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._attr_target_temperature = temperature
        # Add your logic to control the actual device here
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        self._attr_hvac_mode = hvac_mode
        # Add your logic to control the actual device here
        self.async_write_ha_state()
