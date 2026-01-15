"""Sensor platform for TRV Control integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up TRV Control sensors from a config entry."""
    climate_entity_id = f"climate.{config_entry.data['name'].lower().replace(' ', '_')}"
    
    # Wait for climate entity to be ready
    await hass.async_block_till_done()
    
    # Get the climate entity
    climate_entity = None
    for entity in hass.data[DOMAIN].values():
        if hasattr(entity, 'entity_id') and entity.entity_id == climate_entity_id:
            climate_entity = entity
            break
    
    if not climate_entity:
        _LOGGER.warning("Could not find climate entity %s for sensors", climate_entity_id)
        return
    
    sensors = []
    
    # Add sensors for each TRV
    for idx, trv in enumerate(climate_entity._trvs):
        trv_name = trv.get('name', f"TRV {idx + 1}")
        base_name = config_entry.data['name']
        
        sensors.extend([
            TRVValvePositionSensor(climate_entity, trv, base_name, trv_name),
            TRVReturnTempSensor(climate_entity, trv, base_name, trv_name),
        ])
    
    # Add overall control sensors
    sensors.extend([
        HeatingStatusSensor(climate_entity, config_entry.data['name']),
        TargetTempDifferenceSensor(climate_entity, config_entry.data['name']),
    ])
    
    async_add_entities(sensors)


class TRVControlSensorBase(SensorEntity):
    """Base class for TRV Control sensors."""
    
    _attr_should_poll = False
    
    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        self._climate_entity = climate_entity
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, climate_entity.unique_id)},
            "name": climate_entity.name,
        }
    
    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        @callback
        def _update(event=None):
            self.async_schedule_update_ha_state(True)
        
        # Update when climate entity updates
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                self._climate_entity.entity_id,
                _update,
            )
        )


class TRVValvePositionSensor(TRVControlSensorBase):
    """Sensor for TRV valve position."""
    
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:pipe-valve"
    
    def __init__(self, climate_entity, trv: dict, base_name: str, trv_name: str):
        """Initialize the sensor."""
        self._trv = trv
        self._trv_id = trv['trv']
        super().__init__(climate_entity, f"{base_name} {trv_name} Valve Position")
        self._attr_unique_id = f"{climate_entity.unique_id}_{trv_name.lower().replace(' ', '_')}_valve_position"
    
    @property
    def native_value(self) -> int | None:
        """Return the valve position."""
        if self._trv_id in self._climate_entity._trv_states:
            return self._climate_entity._trv_states[self._trv_id].get("valve_position")
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self._trv_id in self._climate_entity._trv_states:
            state = self._climate_entity._trv_states[self._trv_id]
            return {
                "max_position": self._trv.get("max_position", 100),
                "valve_control_active": state.get("valve_control_active", False),
                "status": state.get("status", "unknown"),
            }
        return {}


class TRVReturnTempSensor(TRVControlSensorBase):
    """Sensor for TRV return temperature."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    
    def __init__(self, climate_entity, trv: dict, base_name: str, trv_name: str):
        """Initialize the sensor."""
        self._trv = trv
        self._trv_id = trv['trv']
        super().__init__(climate_entity, f"{base_name} {trv_name} Return Temperature")
        self._attr_unique_id = f"{climate_entity.unique_id}_{trv_name.lower().replace(' ', '_')}_return_temp"
    
    @property
    def native_value(self) -> float | None:
        """Return the return temperature."""
        if self._trv_id in self._climate_entity._trv_states:
            return self._climate_entity._trv_states[self._trv_id].get("return_temp")
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "open_threshold": self._trv.get("open_threshold"),
            "close_threshold": self._trv.get("close_threshold"),
        }


class HeatingStatusSensor(TRVControlSensorBase):
    """Sensor for overall heating status."""
    
    _attr_icon = "mdi:radiator"
    
    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Heating Status")
        self._attr_unique_id = f"{climate_entity.unique_id}_heating_status"
    
    @property
    def native_value(self) -> str:
        """Return the heating status."""
        return getattr(self._climate_entity, "_heating_status", "unknown")
    
    @property
    def icon(self) -> str:
        """Return icon based on status."""
        status = self.native_value
        if status == "heating":
            return "mdi:fire"
        elif status == "target_reached":
            return "mdi:check-circle"
        elif status == "off":
            return "mdi:power-off"
        elif status == "window_open":
            return "mdi:window-open"
        return "mdi:help-circle"


class TargetTempDifferenceSensor(TRVControlSensorBase):
    """Sensor for temperature difference from target."""
    
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer-lines"
    
    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Temperature Difference")
        self._attr_unique_id = f"{climate_entity.unique_id}_temp_difference"
    
    @property
    def native_value(self) -> float | None:
        """Return the temperature difference (current - target)."""
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature
        if current is not None and target is not None:
            return round(current - target, 1)
        return None
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        return {
            "current_temperature": self._climate_entity.current_temperature,
            "target_temperature": self._climate_entity.target_temperature,
        }
