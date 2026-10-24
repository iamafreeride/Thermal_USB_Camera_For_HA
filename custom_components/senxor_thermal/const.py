"""Constants for the SenXor thermal camera integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "senxor_thermal"
NAME: Final = "SenXor Thermal Camera"
MANUFACTURER: Final = "Meridian Innovation"
MODEL: Final = "SenXor thermal module (TCP bridge)"

DEFAULT_PORT: Final = 3333
DEFAULT_NAME: Final = "Thermal Camera"
DEFAULT_SCAN_INTERVAL: Final = 1
MIN_SCAN_INTERVAL: Final = 0.2

CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_EMISSIVITY: Final = "emissivity"
CONF_OFFSET: Final = "temperature_offset"
CONF_PALETTE: Final = "palette"
CONF_UNIT: Final = "temperature_unit"
CONF_FILTER: Final = "filtering"
CONF_GAIN: Final = "gain"
CONF_AUTO_RANGE: Final = "auto_range"
CONF_REMOVE_EXTREME: Final = "remove_extreme"
CONF_SCALE_MIN: Final = "scale_min"
CONF_SCALE_MAX: Final = "scale_max"
CONF_SHOW_MARKERS: Final = "show_markers"
CONF_SHOW_COLORBAR: Final = "show_colorbar"
CONF_JPEG_QUALITY: Final = "jpeg_quality"

DEFAULT_EMISSIVITY: Final = 0.97
DEFAULT_OFFSET: Final = 1.5
DEFAULT_UNIT: Final = "°C"
DEFAULT_FILTER: Final = "None"
DEFAULT_GAIN: Final = "1"
DEFAULT_SCALE_MIN: Final = 20.0
DEFAULT_SCALE_MAX: Final = 40.0
DEFAULT_JPEG_QUALITY: Final = 85

TEMPERATURE_UNITS: Final = ["°C", "°F", "K", "dK"]
FILTER_MODES: Final = ["None", "Low", "High"]
GAIN_MODES: Final = ["0.25", "0.5", "1"]

# Attributes exposed on the camera entity, handy for automations/templates.
ATTR_FRAME_SEQUENCE: Final = "frame_sequence"
ATTR_MIN_TEMPERATURE: Final = "min_temperature"
ATTR_MAX_TEMPERATURE: Final = "max_temperature"
ATTR_MEAN_TEMPERATURE: Final = "mean_temperature"
ATTR_CENTER_TEMPERATURE: Final = "center_temperature"
ATTR_FRAME_RATE: Final = "frame_rate"
ATTR_RAW_MIN: Final = "raw_min_dk"
ATTR_RAW_MAX: Final = "raw_max_dk"

SERVICE_SNAPSHOT: Final = "snapshot"
