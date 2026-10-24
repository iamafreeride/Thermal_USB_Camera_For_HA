"""Setup smoke test: exercises async_setup_entry and every platform."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
import unittest
from pathlib import Path

import ha_stub

ha_stub.install()

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "custom_components" / "senxor_thermal"

# voluptuous is only used by __init__/config_flow; provide a tiny stand-in.
if "voluptuous" not in sys.modules:
    vol = types.ModuleType("voluptuous")

    class _Marker:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

    class _Schema:
        def __init__(self, schema, extra=None):
            self.schema = schema

        def __call__(self, data):
            return data

    vol.Schema = _Schema
    vol.Required = lambda key, default=None: _Marker(key, default)
    vol.Optional = lambda key, default=None: _Marker(key, default)
    vol.All = lambda *validators: validators
    vol.Coerce = lambda kind: kind
    vol.Range = lambda **kwargs: None
    vol.In = lambda *args, **kwargs: None
    sys.modules["voluptuous"] = vol

# Import the *real* package (executes __init__.py) rather than a synthetic module.
_spec = importlib.util.spec_from_file_location(
    "senxor_thermal", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)]
)
assert _spec and _spec.loader
integration = importlib.util.module_from_spec(_spec)
sys.modules["senxor_thermal"] = integration
_spec.loader.exec_module(integration)

from senxor_thermal import button, camera, number, protocol, select, sensor, switch  # noqa: E402
from senxor_thermal.const import DOMAIN  # noqa: E402
from senxor_thermal.coordinator import SenXorCoordinator  # noqa: E402


def sample_frames() -> bytes:
    return (REPO / "docs" / "captures" / "camera_frames_sample.bin").read_bytes()


def _fake_frame():
    messages, _ = protocol.parse_messages(sample_frames())
    return protocol.decode_frame(messages[0][1], 0)


async def _fake_connect(self, wait_for_frame: float = 8.0, attempts: int = 2) -> None:
    """Stand-in for the TCP connect that simply delivers one recorded frame."""
    self._handle_frame(_fake_frame())
    self._connection.connected = True


class SetupTest(unittest.TestCase):
    def setUp(self) -> None:
        self._original_connect = SenXorCoordinator.async_connect
        SenXorCoordinator.async_connect = _fake_connect

        self.hass = sys.modules["homeassistant.core"].HomeAssistant()
        entry_cls = sys.modules["homeassistant.config_entries"].ConfigEntry
        self.entry = entry_cls(
            data={"host": "192.0.2.10", "port": 3333}, title="Thermal Camera"
        )

    def tearDown(self) -> None:
        SenXorCoordinator.async_connect = self._original_connect

    def test_setup_and_unload(self) -> None:
        async def run() -> None:
            ok = await integration.async_setup_entry(self.hass, self.entry)
            self.assertTrue(ok)
            self.assertIsInstance(self.entry.runtime_data, SenXorCoordinator)
            self.assertIn(self.entry.entry_id, self.hass.data[DOMAIN])
            self.assertTrue(self.hass.services.has_service(DOMAIN, "snapshot"))

            for module in (camera, sensor, number, select, switch, button):
                collected: list = []
                await module.async_setup_entry(
                    self.hass, self.entry, lambda entities, c=collected: c.extend(entities)
                )
                self.assertTrue(collected, f"{module.__name__} created no entities")

            unloaded = await integration.async_unload_entry(self.hass, self.entry)
            self.assertTrue(unloaded)
            self.assertNotIn(self.entry.entry_id, self.hass.data[DOMAIN])

        asyncio.run(run())

    def test_config_flow_module_imports(self) -> None:
        flow = importlib.import_module("senxor_thermal.config_flow")
        self.assertTrue(hasattr(flow, "SenXorConfigFlow"))
        self.assertTrue(hasattr(flow, "SenXorOptionsFlow"))

    def test_entities_expose_values(self) -> None:
        async def run() -> None:
            await integration.async_setup_entry(self.hass, self.entry)
            coordinator = self.entry.runtime_data

            collected: list = []
            await sensor.async_setup_entry(
                self.hass, self.entry, lambda entities: collected.extend(entities)
            )
            values = {entity.entity_description.key: entity.native_value for entity in collected}
            self.assertIsNotNone(values["maximum_temperature"])
            self.assertIsNotNone(values["vdd"])
            self.assertIsNotNone(values["die_temperature"])
            self.assertIsNotNone(values["probe_1_temperature"])
            self.assertIsNotNone(values["frame_rate"])

            numbers: list = []
            await number.async_setup_entry(
                self.hass, self.entry, lambda entities: numbers.extend(entities)
            )
            by_key = {entity.entity_description.key: entity for entity in numbers}
            self.assertEqual(by_key["emissivity"].native_value, 97.0)
            self.assertEqual(by_key["frame_rate_divider"].native_value, 0)

            image = await camera.SenXorThermalCamera(coordinator, self.entry).async_camera_image()
            self.assertTrue(image.startswith(b"\xff\xd8"))

            await integration.async_unload_entry(self.hass, self.entry)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
