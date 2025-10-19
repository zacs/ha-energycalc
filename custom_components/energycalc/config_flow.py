"""Config flow for EnergyCalc integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Ensure the ConfigFlow is exported
__all__ = ["ConfigFlow"]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnergyCalc."""

    VERSION = 1
    
    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: dict[str, Any] = {}
        self._discovery_info: dict[str, Any] = {}

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle integration discovery."""
        _LOGGER.debug(f"Starting integration discovery flow with info: {discovery_info}")
        
        # Handle both old (single entity) and new (multiple entities) discovery formats
        if "power_entity_ids" in discovery_info:
            # New multi-entity format
            power_entity_ids = discovery_info["power_entity_ids"]
            unique_id = discovery_info["unique_id"]
            primary_entity_id = power_entity_ids[0]  # Use first entity for display
        else:
            # Legacy single entity format (for backward compatibility)
            power_entity_ids = [discovery_info["power_entity_id"]]
            primary_entity_id = discovery_info["power_entity_id"]
            unique_id = f"energycalc_{primary_entity_id}"
        
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        
        # Use device name from discovery data if available, following Battery Notes pattern
        device_name = discovery_info.get("device_name")
        if not device_name:
            # Fallback to extracting from entity ID
            try:
                device_name = self._extract_device_name(primary_entity_id)
                _LOGGER.debug(f"Extracted device name: '{device_name}' from entity: {primary_entity_id}")
            except Exception as e:
                _LOGGER.warning(f"Could not extract device name for {primary_entity_id}: {e}")
                device_name = primary_entity_id.replace("sensor.", "").replace("_", " ").title()
        else:
            _LOGGER.debug(f"Using device name from discovery: '{device_name}' for entities: {power_entity_ids}")
        
        # Store discovery info for confirmation step
        self._discovery_info = discovery_info
        self.data = {
            "power_entity_ids": power_entity_ids,  # Store all entities
            "device_name": device_name,
            # Don't store device_id to avoid config entry being associated with the device
            "manufacturer": discovery_info.get("manufacturer"),
            "model": discovery_info.get("model"),
        }
        
        # Set title placeholders for discovery UI like Battery Notes does
        entity_count = len(power_entity_ids)
        display_text = f"{device_name}" if entity_count == 1 else f"{device_name} ({entity_count} power sensors)"
        self.context["title_placeholders"] = {
            "name": display_text,
            "manufacturer": discovery_info.get("manufacturer", ""),
            "model": discovery_info.get("model", ""),
        }
        
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup."""
        if user_input is not None:
            # Handle both single and multiple entity formats
            power_entity_ids = self.data.get("power_entity_ids", [self.data.get("power_entity_id")])
            device_name = self.data.get("device_name", "Unknown Device")
            
            # Create a descriptive title
            entity_count = len(power_entity_ids)
            if entity_count == 1:
                title = f"{device_name} - Energy Sensor"
            else:
                title = f"{device_name} - Energy Sensors ({entity_count} power sensors)"
            
            return self.async_create_entry(
                title=title,
                data=self.data,
            )

        # Handle both single and multiple entity formats for display
        power_entity_ids = self.data.get("power_entity_ids", [self.data.get("power_entity_id")])
        device_name = self.data.get("device_name", "Unknown Device")
        primary_entity_id = power_entity_ids[0]
        
        entity_count = len(power_entity_ids)
        display_name = f"{device_name}" if entity_count == 1 else f"{device_name} ({entity_count} power sensors)"

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": display_name,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        # Don't allow manual setup - this integration is YAML configuration only
        return self.async_abort(reason="not_supported")

    def _extract_device_name(self, entity_id: str) -> str:
        """Extract a human-readable device name from entity ID."""
        # For now, just do simple string manipulation to avoid async issues
        # We can enhance this later if needed
        name = entity_id.replace("sensor.", "").replace("_", " ").title()
        return name if name else "Unknown Device"

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for EnergyCalc."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                # Add options here if needed later
            }),
        )