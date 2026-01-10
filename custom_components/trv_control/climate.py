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
    CONF_TRVS,
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
    
    # Get rooms from options if available, otherwise from data
    rooms = config_entry.options.get(CONF_ROOMS, config_entry.data.get(CONF_ROOMS, []))
    
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
        
        # Store shared sensors
        self._temp_sensor_id = room_data.get(CONF_TEMP_SENSOR)
        self._window_sensor_id = room_data.get(CONF_WINDOW_SENSOR)
        
        # Store list of TRVs with their configs
        self._trvs = room_data.get(CONF_TRVS, [])
        
        # State tracking
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = None
        self._window_open = False
        self._saved_hvac_mode = HVACMode.HEAT
        self._attr_min_temp = 5.0
        self._attr_max_temp = 30.0
        self._attr_target_temperature_step = 0.5
        
        # Track each TRV's state
        self._trv_states = {}
        for trv in self._trvs:
            trv_id = trv[CONF_TRV]
            self._trv_states[trv_id] = {
                "return_temp": None,
                "valve_position": 0,
                "valve_control_active": False,
            }
        
        self._unsub_state_changed = None
        self._unsub_temp_update = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()
        
        # Send room temperature to all TRVs every 5 minutes
        async def _async_update_trv_temperature(now=None):
            """Send current room temperature from shared sensor to all TRVs."""
            if self._attr_current_temperature is not None:
                _LOGGER.info(
                    "[%s] Sending room temperature %.1f°C to %d TRVs",
                    self._attr_name,
                    self._attr_current_temperature,
                    len(self._trvs),
                )
                await self._async_send_room_temperature_to_all_trvs(self._attr_current_temperature)
            else:
                _LOGGER.warning("[%s] Cannot send temperature - sensor value not available yet", self._attr_name)
        
        # Set up 5-minute interval
        self._unsub_temp_update = async_track_time_interval(
            self.hass,
            _async_update_trv_temperature,
            timedelta(minutes=5),
        )
        
        # Subscribe to state changes of all entities
        entities_to_track = [self._temp_sensor_id]
        
        # Add all TRV entities and their return temp sensors
        for trv in self._trvs:
            entities_to_track.append(trv[CONF_TRV])
            entities_to_track.append(trv[CONF_RETURN_TEMP])
        
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
                    new_temp = float(new_state.state)
                    if new_temp != self._attr_current_temperature:
                        _LOGGER.info(
                            "[%s] Room temperature changed: %.1f°C → %.1f°C",
                            self._attr_name,
                            self._attr_current_temperature if self._attr_current_temperature else 0,
                            new_temp,
                        )
                        self._attr_current_temperature = new_temp
                        # Send updated room temperature to all TRVs
                        self.hass.async_create_task(
                            self._async_send_room_temperature_to_all_trvs(self._attr_current_temperature)
                        )
                except (ValueError, TypeError):
                    pass
            
            # Check if it's a return temperature sensor
            for trv in self._trvs:
                if entity_id == trv[CONF_RETURN_TEMP]:
                    try:
                        return_temp = float(new_state.state)
                        self._trv_states[trv[CONF_TRV]]["return_temp"] = return_temp
                        # Check valve control based on return temperature
                        self.hass.async_create_task(self._async_control_valve(trv))
                    except (ValueError, TypeError):
                        pass
                    break
                
                # Update from TRV state
                elif entity_id == trv[CONF_TRV]:
                    if hasattr(new_state, 'attributes'):
                        if temp := new_state.attributes.get('temperature'):
                            self._attr_target_temperature = float(temp)
                        if hvac_mode := new_state.state:
                            if hvac_mode in [mode.value for mode in HVACMode]:
                                self._attr_hvac_mode = HVACMode(hvac_mode)
                    break
            
            # Handle window sensor
            if entity_id == self._window_sensor_id:
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
                _LOGGER.info(
                    "[%s] Initial room temperature: %.1f°C from %s",
                    self._attr_name,
                    self._attr_current_temperature,
                    self._temp_sensor_id,
                )
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "[%s] Could not read initial temperature from %s: %s",
                    self._attr_name,
                    self._temp_sensor_id,
                    temp_state.state,
                )
        
        # Get initial return temps
        for trv in self._trvs:
            if return_state := self.hass.states.get(trv[CONF_RETURN_TEMP]):
                try:
                    self._trv_states[trv[CONF_TRV]]["return_temp"] = float(return_state.state)
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
        
        # Send initial room temperature to all TRVs now that we have the initial state
        await _async_update_trv_temperature()

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        if self._unsub_state_changed:
            self._unsub_state_changed()
        if self._unsub_temp_update:
            self._unsub_temp_update()

    async def _async_control_valve(self, trv_config: dict[str, Any]) -> None:
        """Control valve based on return temperature for a specific TRV."""
        trv_id = trv_config[CONF_TRV]
        trv_state = self._trv_states[trv_id]
        return_temp = trv_state["return_temp"]
        
        if return_temp is None:
            return
        
        # Don't control if window is open
        if self._window_open:
            return
        
        # Get thresholds for this TRV
        close_threshold = trv_config.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
        open_threshold = trv_config.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
        max_position = trv_config.get(CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION)
        
        # Close valve if return temp is too high
        if return_temp >= close_threshold:
            if not trv_state["valve_control_active"]:
                _LOGGER.info(
                    "Return temp %.1f >= %.1f, closing valve for TRV %s",
                    return_temp,
                    close_threshold,
                    trv_id,
                )
                await self._async_set_valve_position(trv_id, 0)
                trv_state["valve_control_active"] = True
        
        # Open valve when temp drops below open threshold
        elif return_temp <= open_threshold:
            if trv_state["valve_control_active"]:
                _LOGGER.info(
                    "Return temp %.1f <= %.1f, opening valve for TRV %s",
                    return_temp,
                    open_threshold,
                    trv_id,
                )
                await self._async_set_valve_position(trv_id, max_position)
                trv_state["valve_control_active"] = False

    async def _async_set_valve_position(self, trv_id: str, position: int) -> None:
        """Set the valve position for a specific TRV."""
        self._trv_states[trv_id]["valve_position"] = position
        
        # Try to set position attribute on TRV (Z2M specific)
        try:
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": f"{trv_id.replace('climate.', 'number.')}_position",
                    "value": position,
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.debug("Could not set valve position via number entity for %s: %s", trv_id, e)
        
        # Alternative: Try MQTT for Z2M devices
        try:
            device_name = trv_id.replace("climate.", "").replace("_", " ")
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
            _LOGGER.debug("Could not set valve position via MQTT for %s: %s", trv_id, e)

    async def _async_send_room_temperature_to_all_trvs(self, temperature: float) -> None:
        """Send current room temperature from shared sensor to all TRVs."""
        for trv in self._trvs:
            await self._async_send_room_temperature_to_trv(trv[CONF_TRV], temperature)

    async def _async_send_room_temperature_to_trv(self, trv_id: str, temperature: float) -> None:
        """Send room temperature to TRV and enable external sensor mode (Z2M)."""
        # Get device name from entity_id for MQTT topic
        device_name = trv_id.replace("climate.", "")
        topic = f"zigbee2mqtt/{device_name}/set"
        
        # Sonoff TRVZB requires specific sequence:
        # 1. Set temperature_sensor_select to "external"
        # 2. Send external_temperature_input value
        
        try:
            # Step 1: Set to external sensor mode
            sensor_mode_payload = '{"temperature_sensor_select": "external"}'
            
            _LOGGER.info(
                "Setting external sensor mode for %s: topic=%s, payload=%s",
                trv_id,
                topic,
                sensor_mode_payload,
            )
            
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": sensor_mode_payload,
                },
                blocking=True,  # Wait for this to complete
            )
            
            # Small delay to ensure mode is set
            import asyncio
            await asyncio.sleep(0.1)
            
            # Step 2: Send external temperature value
            temp_payload = f'{{"external_temperature_input": {temperature}}}'
            
            _LOGGER.info(
                "Sending external temperature to %s: topic=%s, payload=%s",
                trv_id,
                topic,
                temp_payload,
            )
            
            await self.hass.services.async_call(
                "mqtt",
                "publish",
                {
                    "topic": topic,
                    "payload": temp_payload,
                },
                blocking=False,
            )
        except Exception as e:
            _LOGGER.error("Failed to send room temperature to %s via MQTT: %s", trv_id, e)

    async def _async_send_temperature_to_all_trvs(self, temperature: float) -> None:
        """Send target temperature command to all TRVs."""
        for trv in self._trvs:
            await self._async_send_temperature_to_trv(trv[CONF_TRV], temperature)

    async def _async_send_temperature_to_trv(self, trv_id: str, temperature: float) -> None:
        """Send target temperature command to a specific TRV."""
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {
                "entity_id": trv_id,
                "temperature": temperature,
            },
            blocking=True,
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        self._attr_target_temperature = temperature
        
        # Send temperature command to all TRVs
        await self._async_send_temperature_to_all_trvs(temperature)
        
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        # Don't allow turning on if window is open
        if hvac_mode != HVACMode.OFF and self._window_open:
            _LOGGER.warning("Cannot turn on heating for %s - window is open", self._attr_name)
            return
        
        self._attr_hvac_mode = hvac_mode
        
        # Send HVAC mode to all TRVs
        for trv in self._trvs:
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {
                    "entity_id": trv[CONF_TRV],
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
            "trv_count": len(self._trvs),
        }
        
        if self._window_sensor_id:
            attrs["window_sensor"] = self._window_sensor_id
            attrs["window_open"] = self._window_open
        
        # Add info for each TRV
        for idx, trv in enumerate(self._trvs, 1):
            trv_id = trv[CONF_TRV]
            trv_state = self._trv_states[trv_id]
            prefix = f"trv{idx}"
            
            attrs[f"{prefix}_entity"] = trv_id
            attrs[f"{prefix}_return_temp_sensor"] = trv[CONF_RETURN_TEMP]
            attrs[f"{prefix}_return_temp"] = trv_state["return_temp"]
            attrs[f"{prefix}_valve_position"] = trv_state["valve_position"]
            attrs[f"{prefix}_valve_control_active"] = trv_state["valve_control_active"]
            attrs[f"{prefix}_close_threshold"] = trv.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
            attrs[f"{prefix}_open_threshold"] = trv.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
            attrs[f"{prefix}_max_position"] = trv.get(CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION)
        
        return attrs
    
    async def async_set_valve_position(self, trv_entity_id: str, position: int) -> None:
        """Service to manually set valve position for a specific TRV."""
        if trv_entity_id in self._trv_states:
            await self._async_set_valve_position(trv_entity_id, position)
            self.async_write_ha_state()
        else:
            _LOGGER.error("TRV %s not found in room %s", trv_entity_id, self._attr_name)
    
    async def async_set_return_thresholds(
        self, trv_entity_id: str, close_temp: float | None = None, open_temp: float | None = None
    ) -> None:
        """Service to set return temperature thresholds for a specific TRV."""
        # Find the TRV config
        for trv in self._trvs:
            if trv[CONF_TRV] == trv_entity_id:
                if close_temp is not None:
                    trv[CONF_RETURN_TEMP_CLOSE] = close_temp
                if open_temp is not None:
                    trv[CONF_RETURN_TEMP_OPEN] = open_temp
                self.async_write_ha_state()
                return
        
        _LOGGER.error("TRV %s not found in room %s", trv_entity_id, self._attr_name)
