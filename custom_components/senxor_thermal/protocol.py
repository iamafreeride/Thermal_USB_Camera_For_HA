"""Low-level protocol for the Meridian Innovation SenXor thermal camera (TCP mode).

The camera (or the network bridge in front of it) exposes a raw TCP server,
default port 3333.  Every message, in both directions, is an ASCII framed
packet::

    '#' <4 hex digits: payload length> <4 chars: command> <payload ...>

The length field counts the command word plus the payload, so the total size of
a message is ``1 + 4 + length``.

Two message types are used by the viewer software for TCP mode:

``WREG``
    Write command register.  Payload is the 4 hex digit register address
    followed by a 4 hex digit checksum (the sum of every character between the
    leading ``#`` and the checksum itself, modulo 65536).

``GFRA``
    Get FRame A - one thermal frame.  Payload is 10244 bytes:

    * ``0 .. 319``    320 byte metadata block (timestamps, sensor counters)
    * ``320 .. 10239`` 4960 little endian ``uint16`` pixels, row major,
      80 x 62, in deci Kelvin (1/10 K)
    * ``10240 .. 10243`` 4 ASCII hex digit checksum

    The frame checksum is the sum of the message characters with the same
    rule, for which the device uses an initial accumulator value of ``0x01FE``;
    that constant was determined empirically over several thousand frames and
    is verified but never enforced by this client.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Final

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Frame geometry
# ---------------------------------------------------------------------------
FRAME_WIDTH: Final = 80
FRAME_HEIGHT: Final = 62
PIXEL_COUNT: Final = FRAME_WIDTH * FRAME_HEIGHT
META_LEN: Final = 320
PIXEL_BYTES: Final = PIXEL_COUNT * 2
TRAILER_LEN: Final = 4
GFRA_PAYLOAD_LEN: Final = META_LEN + PIXEL_BYTES + TRAILER_LEN  # 10244
FRAME_MESSAGE_LEN: Final = 1 + 4 + 4 + GFRA_PAYLOAD_LEN  # 10253

FRAME_CHECKSUM_SEED: Final = 0x03F0
LOAD_FIELD_LEN: Final = 12  # len("WREG") + 8 character payload


class SenXorProtocolError(Exception):
    """Raised when the device stream cannot be parsed."""


# ---------------------------------------------------------------------------
# Command registers.  Writing to a command register triggers an action.
# These values were recovered from the viewer binary and confirmed on the wire.
# ---------------------------------------------------------------------------
REG_STREAM_START: Final = 0xB103
REG_STREAM_STOP: Final = 0xB100
REG_SINGLE_FRAME: Final = 0xB101

# Frame rate is selected with an *absolute level* register, not with relative
# "faster/slower" commands: 0xB400 + level.  Level 1 is the fastest stream.
# Captured from the viewer: decrease -> B402, increase -> B401 (level 1..2),
# and B403 / B404 (level 3 / 4) in a later session; measured ~6.5 fps for
# level 3 and ~4.3 fps for level 4, ~15.8 fps at level 1.
REG_FPS_BASE: Final = 0xB400
FPS_LEVEL_MIN: Final = 1
FPS_LEVEL_MAX: Final = 4
FPS_LEVELS: Final = tuple(range(FPS_LEVEL_MIN, FPS_LEVEL_MAX + 1))

# Kept for backwards compatibility with older entity descriptions.
REG_FPS_UP: Final = REG_FPS_BASE + 1
REG_FPS_DOWN: Final = REG_FPS_BASE + 2

_COMMAND_NAMES: Final = {
    REG_STREAM_START: "stream start",
    REG_STREAM_STOP: "stream stop",
    REG_SINGLE_FRAME: "single frame",
    0xB401: "frame rate level 1 (fastest)",
    0xB402: "frame rate level 2",
    0xB403: "frame rate level 3",
    0xB404: "frame rate level 4 (slowest)",
}


def fps_register(level: int) -> int:
    """Return the command register for a frame rate ``level`` (1 = fastest)."""
    return REG_FPS_BASE + max(FPS_LEVEL_MIN, min(FPS_LEVEL_MAX, level))


def step_fps_level(level: int, delta: int) -> int:
    """Move ``level`` by ``delta`` frames of speed, clamped to the valid range."""
    return max(FPS_LEVEL_MIN, min(FPS_LEVEL_MAX, level + delta))



def build_wreg(register: int) -> bytes:
    """Build a ``WREG`` command frame for ``register``.

    >>> build_wreg(0xB103)
    b'#000CWREGB10302DE'
    """
    prefix = f"{LOAD_FIELD_LEN:04X}WREG{register:04X}"
    checksum = sum(prefix.encode("ascii")) & 0xFFFF
    return f"#{prefix}{checksum:04X}".encode("ascii")


def command_name(register: int) -> str:
    """Human readable name for a command register."""
    return _COMMAND_NAMES.get(register, f"register 0x{register:04X}")


@dataclass(slots=True)
class ThermalFrame:
    """A decoded thermal frame."""

    sequence: int
    received: float
    meta: bytes
    pixels: tuple[int, ...]  # deci Kelvin, row major, 80 x 62
    checksum_ok: bool

    @property
    def min_dk(self) -> int:
        return min(self.pixels)

    @property
    def max_dk(self) -> int:
        return max(self.pixels)

    def pixel(self, x: int, y: int) -> int:
        return self.pixels[y * FRAME_WIDTH + x]


@dataclass(slots=True)
class CommandAck:
    """Acknowledged ``WREG`` command from the device."""

    payload: bytes
    received: float = field(default_factory=time.time)


def parse_messages(buffer: bytes) -> tuple[list[tuple[str, bytes]], bytes]:
    """Split ``buffer`` into complete messages and return (messages, rest)."""
    messages: list[tuple[str, bytes]] = []
    pos = 0
    end = len(buffer)
    while True:
        start = buffer.find(b"#", pos)
        if start < 0:
            # Nothing that looks like a header; drop everything.
            return messages, b""
        if start + 9 > end:
            return messages, buffer[start:]
        try:
            length = int(buffer[start + 1 : start + 5], 16)
        except ValueError:
            pos = start + 1
            continue
        total = 1 + 4 + length
        if start + total > end:
            return messages, buffer[start:]
        command = buffer[start + 5 : start + 9].decode("ascii", "replace")
        messages.append((command, buffer[start + 9 : start + total]))
        pos = start + total


def decode_frame(payload: bytes, sequence: int) -> ThermalFrame:
    """Decode a ``GFRA`` payload into a :class:`ThermalFrame`."""
    if len(payload) != GFRA_PAYLOAD_LEN:
        raise SenXorProtocolError(
            f"unexpected GFRA payload length {len(payload)}, expected {GFRA_PAYLOAD_LEN}"
        )
    raw = payload[META_LEN : META_LEN + PIXEL_BYTES]
    pixels = tuple(int.from_bytes(raw[i : i + 2], "little") for i in range(0, PIXEL_BYTES, 2))
    try:
        expected = int(payload[-TRAILER_LEN:], 16)
    except ValueError:
        expected = -1
    checksum_ok = expected == (sum(payload[:-TRAILER_LEN]) + FRAME_CHECKSUM_SEED) & 0xFFFF
    return ThermalFrame(
        sequence=sequence,
        received=time.time(),
        meta=payload[:META_LEN],
        pixels=pixels,
        checksum_ok=checksum_ok,
    )


class SenXorConnection:
    """Asynchronous connection to a SenXor camera over TCP."""

    def __init__(
        self,
        host: str,
        port: int,
        on_frame: Callable[[ThermalFrame], None],
        on_ack: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._on_frame = on_frame
        self._on_ack = on_ack
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._sequence = 0
        self._buffer = b""
        self.connected = False
        self.last_error: str | None = None
        self.bytes_received = 0
        self.last_rx = 0.0

    # -- lifecycle ---------------------------------------------------------
    async def connect(self, timeout: float = 5.0) -> None:
        """Open the TCP connection and start the reader task."""
        await self.close()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout
        )
        writer.transport.set_write_buffer_limits(high=1024 * 1024)
        self._reader = reader
        self._writer = writer
        self._buffer = b""
        self.connected = True
        self.last_error = None
        self.bytes_received = 0
        self.last_rx = 0.0
        self._task = asyncio.create_task(self._read_loop(), name="senxor-reader")
        _LOGGER.debug("Connected to SenXor camera at %s:%s", self.host, self.port)

    async def close(self) -> None:
        """Stop the reader task and close the socket."""
        self.connected = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: B014 - cancel races
                pass
            self._task = None
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001 - socket may already be gone
                pass

    # -- commands ----------------------------------------------------------
    async def send_command(self, register: int) -> None:
        """Send a command register write."""
        if self._writer is None:
            raise SenXorProtocolError("not connected")
        self._writer.write(build_wreg(register))
        await self._writer.drain()
        _LOGGER.debug("Sent %s (0x%04X)", command_name(register), register)

    async def start_stream(self) -> None:
        await self.send_command(REG_STREAM_START)

    async def stop_stream(self) -> None:
        await self.send_command(REG_STREAM_STOP)

    async def single_frame(self) -> None:
        await self.send_command(REG_SINGLE_FRAME)

    async def set_fps_level(self, level: int) -> int:
        """Select an absolute frame rate level (1 fastest .. 4 slowest)."""
        selected = max(FPS_LEVEL_MIN, min(FPS_LEVEL_MAX, level))
        await self.send_command(fps_register(selected))
        return selected

    async def frame_rate_up(self) -> None:
        await self.send_command(REG_FPS_UP)

    async def frame_rate_down(self) -> None:
        await self.send_command(REG_FPS_DOWN)

    # -- reader ------------------------------------------------------------
    async def _read_loop(self) -> None:
        assert self._reader is not None
        reader = self._reader
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    self.connected = False
                    self.last_error = "connection closed by device"
                    _LOGGER.warning("SenXor camera closed the connection")
                    return
                self.bytes_received += len(chunk)
                self.last_rx = time.time()
                self._buffer += chunk
                messages, self._buffer = parse_messages(self._buffer)
                for command, payload in messages:
                    if command == "GFRA":
                        try:
                            frame = decode_frame(payload, self._sequence)
                        except SenXorProtocolError as err:
                            _LOGGER.debug("Dropping frame: %s", err)
                            continue
                        self._sequence += 1
                        if not frame.checksum_ok:
                            _LOGGER.debug(
                                "Frame %s checksum mismatch (trailer %r)",
                                frame.sequence,
                                payload[-4:],
                            )
                        self._on_frame(frame)
                    elif command == "WREG":
                        if self._on_ack is not None:
                            self._on_ack(payload.decode("ascii", "replace"))
                    else:  # pragma: no cover - unknown message types are ignored
                        _LOGGER.debug("Ignoring message %s (%s bytes)", command, len(payload))
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            self.connected = False
            self.last_error = repr(err)
            _LOGGER.debug("SenXor reader stopped: %r", err)


async def async_probe(host: str, port: int, timeout: float = 10.0) -> ThermalFrame:
    """Connect to ``host:port``, request streaming and return the first frame.

    The stream is stopped again before the socket is closed so the camera is
    released cleanly for the next client.  Raises
    :class:`SenXorProtocolError` when no valid frame arrives in time.  Used by
    the config flow to validate user input.
    """
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    try:
        writer.write(build_wreg(REG_STREAM_START))
        await writer.drain()
        buffer = b""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            chunk = await asyncio.wait_for(reader.read(65536), timeout)
            if not chunk:
                raise SenXorProtocolError("connection closed by device")
            buffer += chunk
            messages, buffer = parse_messages(buffer)
            for command, payload in messages:
                if command == "GFRA":
                    return decode_frame(payload, 0)
        raise SenXorProtocolError("no thermal frame received")
    finally:
        try:
            writer.write(build_wreg(REG_STREAM_STOP))
            await writer.drain()
            await asyncio.sleep(0.1)
        except Exception:  # noqa: BLE001 - device may already be gone
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001 - best effort close
            pass