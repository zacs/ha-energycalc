"""Config flow for Power Calc Totals integration."""
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
    """Handle a config flow for Power Calc Totals."""

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
        
        # Set unique ID for this discovery
        power_entity_id = discovery_info["power_entity_id"]
        await self.async_set_unique_id(f"powercalc_totals_{power_entity_id}")
        self._abort_if_unique_id_configured()
        
        # Use device name from discovery data if available, following Battery Notes pattern
        device_name = discovery_info.get("device_name")
        if not device_name:
            # Fallback to extracting from entity ID
            try:
                device_name = self._extract_device_name(power_entity_id)
                _LOGGER.debug(f"Extracted device name: '{device_name}' from entity: {power_entity_id}")
            except Exception as e:
                _LOGGER.warning(f"Could not extract device name for {power_entity_id}: {e}")
                device_name = power_entity_id.replace("sensor.", "").replace("_", " ").title()
        else:
            _LOGGER.debug(f"Using device name from discovery: '{device_name}' for entity: {power_entity_id}")
        
        # Store discovery info for confirmation step
        self._discovery_info = discovery_info
        self.data = {
            "power_entity_id": power_entity_id,
            "device_name": device_name,
            "device_id": discovery_info.get("device_id"),
            "manufacturer": discovery_info.get("manufacturer"),
            "model": discovery_info.get("model"),
        }
        
        # Set title placeholders for discovery UI like Battery Notes does
        self.context["title_placeholders"] = {
            "name": device_name,
            "power_entity": power_entity_id,
            "manufacturer": discovery_info.get("manufacturer", ""),
            "model": discovery_info.get("model", ""),
        }
        
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the setup."""
        if user_input is not None:
            # Get entity registry to get the power entity name
            entity_registry = er.async_get(self.hass)
            power_entity_id = self.data["power_entity_id"]
            power_entity = entity_registry.async_get(power_entity_id)
            
            # Create a more descriptive title
            device_name = self.data.get("device_name", "Unknown Device")
            
            if power_entity:
                power_entity_name = power_entity.name or power_entity.original_name or power_entity_id
            else:
                # Fallback if entity not in registry
                power_entity_name = power_entity_id.replace("sensor.", "").replace("_", " ").title()
            
            if device_name and device_name != "Unknown Device":
                title = f"{device_name} - Energy Sensor"
            else:
                title = f"{power_entity_name} - Energy Sensor"
            
            return self.async_create_entry(
                title=title,
                data=self.data,
            )

        power_entity_id = self.data["power_entity_id"]
        device_name = self.data.get("device_name", "Unknown Device")

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": device_name,
                "power_entity": power_entity_id,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        # Don't allow manual setup - this integration is discovery-only
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
    """Handle options flow for Power Calc Totals."""

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