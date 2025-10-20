"""Device discovery for EnergyCalc."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfTime
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er, discovery_flow
from homeassistant.helpers.entity_registry import RegistryEntry

from .const import (
    DOMAIN,
    POWER_WATT,
    ENERGY_KILO_WATT_HOUR,
    ENERGY_WATT_HOUR,
)

_LOGGER = logging.getLogger(__name__)


class PowerDeviceDiscovery:
    """Discover devices with power entities but missing energy entities."""

    def __init__(self, hass: HomeAssistant, exclude_entities: list[str] | None = None) -> None:
        """Initialize the discovery."""
        self.hass = hass
        self.exclude_entities = exclude_entities or []
        self._discovered_entities: dict[str, dict[str, Any]] = {}

    def _clear_caches(self) -> None:
        """Clear internal caches for fresh discovery."""
        if hasattr(self, '_device_entities_cache'):
            delattr(self, '_device_entities_cache')
        if hasattr(self, '_states_cache'):
            delattr(self, '_states_cache')

    async def async_discover_and_create_sensors(self) -> None:
        """Discover power entities and create discovered integration entries."""
        _LOGGER.info("Starting power entity discovery...")
        
        # Clear any existing caches for fresh discovery
        self._clear_caches()
        
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        
        # Get all power entities
        power_entities = self._get_power_entities()
        _LOGGER.info("Found %d power entities to check", len(power_entities))
        
        # Filter entities that need energy sensors
        entities_needing_energy = []
        
        for power_entity in power_entities:
            if not self._has_energy_entity(power_entity, entity_registry):
                _LOGGER.debug("Power entity %s needs energy sensor", power_entity.entity_id)
                entities_needing_energy.append(power_entity)
        
        # Group entities by device
        device_groups = self._group_entities_by_device(entities_needing_energy)
        _LOGGER.info("Grouped entities into %d device groups", len(device_groups))
        
        # Create discovery flows per device
        discovered_count = 0
        for device_id, entities_group in device_groups.items():
            if device_id is None:
                # Handle entities without device_id individually
                for entity in entities_group:
                    await self._init_entity_discovery(entity, device_registry)
                    discovered_count += 1
            else:
                # Handle entities with device_id as a group
                await self._init_device_discovery(entities_group, device_registry)
                discovered_count += 1
        
        _LOGGER.info("Discovery complete. Created %d discovered integration entries", discovered_count)

    def _get_power_entities(self) -> list[RegistryEntry]:
        """Get all entities that measure power in watts."""
        registry = er.async_get(self.hass)
        power_entities = []
        total_sensors = 0
        disabled_count = 0
        no_state_count = 0
        
        # Pre-convert exclude list to set for O(1) lookup
        exclude_set = set(self.exclude_entities)
        
        # Get all states at once to reduce individual state lookups  
        all_states = self.hass.states.async_all()
        state_dict = {state.entity_id: state for state in all_states}
        
        # Log state loading stats for large systems
        available_states = sum(1 for state in all_states if state.state != "unavailable")
        _LOGGER.debug("Loaded %d states (%d available, %d unavailable)", 
                     len(all_states), available_states, len(all_states) - available_states)
        
        sensor_entities = [e for e in registry.entities.values() if e.domain == "sensor"]
        
        # Log some sample units to see what we're working with
        sample_units = set()
        sample_count = 0
        
        for entity in sensor_entities:
            total_sensors += 1
                
            # Early checks that don't require state lookup
            if (entity.disabled or entity.entity_id in exclude_set):
                if entity.disabled:
                    disabled_count += 1
                continue
                
            # Get the entity state from our pre-loaded dict, fallback to individual lookup
            state = state_dict.get(entity.entity_id)
            if not state:
                # Fallback to individual state lookup in case bulk approach missed it
                state = self.hass.states.get(entity.entity_id)
                if not state:
                    no_state_count += 1
                    continue
                
            # Check if it's a power sensor with watts as unit
            unit = state.attributes.get("unit_of_measurement")
            device_class = state.attributes.get("device_class")
            
            # Collect sample units for debugging (first 100)
            if sample_count < 100 and unit:
                sample_units.add(unit)
                sample_count += 1
            
            # Removed excessive debugging - discovery is working
            
            if (unit in [POWER_WATT, UnitOfPower.WATT] and 
                (device_class == "power" or device_class is None)):
                power_entities.append(entity)
        
        _LOGGER.info("Found %d power entities (scanned %d sensors, %d disabled, %d no state)", 
                    len(power_entities), total_sensors, disabled_count, no_state_count)
        return power_entities

    def _has_energy_entity(
        self, power_entity: RegistryEntry, entity_registry: er.EntityRegistry
    ) -> bool:
        """Check if there's already an energy entity for this power entity's device."""
        if not power_entity.device_id:
            # No device associated, check by entity name pattern
            return self._has_energy_entity_by_name(power_entity, entity_registry)
            
        # Use cached device entities to avoid repeated registry lookups
        device_id = power_entity.device_id
        if not hasattr(self, '_device_entities_cache'):
            self._device_entities_cache = {}
            
        if device_id not in self._device_entities_cache:
            device_entities = er.async_entries_for_device(entity_registry, device_id)
            self._device_entities_cache[device_id] = device_entities
        
        device_entities = self._device_entities_cache[device_id]
        
        # Use cached states for faster lookup
        if not hasattr(self, '_states_cache'):
            all_states = self.hass.states.async_all()
            self._states_cache = {state.entity_id: state for state in all_states}
        
        for entity in device_entities:
            if entity.disabled or entity.domain != "sensor":
                continue
                
            state = self._states_cache.get(entity.entity_id)
            if not state:
                continue
                
            unit = state.attributes.get("unit_of_measurement")
            device_class = state.attributes.get("device_class")
            
            if (unit in [ENERGY_KILO_WATT_HOUR, ENERGY_WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.WATT_HOUR] and 
                (device_class == "energy" or device_class is None)):
                return True
                
        return False

    def _has_energy_entity_by_name(
        self, power_entity: RegistryEntry, entity_registry: er.EntityRegistry
    ) -> bool:
        """Check for energy entity by similar naming pattern."""
        power_name = power_entity.entity_id.replace("sensor.", "")
        
        # Common patterns for energy sensors
        energy_patterns = [
            power_name.replace("_power", "_energy"),
            power_name.replace("_power", "_total_energy"),
            power_name.replace("power", "energy"),
            power_name.replace("power", "total_energy"),
            f"{power_name}_energy",
            f"{power_name}_total_energy",
        ]
        
        # Use cached states for faster lookup
        if not hasattr(self, '_states_cache'):
            all_states = self.hass.states.async_all()
            self._states_cache = {state.entity_id: state for state in all_states}
        
        for pattern in energy_patterns:
            energy_entity_id = f"sensor.{pattern}"
            if entity_registry.async_get(energy_entity_id):
                # Check if it's actually an energy sensor using cached state
                state = self._states_cache.get(energy_entity_id)
                if state:
                    unit = state.attributes.get("unit_of_measurement")
                    if unit in [ENERGY_KILO_WATT_HOUR, ENERGY_WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.WATT_HOUR]:
                        return True
                        
        return False

    def _group_entities_by_device(self, power_entities: list[RegistryEntry]) -> dict[str | None, list[RegistryEntry]]:
        """Group power entities by their device_id."""
        device_groups: dict[str | None, list[RegistryEntry]] = {}
        
        for entity in power_entities:
            device_id = entity.device_id
            if device_id not in device_groups:
                device_groups[device_id] = []
            device_groups[device_id].append(entity)
        
        return device_groups

    async def _init_device_discovery(
        self,
        power_entities: list[RegistryEntry],
        device_registry: dr.DeviceRegistry,
    ) -> None:
        """Create discovery flow for a device with multiple power entities."""
        if not power_entities:
            return
            
        # Use the first entity to determine device info, but all entities will be included
        primary_entity = power_entities[0]
        device_id = primary_entity.device_id
        
        # Check if we already have a config entry for this device
        expected_unique_id = f"energycalc_device_{device_id}" if device_id else f"energycalc_no_device_{primary_entity.entity_id}"
        existing_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == expected_unique_id
        ]
        if existing_entries:
            _LOGGER.debug(
                "Already have config entry for device %s, skipping discovery",
                device_id or "no_device",
            )
            return

        # Get device info if available
        device_entry = None
        if device_id:
            device_entry = device_registry.async_get(device_id)

        # Create discovery data with all power entities for this device
        power_entity_ids = [entity.entity_id for entity in power_entities]
        discovery_data: dict[str, Any] = {
            "power_entity_ids": power_entity_ids,  # Multiple entities
            "device_id": device_id,
            "area_id": primary_entity.area_id,
        }

        # Get device name based on the device or primary entity
        if device_entry:
            device_name = device_entry.name_by_user or device_entry.name
            if device_name:
                discovery_data["device_name"] = device_name
                discovery_data["manufacturer"] = device_entry.manufacturer
                discovery_data["model"] = device_entry.model
                _LOGGER.debug("Using device name: %s for device %s", device_name, device_id)
            else:
                # Fallback to primary entity name if device has no name
                entity_name = primary_entity.name or primary_entity.original_name
                discovery_data["device_name"] = entity_name or primary_entity.entity_id.replace("sensor.", "").replace("_", " ").title()
        else:
            # No device, use primary entity name
            entity_name = primary_entity.name or primary_entity.original_name
            discovery_data["device_name"] = entity_name or primary_entity.entity_id.replace("sensor.", "").replace("_", " ").title()

        # Create discovery flow with proper title
        device_name = discovery_data.get("device_name", "Unknown Device")
        entity_count = len(power_entities)
        _LOGGER.info("Creating discovery flow for device %s with %d power entities: %s", 
                    device_name, entity_count, ", ".join(power_entity_ids))
        
        try:
            unique_id = f"energycalc_device_{device_id}" if device_id else f"energycalc_no_device_{primary_entity.entity_id}"
            discovery_data["unique_id"] = unique_id
            
            discovery_flow.async_create_flow(
                self.hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=discovery_data,
            )
            _LOGGER.info("Discovery flow created successfully for device %s", device_name)
        except Exception as e:
            _LOGGER.error("Failed to create discovery flow for device %s: %s", device_name, e)

    async def _init_entity_discovery(
        self,
        power_entity: RegistryEntry,
        device_registry: dr.DeviceRegistry,
    ) -> None:
        """Create discovery flow for a power entity."""
        # Check if we already have a config entry for this entity
        existing_entries = [
            entry
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.unique_id == f"energycalc_{power_entity.entity_id}"
        ]
        if existing_entries:
            _LOGGER.debug(
                "Already have config entry for %s, skipping discovery",
                power_entity.entity_id,
            )
            return

        # Get device info if available
        device_entry = None
        if power_entity.device_id:
            device_entry = device_registry.async_get(power_entity.device_id)

        # Create discovery data
        discovery_data: dict[str, Any] = {
            "power_entity_id": power_entity.entity_id,
            "unique_id": power_entity.unique_id,
            "device_id": power_entity.device_id,
            "area_id": power_entity.area_id,
        }

        # Get the best available name, combining device and entity names for clarity
        entity_name = power_entity.name or power_entity.original_name
        device_name = None
        
        if device_entry:
            device_name = device_entry.name_by_user or device_entry.name
        
        if entity_name and device_name and entity_name != device_name:
            # Combine device and entity names for multi-outlet devices: "Parent Device: Outlet Name"
            # Check if entity name already contains device name to avoid duplication
            if device_name.lower() in entity_name.lower():
                # Entity already contains device name, use as-is
                discovery_data["device_name"] = entity_name
                _LOGGER.debug("Using entity name (contains device): %s for %s", entity_name, power_entity.entity_id)
            else:
                # Combine: "Device Name: Entity Name"
                discovery_data["device_name"] = f"{device_name}: {entity_name}"
                _LOGGER.debug("Using combined name: %s for %s", discovery_data["device_name"], power_entity.entity_id)
        elif entity_name:
            # Use entity name only
            discovery_data["device_name"] = entity_name
            _LOGGER.debug("Using entity name: %s for %s", entity_name, power_entity.entity_id)
        elif device_name:
            # Use device name only
            discovery_data["device_name"] = device_name
            _LOGGER.debug("Using device name: %s for %s", device_name, power_entity.entity_id)
        else:
            # Last resort: use entity ID without sensor prefix
            discovery_data["device_name"] = power_entity.entity_id.replace("sensor.", "").replace("_", " ").title()
            _LOGGER.debug("Using entity ID-based name: %s for %s", discovery_data["device_name"], power_entity.entity_id)
        
        # Add device info if available
        if device_entry:
            discovery_data["manufacturer"] = device_entry.manufacturer
            discovery_data["model"] = device_entry.model


        # Create discovery flow with proper title
        device_name = discovery_data.get("device_name", "Unknown Device")
        _LOGGER.info("Creating discovery flow for %s (device: %s)", power_entity.entity_id, device_name)
        try:
            discovery_flow.async_create_flow(
                self.hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=discovery_data,
            )
            _LOGGER.info("Discovery flow created successfully for %s", power_entity.entity_id)
        except Exception as e:
            _LOGGER.error("Failed to create discovery flow for %s: %s", power_entity.entity_id, e)

    @callback
    def get_discovered_entities(self) -> dict[str, dict[str, Any]]:
        """Get all discovered entities that need energy sensors."""
        return self._discovered_entities

    @callback
    def remove_discovered_entity(self, power_entity_id: str) -> None:
        """Remove an entity from the discovered list."""
        self._discovered_entities.pop(power_entity_id, None)