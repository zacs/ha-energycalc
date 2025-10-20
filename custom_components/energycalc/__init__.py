"""The EnergyCalc integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED, EventEntityRegistryUpdatedData
from homeassistant.core import Event, callback

from .const import (
    DOMAIN,
    SERVICE_CREATE_ENERGY_SENSOR,
    SERVICE_REMOVE_ENERGY_SENSOR,
)
from .discovery import PowerDeviceDiscovery
from .services import async_setup_services

# Constants for your integration
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

# YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({
            vol.Optional("exclude_entities", default=[]): vol.All(cv.ensure_list, [cv.entity_id]),
        }),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the EnergyCalc component."""
    hass.data.setdefault(DOMAIN, {})
    
    # Set up services
    await async_setup_services(hass)
    
    # Only run discovery if domain is configured in YAML
    if DOMAIN in config:
        domain_config = config[DOMAIN]
        exclude_entities = domain_config.get("exclude_entities", [])
        _LOGGER.info("EnergyCalc configured in YAML, starting discovery with %d excluded entities", len(exclude_entities))
        
        # Store exclude_entities in hass.data for periodic discovery
        hass.data[DOMAIN]["exclude_entities"] = exclude_entities
        
        # Schedule initial discovery
        async def run_discovery():
            """Run discovery after startup."""
            import asyncio
            # Wait longer to ensure all entities are loaded (especially on large systems)
            _LOGGER.info("Starting initial discovery in 30 seconds...")
            await asyncio.sleep(30)
            _LOGGER.info("Running initial discovery now...")
            discovery = PowerDeviceDiscovery(hass, exclude_entities=exclude_entities)
            try:
                await discovery.async_discover_and_create_sensors()
                _LOGGER.info("Initial discovery completed successfully")
            except Exception as e:
                _LOGGER.error("Initial discovery failed: %s", e, exc_info=True)
        
        hass.async_create_task(run_discovery())
        
        # Set up periodic discovery every 24 hours (like Battery Notes)
        async def periodic_discovery(now=None):
            """Run periodic discovery for new devices."""
            _LOGGER.info("Running periodic device discovery...")
            discovery = PowerDeviceDiscovery(hass, exclude_entities=exclude_entities)
            try:
                await discovery.async_discover_and_create_sensors()
                _LOGGER.info("Periodic discovery completed successfully")
            except Exception as e:
                _LOGGER.error("Periodic discovery failed: %s", e, exc_info=True)
        
        # Schedule periodic discovery
        async_track_time_interval(hass, periodic_discovery, timedelta(hours=24))
        
        # Set up entity registry listener for real-time discovery (like Battery Notes)
        @callback
        async def entity_registry_updated(event: Event[EventEntityRegistryUpdatedData]) -> None:
            """Handle entity registry updates."""
            data = event.data
            action = data["action"]
            entity_id = data["entity_id"]
            
            # Care about both newly created entities and updated entities (template reloads)
            if action not in ["create", "update"]:
                return
                
            # Check if it's a sensor (domain check)
            if not entity_id.startswith("sensor."):
                return
            
            # Wait a moment for the entity state to be available
            import asyncio
            await asyncio.sleep(1)
            
            # Check if it might be a power sensor by getting the state
            state = hass.states.get(entity_id)
            if not state:
                return
                
            unit = state.attributes.get("unit_of_measurement")
            device_class = state.attributes.get("device_class")
            
            # Check for power sensors (with or without device_class, matching our discovery logic)
            if unit in ["W", "watt", "watts"] and (device_class == "power" or device_class is None):
                _LOGGER.info("New power sensor detected: %s, triggering discovery", entity_id)
                
                # Run discovery for the new entity
                discovery = PowerDeviceDiscovery(hass, exclude_entities=exclude_entities)
                await discovery.async_discover_and_create_sensors()
        
        # Register the entity registry listener
        hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, entity_registry_updated)
    else:
        _LOGGER.info("EnergyCalc not configured in YAML, discovery disabled")
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EnergyCalc from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    
    _LOGGER.info("Setting up config entry: %s with data: %s", entry.title, entry.data)
    
    # Only handle specific power entity entries - no main discovery entry needed
    if "power_entity_id" in entry.data or "power_entity_ids" in entry.data:
        # This is a power entity entry (single or multiple) - set up platforms for it
        if "power_entity_ids" in entry.data:
            entity_info = f"{len(entry.data['power_entity_ids'])} power entities"
        else:
            entity_info = entry.data["power_entity_id"]
        
        _LOGGER.info("Power entity entry - setting up platforms for %s", entity_info)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True
    else:
        _LOGGER.error("Unknown config entry type, data: %s", entry.data)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
