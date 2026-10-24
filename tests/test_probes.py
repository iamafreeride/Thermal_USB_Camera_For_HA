"""Tests for the 1.2.0 additions: probes, pressable buttons, sensor list."""

import asyncio
import unittest

import ha_stub

ha_stub.install()

from common import load  # noqa: E402

protocol = load("protocol")
coordinator_module = load("coordinator")
sensor_module = load("sensor")
number_module = load("number")
button_module = load("button")
rendering = load("rendering")


def build_coordinator():
    import sys

    hass = sys.modules["homeassistant.core"].HomeAssistant()
    entry = sys.modules["homeassistant.config_entries"].ConfigEntry(
        data={"host": "192.0.2.10", "port": 3333}, title="Thermal Camera"
    )
    coordinator = coordinator_module.SenXorCoordinator(hass, entry, "192.0.2.10", 3333, 1.0)
    messages, _ = protocol.parse_messages(
        (__import__("pathlib").Path(__file__).resolve().parent.parent / "docs" / "captures" / "camera_frames_sample.bin").read_bytes()
    )
    frame = protocol.decode_frame(messages[0][1], 0)
    coordinator._handle_frame(frame)
    coordinator._connection.connected = True
    coordinator.async_set_updated_data(coordinator._build_data())
    return coordinator, entry


class ProbeSensorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: sensor_module.SenXorSensor(self.coordinator, self.entry, description)
            for description in sensor_module.SENSORS
        }

    def test_frames_received_removed(self) -> None:
        self.assertNotIn("frames_received", self.entities)

    def test_default_probe_coordinates(self) -> None:
        self.assertEqual(self.coordinator.settings.probes, ((20, 31), (60, 31)))

    def test_probe_temperatures_match_pixels(self) -> None:
        values = self.coordinator.data.values
        for probe, (x, y) in ((1, (20, 31)), (2, (60, 31))):
            expected = round(values[y * 80 + x], 2)
            self.assertAlmostEqual(self.entities[f"probe_{probe}_temperature"].native_value, expected)

    def test_coordinate_change_moves_probe(self) -> None:
        asyncio.run(self.coordinator.async_update_settings(probe_1_x=0, probe_1_y=0))
        self.assertEqual(self.coordinator.settings.probes[0], (0, 0))
        self.assertAlmostEqual(
            self.entities["probe_1_temperature"].native_value,
            round(self.coordinator.data.values[0], 2),
        )

    def test_coordinates_are_clamped(self) -> None:
        asyncio.run(self.coordinator.async_update_settings(probe_1_x=500, probe_1_y=-20))
        self.assertEqual(self.coordinator.settings.probes[0], (79, 0))


class ProbeNumberTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: number_module.SenXorNumber(self.coordinator, self.entry, description)
            for description in number_module.NUMBERS
        }

    def test_all_four_coordinates_exist(self) -> None:
        for key in ("probe_1_x", "probe_1_y", "probe_2_x", "probe_2_y"):
            self.assertIn(key, self.entities)

    def test_ranges(self) -> None:
        self.assertEqual(self.entities["probe_1_x"]._attr_native_max_value, 79)
        self.assertEqual(self.entities["probe_1_y"]._attr_native_max_value, 61)

    def test_setting_a_coordinate_persists(self) -> None:
        asyncio.run(self.entities["probe_2_y"].async_set_native_value(10))
        self.assertEqual(self.coordinator.settings.probe_2_y, 10)
        self.assertEqual(self.entry.options["probe_2_y"], 10)


class ButtonAvailabilityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.buttons = {
            description.key: button_module.SenXorButton(self.coordinator, self.entry, description)
            for description in button_module.BUTTONS
        }

    def test_buttons_available_when_disconnected(self) -> None:
        self.coordinator._connection.connected = False
        for button in self.buttons.values():
            self.assertTrue(button.available)

    def test_press_reconnects_first(self) -> None:
        calls: list[str] = []
        self.coordinator._connection.connected = False

        async def fake_connect(*args, **kwargs):
            calls.append("connect")
            self.coordinator._connection.connected = True

        async def fake_single():
            calls.append("single")

        self.coordinator.async_connect = fake_connect
        self.coordinator.async_single_frame = fake_single
        asyncio.run(self.buttons["single_frame"].async_press())
        self.assertEqual(calls, ["connect", "single"])


class ProbeRenderTest(unittest.TestCase):
    def test_render_with_probes(self) -> None:
        coordinator, _ = build_coordinator()
        options = coordinator.settings.render_options()
        self.assertEqual(options.probes, ((20, 31), (60, 31)))
        rendered = rendering.render_values(coordinator.data.values, options)
        self.assertTrue(rendered.jpeg.startswith(b"\xff\xd8"))


if __name__ == "__main__":
    unittest.main()
