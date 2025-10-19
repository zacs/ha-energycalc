"""Button entities for EnergyCalc."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities from a config entry."""
    _LOGGER.debug(f"Setting up button entities for config entry: {config_entry.entry_id}")
    
    # Get the device by looking at the energy sensors we've created
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    
    # Find energy sensors for this config entry to get device info
    config_entry_entities = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    device_info = None
    device_id = None
    
    for entity_entry in config_entry_entities:
        if entity_entry.entity_id.startswith("sensor.") and entity_entry.device_id:
            device_id = entity_entry.device_id
            device = device_registry.async_get(device_id)
            if device:
                device_info = DeviceInfo(
                    identifiers=device.identifiers,
                    connections=device.connections,
                )
                _LOGGER.debug(f"Found device for button via sensor: {device.name} ({device_id})")
                break
    
    if not device_info:
        _LOGGER.debug("No device found for config entry, creating button without device association")
    
    # Create the reset button
    button = EnergyResetButton(
        hass=hass,
        config_entry=config_entry,
        device_info=device_info,
        device_id=device_id,
    )
    
    async_add_entities([button])
    _LOGGER.debug("Added energy reset button")


class EnergyResetButton(ButtonEntity):
    """Button to reset all energy sensors for a device."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_info: DeviceInfo | None,
        device_id: str | None,
    ) -> None:
        """Initialize the reset button."""
        self.hass = hass
        self._config_entry = config_entry
        self._device_id = device_id
        self._device_info = device_info
        
        # Create unique ID for the button
        self._attr_unique_id = f"{config_entry.unique_id}_reset_button"
        self._attr_name = "Reset Energy Sensors"
        self._attr_device_class = ButtonDeviceClass.RESTART
        self._attr_icon = "mdi:counter"

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device info."""
        return self._device_info

    async def async_press(self) -> None:
        """Handle the button press to reset energy sensors."""
        _LOGGER.info("Energy reset button pressed for config entry: %s", self._config_entry.entry_id)
        
        try:
            # Get all energy sensors associated with this config entry
            entity_registry = er.async_get(self.hass)
            config_entry_entities = er.async_entries_for_config_entry(
                entity_registry, self._config_entry.entry_id
            )
            
            reset_count = 0
            failed_resets = []
            
            for entity_entry in config_entry_entities:
                # Only reset sensor entities (not the button itself)
                if (entity_entry.entity_id.startswith("sensor.") and 
                    entity_entry.entity_id != self.entity_id):
                    
                    entity_state = self.hass.states.get(entity_entry.entity_id)
                    if entity_state and entity_state.attributes.get('source_entity'):
                        _LOGGER.debug(f"Attempting to reset energy sensor: {entity_entry.entity_id}")
                        
                        try:
                            # Find the actual entity instance from our stored references
                            energy_sensors = self.hass.data.get(DOMAIN, {}).get("energy_sensors", {})
                            entity_obj = energy_sensors.get(entity_entry.entity_id)
                            
                            # If we found the entity, call our custom reset method
                            if entity_obj and hasattr(entity_obj, 'async_reset_integration'):
                                await entity_obj.async_reset_integration()
                                reset_count += 1
                                _LOGGER.debug(f"Successfully reset {entity_entry.entity_id} using custom method")
                            else:
                                # Fallback: directly set state to 0
                                self.hass.states.async_set(
                                    entity_entry.entity_id,
                                    "0.0",
                                    entity_state.attributes,
                                )
                                reset_count += 1
                                _LOGGER.debug(f"Reset {entity_entry.entity_id} using state override (entity object not found)")
                            
                        except Exception as reset_error:
                            _LOGGER.warning(f"Failed to reset {entity_entry.entity_id}: {reset_error}")
                            failed_resets.append(entity_entry.entity_id)
            
            # Create appropriate notification based on results
            if reset_count > 0:
                message = f"Successfully reset {reset_count} energy sensor{'s' if reset_count != 1 else ''}"
                if failed_resets:
                    message += f". Failed to reset {len(failed_resets)} sensor{'s' if len(failed_resets) != 1 else ''}"
                
                _LOGGER.info(message)
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "EnergyCalc Reset Complete",
                        "message": message,
                        "notification_id": f"energycalc_reset_{self._config_entry.entry_id}",
                    },
                )
            else:
                message = "No energy sensors found to reset"
                if failed_resets:
                    message = f"Failed to reset all {len(failed_resets)} energy sensors"
                
                _LOGGER.warning(message)
                await self.hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "EnergyCalc Reset",
                        "message": message,
                        "notification_id": f"energycalc_reset_{self._config_entry.entry_id}",
                    },
                )
                
        except Exception as e:
            _LOGGER.error(f"Error in reset button handler: {e}")
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "EnergyCalc Reset Error",
                    "message": f"Error resetting energy sensors: {str(e)}",
                    "notification_id": f"energycalc_reset_error_{self._config_entry.entry_id}",
                },
            )