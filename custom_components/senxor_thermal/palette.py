"""Colour palettes used by the SenXor thermal viewer.

The manufacturer's viewer offers twelve palettes.  The exact lookup tables
live inside the closed source Qt application, so the tables here are faithful
in character (same ordering, same visual intent) rather than byte identical.
Every palette is a list of 256 ``(r, g, b)`` tuples.
"""

from __future__ import annotations

from typing import Final

RGB = tuple[int, int, int]
Stops = tuple[tuple[float, RGB], ...]

# Anchor points, interpolated linearly into 256 entry tables.
_STOPS: Final[dict[str, Stops]] = {
    "INFERNO": (
        (0.00, (0, 0, 4)),
        (0.13, (31, 12, 72)),
        (0.25, (85, 15, 109)),
        (0.38, (136, 34, 106)),
        (0.50, (186, 54, 85)),
        (0.63, (227, 89, 51)),
        (0.75, (249, 140, 10)),
        (0.88, (249, 201, 50)),
        (1.00, (252, 255, 164)),
    ),
    "HEATED_IRON": (
        (0.00, (8, 0, 32)),
        (0.15, (48, 0, 80)),
        (0.30, (96, 4, 112)),
        (0.45, (150, 20, 124)),
        (0.60, (200, 60, 96)),
        (0.72, (232, 110, 50)),
        (0.84, (250, 170, 20)),
        (0.93, (255, 220, 90)),
        (1.00, (255, 255, 230)),
    ),
    "BLACK_BODY": (
        (0.00, (0, 0, 0)),
        (0.20, (40, 0, 0)),
        (0.40, (110, 0, 0)),
        (0.60, (180, 30, 0)),
        (0.75, (235, 90, 10)),
        (0.88, (255, 170, 50)),
        (1.00, (255, 245, 200)),
    ),
    "PLASMA": (
        (0.00, (13, 8, 135)),
        (0.18, (75, 3, 161)),
        (0.35, (126, 3, 168)),
        (0.50, (168, 34, 150)),
        (0.65, (204, 71, 120)),
        (0.80, (237, 121, 83)),
        (0.90, (253, 180, 47)),
        (1.00, (240, 249, 33)),
    ),
    "COOLWARM": (
        (0.00, (59, 76, 192)),
        (0.25, (144, 178, 254)),
        (0.50, (221, 221, 221)),
        (0.75, (245, 156, 125)),
        (1.00, (180, 4, 38)),
    ),
    "IRON_GLOW": (
        (0.00, (0, 0, 0)),
        (0.15, (20, 0, 24)),
        (0.30, (66, 0, 58)),
        (0.45, (126, 8, 46)),
        (0.60, (190, 48, 16)),
        (0.75, (240, 120, 16)),
        (0.88, (255, 196, 70)),
        (1.00, (255, 255, 220)),
    ),
    "GRAYSCALE": (
        (0.00, (0, 0, 0)),
        (1.00, (255, 255, 255)),
    ),
    "BONE": (
        (0.00, (0, 0, 0)),
        (0.25, (46, 46, 62)),
        (0.50, (98, 98, 116)),
        (0.70, (150, 150, 162)),
        (0.85, (200, 200, 204)),
        (1.00, (255, 255, 250)),
    ),
    "BEZIER": (
        (0.00, (0, 0, 128)),
        (0.20, (0, 72, 200)),
        (0.40, (0, 170, 205)),
        (0.55, (90, 226, 150)),
        (0.70, (232, 224, 96)),
        (0.85, (255, 140, 60)),
        (1.00, (190, 8, 0)),
    ),
    "OCEAN": (
        (0.00, (0, 24, 56)),
        (0.25, (0, 72, 108)),
        (0.45, (0, 128, 148)),
        (0.62, (44, 180, 168)),
        (0.78, (130, 222, 196)),
        (0.90, (206, 246, 226)),
        (1.00, (255, 255, 255)),
    ),
    "RAINBOW": (
        (0.00, (60, 0, 120)),
        (0.15, (0, 0, 255)),
        (0.32, (0, 200, 255)),
        (0.48, (0, 220, 60)),
        (0.64, (220, 230, 0)),
        (0.80, (255, 140, 0)),
        (1.00, (255, 0, 0)),
    ),
    "SUMMER": (
        (0.00, (0, 128, 102)),
        (1.00, (255, 255, 102)),
    ),
}

PALETTES: Final[dict[str, list[RGB]]] = {}


def _interpolate(stops: Stops) -> list[RGB]:
    table: list[RGB] = []
    for index in range(256):
        position = index / 255.0
        lower = stops[0]
        upper = stops[-1]
        for i in range(len(stops) - 1):
            if stops[i][0] <= position <= stops[i + 1][0]:
                lower, upper = stops[i], stops[i + 1]
                break
        span = upper[0] - lower[0]
        factor = 0.0 if span <= 0 else (position - lower[0]) / span
        table.append(
            (
                round(lower[1][0] + (upper[1][0] - lower[1][0]) * factor),
                round(lower[1][1] + (upper[1][1] - lower[1][1]) * factor),
                round(lower[1][2] + (upper[1][2] - lower[1][2]) * factor),
            )
        )
    return table


for _name, _stops in _STOPS.items():
    PALETTES[_name] = _interpolate(_stops)

PALETTE_NAMES: Final[list[str]] = list(_STOPS)
DEFAULT_PALETTE: Final = "HEATED_IRON"


def get_palette(name: str) -> list[RGB]:
    """Return the 256 entry table for ``name`` (falling back to the default)."""
    return PALETTES.get(name.upper(), PALETTES[DEFAULT_PALETTE])
