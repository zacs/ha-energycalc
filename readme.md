# EnergyCalc

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commit-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

A Home Assistant custom component that automatically discovers devices with power sensors (W) but missing total energy sensors (kWh) and offers to create energy tracking entities. This is useful for integrating power-only devices with Home Assistant's Energy Dashboard.

## Overview

Many devices provide real-time power consumption data but don't track total energy usage over time. The Energy Dashboard in Home Assistant requires energy sensors (kWh) to function properly. This component bridges that gap by:

1. **Automatic Discovery**: Scans your Home Assistant instance for power entities (watts) that don't have corresponding energy entities (kWh)
2. **Energy Calculation**: Creates integration sensors that calculate total energy consumption using trapezoidal integration
3. **Energy Dashboard Integration**: Generated sensors work seamlessly with Home Assistant's Energy Dashboard
4. **Device Integration**: Created sensors are automatically "appended" to existing devices (eg. they will show up on the device page automatically)

NOTE: The discovery happens at the device level, so if you have a device that has 5 power-monitored outlets, discovery will let you add the device as a whole (all 5 outlets), creating 5 new energy sensors linked to that device. 

## Example Use Cases

- **Smart Switches**: Many provide instantaneous power but lack energy accumulation
- **DIY Power Monitors**: Custom sensors that measure power but don't track totals
- **Unifi PDU Pro**: Provides power data for each outlet but no energy totals
- **PoE Switches**: Frequently offers power monitoring per-port without energy tracking

## Installation

### 1. Place Files
- Copy this folder to your Home Assistant `config/custom_components/` directory

### 2. Add to Configuration
- Add the following to your `configuration.yaml`:
```yaml
energycalc:
```

#### Optional: Exclude Specific Entities
You can prevent certain power entities from being discovered by listing them in the `exclude_entities` configuration:
```yaml
energycalc:
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
- Continue discovering new power sensors automatically (real-time + every 24 hours)

## How It Works

### Discovery Process

The component analyzes your entity registry to find:
- **Power Entities**: Sensors with `W` or `watt` units (device class is optional)
- **Missing Energy Entities**: Checks if corresponding energy sensors already exist

Note: The component will attempt to find devices first, but will also look for power entities that don't have a similarly-named corresponding energy entity. Please file bugs if you notice any weirdness with the entity-based discovery. 

### Energy Calculation

Uses Home Assistant's built-in integration sensor with:
- **Trapezoidal Integration**: Fixed method for accurate energy calculation
- **Automatic Unit Conversion**: Converts watts to kilowatt-hours for Energy Dashboard compatibility

### Entity Naming

Generated entities follow this pattern:
- **Source**: `sensor.device_power`
- **Created**: `sensor.device_energy` (removes "Power" suffix to avoid "Power Energy")

## Manual Control

While the integration primarily works through automatic discovery, you can also manually create and manage energy sensors using services:

### Create Energy Sensor
**Service**: `energycalc.create_energy_sensor`

Manually create an energy sensor for any power entity, with full control over calculation parameters.

**Parameters**:
- **source_entity** (required): The power sensor entity ID to track
- **integration_method** (optional): Calculation method - `trapezoidal` (default), `left`, or `right`
- **round_digits** (optional): Decimal places for the result (default: 2)
- **unit_prefix** (optional): `k` for kWh (default) or empty string for Wh
- **max_sub_interval_minutes** (optional): Maximum time between measurements (default: 5 minutes)

**Example**:
```yaml
service: energycalc.create_energy_sensor
data:
  source_entity: sensor.custom_device_power
  integration_method: trapezoidal
  round_digits: 3
  unit_prefix: k
  max_sub_interval_minutes: 2
```

### Remove Energy Sensor  
**Service**: `energycalc.remove_energy_sensor`

Remove an energy sensor created by this integration.

**Parameters**:
- **entity_id** (required): The energy sensor entity ID to remove

**Example**:
```yaml
service: energycalc.remove_energy_sensor
data:
  entity_id: sensor.custom_device_energy
```

**Use Cases for Manual Services**:
- Create energy sensors with custom precision or calculation methods
- Set up energy tracking for power entities that discovery missed
- Remove unwanted energy sensors
- Configure specific sub-interval timing for high-frequency monitoring

## Similar Projects

This component is inspired by [PowerCalc](https://github.com/bramstroker/homeassistant-powercalc) and [Battery Notes](https://github.com/andrew-codechimp/HA-Battery-Notes), which perform similar device scanning and entity creation to augment existing devices with useful new entities.

## Contributing

Issues and pull requests are welcome! Please check the existing issues before creating new ones.

## License

This project is licensed under the MIT License.

---

[energycalc]: https://github.com/zacs/energycalc
[commits-shield]: https://img.shields.io/github/commit-activity/y/zacs/energycalc.svg?style=for-the-badge
[commits]: https://github.com/zacs/energycalc/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/zacs/energycalc.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/zacs/energycalc.svg?style=for-the-badge
[releases]: https://github.com/zacs/energycalc/releases 