"""Button entities for EnergyCalc."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device import async_entity_id_to_device
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_DEVICE_NAME
from .helpers import reset_button_unique_id, source_entity_ids

if TYPE_CHECKING:
    from . import EnergyCalcConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: EnergyCalcConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the reset button for a config entry."""
    power_entity_ids = source_entity_ids(config_entry)
    if not power_entity_ids:
        return

    async_add_entities([EnergyResetButton(hass, config_entry, power_entity_ids[0])])


class EnergyResetButton(ButtonEntity):
    """Button that resets every energy sensor of a config entry."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "reset_energy"

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: EnergyCalcConfigEntry,
        power_entity_id: str,
    ) -> None:
        """Initialize the reset button."""
        self._config_entry = config_entry
        self._attr_unique_id = reset_button_unique_id(config_entry)

        # Link to the source entity's device rather than describing it, so the
        # EnergyCalc config entry is not added to that device.
        device = async_entity_id_to_device(hass, power_entity_id)
        self.device_entry = device

        if device is not None:
            # The device already supplies the context, so "Fake PDU Reset
            # energy" reads better than "Reset Fake PDU energy".
            self._attr_has_entity_name = True
        else:
            self._attr_name = self._standalone_name(config_entry, power_entity_id)

    @staticmethod
    def _standalone_name(
        config_entry: EnergyCalcConfigEntry, power_entity_id: str
    ) -> str:
        """Build a name for a button that is not attached to a device."""
        name = config_entry.data.get(CONF_DEVICE_NAME) or power_entity_id.removeprefix(
            "sensor."
        ).replace("_", " ").title()
        if name.lower().endswith(" power"):
            name = name[: -len(" power")]
        return f"Reset {name} energy"

    async def async_press(self) -> None:
        """Reset every energy sensor belonging to this config entry."""
        energy_sensors = list(self._config_entry.runtime_data.energy_sensors.values())

        if not energy_sensors:
            raise HomeAssistantError(
                f"No EnergyCalc energy sensors to reset for {self._config_entry.title}"
            )

        failed: list[str] = []
        for sensor in energy_sensors:
            try:
                await sensor.async_reset_integration()
            except Exception:  # noqa: BLE001 - one failure must not stop the rest
                _LOGGER.exception("Failed to reset %s", sensor.entity_id)
                failed.append(sensor.entity_id)

        if failed:
            raise HomeAssistantError(f"Failed to reset {', '.join(failed)}")

        _LOGGER.debug(
            "Reset %d energy sensor(s) for %s",
            len(energy_sensors),
            self._config_entry.title,
        )
