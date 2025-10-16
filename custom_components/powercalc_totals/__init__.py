"""The Power Calc Totals integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_CREATE_ENERGY_SENSOR,
    SERVICE_REMOVE_ENERGY_SENSOR,
)
from .discovery import PowerDeviceDiscovery
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Power Calc Totals component."""
    hass.data.setdefault(DOMAIN, {})
    
    # Set up services
    await async_setup_services(hass)
    
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
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Power Calc Totals from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}
    
    _LOGGER.info("Setting up config entry: %s with data: %s", entry.title, entry.data)
    
    # Check if this is the main discovery config entry or a specific power entity entry
    if entry.data.get("setup_mode") == "discovery":
        # This is the main integration entry - run discovery but don't create platforms
        _LOGGER.info("Main integration entry - running discovery")
        discovery = PowerDeviceDiscovery(hass)
        await discovery.async_discover_and_create_sensors()
        # Don't set up platforms for the main entry - it's just for discovery
        return True
    elif "power_entity_id" in entry.data:
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
