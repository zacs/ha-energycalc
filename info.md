# Power Calc Totals

Automatically discovers devices with power sensors (W) but missing energy sensors (kWh) and creates energy tracking entities for Home Assistant's Energy Dashboard.

## Key Features

- **🔍 Automatic Discovery**: Scans for power entities without energy counterparts
- **⚡ Real-time Detection**: Discovers new power sensors immediately when added  
- **📊 Energy Dashboard Ready**: Creates sensors compatible with HA Energy Dashboard
- **🛠️ Manual Control**: Services for creating/removing sensors with custom settings
- **🔗 Device Association**: Maintains device relationships for organization
- **🚫 Exclude Entities**: YAML configuration to skip unwanted power sensors

## Quick Setup

1. **Install via HACS** or copy to `custom_components/powercalc_totals/`
2. **Add to configuration.yaml**:
   ```yaml
   powercalc_totals:
   ```
3. **Restart Home Assistant**
4. **Check Integrations page** for discovered power devices

## Use Cases

Perfect for devices that provide power data but no energy totals:
- **Unifi PDU Pro** / **WattBox** - Multi-outlet power distribution units
- **Smart Switches** - Power monitoring without energy accumulation  
- **DIY Power Monitors** - Custom sensors measuring instantaneous power
- **Template Sensors** - Calculated power values needing energy tracking

## Configuration

### Basic Setup
```yaml
powercalc_totals:
```

### Exclude Unwanted Sensors
```yaml
powercalc_totals:
  exclude_entities:
    - sensor.power_budget
    - sensor.baseline_power
    - sensor.static_load
```

## How It Works

1. **Scans** your entity registry for power sensors (W/watt units)
2. **Checks** if corresponding energy sensors already exist
3. **Creates** discovery flows for missing energy entities
4. **Groups** multi-outlet devices together for clean organization
5. **Continues** monitoring for new power sensors automatically

Generated energy sensors use trapezoidal integration for accurate energy calculation and are compatible with Home Assistant's Energy Dashboard.

## Advanced Usage

Manual services available for custom configuration:
- `powercalc_totals.create_energy_sensor` - Create with custom settings
- `powercalc_totals.remove_energy_sensor` - Remove unwanted sensors

See the [full documentation](https://github.com/zacs/powercalc_totals) for complete details.