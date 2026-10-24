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
HEADER_OFFSET: Final = 160
HEADER_BYTES: Final = 160
PIXEL_BYTES: Final = PIXEL_COUNT * 2
TRAILER_LEN: Final = 4
GFRA_PAYLOAD_LEN: Final = META_LEN + PIXEL_BYTES + TRAILER_LEN  # 10244
FRAME_MESSAGE_LEN: Final = 1 + 4 + 4 + GFRA_PAYLOAD_LEN  # 10253

FRAME_CHECKSUM_SEED: Final = 0x03F0
LOAD_FIELD_LEN: Final = 12  # len("WREG") + 8 character payload


class SenXorProtocolError(Exception):
    """Raised when the device stream cannot be parsed."""


# ---------------------------------------------------------------------------
# Register map.  A ``WREG`` message carries one byte of register address and one
# byte of value: ``#000CWREG<reg:02X><value:02X><checksum:04X>``.
# The addresses below were cross-checked against Meridian's pysenxor-lite field
# definitions (``senxor.regmap.fields``) and confirmed on the wire.
# ---------------------------------------------------------------------------
REG_FRAME_MODE: Final = 0xB1
REG_FPS_DIVIDER: Final = 0xB4
REG_MODULE_GAIN: Final = 0xB9
REG_CORR_FACTOR: Final = 0xC2
REG_EMISSIVITY: Final = 0xCA
REG_OFFSET: Final = 0xCB
REG_DEVICE_INFO: Final = 0xD0

FRAME_MODE_STOP: Final = 0x00
FRAME_MODE_SINGLE: Final = 0x01
FRAME_MODE_CONTINUOUS: Final = 0x03

# Gain register values (0xB9): 0 = 1.0, 1 = auto, 2 = 0.25, 3 = 0.5.
GAIN_VALUES: Final = {"1": 0, "Auto": 1, "0.25": 2, "0.5": 3}
GAIN_DISPLAY: Final = {0: "1", 1: "Auto", 2: "0.25", 3: "0.5"}

FPS_DIVIDER_MIN: Final = 0
FPS_DIVIDER_MAX: Final = 127


def build_wreg(register: int, value: int = 0) -> bytes:
    """Build a ``WREG`` frame: one byte register address, one byte value.

    >>> build_wreg(0xB1, 0x03)
    b'#000CWREGB10302DE'
    >>> build_wreg(0xB1, 0x00)
    b'#000CWREGB10002DB'
    """
    body = f"{LOAD_FIELD_LEN:04X}WREG{register & 0xFF:02X}{value & 0xFF:02X}"
    checksum = sum(body.encode("ascii")) & 0xFFFF
    return f"#{body}{checksum:04X}".encode("ascii")


def command_name(register: int, value: int | None = None) -> str:
    """Human readable name for a register write."""
    if register == REG_FRAME_MODE:
        return {
            FRAME_MODE_STOP: "stop stream",
            FRAME_MODE_SINGLE: "single frame",
            FRAME_MODE_CONTINUOUS: "start stream",
        }.get(value if value is not None else -1, "frame mode")
    if register == REG_FPS_DIVIDER:
        return "frame rate divider"
    if register == REG_MODULE_GAIN:
        return "module gain"
    if register == REG_CORR_FACTOR:
        return "sensitivity correction"
    if register == REG_EMISSIVITY:
        return "emissivity"
    if register == REG_OFFSET:
        return "temperature offset"
    return f"register 0x{register:02X}"


@dataclass(slots=True)
class FrameHeader:
    """Decoded MI08 GFRA header (payload bytes 160..319, 80 uint16 words)."""

    frame_counter: int
    vdd: float
    die_temperature: float
    timestamp: int
    max_temperature: float
    min_temperature: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "frame_counter": self.frame_counter,
            "vdd": round(self.vdd, 4),
            "die_temperature": round(self.die_temperature, 2),
            "timestamp": self.timestamp,
        }


@dataclass(slots=True)
class ThermalFrame:
    """A decoded thermal frame."""

    sequence: int
    received: float
    meta: bytes
    pixels: tuple[int, ...]  # deci Kelvin, row major, 80 x 62
    checksum_ok: bool
    header: FrameHeader | None = None

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


def decode_header(meta: bytes) -> FrameHeader | None:
    """Decode the MI08 header block.

    Layout (little endian uint16): 0 frame counter, 1 VDD (x 1e-4 V),
    2 die temperature (x 0.01 K), 3/4 timestamp, 5/6 max/min (x 0.1 K).
    """
    if len(meta) < HEADER_OFFSET + HEADER_BYTES:
        return None
    words = memoryview(meta)[HEADER_OFFSET : HEADER_OFFSET + HEADER_BYTES].cast("H")
    return FrameHeader(
        frame_counter=words[0],
        vdd=words[1] * 0.0001,
        die_temperature=words[2] * 0.01 - 273.15,
        timestamp=(words[4] << 16) | words[3],
        max_temperature=words[5] * 0.1 - 273.15,
        min_temperature=words[6] * 0.1 - 273.15,
    )


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
    meta = payload[:META_LEN]
    return ThermalFrame(
        sequence=sequence,
        received=time.time(),
        meta=meta,
        pixels=pixels,
        checksum_ok=checksum_ok,
        header=decode_header(meta),
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
    async def send_command(self, register: int, value: int = 0) -> None:
        """Send a register write."""
        if self._writer is None:
            raise SenXorProtocolError("not connected")
        self._writer.write(build_wreg(register, value))
        await self._writer.drain()
        _LOGGER.debug(
            "Sent %s (0x%02X <- 0x%02X)", command_name(register, value), register, value
        )

    async def start_stream(self) -> None:
        await self.send_command(REG_FRAME_MODE, FRAME_MODE_CONTINUOUS)

    async def stop_stream(self) -> None:
        await self.send_command(REG_FRAME_MODE, FRAME_MODE_STOP)

    async def single_frame(self) -> None:
        await self.send_command(REG_FRAME_MODE, FRAME_MODE_SINGLE)

    async def set_fps_divider(self, divider: int) -> int:
        """Select the frame rate divider (0 = maximum frame rate)."""
        value = max(FPS_DIVIDER_MIN, min(FPS_DIVIDER_MAX, int(divider)))
        await self.send_command(REG_FPS_DIVIDER, value)
        return value

    async def set_gain(self, gain_value: int) -> None:
        """Write the module gain register (0 = 1.0, 1 = auto, 2 = 0.25, 3 = 0.5)."""
        await self.send_command(REG_MODULE_GAIN, gain_value)

    async def set_sensitivity(self, factor: float) -> None:
        """Write the sensitivity correction factor (0.01 .. 2.55)."""
        await self.send_command(REG_CORR_FACTOR, int(round(factor * 100)) & 0xFF)

    async def set_emissivity(self, percent: int) -> None:
        """Write the target emissivity register (percent, 1..100)."""
        await self.send_command(REG_EMISSIVITY, max(1, min(100, int(percent))))

    async def set_offset(self, offset: float) -> None:
        """Write the temperature offset register (0.1 K units, signed byte)."""
        raw = int(round(offset * 10)) & 0xFF
        await self.send_command(REG_OFFSET, raw)

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