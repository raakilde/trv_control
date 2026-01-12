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
        """Control valve based on room temperature and return temperature for a specific TRV."""
        trv_id = trv_config[CONF_TRV]
        trv_state = self._trv_states[trv_id]
        return_temp = trv_state["return_temp"]
        
        if return_temp is None:
            return
        
        # Don't control if window is open or HVAC is off
        if self._window_open or self._attr_hvac_mode == HVACMode.OFF:
            return
        
        # Get thresholds for this TRV
        close_threshold = trv_config.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
        open_threshold = trv_config.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
        max_position = trv_config.get(CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION)
        
        # Primary control: Room temperature vs target temperature
        room_temp = self._attr_current_temperature
        target_temp = self._attr_target_temperature
        
        if room_temp is not None and target_temp is not None:
            # Room has reached or exceeded target - close valve
            if room_temp >= target_temp:
                if not trv_state["valve_control_active"]:
                    _LOGGER.info(
                        "Room temp %.1f°C >= target %.1f°C, closing valve for TRV %s",
                        room_temp,
                        target_temp,
                        trv_id,
                    )
                    await self._async_set_valve_position(trv_id, 0)
                    trv_state["valve_control_active"] = True
            
            # Room is below target - check return temp before opening
            elif room_temp < target_temp:
                # Safety check: only open if return temp is not too high
                if return_temp >= close_threshold:
                    _LOGGER.info(
                        "Room temp %.1f°C < target %.1f°C, but return temp %.1f°C >= %.1f°C - keeping valve closed for %s",
                        room_temp,
                        target_temp,
                        return_temp,
                        close_threshold,
                        trv_id,
                    )
                    if not trv_state["valve_control_active"]:
                        await self._async_set_valve_position(trv_id, 0)
                        trv_state["valve_control_active"] = True
                
                # Open valve if return temp is acceptable
                elif return_temp <= open_threshold:
                    # Always ensure valve is at max position when return temp is low
                    if trv_state["valve_position"] != max_position:
                        _LOGGER.info(
                            "Room temp %.1f°C < target %.1f°C and return temp %.1f°C <= %.1f°C - opening valve to %d%% for %s",
                            room_temp,
                            target_temp,
                            return_temp,
                            open_threshold,
                            max_position,
                            trv_id,
                        )
                        await self._async_set_valve_position(trv_id, max_position)
                        trv_state["valve_control_active"] = False
        
        else:
            # Fallback to return temp only if room temp not available
            # Close valve if return temp is too high
            if return_temp >= close_threshold:
                if not trv_state["valve_control_active"]:
                    _LOGGER.info(
                        "Return temp %.1f >= %.1f, closing valve for TRV %s (room temp not available)",
                        return_temp,
                        close_threshold,
                        trv_id,
                    )
                    await self._async_set_valve_position(trv_id, 0)
                    trv_state["valve_control_active"] = True
            
            # Open valve when temp drops below open threshold
            elif return_temp <= open_threshold:
                # Always ensure valve is at max position when return temp is low
                if trv_state["valve_position"] != max_position:
                    _LOGGER.info(
                        "Return temp %.1f <= %.1f, opening valve to %d%% for TRV %s (room temp not available)",
                        return_temp,
                        open_threshold,
                        max_position,
                        trv_id,
                    )
                    await self._async_set_valve_position(trv_id, max_position)
                    trv_state["valve_control_active"] = False

    async def _async_set_valve_position(self, trv_id: str, position: int) -> None:
        """Set the valve position for a specific TRV."""
        self._trv_states[trv_id]["valve_position"] = position
        device_name = trv_id.replace("climate.", "")
        
        _LOGGER.info("Setting valve position to %d%% for %s", position, trv_id)
        
        # Try to set position via number entity first
        # Possible entity names for valve opening degree
        number_patterns = [
            f"number.{device_name}_valve_opening_degree",
            f"number.{device_name}_position",
            f"number.{device_name}_valve_position",
        ]
        
        position_set = False
        for number_entity in number_patterns:
            if self.hass.states.get(number_entity):
                try:
                    _LOGGER.info("Setting valve via entity %s to %d%%", number_entity, position)
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": number_entity,
                            "value": position,
                        },
                        blocking=False,
                    )
                    position_set = True
                    break
                except Exception as e:
                    _LOGGER.warning("Could not set valve position via %s: %s", number_entity, e)
        
        # Fallback to MQTT if no entity found
        if not position_set:
            try:
                # Sonoff uses "valve_opening_degree" attribute
                topic = f"zigbee2mqtt/{device_name}/set"
                payload = f'{{"valve_opening_degree": {position}}}'
                
                _LOGGER.info(
                    "Setting valve via MQTT for %s: topic=%s, payload=%s",
                    trv_id,
                    topic,
                    payload,
                )
                
                await self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": topic,
                        "payload": payload,
                    },
                    blocking=False,
                )
            except Exception as e:
                _LOGGER.error("Could not set valve position via MQTT for %s: %s", trv_id, e)

    async def _async_send_room_temperature_to_all_trvs(self, temperature: float) -> None:
        """Send current room temperature from shared sensor to all TRVs."""
        for trv in self._trvs:
            await self._async_send_room_temperature_to_trv(trv[CONF_TRV], temperature)

    async def _async_send_room_temperature_to_trv(self, trv_id: str, temperature: float) -> None:
        """Send room temperature to TRV and enable external sensor mode (Z2M)."""
        # Get device name from entity_id for MQTT topic
        device_name = trv_id.replace("climate.", "")
        topic = f"zigbee2mqtt/{device_name}/set"
        
        # Sonoff TRVZB exposes temperature sensor selection as a select entity
        # Try multiple possible entity name patterns
        
        # Possible select entity names for temperature sensor mode
        select_patterns = [
            f"select.{device_name}_temperature_sensor",
            f"select.{device_name}_sensor",
            f"select.{device_name}_temperature_sensor_select",
        ]
        
        # Possible number entity names for external temperature
        number_patterns = [
            f"number.{device_name}_external_temperature",
            f"number.{device_name}_external_temperature_input",
            f"number.{device_name}_ext_temperature",
        ]
        
        try:
            # Step 1: Set to external sensor mode
            sensor_set = False
            for select_entity in select_patterns:
                if self.hass.states.get(select_entity):
                    _LOGGER.info(
                        "Found select entity: %s, setting to 'external'",
                        select_entity,
                    )
                    
                    await self.hass.services.async_call(
                        "select",
                        "select_option",
                        {
                            "entity_id": select_entity,
                            "option": "external",
                        },
                        blocking=True,
                    )
                    sensor_set = True
                    break
            
            if not sensor_set:
                # No select entity found, use MQTT
                _LOGGER.info(
                    "No select entity found for %s, using MQTT: topic=%s",
                    trv_id,
                    topic,
                )
                
                await self.hass.services.async_call(
                    "mqtt",
                    "publish",
                    {
                        "topic": topic,
                        "payload": '{"temperature_sensor_select": "external"}',
                    },
                    blocking=True,
                )
            
            # Small delay to ensure mode is set
            import asyncio
            await asyncio.sleep(0.1)
            
            # Step 2: Send external temperature value
            temp_set = False
            for number_entity in number_patterns:
                if self.hass.states.get(number_entity):
                    _LOGGER.info(
                        "Found number entity: %s, setting to %.1f°C",
                        number_entity,
                        temperature,
                    )
                    
                    await self.hass.services.async_call(
                        "number",
                        "set_value",
                        {
                            "entity_id": number_entity,
                            "value": temperature,
                        },
                        blocking=False,
                    )
                    temp_set = True
                    break
            
            if not temp_set:
                # No number entity found, use MQTT
                temp_payload = f'{{"external_temperature_input": {temperature}}}'
                
                _LOGGER.info(
                    "No number entity found for %s, using MQTT: topic=%s, payload=%s",
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
            _LOGGER.error("Failed to send room temperature to %s: %s", trv_id, e)

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
        # Determine overall heating status
        heating_status = self._determine_heating_status()
        
        attrs = {
            "heating_status": heating_status["status"],
            "temp_sensor": self._temp_sensor_id,
            "trv_count": len(self._trvs),
            "window_open": self._window_open,  # Always show window state
        }
        
        if self._window_sensor_id:
            attrs["window_sensor"] = self._window_sensor_id
        
        # Add info for each TRV
        for idx, trv in enumerate(self._trvs, 1):
            trv_id = trv[CONF_TRV]
            trv_state = self._trv_states[trv_id]
            
            # Use friendly name from entity state, fallback to entity_id
            trv_entity_state = self.hass.states.get(trv_id)
            if trv_entity_state and trv_entity_state.attributes.get("friendly_name"):
                trv_name = trv_entity_state.attributes["friendly_name"].lower().replace(" ", "_")
            else:
                # Fallback to cleaned entity_id
                trv_name = trv_id.replace("climate.", "").replace(" ", "_")
            
            prefix = trv_name
            
            attrs[f"{prefix}_entity"] = trv_id
            attrs[f"{prefix}_return_temp_sensor"] = trv[CONF_RETURN_TEMP]
            attrs[f"{prefix}_return_temp"] = trv_state["return_temp"]
            attrs[f"{prefix}_valve_position"] = trv_state["valve_position"]
            attrs[f"{prefix}_valve_control_active"] = trv_state["valve_control_active"]
            attrs[f"{prefix}_close_threshold"] = trv.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
            attrs[f"{prefix}_open_threshold"] = trv.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
            attrs[f"{prefix}_max_position"] = trv.get(CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION)
            
            # Add individual TRV status and reason
            trv_status = self._determine_trv_status_with_reason(trv, trv_state)
            attrs[f"{prefix}_status"] = trv_status["status"]
            attrs[f"{prefix}_status_reason"] = trv_status["reason"]
        
        return attrs
    
    def _determine_heating_status(self) -> dict[str, str]:
        """Determine the current heating status."""
        # Check window first - it sets HVAC to OFF so needs priority
        if self._window_open:
            return {"status": "window_open"}
        
        if self._attr_hvac_mode == HVACMode.OFF:
            return {"status": "off"}
        
        room_temp = self._attr_current_temperature
        target_temp = self._attr_target_temperature
        
        if room_temp is None:
            return {"status": "no_sensor"}
        
        if target_temp is None:
            return {"status": "no_target"}
        
        # Check if room has reached target
        if room_temp >= target_temp:
            return {"status": "target_reached"}
        
        # Room needs heating - check return temp
        any_valve_open = False
        all_return_temp_high = True
        
        for trv in self._trvs:
            trv_id = trv[CONF_TRV]
            trv_state = self._trv_states[trv_id]
            return_temp = trv_state["return_temp"]
            close_threshold = trv.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
            
            if not trv_state["valve_control_active"]:
                any_valve_open = True
            
            if return_temp is None or return_temp < close_threshold:
                all_return_temp_high = False
        
        if any_valve_open:
            return {"status": "heating"}
        elif all_return_temp_high:
            return {"status": "return_temp_high"}
        else:
            return {"status": "waiting"}
    
    def _determine_trv_status_with_reason(self, trv_config: dict[str, Any], trv_state: dict[str, Any]) -> dict[str, str]:
        """Determine status and reason for individual TRV."""
        room_temp = self._attr_current_temperature
        target_temp = self._attr_target_temperature
        return_temp = trv_state["return_temp"]
        valve_position = trv_state["valve_position"]
        close_threshold = trv_config.get(CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE)
        open_threshold = trv_config.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)
        
        if self._attr_hvac_mode == HVACMode.OFF:
            return {"status": "off", "reason": "HVAC mode is OFF"}
        
        if self._window_open:
            return {"status": "window_open", "reason": "Window/door is open - heating disabled"}
        
        if return_temp is None:
            return {"status": "no_sensor", "reason": "Return temperature sensor not available"}
        
        if room_temp is not None and target_temp is not None:
            # Room temperature based control
            if room_temp >= target_temp:
                return {
                    "status": "target_reached",
                    "reason": f"Room {room_temp}°C ≥ target {target_temp}°C - valve closed"
                }
            elif return_temp >= close_threshold:
                return {
                    "status": "return_high",
                    "reason": f"Room {room_temp}°C < target {target_temp}°C but return {return_temp}°C ≥ {close_threshold}°C - valve closed"
                }
            elif return_temp <= open_threshold:
                return {
                    "status": "heating",
                    "reason": f"Room {room_temp}°C < target {target_temp}°C, return {return_temp}°C ≤ {open_threshold}°C - valve {valve_position}%"
                }
            else:
                return {
                    "status": "between_thresholds",
                    "reason": f"Return temp {return_temp}°C between {open_threshold}-{close_threshold}°C - valve {valve_position}%"
                }
        else:
            # Fallback to return temp only
            if return_temp >= close_threshold:
                return {
                    "status": "return_high",
                    "reason": f"Return {return_temp}°C ≥ {close_threshold}°C - valve closed (no room temp)"
                }
            elif return_temp <= open_threshold:
                return {
                    "status": "heating",
                    "reason": f"Return {return_temp}°C ≤ {open_threshold}°C - valve {valve_position}% (no room temp)"
                }
            else:
                return {
                    "status": "between_thresholds",
                    "reason": f"Return {return_temp}°C between {open_threshold}-{close_threshold}°C - valve {valve_position}%"
                }

    
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
