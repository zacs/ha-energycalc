"""Services for EnergyCalc."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    SERVICE_CREATE_ENERGY_SENSOR,
    SERVICE_REMOVE_ENERGY_SENSOR,
    ATTR_SOURCE_ENTITY,
    ATTR_INTEGRATION_METHOD,
    ATTR_ROUND_DIGITS,
    DEFAULT_INTEGRATION_METHOD,
    DEFAULT_ROUND_DIGITS,
    DEFAULT_UNIT_PREFIX,
    DEFAULT_MAX_SUB_INTERVAL_MINUTES,
    INTEGRATION_METHOD_TRAPEZOIDAL,
    INTEGRATION_METHOD_LEFT,
    INTEGRATION_METHOD_RIGHT,
)
from .sensor import PowerTotalEnergyIntegrationSensor

_LOGGER = logging.getLogger(__name__)

CREATE_ENERGY_SENSOR_SCHEMA = vol.Schema({
    vol.Required(ATTR_SOURCE_ENTITY): cv.entity_id,
    vol.Optional(ATTR_INTEGRATION_METHOD, default=DEFAULT_INTEGRATION_METHOD): vol.In([
        INTEGRATION_METHOD_TRAPEZOIDAL,
        INTEGRATION_METHOD_LEFT,
        INTEGRATION_METHOD_RIGHT,
    ]),
    vol.Optional(ATTR_ROUND_DIGITS, default=DEFAULT_ROUND_DIGITS): vol.All(int, vol.Range(min=0, max=10)),
    vol.Optional("unit_prefix", default=DEFAULT_UNIT_PREFIX): vol.In(["", "k"]),
    vol.Optional("max_sub_interval_minutes", default=DEFAULT_MAX_SUB_INTERVAL_MINUTES): vol.All(int, vol.Range(min=1, max=60)),
})

REMOVE_ENERGY_SENSOR_SCHEMA = vol.Schema({
    vol.Required("entity_id"): cv.entity_id,
})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for EnergyCalc."""
    
    async def async_create_energy_sensor(call: ServiceCall) -> None:
        """Create an energy sensor for a power entity."""
        source_entity = call.data[ATTR_SOURCE_ENTITY]
        integration_method = call.data[ATTR_INTEGRATION_METHOD]
        round_digits = call.data[ATTR_ROUND_DIGITS]
        unit_prefix = call.data["unit_prefix"]
        max_sub_interval_minutes = call.data["max_sub_interval_minutes"]
        
        # Validate source entity exists and is a power sensor
        state = hass.states.get(source_entity)
        if not state:
            raise ServiceValidationError(f"Source entity {source_entity} not found")
            
        # Check if it's a power sensor
        unit = state.attributes.get("unit_of_measurement")
        if unit not in ["W", "watt", "watts"]:
            raise ServiceValidationError(f"Source entity {source_entity} is not a power sensor (unit: {unit})")
        
        # Generate names and IDs
        source_name = source_entity.replace("sensor.", "")
        sensor_name = f"{source_name.replace('_power', '').replace('power', '').strip('_')} Total Energy"
        unique_id = f"{source_name}_total_energy"
        
        # Check if sensor already exists
        entity_registry = er.async_get(hass)
        if entity_registry.async_get(f"sensor.{unique_id}"):
            raise ServiceValidationError(f"Energy sensor for {source_entity} already exists")
        
        # Create the sensor
        max_sub_interval = timedelta(minutes=max_sub_interval_minutes)
        
        sensor = PowerTotalEnergyIntegrationSensor(
            hass=hass,
            name=sensor_name,
            source_entity=source_entity,
            unique_id=unique_id,
            integration_method=integration_method,
            round_digits=round_digits,
            unit_prefix=unit_prefix,
            unit_time=UnitOfTime.HOURS,
            max_sub_interval=max_sub_interval,
        )
        
        # Add the sensor to the entity registry and platform
        if "sensor_platforms" in hass.data[DOMAIN]:
            for add_entities in hass.data[DOMAIN]["sensor_platforms"]:
                add_entities([sensor])
                break
        
        _LOGGER.info("Created energy sensor %s for power entity %s", sensor_name, source_entity)
    
    async def async_remove_energy_sensor(call: ServiceCall) -> None:
        """Remove an energy sensor."""
        entity_id = call.data["entity_id"]
        
        entity_registry = er.async_get(hass)
        entity_entry = entity_registry.async_get(entity_id)
        
        if not entity_entry:
            raise ServiceValidationError(f"Entity {entity_id} not found")
            
        if entity_entry.platform != DOMAIN:
            raise ServiceValidationError(f"Entity {entity_id} is not managed by {DOMAIN}")
        
        # Remove from entity registry
        entity_registry.async_remove(entity_id)
        
        _LOGGER.info("Removed energy sensor %s", entity_id)
    
    # Register services
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE_ENERGY_SENSOR,
        async_create_energy_sensor,
        schema=CREATE_ENERGY_SENSOR_SCHEMA,
    )
    
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_REMOVE_ENERGY_SENSOR,
        async_remove_energy_sensor,
        schema=REMOVE_ENERGY_SENSOR_SCHEMA,
    )