"""Entity level tests using lightweight Home Assistant stubs."""

from __future__ import annotations

import asyncio
import unittest

import ha_stub

ha_stub.install()

from common import load, sample_frames  # noqa: E402

protocol = load("protocol")
coordinator_module = load("coordinator")
camera_module = load("camera")
sensor_module = load("sensor")
number_module = load("number")
select_module = load("select")
switch_module = load("switch")
button_module = load("button")


def build_coordinator(scan_interval: float = 1.0):
    hass = ha_stub_config()
    entry = sys_modules_entry()
    coordinator = coordinator_module.SenXorCoordinator(
        hass, entry, "192.0.2.10", 3333, scan_interval
    )
    messages, _ = protocol.parse_messages(sample_frames())
    frame = protocol.decode_frame(messages[0][1], 0)
    coordinator._handle_frame(frame)
    coordinator._connection.connected = True
    coordinator.async_set_updated_data(coordinator._build_data())
    return coordinator, entry


def ha_stub_config():
    import sys

    return sys.modules["homeassistant.core"].HomeAssistant()


def sys_modules_entry():
    import sys

    entry_cls = sys.modules["homeassistant.config_entries"].ConfigEntry
    return entry_cls(data={"host": "192.0.2.10", "port": 3333}, title="Thermal Camera")


class CoordinatorTest(unittest.TestCase):
    def test_build_data_statistics(self) -> None:
        coordinator, _ = build_coordinator()
        data = coordinator.data
        self.assertIsNotNone(data.frame)
        self.assertEqual(len(data.values), 80 * 62)
        self.assertAlmostEqual(data.stats.maximum, max(data.values), places=6)
        self.assertAlmostEqual(data.stats.minimum, min(data.values), places=6)
        self.assertTrue(data.available)

    def test_frame_rate_needs_two_frames(self) -> None:
        coordinator, _ = build_coordinator()
        self.assertEqual(coordinator.data.frame_rate, 0.0)

    def test_settings_are_persisted(self) -> None:
        coordinator, entry = build_coordinator()
        asyncio.run(coordinator.async_update_settings(palette="OCEAN", emissivity=0.5))
        self.assertEqual(coordinator.settings.palette, "OCEAN")
        self.assertEqual(entry.options["palette"], "OCEAN")
        self.assertAlmostEqual(entry.options["emissivity"], 0.5)

    def test_render_produces_jpeg(self) -> None:
        coordinator, _ = build_coordinator()
        rendered = asyncio.run(coordinator.async_render())
        self.assertTrue(rendered.jpeg.startswith(b"\xff\xd8"))
        # second call hits the cache for the same frame
        again = asyncio.run(coordinator.async_render())
        self.assertEqual(rendered.jpeg, again.jpeg)


class CameraEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entity = camera_module.SenXorThermalCamera(self.coordinator, self.entry)

    def test_available(self) -> None:
        self.assertTrue(self.entity.available)
        self.assertEqual(self.entity.unique_id, "test-entry_camera")

    def test_image(self) -> None:
        image = asyncio.run(self.entity.async_camera_image())
        self.assertTrue(image.startswith(b"\xff\xd8"))

    def test_attributes(self) -> None:
        attributes = self.entity.extra_state_attributes
        self.assertIn("frame_sequence", attributes)
        self.assertIn("max_temperature", attributes)
        self.assertEqual(attributes["frame_size"], "80x62")


class SensorEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = [
            sensor_module.SenXorSensor(self.coordinator, self.entry, description)
            for description in sensor_module.SENSORS
        ]

    def test_all_sensors_have_values(self) -> None:
        for entity in self.entities:
            with self.subTest(entity=entity.entity_description.key):
                value = entity.native_value
                self.assertIsNotNone(value)

    def test_temperature_sensors_match_stats(self) -> None:
        stats = self.coordinator.data.stats
        by_key = {e.entity_description.key: e for e in self.entities}
        self.assertAlmostEqual(by_key["minimum_temperature"].native_value, round(stats.minimum, 2))
        self.assertAlmostEqual(by_key["maximum_temperature"].native_value, round(stats.maximum, 2))
        self.assertAlmostEqual(by_key["center_temperature"].native_value, round(stats.center, 2))

    def test_unique_ids(self) -> None:
        unique = {entity.unique_id for entity in self.entities}
        self.assertEqual(len(unique), len(self.entities))


class NumberEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: number_module.SenXorNumber(self.coordinator, self.entry, description)
            for description in number_module.NUMBERS
        }

    def test_initial_values(self) -> None:
        self.assertAlmostEqual(self.entities["emissivity"].native_value, 97.0)
        self.assertAlmostEqual(self.entities["temperature_offset"].native_value, 1.5)

    def test_set_value_updates_settings(self) -> None:
        asyncio.run(self.entities["temperature_offset"].async_set_native_value(3.4))
        self.assertAlmostEqual(self.coordinator.settings.offset, 3.4)
        self.assertAlmostEqual(self.entities["temperature_offset"].native_value, 3.4)


class SelectEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: select_module.SenXorSelect(self.coordinator, self.entry, description)
            for description in select_module.SELECTS
        }

    def test_palette_selection(self) -> None:
        entity = self.entities["palette"]
        self.assertEqual(entity.current_option, "HEATED_IRON")
        self.assertIn("OCEAN", entity.options)
        asyncio.run(entity.async_select_option("OCEAN"))
        self.assertEqual(entity.current_option, "OCEAN")

    def test_filtering_selection(self) -> None:
        entity = self.entities["filtering"]
        asyncio.run(entity.async_select_option("High"))
        self.assertEqual(self.coordinator.settings.filtering, "High")

    def test_unit_selection(self) -> None:
        entity = self.entities["temperature_unit"]
        self.assertEqual(entity.options, ["°C", "°F", "K", "dK"])
        asyncio.run(entity.async_select_option("°F"))
        self.assertEqual(self.coordinator.settings.unit, "°F")


class FrameRateButtonTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.sent: list[int] = []

        async def fake_set_divider(divider: int) -> int:
            self.sent.append(divider)
            return divider

        self.coordinator._connection.set_fps_divider = fake_set_divider
        self.buttons = {
            description.key: button_module.SenXorButton(self.coordinator, self.entry, description)
            for description in button_module.BUTTONS
        }

    def test_increase_lowers_the_divider(self) -> None:
        asyncio.run(self.coordinator.async_set_fps_divider(3))
        asyncio.run(self.buttons["increase_frame_rate"].async_press())
        self.assertEqual(self.sent[-1], 2)
        self.assertEqual(self.coordinator.settings.frame_rate_divider, 2)
        self.assertEqual(self.entry.options["frame_rate_divider"], 2)

    def test_decrease_raises_the_divider(self) -> None:
        asyncio.run(self.coordinator.async_set_fps_divider(2))
        asyncio.run(self.buttons["decrease_frame_rate"].async_press())
        self.assertEqual(self.sent[-1], 3)
        self.assertEqual(self.coordinator.settings.frame_rate_divider, 3)

    def test_divider_is_clamped(self) -> None:
        asyncio.run(self.coordinator.async_set_fps_divider(0))
        asyncio.run(self.buttons["increase_frame_rate"].async_press())
        self.assertEqual(self.sent[-1], 0)
        asyncio.run(self.coordinator.async_set_fps_divider(127))
        asyncio.run(self.buttons["decrease_frame_rate"].async_press())
        self.assertEqual(self.sent[-1], 127)


class GainSelectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.sent: list[int] = []

        async def fake_set_gain(value: int) -> None:
            self.sent.append(value)

        self.coordinator._connection.set_gain = fake_set_gain
        descriptions = {d.key: d for d in select_module.SELECTS}
        self.entity = select_module.SenXorSelect(
            self.coordinator, self.entry, descriptions["gain"]
        )

    def test_options_and_default(self) -> None:
        self.assertEqual(self.entity.options, ["Auto", "1", "0.5", "0.25"])
        self.assertEqual(self.entity.current_option, "Auto")

    def test_select_option_writes_register(self) -> None:
        asyncio.run(self.entity.async_select_option("0.25"))
        self.assertEqual(self.sent[-1], 2)  # 0=B1.0, 1=auto, 2=0.25, 3=0.5
        self.assertEqual(self.coordinator.settings.gain, "0.25")


class SwitchEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: switch_module.SenXorSwitch(self.coordinator, self.entry, description)
            for description in switch_module.SWITCHES
        }

    def test_toggle(self) -> None:
        entity = self.entities["auto_range"]
        self.assertTrue(entity.is_on)
        asyncio.run(entity.async_turn_off())
        self.assertFalse(entity.is_on)
        asyncio.run(entity.async_turn_on())
        self.assertTrue(entity.is_on)


class ButtonEntityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.coordinator, self.entry = build_coordinator()
        self.entities = {
            description.key: button_module.SenXorButton(self.coordinator, self.entry, description)
            for description in button_module.BUTTONS
        }

    def test_buttons_delegate_to_coordinator(self) -> None:
        calls: list[str] = []

        async def fake_disconnect():
            calls.append("disconnect")

        async def fake_connect():
            calls.append("connect")

        self.coordinator.async_disconnect = fake_disconnect
        self.coordinator.async_reconnect = fake_connect
        asyncio.run(self.entities["disconnect"].async_press())
        asyncio.run(self.entities["reconnect"].async_press())
        self.assertEqual(calls, ["disconnect", "connect"])


if __name__ == "__main__":
    unittest.main()
