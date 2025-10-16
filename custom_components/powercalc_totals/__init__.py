"""The Power Calc Totals integration."""
from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_CREATE_ENERGY_SENSOR,
    SERVICE_REMOVE_ENERGY_SENSOR,
)
from .discovery import PowerDeviceDiscovery
from .services import async_setup_services

# Constants for your integration
PLATFORMS: list[Platform] = [Platform.SENSOR]

# YAML configuration schema
CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema({}),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Power Calc Totals component."""
    hass.data.setdefault(DOMAIN, {})
    
    # Set up services
    await async_setup_services(hass)
    
    # Only run discovery if domain is configured in YAML
    if DOMAIN in config:
        _LOGGER.info("Power Calc Totals configured in YAML, starting discovery")
        # Schedule discovery to run after Home Assistant has fully started
        # This ensures all entities and devices are loaded
        async def run_discovery():
            """Run discovery after startup."""
            import asyncio
            # Wait a bit to ensure all entities are loaded
            await asyncio.sleep(5)
            discovery = PowerDeviceDiscovery(hass)
            await discovery.async_discover_and_create_sensors()
        
        hass.async_create_task(run_discovery())
    else:
        _LOGGER.info("Power Calc Totals not configured in YAML, discovery disabled")
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Power Calc Totals from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    
    _LOGGER.info("Setting up config entry: %s with data: %s", entry.title, entry.data)
    
    # Only handle specific power entity entries - no main discovery entry needed
    if "power_entity_id" in entry.data:
        # This is a specific power entity entry - set up platforms for it
        _LOGGER.info("Power entity entry - setting up platforms for %s", entry.data["power_entity_id"])
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
