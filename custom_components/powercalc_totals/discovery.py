"""Device discovery for Power Calc Totals."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import UnitOfPower, UnitOfEnergy, UnitOfTime
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

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the discovery."""
        self.hass = hass
        self._discovered_entities: dict[str, dict[str, Any]] = {}

    async def async_discover_and_create_sensors(self) -> None:
        """Discover power entities and create discovered integration entries."""
        _LOGGER.info("Starting power entity discovery...")
        
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        
        # Get all power entities
        power_entities = self._get_power_entities(entity_registry)
        _LOGGER.info("Found %d power entities to check", len(power_entities))
        
        discovered_count = 0
        for power_entity in power_entities:
            # Check if there's already an energy entity for this device
            if not self._has_energy_entity(power_entity, entity_registry):
                _LOGGER.info(
                    "Found power entity %s without corresponding energy entity",
                    power_entity.entity_id
                )
                
                # Create discovery flow for this entity
                await self._init_entity_discovery(power_entity, device_registry)
                discovered_count += 1
            else:
                _LOGGER.debug(
                    "Power entity %s already has energy entity, skipping",
                    power_entity.entity_id
                )
        
        _LOGGER.info("Discovery complete. Created %d discovered integration entries", discovered_count)

    def _get_power_entities(self, entity_registry: er.EntityRegistry) -> list[RegistryEntry]:
        """Get all entities that measure power in watts."""
        power_entities = []
        total_sensors = 0
        disabled_count = 0
        no_state_count = 0
        
        for entity in entity_registry.entities.values():
            if entity.domain == "sensor":
                total_sensors += 1
                
            # Skip disabled entities
            if entity.disabled:
                disabled_count += 1
                continue
                
            # Get the entity state to check unit
            state = self.hass.states.get(entity.entity_id)
            if not state:
                no_state_count += 1
                continue
                
            # Check if it's a power sensor with watts as unit
            unit = state.attributes.get("unit_of_measurement")
            device_class = state.attributes.get("device_class")
            
            if (
                entity.domain == "sensor" 
                and unit in [POWER_WATT, UnitOfPower.WATT]
                and (device_class == "power" or device_class is None)
            ):
                power_entities.append(entity)
                _LOGGER.debug(
                    "Found power entity: %s (unit=%s, device_class=%s)",
                    entity.entity_id, unit, device_class
                )
        
        _LOGGER.info(
            "Scanned %d total sensors, %d disabled, %d no state, found %d power entities",
            total_sensors, disabled_count, no_state_count, len(power_entities)
        )
        return power_entities

    def _has_energy_entity(
        self, power_entity: RegistryEntry, entity_registry: er.EntityRegistry
    ) -> bool:
        """Check if there's already an energy entity for this power entity's device."""
        if not power_entity.device_id:
            # No device associated, check by entity name pattern
            return self._has_energy_entity_by_name(power_entity, entity_registry)
            
        # Get all entities for the same device
        device_entities = er.async_entries_for_device(
            entity_registry, power_entity.device_id
        )
        
        for entity in device_entities:
            if entity.disabled:
                continue
                
            # Check if it's an energy sensor
            state = self.hass.states.get(entity.entity_id)
            if not state:
                continue
                
            unit = state.attributes.get("unit_of_measurement")
            device_class = state.attributes.get("device_class")
            
            if (
                entity.domain == "sensor"
                and unit in [ENERGY_KILO_WATT_HOUR, ENERGY_WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.WATT_HOUR]
                and (device_class == "energy" or device_class is None)
            ):
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
        
        for pattern in energy_patterns:
            energy_entity_id = f"sensor.{pattern}"
            if entity_registry.async_get(energy_entity_id):
                # Check if it's actually an energy sensor
                state = self.hass.states.get(energy_entity_id)
                if state:
                    unit = state.attributes.get("unit_of_measurement")
                    if unit in [ENERGY_KILO_WATT_HOUR, ENERGY_WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR, UnitOfEnergy.WATT_HOUR]:
                        return True
                        
        return False

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
            if entry.unique_id == f"powercalc_totals_{power_entity.entity_id}"
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

        # Get the best available name, preferring entity name for multi-outlet devices
        entity_name = power_entity.name or power_entity.original_name
        if entity_name:
            # Use entity name first as it's more specific (e.g., "PDU Pro Outlet 1" vs "PDU Pro")
            discovery_data["device_name"] = entity_name
            _LOGGER.debug("Using entity name: %s for %s", entity_name, power_entity.entity_id)
        elif device_entry:
            # Fallback to device name if entity has no specific name
            device_name = device_entry.name_by_user or device_entry.name
            if device_name:
                discovery_data["device_name"] = device_name
                _LOGGER.debug("Using device name: %s for %s", device_name, power_entity.entity_id)
            else:
                # Last resort: use entity ID without sensor prefix
                discovery_data["device_name"] = power_entity.entity_id.replace("sensor.", "").replace("_", " ").title()
                _LOGGER.debug("Device has no name, using entity ID-based name: %s for %s", discovery_data["device_name"], power_entity.entity_id)
        else:
            # No device entry, use entity ID as name
            discovery_data["device_name"] = power_entity.entity_id.replace("sensor.", "").replace("_", " ").title()
            _LOGGER.debug("No device found, using entity ID-based name: %s for %s", discovery_data["device_name"], power_entity.entity_id)
        
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