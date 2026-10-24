"""Sensor platform: temperatures, frame statistics and device diagnostics."""

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
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfTemperature,
)
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
        name="最低溫",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.minimum),
    ),
    SenXorSensorDescription(
        key="maximum_temperature",
        translation_key="maximum_temperature",
        name="最高溫",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.maximum),
    ),
    SenXorSensorDescription(
        key="average_temperature",
        translation_key="average_temperature",
        name="平均溫",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.mean),
    ),
    SenXorSensorDescription(
        key="center_temperature",
        translation_key="center_temperature",
        name="中心溫",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        value_fn=_stats_value(lambda stats: stats.center),
    ),
    SenXorSensorDescription(
        key="probe_1_temperature",
        translation_key="probe_1_temperature",
        name="溫度1",
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
        name="溫度2",
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
        name="熱點 X",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:axis-x-arrow",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_stats_value(lambda stats: float(stats.max_position[0])),
    ),
    SenXorSensorDescription(
        key="hotspot_y",
        translation_key="hotspot_y",
        name="熱點 Y",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:axis-y-arrow",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_stats_value(lambda stats: float(stats.max_position[1])),
    ),
    SenXorSensorDescription(
        key="die_temperature",
        translation_key="die_temperature",
        name="晶片溫度",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:thermometer",
        value_fn=lambda data: None if data.die_temperature is None else round(data.die_temperature, 2),
    ),
    SenXorSensorDescription(
        key="vdd",
        translation_key="vdd",
        name="供應電壓",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        suggested_display_precision=4,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:flash",
        value_fn=lambda data: None if data.vdd is None else round(data.vdd, 4),
    ),
    SenXorSensorDescription(
        key="frame_rate",
        translation_key="frame_rate",
        name="影格率",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="fps",
        icon="mdi:speedometer",
        suggested_display_precision=1,
        value_fn=lambda data: data.frame_rate,
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
        super().__init__(coordinator, entry, description.key, "sensor")
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_name = description.name

    @property
    def native_value(self) -> float | int | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, int] | None:
        """Expose the pixel coordinate behind each probe reading."""
        key = self.entity_description.key
        if key not in ("probe_1_temperature", "probe_2_temperature"):
            return None
        index = 0 if key.startswith("probe_1") else 1
        x, y = self.coordinator.settings.probes[index]
        return {"pixel_x": x, "pixel_y": y}
