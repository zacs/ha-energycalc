"""Constants for the EnergyCalc integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "energycalc"

# Configuration
CONF_CREATE_ENERGY_SENSOR: Final = "create_energy_sensor"
CONF_POWER_ENTITY_ID: Final = "power_entity_id"
CONF_INTEGRATION_METHOD: Final = "integration_method"
CONF_ROUND_DIGITS: Final = "round_digits"
CONF_UNIT_PREFIX: Final = "unit_prefix"
CONF_MAX_SUB_INTERVAL: Final = "max_sub_interval"

# Defaults
DEFAULT_INTEGRATION_METHOD: Final = "trapezoidal"
DEFAULT_ROUND_DIGITS: Final = 2
DEFAULT_UNIT_PREFIX: Final = "k"
DEFAULT_MAX_SUB_INTERVAL_MINUTES: Final = 5

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