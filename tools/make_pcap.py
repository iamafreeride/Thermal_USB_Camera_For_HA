#!/usr/bin/env python3
"""Build a PCAP file from a recorded SenXor TCP session.

Live packet capture of the camera traffic requires Windows' Npcap driver in
"admin only" capture mode (or root on Linux).  When that is not available the
protocol can still be observed with a local TCP relay; this tool turns such a
relay log (raw payload bytes per direction) into a real Ethernet/IPv4/TCP PCAP
that Wireshark happily dissects, so the protocol can be inspected interactively.

Usage::

    python tools/make_pcap.py --client recon/c2d_1.bin --server recon/d2c_1.bin \
        --out docs/captures/senxor_session.pcapng

Both files contain the reassembled payload bytes in transmission order.
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

CLIENT_IP = "127.0.0.1"
SERVER_IP = "127.0.0.1"
CLIENT_PORT = 51000
SERVER_PORT = 3333
CLIENT_MAC = bytes.fromhex("020000000001")
SERVER_MAC = bytes.fromhex("020000000002")
MSS = 1448
FRAME_INTERVAL = 0.0645  # ~15.5 fps


def _split_messages(data: bytes) -> list[bytes]:
    """Split a SenXor byte stream into complete messages."""
    messages = []
    pos = 0
    while True:
        start = data.find(b"#", pos)
        if start < 0 or start + 9 > len(data):
            break
        try:
            length = int(data[start + 1 : start + 5], 16)
        except ValueError:
            pos = start + 1
            continue
        total = 1 + 4 + length
        if start + total > len(data):
            break
        messages.append(data[start : start + total])
        pos = start + total
    return messages


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for index in range(0, len(data), 2):
        total += (data[index] << 8) + data[index + 1]
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _ethernet(payload: bytes, source: bytes, destination: bytes) -> bytes:
    return destination + source + b"\x08\x00" + payload


def _ipv4(payload: bytes, source: str, destination: str, ident: int) -> bytes:
    total_length = 20 + len(payload)
    header = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        total_length,
        ident & 0xFFFF,
        0x4000,
        64,
        6,
        0,
        bytes(map(int, source.split("."))),
        bytes(map(int, destination.split("."))),
    )
    header = header[:10] + struct.pack("!H", _checksum(header)) + header[12:]
    return header + payload


def _tcp(
    payload: bytes,
    sport: int,
    dport: int,
    seq: int,
    ack: int,
    flags: int,
    window: int = 64240,
) -> bytes:
    offset_flags = (5 << 12) | flags
    header = struct.pack(
        "!HHIIHHHH", sport, dport, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF, offset_flags, window, 0, 0
    )
    pseudo = struct.pack(
        "!4s4sBBH",
        bytes(map(int, CLIENT_IP.split("."))),
        bytes(map(int, SERVER_IP.split("."))),
        0,
        6,
        len(header) + len(payload),
    )
    checksum = _checksum(pseudo + header + payload)
    header = header[:16] + struct.pack("!H", checksum) + header[18:]
    return header + payload


class PcapWriter:
    """Minimal classic PCAP writer."""

    def __init__(self, path: Path) -> None:
        self.handle = open(path, "wb")
        self.handle.write(
            struct.pack("!IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
        )
        self.now = 0.0

    def write(self, frame: bytes) -> None:
        seconds = int(self.now)
        microseconds = int((self.now - seconds) * 1_000_000)
        self.handle.write(
            struct.pack("!IIII", seconds, microseconds, len(frame), len(frame))
        )
        self.handle.write(frame)

    def close(self) -> None:
        self.handle.close()


class Session:
    """Tracks TCP sequence numbers for both directions."""

    def __init__(self, writer: PcapWriter) -> None:
        self.writer = writer
        self.client_seq = 1000
        self.server_seq = 9000
        self.ident = 1

    def _emit(self, source: str, payload: bytes, seq: int, ack: int, flags: int) -> None:
        if source == "client":
            tcp = _tcp(payload, CLIENT_PORT, SERVER_PORT, seq, ack, flags)
            ip = _ipv4(tcp, CLIENT_IP, SERVER_IP, self.ident)
            frame = _ethernet(ip, CLIENT_MAC, SERVER_MAC)
        else:
            tcp = _tcp(payload, SERVER_PORT, CLIENT_PORT, seq, ack, flags)
            ip = _ipv4(tcp, SERVER_IP, CLIENT_IP, self.ident)
            frame = _ethernet(ip, SERVER_MAC, CLIENT_MAC)
        self.ident += 1
        self.writer.write(frame)

    def handshake(self) -> None:
        self._emit("client", b"", self.client_seq, 0, 0x002)
        self.client_seq += 1
        self._emit("server", b"", self.server_seq, self.client_seq, 0x012)
        self.server_seq += 1
        self._emit("client", b"", self.client_seq, self.server_seq, 0x010)

    def send(self, source: str, payload: bytes, advance_time: float = 0.0) -> None:
        self.writer.now += advance_time
        for offset in range(0, len(payload), MSS):
            chunk = payload[offset : offset + MSS]
            if source == "client":
                self._emit("client", chunk, self.client_seq, self.server_seq, 0x018)
                self.client_seq += len(chunk)
            else:
                self._emit("server", chunk, self.server_seq, self.client_seq, 0x018)
                self.server_seq += len(chunk)
            self.writer.now += 0.0002

    def close(self) -> None:
        self._emit("client", b"", self.client_seq, self.server_seq, 0x011)
        self.client_seq += 1
        self._emit("server", b"", self.server_seq, self.client_seq, 0x011)
        self.server_seq += 1
        self._emit("client", b"", self.client_seq, self.server_seq, 0x010)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client", required=True, help="client -> device payload dump")
    parser.add_argument("--server", required=True, help="device -> client payload dump")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    client_bytes = Path(args.client).read_bytes()
    server_bytes = Path(args.server).read_bytes()
    commands = _split_messages(client_bytes)
    messages = _split_messages(server_bytes)
    frames = [m for m in messages if m[5:9] == b"GFRA"]
    replies = [m for m in messages if m[5:9] != b"GFRA"]
    if not commands or not frames:
        print("nothing to convert", file=sys.stderr)
        return 1

    writer = PcapWriter(Path(args.out))
    writer.now = time.time()
    session = Session(writer)
    session.handshake()

    per_command = max(1, len(frames) // len(commands))
    frame_index = 0
    reply_index = 0
    for index, command in enumerate(commands):
        session.send("client", command, advance_time=0.35)
        # command acknowledgement, when one was recorded
        for _ in range(2):
            if reply_index < len(replies):
                session.send("server", replies[reply_index], advance_time=0.001)
                reply_index += 1
                break
        stop = len(frames) if index == len(commands) - 1 else frame_index + per_command
        while frame_index < stop:
            session.send("server", frames[frame_index], advance_time=FRAME_INTERVAL)
            frame_index += 1

    session.close()
    writer.close()
    print(
        f"wrote {args.out}: {len(commands)} commands, {len(frames)} frames, "
        f"{frame_index} frames emitted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
