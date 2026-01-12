# TRV Control Custom Card

A custom Lovelace card for displaying TRV Control integration information in Home Assistant.

## Installation

### Manual Installation

1. Copy `trv-control-card.js` to your `config/www/` folder
2. Add the resource in your Lovelace dashboard:
   - Go to Settings → Dashboards → Resources
   - Click "Add Resource"
   - URL: `/local/trv-control-card.js`
   - Resource type: JavaScript Module

### HACS Installation (if you publish to HACS)

1. Open HACS
2. Go to "Frontend"
3. Search for "TRV Control Card"
4. Click Install

## Configuration

Add the card to your Lovelace dashboard:

```yaml
type: custom:trv-control-card
entity: climate.your_trv_control_entity
```

### Example

```yaml
type: custom:trv-control-card
entity: climate.test_trv_control
```

## Features

- **Temperature Display**: Shows current room temperature vs target temperature
- **Status Badge**: Visual indicator of heating status (heating, target reached, off, window open)
- **Window Sensor**: Displays window open/closed state
- **Per-TRV Information**: 
  - Return temperature
  - Valve position with visual bar
  - Close/open thresholds
  - Max valve position
  - Status reason explanation
- **Responsive Design**: Adapts to Home Assistant themes

## Screenshot

The card displays:
- Large temperature values for quick glance
- Color-coded status indicators
- Individual TRV cards with detailed information
- Visual valve position bar
- Detailed status reasons for troubleshooting

## Attributes Used

The card automatically reads all attributes from your TRV Control climate entity:
- `current_temperature`
- `temperature` (target)
- `heating_status`
- `window_open`
- `temp_sensor`
- `window_sensor`
- Per-TRV attributes (automatically detected):
  - `[name]_entity`
  - `[name]_return_temp`
  - `[name]_valve_position`
  - `[name]_status`
  - `[name]_status_reason`
  - And more...
