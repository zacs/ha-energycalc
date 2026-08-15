"""Tests for the EnergyCalc integration."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)

from custom_components.energycalc.const import (
    CONF_DEVICE_NAME,
    CONF_POWER_ENTITY_IDS,
    DOMAIN,
)
from custom_components.energycalc.discovery import PowerDeviceDiscovery

SOURCE_DOMAIN = "fake_pdu"


async def _add_source_device(
    hass: HomeAssistant, entity_ids: list[str]
) -> tuple[dr.DeviceEntry, MockConfigEntry]:
    """Create a device owned by another integration exposing power sensors."""
    source_entry = MockConfigEntry(domain=SOURCE_DOMAIN, title="Fake PDU")
    source_entry.add_to_hass(hass)

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={(SOURCE_DOMAIN, "pdu-1")},
        name="Fake PDU",
        manufacturer="Ubiquiti",
    )

    registry = er.async_get(hass)
    for entity_id in entity_ids:
        object_id = entity_id.removeprefix("sensor.")
        registry.async_get_or_create(
            "sensor",
            SOURCE_DOMAIN,
            object_id,
            suggested_object_id=object_id,
            config_entry=source_entry,
            device_id=device.id,
            original_name=object_id.replace("_", " ").title(),
        )
        hass.states.async_set(
            entity_id,
            "50",
            {
                "unit_of_measurement": "W",
                "device_class": "power",
                "state_class": "measurement",
                "friendly_name": object_id.replace("_", " ").title(),
            },
        )

    await hass.async_block_till_done()
    return device, source_entry


def _energycalc_entry(power_entity_ids: list[str], **kwargs) -> MockConfigEntry:
    """Build an EnergyCalc config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Fake PDU - Energy Sensors",
        unique_id=kwargs.pop("unique_id", "energycalc_device_pdu"),
        data={
            CONF_POWER_ENTITY_IDS: power_entity_ids,
            CONF_DEVICE_NAME: "Fake PDU",
        },
        version=kwargs.pop("version", 1),
        minor_version=kwargs.pop("minor_version", 2),
    )


async def test_entities_link_to_source_device_without_owning_it(
    hass: HomeAssistant,
) -> None:
    """Entities show on the source device without EnergyCalc owning a device."""
    power_entities = ["sensor.outlet_1_power", "sensor.outlet_2_power"]
    device, _ = await _add_source_device(hass, power_entities)

    entry = _energycalc_entry(power_entities)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    our_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len([e for e in our_entities if e.domain == "sensor"]) == 2
    assert len([e for e in our_entities if e.domain == "button"]) == 1

    for registry_entry in our_entities:
        assert registry_entry.device_id == device.id, registry_entry.entity_id

    refreshed = device_registry.async_get(device.id)
    assert entry.entry_id not in refreshed.config_entries
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id) == []


async def test_energy_sensor_attributes(hass: HomeAssistant) -> None:
    """The created sensor is usable on the Energy Dashboard."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    sensor = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["state_class"] == "total_increasing"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert state.attributes["source_entity"] == "sensor.outlet_1_power"
    assert state.attributes["integration_method"] == "trapezoidal"


async def test_energy_sensor_without_source_device_class(hass: HomeAssistant) -> None:
    """Power sensors without a device class still produce energy sensors."""
    source_entry = MockConfigEntry(domain=SOURCE_DOMAIN)
    source_entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "sensor",
        SOURCE_DOMAIN,
        "diy_power",
        suggested_object_id="diy_power",
        config_entry=source_entry,
    )
    hass.states.async_set("sensor.diy_power", "12", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()

    entry = _energycalc_entry(["sensor.diy_power"], unique_id="energycalc_diy")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    sensor = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )

    state = hass.states.get(sensor.entity_id)
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert "icon" not in state.attributes
    # No device to link to, and none invented.
    assert sensor.device_id is None


async def test_migration_detaches_device_and_rekeys_entities(
    hass: HomeAssistant,
) -> None:
    """A pre-2.0 entry is detached from the source device and re-keyed."""
    power_entities = ["sensor.outlet_1_power", "sensor.outlet_2_power"]
    device, _ = await _add_source_device(hass, power_entities)

    entry = _energycalc_entry(power_entities, minor_version=1)
    entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    registry = er.async_get(hass)

    # Recreate the pre-2026.8 state: EnergyCalc co-owned the source device and
    # keyed its entities on their position in the power entity list.
    device_registry.async_update_device(device.id, add_config_entry_id=entry.entry_id)
    for index in range(len(power_entities)):
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_energy_{index}",
            suggested_object_id=f"outlet_{index + 1}_energy",
            config_entry=entry,
            device_id=device.id,
        )
    registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{entry.unique_id}_reset_button",
        suggested_object_id="reset_fake_pdu_energy",
        config_entry=entry,
        device_id=device.id,
    )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.minor_version == 2

    refreshed = device_registry.async_get(device.id)
    assert entry.entry_id not in refreshed.config_entries
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id) == []

    our_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    unique_ids = {e.unique_id for e in our_entities}

    assert not any(uid.startswith(f"{entry.entry_id}_energy_") for uid in unique_ids)
    assert f"{entry.unique_id}_reset_button" not in unique_ids
    assert f"{entry.entry_id}_reset" in unique_ids
    assert len([e for e in our_entities if e.domain == "sensor"]) == 2

    # Entity IDs are preserved, so recorded history survives the migration.
    entity_ids = {e.entity_id for e in our_entities}
    assert entity_ids == {
        "sensor.outlet_1_energy",
        "sensor.outlet_2_energy",
        "button.reset_fake_pdu_energy",
    }

    for registry_entry in our_entities:
        assert registry_entry.device_id == device.id


async def test_reset_button_zeroes_sensors(hass: HomeAssistant) -> None:
    """Pressing the reset button zeroes every energy sensor of the entry."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    our_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    sensor_id = next(e.entity_id for e in our_entities if e.domain == "sensor")
    button_id = next(e.entity_id for e in our_entities if e.domain == "button")

    sensor = entry.runtime_data.energy_sensors[sensor_id]
    sensor._state = Decimal("1.234")
    sensor.async_write_ha_state()
    assert float(hass.states.get(sensor_id).state) > 0

    with patch(
        "custom_components.energycalc.sensor."
        "PowerTotalEnergyIntegrationSensor._async_purge_history"
    ) as purge:
        await hass.services.async_call(
            "button", "press", {"entity_id": button_id}, blocking=True
        )
        await hass.async_block_till_done()

    assert purge.called
    assert float(hass.states.get(sensor_id).state) == 0.0


async def test_source_entity_rename_is_followed(hass: HomeAssistant) -> None:
    """Renaming a power sensor keeps the energy sensor and its history."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    before = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )

    registry.async_update_entity(
        "sensor.outlet_1_power", new_entity_id="sensor.rack_outlet_1_power"
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_POWER_ENTITY_IDS] == ["sensor.rack_outlet_1_power"]

    after = [
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    ]
    assert len(after) == 1
    assert after[0].unique_id == before.unique_id
    assert after[0].entity_id == before.entity_id
    assert (
        hass.states.get(after[0].entity_id).attributes["source_entity"]
        == "sensor.rack_outlet_1_power"
    )


async def test_create_and_remove_services(hass: HomeAssistant) -> None:
    """The services create and tear down a config entry."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "create_energy_sensor",
        {"source_entity": "sensor.outlet_1_power"},
        blocking=True,
    )
    await hass.async_block_till_done()

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    sensor_id = next(
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )

    await hass.services.async_call(
        DOMAIN, "remove_energy_sensor", {"entity_id": sensor_id}, blocking=True
    )
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_discovery_creates_flow(hass: HomeAssistant) -> None:
    """Devices with power but no energy sensors are offered to the user."""
    await _add_source_device(hass, ["sensor.outlet_1_power", "sensor.outlet_2_power"])
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    await PowerDeviceDiscovery(hass).async_discover_and_create_sensors()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "confirm"

    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["type"] == "create_entry"
    assert result["data"][CONF_POWER_ENTITY_IDS] == [
        "sensor.outlet_1_power",
        "sensor.outlet_2_power",
    ]


async def test_discovery_skips_devices_that_report_energy(
    hass: HomeAssistant,
) -> None:
    """Devices that already report energy are left alone."""
    device, source_entry = await _add_source_device(hass, ["sensor.outlet_1_power"])

    er.async_get(hass).async_get_or_create(
        "sensor",
        SOURCE_DOMAIN,
        "outlet_1_energy",
        suggested_object_id="outlet_1_energy",
        config_entry=source_entry,
        device_id=device.id,
    )
    hass.states.async_set(
        "sensor.outlet_1_energy",
        "5",
        {"unit_of_measurement": "kWh", "device_class": "energy"},
    )
    await hass.async_block_till_done()

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await PowerDeviceDiscovery(hass).async_discover_and_create_sensors()
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_discovery_skips_entities_already_tracked(hass: HomeAssistant) -> None:
    """A power sensor owned by an EnergyCalc entry is never offered again."""
    await _add_source_device(hass, ["sensor.outlet_1_power", "sensor.outlet_2_power"])

    # Only outlet 1 was set up, e.g. through the service or the user flow.
    entry = _energycalc_entry(["sensor.outlet_1_power"], unique_id="energycalc_outlet_1")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await PowerDeviceDiscovery(hass).async_discover_and_create_sensors()
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["title_placeholders"]
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {})
    assert result["data"][CONF_POWER_ENTITY_IDS] == ["sensor.outlet_2_power"]


async def test_discovery_matches_energy_sensor_by_name(hass: HomeAssistant) -> None:
    """Power sensors without a device fall back to name matching."""
    hass.states.async_set(
        "sensor.shed_power",
        "12",
        {"unit_of_measurement": "W", "device_class": "power"},
    )
    hass.states.async_set(
        "sensor.shed_energy",
        "3",
        {"unit_of_measurement": "kWh", "device_class": "energy"},
    )
    registry = er.async_get(hass)
    for object_id in ("shed_power", "shed_energy"):
        registry.async_get_or_create(
            "sensor", "template", object_id, suggested_object_id=object_id
        )
    await hass.async_block_till_done()

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await PowerDeviceDiscovery(hass).async_discover_and_create_sensors()
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_discovery_runs_on_startup(hass: HomeAssistant) -> None:
    """Discovery is wired up to the real startup path, not just callable."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    # async_at_started fires immediately once hass is already running.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=5))
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "confirm"


async def test_discovery_honours_exclude_entities(hass: HomeAssistant) -> None:
    """Excluded power entities never reach a discovery flow."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    discovery = PowerDeviceDiscovery(
        hass, exclude_entities=["sensor.outlet_1_power"]
    )
    await discovery.async_discover_and_create_sensors()
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_source_entity_moved_to_another_device(hass: HomeAssistant) -> None:
    """Moving a power sensor moves its energy sensor with it."""
    device, source_entry = await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    other_device = device_registry.async_get_or_create(
        config_entry_id=source_entry.entry_id,
        identifiers={(SOURCE_DOMAIN, "pdu-2")},
        name="Other PDU",
    )

    registry = er.async_get(hass)
    registry.async_update_entity("sensor.outlet_1_power", device_id=other_device.id)
    await hass.async_block_till_done()

    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        assert registry_entry.device_id == other_device.id, registry_entry.entity_id

    # Still no device ownership anywhere.
    assert dr.async_entries_for_config_entry(device_registry, entry.entry_id) == []
    assert entry.entry_id not in device_registry.async_get(device.id).config_entries
    assert entry.entry_id not in device_registry.async_get(other_device.id).config_entries


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Unloading removes the entities from the state machine."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    entity_ids = [
        e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    ]
    assert entity_ids

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    for entity_id in entity_ids:
        assert hass.states.get(entity_id).state == "unavailable"


async def test_setup_fails_without_power_entities(hass: HomeAssistant) -> None:
    """An entry with no source entities does not silently load."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, version=1, minor_version=2)
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_create_service_rejects_bad_input(hass: HomeAssistant) -> None:
    """Unknown, non-power and already tracked entities are rejected."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])
    hass.states.async_set(
        "sensor.living_room_temperature",
        "21",
        {"unit_of_measurement": "°C", "device_class": "temperature"},
    )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    for source_entity in ("sensor.does_not_exist", "sensor.living_room_temperature"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "create_energy_sensor",
                {"source_entity": source_entity},
                blocking=True,
            )

    await hass.services.async_call(
        DOMAIN,
        "create_energy_sensor",
        {"source_entity": "sensor.outlet_1_power"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "create_energy_sensor",
            {"source_entity": "sensor.outlet_1_power"},
            blocking=True,
        )


async def test_remove_service_keeps_sibling_sensors(hass: HomeAssistant) -> None:
    """Removing one sensor of a multi entity entry keeps the others."""
    power_entities = ["sensor.outlet_1_power", "sensor.outlet_2_power"]
    await _add_source_device(hass, power_entities)
    assert await async_setup_component(hass, DOMAIN, {})

    entry = _energycalc_entry(power_entities)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    sensors = sorted(
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )
    assert len(sensors) == 2

    await hass.services.async_call(
        DOMAIN, "remove_energy_sensor", {"entity_id": sensors[0]}, blocking=True
    )
    await hass.async_block_till_done()

    assert entry.data[CONF_POWER_ENTITY_IDS] == ["sensor.outlet_2_power"]
    remaining = [
        e.entity_id
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    ]
    assert remaining == [sensors[1]]


async def test_discovery_skips_already_configured_devices(
    hass: HomeAssistant,
) -> None:
    """A device that already has an EnergyCalc entry is not offered again."""
    device, _ = await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(
        ["sensor.outlet_1_power"], unique_id=f"energycalc_device_{device.id}"
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    await PowerDeviceDiscovery(hass).async_discover_and_create_sensors()
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_reset_purges_recorded_history(hass: HomeAssistant) -> None:
    """The reset button purges states and long term statistics."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    our_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    sensor_id = next(e.entity_id for e in our_entities if e.domain == "sensor")
    button_id = next(e.entity_id for e in our_entities if e.domain == "button")

    sensor = entry.runtime_data.energy_sensors[sensor_id]
    sensor._state = Decimal("42")
    sensor.async_write_ha_state()

    purge_calls = async_mock_service(hass, "recorder", "purge_entities")
    recorder_instance = MagicMock()

    with patch(
        "homeassistant.components.recorder.get_instance",
        return_value=recorder_instance,
    ):
        await hass.services.async_call(
            "button", "press", {"entity_id": button_id}, blocking=True
        )
        await hass.async_block_till_done()

    assert len(purge_calls) == 1
    assert purge_calls[0].data["entity_id"] == sensor_id
    assert purge_calls[0].data["keep_days"] == 0
    recorder_instance.async_clear_statistics.assert_called_once_with([sensor_id])
    assert float(hass.states.get(sensor_id).state) == 0.0


async def test_reset_clears_long_term_statistics(
    recorder_mock, hass: HomeAssistant
) -> None:
    """The reset button really reaches the recorder."""
    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period
    from homeassistant.util import dt as dt_util

    await _add_source_device(hass, ["sensor.outlet_1_power"])

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    our_entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    sensor_id = next(e.entity_id for e in our_entities if e.domain == "sensor")
    button_id = next(e.entity_id for e in our_entities if e.domain == "button")

    now = dt_util.utcnow()
    start = now.replace(minute=now.minute - now.minute % 5, second=0, microsecond=0)
    sensor = entry.runtime_data.energy_sensors[sensor_id]
    sensor._state = Decimal("42")
    sensor.async_write_ha_state()

    # Compile statistics so there is something to clear.
    await async_wait_recording_done(hass)
    do_adhoc_statistics(hass, start=start)
    await async_wait_recording_done(hass)

    def _stats() -> dict:
        return statistics_during_period(
            hass,
            start - timedelta(minutes=5),
            None,
            {sensor_id},
            "5minute",
            None,
            {"state"},
        )

    assert await get_instance(hass).async_add_executor_job(_stats)

    await hass.services.async_call(
        "button", "press", {"entity_id": button_id}, blocking=True
    )
    await async_wait_recording_done(hass)

    assert not await get_instance(hass).async_add_executor_job(_stats)
    assert hass.states.get(sensor_id).state == "0.000"


async def test_user_flow(hass: HomeAssistant) -> None:
    """A user can add an energy sensor from the Integrations page."""
    device, _ = await _add_source_device(hass, ["sensor.outlet_1_power"])
    assert await async_setup_component(hass, DOMAIN, {})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "power_entity_id": "sensor.outlet_1_power",
            "integration_method": "left",
            "unit_prefix": "none",
            "round_digits": 1,
            "max_sub_interval_minutes": 5,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.data[CONF_POWER_ENTITY_IDS] == ["sensor.outlet_1_power"]
    assert entry.data["unit_prefix"] is None

    registry = er.async_get(hass)
    sensor = next(
        e
        for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if e.domain == "sensor"
    )
    assert sensor.device_id == device.id

    state = hass.states.get(sensor.entity_id)
    assert state.attributes["unit_of_measurement"] == "Wh"
    assert state.attributes["device_class"] == "energy"
    assert state.attributes["integration_method"] == "left"


async def test_user_flow_rejects_invalid_sources(hass: HomeAssistant) -> None:
    """The form reports why an entity cannot be used."""
    await _add_source_device(hass, ["sensor.outlet_1_power"])
    hass.states.async_set(
        "sensor.living_room_temperature", "21", {"unit_of_measurement": "°C"}
    )
    assert await async_setup_component(hass, DOMAIN, {})

    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    base_input = {
        "integration_method": "trapezoidal",
        "unit_prefix": "k",
        "round_digits": 3,
        "max_sub_interval_minutes": 1,
    }
    expected = {
        "sensor.nope": "unknown_entity",
        "sensor.living_room_temperature": "not_a_power_sensor",
        "sensor.outlet_1_power": "already_tracked",
    }

    for power_entity_id, error in expected.items():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**base_input, "power_entity_id": power_entity_id}
        )
        assert result["type"] == "form"
        assert result["errors"] == {"power_entity_id": error}


async def test_entries_appear_on_the_integrations_page(
    hass: HomeAssistant, hass_ws_client
) -> None:
    """The Integrations page must list EnergyCalc entries.

    It subscribes with type_filter ["device", "hub", "service", "hardware"],
    and the backend drops entries whose integration_type is not in that set.
    Declaring the manifest as a "helper" therefore hid EnergyCalc from
    Settings > Devices & Services entirely.
    """
    await _add_source_device(hass, ["sensor.outlet_1_power"])
    entry = _energycalc_entry(["sensor.outlet_1_power"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert await async_setup_component(hass, "config", {})
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json_auto_id(
        {
            "type": "config_entries/get",
            "type_filter": ["device", "hub", "service", "hardware"],
        }
    )
    response = await client.receive_json()

    assert response["success"]
    assert entry.entry_id in [
        result["entry_id"] for result in response["result"]
    ]
