"""Integration sensor for EnergyCalc."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    ATTR_SOURCE_ENTITY,
    ATTR_INTEGRATION_METHOD,
    ATTR_ROUND_DIGITS,
)

_LOGGER = logging.getLogger(__name__)


class PowerTotalEnergyIntegrationSensor(IntegrationSensor):
    """Integration sensor that calculates total energy from power sensor."""

    def __init__(
        self,
        hass: HomeAssistant,
        power_entity_id: str,
        unique_id: str,
    ) -> None:
        """Initialize the energy integration sensor."""
        _LOGGER.debug(f"Initializing PowerTotalEnergyIntegrationSensor for {power_entity_id}")
        
        try:
            # Use the INTEGRATION_METHOD directly (trapezoidal is the default)
            integration_method = "trapezoidal"
            max_sub_interval = timedelta(minutes=1)  # Default value
            
            # Store integration method for extra_state_attributes
            self._integration_method = integration_method
            
            _LOGGER.debug(f"Calling super().__init__ with hass={hass}, integration_method={integration_method}")
            
            # Create a clean name by removing "Power" from the end and adding "Energy"
            base_name = power_entity_id.replace('sensor.', '').replace('_', ' ').title()
            # Remove "Power" from the end if it exists to avoid "Power Energy"
            if base_name.endswith(' Power'):
                base_name = base_name[:-6]  # Remove " Power"
            energy_name = f"{base_name} Energy"
            
            super().__init__(
                hass=hass,
                integration_method=integration_method,
                name=energy_name,
                round_digits=3,
                source_entity=power_entity_id,
                unique_id=unique_id,
                unit_prefix="k",
                unit_time=UnitOfTime.HOURS,
                max_sub_interval=max_sub_interval,
            )
            
            _LOGGER.debug(f"Successfully initialized PowerTotalEnergyIntegrationSensor for {power_entity_id}")
            
        except Exception as e:
            _LOGGER.error(f"Error initializing PowerTotalEnergyIntegrationSensor for {power_entity_id}: {e}")
            raise

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = super().extra_state_attributes or {}
        attributes.update({
            ATTR_SOURCE_ENTITY: self._source_entity,
            ATTR_INTEGRATION_METHOD: self._integration_method,
            ATTR_ROUND_DIGITS: self._round_digits,
        })
        return attributes

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return device class."""
        return SensorDeviceClass.ENERGY

    @property
    def state_class(self) -> SensorStateClass | None:
        """Return state class."""
        return SensorStateClass.TOTAL_INCREASING

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return UnitOfEnergy.KILO_WATT_HOUR

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info to link this entity to the parent power entity's device."""
        if not self._source_entity:
            return None
            
        entity_registry = er.async_get(self.hass)
        entity_entry = entity_registry.async_get(self._source_entity)
        
        if not entity_entry or not entity_entry.device_id:
            return None
            
        device_registry = dr.async_get(self.hass)
        device_entry = device_registry.async_get(entity_entry.device_id)
        
        if not device_entry:
            return None
            
        # Use the same identifiers and connections as the original device
        # This ensures the energy sensor appears on the same device page
        # Do NOT include name, manufacturer, model etc. to avoid overriding the existing device
        return DeviceInfo(
            identifiers=device_entry.identifiers,
            connections=device_entry.connections,
        )

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        return "mdi:lightning-bolt"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up the EnergyCalc sensor platform."""
    # This function is called by the platform setup
    # Actual entity creation is handled by services
    pass


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EnergyCalc sensor entities from a config entry."""
    _LOGGER.debug(f"Setting up sensor platform for config entry: {config_entry.entry_id}")
    _LOGGER.debug(f"Config entry data: {config_entry.data}")
    
    try:
        # Handle both single and multiple entity formats
        power_entity_ids = config_entry.data.get("power_entity_ids")
        if not power_entity_ids:
            # Legacy single entity format
            power_entity_id = config_entry.data.get("power_entity_id")
            if not power_entity_id:
                _LOGGER.error(f"No power entity IDs found in config entry {config_entry.entry_id}")
                return
            power_entity_ids = [power_entity_id]
        
        _LOGGER.debug(f"Creating energy sensors for power entities: {power_entity_ids}")
        
        # Create energy sensors for all power entities
        energy_sensors = []
        for i, power_entity_id in enumerate(power_entity_ids):
            # Create unique ID for each sensor
            energy_entity_unique_id = f"{config_entry.entry_id}_energy_{i}"
            
            _LOGGER.debug(f"Energy sensor unique ID: {energy_entity_unique_id} for {power_entity_id}")
            
            # Create the integration sensor
            energy_sensor = PowerTotalEnergyIntegrationSensor(
                hass=hass,
                power_entity_id=power_entity_id,
                unique_id=energy_entity_unique_id,
            )
            energy_sensors.append(energy_sensor)
        
        _LOGGER.debug(f"Successfully created {len(energy_sensors)} energy sensors, adding to Home Assistant...")
        async_add_entities(energy_sensors, True)
        _LOGGER.info(f"Successfully added energy sensors for {len(power_entity_ids)} power entities: {power_entity_ids}")
        
    except Exception as e:
        _LOGGER.error(f"Failed to create energy sensor for {power_entity_id}: {e}")
        raise
