"""Constants for the EnergyCalc integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "energycalc"

# Minimum Home Assistant version. 2026.8 removed the ``hass`` argument from
# ``IntegrationSensor.__init__`` and added ``async_remove_helper_devices``,
# both of which this integration relies on.
MIN_HA_VERSION: Final = "2026.8.0"

# Config entry schema version
CONFIG_VERSION: Final = 1
CONFIG_MINOR_VERSION: Final = 2

# Configuration
CONF_CREATE_ENERGY_SENSOR: Final = "create_energy_sensor"
CONF_POWER_ENTITY_ID: Final = "power_entity_id"
CONF_POWER_ENTITY_IDS: Final = "power_entity_ids"
CONF_DEVICE_NAME: Final = "device_name"
CONF_EXCLUDE_ENTITIES: Final = "exclude_entities"
CONF_INTEGRATION_METHOD: Final = "integration_method"
CONF_ROUND_DIGITS: Final = "round_digits"
CONF_UNIT_PREFIX: Final = "unit_prefix"
CONF_MAX_SUB_INTERVAL_MINUTES: Final = "max_sub_interval_minutes"

# Defaults. These mirror the values EnergyCalc has always used when creating
# sensors, so existing installations keep their current behaviour.
DEFAULT_INTEGRATION_METHOD: Final = "trapezoidal"
DEFAULT_ROUND_DIGITS: Final = 3
DEFAULT_UNIT_PREFIX: Final = "k"
DEFAULT_MAX_SUB_INTERVAL_MINUTES: Final = 1

# Discovery
DISCOVERY_INTERVAL_HOURS: Final = 24
DISCOVERY_DEBOUNCE_SECONDS: Final = 30

# Service names
SERVICE_CREATE_ENERGY_SENSOR: Final = "create_energy_sensor"
SERVICE_REMOVE_ENERGY_SENSOR: Final = "remove_energy_sensor"

# Entity attributes
ATTR_SOURCE_ENTITY: Final = "source_entity"
ATTR_INTEGRATION_METHOD: Final = "integration_method"
ATTR_ROUND_DIGITS: Final = "round_digits"

# Power and energy units
POWER_WATT: Final = "W"
ENERGY_KILO_WATT_HOUR: Final = "kWh"
ENERGY_WATT_HOUR: Final = "Wh"

# Integration methods
INTEGRATION_METHOD_TRAPEZOIDAL: Final = "trapezoidal"
INTEGRATION_METHOD_LEFT: Final = "left"
INTEGRATION_METHOD_RIGHT: Final = "right"
INTEGRATION_METHODS: Final = [
    INTEGRATION_METHOD_TRAPEZOIDAL,
    INTEGRATION_METHOD_LEFT,
    INTEGRATION_METHOD_RIGHT,
]
