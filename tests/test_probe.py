"""Config-flow probe test against an in-process fake camera."""

from __future__ import annotations

import asyncio
import unittest

import ha_stub

ha_stub.install()

from common import load, sample_frames  # noqa: E402

protocol = load("protocol")


class FakeCameraServer:
    """Minimal TCP server that answers like a SenXor bridge."""

    def __init__(self) -> None:
        self.received = b""
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.read(64), timeout=5)
            self.received += request
            writer.write(b"#0008WREG01FD")
            writer.write(sample_frames()[: protocol.FRAME_MESSAGE_LEN])
            await writer.drain()
            # Wait for the stop command that async_probe sends on the way out.
            try:
                self.received += await asyncio.wait_for(reader.read(64), timeout=5)
            except TimeoutError:
                pass
        finally:
            writer.close()

    async def stop(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()


class ProbeTest(unittest.TestCase):
    def test_probe_reads_a_frame_and_stops_the_stream(self) -> None:
        async def run() -> None:
            server = FakeCameraServer()
            await server.start()
            try:
                frame = await protocol.async_probe("127.0.0.1", server.port, timeout=5)
            finally:
                await server.stop()
            self.assertEqual(len(frame.pixels), protocol.PIXEL_COUNT)
            self.assertTrue(frame.checksum_ok)
            self.assertIsNotNone(frame.header)
            # start command, then the stop command on the way out
            self.assertEqual(
                server.received[:17], protocol.build_wreg(protocol.REG_FRAME_MODE, protocol.FRAME_MODE_CONTINUOUS)
            )
            self.assertIn(
                protocol.build_wreg(protocol.REG_FRAME_MODE, protocol.FRAME_MODE_STOP),
                server.received,
            )

        asyncio.run(run())

    def test_probe_times_out_without_frames(self) -> None:
        async def run() -> None:
            server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                with self.assertRaises((protocol.SenXorProtocolError, TimeoutError)):
                    await protocol.async_probe("127.0.0.1", port, timeout=1)
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
