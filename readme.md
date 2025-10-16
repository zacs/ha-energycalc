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

### 1. Place Files
- Copy this folder to your Home Assistant `config/custom_components/` directory

### 2. Add to Configuration
- Add the following to your `configuration.yaml`:
```yaml
powercalc_totals:
```

#### Optional: Exclude Specific Entities
You can prevent certain power entities from being discovered by listing them in the `exclude_entities` configuration:
```yaml
powercalc_totals:
  exclude_entities:
    - sensor.zigbee_power_budget
    - sensor.ups_power_static
    - sensor.server_power_baseline
```

This is useful for excluding:
- Static/baseline power sensors that don't change
- Administrative power entities like "power budget" sensors
- Power sensors you don't want energy tracking for

### 3. Restart Home Assistant
- Restart your Home Assistant instance to load the integration

After setup, the component will:
- Automatically scan all your devices for power sensors without corresponding energy sensors
- Present discovered entities through the Integrations page
- Allow you to confirm and create energy sensors for each discovered power entity

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