"""Services for EnergyCalc."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.service import async_register_admin_service

from .const import (
    ATTR_INTEGRATION_METHOD,
    ATTR_ROUND_DIGITS,
    ATTR_SOURCE_ENTITY,
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
    SERVICE_CREATE_ENERGY_SENSOR,
    SERVICE_REMOVE_ENERGY_SENSOR,
)
from .helpers import source_entity_ids

_LOGGER = logging.getLogger(__name__)

CREATE_ENERGY_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_SOURCE_ENTITY): cv.entity_id,
        vol.Optional(
            ATTR_INTEGRATION_METHOD, default=DEFAULT_INTEGRATION_METHOD
        ): vol.In(INTEGRATION_METHODS),
        vol.Optional(ATTR_ROUND_DIGITS, default=DEFAULT_ROUND_DIGITS): vol.All(
            int, vol.Range(min=0, max=10)
        ),
        vol.Optional(CONF_UNIT_PREFIX, default=DEFAULT_UNIT_PREFIX): vol.In(["", "k"]),
        vol.Optional(
            CONF_MAX_SUB_INTERVAL_MINUTES, default=DEFAULT_MAX_SUB_INTERVAL_MINUTES
        ): vol.All(int, vol.Range(min=1, max=60)),
    }
)

REMOVE_ENERGY_SENSOR_SCHEMA = vol.Schema({vol.Required(ATTR_ENTITY_ID): cv.entity_id})


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the EnergyCalc services."""

    async def async_create_energy_sensor(call: ServiceCall) -> None:
        """Create an energy sensor for a power entity."""
        source_entity = call.data[ATTR_SOURCE_ENTITY]

        state = hass.states.get(source_entity)
        if state is None:
            raise ServiceValidationError(f"Source entity {source_entity} not found")

        unit = state.attributes.get("unit_of_measurement")
        if unit != POWER_WATT:
            raise ServiceValidationError(
                f"Source entity {source_entity} is not a power sensor (unit: {unit})"
            )

        if _async_find_owning_entry(hass, source_entity) is not None:
            raise ServiceValidationError(
                f"An energy sensor for {source_entity} already exists"
            )

        # Creating a config entry keeps service created sensors identical to
        # discovered ones: same setup path, same reset button, same reloading.
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_POWER_ENTITY_IDS: [source_entity],
                CONF_INTEGRATION_METHOD: call.data[ATTR_INTEGRATION_METHOD],
                CONF_ROUND_DIGITS: call.data[ATTR_ROUND_DIGITS],
                CONF_UNIT_PREFIX: call.data[CONF_UNIT_PREFIX],
                CONF_MAX_SUB_INTERVAL_MINUTES: call.data[
                    CONF_MAX_SUB_INTERVAL_MINUTES
                ],
            },
        )

        if result["type"] is not FlowResultType.CREATE_ENTRY:
            raise ServiceValidationError(
                f"Could not create an energy sensor for {source_entity}: "
                f"{result.get('reason', result['type'])}"
            )

        _LOGGER.info("Created energy sensor for %s", source_entity)

    async def async_remove_energy_sensor(call: ServiceCall) -> None:
        """Remove an energy sensor created by EnergyCalc."""
        entity_id = call.data[ATTR_ENTITY_ID]

        entity_registry = er.async_get(hass)
        entity_entry = entity_registry.async_get(entity_id)

        if entity_entry is None:
            raise ServiceValidationError(f"Entity {entity_id} not found")

        if entity_entry.platform != DOMAIN:
            raise ServiceValidationError(
                f"Entity {entity_id} is not managed by {DOMAIN}"
            )

        if entity_entry.config_entry_id is None or (
            config_entry := hass.config_entries.async_get_entry(
                entity_entry.config_entry_id
            )
        ) is None:
            raise ServiceValidationError(
                f"Entity {entity_id} does not belong to an EnergyCalc config entry"
            )

        source_entity = (
            state.attributes.get(ATTR_SOURCE_ENTITY)
            if (state := hass.states.get(entity_id))
            else None
        )
        power_entity_ids = source_entity_ids(config_entry)
        remaining = [
            entity for entity in power_entity_ids if entity != source_entity
        ]

        if not remaining:
            # The entry only tracked this sensor, so remove it entirely. That
            # also removes the entity and its reset button.
            await hass.config_entries.async_remove(config_entry.entry_id)
            _LOGGER.info("Removed energy sensor %s and its config entry", entity_id)
            return

        data = {**config_entry.data, CONF_POWER_ENTITY_IDS: remaining}
        data.pop(CONF_POWER_ENTITY_ID, None)
        hass.config_entries.async_update_entry(config_entry, data=data)
        entity_registry.async_remove(entity_id)
        _LOGGER.info("Removed energy sensor %s", entity_id)

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_CREATE_ENERGY_SENSOR,
        async_create_energy_sensor,
        schema=CREATE_ENERGY_SENSOR_SCHEMA,
    )

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_REMOVE_ENERGY_SENSOR,
        async_remove_energy_sensor,
        schema=REMOVE_ENERGY_SENSOR_SCHEMA,
    )


def _async_find_owning_entry(
    hass: HomeAssistant, power_entity_id: str
) -> ConfigEntry | None:
    """Return the config entry already tracking a power entity, if any."""
    for config_entry in hass.config_entries.async_entries(DOMAIN):
        if power_entity_id in source_entity_ids(config_entry):
            return config_entry
    return None
