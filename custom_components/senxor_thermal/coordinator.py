"""Runtime state, connection management and rendering cache for SenXor cameras."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_AUTO_RANGE,
    CONF_EMISSIVITY,
    CONF_FILTER,
    CONF_FPS_LEVEL,
    CONF_GAIN,
    CONF_JPEG_QUALITY,
    CONF_OFFSET,
    CONF_PALETTE,
    CONF_PROBE_1_X,
    CONF_PROBE_1_Y,
    CONF_PROBE_2_X,
    CONF_PROBE_2_Y,
    CONF_REMOVE_EXTREME,
    CONF_SCALE_MAX,
    CONF_SCALE_MIN,
    CONF_SHOW_COLORBAR,
    CONF_SHOW_MARKERS,
    CONF_UNIT,
    DEFAULT_EMISSIVITY,
    DEFAULT_FILTER,
    DEFAULT_FPS_LEVEL,
    DEFAULT_GAIN,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_OFFSET,
    DEFAULT_PROBE_1,
    DEFAULT_PROBE_2,
    DEFAULT_SCALE_MAX,
    DEFAULT_SCALE_MIN,
    DEFAULT_UNIT,
    DOMAIN,
)
from .palette import DEFAULT_PALETTE
from .protocol import (
    FPS_LEVEL_MAX,
    FPS_LEVEL_MIN,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    SenXorConnection,
    SenXorProtocolError,
    ThermalFrame,
    step_fps_level,
)
from .rendering import (
    FrameStats,
    RenderOptions,
    RenderedFrame,
    apply_filter,
    calibrate,
    compute_stats,
    render_values,
)

_LOGGER = logging.getLogger(__name__)

RECONNECT_COOLDOWN = 15.0

RENDER_WIDTH = FRAME_WIDTH * 8
RENDER_HEIGHT = FRAME_HEIGHT * 8


@dataclass(slots=True)
class SenXorSettings:
    """User adjustable settings, persisted in the config entry options."""

    palette: str = DEFAULT_PALETTE
    unit: str = DEFAULT_UNIT
    emissivity: float = DEFAULT_EMISSIVITY
    offset: float = DEFAULT_OFFSET
    filtering: str = DEFAULT_FILTER
    gain: str = DEFAULT_GAIN
    auto_range: bool = True
    remove_extreme: bool = False
    scale_min: float = DEFAULT_SCALE_MIN
    scale_max: float = DEFAULT_SCALE_MAX
    show_markers: bool = True
    show_colorbar: bool = True
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    fps_level: int = DEFAULT_FPS_LEVEL
    probe_1_x: int = DEFAULT_PROBE_1[0]
    probe_1_y: int = DEFAULT_PROBE_1[1]
    probe_2_x: int = DEFAULT_PROBE_2[0]
    probe_2_y: int = DEFAULT_PROBE_2[1]

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "SenXorSettings":
        return cls(
            palette=options.get(CONF_PALETTE, DEFAULT_PALETTE),
            unit=options.get(CONF_UNIT, DEFAULT_UNIT),
            emissivity=float(options.get(CONF_EMISSIVITY, DEFAULT_EMISSIVITY)),
            offset=float(options.get(CONF_OFFSET, DEFAULT_OFFSET)),
            filtering=options.get(CONF_FILTER, DEFAULT_FILTER),
            gain=str(options.get(CONF_GAIN, DEFAULT_GAIN)),
            auto_range=bool(options.get(CONF_AUTO_RANGE, True)),
            remove_extreme=bool(options.get(CONF_REMOVE_EXTREME, False)),
            scale_min=float(options.get(CONF_SCALE_MIN, DEFAULT_SCALE_MIN)),
            scale_max=float(options.get(CONF_SCALE_MAX, DEFAULT_SCALE_MAX)),
            show_markers=bool(options.get(CONF_SHOW_MARKERS, True)),
            show_colorbar=bool(options.get(CONF_SHOW_COLORBAR, True)),
            jpeg_quality=int(options.get(CONF_JPEG_QUALITY, DEFAULT_JPEG_QUALITY)),
            fps_level=int(options.get(CONF_FPS_LEVEL, DEFAULT_FPS_LEVEL)),
            probe_1_x=int(options.get(CONF_PROBE_1_X, DEFAULT_PROBE_1[0])),
            probe_1_y=int(options.get(CONF_PROBE_1_Y, DEFAULT_PROBE_1[1])),
            probe_2_x=int(options.get(CONF_PROBE_2_X, DEFAULT_PROBE_2[0])),
            probe_2_y=int(options.get(CONF_PROBE_2_Y, DEFAULT_PROBE_2[1])),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            CONF_PALETTE: self.palette,
            CONF_UNIT: self.unit,
            CONF_EMISSIVITY: self.emissivity,
            CONF_OFFSET: self.offset,
            CONF_FILTER: self.filtering,
            CONF_GAIN: self.gain,
            CONF_AUTO_RANGE: self.auto_range,
            CONF_REMOVE_EXTREME: self.remove_extreme,
            CONF_SCALE_MIN: self.scale_min,
            CONF_SCALE_MAX: self.scale_max,
            CONF_SHOW_MARKERS: self.show_markers,
            CONF_SHOW_COLORBAR: self.show_colorbar,
            CONF_JPEG_QUALITY: self.jpeg_quality,
            CONF_FPS_LEVEL: self.fps_level,
            CONF_PROBE_1_X: self.probe_1_x,
            CONF_PROBE_1_Y: self.probe_1_y,
            CONF_PROBE_2_X: self.probe_2_x,
            CONF_PROBE_2_Y: self.probe_2_y,
        }

    @property
    def probes(self) -> tuple[tuple[int, int], tuple[int, int]]:
        """The two user positioned probe coordinates (clamped to the frame)."""
        return (
            (max(0, min(FRAME_WIDTH - 1, self.probe_1_x)), max(0, min(FRAME_HEIGHT - 1, self.probe_1_y))),
            (max(0, min(FRAME_WIDTH - 1, self.probe_2_x)), max(0, min(FRAME_HEIGHT - 1, self.probe_2_y))),
        )

    def render_options(self) -> RenderOptions:
        return RenderOptions(
            palette=self.palette,
            unit=self.unit,
            auto_range=self.auto_range,
            scale_min=self.scale_min,
            scale_max=self.scale_max,
            remove_extreme=self.remove_extreme,
            filtering=self.filtering,
            emissivity=self.emissivity,
            offset=self.offset,
            show_markers=self.show_markers,
            show_colorbar=self.show_colorbar,
            probes=(
                (self.probe_1_x, self.probe_1_y),
                (self.probe_2_x, self.probe_2_y),
            ),
            width=RENDER_WIDTH,
            height=RENDER_HEIGHT,
            jpeg_quality=self.jpeg_quality,
        )


@dataclass(slots=True)
class SenXorData:
    """Snapshot handed to every entity on each coordinator update."""

    frame: ThermalFrame | None = None
    stats: FrameStats | None = None
    values: list[float] = field(default_factory=list, repr=False)
    frame_rate: float = 0.0
    connected: bool = False
    last_error: str | None = None
    probe_1: float | None = None
    probe_2: float | None = None

    @property
    def available(self) -> bool:
        return self.frame is not None and self.connected


class SenXorCoordinator(DataUpdateCoordinator[SenXorData]):
    """Owns the TCP connection and turns frames into entity friendly data."""
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        host: str,
        port: int,
        scan_interval: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {host}:{port}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.entry = entry
        self.host = host
        self.port = port
        self.settings = SenXorSettings.from_options(dict(entry.options))
        self._connection = SenXorConnection(host, port, self._handle_frame)
        self._frame: ThermalFrame | None = None
        self._frame_times: deque[float] = deque(maxlen=32)
        self._connect_lock = asyncio.Lock()
        self._render_cache: tuple[int, int, RenderedFrame] | None = None
        self._first_frame = asyncio.Event()
        self._next_connect_attempt = 0.0
        self._last_problem: str | None = None
        self.streaming = True
        self.frames_rendered = 0

    # -- connection --------------------------------------------------------
    async def async_connect(self, wait_for_frame: float = 8.0, attempts: int = 2) -> None:
        """(Re)connect, start streaming and wait for the first thermal frame.

        The camera serves a single TCP client and keeps streaming to a peer
        that disappeared, so a "connected but silent" socket is treated as a
        failure and the connection is rebuilt (stop, single frame, start).
        Raises :class:`SenXorProtocolError` when no frame can be obtained.
        """
        async with self._connect_lock:
            problem = "camera did not stream"
            for attempt in range(attempts):
                self._first_frame.clear()
                try:
                    await self._connection.connect()
                except Exception as err:  # noqa: BLE001 - network errors are expected
                    problem = f"cannot connect to {self.host}:{self.port}: {err}"
                    _LOGGER.debug("Connection attempt %s failed: %s", attempt + 1, problem)
                    await asyncio.sleep(0.5)
                    continue

                await self._connection.start_stream()
                self.streaming = True

                timeout = wait_for_frame if attempt == 0 else max(4.0, wait_for_frame / 2)
                if await self._wait_for_first_frame(timeout):
                    await self._apply_fps_level()
                    return

                if self._connection.bytes_received == 0:
                    problem = (
                        f"connected to {self.host}:{self.port} but the camera sent no data - "
                        "another client (e.g. the Windows SenXor viewer) may still hold the stream"
                    )
                else:
                    problem = "the camera sent data but no thermal frame"
                _LOGGER.debug("No frame after %.1f s, nudging the camera", timeout)

                # Nudge the firmware: a fresh stop/single/start cycle usually
                # restarts the stream when the previous one was orphaned.
                try:
                    await self._connection.stop_stream()
                    await asyncio.sleep(0.4)
                    await self._connection.single_frame()
                    await self._connection.start_stream()
                except Exception as err:  # noqa: BLE001 - best effort
                    _LOGGER.debug("Could not nudge the camera: %r", err)

                if await self._wait_for_first_frame(4.0):
                    await self._apply_fps_level()
                    return

                await self._connection.close()
                await asyncio.sleep(0.5)

            raise SenXorProtocolError(problem)

    async def _apply_fps_level(self) -> None:
        """Re-apply the stored frame rate level after (re)connecting."""
        try:
            await self._connection.set_fps_level(self.settings.fps_level)
        except Exception as err:  # noqa: BLE001 - not fatal
            _LOGGER.debug("Could not restore frame rate level: %r", err)

    async def _wait_for_first_frame(self, timeout: float) -> bool:
        """Wait up to ``timeout`` seconds for the reader to deliver a frame."""
        try:
            await asyncio.wait_for(self._first_frame.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def async_shutdown(self) -> None:
        """Close the connection."""
        await self._connection.close()

    def _handle_frame(self, frame: ThermalFrame) -> None:
        self._frame = frame
        self._frame_times.append(frame.received)
        self._first_frame.set()

    # -- commands ----------------------------------------------------------
    async def async_start_stream(self) -> None:
        await self._connection.start_stream()
        self.streaming = True
        await self.async_request_refresh()

    async def async_stop_stream(self) -> None:
        await self._connection.stop_stream()
        self.streaming = False
        await self.async_request_refresh()

    async def async_single_frame(self) -> None:
        await self._connection.single_frame()
        await self.async_request_refresh()

    async def async_set_fps_level(self, level: int) -> None:
        """Select the absolute frame rate level (1 fastest .. 4 slowest)."""
        selected = max(FPS_LEVEL_MIN, min(FPS_LEVEL_MAX, int(level)))
        if self._connection.connected:
            try:
                await self._connection.set_fps_level(selected)
                self._last_problem = None
            except Exception as err:  # noqa: BLE001 - keep the UI responsive
                _LOGGER.warning("Could not set frame rate level %s: %r", selected, err)
        await self.async_update_settings(fps_level=selected)

    async def async_frame_rate_up(self) -> None:
        """One step faster (towards level 1)."""
        await self.async_set_fps_level(step_fps_level(self.settings.fps_level, -1))

    async def async_frame_rate_down(self) -> None:
        """One step slower (towards level 4)."""
        await self.async_set_fps_level(step_fps_level(self.settings.fps_level, 1))

    # -- settings ----------------------------------------------------------
    async def async_update_settings(self, **changes: Any) -> None:
        """Apply and persist new settings without reloading the integration."""
        for key, value in changes.items():
            setattr(self.settings, key, value)
        self._render_cache = None
        self.hass.config_entries.async_update_entry(
            self.entry,
            options={**self.entry.options, **self.settings.as_dict()},
        )
        self.async_set_updated_data(self._build_data())

    # -- coordinator -------------------------------------------------------
    async def _async_update_data(self) -> SenXorData:
        interval = self.update_interval or timedelta(seconds=10)
        max_age = max(10.0, interval.total_seconds() * 3)
        frame = self._frame
        stale = frame is None or (time.time() - frame.received) > max_age

        if stale or not self._connection.connected:
            now = time.time()
            if now < self._next_connect_attempt:
                raise UpdateFailed(self._last_problem or "camera unavailable")

            if self._connection.connected:
                _LOGGER.debug("Thermal frames are stale, reconnecting")
            try:
                await self.async_connect()
            except Exception as err:  # noqa: BLE001 - surfaced as ConfigEntryNotReady
                self._last_problem = str(err)
                self._next_connect_attempt = time.time() + RECONNECT_COOLDOWN
                _LOGGER.warning("SenXor camera unavailable: %s", err)
                raise UpdateFailed(str(err)) from err

            if self._last_problem is not None:
                _LOGGER.info("SenXor camera is streaming again")
                self._last_problem = None
            frame = self._frame
            if frame is None:
                raise UpdateFailed("camera did not deliver a frame")

        return self._build_data()

    @property
    def connected(self) -> bool:
        """True while the TCP connection to the camera is open."""
        return self._connection.connected

    def probe_temperature(self, which: int) -> float | None:
        """Calibrated temperature (Celsius) at probe 1 or probe 2."""
        data = self.data
        if data is None:
            return None
        return data.probe_1 if which == 1 else data.probe_2

    def _build_data(self) -> SenXorData:
        frame = self._frame
        data = SenXorData(
            frame=frame,
            connected=self._connection.connected,
            last_error=self._connection.last_error,
            frame_rate=self._compute_frame_rate(),
        )
        if frame is None:
            return data
        values = apply_filter(
            calibrate(frame.pixels, self.settings.emissivity, self.settings.offset),
            self.settings.filtering,
        )
        data.values = values
        data.stats = compute_stats(values)
        (x1, y1), (x2, y2) = self.settings.probes
        data.probe_1 = values[y1 * FRAME_WIDTH + x1]
        data.probe_2 = values[y2 * FRAME_WIDTH + x2]
        return data

    def _compute_frame_rate(self) -> float:
        times = list(self._frame_times)
        if len(times) < 2:
            return 0.0
        span = times[-1] - times[0]
        if span <= 0:
            return 0.0
        return round((len(times) - 1) / span, 1)

    # -- rendering ---------------------------------------------------------
    async def async_render(self) -> RenderedFrame | None:
        """Render the latest frame, reusing the previous result when possible."""
        frame = self._frame
        if frame is None:
            return None

        options = self.settings.render_options()
        data = self.data
        values = data.values if data is not None and data.values else None
        if values is None:
            values = apply_filter(
                calibrate(frame.pixels, self.settings.emissivity, self.settings.offset),
                self.settings.filtering,
            )

        cache_key = hash(
            (
                options.palette,
                options.unit,
                options.auto_range,
                options.scale_min,
                options.scale_max,
                options.remove_extreme,
                options.trim_percent,
                options.filtering,
                options.emissivity,
                options.offset,
                options.show_markers,
                options.show_colorbar,
                options.jpeg_quality,
            )
        )
        cached = self._render_cache
        if cached is not None and cached[0] == frame.sequence and cached[1] == cache_key:
            return cached[2]

        rendered = await self.hass.async_add_executor_job(render_values, values, options)
        self.frames_rendered += 1
        self._render_cache = (frame.sequence, cache_key, rendered)
        return rendered
