# EnergyCalc

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

<img src="icons/icon.png">

EnergyCalc is a Home Assistant custom component that automatically discovers devices with power sensors (W) but missing total energy sensors (kWh) and offers to create energy tracking entities. This is useful for integrating power-only devices with Home Assistant's Energy Dashboard.

## Overview

Many devices provide real-time power consumption data but don't track total energy usage over time. The Energy Dashboard in Home Assistant requires energy sensors (kWh) to function properly. This component bridges that gap by:

1. **Automatic Discovery**: Scans your Home Assistant instance for power entities (watts) that don't have corresponding energy entities (kWh)
2. **Energy Calculation**: Creates integration sensors that calculate total energy consumption using trapezoidal integration
3. **Energy Dashboard Integration**: Generated sensors work seamlessly with Home Assistant's Energy Dashboard
4. **Device Integration**: Created sensors are linked to the existing device, so they show up on that device's page automatically

NOTE: The discovery happens at the device level, so if you have a device like a power strip that has 5 power-monitored outlets, discovery will let you add the device as a whole (all 5 outlets), creating 5 new energy sensors linked to that device.

## Requirements

Home Assistant **2026.8.0** or newer.

## Example Use Cases

- **Smart Switches**: Many provide instantaneous power but lack energy accumulation
- **DIY Power Monitors**: Custom sensors that measure power but don't track totals
- **Unifi PDU Pro**: Provides power data for each outlet but no energy totals
- **PoE Switches**: Frequently offers power monitoring per-port without energy tracking

## Installation

### 1. Install component

- Install the component via HACS (just search for "energycalc")

Alternatively, you can manually install it:
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
    - sensor.device1_power_budget
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

Energy sensors that EnergyCalc created itself are ignored during this check, so
a device where only some outlets are covered stays discoverable for the rest.

### Energy Calculation

Uses Home Assistant's built-in integration sensor with:
- **Trapezoidal Integration**: Fixed method for accurate energy calculation
- **Automatic Unit Conversion**: Converts watts to kilowatt-hours for Energy Dashboard compatibility

### Entity Naming

Generated entities follow this pattern:
- **Source**: `sensor.device_power`
- **Created**: `sensor.device_energy`

### Device Linking

EnergyCalc entities are attached to the device that owns the source power
sensor, so they appear on that device's page alongside the original entities.

EnergyCalc itself is not listed as an integration on the device page, and it
never takes ownership of a device it did not create. This follows Home
Assistant's [pattern for helpers linking to devices][helper-device-pattern],
which became mandatory in 2026.8. To reconfigure or delete the energy sensors,
use the EnergyCalc entry on the Integrations page.

If a power sensor is renamed or moved to a different device, EnergyCalc follows
it: the energy sensor keeps its history and moves to the new device.

### Resetting

Each EnergyCalc entry adds a **Reset energy** button. Pressing it zeroes the
energy sensors of that entry and purges their recorded history, including the
long term statistics that back the Energy Dashboard.

## Manual Control

Discovery only *suggests* devices, so you can also add power sensors yourself.

### Add from the UI

Go to **Settings → Devices & Services → Add Integration → EnergyCalc** and pick
one or more power sensors. The same form lets you choose the integration method,
the unit, the precision and the maximum sub-interval. This is the easiest way to
add a sensor that discovery skipped, for example one on a device that already
reports energy for a different circuit.

### Services

You can also manage energy sensors from scripts and automations:

### Create Energy Sensor
**Service**: `energycalc.create_energy_sensor`

Manually create an energy sensor for any power entity, with full control over calculation parameters.

**Parameters**:
- **source_entity** (required): The power sensor entity ID to track
- **integration_method** (optional): Calculation method - `trapezoidal` (default), `left`, or `right`
- **round_digits** (optional): Decimal places for the result (default: 3)
- **unit_prefix** (optional): `k` for kWh (default) or empty string for Wh
- **max_sub_interval_minutes** (optional): Maximum time between measurements (default: 1 minute)

**Example**:
```yaml
action: energycalc.create_energy_sensor
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
action: energycalc.remove_energy_sensor
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

### Running the tests

```bash
python3 -m venv venv
venv/bin/pip install -r requirements_test.txt
venv/bin/python -m pytest
```

## License

This project is licensed under the MIT License.

---

[energycalc]: https://github.com/zacs/ha-energycalc
[helper-device-pattern]: https://developers.home-assistant.io/blog/2025/07/18/updated-pattern-for-helpers-linking-to-devices/
[commits-shield]: https://img.shields.io/github/commit-activity/y/zacs/ha-energycalc.svg?style=for-the-badge
[commits]: https://github.com/zacs/ha-energycalc/commits/main
[hacs]: https://github.com/hacs/integration
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/zacs/ha-energycalc.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/zacs/ha-energycalc.svg?style=for-the-badge
[releases]: https://github.com/zacs/ha-energycalc/releases 