"""Config flow for the EnergyCalc integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import (
    CONFIG_MINOR_VERSION,
    CONFIG_VERSION,
    CONF_DEVICE_NAME,
    CONF_INTEGRATION_METHOD,
    CONF_MAX_SUB_INTERVAL_MINUTES,
    CONF_POWER_ENTITY_ID,
    CONF_POWER_ENTITY_IDS,
    CONF_ROUND_DIGITS,
    CONF_UNIT_PREFIX,
    DEFAULT_INTEGRATION_METHOD,
    DEFAULT_MAX_SUB_INTERVAL_MINUTES,
    DEFAULT_ROUND_DIGITS,
    DEFAULT_UNIT_PREFIX,
    DOMAIN,
    INTEGRATION_METHODS,
    POWER_WATT,
)
from .helpers import source_entity_ids

_LOGGER = logging.getLogger(__name__)

__all__ = ["ConfigFlow"]

# A select option cannot have an empty value, so map the "no prefix" choice
# onto the prefix the integration sensor actually expects.
UNIT_PREFIX_NONE = "none"
UNIT_PREFIXES: dict[str, str | None] = {"k": "k", UNIT_PREFIX_NONE: None}

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_POWER_ENTITY_ID): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
        vol.Required(
            CONF_INTEGRATION_METHOD, default=DEFAULT_INTEGRATION_METHOD
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=INTEGRATION_METHODS,
                translation_key="integration_method",
            )
        ),
        vol.Required(
            CONF_UNIT_PREFIX, default=DEFAULT_UNIT_PREFIX
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(UNIT_PREFIXES),
                translation_key="unit_prefix",
            )
        ),
        vol.Required(
            CONF_ROUND_DIGITS, default=DEFAULT_ROUND_DIGITS
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=10, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(
            CONF_MAX_SUB_INTERVAL_MINUTES, default=DEFAULT_MAX_SUB_INTERVAL_MINUTES
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=60,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        ),
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnergyCalc."""

    VERSION = CONFIG_VERSION
    MINOR_VERSION = CONFIG_MINOR_VERSION

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create an energy sensor for a power sensor picked by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            power_entity_id = user_input[CONF_POWER_ENTITY_ID]

            if (error := self._validate_source(power_entity_id)) is not None:
                errors[CONF_POWER_ENTITY_ID] = error
            else:
                await self.async_set_unique_id(f"energycalc_{power_entity_id}")
                self._abort_if_unique_id_configured()

                return self._create_entry(
                    {
                        CONF_POWER_ENTITY_IDS: [power_entity_id],
                        CONF_DEVICE_NAME: source_name(self.hass, power_entity_id),
                        CONF_INTEGRATION_METHOD: user_input[CONF_INTEGRATION_METHOD],
                        CONF_ROUND_DIGITS: int(user_input[CONF_ROUND_DIGITS]),
                        CONF_UNIT_PREFIX: UNIT_PREFIXES[user_input[CONF_UNIT_PREFIX]],
                        CONF_MAX_SUB_INTERVAL_MINUTES: int(
                            user_input[CONF_MAX_SUB_INTERVAL_MINUTES]
                        ),
                    }
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, user_input or {}
            ),
            errors=errors,
        )

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle a device discovered by EnergyCalc."""
        _LOGGER.debug("Starting discovery flow: %s", discovery_info)

        if power_entity_ids := discovery_info.get(CONF_POWER_ENTITY_IDS):
            unique_id = discovery_info["unique_id"]
        else:
            # Entries discovered by older versions carried a single entity.
            power_entity_ids = [discovery_info[CONF_POWER_ENTITY_ID]]
            unique_id = f"energycalc_{power_entity_ids[0]}"

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        device_name = discovery_info.get(CONF_DEVICE_NAME) or fallback_name(
            power_entity_ids[0]
        )

        self.data = {
            CONF_POWER_ENTITY_IDS: power_entity_ids,
            CONF_DEVICE_NAME: device_name,
        }

        self.context["title_placeholders"] = {
            "name": _display_name(device_name, len(power_entity_ids)),
        }

        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user to confirm a discovered device."""
        if user_input is not None:
            return self._create_entry(self.data)

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": _display_name(
                    self.data[CONF_DEVICE_NAME],
                    len(self.data[CONF_POWER_ENTITY_IDS]),
                ),
            },
        )

    async def async_step_import(self, import_data: dict[str, Any]) -> ConfigFlowResult:
        """Create an entry for the ``create_energy_sensor`` action."""
        power_entity_ids = import_data[CONF_POWER_ENTITY_IDS]

        await self.async_set_unique_id(f"energycalc_{power_entity_ids[0]}")
        self._abort_if_unique_id_configured()

        device_name = import_data.get(CONF_DEVICE_NAME) or source_name(
            self.hass, power_entity_ids[0]
        )
        return self._create_entry({**import_data, CONF_DEVICE_NAME: device_name})

    def _validate_source(self, power_entity_id: str) -> str | None:
        """Return an error key if the chosen entity cannot be integrated."""
        if (state := self.hass.states.get(power_entity_id)) is None:
            return "unknown_entity"

        if state.attributes.get("unit_of_measurement") != POWER_WATT:
            return "not_a_power_sensor"

        if any(
            power_entity_id in source_entity_ids(entry)
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        ):
            return "already_tracked"

        return None

    def _create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry for a set of power entities."""
        device_name = data[CONF_DEVICE_NAME]
        entity_count = len(data[CONF_POWER_ENTITY_IDS])
        title = (
            f"{device_name} - Energy Sensor"
            if entity_count == 1
            else f"{device_name} - Energy Sensors ({entity_count} power sensors)"
        )
        return self.async_create_entry(title=title, data=data)


def fallback_name(power_entity_id: str) -> str:
    """Derive a name from an entity ID when nothing better is available."""
    return power_entity_id.removeprefix("sensor.").replace("_", " ").title()


def source_name(hass: HomeAssistant, power_entity_id: str) -> str:
    """Return the friendly name of a power entity."""
    state = hass.states.get(power_entity_id)
    if state is not None and (friendly_name := state.attributes.get("friendly_name")):
        return str(friendly_name)
    return fallback_name(power_entity_id)


def _display_name(device_name: str, entity_count: int) -> str:
    """Describe a device and how many power sensors it exposes."""
    if entity_count == 1:
        return device_name
    return f"{device_name} ({entity_count} power sensors)"
