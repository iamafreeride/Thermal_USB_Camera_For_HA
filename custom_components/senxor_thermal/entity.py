"""Shared entity helpers for the SenXor thermal camera integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import SenXorCoordinator

# Chinese entity names contain no ASCII letters, so Home Assistant's slugify()
# would produce an empty object id.  Pin an explicit English entity_id for every
# entity while keeping the Chinese display name.
ENTITY_IDS: dict[str, dict[str, str]] = {
    "sensor": {
        "minimum_temperature": "thermal_camera_minimum_temperature",
        "maximum_temperature": "thermal_camera_maximum_temperature",
        "average_temperature": "thermal_camera_average_temperature",
        "center_temperature": "thermal_camera_centre_temperature",
        "probe_1_temperature": "thermal_camera_temperature_1",
        "probe_2_temperature": "thermal_camera_temperature_2",
        "hotspot_x": "thermal_camera_hotspot_x",
        "hotspot_y": "thermal_camera_hotspot_y",
        "die_temperature": "thermal_camera_die_temperature",
        "vdd": "thermal_camera_vdd",
        "frame_rate": "thermal_camera_frame_rate",
    },
    "number": {
        "emissivity": "thermal_camera_emissivity",
        "temperature_offset": "thermal_camera_temperature_offset",
        "sensitivity": "thermal_camera_sensitivity",
        "frame_rate_divider": "thermal_camera_frame_rate_divider",
        "percentile": "thermal_camera_percentile",
        "scale_minimum": "thermal_camera_scale_min",
        "scale_maximum": "thermal_camera_scale_max",
        "probe_1_x": "thermal_camera_x1",
        "probe_1_y": "thermal_camera_y1",
        "probe_2_x": "thermal_camera_x2",
        "probe_2_y": "thermal_camera_y2",
    },
    "select": {
        "palette": "thermal_camera_palette",
        "temperature_unit": "thermal_camera_temperature_unit",
        "filtering": "thermal_camera_filtering",
        "gain": "thermal_camera_gain",
    },
    "switch": {
        "streaming": "thermal_camera_streaming",
        "auto_range": "thermal_camera_auto_range",
        "remove_extreme": "thermal_camera_remove_extreme",
        "show_markers": "thermal_camera_show_markers",
        "show_colorbar": "thermal_camera_show_colorbar",
    },
    "button": {
        "single_frame": "thermal_camera_single_frame",
        "reconnect": "thermal_camera_reconnect",
        "disconnect": "thermal_camera_disconnect",
        "increase_frame_rate": "thermal_camera_fps_increase",
        "decrease_frame_rate": "thermal_camera_fps_decrease",
    },
}

PLATFORM_CAMERA = "camera"


class SenXorEntity(CoordinatorEntity[SenXorCoordinator]):
    """Base class that wires entities to the shared device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        key: str,
        platform: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        object_id = ENTITY_IDS.get(platform, {}).get(key)
        if object_id is not None:
            # Set before the entity is added so Home Assistant keeps this id.
            self.entity_id = f"{platform}.{object_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.available
