# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-10-17

### Added
- Initial release of Power Calc Totals integration
- Automatic discovery of power entities without corresponding energy entities
- Real-time detection of new power sensors via entity registry listeners
- Periodic discovery every 24 hours as backup
- YAML configuration with exclude_entities support
- Device grouping for multi-outlet devices (PDUs, PoE switches, etc.)
- Individual discovery flows for entities without device association
- Manual services for creating/removing energy sensors with custom parameters
- Trapezoidal integration for accurate energy calculation
- Energy Dashboard compatibility with kWh output
- Complete device association and proper entity organization

### Features
- **Automatic Discovery**: Finds power entities without energy counterparts
- **Real-time Detection**: Discovers new power sensors immediately when added
- **Energy Dashboard Ready**: Creates sensors compatible with HA Energy Dashboard  
- **Manual Control**: Services for creating/removing sensors with custom settings
- **Device Association**: Maintains device relationships for organization
- **Exclude Entities**: YAML configuration to skip unwanted power sensors