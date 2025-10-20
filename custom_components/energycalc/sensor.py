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

    async def async_reset_integration(self) -> None:
        """Reset the integration sensor to zero and purge its history."""
        try:
            _LOGGER.info(f"Starting reset for {self.entity_id}")
            
            # Reset the internal state to zero
            from decimal import Decimal
            self._state = Decimal('0')
            self._last_valid_state = Decimal('0')
            
            # Update the state in Home Assistant
            self.async_write_ha_state()
            _LOGGER.info(f"Reset state to 0 for {self.entity_id}")
            
            # Check what recorder services are available
            recorder_services = self.hass.services.async_services().get("recorder", {})
            _LOGGER.info(f"Available recorder services: {list(recorder_services.keys())}")
            
            # Try to purge historical data for this entity from the recorder
            history_cleared = False
            
            # Method 1: Clear entity states using purge_entities service
            if "purge_entities" in recorder_services:
                try:
                    _LOGGER.info(f"Clearing entity states for {self.entity_id}")
                    await self.hass.services.async_call(
                        "recorder",
                        "purge_entities",
                        {
                            "entity_id": self.entity_id,  # String format works
                            "keep_days": 0,
                        },
                        blocking=True,
                    )
                    _LOGGER.info(f"Successfully cleared entity states for {self.entity_id}")
                    history_cleared = True
                except Exception as purge_error:
                    _LOGGER.error(f"Failed to clear entity states for {self.entity_id}: {purge_error}")
            
            # Method 2: ALWAYS clear statistics (this is what graphs use)
            # Do this regardless of whether purge_entities succeeded, since graphs use statistics
            statistics_cleared = False
            try:
                _LOGGER.info(f"Clearing statistics for {self.entity_id} (graphs use statistics data)")
                
                # Try statistics clearing service first if available
                if "clear_statistics" in recorder_services:
                    await self.hass.services.async_call(
                        "recorder",
                        "clear_statistics",
                        {"statistic_ids": [self.entity_id]},
                        blocking=True,
                    )
                    _LOGGER.info(f"Cleared statistics via recorder service for {self.entity_id}")
                    statistics_cleared = True
                else:
                    statistics_services = self.hass.services.async_services().get("statistics", {})
                    if "clear_statistics" in statistics_services:
                        await self.hass.services.async_call(
                            "statistics",
                            "clear_statistics",
                            {"statistic_ids": [self.entity_id]},
                            blocking=True,
                        )
                        _LOGGER.info(f"Cleared statistics via statistics service for {self.entity_id}")
                        statistics_cleared = True
                    else:
                        _LOGGER.info("No statistics clearing service found - using direct database approach")
                        
                        # Try direct database manipulation to clear statistics
                        try:
                            from homeassistant.components.recorder import get_instance
                            recorder_instance = get_instance(self.hass)
                            
                            if recorder_instance and recorder_instance.engine:
                                _LOGGER.info(f"Attempting direct statistics database deletion for {self.entity_id}")
                                
                                def clear_statistics_db(entity_id):
                                    """Clear statistics directly from database."""
                                    from homeassistant.components.recorder.util import session_scope
                                    import sqlalchemy as sa
                                    
                                    with session_scope(session=recorder_instance.get_session()) as session:
                                        # Find the metadata_id for this entity in statistics_meta
                                        metadata_result = session.execute(
                                            sa.text("SELECT id FROM statistics_meta WHERE statistic_id = :entity_id"),
                                            {"entity_id": entity_id}
                                        ).fetchone()
                                        
                                        if metadata_result:
                                            metadata_id = metadata_result[0]
                                            _LOGGER.info(f"Found statistics metadata_id {metadata_id} for {entity_id}")
                                            
                                            # Delete from statistics table
                                            stats_result = session.execute(
                                                sa.text("DELETE FROM statistics WHERE metadata_id = :metadata_id"),
                                                {"metadata_id": metadata_id}
                                            )
                                            
                                            # Delete from statistics_short_term table
                                            short_stats_result = session.execute(
                                                sa.text("DELETE FROM statistics_short_term WHERE metadata_id = :metadata_id"),
                                                {"metadata_id": metadata_id}
                                            )
                                            
                                            session.commit()
                                            
                                            _LOGGER.info(f"Deleted {stats_result.rowcount} statistics and {short_stats_result.rowcount} short-term statistics for {entity_id}")
                                            return True
                                        else:
                                            _LOGGER.info(f"No statistics metadata found for {entity_id}")
                                            return False
                                
                                # Run the database operation in executor
                                success = await recorder_instance.async_add_executor_job(
                                    clear_statistics_db, self.entity_id
                                )
                                
                                if success:
                                    _LOGGER.info(f"Successfully cleared statistics via direct database access for {self.entity_id}")
                                    statistics_cleared = True
                                else:
                                    _LOGGER.info(f"No statistics found to clear for {self.entity_id}")
                            else:
                                _LOGGER.warning("Recorder instance not available for direct database access")
                                
                        except ImportError as ie:
                            _LOGGER.warning(f"Recorder database components not available: {ie}")
                        except Exception as db_error:
                            _LOGGER.error(f"Direct statistics database deletion failed: {db_error}")
                        
            except Exception as stats_error:
                _LOGGER.error(f"Statistics clearing failed for {self.entity_id}: {stats_error}")
                _LOGGER.warning("This is likely why historical data still appears in graphs")

            
            

            
            # Final step: Force frontend refresh and verify
            if history_cleared or statistics_cleared:
                try:
                    # Force the entity to update its state to trigger frontend refresh
                    self.async_write_ha_state()
                    
                    # Try to trigger a frontend reload for this entity
                    await self.hass.services.async_call(
                        "homeassistant",
                        "update_entity",
                        {"entity_id": self.entity_id},
                        blocking=False,
                    )
                    
                    # Also try to reload the lovelace dashboards to clear cached graphs
                    try:
                        await self.hass.services.async_call(
                            "lovelace",
                            "reload_resources",
                            {},
                            blocking=False,
                        )
                        _LOGGER.info(f"Triggered frontend resource reload")
                    except:
                        pass  # Not critical if this fails
                    
                    status_parts = []
                    if history_cleared:
                        status_parts.append("states cleared")
                    if statistics_cleared:
                        status_parts.append("statistics cleared")
                    
                    status = " and ".join(status_parts) if status_parts else "state reset"
                    _LOGGER.info(f"Successfully reset integration sensor {self.entity_id} ({status}, frontend refreshed)")
                    
                except Exception as refresh_error:
                    _LOGGER.warning(f"Reset completed but frontend refresh failed: {refresh_error}")
                    status_parts = []
                    if history_cleared:
                        status_parts.append("states cleared")
                    if statistics_cleared:
                        status_parts.append("statistics cleared")
                    status = " and ".join(status_parts) if status_parts else "state reset"
                    _LOGGER.info(f"Successfully reset integration sensor {self.entity_id} ({status})")
            else:
                _LOGGER.warning(f"Successfully reset state for {self.entity_id} but could not clear history or statistics")
                _LOGGER.warning("Historical data will still be visible in graphs until manually purged")
                _LOGGER.info("Try refreshing your browser or waiting a few minutes for the UI to update")
                
        except Exception as e:
            _LOGGER.error(f"Error resetting integration sensor {self.entity_id}: {e}")
            raise


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
        
        # Store entity references for the reset button to use
        if DOMAIN not in hass.data:
            hass.data[DOMAIN] = {}
        if "energy_sensors" not in hass.data[DOMAIN]:
            hass.data[DOMAIN]["energy_sensors"] = {}
        
        for sensor in energy_sensors:
            hass.data[DOMAIN]["energy_sensors"][sensor.entity_id] = sensor
        
        _LOGGER.info(f"Successfully added energy sensors for {len(power_entity_ids)} power entities: {power_entity_ids}")
        
    except Exception as e:
        _LOGGER.error(f"Failed to create energy sensor for {power_entity_id}: {e}")
        raise
