"""Disconnect / reconnect must survive the coordinator's polling loop."""

from __future__ import annotations

import asyncio
import unittest

import ha_stub

ha_stub.install()

from common import load, sample_frames  # noqa: E402

protocol = load("protocol")
coordinator_module = load("coordinator")


def make_frame():
    messages, _ = protocol.parse_messages(sample_frames())
    return protocol.decode_frame(messages[0][1], 0)


class DisconnectReconnectTest(unittest.TestCase):
    def setUp(self) -> None:
        import sys

        hass = sys.modules["homeassistant.core"].HomeAssistant()
        entry_cls = sys.modules["homeassistant.config_entries"].ConfigEntry
        self.entry = entry_cls(
            data={"host": "192.0.2.10", "port": 3333}, title="Thermal Camera"
        )
        self.coordinator = coordinator_module.SenXorCoordinator(
            hass, self.entry, "192.0.2.10", 3333, 1.0
        )
        self.connect_calls = 0

        async def fake_connect(wait_for_frame: float = 8.0, attempts: int = 2) -> None:
            self.connect_calls += 1
            self.coordinator._handle_frame(make_frame())
            self.coordinator._connection.connected = True

        async def fake_close() -> None:
            self.coordinator._connection.connected = False

        self.coordinator.async_connect = fake_connect
        self.coordinator._connection.close = fake_close
        self.coordinator._handle_frame(make_frame())
        self.coordinator._connection.connected = True
        self.coordinator.async_set_updated_data(self.coordinator._build_data())

    def test_disconnect_closes_and_stays_offline(self) -> None:
        asyncio.run(self.coordinator.async_disconnect())

        self.assertFalse(self.coordinator.settings.streaming)
        self.assertFalse(self.coordinator.connected)
        self.assertIsNone(self.coordinator.data.frame)

        # the polling loop must not reconnect on its own
        data = asyncio.run(self.coordinator._async_update_data())
        self.assertFalse(data.connected)
        self.assertEqual(self.connect_calls, 0)

    def test_reconnect_restores_the_stream(self) -> None:
        asyncio.run(self.coordinator.async_disconnect())
        asyncio.run(self.coordinator.async_reconnect())

        self.assertTrue(self.coordinator.settings.streaming)
        self.assertTrue(self.coordinator.connected)
        self.assertEqual(self.connect_calls, 1)
        self.assertIsNotNone(self.coordinator.data.frame)
        self.assertTrue(self.coordinator.data.available)

    def test_streaming_switch_off_then_on(self) -> None:
        asyncio.run(self.coordinator.async_set_streaming(False))
        self.assertFalse(self.coordinator.settings.streaming)

        asyncio.run(self.coordinator.async_set_streaming(True))
        self.assertTrue(self.coordinator.settings.streaming)
        self.assertTrue(self.coordinator.connected)


if __name__ == "__main__":
    unittest.main()
