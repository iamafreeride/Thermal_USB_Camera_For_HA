"""Sensor platform: temperatures and stream statistics."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SenXorCoordinator, SenXorData
from .entity import SenXorEntity
from .rendering import FrameStats

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SenXorSensorDescription(SensorEntityDescription):
    """Describes a SenXor sensor and how to derive its value."""

    value_fn: Callable[[SenXorData], float | None]


def _stats_value(selector: Callable[[FrameStats], float]) -> Callable[[SenXorData], float | None]:
    def _get(data: SenXorData) -> float | None:
        if data.stats is None:
            return None
        return round(selector(data.stats), 2)

    return _get


SENSORS: tuple[SenXorSensorDescription, ...] = (
    SenXorSensorDescription(
        key="minimum_temperature",
        translation_key="minimum_temperature",
        name="Minimum temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.minimum),
    ),
    SenXorSensorDescription(
        key="maximum_temperature",
        translation_key="maximum_temperature",
        name="Maximum temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.maximum),
    ),
    SenXorSensorDescription(
        key="average_temperature",
        translation_key="average_temperature",
        name="Average temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.mean),
    ),
    SenXorSensorDescription(
        key="center_temperature",
        translation_key="center_temperature",
        name="Centre temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.center),
    ),
    SenXorSensorDescription(
        key="frame_rate",
        translation_key="frame_rate",
        name="Frame rate",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="fps",
        icon="mdi:speedometer",
        suggested_display_precision=1,
        value_fn=lambda data: data.frame_rate,
    ),
    SenXorSensorDescription(
        key="probe_1_temperature",
        translation_key="probe_1_temperature",
        name="Probe 1 temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        icon="mdi:crosshairs-gps",
        value_fn=lambda data: None if data.probe_1 is None else round(data.probe_1, 2),
    ),
    SenXorSensorDescription(
        key="probe_2_temperature",
        translation_key="probe_2_temperature",
        name="Probe 2 temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        icon="mdi:crosshairs-gps",
        value_fn=lambda data: None if data.probe_2 is None else round(data.probe_2, 2),
    ),
    SenXorSensorDescription(
        key="hotspot_x",
        translation_key="hotspot_x",
        name="Hotspot X",
        icon="mdi:axis-x-arrow",
        value_fn=_stats_value(lambda stats: float(stats.max_position[0])),
    ),
    SenXorSensorDescription(
        key="hotspot_y",
        translation_key="hotspot_y",
        name="Hotspot Y",
        icon="mdi:axis-y-arrow",
        value_fn=_stats_value(lambda stats: float(stats.max_position[1])),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SenXor sensors."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities(
        SenXorSensor(coordinator, entry, description) for description in SENSORS
    )


class SenXorSensor(SenXorEntity, SensorEntity):
    """A sensor derived from the latest thermal frame."""

    entity_description: SenXorSensorDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.translation_key

    @property
    def native_value(self) -> float | int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)
