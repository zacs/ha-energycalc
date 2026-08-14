"""The EnergyCalc integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

import voluptuous as vol
from awesomeversion import AwesomeVersion
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, __version__ as HA_VERSION, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.device import async_entity_id_to_device_id
from homeassistant.helpers.entity_registry import (
    EVENT_ENTITY_REGISTRY_UPDATED,
    EventEntityRegistryUpdatedData,
)
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.helper_integration import async_remove_helper_devices
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONFIG_MINOR_VERSION,
    CONF_EXCLUDE_ENTITIES,
    CONF_POWER_ENTITY_ID,
    CONF_POWER_ENTITY_IDS,
    DISCOVERY_DEBOUNCE_SECONDS,
    DISCOVERY_INTERVAL_HOURS,
    DOMAIN,
    MIN_HA_VERSION,
    POWER_WATT,
)
from .discovery import PowerDeviceDiscovery
from .helpers import (
    energy_sensor_unique_id,
    reset_button_unique_id,
    source_entity_ids,
)
from .services import async_setup_services

if TYPE_CHECKING:
    from .sensor import PowerTotalEnergyIntegrationSensor

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_EXCLUDE_ENTITIES, default=[]): vol.All(
                    cv.ensure_list, [cv.entity_id]
                ),
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class EnergyCalcData:
    """Runtime data for an EnergyCalc config entry."""

    energy_sensors: dict[str, PowerTotalEnergyIntegrationSensor] = field(
        default_factory=dict
    )


type EnergyCalcConfigEntry = ConfigEntry[EnergyCalcData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the EnergyCalc component."""
    if AwesomeVersion(HA_VERSION) < AwesomeVersion(MIN_HA_VERSION):
        _LOGGER.error(
            "EnergyCalc requires Home Assistant %s or newer, but %s is running",
            MIN_HA_VERSION,
            HA_VERSION,
        )
        return False

    hass.data.setdefault(DOMAIN, {})

    await async_setup_services(hass)

    if DOMAIN not in config:
        _LOGGER.debug("EnergyCalc not configured in YAML, discovery disabled")
        return True

    exclude_entities: list[str] = config[DOMAIN].get(CONF_EXCLUDE_ENTITIES, [])
    hass.data[DOMAIN][CONF_EXCLUDE_ENTITIES] = exclude_entities
    _LOGGER.debug(
        "EnergyCalc configured in YAML with %d excluded entities",
        len(exclude_entities),
    )

    async def _run_discovery(_now=None) -> None:
        """Scan for power entities that have no energy counterpart."""
        discovery = PowerDeviceDiscovery(hass, exclude_entities=exclude_entities)
        try:
            await discovery.async_discover_and_create_sensors()
        except Exception:  # noqa: BLE001 - discovery must never break setup
            _LOGGER.exception("EnergyCalc discovery failed")

    # Discovery walks the whole entity registry, so coalesce the bursts of
    # registry events that happen at startup and on reloads. The cooldown also
    # gives integrations time to finish registering their entities, otherwise
    # a device that is still loading looks like it has no energy sensor.
    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=DISCOVERY_DEBOUNCE_SECONDS,
        immediate=False,
        function=_run_discovery,
    )

    @callback
    def _schedule_initial_discovery(_hass: HomeAssistant) -> None:
        """Run the first scan once Home Assistant has finished starting."""
        debouncer.async_schedule_call()

    async_at_started(hass, _schedule_initial_discovery)
    async_track_time_interval(
        hass,
        _run_discovery,
        timedelta(hours=DISCOVERY_INTERVAL_HOURS),
        name="EnergyCalc discovery",
        cancel_on_shutdown=True,
    )

    @callback
    def _shutdown(_event: Event) -> None:
        debouncer.async_shutdown()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown)

    @callback
    def _entity_registry_updated(
        event: Event[EventEntityRegistryUpdatedData],
    ) -> None:
        """Trigger discovery when a power sensor appears or changes."""
        if event.data["action"] not in ("create", "update"):
            return

        entity_id = event.data["entity_id"]
        if not entity_id.startswith("sensor."):
            return

        if (state := hass.states.get(entity_id)) is None:
            return

        unit = state.attributes.get("unit_of_measurement")
        device_class = state.attributes.get("device_class")
        if unit == POWER_WATT and device_class in ("power", None):
            debouncer.async_schedule_call()

    hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, _entity_registry_updated)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: EnergyCalcConfigEntry) -> bool:
    """Set up EnergyCalc from a config entry."""
    power_entity_ids = source_entity_ids(entry)
    if not power_entity_ids:
        _LOGGER.error("Config entry %s has no power entities", entry.entry_id)
        return False

    entry.runtime_data = EnergyCalcData()

    _async_track_source_entities(hass, entry, power_entity_ids)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: EnergyCalcConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: EnergyCalcConfigEntry) -> None:
    """Reload a config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    _LOGGER.debug(
        "Migrating EnergyCalc entry %s from version %s.%s",
        entry.entry_id,
        entry.version,
        entry.minor_version,
    )

    if entry.version > 1:
        # Downgrade from a future version is not supported.
        return False

    if entry.minor_version < 2:
        await _async_migrate_entity_unique_ids(hass, entry)
        _detach_config_entry_from_source_device(hass, entry)
        hass.config_entries.async_update_entry(
            entry, version=1, minor_version=CONFIG_MINOR_VERSION
        )

    _LOGGER.debug(
        "Migration of EnergyCalc entry %s to version %s.%s successful",
        entry.entry_id,
        entry.version,
        entry.minor_version,
    )
    return True


async def _async_migrate_entity_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Move entities off index based unique IDs.

    Energy sensors used to be identified by their position in the power entity
    list, which meant removing one entity silently changed the identity of the
    others. Key them on the source entity's registry ID instead, and give the
    reset button an ID that does not depend on the (optional) config entry
    unique ID.
    """
    power_entity_ids = source_entity_ids(entry)
    legacy_sensor_ids = {
        f"{entry.entry_id}_energy_{index}": energy_sensor_unique_id(
            hass, entry, power_entity_id
        )
        for index, power_entity_id in enumerate(power_entity_ids)
    }
    legacy_button_ids = {
        f"{unique_id}_reset_button"
        for unique_id in (entry.unique_id, entry.entry_id)
        if unique_id
    }

    @callback
    def _migrate(registry_entry: er.RegistryEntry) -> dict[str, str] | None:
        if new_unique_id := legacy_sensor_ids.get(registry_entry.unique_id):
            return {"new_unique_id": new_unique_id}
        if registry_entry.unique_id in legacy_button_ids:
            return {"new_unique_id": reset_button_unique_id(entry)}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


@callback
def _detach_config_entry_from_source_device(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Stop the config entry from owning the source entity's device.

    EnergyCalc used to return the source device's identifiers from
    ``device_info``, which implicitly added its config entry to that device.
    That is no longer supported, so drop any device EnergyCalc ended up owning
    and relink its entities to the source device.

    See https://developers.home-assistant.io/blog/2025/07/18/updated-pattern-for-helpers-linking-to-devices/
    """
    power_entity_ids = source_entity_ids(entry)
    source_device_id = (
        async_entity_id_to_device_id(hass, power_entity_ids[0])
        if power_entity_ids
        else None
    )

    try:
        async_remove_helper_devices(
            hass,
            helper_config_entry_id=entry.entry_id,
            source_device_id=source_device_id,
            remove_all_devices=True,
        )
    except ValueError as err:
        _LOGGER.debug(
            "Could not detach entry %s from its source device: %s",
            entry.entry_id,
            err,
        )


@callback
def _async_track_source_entities(
    hass: HomeAssistant,
    entry: EnergyCalcConfigEntry,
    power_entity_ids: list[str],
) -> None:
    """Keep the entry in sync when its source entities change.

    ``async_handle_source_entity_changes`` is not usable here because it
    relinks every entity of the config entry to a single device, which is wrong
    for entries that track several power entities. Instead, follow renames and
    reload the entry so each sensor is relinked to its own source device.
    """
    tracked = set(power_entity_ids)

    async def _source_entity_updated(
        event: Event[EventEntityRegistryUpdatedData],
    ) -> None:
        data = event.data
        action = data["action"]

        if action == "remove":
            if data["entity_id"] in tracked:
                _LOGGER.debug(
                    "Source entity %s was removed, reloading %s",
                    data["entity_id"],
                    entry.entry_id,
                )
                hass.config_entries.async_schedule_reload(entry.entry_id)
            return

        if action != "update":
            return

        changes = data.get("changes", {})

        if (old_entity_id := data.get("old_entity_id")) in tracked:
            _async_replace_source_entity(hass, entry, old_entity_id, data["entity_id"])
            return

        # A source entity moved to (or off) a device; reload so the energy
        # sensors are relinked.
        if data["entity_id"] in tracked and "device_id" in changes:
            _LOGGER.debug(
                "Source entity %s changed device, reloading %s",
                data["entity_id"],
                entry.entry_id,
            )
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(
        hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, _source_entity_updated)
    )


@callback
def _async_replace_source_entity(
    hass: HomeAssistant,
    entry: EnergyCalcConfigEntry,
    old_entity_id: str,
    new_entity_id: str,
) -> None:
    """Follow a source entity rename in the config entry data."""
    power_entity_ids = source_entity_ids(entry)
    power_entity_ids = [
        new_entity_id if entity_id == old_entity_id else entity_id
        for entity_id in power_entity_ids
    ]

    data = {**entry.data, CONF_POWER_ENTITY_IDS: power_entity_ids}
    data.pop(CONF_POWER_ENTITY_ID, None)

    _LOGGER.debug(
        "Source entity %s was renamed to %s, updating %s",
        old_entity_id,
        new_entity_id,
        entry.entry_id,
    )
    # Updating the entry triggers the update listener, which reloads it.
    hass.config_entries.async_update_entry(entry, data=data)
