#!/usr/bin/env python3
"""Command line probe for a SenXor thermal camera (TCP mode).

This tool is intentionally dependency free (only Pillow for the optional JPEG
output) and talks to the camera exactly like the Home Assistant integration
does, which makes it handy for validating a fresh installation.

    python tools/probe.py --host 192.168.11.153 --port 3333 --frames 5

It prints a summary of every message received, the temperature range of the
last frame and writes ``frame.jpg`` (false colour thermogram) plus
``frame.csv`` (calibrated pixel matrix).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Import the protocol/rendering modules without executing the integration's
# __init__.py (which needs a full Home Assistant installation).
import importlib  # noqa: E402
import types  # noqa: E402

_package = types.ModuleType("senxor_thermal")
_package.__path__ = [str(ROOT / "custom_components" / "senxor_thermal")]
sys.modules["senxor_thermal"] = _package

protocol = importlib.import_module("senxor_thermal.protocol")
rendering = importlib.import_module("senxor_thermal.rendering")
palette = importlib.import_module("senxor_thermal.palette")
PALETTE_NAMES = palette.PALETTE_NAMES


async def run(host: str, port: int, frames: int, palette: str) -> int:
    received = 0
    last = None
    ready = asyncio.Event()

    def on_frame(frame):  # noqa: ANN001 - callback signature from protocol
        nonlocal received, last
        received += 1
        last = frame
        if received >= frames:
            ready.set()

    connection = protocol.SenXorConnection(host, port, on_frame)
    print(f"connecting to {host}:{port} ...")
    await connection.connect()
    await connection.start_stream()
    print("stream started, waiting for frames")

    try:
        await asyncio.wait_for(ready.wait(), timeout=15)
    except TimeoutError:
        print("timeout while waiting for frames", file=sys.stderr)
        await connection.close()
        return 1

    await connection.stop_stream()
    await connection.close()

    assert last is not None
    options = rendering.RenderOptions(palette=palette)
    rendered = rendering.render_frame(last, options)
    out = pathlib.Path("frame.jpg")
    out.write_bytes(rendered.jpeg)
    with open("frame.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        for row in range(protocol.FRAME_HEIGHT):
            writer.writerow(
                round(rendered.values[row * protocol.FRAME_WIDTH + col], 2)
                for col in range(protocol.FRAME_WIDTH)
            )

    stats = rendered.stats
    print(f"frames received : {received}")
    print(f"frame size      : {protocol.FRAME_WIDTH}x{protocol.FRAME_HEIGHT}")
    print(f"checksum ok     : {last.checksum_ok}")
    print(f"raw range       : {last.min_dk} .. {last.max_dk} dK")
    print(f"temperature     : min {stats.minimum:.2f} C  max {stats.maximum:.2f} C")
    print(f"average/centre  : {stats.mean:.2f} C / {stats.center:.2f} C")
    print(f"hot spot at     : {stats.max_position}")
    print(f"saved           : {out.resolve()}, frame.csv")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.11.153")
    parser.add_argument("--port", type=int, default=3333)
    parser.add_argument("--frames", type=int, default=5)
    parser.add_argument("--palette", default="HEATED_IRON", choices=PALETTE_NAMES)
    args = parser.parse_args()
    return asyncio.run(run(args.host, args.port, args.frames, args.palette))


if __name__ == "__main__":
    raise SystemExit(main())
