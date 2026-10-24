"""Number platform: camera register controls and viewer settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    EMISSIVITY_MAX,
    EMISSIVITY_MIN,
    FPS_DIVIDER_MAX,
    FPS_DIVIDER_MIN,
    OFFSET_MAX,
    OFFSET_MIN,
    PERCENTILE_MAX,
    PERCENTILE_MIN,
    SENSITIVITY_MAX,
    SENSITIVITY_MIN,
)
from .coordinator import SenXorCoordinator
from .entity import SenXorEntity

_LOGGER = logging.getLogger(__name__)


async def _set_option(coordinator: SenXorCoordinator, **changes: Any) -> None:
    await coordinator.async_update_settings(**changes)


@dataclass(frozen=True, kw_only=True)
class SenXorNumberDescription:
    """Description of an adjustable numeric setting."""

    key: str
    name: str
    getter: Callable[[SenXorCoordinator], float]
    setter: Callable[[SenXorCoordinator, float], Awaitable[None]]
    minimum: float
    maximum: float
    step: float
    unit: str | None = None
    device_class: NumberDeviceClass | None = None
    mode: NumberMode = NumberMode.BOX
    icon: str | None = None
    entity_category: EntityCategory | None = EntityCategory.CONFIG


NUMBERS: tuple[SenXorNumberDescription, ...] = (
    SenXorNumberDescription(
        key="emissivity",
        name="放射率",
        getter=lambda coord: coord.settings.emissivity,
        setter=lambda coord, value: coord.async_set_emissivity(value),
        minimum=EMISSIVITY_MIN,
        maximum=EMISSIVITY_MAX,
        step=1,
        unit="%",
        mode=NumberMode.SLIDER,
        icon="mdi:circle-opacity",
    ),
    SenXorNumberDescription(
        key="temperature_offset",
        name="溫度補償",
        getter=lambda coord: coord.settings.offset,
        setter=lambda coord, value: coord.async_set_offset(value),
        minimum=OFFSET_MIN,
        maximum=OFFSET_MAX,
        step=0.1,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-plus",
    ),
    SenXorNumberDescription(
        key="sensitivity",
        name="靈敏度",
        getter=lambda coord: coord.settings.sensitivity,
        setter=lambda coord, value: coord.async_set_sensitivity(value),
        minimum=SENSITIVITY_MIN,
        maximum=SENSITIVITY_MAX,
        step=0.01,
        icon="mdi:tune-vertical",
    ),
    SenXorNumberDescription(
        key="frame_rate_divider",
        name="影格率除數",
        getter=lambda coord: coord.settings.frame_rate_divider,
        setter=lambda coord, value: coord.async_set_fps_divider(int(value)),
        minimum=FPS_DIVIDER_MIN,
        maximum=FPS_DIVIDER_MAX,
        step=1,
        icon="mdi:speedometer",
    ),
    SenXorNumberDescription(
        key="percentile",
        name="極值裁切",
        getter=lambda coord: coord.settings.percentile,
        setter=lambda coord, value: _set_option(coord, percentile=float(value)),
        minimum=PERCENTILE_MIN,
        maximum=PERCENTILE_MAX,
        step=0.001,
        icon="mdi:chart-bell-curve",
    ),
    SenXorNumberDescription(
        key="scale_minimum",
        name="色階下限",
        getter=lambda coord: coord.settings.scale_min,
        setter=lambda coord, value: _set_option(coord, scale_min=float(value)),
        minimum=-40.0,
        maximum=300.0,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-down",
    ),
    SenXorNumberDescription(
        key="scale_maximum",
        name="色階上限",
        getter=lambda coord: coord.settings.scale_max,
        setter=lambda coord, value: _set_option(coord, scale_max=float(value)),
        minimum=-40.0,
        maximum=300.0,
        step=0.5,
        unit=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-up",
    ),
    SenXorNumberDescription(
        key="probe_1_x",
        name="X1",
        getter=lambda coord: coord.settings.probe_1_x,
        setter=lambda coord, value: _set_option(coord, probe_1_x=int(value)),
        minimum=0,
        maximum=79,
        step=1,
        icon="mdi:axis-x-arrow",
    ),
    SenXorNumberDescription(
        key="probe_1_y",
        name="Y1",
        getter=lambda coord: coord.settings.probe_1_y,
        setter=lambda coord, value: _set_option(coord, probe_1_y=int(value)),
        minimum=0,
        maximum=61,
        step=1,
        icon="mdi:axis-y-arrow",
    ),
    SenXorNumberDescription(
        key="probe_2_x",
        name="X2",
        getter=lambda coord: coord.settings.probe_2_x,
        setter=lambda coord, value: _set_option(coord, probe_2_x=int(value)),
        minimum=0,
        maximum=79,
        step=1,
        icon="mdi:axis-x-arrow",
    ),
    SenXorNumberDescription(
        key="probe_2_y",
        name="Y2",
        getter=lambda coord: coord.settings.probe_2_y,
        setter=lambda coord, value: _set_option(coord, probe_2_y=int(value)),
        minimum=0,
        maximum=61,
        step=1,
        icon="mdi:axis-y-arrow",
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
        super().__init__(coordinator, entry, description.key, "number")
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_name = description.name
        self._attr_native_min_value = description.minimum
        self._attr_native_max_value = description.maximum
        self._attr_native_step = description.step
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_mode = description.mode
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> float:
        return self.entity_description.getter(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Push the new value to the camera or to the display settings."""
        await self.entity_description.setter(self.coordinator, value)
