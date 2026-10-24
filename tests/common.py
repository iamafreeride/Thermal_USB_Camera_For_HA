"""Test helpers: import the integration modules without a Home Assistant install."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPONENT = ROOT / "custom_components" / "senxor_thermal"


def load(module: str):
    """Import ``senxor_thermal.<module>`` without executing the package __init__."""
    if "senxor_thermal" not in sys.modules:
        package = types.ModuleType("senxor_thermal")
        package.__path__ = [str(COMPONENT)]
        sys.modules["senxor_thermal"] = package
    return importlib.import_module(f"senxor_thermal.{module}")


def sample_frames() -> bytes:
    """Three complete GFRA messages recorded from the live camera."""
    return (ROOT / "docs" / "captures" / "camera_frames_sample.bin").read_bytes()
