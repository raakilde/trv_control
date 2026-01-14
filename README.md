# TRV Control - Home Assistant Custom Component

A custom component for controlling Thermostatic Radiator Valves with Zigbee2MQTT in Home Assistant. Designed specifically for managing multiple rooms with external temperature sensors and return temperature monitoring.

## Features

### Room-Based Control
- **Multiple Rooms**: Add unlimited rooms under a single integration instance
- **Per-Room Configuration**: Each room has its own TRV, temperature sensor, and return temp sensor
- **Individual Settings**: Customize valve position limits and temperature thresholds per room

### Temperature Management
- **External Temperature Control**: Uses Zigbee2MQTT temperature sensors instead of TRV internal sensors
- **Automatic Refresh**: Sends target temperature to TRV every 5 minutes (prevents Sonoff TRV from defaulting to internal sensor)
- **Return Temperature Monitoring**: Tracks radiator return temperature for system efficiency
- **Automatic Valve Control**: Closes valve when return temp ≥ 32°C, opens when ≤ 30°C (configurable)

### Window Detection
- **Automatic Shutoff**: Monitors window sensors and turns off heating when window opens
- **Smart Resume**: Automatically restores previous heating mode when window closes
- **Energy Savings**: Prevents wasted heating with open windows

### Valve Control
- **Automatic Position Control**: Manages valve opening based on return temperature
- **Manual Valve Position**: Override with manual control (0-100%)
- **Configurable Max Position**: Limit maximum valve opening per room
- **Multi-Method Support**: Uses both number entity and MQTT commands for broad TRV compatibility
- **Status Tracking**: View valve control state and position in entity attributes

### Smart Integration
- **Zigbee2MQTT Support**: Designed for Z2M climate and sensor entities
- **Real-time Updates**: Monitors all sensors and updates immediately
- **Service Calls**: Control valves and thresholds via Home Assistant services

## Installation

### HACS (Recommended)
1. Add this repository to HACS as a custom repository
2. Install "TRV Control" through HACS
3. Restart Home Assistant

### Manual Installation
1. Copy the `custom_components/trv_control` folder to your Home Assistant `custom_components` directory
2. Restart Home Assistant

## Configuration

### Initial Setup
1. Go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "TRV Control"
4. Click to create the integration (no initial configuration needed)

### Adding Rooms
1. Click "Configure" on the TRV Control integration
2. Select "Add Room"
3. Configure the room:
   - **Room Name**: e.g., "Living Room", "Bedroom"
   - **Temperature Sensor**: Z2M temperature sensor entity
   - **TRV Device**: Z2M climate entity (e.g., Sonoff TRVZB)
   - **Return Temperature Sensor**: Z2M sensor on radiator return pipe
   - **Window Sensor** (optional): Binary sensor for window open/close detection
   - **Return Temp Close** (default: 32°C): Temperature to trigger valve closure
   - **Return Temp Open** (default: 30°C): Temperature to reopen valve
   - **Max Valve Position** (default: 100%): Maximum valve opening percentage

### Managing Rooms
- **Add Room**: Add additional rooms
- **Remove Room**: Delete a room configuration
- **List Rooms**: View all configured rooms

## Usage

### Entity Attributes

Each room creates a climate entity with these attributes:

```yaml
# Example: climate.living_room_trv_control
current_temperature: 21.5          # From temperature sensor
target_temperature: 22.0           # Your setpoint
return_temperature: 28.3           # From return temp sensor
current_valve_position: 75         # Current valve opening %
max_valve_position: 100            # Configured max
return_temp_close_threshold: 32.0  # Auto-close valve at this temp
return_temp_open_threshold: 30.0   # Auto-open valve at this temp
valve_control_active: false        # True when valve auto-closed
window_sensor: binary_sensor.window # Window sensor entity (if configured)
window_open: false                 # Window state
temp_sensor: sensor.living_room_temp
trv: climate.living_room_trv
return_temp_sensor: sensor.living_room_return
```

### Services

#### Set Valve Position
Manually control the valve opening percentage:

```yaml
service: trv_control.set_valve_position
target:
  entity_id: climate.living_room_trv_control
data:
  position: 50  # 0-100%
```

#### Set Return Temperature Thresholds
Adjust the monitoring thresholds:

```yaml
service: trv_control.set_return_thresholds
target:
  entity_id: climate.living_room_trv_control
data:
  close_temp: 35.0  # °C
  open_temp: 32.0   # °C
```

## How It Works

### Temperature Control
1. Component reads external temperature sensor for accurate room temperature
2. When you change setpoint via UI or service:
   - Updates virtual entity target temperature
   - Immediately sends new setpoint to physical TRV
   - TRV adjusts its target temperature
3. Sends target temperature to TRV every 5 minutes (keeps TRV synchronized)
4. TRV uses external temperature instead of internal sensor
5. Prevents temperature drift and inaccurate readings

### Return Temperature Monitoring & Valve Control
1. Monitors return pipe temperature continuously
2. **Auto-close**: When return temp ≥ close threshold (default 32°C)
   - Sets valve position to 0%
   - Sets `valve_control_active` to true
   - Prevents overheating and balances system
3. **Auto-open**: When return temp ≤ open threshold (default 30°C)
   - Restores valve to max position
   - Sets `valve_control_active` to false
   - Resumes normal heating
4. Uses both number entity and MQTT methods for broad compatibility

### Window Detection
1. Monitors configured window sensor continuously
2. **Window opens**:
   - Saves current HVAC mode
   - Turns heating off immediately
   - Prevents operation while window is open
3. **Window closes**:
   - Restores previous HVAC mode
   - Resumes normal operation
4. Manual turn-on blocked while window remains open

## Compatible Devices

### Tested TRVs (Zigbee2MQTT)
- Sonoff TRVZB
- Other Z2M compatible TRVs

### Temperature Sensors
- Any Z2M temperature sensor
- Aqara Temperature/Humidity sensors
- Sonoff SNZB-02 Temperature sensors
- Other Zigbee temperature sensors

## Troubleshooting

### TRV not responding to temperature changes
- Verify Z2M is working and TRV is online
- Check the 5-minute refresh is working (see debug logs)
- Ensure TRV entity ID is correct

### Temperature sensor not updating
- Check Z2M integration is working
- Verify sensor entity ID in configuration
- Check sensor battery level

### Valve position not changing
- Ensure your TRV supports position commands
- Check MQTT topic is correct for your device
- Review debug logs for "Could not set valve position" messages
- Try using the manual service call to test

### Window detection not working
- Verify window sensor entity ID is correct
- Check sensor reports "on"/"open" when window is open
- Review entity attributes to see `window_open` status
- Check logs for "Window opened/closed" messages

### Heating won't turn on
- Check if window is open (`window_open: true` in attributes)
- Check if return temp control is active (`valve_control_active: true`)
- Verify return temperature is below open threshold
- Close window and wait for sensor to update

## Development

This component follows Home Assistant integration structure and best practices.

### Development Environment

#### Requirements
- VSCode
- Docker
- Dev Containers extension

#### Setup
1. Clone the repository
2. Open the repository in VSCode
3. Click on the green button in the bottom left corner and select "Reopen in Container"
4. Wait for the container to build
5. Run the setup script: `./scripts/setup`
6. Start Home Assistant: Run Task "Run Home Assistant on port 9123" or `./scripts/start`
7. Open browser: http://localhost:9123

#### Development Tasks (VSCode)

Use Command Palette (Ctrl+Shift+P) → "Tasks: Run Task":
- **Run Home Assistant on port 9123**: Start HA with your component loaded
- **Sync configuration.yaml**: Copy test config to HA config directory
- **Upgrade Home Assistant to latest dev**: Update to latest HA dev version
- **Install a specific version of Home Assistant**: Install specific HA version

#### Debug Configuration

The dev container includes VSCode debug configuration:
1. Set breakpoints in your code
2. Press F5 or Run → Start Debugging
3. Select "HomeAssistant" configuration
4. Home Assistant will start in debug mode

#### Test Configuration

The `.devcontainer/configuration.yaml` includes:
- **2 Rooms**: Living Room and Bedroom
- **Dummy TRV entities**: Simulating Sonoff TRVZB devices
- **Temperature sensors**: External room sensors for each room
- **Return temp sensors**: Radiator return temperature sensors
- **Window sensors**: Binary sensors for window detection
- **Valve position controls**: Number entities for testing valve control

Adjust the `input_number` sliders in the UI to simulate:
- Temperature changes
- Return temperature changes (test auto-close at 32°C)
- Window opening/closing
- Valve position changes

#### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=custom_components.trv_control --cov-report=html

# Run specific test file
pytest tests/test_climate.py

# Run specific test
pytest tests/test_climate.py::test_return_temp_control_close_valve
```

### Structure
```
custom_components/trv_control/
├── __init__.py          # Integration setup and services
├── climate.py           # Climate entity platform
├── config_flow.py       # UI configuration flow
├── const.py            # Constants and defaults
├── manifest.json       # Integration metadata
├── services.yaml       # Service definitions
└── strings.json        # UI translations

.devcontainer/
├── devcontainer.json   # Dev container configuration
└── configuration.yaml  # Test Home Assistant config

.vscode/
├── launch.json         # Debug configurations
└── tasks.json          # VSCode tasks

scripts/
├── setup               # Initial setup script
├── start               # Start Home Assistant
├── sync                # Sync configuration
├── upgrade-dev         # Upgrade to latest HA dev
└── upgrade-version     # Install specific HA version

tests/
├── conftest.py         # Test fixtures
├── const.py            # Test constants
├── test_climate.py     # Climate platform tests
└── test_config_flow.py # Config flow tests
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
