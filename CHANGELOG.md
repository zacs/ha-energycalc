# Changelog

All notable changes to this project will be documented in this file.

## [2.0.0] - 2026-08-14

**Requires Home Assistant 2026.8.0 or newer.**

### Fixed
- Energy sensors failed to be created on Home Assistant 2026.8 with
  `IntegrationSensor.__init__() got an unexpected keyword argument 'hass'`.
- The reset button never reset anything: it looked up sensors in a registry
  that was keyed on entity IDs that did not exist yet, so it always fell
  through to writing a state that the sensor immediately overwrote.
- Resetting now clears long term statistics as well as states, so the Energy
  Dashboard and history graphs no longer keep showing the old totals. The
  previous implementation issued raw SQL against the recorder database.
- `energycalc.create_energy_sensor` did nothing. It passed arguments the sensor
  did not accept and stored the result where nothing read it.
- `energycalc.remove_energy_sensor` left the config entry and the reset button
  behind.
- Real time discovery never ran. The entity registry listener was registered as
  a callback but written as a coroutine, so it was silently dropped.
- Opening the integration's options dialog raised an `AttributeError` on recent
  Home Assistant versions. The dialog was empty, so it has been removed.
- Removing one power sensor from a multi sensor entry no longer changes the
  identity of the remaining energy sensors, which previously orphaned them and
  threw away their history.
- Power sensors already tracked by EnergyCalc are excluded from discovery, and
  EnergyCalc's own energy sensors no longer count as a device's energy sensor.
  A device where only some outlets were set up is now discoverable for the rest.
- Power sensors without a `device_class` now produce sensors that are usable on
  the Energy Dashboard.

### Changed
- **Device linking now follows Home Assistant's [updated pattern for helpers][helper-device-pattern].**
  Entities are attached to the source device with `device_entry` instead of
  describing that device with `device_info`. EnergyCalc no longer takes part
  ownership of devices belonging to other integrations, which Home Assistant
  stopped supporting in 2026.8. Entities still appear on the source device's
  page; EnergyCalc is simply no longer listed as an integration on it.
- Energy sensors are now keyed on the source entity's registry ID, so renaming
  a power sensor keeps the energy sensor and its history.
- Config entries follow their source entities. Renaming a power sensor updates
  the entry, and moving one to another device moves the energy sensor with it.
- The reset button is named "Reset energy" under its device, and reports
  failures as errors instead of creating a persistent notification.
- Discovery is debounced and runs once Home Assistant has finished starting,
  instead of on a fixed 30 second timer.
- The documented service defaults now match the code: `round_digits` is 3 and
  `max_sub_interval_minutes` is 1.
- `integration_type` is now `helper` rather than `device`.

### Added
- Manual setup from the UI. **Add Integration → EnergyCalc** now opens a form to
  pick power sensors and set the integration method, unit, precision and maximum
  sub-interval, instead of telling you to wait for discovery.
- A migration that moves existing entries onto the new device linking and
  unique ID scheme. Entity IDs and recorded history are preserved.
- A test suite covering setup, device linking, migration, discovery, the reset
  button and the services.

## [1.0.0] - 2025-10-17

### Added
- Initial release of EnergyCalc integration
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

[helper-device-pattern]: https://developers.home-assistant.io/blog/2025/07/18/updated-pattern-for-helpers-linking-to-devices/
