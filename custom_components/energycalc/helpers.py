"""Shared helpers for EnergyCalc."""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import CONF_POWER_ENTITY_ID, CONF_POWER_ENTITY_IDS

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


@callback
def source_entity_ids(config_entry: ConfigEntry) -> list[str]:
    """Return the power entities tracked by a config entry.

    Entries created before multi-entity support stored a single
    ``power_entity_id`` instead of a ``power_entity_ids`` list.
    """
    if power_entity_ids := config_entry.data.get(CONF_POWER_ENTITY_IDS):
        return list(power_entity_ids)
    if power_entity_id := config_entry.data.get(CONF_POWER_ENTITY_ID):
        return [power_entity_id]
    return []


@callback
def energy_sensor_unique_id(
    hass: HomeAssistant, config_entry: ConfigEntry, power_entity_id: str
) -> str:
    """Return the unique ID of the energy sensor for a power entity.

    Keyed on the source entity's registry ID rather than its entity ID or its
    position in the list, so that renaming a power sensor or removing another
    power entity from the same entry does not orphan the energy sensor and
    throw away its history.
    """
    registry_entry = er.async_get(hass).async_get(power_entity_id)
    key = registry_entry.id if registry_entry else power_entity_id
    return f"{config_entry.entry_id}_{key}"


@callback
def reset_button_unique_id(config_entry: ConfigEntry) -> str:
    """Return the unique ID of the reset button for a config entry."""
    return f"{config_entry.entry_id}_reset"


@callback
def energy_sensor_name(hass: HomeAssistant, power_entity_id: str) -> str:
    """Build a friendly name for the energy sensor of a power entity."""
    base_name: str | None = None

    if (state := hass.states.get(power_entity_id)) is not None:
        base_name = state.attributes.get("friendly_name")

    if not base_name:
        base_name = power_entity_id.removeprefix("sensor.").replace("_", " ").title()

    # Avoid names like "Office Power Energy".
    if base_name.lower().endswith(" power"):
        base_name = base_name[: -len(" power")]

    return f"{base_name} Energy"
