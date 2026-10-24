"""Number platform: calibration and manual temperature range."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SenXorCoordinator
from .entity import SenXorEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SenXorNumberDescription:
    """Description of an adjustable numeric setting."""

    key: str
    name: str
    getter: Callable[[SenXorCoordinator], float]
    setter: Callable[[SenXorCoordinator, float], dict[str, float]]
    minimum: float
    maximum: float
    step: float
    unit: str | None = None
    device_class: NumberDeviceClass | None = None
    mode: NumberMode = NumberMode.BOX
    icon: str | None = None


NUMBERS: tuple[SenXorNumberDescription, ...] = (
    SenXorNumberDescription(
        key="emissivity",
        name="Emissivity",
        getter=lambda coord: coord.settings.emissivity,
        setter=lambda coord, value: {"emissivity": round(value, 3)},
        minimum=0.1,
        maximum=1.0,
        step=0.01,
        mode=NumberMode.SLIDER,
        icon="mdi:circle-opacity",
    ),
    SenXorNumberDescription(
        key="temperature_offset",
        name="Temperature offset",
        getter=lambda coord: coord.settings.offset,
        setter=lambda coord, value: {"offset": round(value, 2)},
        minimum=-20.0,
        maximum=20.0,
        step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-plus",
    ),
    SenXorNumberDescription(
        key="scale_minimum",
        name="Scale minimum",
        getter=lambda coord: coord.settings.scale_min,
        setter=lambda coord, value: {"scale_min": round(value, 1)},
        minimum=-40.0,
        maximum=300.0,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-down",
    ),
    SenXorNumberDescription(
        key="scale_maximum",
        name="Scale maximum",
        getter=lambda coord: coord.settings.scale_max,
        setter=lambda coord, value: {"scale_max": round(value, 1)},
        minimum=-40.0,
        maximum=300.0,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-up",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SenXor number entities."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities(
        SenXorNumber(coordinator, entry, description) for description in NUMBERS
    )


class SenXorNumber(SenXorEntity, NumberEntity):
    """An adjustable numeric setting."""

    entity_description: SenXorNumberDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorNumberDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_native_min_value = description.minimum
        self._attr_native_max_value = description.maximum
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_mode = description.mode
        self._attr_icon = description.icon

    @property
    def native_value(self) -> float:
        return self.entity_description.getter(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Persist the new value."""
        changes = self.entity_description.setter(self.coordinator, value)
        await self.coordinator.async_update_settings(**changes)
