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
CONF_SENSITIVITY: Final = "sensitivity"
CONF_PALETTE: Final = "palette"
CONF_UNIT: Final = "temperature_unit"
CONF_FILTER: Final = "filtering"
CONF_GAIN: Final = "gain"
CONF_AUTO_RANGE: Final = "auto_range"
CONF_REMOVE_EXTREME: Final = "remove_extreme"
CONF_PERCENTILE: Final = "percentile"
CONF_SCALE_MIN: Final = "scale_min"
CONF_SCALE_MAX: Final = "scale_max"
CONF_SHOW_MARKERS: Final = "show_markers"
CONF_SHOW_COLORBAR: Final = "show_colorbar"
CONF_JPEG_QUALITY: Final = "jpeg_quality"
CONF_FPS_DIVIDER: Final = "frame_rate_divider"
CONF_STREAMING: Final = "streaming"
CONF_PROBE_1_X: Final = "probe_1_x"
CONF_PROBE_1_Y: Final = "probe_1_y"
CONF_PROBE_2_X: Final = "probe_2_x"
CONF_PROBE_2_Y: Final = "probe_2_y"

DEFAULT_EMISSIVITY: Final = 97.0  # percent, written to register 0xCA
DEFAULT_OFFSET: Final = 1.5  # degrees Celsius, written to register 0xCB
DEFAULT_SENSITIVITY: Final = 0.95  # correction factor, written to register 0xC2
DEFAULT_GAIN: Final = "Auto"
DEFAULT_UNIT: Final = "°C"
DEFAULT_FILTER: Final = "None"
DEFAULT_SCALE_MIN: Final = 20.0
DEFAULT_SCALE_MAX: Final = 40.0
DEFAULT_JPEG_QUALITY: Final = 85
DEFAULT_FPS_DIVIDER: Final = 0
DEFAULT_STREAMING: Final = True
DEFAULT_PROBE_1: Final = (20, 30)
DEFAULT_PROBE_2: Final = (60, 30)

TEMPERATURE_UNITS: Final = ["°C", "°F", "K", "dK"]
FILTER_MODES: Final = ["None", "Low", "High"]
GAIN_MODES: Final = ["Auto", "1", "0.5", "0.25"]

# Register limits (see protocol.py)
EMISSIVITY_MIN: Final = 1
EMISSIVITY_MAX: Final = 100
OFFSET_MIN: Final = -12.8
OFFSET_MAX: Final = 12.7
SENSITIVITY_MIN: Final = 0.01
SENSITIVITY_MAX: Final = 2.55
FPS_DIVIDER_MIN: Final = 0
FPS_DIVIDER_MAX: Final = 127
PERCENTILE_MIN: Final = 0.0
PERCENTILE_MAX: Final = 0.2

# Attributes exposed on the camera entity, handy for automations/templates.
ATTR_FRAME_SEQUENCE: Final = "frame_sequence"
ATTR_MIN_TEMPERATURE: Final = "min_temperature"
ATTR_MAX_TEMPERATURE: Final = "max_temperature"
ATTR_MEAN_TEMPERATURE: Final = "mean_temperature"
ATTR_CENTER_TEMPERATURE: Final = "center_temperature"
ATTR_FRAME_RATE: Final = "frame_rate"
ATTR_RAW_MIN: Final = "raw_min_dk"
ATTR_RAW_MAX: Final = "raw_max_dk"
ATTR_PROBE_1_TEMPERATURE: Final = "probe_1_temperature"
ATTR_PROBE_2_TEMPERATURE: Final = "probe_2_temperature"
ATTR_VDD: Final = "vdd"
ATTR_DIE_TEMPERATURE: Final = "die_temperature"

SERVICE_SNAPSHOT: Final = "snapshot"
