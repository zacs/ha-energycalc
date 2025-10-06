# Power Calc Totals

A Home Assistant custom component that automatically discovers devices with power sensors (W) but missing total energy sensors (kWh) and offers to create energy tracking entities. This is useful for integrating power-only devices with Home Assistant's Energy Dashboard.

## Overview

Many devices provide real-time power consumption data but don't track total energy usage over time. The Energy Dashboard in Home Assistant requires energy sensors (kWh) to function properly. This component bridges that gap by:

1. **Automatic Discovery**: Scans your Home Assistant instance for power entities (watts) that don't have corresponding energy entities (kWh)
2. **Energy Calculation**: Creates integration sensors that calculate total energy consumption using trapezoidal integration
3. **Energy Dashboard Integration**: Generated sensors work seamlessly with Home Assistant's Energy Dashboard

## Example Use Cases

- **Unifi PDU Pro**: Provides power data for each outlet but no energy totals
- **WattBox**: Similar to Unifi PDU, offers power monitoring without energy tracking
- **Smart Switches**: Many provide instantaneous power but lack energy accumulation
- **DIY Power Monitors**: Custom sensors that measure power but don't track totals

## Installation

### Manual Installation

1. Copy the `custom_components/powercalc_totals` directory to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Go to Settings → Devices & Services → Add Integration
4. Search for "Power Calc Totals" and follow the setup process

### HACS Installation

1. Add this repository to HACS as a custom repository
2. Search for "Power Calc Totals" in HACS
3. Install and restart Home Assistant
4. Add the integration through the UI

## Configuration

### Initial Setup

1. Navigate to **Settings** → **Devices & Services**
2. Click **Add Integration** and search for "Power Calc Totals"
3. Choose whether to automatically create energy sensors for discovered power entities
4. Complete the setup

### Manual Sensor Creation

You can manually create energy sensors using the provided services:

#### Create Energy Sensor Service

```yaml
service: powercalc_totals.create_energy_sensor
data:
  source_entity: sensor.device_power
  integration_method: trapezoidal  # Options: trapezoidal, left, right
  round_digits: 2
  unit_prefix: k  # 'k' for kWh, '' for Wh
  max_sub_interval_minutes: 5
```

#### Remove Energy Sensor Service

```yaml
service: powercalc_totals.remove_energy_sensor
data:
  entity_id: sensor.device_total_energy
```

## How It Works

### Discovery Process

The component analyzes your entity registry to find:
- **Power Entities**: Sensors with `W` or `watt` units and `power` device class
- **Missing Energy Entities**: Checks if corresponding energy sensors already exist

### Energy Calculation

Uses Home Assistant's built-in integration sensor with:
- **Trapezoidal Integration**: Default method for accurate energy calculation
- **Configurable Intervals**: Maximum 5-minute sub-intervals to balance accuracy and performance
- **Automatic Unit Conversion**: Converts watts to kilowatt-hours for Energy Dashboard compatibility

### Entity Naming

Generated entities follow this pattern:
- **Source**: `sensor.device_power`
- **Created**: `sensor.device_total_energy`

## Features

- ✅ **Automatic Discovery**: Finds power entities without energy counterparts
- ✅ **Flexible Integration**: Supports trapezoidal, left, and right integration methods
- ✅ **Energy Dashboard Ready**: Creates sensors compatible with HA Energy Dashboard
- ✅ **Manual Control**: Services for creating/removing sensors as needed
- ✅ **Device Association**: Maintains device relationships for organization
- ✅ **Configurable Precision**: Adjustable decimal places and units

## Similar Projects

This component is inspired by [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes), which performs similar device scanning and entity creation for battery-powered devices.

## Contributing

Issues and pull requests are welcome! Please check the existing issues before creating new ones.

## License

This project is licensed under the MIT License. 