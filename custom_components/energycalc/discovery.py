"""Discovery of power sensors that have no energy counterpart."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import (
    device_registry as dr,
    discovery_flow,
    entity_registry as er,
)

from .const import CONF_DEVICE_NAME, CONF_POWER_ENTITY_IDS, DOMAIN
from .helpers import source_entity_ids

_LOGGER = logging.getLogger(__name__)

POWER_UNITS = {UnitOfPower.WATT}
ENERGY_UNITS = {UnitOfEnergy.WATT_HOUR, UnitOfEnergy.KILO_WATT_HOUR}

# Suffix pairs used to spot an energy sensor that belongs to a power sensor
# which is not attached to a device.
_NAME_PATTERNS = (
    ("_power", "_energy"),
    ("_power", "_total_energy"),
    ("power", "energy"),
    ("power", "total_energy"),
)


class PowerDeviceDiscovery:
    """Find power sensors that are missing an energy sensor."""

    def __init__(
        self, hass: HomeAssistant, exclude_entities: list[str] | None = None
    ) -> None:
        """Initialize the discovery."""
        self.hass = hass
        self.exclude_entities = set(exclude_entities or [])
        self._states: dict[str, State] = {}

    async def async_discover_and_create_sensors(self) -> None:
        """Scan the entity registry and start a discovery flow per device."""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        # Snapshot the states once. Discovery walks every sensor, and on large
        # installations individual lookups add up.
        self._states = {
            state.entity_id: state for state in self.hass.states.async_all("sensor")
        }

        candidates = [
            entity
            for entity in self._power_entities(entity_registry)
            if not self._has_energy_entity(entity, entity_registry)
        ]

        if not candidates:
            _LOGGER.debug("No power sensors are missing an energy sensor")
            self._states = {}
            return

        # Multi outlet devices are offered as a whole, so the user confirms a
        # PDU once instead of once per outlet. Entities without a device have
        # nothing to group on and are offered individually.
        groups: dict[str | None, list[er.RegistryEntry]] = {}
        for entity in candidates:
            groups.setdefault(entity.device_id, []).append(entity)

        for device_id, entities in groups.items():
            if device_id is None:
                for entity in entities:
                    self._init_discovery([entity], device_registry)
            else:
                self._init_discovery(entities, device_registry)

        self._states = {}

    def _power_entities(
        self, entity_registry: er.EntityRegistry
    ) -> list[er.RegistryEntry]:
        """Return the registered sensors that report power in watts."""
        tracked = {
            entity_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            for entity_id in source_entity_ids(entry)
        }

        return [
            entity
            for entity in entity_registry.entities.values()
            if entity.domain == "sensor"
            and not entity.disabled
            and entity.entity_id not in self.exclude_entities
            and entity.entity_id not in tracked
            and self._is_power_sensor(self._states.get(entity.entity_id))
        ]

    @staticmethod
    def _is_power_sensor(state: State | None) -> bool:
        """Return whether a state looks like a power sensor.

        Sensors without a device class are accepted on purpose: DIY and
        template power sensors routinely omit it, and they are exactly the
        ones that tend to lack an energy counterpart.
        """
        if state is None:
            return False
        return state.attributes.get("unit_of_measurement") in POWER_UNITS and (
            state.attributes.get("device_class") in ("power", None)
        )

    @staticmethod
    def _is_energy_sensor(state: State | None) -> bool:
        """Return whether a state looks like an energy sensor."""
        if state is None:
            return False
        return state.attributes.get("unit_of_measurement") in ENERGY_UNITS and (
            state.attributes.get("device_class") in ("energy", None)
        )

    def _has_energy_entity(
        self, power_entity: er.RegistryEntry, entity_registry: er.EntityRegistry
    ) -> bool:
        """Return whether an energy sensor already covers this power sensor."""
        if power_entity.device_id is None:
            return self._has_energy_entity_by_name(power_entity, entity_registry)

        return any(
            not entity.disabled
            and entity.domain == "sensor"
            # Our own output says nothing about the sensors we have not covered
            # yet, so a partially configured device stays discoverable.
            and entity.platform != DOMAIN
            and self._is_energy_sensor(self._states.get(entity.entity_id))
            for entity in er.async_entries_for_device(
                entity_registry, power_entity.device_id
            )
        )

    def _has_energy_entity_by_name(
        self, power_entity: er.RegistryEntry, entity_registry: er.EntityRegistry
    ) -> bool:
        """Look for an energy sensor named after a device-less power sensor."""
        object_id = power_entity.entity_id.removeprefix("sensor.")

        candidates = {f"sensor.{object_id}_energy", f"sensor.{object_id}_total_energy"}
        candidates.update(
            f"sensor.{object_id.replace(old, new)}"
            for old, new in _NAME_PATTERNS
            if old in object_id
        )

        return any(
            (entity := entity_registry.async_get(entity_id)) is not None
            and entity.platform != DOMAIN
            and self._is_energy_sensor(self._states.get(entity_id))
            for entity_id in candidates
        )

    def _init_discovery(
        self,
        power_entities: list[er.RegistryEntry],
        device_registry: dr.DeviceRegistry,
    ) -> None:
        """Start a discovery flow for a group of power entities."""
        primary_entity = power_entities[0]
        device_id = primary_entity.device_id

        unique_id = (
            f"energycalc_device_{device_id}"
            if device_id
            else f"energycalc_{primary_entity.entity_id}"
        )

        if any(
            entry.unique_id == unique_id
            for entry in self.hass.config_entries.async_entries(DOMAIN)
        ):
            _LOGGER.debug("%s is already configured, skipping discovery", unique_id)
            return

        device_entry = device_registry.async_get(device_id) if device_id else None
        power_entity_ids = [entity.entity_id for entity in power_entities]

        discovery_data: dict[str, Any] = {
            CONF_POWER_ENTITY_IDS: power_entity_ids,
            CONF_DEVICE_NAME: self._build_name(primary_entity, device_entry),
            "unique_id": unique_id,
        }

        _LOGGER.debug(
            "Discovered %d power sensor(s) without energy sensors: %s",
            len(power_entity_ids),
            ", ".join(power_entity_ids),
        )

        discovery_flow.async_create_flow(
            self.hass,
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=discovery_data,
        )

    @staticmethod
    def _build_name(
        primary_entity: er.RegistryEntry, device_entry: dr.DeviceEntry | None
    ) -> str:
        """Build the name shown for a discovered device."""
        entity_name = primary_entity.name or primary_entity.original_name
        device_name = (
            device_entry.name_by_user or device_entry.name if device_entry else None
        )

        if device_name and entity_name and entity_name != device_name:
            # Multi outlet devices need both parts to be identifiable, unless
            # the entity name already repeats the device name.
            if device_name.lower() in entity_name.lower():
                return entity_name
            return f"{device_name}: {entity_name}"

        if device_name:
            return device_name
        if entity_name:
            return entity_name

        return primary_entity.entity_id.removeprefix("sensor.").replace("_", " ").title()
