"""Number platform: camera register controls and viewer settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
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
class SenXorNumberDescription(NumberEntityDescription):
    """Describes a numeric setting and how to read/write it."""

    getter: Callable[[SenXorCoordinator], float]
    setter: Callable[[SenXorCoordinator, float], Awaitable[None]]


NUMBERS: tuple[SenXorNumberDescription, ...] = (
    SenXorNumberDescription(
        key="emissivity",
        translation_key="emissivity",
        name="放射率",
        getter=lambda coord: coord.settings.emissivity,
        setter=lambda coord, value: coord.async_set_emissivity(value),
        native_min_value=EMISSIVITY_MIN,
        native_max_value=EMISSIVITY_MAX,
        native_step=1,
        native_unit_of_measurement="%",
        mode=NumberMode.SLIDER,
        icon="mdi:circle-opacity",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="temperature_offset",
        translation_key="temperature_offset",
        name="溫度補償",
        getter=lambda coord: coord.settings.offset,
        setter=lambda coord, value: coord.async_set_offset(value),
        native_min_value=OFFSET_MIN,
        native_max_value=OFFSET_MAX,
        native_step=0.1,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:thermometer-plus",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="sensitivity",
        translation_key="sensitivity",
        name="靈敏度",
        getter=lambda coord: coord.settings.sensitivity,
        setter=lambda coord, value: coord.async_set_sensitivity(value),
        native_min_value=SENSITIVITY_MIN,
        native_max_value=SENSITIVITY_MAX,
        native_step=0.01,
        icon="mdi:tune-vertical",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="frame_rate_divider",
        translation_key="frame_rate_divider",
        name="影格率除數",
        getter=lambda coord: coord.settings.frame_rate_divider,
        setter=lambda coord, value: coord.async_set_fps_divider(int(value)),
        native_min_value=FPS_DIVIDER_MIN,
        native_max_value=FPS_DIVIDER_MAX,
        native_step=1,
        icon="mdi:speedometer",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="percentile",
        translation_key="percentile",
        name="極值裁切",
        getter=lambda coord: coord.settings.percentile,
        setter=lambda coord, value: _set_option(coord, percentile=float(value)),
        native_min_value=PERCENTILE_MIN,
        native_max_value=PERCENTILE_MAX,
        native_step=0.001,
        icon="mdi:chart-bell-curve",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="scale_minimum",
        translation_key="scale_minimum",
        name="色階下限",
        getter=lambda coord: coord.settings.scale_min,
        setter=lambda coord, value: _set_option(coord, scale_min=float(value)),
        native_min_value=-40.0,
        native_max_value=300.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-down",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="scale_maximum",
        translation_key="scale_maximum",
        name="色階上限",
        getter=lambda coord: coord.settings.scale_max,
        setter=lambda coord, value: _set_option(coord, scale_max=float(value)),
        native_min_value=-40.0,
        native_max_value=300.0,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=NumberDeviceClass.TEMPERATURE,
        icon="mdi:arrow-collapse-up",
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="probe_1_x",
        translation_key="probe_1_x",
        name="X1",
        getter=lambda coord: coord.settings.probe_1_x,
        setter=lambda coord, value: _set_option(coord, probe_1_x=int(value)),
        native_min_value=0,
        native_max_value=79,
        native_step=1,
        icon="mdi:axis-x-arrow",
        mode=NumberMode.BOX,
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="probe_1_y",
        translation_key="probe_1_y",
        name="Y1",
        getter=lambda coord: coord.settings.probe_1_y,
        setter=lambda coord, value: _set_option(coord, probe_1_y=int(value)),
        native_min_value=0,
        native_max_value=61,
        native_step=1,
        icon="mdi:axis-y-arrow",
        mode=NumberMode.BOX,
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="probe_2_x",
        translation_key="probe_2_x",
        name="X2",
        getter=lambda coord: coord.settings.probe_2_x,
        setter=lambda coord, value: _set_option(coord, probe_2_x=int(value)),
        native_min_value=0,
        native_max_value=79,
        native_step=1,
        icon="mdi:axis-x-arrow",
        mode=NumberMode.BOX,
        entity_category=None,
    ),
    SenXorNumberDescription(
        key="probe_2_y",
        translation_key="probe_2_y",
        name="Y2",
        getter=lambda coord: coord.settings.probe_2_y,
        setter=lambda coord, value: _set_option(coord, probe_2_y=int(value)),
        native_min_value=0,
        native_max_value=61,
        native_step=1,
        icon="mdi:axis-y-arrow",
        mode=NumberMode.BOX,
        entity_category=None,
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
        self._attr_translation_key = description.translation_key
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    @property
    def native_value(self) -> float:
        return self.entity_description.getter(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        """Push the new value to the camera or to the display settings."""
        await self.entity_description.setter(self.coordinator, value)
