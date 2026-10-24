"""Camera platform: false colour thermogram of the SenXor thermal module."""

from __future__ import annotations

import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CENTER_TEMPERATURE,
    ATTR_FRAME_RATE,
    ATTR_FRAME_SEQUENCE,
    ATTR_MAX_TEMPERATURE,
    ATTR_MEAN_TEMPERATURE,
    ATTR_MIN_TEMPERATURE,
    ATTR_PROBE_1_TEMPERATURE,
    ATTR_PROBE_2_TEMPERATURE,
    ATTR_RAW_MAX,
    ATTR_RAW_MIN,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import SenXorCoordinator
from .protocol import FRAME_HEIGHT, FRAME_WIDTH
from .rendering import FrameStats, celsius_to_unit

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the SenXor camera entity."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities([SenXorThermalCamera(coordinator, entry)])


class SenXorThermalCamera(CoordinatorEntity[SenXorCoordinator], Camera):
    """A still image camera that renders the thermogram at full resolution."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_brand = MANUFACTURER
    _attr_model = MODEL
    _attr_supported_features = CameraEntityFeature(0)

    def __init__(self, coordinator: SenXorCoordinator, entry: ConfigEntry) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._attr_unique_id = f"{entry.entry_id}_camera"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=f"http://{coordinator.host}:{coordinator.port}",
        )
        self.content_type = "image/jpeg"

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.available

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the newest thermogram as JPEG."""
        rendered = await self.coordinator.async_render()
        if rendered is None:
            return None
        return rendered.jpeg

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        data = self.coordinator.data
        if data is None or data.frame is None:
            return None
        stats: FrameStats | None = data.stats
        unit = self.coordinator.settings.unit
        attributes: dict[str, object] = {
            ATTR_FRAME_SEQUENCE: data.frame.sequence,
            ATTR_FRAME_RATE: data.frame_rate,
            ATTR_RAW_MIN: data.frame.min_dk,
            ATTR_RAW_MAX: data.frame.max_dk,
        }
        if stats is not None:
            attributes.update(
                {
                    ATTR_MIN_TEMPERATURE: round(celsius_to_unit(stats.minimum, unit), 2),
                    ATTR_MAX_TEMPERATURE: round(celsius_to_unit(stats.maximum, unit), 2),
                    ATTR_MEAN_TEMPERATURE: round(celsius_to_unit(stats.mean, unit), 2),
                    ATTR_CENTER_TEMPERATURE: round(celsius_to_unit(stats.center, unit), 2),
                }
            )
        attributes["frame_size"] = f"{FRAME_WIDTH}x{FRAME_HEIGHT}"
        attributes["temperature_unit"] = unit
        attributes["palette"] = self.coordinator.settings.palette
        attributes["streaming"] = self.coordinator.streaming
        attributes["frame_rate_level"] = self.coordinator.settings.fps_level
        probe_1 = self.coordinator.probe_temperature(1)
        probe_2 = self.coordinator.probe_temperature(2)
        if probe_1 is not None:
            attributes[ATTR_PROBE_1_TEMPERATURE] = round(celsius_to_unit(probe_1, unit), 2)
        if probe_2 is not None:
            attributes[ATTR_PROBE_2_TEMPERATURE] = round(celsius_to_unit(probe_2, unit), 2)
        return attributes
