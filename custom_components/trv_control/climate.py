"""Platform for climate integration."""

from __future__ import annotations

import logging
from datetime import timedelta
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
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ANTICIPATORY_OFFSET,
    CONF_MAX_VALVE_POSITION,
    CONF_MIN_VALVE_POSITION,
    CONF_PID_ANTICIPATORY_OFFSET,
    CONF_PROPORTIONAL_BAND,
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
    DEFAULT_MIN_VALVE_POSITION_DELTA,
    DEFAULT_PROPORTIONAL_BAND,
    DEFAULT_RETURN_TEMP_CLOSE,
    DEFAULT_RETURN_TEMP_OPEN,
    DEFAULT_TEMP_HISTORY_SIZE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform."""
    # Get rooms from options if available, otherwise from data
    # Check explicitly for None to allow empty list
    if CONF_ROOMS in config_entry.options:
        rooms = config_entry.options[CONF_ROOMS]
    else:
        rooms = config_entry.data.get(CONF_ROOMS, [])

    entities = []
    for room in rooms:
        entity = TRVClimate(config_entry, room)
        entities.append(entity)

    async_add_entities(entities)

    # Store all entities in hass.data for sensor access
    if entities:
        from .const import DOMAIN

        hass.data[DOMAIN][config_entry.entry_id] = entities
        _LOGGER.info(
            "Climate entities stored in hass.data for entry %s: %d entities",
            config_entry.entry_id,
            len(entities),
        )


class TRVClimate(ClimateEntity, RestoreEntity):
    """Representation of a TRV Climate device."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_OFF
        | ClimateEntityFeature.TURN_ON
    )
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_icon = "mdi:radiator"

    def __init__(self, config_entry: ConfigEntry, room_data: dict[str, Any]) -> None:
        """Initialize the climate device."""
        self.config_entry = config_entry
        self._room_name = room_data.get(CONF_ROOM_NAME, "Room")

        self._attr_unique_id = (
            f"{config_entry.entry_id}_{self._room_name.lower().replace(' ', '_')}"
        )
        self._attr_name = f"{self._room_name} TRV Control"

        # Store shared sensors
        self._temp_sensor_id = room_data.get(CONF_TEMP_SENSOR)
        self._window_sensor_id = room_data.get(CONF_WINDOW_SENSOR)

        # Store list of TRVs with their configs - make a deep copy to avoid reference issues
        original_trvs = room_data.get(CONF_TRVS, [])
        self._trvs = [dict(trv) for trv in original_trvs]

        # State tracking - default target temp will be restored in async_added_to_hass
        self._attr_hvac_mode = HVACMode.HEAT
        self._attr_target_temperature = 20.0
        self._attr_current_temperature = None
        self._temp_last_updated = None
        self._window_open = False
        self._saved_hvac_mode = HVACMode.HEAT
        self._attr_min_temp = 5.0
        self._attr_max_temp = 30.0
        self._attr_target_temperature_step = 0.5

        # Temperature history for rate calculation - store tuples of (timestamp, temperature)
        self._temp_history = []
        self._max_history_size = DEFAULT_TEMP_HISTORY_SIZE

        # Track each TRV's state
        self._trv_states = {}
        for trv in self._trvs:
            trv_id = trv[CONF_TRV]
            self._trv_states[trv_id] = {
                "return_temp": None,
                "return_temp_last_updated": None,
                "valve_position": 0,
                "valve_control_active": False,
            }

        self._unsub_state_changed = None
        self._unsub_temp_update = None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Restore previous state if available
        if (last_state := await self.async_get_last_state()) is not None:
            if last_state.attributes.get(ATTR_TEMPERATURE) is not None:
                self._attr_target_temperature = last_state.attributes[ATTR_TEMPERATURE]
                _LOGGER.info(
                    "Restored target temperature %.1f for room %s",
                    self._attr_target_temperature,
                    self._room_name,
                )

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
                await self._async_send_room_temperature_to_all_trvs(
                    self._attr_current_temperature
                )

                # Also check and nudge any idle TRVs that should be heating
                if (
                    self._attr_hvac_mode == HVACMode.HEAT
                    and self._attr_target_temperature is not None
                ):
                    for trv in self._trvs:
                        trv_id = trv[CONF_TRV]
                        trv_state = self._trv_states[trv_id]

                        # If valve is open but TRV might be idle, nudge it
                        if trv_state["valve_position"] > 0:
                            await self._async_nudge_trv_if_idle(
                                trv_id, self._attr_target_temperature
                            )
            else:
                _LOGGER.warning(
                    "[%s] Cannot send temperature - sensor value not available yet",
                    self._attr_name,
                )

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
                            self._attr_current_temperature
                            if self._attr_current_temperature
                            else 0,
                            new_temp,
                        )
                        self._attr_current_temperature = new_temp
                        self._temp_last_updated = new_state.last_updated

                        # Add to temperature history for rate calculation
                        self._update_temperature_history(
                            new_temp, new_state.last_updated
                        )

                        # Send updated room temperature to all TRVs
                        self.hass.async_create_task(
                            self._async_send_room_temperature_to_all_trvs(
                                self._attr_current_temperature
                            )
                        )
                except (ValueError, TypeError):
                    pass

            # Check if it's a return temperature sensor
            for trv in self._trvs:
                if entity_id == trv[CONF_RETURN_TEMP]:
                    try:
                        return_temp = float(new_state.state)
                        self._trv_states[trv[CONF_TRV]]["return_temp"] = return_temp
                        self._trv_states[trv[CONF_TRV]]["return_temp_last_updated"] = (
                            new_state.last_updated
                        )
                        # Check valve control based on return temperature
                        self.hass.async_create_task(self._async_control_valve(trv))
                    except (ValueError, TypeError):
                        pass
                    break

                # Update from TRV state
                elif entity_id == trv[CONF_TRV]:
                    if hasattr(new_state, "attributes"):
                        if hvac_mode := new_state.state:
                            if hvac_mode in [mode.value for mode in HVACMode]:
                                self._attr_hvac_mode = HVACMode(hvac_mode)
                    break

            # Handle window sensor
            if entity_id == self._window_sensor_id:
                window_state = new_state.state
                self._window_open = window_state in ["on", "open", "true", True]

                if self._window_open:
                    _LOGGER.info(
                        "Window opened for %s, turning off heating", self._attr_name
                    )
                    # Save current mode and turn off
                    self._saved_hvac_mode = self._attr_hvac_mode
                    self.hass.async_create_task(self.async_set_hvac_mode(HVACMode.OFF))
                else:
                    _LOGGER.info(
                        "Window closed for %s, restoring heating", self._attr_name
                    )
                    # Restore previous mode
                    if self._saved_hvac_mode != HVACMode.OFF:
                        self.hass.async_create_task(
                            self.async_set_hvac_mode(self._saved_hvac_mode)
                        )

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
                self._temp_last_updated = temp_state.last_updated
                # Initialize temperature history with first reading
                self._update_temperature_history(
                    self._attr_current_temperature, temp_state.last_updated
                )
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

        # Get initial return temps and trigger valve control
        for trv in self._trvs:
            if return_state := self.hass.states.get(trv[CONF_RETURN_TEMP]):
                try:
                    self._trv_states[trv[CONF_TRV]]["return_temp"] = float(
                        return_state.state
                    )
                    self._trv_states[trv[CONF_TRV]]["return_temp_last_updated"] = (
                        return_state.last_updated
                    )
                    # Immediately check valve control with current settings
                    await self._async_control_valve(trv)
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

    def _update_temperature_history(self, temperature: float, timestamp) -> None:
        """Update temperature history for rate calculation."""
        self._temp_history.append((timestamp, temperature))

        # Keep only the last N readings
        if len(self._temp_history) > self._max_history_size:
            self._temp_history = self._temp_history[-self._max_history_size :]

    def _calculate_heating_rate(self) -> float:
        """Calculate recent temperature change rate in °C per hour.

        Returns:
            Heating rate in °C/hour. Positive = heating, negative = cooling.
        """
        if len(self._temp_history) < 2:
            return 0.0

        # Use recent history for rate calculation (last 10 readings or all if less)
        recent_count = min(10, len(self._temp_history))
        recent = self._temp_history[-recent_count:]

        if not recent or len(recent) < 2:
            return 0.0

        # Calculate time span in hours
        time_span = (recent[-1][0] - recent[0][0]).total_seconds() / 3600.0

        if time_span <= 0:
            return 0.0

        # Calculate temperature change
        temp_change = recent[-1][1] - recent[0][1]

        heating_rate = temp_change / time_span

        _LOGGER.debug(
            "[%s] Heating rate: %.2f°C/hour (%.1f°C over %.1f minutes)",
            self._attr_name,
            heating_rate,
            temp_change,
            time_span * 60,
        )

        return heating_rate

    def _is_learning(self) -> bool:
        """Check if system is still learning (insufficient data for reliable rate calculation).

        Returns:
            True if learning, False if enough data collected.
        """
        # Need at least 5 temperature readings spanning 15+ minutes for reliable data
        if len(self._temp_history) < 5:
            return True

        # Check time span
        time_span = (
            self._temp_history[-1][0] - self._temp_history[0][0]
        ).total_seconds() / 60.0
        if time_span < 15:  # Less than 15 minutes of data
            return True

        return False

    def _calculate_proportional_valve_position(
        self,
        room_temp: float,
        target_temp: float,
        anticipatory_offset: float,
        max_valve_position: int,
        proportional_band: float = DEFAULT_PROPORTIONAL_BAND,
    ) -> int:
        """Calculate valve position using proportional control.

        Args:
            room_temp: Current room temperature
            target_temp: Target temperature
            anticipatory_offset: Offset to close valve before reaching target
            max_valve_position: Maximum allowed valve position (%)
            proportional_band: Proportional band for this TRV
        Returns:
            Valve position (0-max_valve_position%)
        """
        temp_diff = target_temp - room_temp
        effective_diff = temp_diff - anticipatory_offset
        if effective_diff <= 0:
            return 0
        valve_position = int((effective_diff / proportional_band) * max_valve_position)
        valve_position = max(0, min(max_valve_position, valve_position))
        if valve_position < 10:
            valve_position = 0
        _LOGGER.debug(
            "[%s] Proportional control: temp_diff=%.2f°C, effective_diff=%.2f°C, valve=%d%% (max=%d%%, band=%.2f)",
            self._attr_name,
            temp_diff,
            effective_diff,
            valve_position,
            max_valve_position,
            proportional_band,
        )
        return valve_position

    async def _async_control_valve(self, trv_config: dict[str, Any]) -> None:
        """Control valve based on room temperature and return temperature for a specific TRV.

        Strategy: Set valve position and send actual target temperature.
        If TRV shows idle when it should be heating, nudge setpoint by +0.5°C then back.
        """
        trv_id = trv_config[CONF_TRV]
        trv_state = self._trv_states[trv_id]
        return_temp = trv_state["return_temp"]

        if return_temp is None:
            return

        # Don't control if window is open or HVAC is off
        if self._window_open or self._attr_hvac_mode == HVACMode.OFF:
            return

        # Get configuration for this TRV (needed for failsafe)
        current_valve_position = trv_state["valve_position"]
        min_valve_position = trv_config.get(
            CONF_MIN_VALVE_POSITION, current_valve_position
        )
        max_valve_position = trv_config.get(
            CONF_MAX_VALVE_POSITION,
            min_valve_position + DEFAULT_MIN_VALVE_POSITION_DELTA,
        )

        # Failsafe: If return temp hasn't updated in 1 hour and room needs heating, force heating
        return_temp_last_updated = trv_state.get("return_temp_last_updated")
        failsafe_active = False
        if return_temp_last_updated:
            now = dt_util.now()
            time_since_update = (now - return_temp_last_updated).total_seconds()
            room_temp = self._attr_current_temperature
            target_temp = self._attr_target_temperature

            # If return temp is stale (>60 min) and room needs heating, force valve open
            if (
                time_since_update > 3600
                and room_temp is not None
                and target_temp is not None
            ):
                if room_temp < target_temp:
                    if trv_state["valve_position"] != max_valve_position:
                        _LOGGER.warning(
                            "Failsafe: Return temp for %s hasn't updated in %.0f minutes, room needs heating - forcing open to %d%%",
                            trv_id,
                            time_since_update / 60,
                            max_valve_position,
                        )
                        await self._async_set_valve_position(
                            trv_id, max_valve_position
                        )
                        await self._async_send_temperature_to_trv(trv_id, target_temp)
                        await self._async_nudge_trv_if_idle(trv_id, target_temp)
                        trv_state["valve_control_active"] = True
                    failsafe_active = True

        # If failsafe is active, don't run normal control logic
        if failsafe_active:
            return

        # Get thresholds for this TRV
        close_threshold = trv_config.get(
            CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
        )

        # Only control based on return temp and allowed range
        if return_temp >= close_threshold:
            # Close valve if return temp is too high
            if trv_state["valve_position"] != 0:
                await self._async_set_valve_position(trv_id, 0)
                trv_state["valve_control_active"] = True
                _LOGGER.info(
                    "Return temp %.1f >= %.1f, valve closed for TRV %s",
                    return_temp,
                    close_threshold,
                    trv_id,
                )
        else:
            # PID/proportional control within [min_valve_position, max_valve_position]
            room_temp = self._attr_current_temperature
            target_temp = self._attr_target_temperature
            proportional_band = trv_config.get(
                CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND
            )
            anticipatory_offset = trv_config.get(
                CONF_PID_ANTICIPATORY_OFFSET,
                trv_config.get(CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET),
            )
            if room_temp is not None and target_temp is not None:
                pid_position = self._calculate_proportional_valve_position(
                    room_temp,
                    target_temp,
                    anticipatory_offset,
                    max_pid_valve_position,
                    proportional_band,
                )
                # Clamp to [min_valve_position, max_valve_position] (unless 0)
                if pid_position > 0:
                    desired_position = max(
                        min_valve_position,
                        min(max_valve_position, pid_position),
                    )
                else:
                    desired_position = 0
            else:
                # If no room temp, just use max_valve_position
                desired_position = max_valve_position
            if trv_state["valve_position"] != desired_position:
                await self._async_set_valve_position(trv_id, desired_position)
                trv_state["valve_control_active"] = True
                _LOGGER.info(
                    "Return temp %.1f < %.1f, valve set to %d%% for TRV %s (PID in range %d-%d%%)",
                    return_temp,
                    close_threshold,
                    desired_position,
                    trv_id,
                    min_valve_position,
                    max_valve_position,
                )

    async def _async_nudge_trv_if_idle(self, trv_id: str, target_temp: float) -> None:
        """Check if TRV is idle when it should be heating, and force it to use external sensor.

        Switches TRV to internal sensor then back to external to force re-evaluation.
        """
        import asyncio

        device_name = trv_id.replace("climate.", "")

        # Check TRV running_state
        running_state_patterns = [
            f"sensor.{device_name}_running_state",
            f"{trv_id}",  # Climate entity itself might have running_state attribute
        ]

        running_state = None
        trv_state = None
        for pattern in running_state_patterns:
            if state := self.hass.states.get(pattern):
                # Check if it's a sensor with the state, or climate entity with attribute
                if pattern.startswith("sensor."):
                    running_state = state.state
                elif pattern == trv_id:
                    trv_state = state
                    running_state = state.attributes.get("running_state")

                if running_state:
                    break

        # Determine if we should nudge based on running state or hvac_action
        should_nudge = False

        if running_state and running_state.lower() == "idle":
            should_nudge = True
            _LOGGER.debug("TRV %s running_state is idle", trv_id)
        elif trv_state and hasattr(trv_state, "attributes"):
            # Also check hvac_action attribute
            hvac_action = trv_state.attributes.get("hvac_action")
            if hvac_action and hvac_action.lower() == "idle":
                should_nudge = True
                _LOGGER.debug("TRV %s hvac_action is idle", trv_id)

        # If TRV shows "idle" when we expect heating, switch sensor mode
        # This forces TRV to re-evaluate and start using external temperature
        if should_nudge:
            _LOGGER.info(
                "TRV %s shows idle when heating expected - switching to internal sensor then back to external",
                trv_id,
            )

            # Switch to internal sensor
            sensor_select = f"select.{device_name}_sensor"
            if self.hass.states.get(sensor_select):
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": sensor_select, "option": "internal"},
                    blocking=True,
                )
                await asyncio.sleep(1)  # Wait for TRV to process

                # Switch back to external sensor
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {"entity_id": sensor_select, "option": "external"},
                    blocking=True,
                )
                _LOGGER.info("TRV %s sensor switched back to external", trv_id)
            else:
                _LOGGER.warning(
                    "TRV %s sensor select entity not found: %s", trv_id, sensor_select
                )

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
                    _LOGGER.info(
                        "Setting valve via entity %s to %d%%", number_entity, position
                    )
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
                    _LOGGER.warning(
                        "Could not set valve position via %s: %s", number_entity, e
                    )

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

                if self.hass.services.has_service("mqtt", "publish"):
                    await self.hass.services.async_call(
                        "mqtt",
                        "publish",
                        {
                            "topic": topic,
                            "payload": payload,
                        },
                        blocking=False,
                    )
                else:
                    _LOGGER.warning("MQTT service not available for %s", trv_id)
            except Exception as e:
                _LOGGER.error(
                    "Could not set valve position via MQTT for %s: %s", trv_id, e
                )

    async def _async_send_room_temperature_to_all_trvs(
        self, temperature: float
    ) -> None:
        """Send current room temperature from shared sensor to all TRVs."""
        for trv in self._trvs:
            await self._async_send_room_temperature_to_trv(trv[CONF_TRV], temperature)

    async def _async_send_room_temperature_to_trv(
        self, trv_id: str, temperature: float
    ) -> None:
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
                # No select entity found, try MQTT if available
                if self.hass.services.has_service("mqtt", "publish"):
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
                else:
                    _LOGGER.warning(
                        "No select entity found for %s and MQTT not available",
                        trv_id,
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
                # No number entity found, try MQTT if available
                if self.hass.services.has_service("mqtt", "publish"):
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
                else:
                    _LOGGER.warning(
                        "No number entity found for %s and MQTT not available",
                        trv_id,
                    )

        except Exception as e:
            _LOGGER.error("Failed to send room temperature to %s: %s", trv_id, e)

    async def _async_send_temperature_to_all_trvs(self, temperature: float) -> None:
        """Send target temperature command to all TRVs."""
        for trv in self._trvs:
            await self._async_send_temperature_to_trv(trv[CONF_TRV], temperature)

    async def _async_send_temperature_to_trv(
        self, trv_id: str, temperature: float
    ) -> None:
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

        # Trigger valve control for all TRVs to re-evaluate with new target
        # Valve control will send appropriate setpoint (5°C or 35°C) based on logic
        for trv in self._trvs:
            await self._async_control_valve(trv)

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        # Don't allow turning on if window is open
        if hvac_mode != HVACMode.OFF and self._window_open:
            _LOGGER.warning(
                "Cannot turn on heating for %s - window is open", self._attr_name
            )
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
            "learning_mode": self._is_learning(),
            "temp_readings": len(self._temp_history),
        }

        # Add learning status info
        if self._is_learning():
            readings_needed = max(0, 5 - len(self._temp_history))
            if len(self._temp_history) >= 2:
                time_span_min = (
                    self._temp_history[-1][0] - self._temp_history[0][0]
                ).total_seconds() / 60.0
                time_needed = max(0, 15 - int(time_span_min))
                attrs["learning_status"] = (
                    f"Learning: need {readings_needed} more readings or {time_needed} more minutes"
                )
            else:
                attrs["learning_status"] = (
                    f"Learning: need {readings_needed} more readings"
                )
        else:
            # Show current heating rate when not learning
            heating_rate = self._calculate_heating_rate()
            if heating_rate != 0:
                attrs["heating_rate"] = round(heating_rate, 2)  # °C per hour

        # Add timestamp for room temperature
        if self._temp_last_updated:
            attrs["temp_last_updated"] = self._format_relative_time(
                self._temp_last_updated
            )

        if self._window_sensor_id:
            attrs["window_sensor"] = self._window_sensor_id

        # Add info for each TRV

        for idx, trv in enumerate(self._trvs, 1):
            trv_id = trv[CONF_TRV]
            trv_state = self._trv_states[trv_id]

            # Use friendly name from entity state, fallback to entity_id
            trv_entity_state = self.hass.states.get(trv_id)
            if trv_entity_state and trv_entity_state.attributes.get("friendly_name"):
                trv_name = (
                    trv_entity_state.attributes["friendly_name"]
                    .lower()
                    .replace(" ", "_")
                )
            else:
                # Fallback to cleaned entity_id
                trv_name = trv_id.replace("climate.", "").replace(" ", "_")

            prefix = trv_name

            attrs[f"{prefix}_entity"] = trv_id
            attrs[f"{prefix}_return_temp_sensor"] = trv[CONF_RETURN_TEMP]
            attrs[f"{prefix}_return_temp"] = (
                round(trv_state["return_temp"], 1)
                if trv_state["return_temp"] is not None
                else None
            )

            # Add timestamp for return temperature
            if trv_state.get("return_temp_last_updated"):
                attrs[f"{prefix}_return_temp_last_updated"] = (
                    self._format_relative_time(trv_state["return_temp_last_updated"])
                )

            attrs[f"{prefix}_valve_position"] = trv_state["valve_position"]
            attrs[f"{prefix}_valve_control_active"] = trv_state["valve_control_active"]
            attrs[f"{prefix}_close_threshold"] = trv.get(
                CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
            )
            attrs[f"{prefix}_open_threshold"] = trv.get(
                CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN
            )
            attrs[f"{prefix}_max_position"] = trv.get(
                CONF_MAX_VALVE_POSITION, DEFAULT_MAX_VALVE_POSITION
            )
            attrs[f"{prefix}_anticipatory_offset"] = trv.get(
                CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET
            )

            # Expose valve range config as attributes
            min_valve_position = trv.get(
                CONF_MIN_VALVE_POSITION, trv_state["valve_position"]
            )
            max_valve_position = trv.get(
                CONF_MAX_VALVE_POSITION,
                min_valve_position + DEFAULT_MIN_VALVE_POSITION_DELTA,
            )
            attrs[f"{prefix}_min_valve_position"] = min_valve_position
            attrs[f"{prefix}_max_valve_position"] = max_valve_position
            attrs[f"{prefix}_proportional_band"] = trv.get(
                CONF_PROPORTIONAL_BAND, DEFAULT_PROPORTIONAL_BAND
            )
            attrs[f"{prefix}_pid_anticipatory_offset"] = trv.get(
                CONF_PID_ANTICIPATORY_OFFSET,
                trv.get(CONF_ANTICIPATORY_OFFSET, DEFAULT_ANTICIPATORY_OFFSET),
            )

            # Add individual TRV status and reason
            trv_status = self._determine_trv_status_with_reason(trv, trv_state)
            attrs[f"{prefix}_status"] = trv_status["status"]
            attrs[f"{prefix}_status_reason"] = trv_status["reason"]

        return attrs

    def _format_relative_time(self, timestamp) -> str:
        """Format timestamp as relative time in Danish."""
        if timestamp is None:
            return "Aldrig"

        now = dt_util.now()
        delta = now - timestamp

        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "Nu"
        elif seconds < 120:
            return "For 1 minut siden"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"For {minutes} minutter siden"
        elif seconds < 7200:
            return "For 1 time siden"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"For {hours} timer siden"
        elif seconds < 172800:
            return "For 1 dag siden"
        else:
            days = seconds // 86400
            return f"For {days} dage siden"

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

        # Show learning status prominently
        if self._is_learning():
            readings_needed = max(0, 5 - len(self._temp_history))
            if len(self._temp_history) >= 2:
                time_span_min = (
                    self._temp_history[-1][0] - self._temp_history[0][0]
                ).total_seconds() / 60.0
                time_needed = max(0, 15 - int(time_span_min))
                if readings_needed > 0:
                    return {"status": f"learning ({readings_needed} readings needed)"}
                else:
                    return {"status": f"learning ({time_needed} min needed)"}
            else:
                return {"status": "learning (collecting data)"}

        # Check if room has reached target
        if room_temp >= target_temp:
            return {"status": "target_reached"}

        # Room needs heating - always return heating status
        return {"status": "heating"}

    def _determine_trv_status_with_reason(
        self, trv_config: dict[str, Any], trv_state: dict[str, Any]
    ) -> dict[str, str]:
        """Determine status and reason for individual TRV."""
        room_temp = self._attr_current_temperature
        target_temp = self._attr_target_temperature
        return_temp = trv_state["return_temp"]
        valve_position = trv_state["valve_position"]
        close_threshold = trv_config.get(
            CONF_RETURN_TEMP_CLOSE, DEFAULT_RETURN_TEMP_CLOSE
        )
        open_threshold = trv_config.get(CONF_RETURN_TEMP_OPEN, DEFAULT_RETURN_TEMP_OPEN)

        if self._attr_hvac_mode == HVACMode.OFF:
            return {"status": "off", "reason": "HVAC mode is OFF"}

        if self._window_open:
            return {
                "status": "window_open",
                "reason": "Window/door is open - heating disabled",
            }

        if return_temp is None:
            return {
                "status": "no_sensor",
                "reason": "Return temperature sensor not available",
            }

        if room_temp is not None and target_temp is not None:
            # Room temperature based control
            if room_temp >= target_temp:
                return {
                    "status": "target_reached",
                    "reason": f"Room {room_temp}°C ≥ target {target_temp}°C - valve closed",
                }
            elif return_temp >= close_threshold:
                return {
                    "status": "return_high",
                    "reason": f"Room {room_temp}°C < target {target_temp}°C but return {return_temp}°C ≥ {close_threshold}°C - valve closed",
                }
            elif return_temp <= open_threshold:
                return {
                    "status": "heating",
                    "reason": f"Room {room_temp}°C < target {target_temp}°C, return {return_temp}°C ≤ {open_threshold}°C - valve {valve_position}%",
                }
            else:
                return {
                    "status": "between_thresholds",
                    "reason": f"Return temp {return_temp}°C between {open_threshold}-{close_threshold}°C - valve {valve_position}%",
                }
        else:
            # Fallback to return temp only
            if return_temp >= close_threshold:
                return {
                    "status": "return_high",
                    "reason": f"Return {return_temp}°C ≥ {close_threshold}°C - valve closed (no room temp)",
                }
            elif return_temp <= open_threshold:
                return {
                    "status": "heating",
                    "reason": f"Return {return_temp}°C ≤ {open_threshold}°C - valve {valve_position}% (no room temp)",
                }
            else:
                return {
                    "status": "between_thresholds",
                    "reason": f"Return {return_temp}°C between {open_threshold}-{close_threshold}°C - valve {valve_position}%",
                }

    async def async_set_valve_position(self, trv_entity_id: str, position: int) -> None:
        """Service to manually set valve position for a specific TRV."""
        if trv_entity_id in self._trv_states:
            await self._async_set_valve_position(trv_entity_id, position)
            self.async_write_ha_state()
        else:
            _LOGGER.error("TRV %s not found in room %s", trv_entity_id, self._attr_name)

    async def async_set_trv_thresholds(
        self,
        trv_entity_id: str,
        close_threshold: float | None = None,
        open_threshold: float | None = None,
        max_valve_position: int | None = None,
    ) -> None:
        """Service to set thresholds and max position for a specific TRV."""
        # Find the TRV config
        for trv in self._trvs:
            if trv[CONF_TRV] == trv_entity_id:
                updated = False
                if close_threshold is not None:
                    trv[CONF_RETURN_TEMP_CLOSE] = close_threshold
                    _LOGGER.info(
                        "Set close threshold to %.1f°C for %s",
                        close_threshold,
                        trv_entity_id,
                    )
                    updated = True
                if open_threshold is not None:
                    trv[CONF_RETURN_TEMP_OPEN] = open_threshold
                    _LOGGER.info(
                        "Set open threshold to %.1f°C for %s",
                        open_threshold,
                        trv_entity_id,
                    )
                    updated = True
                if max_valve_position is not None:
                    trv[CONF_MAX_VALVE_POSITION] = max_valve_position
                    _LOGGER.info(
                        "Set max valve position to %d%% for %s",
                        max_valve_position,
                        trv_entity_id,
                    )
                    updated = True

                if updated:
                    # Save to config entry
                    await self._save_config()
                    # Trigger valve control check with new settings
                    await self._async_control_valve(trv)
                    self.async_write_ha_state()
                return

        _LOGGER.error("TRV %s not found in room %s", trv_entity_id, self._attr_name)

    async def _save_config(self) -> None:
        """Save current configuration to config entry."""
        # Get current rooms from options, check explicitly for None to allow empty list
        if CONF_ROOMS in self.config_entry.options:
            rooms = list(self.config_entry.options[CONF_ROOMS])
        else:
            rooms = list(self.config_entry.data.get(CONF_ROOMS, []))

        # Find and update the current room's TRV configuration
        for i, room in enumerate(rooms):
            if room.get(CONF_ROOM_NAME) == self._room_name:
                # Create a deep copy to avoid reference issues
                updated_room = dict(room)
                # Deep copy TRVs list
                updated_room[CONF_TRVS] = [dict(trv) for trv in self._trvs]
                rooms[i] = updated_room
                break

        # Create deep copy of all rooms to avoid reference issues
        rooms_copy = []
        for room in rooms:
            room_copy = dict(room)
            if CONF_TRVS in room_copy:
                room_copy[CONF_TRVS] = [dict(trv) for trv in room_copy[CONF_TRVS]]
            rooms_copy.append(room_copy)

        # Update config entry with new data
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={**self.config_entry.options, CONF_ROOMS: rooms_copy},
        )

        _LOGGER.info("Saved configuration for room %s", self._room_name)
