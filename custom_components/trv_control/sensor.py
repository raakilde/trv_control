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
    _LOGGER.info("Sensor platform setup starting for entry %s", config_entry.entry_id)

    # Retry logic to wait for climate entities to be available
    import asyncio

    climate_entities = None
    for attempt in range(10):  # Try for up to 5 seconds
        climate_entities = hass.data.get(DOMAIN, {}).get(config_entry.entry_id)
        if climate_entities:
            break
        _LOGGER.debug(
            "Climate entities not yet available, waiting... (attempt %d/10)",
            attempt + 1,
        )
        await asyncio.sleep(0.5)

    if not climate_entities:
        _LOGGER.error(
            "Could not find climate entities for config entry %s after waiting",
            config_entry.entry_id,
        )
        return

    # Ensure it's a list
    if not isinstance(climate_entities, list):
        climate_entities = [climate_entities]

    _LOGGER.info(
        "Setting up sensors for %d climate entities",
        len(climate_entities),
    )

    all_sensors = []

    # Create sensors for each climate entity (room)
    for climate_entity in climate_entities:
        _LOGGER.info(
            "Creating sensors for %s (has %d TRVs)",
            climate_entity.name,
            len(climate_entity._trvs),
        )

        # Use the climate entity's room name as the base name
        base_name = climate_entity._room_name

        sensors = []

        # Add sensors for each TRV
        for idx, trv in enumerate(climate_entity._trvs):
            trv_name = trv.get("name", f"TRV {idx + 1}")

            sensors.extend(
                [
                    TRVValvePositionSensor(climate_entity, trv, base_name, trv_name),
                    TRVReturnTempSensor(climate_entity, trv, base_name, trv_name),
                ]
            )

        # Add overall control sensors
        sensors.extend(
            [
                HeatingStatusSensor(climate_entity, base_name),
                TargetTempDifferenceSensor(climate_entity, base_name),
                AverageValvePositionSensor(climate_entity, base_name),
                HeatingDemandSensor(climate_entity, base_name),
                ControlEfficiencySensor(climate_entity, base_name),
                TemperatureTrendSensor(climate_entity, base_name),
                ReturnTempDeltaSensor(climate_entity, base_name),
            ]
        )

        # Add per-TRV diagnostic sensors
        for idx, trv in enumerate(climate_entity._trvs):
            trv_name = trv.get("name", f"TRV {idx + 1}")
            sensors.append(TRVHealthSensor(climate_entity, trv, base_name, trv_name))

        _LOGGER.info("Adding %d sensors for %s", len(sensors), climate_entity.name)
        all_sensors.extend(sensors)

    _LOGGER.info("Adding total of %d sensors to Home Assistant", len(all_sensors))
    for sensor in all_sensors:
        _LOGGER.debug("  - %s (unique_id: %s)", sensor.name, sensor.unique_id)

    async_add_entities(all_sensors)
    _LOGGER.info("Sensor platform setup complete")


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
        if (
            hasattr(self._climate_entity, "entity_id")
            and self._climate_entity.entity_id
        ):
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass,
                    self._climate_entity.entity_id,
                    _update,
                )
            )
        else:
            _LOGGER.warning(
                "Climate entity %s does not have entity_id yet, sensor %s may not update",
                self._climate_entity.name
                if hasattr(self._climate_entity, "name")
                else "unknown",
                self.name,
            )

        # Trigger initial update
        self.async_schedule_update_ha_state(True)


class TRVValvePositionSensor(TRVControlSensorBase):
    """Sensor for TRV valve position."""

    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:pipe-valve"

    def __init__(self, climate_entity, trv: dict, base_name: str, trv_name: str):
        """Initialize the sensor."""
        self._trv = trv
        self._trv_id = trv["trv"]
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
        self._trv_id = trv["trv"]
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


class AverageValvePositionSensor(TRVControlSensorBase):
    """Sensor for average valve position across all TRVs."""

    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:percent"

    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Average Valve Position")
        self._attr_unique_id = f"{climate_entity.unique_id}_avg_valve_position"

    @property
    def native_value(self) -> float | None:
        """Return the average valve position."""
        positions = []
        for trv_id, state in self._climate_entity._trv_states.items():
            valve_pos = state.get("valve_position")
            if valve_pos is not None:
                positions.append(valve_pos)

        if positions:
            return round(sum(positions) / len(positions), 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        positions = {}
        for trv in self._climate_entity._trvs:
            trv_id = trv["trv"]
            if trv_id in self._climate_entity._trv_states:
                trv_name = trv.get("name", trv_id.split(".")[-1])
                positions[trv_name] = self._climate_entity._trv_states[trv_id].get(
                    "valve_position"
                )
        return {"individual_positions": positions}


class HeatingDemandSensor(TRVControlSensorBase):
    """Sensor showing if any TRV is calling for heat."""

    _attr_icon = "mdi:fire-alert"

    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Heating Demand")
        self._attr_unique_id = f"{climate_entity.unique_id}_heating_demand"

    @property
    def native_value(self) -> str:
        """Return heating demand status."""
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature

        if current is None or target is None:
            return "unknown"

        # Check if any valve is open
        any_open = any(
            state.get("valve_position", 0) > 0
            for state in self._climate_entity._trv_states.values()
        )

        if current < target and any_open:
            return "heating"
        elif current < target and not any_open:
            return "demand_but_closed"
        elif current >= target:
            return "no_demand"
        return "unknown"

    @property
    def icon(self) -> str:
        """Return icon based on demand."""
        if self.native_value == "heating":
            return "mdi:fire"
        elif self.native_value == "demand_but_closed":
            return "mdi:alert-circle"
        elif self.native_value == "no_demand":
            return "mdi:fire-off"
        return "mdi:help-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        open_valves = sum(
            1
            for state in self._climate_entity._trv_states.values()
            if state.get("valve_position", 0) > 0
        )
        total_valves = len(self._climate_entity._trv_states)

        return {
            "open_valves": open_valves,
            "total_valves": total_valves,
            "temperature_below_target": (
                self._climate_entity.current_temperature
                < self._climate_entity.target_temperature
                if self._climate_entity.current_temperature
                and self._climate_entity.target_temperature
                else None
            ),
        }


class ControlEfficiencySensor(TRVControlSensorBase):
    """Sensor for control efficiency (how close to target)."""

    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:chart-line"

    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Control Efficiency")
        self._attr_unique_id = f"{climate_entity.unique_id}_control_efficiency"

    @property
    def native_value(self) -> float | None:
        """Return control efficiency (100% = perfect, lower = further from target)."""
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature

        if current is None or target is None:
            return None

        # Calculate efficiency: 100% when within 0.5°C, decreases with distance
        diff = abs(current - target)
        if diff <= 0.5:
            return 100.0
        elif diff <= 1.0:
            return 95.0
        elif diff <= 1.5:
            return 85.0
        elif diff <= 2.0:
            return 70.0
        elif diff <= 3.0:
            return 50.0
        else:
            return max(0, 100 - (diff * 20))

    @property
    def icon(self) -> str:
        """Return icon based on efficiency."""
        efficiency = self.native_value
        if efficiency is None:
            return "mdi:help-circle"
        elif efficiency >= 95:
            return "mdi:check-circle"
        elif efficiency >= 70:
            return "mdi:check"
        elif efficiency >= 50:
            return "mdi:alert"
        else:
            return "mdi:alert-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature

        attrs = {
            "current_temperature": current,
            "target_temperature": target,
        }

        if current and target:
            attrs["temperature_difference"] = round(abs(current - target), 1)
            attrs["within_0_5_degrees"] = abs(current - target) <= 0.5
            attrs["within_1_degree"] = abs(current - target) <= 1.0

        return attrs


class TemperatureTrendSensor(TRVControlSensorBase):
    """Sensor showing temperature trend (rising/falling/stable)."""

    _attr_icon = "mdi:chart-line-variant"

    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, name + " Temperature Trend")
        self._attr_unique_id = f"{climate_entity.unique_id}_temp_trend"
        self._previous_temp = None
        self._trend_count = 0

    @property
    def native_value(self) -> str:
        """Return temperature trend."""
        current = self._climate_entity.current_temperature

        if current is None:
            return "unknown"

        if self._previous_temp is None:
            self._previous_temp = current
            return "stable"

        diff = current - self._previous_temp

        if abs(diff) < 0.1:
            trend = "stable"
            self._trend_count = 0
        elif diff > 0:
            trend = "rising"
            self._trend_count = self._trend_count + 1 if self._trend_count > 0 else 1
        else:
            trend = "falling"
            self._trend_count = self._trend_count - 1 if self._trend_count < 0 else -1

        self._previous_temp = current
        return trend

    @property
    def icon(self) -> str:
        """Return icon based on trend."""
        if self.native_value == "rising":
            return "mdi:trending-up"
        elif self.native_value == "falling":
            return "mdi:trending-down"
        elif self.native_value == "stable":
            return "mdi:trending-neutral"
        return "mdi:help-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature

        attrs = {
            "current_temperature": current,
            "previous_temperature": self._previous_temp,
        }

        if current and self._previous_temp:
            attrs["change"] = round(current - self._previous_temp, 2)

        if current and target:
            attrs["needs_heating"] = current < target
            attrs["approaching_target"] = (
                current < target and self.native_value == "rising"
            ) or (current > target and self.native_value == "falling")

        return attrs


class ReturnTempDeltaSensor(TRVControlSensorBase):
    """Sensor showing temperature delta between room and return pipes."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:delta"

    def __init__(self, climate_entity, name: str):
        """Initialize the sensor."""
        super().__init__(climate_entity, f"{name} Return Temperature Delta")
        self._attr_unique_id = f"{climate_entity.unique_id}_return_temp_delta"

    @property
    def native_value(self) -> float | None:
        """Return average return temp delta."""
        current = self._climate_entity.current_temperature
        if current is None:
            return None

        deltas = []
        for state in self._climate_entity._trv_states.values():
            return_temp = state.get("return_temp")
            if return_temp is not None:
                deltas.append(return_temp - current)

        if deltas:
            return round(sum(deltas) / len(deltas), 1)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        current = self._climate_entity.current_temperature
        deltas = {}

        for trv in self._climate_entity._trvs:
            trv_id = trv["trv"]
            if trv_id in self._climate_entity._trv_states:
                return_temp = self._climate_entity._trv_states[trv_id].get(
                    "return_temp"
                )
                if return_temp and current:
                    trv_name = trv.get("name", trv_id.split(".")[-1])
                    deltas[trv_name] = round(return_temp - current, 1)

        return {
            "individual_deltas": deltas,
            "room_temperature": current,
        }


class TRVHealthSensor(TRVControlSensorBase):
    """Sensor for TRV health/responsiveness."""

    _attr_icon = "mdi:heart-pulse"

    def __init__(self, climate_entity, trv: dict, base_name: str, trv_name: str):
        """Initialize the sensor."""
        self._trv = trv
        self._trv_id = trv["trv"]
        super().__init__(climate_entity, f"{base_name} {trv_name} Health")
        self._attr_unique_id = (
            f"{climate_entity.unique_id}_{trv_name.lower().replace(' ', '_')}_health"
        )

    @property
    def native_value(self) -> str:
        """Return health status."""
        if self._trv_id not in self._climate_entity._trv_states:
            return "unknown"

        state = self._climate_entity._trv_states[self._trv_id]
        valve_pos = state.get("valve_position")
        return_temp = state.get("return_temp")
        valve_active = state.get("valve_control_active", False)

        # Check if data is stale (would need to implement last_updated tracking)
        if valve_pos is None or return_temp is None:
            return "no_data"

        if not valve_active:
            return "control_disabled"

        # Check if valve seems stuck
        current = self._climate_entity.current_temperature
        target = self._climate_entity.target_temperature

        if current and target and current < target - 1.0 and valve_pos == 0:
            return "possibly_stuck_closed"

        if return_temp and current and valve_pos > 0:
            delta = return_temp - current
            if delta < 1.0:  # Return pipe should be warmer when heating
                return "possibly_stuck_open"

        return "healthy"

    @property
    def icon(self) -> str:
        """Return icon based on health."""
        status = self.native_value
        if status == "healthy":
            return "mdi:check-circle"
        elif status in ["possibly_stuck_closed", "possibly_stuck_open"]:
            return "mdi:alert-circle"
        elif status == "no_data":
            return "mdi:help-circle"
        elif status == "control_disabled":
            return "mdi:power-off"
        return "mdi:help-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional attributes."""
        if self._trv_id in self._climate_entity._trv_states:
            state = self._climate_entity._trv_states[self._trv_id]
            return {
                "valve_position": state.get("valve_position"),
                "return_temperature": state.get("return_temp"),
                "valve_control_active": state.get("valve_control_active"),
                "status": state.get("status"),
                "status_reason": state.get("status_reason"),
            }
        return {}
