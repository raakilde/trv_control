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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from datetime import timedelta

from .const import (
    DOMAIN,
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


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform."""
    from .const import CONF_ROOMS
    
    rooms = config_entry.data.get(CONF_ROOMS, [])
    
    entities = []
    for room in rooms:
        entities.append(TRVClimate(config_entry, room))
    
    async_add_entities(entities)


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

    def __init__(self, config_entry: ConfigEntry, room_data: dict[str, Any]) -> None:
        """Initialize the climate device."""
        self._config_entry = config_entry
        room_name = room_data.get(CONF_ROOM_NAME, "Room")
        
        self._attr_unique_id = f"{config_entry.entry_id}_{room_name.lower().replace(' ', '_')}"
        self._attr_name = f"{room_name} TRV Control"
        
        # Store entity IDs
        self._temp_sensor_id = room_data.get(CONF_TEMP_SENSOR)
        self._trv_id = room_data.get(CONF_TRV)
        self._return_temp_id = room_data.get(CONF_RETURN_TEMP)
        self._window_sensor_id = room_data.get(CONF_WINDOW_SENSOR)
        
        # Control parameters
        self._return_temp_close = room_data.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
        self._return_temp_open = room_data.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
        self._max_valve_position = room_data.get(CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION)
        
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = None
        self._return_temperature = None
        self._window_open = False
        self._saved_hvac_mode = HVACMode.HEAT
        self._valve_position = 0
        self._valve_control_active = False
        self._attr_min_temp = 5.0
        self._attr_max_temp = 30.0
        self._attr_target_temperature_step = 0.5
        
        self._unsub_state_changed = None
        self._unsub_temp_update = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Send temperature to TRV every 5 minutes
        async def _async_update_trv_temperature(now=None):
            """Send current target temperature to TRV."""
            if self._attr_target_temperature is not None and self._attr_hvac_mode != HVACMode.OFF:
                _LOGGER.debug(
                    "Sending temperature %.1f to TRV %s",
                    self._attr_target_temperature,
                    self._trv_id,
                )
                await self._async_send_temperature_to_trv(self._attr_target_temperature)
        
        # Set up 5-minute interval
        self._unsub_temp_update = async_track_time_interval(
            self.hass,
            _async_update_trv_temperature,
            timedelta(minutes=5),
        )
        
        # Subscribe to state changes of all entities
        entities_to_track = [self._temp_sensor_id, self._trv_id, self._return_temp_id]
        if self._window_sensor_id:
            entities_to_track.append(self._window_sensor_id)
        
        @callback
        def async_state_changed(event):
            """Handle state changes of monitored entities."""
            entity_id = event.data.get("entity_id")
            new_state = event.data.get("new_state")
            
            if new_state is None:
                return
                
            # Update current temperature from temp sensor
            if entity_id == self._temp_sensor_id:
                try:
                    self._attr_current_temperature = float(new_state.state)
                except (ValueError, TypeError):
                    pass
            
            # Update return temperature
            elif entity_id == self._return_temp_id:
                try:
                    self._return_temperature = float(new_state.state)
                    # Check valve control based on return temperature
                    self.hass.async_create_task(self._async_control_valve())
                except (ValueError, TypeError):
                    pass
            
            # Handle window sensor
            elif entity_id == self._window_sensor_id:
                window_state = new_state.state
                self._window_open = window_state in ["on", "open", "true", True]
                
                if self._window_open:
                    _LOGGER.info("Window opened for %s, turning off heating", self._attr_name)
                    # Save current mode and turn off
                    self._saved_hvac_mode = self._attr_hvac_mode
                    self.hass.async_create_task(self.async_set_hvac_mode(HVACMode.OFF))
                else:
                    _LOGGER.info("Window closed for %s, restoring heating", self._attr_name)
                    # Restore previous mode
                    if self._saved_hvac_mode != HVACMode.OFF:
                        self.hass.async_create_task(self.async_set_hvac_mode(self._saved_hvac_mode))
            
            # Update from TRV state
            elif entity_id == self._trv_id:
                if hasattr(new_state, 'attributes'):
                    if temp := new_state.attributes.get('temperature'):
                        self._attr_target_temperature = float(temp)
                    if hvac_mode := new_state.state:
                        if hvac_mode in [mode.value for mode in HVACMode]:
                            self._attr_hvac_mode = HVACMode(hvac_mode)
            
            self.async_write_ha_state()
        
        self._unsub_state_changed = async_track_state_change_event(
            self.hass,
            entities_to_track,
            async_state_changed,
        )
        
        # Get initial states
        if temp_state := self.hass.states.get(self._temp_sensor_id):
            try:
                self._attr_current_temperature = float(temp_state.state)
            except (ValueError, TypeError):
                pass
        
        if return_state := self.hass.states.get(self._return_temp_id):
            try:
                self._return_temperature = float(return_state.state)
            except (ValueError, TypeError):
                pass
        
        # Check initial window state
        if self._window_sensor_id:
            if window_state := self.hass.states.get(self._window_sensor_id):
                self._window_open = window_state.state in ["on", "open", "true", True]
                if self._window_open:
                    _LOGGER.info("Initial window state is open for %s", self._attr_name)
                    self._saved_hvac_mode = self._attr_hvac_mode
                    self._attr_hvac_mode = HVACMode.OFF
                pass

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsub_state_changed:
            self._unsub_state_changed()
        if self._unsub_temp_update:
            self._unsub_temp_update()

    async def _async_control_valve(self) -> None:
        """Control valve based on return temperature."""
        if self._return_temperature is None:
            return
        
        # Don't control if window is open
        if self._window_open:
            return
        
        # Close valve if return temp is too high
        if self._return_temperature >= self._return_temp_close:
            if not self._valve_control_active:
                _LOGGER.info(
                    "Return temp %.1f >= %.1f, closing valve for %s",
                    self._return_temperature,
                    self._return_temp_close,
                    self._attr_name,
                )
                await self._async_set_valve_position(0)
                self._valve_control_active = True
        
        # Open valve when temp drops below open threshold
        elif self._return_temperature <= self._return_temp_open:
            if self._valve_control_active:
                _LOGGER.info(
                    "Return temp %.1f <= %.1f, opening valve for %s",
                    self._return_temperature,
                    self._return_temp_open,
                    self._attr_name,
                )
                await self._async_set_valve_position(self._max_valve_position)
                self._valve_control_active = False

    async def _async_set_valve_position(self, position: int) -> None:
        """Set the valve position."""
        self._valve_position = position
        
        # Try to set position attribute on TRV (Z2M specific)
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": f"{self._trv_id.replace('climate.', 'number.')}_position",
                    "value": position,
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.debug("Could not set valve position via number entity: %s", e)
        
        # Alternative: Try MQTT for Z2M devices
        try:
            device_name = self._trv_id.replace("climate.", "").replace("_", " ")
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": f"zigbee2mqtt/{device_name}/set",
                    "payload": f'{{"position": {position}}}',
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.debug("Could not set valve position via MQTT: %s", e)

    async def _async_send_temperature_to_trv(self, temperature: float) -> None:
        """Send temperature command to TRV."""
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": self._trv_id,
                "temperature": temperature,
            },
            blocking=True,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._attr_target_temperature = temperature
        
        # Send temperature command to TRV
        await self._async_send_temperature_to_trv(temperature)
        
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        # Don't allow turning on if window is open
        if hvac_mode != HVACMode.OFF and self._window_open:
            _LOGGER.warning("Cannot turn on heating for %s - window is open", self._attr_name)
            return
        
        self._attr_hvac_mode = hvac_mode
        
        # Send HVAC mode to TRV
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {
                "entity_id": self._trv_id,
                "hvac_mode": hvac_mode,
            },
            blocking=True,
        )
        
        self.async_write_ha_state()
    
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        attrs = {
            "temp_sensor": self._temp_sensor_id,
            "trv": self._trv_id,
            "return_temp_sensor": self._return_temp_id,
            "return_temp_close_threshold": self._return_temp_close,
            "return_temp_open_threshold": self._return_temp_open,
            "max_valve_position": self._max_valve_position,
            "current_valve_position": self._valve_position,
            "valve_control_active": self._valve_control_active,
        }
        
        if self._window_sensor_id:
            attrs["window_sensor"] = self._window_sensor_id
            attrs["window_open"] = self._window_open
        
        if self._return_temperature is not None:
            attrs["return_temperature"] = self._return_temperature
        
        return attrs
    
    async def async_set_valve_position(self, position: int) -> None:
        """Service to manually set valve position."""
        await self._async_set_valve_position(position)
        self.async_write_ha_state()
    
    async def async_set_return_thresholds(
        self, close_temp: float | None = None, open_temp: float | None = None
    ) -> None:
        """Service to set return temperature thresholds."""
        if close_temp is not None:
            self._return_temp_close = close_temp
        if open_temp is not None:
            self._return_temp_open = open_temp
        self.async_write_ha_state()
