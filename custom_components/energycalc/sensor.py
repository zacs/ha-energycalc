"""Integration sensor for EnergyCalc."""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from homeassistant.components.integration.sensor import IntegrationSensor
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_INTEGRATION_METHOD,
    ATTR_ROUND_DIGITS,
    ATTR_SOURCE_ENTITY,
    CONF_INTEGRATION_METHOD,
    CONF_MAX_SUB_INTERVAL_MINUTES,
    CONF_ROUND_DIGITS,
    CONF_UNIT_PREFIX,
    DEFAULT_INTEGRATION_METHOD,
    DEFAULT_MAX_SUB_INTERVAL_MINUTES,
    DEFAULT_ROUND_DIGITS,
    DEFAULT_UNIT_PREFIX,
)
from .helpers import energy_sensor_name, energy_sensor_unique_id, source_entity_ids

if TYPE_CHECKING:
    from . import EnergyCalcConfigEntry

_LOGGER = logging.getLogger(__name__)

# Units the integral may end up with that still represent energy. Used to give
# the sensor an energy device class even when the source power sensor does not
# declare one itself, which is common for template and DIY power sensors.
_ENERGY_UNITS = {
    UnitOfEnergy.WATT_HOUR,
    UnitOfEnergy.KILO_WATT_HOUR,
    UnitOfEnergy.MEGA_WATT_HOUR,
    UnitOfEnergy.GIGA_WATT_HOUR,
}


class PowerTotalEnergyIntegrationSensor(IntegrationSensor):
    """Riemann sum sensor that accumulates energy from a power sensor.

    The entity is linked to the source entity's device via ``device_entry``
    rather than ``device_info``. Returning another integration's identifiers
    from ``device_info`` would implicitly add the EnergyCalc config entry to
    that device, which is no longer supported.
    """

    # A Riemann sum of a power sensor only ever grows, and the reset button
    # relies on Home Assistant treating a drop to zero as a meter reset.
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(
        self,
        *,
        source_entity_id: str,
        unique_id: str,
        name: str,
        device: DeviceEntry | None,
        integration_method: str = DEFAULT_INTEGRATION_METHOD,
        round_digits: int = DEFAULT_ROUND_DIGITS,
        unit_prefix: str | None = DEFAULT_UNIT_PREFIX,
        max_sub_interval: timedelta | None = None,
    ) -> None:
        """Initialize the energy integration sensor."""
        if max_sub_interval is None:
            max_sub_interval = timedelta(minutes=DEFAULT_MAX_SUB_INTERVAL_MINUTES)

        super().__init__(
            integration_method=integration_method,
            name=name,
            round_digits=round_digits,
            source_entity=source_entity_id,
            unique_id=unique_id,
            unit_prefix=unit_prefix or None,
            unit_time=UnitOfTime.HOURS,
            max_sub_interval=max_sub_interval,
            device=device,
        )

        self._integration_method = integration_method

        # ``IntegrationSensor`` seeds a generic chart icon, which is what ends
        # up stored as the entity's original icon. These sensors always end up
        # with an energy device class, so let its icon apply instead.
        self._attr_icon = None

    async def async_added_to_hass(self) -> None:
        """Register the sensor so the reset button can reach it."""
        await super().async_added_to_hass()
        if (entry := self.platform.config_entry) is not None:
            entry.runtime_data.energy_sensors[self.entity_id] = self

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor."""
        if (entry := self.platform.config_entry) is not None:
            entry.runtime_data.energy_sensors.pop(self.entity_id, None)
        await super().async_will_remove_from_hass()

    @property
    def device_class(self) -> SensorDeviceClass | None:
        """Return the device class.

        ``IntegrationSensor`` only derives a device class when the source
        sensor declares one. EnergyCalc deliberately also picks up power
        sensors without a device class, so fall back to energy whenever the
        resulting unit is an energy unit. Without this the sensor cannot be
        used on the Energy Dashboard.
        """
        if (device_class := super().device_class) is not None:
            return device_class
        if self.native_unit_of_measurement in _ENERGY_UNITS:
            return SensorDeviceClass.ENERGY
        return None

    @property
    def icon(self) -> str | None:
        """Return the icon.

        ``IntegrationSensor`` falls back to a generic chart icon when it could
        not derive a device class. Once the fallback above supplies one, defer
        to the device class icon instead.
        """
        if self.device_class is not None:
            return None
        return super().icon

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attributes = dict(super().extra_state_attributes or {})
        attributes.update(
            {
                ATTR_SOURCE_ENTITY: self._source_entity,
                ATTR_INTEGRATION_METHOD: self._integration_method,
                ATTR_ROUND_DIGITS: self._round_digits,
            }
        )
        return attributes

    async def async_reset_integration(self) -> None:
        """Reset the accumulated energy to zero and purge recorded history."""
        _LOGGER.debug("Resetting %s", self.entity_id)

        self._state = Decimal(0)
        self._last_valid_state = Decimal(0)
        self.async_write_ha_state()

        await self._async_purge_history()

    async def _async_purge_history(self) -> None:
        """Purge states and long term statistics for this entity.

        Resetting the state alone is not enough: the Energy Dashboard and
        history graphs are backed by the recorder's statistics tables, so those
        have to be cleared too or the old totals keep showing up.
        """
        try:
            # Purges states and short term statistics.
            await self.hass.services.async_call(
                "recorder",
                "purge_entities",
                {"entity_id": self.entity_id, "keep_days": 0},
                blocking=True,
            )
        except Exception:  # noqa: BLE001 - recorder may be unavailable
            _LOGGER.exception("Could not purge states for %s", self.entity_id)

        try:
            # Purges long term statistics, which is what the Energy Dashboard
            # and history graphs actually read.
            from homeassistant.components.recorder import get_instance

            get_instance(self.hass).async_clear_statistics([self.entity_id])
        except Exception:  # noqa: BLE001 - recorder may be unavailable
            _LOGGER.exception("Could not clear statistics for %s", self.entity_id)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EnergyCalcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EnergyCalc sensor entities from a config entry."""
    power_entity_ids = source_entity_ids(config_entry)
    if not power_entity_ids:
        _LOGGER.error(
            "No power entities found in config entry %s", config_entry.entry_id
        )
        return

    options = {**config_entry.data, **config_entry.options}
    integration_method = options.get(
        CONF_INTEGRATION_METHOD, DEFAULT_INTEGRATION_METHOD
    )
    round_digits = int(options.get(CONF_ROUND_DIGITS, DEFAULT_ROUND_DIGITS))
    unit_prefix = options.get(CONF_UNIT_PREFIX, DEFAULT_UNIT_PREFIX)
    max_sub_interval = timedelta(
        minutes=int(
            options.get(
                CONF_MAX_SUB_INTERVAL_MINUTES, DEFAULT_MAX_SUB_INTERVAL_MINUTES
            )
        )
    )

    energy_sensors = [
        PowerTotalEnergyIntegrationSensor(
            source_entity_id=power_entity_id,
            unique_id=energy_sensor_unique_id(hass, config_entry, power_entity_id),
            name=energy_sensor_name(hass, power_entity_id),
            # Link to the source entity's device instead of describing it, so
            # the EnergyCalc config entry is never added to that device.
            device=async_entity_id_to_device(hass, power_entity_id),
            integration_method=integration_method,
            round_digits=round_digits,
            unit_prefix=unit_prefix,
            max_sub_interval=max_sub_interval,
        )
        for power_entity_id in power_entity_ids
    ]

    async_add_entities(energy_sensors)
    _LOGGER.debug(
        "Added %d energy sensors for %s", len(energy_sensors), ", ".join(power_entity_ids)
    )
