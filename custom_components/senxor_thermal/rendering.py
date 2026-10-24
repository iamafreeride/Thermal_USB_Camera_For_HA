"""Thermal frame processing and image rendering for the SenXor viewer port.

The vendor application shows a false colour thermogram with an optional colour
bar, minimum/maximum markers and a centre crosshair, readouts in °C/°F/K/dK and
three spatial filter strengths.  This module re-implements that pipeline with
pure Python (no numpy dependency) so it runs anywhere Home Assistant runs.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field
from typing import Final

from PIL import Image

_RESAMPLE = getattr(getattr(Image, "Resampling", Image), "BICUBIC")

from .overlay import draw_overlay
from .palette import get_palette
from .protocol import FRAME_HEIGHT, FRAME_WIDTH, ThermalFrame

KELVIN_OFFSET: Final = 273.15
_SIGMA: Final = 5.670374419e-8


# ---------------------------------------------------------------------------
# Temperature helpers
# ---------------------------------------------------------------------------
def dk_to_celsius(value: int | float) -> float:
    """Convert a deci Kelvin sample to Celsius."""
    return value / 10.0 - KELVIN_OFFSET


def celsius_to_unit(value_c: float, unit: str) -> float:
    """Convert Celsius into the requested display unit."""
    if unit == "°F":
        return value_c * 9.0 / 5.0 + 32.0
    if unit == "K":
        return value_c + KELVIN_OFFSET
    if unit == "dK":
        return round((value_c + KELVIN_OFFSET) * 10.0)
    return value_c


def unit_suffix(unit: str) -> str:
    return unit


def format_temperature(value_c: float, unit: str, digits: int = 1) -> str:
    """Format a Celsius value in ``unit`` for display on the image."""
    value = celsius_to_unit(value_c, unit)
    if unit == "dK":
        return f"{value:.0f} dK"
    return f"{value:.{digits}f} {unit}"


# ---------------------------------------------------------------------------
# Calibration (emissivity + user offset)
# ---------------------------------------------------------------------------
def calibrate(pixels: tuple[int, ...], emissivity: float, offset: float) -> list[float]:
    """Convert raw deci Kelvin pixels into calibrated Celsius values.

    Emissivity is applied with the usual grey body approximation

        L_obj = (L_apparent - (1 - e) * L_bg) / e

    where ``L`` is the emitted radiance (∝ T^4).  The background temperature is
    estimated from the coolest 10 % of the frame, which behaves well for the
    indoor scenes this camera is used in.  ``offset`` is then added, matching
    the "Temp Offset" control of the vendor viewer.
    """
    kelvin = [value / 10.0 for value in pixels]
    if emissivity >= 0.999 and offset == 0.0:
        return [value - KELVIN_OFFSET for value in kelvin]

    ambient = _background_kelvin(kelvin)
    result: list[float] = []
    bg4 = ambient**4
    for value in kelvin:
        if emissivity >= 0.999:
            corrected = value
        else:
            radiance = (value**4 - (1.0 - emissivity) * bg4) / emissivity
            corrected = radiance ** 0.25 if radiance > 0 else 0.0
        result.append(corrected - KELVIN_OFFSET + offset)
    return result


def _background_kelvin(kelvin: list[float]) -> float:
    sample = sorted(kelvin)[: max(1, len(kelvin) // 10)]
    return sum(sample) / len(sample)


# ---------------------------------------------------------------------------
# Spatial filtering (None / Low / High), mirrors the viewer's three levels
# ---------------------------------------------------------------------------
def _box_blur(values: list[float], radius: int) -> list[float]:
    if radius <= 0:
        return values
    width, height = FRAME_WIDTH, FRAME_HEIGHT
    out = [0.0] * (width * height)
    for y in range(height):
        y0 = max(0, y - radius)
        y1 = min(height, y + 1 + radius)
        for x in range(width):
            x0 = max(0, x - radius)
            x1 = min(width, x + 1 + radius)
            total = 0.0
            count = 0
            for yy in range(y0, y1):
                row = yy * width
                for xx in range(x0, x1):
                    total += values[row + xx]
                    count += 1
            out[y * width + x] = total / count
    return out


_FILTER_RADIUS: Final = {"None": 0, "Low": 1, "High": 2}


def apply_filter(values: list[float], mode: str) -> list[float]:
    """Apply the selected spatial filter."""
    return _box_blur(values, _FILTER_RADIUS.get(mode, 0))


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class FrameStats:
    """Statistics for one calibrated frame, all values in Celsius."""

    minimum: float
    maximum: float
    mean: float
    median: float
    center: float
    min_position: tuple[int, int]
    max_position: tuple[int, int]

    def as_dict(self) -> dict[str, float]:
        return {
            "minimum": round(self.minimum, 2),
            "maximum": round(self.maximum, 2),
            "mean": round(self.mean, 2),
            "median": round(self.median, 2),
            "center": round(self.center, 2),
        }


def compute_stats(values: list[float]) -> FrameStats:
    """Compute the statistics used by the sensors and the overlay."""
    minimum = min(values)
    maximum = max(values)
    minimum_index = values.index(minimum)
    maximum_index = values.index(maximum)
    ordered = sorted(values)
    count = len(ordered)
    median = ordered[count // 2] if count % 2 else (ordered[count // 2 - 1] + ordered[count // 2]) / 2
    center_index = (FRAME_HEIGHT // 2) * FRAME_WIDTH + FRAME_WIDTH // 2
    return FrameStats(
        minimum=minimum,
        maximum=maximum,
        mean=sum(values) / count,
        median=median,
        center=values[center_index],
        min_position=(minimum_index % FRAME_WIDTH, minimum_index // FRAME_WIDTH),
        max_position=(maximum_index % FRAME_WIDTH, maximum_index // FRAME_WIDTH),
    )


def percentile_limits(values: list[float], trim_percent: float) -> tuple[float, float]:
    """Return (low, high) limits after trimming extreme values."""
    if trim_percent <= 0:
        return min(values), max(values)
    ordered = sorted(values)
    count = len(ordered)
    trim = int(count * (trim_percent / 100.0))
    trim = max(0, min(count // 2 - 1, trim))
    return ordered[trim], ordered[count - 1 - trim]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RenderOptions:
    """Everything that influences the look of the rendered thermogram."""

    palette: str = "HEATED_IRON"
    unit: str = "°C"
    auto_range: bool = True
    scale_min: float = 20.0
    scale_max: float = 40.0
    remove_extreme: bool = False
    trim_percent: float = 0.1
    filtering: str = "None"
    emissivity: float = 0.97
    offset: float = 0.0
    show_markers: bool = True
    show_colorbar: bool = True
    show_crosshair: bool = True
    probes: tuple[tuple[int, int], ...] = ()
    width: int = 640
    height: int = 496
    jpeg_quality: int = 85


@dataclass(slots=True)
class RenderedFrame:
    """Result of the rendering pipeline."""

    jpeg: bytes
    stats: FrameStats
    scale_min: float
    scale_max: float
    values: list[float] = field(repr=False, default_factory=list)


def _colorize(values: list[float], low: float, high: float, palette: str) -> Image.Image:
    """Map calibrated values onto the palette and build an 80x62 RGB image."""
    table = get_palette(palette)
    span = high - low
    if span <= 0:
        span = 1e-6
    buffer = bytearray(FRAME_WIDTH * FRAME_HEIGHT * 3)
    index = 0
    for value in values:
        position = int((value - low) / span * 255.0)
        if position < 0:
            position = 0
        elif position > 255:
            position = 255
        red, green, blue = table[position]
        buffer[index] = red
        buffer[index + 1] = green
        buffer[index + 2] = blue
        index += 3
    return Image.frombytes("RGB", (FRAME_WIDTH, FRAME_HEIGHT), bytes(buffer))


def render_values(values: list[float], options: RenderOptions) -> RenderedFrame:
    """Compose a JPEG image from already calibrated Celsius ``values``."""
    stats = compute_stats(values)
    if options.auto_range:
        if options.remove_extreme:
            low, high = percentile_limits(values, options.trim_percent)
        else:
            low, high = stats.minimum, stats.maximum
    else:
        low, high = options.scale_min, options.scale_max
    if high - low < 0.5:
        high = low + 0.5

    image = _colorize(values, low, high, options.palette)
    image = image.resize((options.width, options.height), _RESAMPLE)
    probe_labels = []
    for index, (x, y) in enumerate(options.probes, start=1):
        px = max(0, min(FRAME_WIDTH - 1, x))
        py = max(0, min(FRAME_HEIGHT - 1, y))
        probe_labels.append((px, py, f"P{index} {format_temperature(values[py * FRAME_WIDTH + px], options.unit)}"))
    draw_overlay(image, stats, options, low, high, format_temperature, probe_labels)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=options.jpeg_quality)
    return RenderedFrame(
        jpeg=buffer.getvalue(),
        stats=stats,
        scale_min=low,
        scale_max=high,
        values=values,
    )


def render_frame(frame: ThermalFrame, options: RenderOptions) -> RenderedFrame:
    """Calibrate, filter and render a raw thermal ``frame``."""
    values = calibrate(frame.pixels, options.emissivity, options.offset)
    values = apply_filter(values, options.filtering)
    return render_values(values, options)


def frame_to_csv(frame: ThermalFrame, options: RenderOptions) -> str:
    """Render the calibrated frame as CSV (raw and calibrated values)."""
    values = calibrate(frame.pixels, options.emissivity, options.offset)
    lines = ["# SenXor thermal frame"]
    lines.append(f"# sequence {frame.sequence}")
    lines.append(f"# received {frame.received}")
    lines.append("# raw values in deci Kelvin; temperate in " + options.unit)
    for y in range(FRAME_HEIGHT):
        row = []
        for x in range(FRAME_WIDTH):
            index = y * FRAME_WIDTH + x
            raw = frame.pixels[index]
            row.append(f"{raw}:{celsius_to_unit(values[index], options.unit):.2f}")
        lines.append(",".join(row))
    return "\n".join(lines)


def round_sig(value: float, digits: int = 2) -> float:
    """Round, guarding against NaN/inf coming from odd sensor readings."""
    if value is None or not math.isfinite(value):
        return 0.0
    return round(value, digits)
