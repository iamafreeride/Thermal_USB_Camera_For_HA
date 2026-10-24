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
    CONF_GAIN,
    CONF_JPEG_QUALITY,
    CONF_OFFSET,
    CONF_PALETTE,
    CONF_REMOVE_EXTREME,
    CONF_SCALE_MAX,
    CONF_SCALE_MIN,
    CONF_SHOW_COLORBAR,
    CONF_SHOW_MARKERS,
    CONF_UNIT,
    DEFAULT_EMISSIVITY,
    DEFAULT_FILTER,
    DEFAULT_GAIN,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_OFFSET,
    DEFAULT_SCALE_MAX,
    DEFAULT_SCALE_MIN,
    DEFAULT_UNIT,
    DOMAIN,
)
from .palette import DEFAULT_PALETTE
from .protocol import FRAME_HEIGHT, FRAME_WIDTH, SenXorConnection, ThermalFrame
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
        }

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
        self.streaming = True
        self.frames_rendered = 0

    # -- connection --------------------------------------------------------
    async def async_connect(self, wait_for_frame: float = 8.0) -> None:
        """(Re)connect to the camera, start streaming and wait for one frame."""
        async with self._connect_lock:
            self._first_frame.clear()
            await self._connection.connect()
            await self._connection.start_stream()
            self.streaming = True
            try:
                await asyncio.wait_for(self._first_frame.wait(), timeout=wait_for_frame)
            except TimeoutError:
                _LOGGER.debug("No frame within %.1f s of connecting", wait_for_frame)

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

    async def async_frame_rate_up(self) -> None:
        await self._connection.frame_rate_up()

    async def async_frame_rate_down(self) -> None:
        await self._connection.frame_rate_down()

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
        if not self._connection.connected:
            try:
                await self.async_connect()
            except Exception as err:  # noqa: BLE001 - network errors are expected
                raise UpdateFailed(f"cannot connect to {self.host}:{self.port}: {err}") from err

        frame = self._frame
        if frame is None:
            raise UpdateFailed("waiting for the first frame")

        interval = self.update_interval or timedelta(seconds=10)
        if time.time() - frame.received > max(10.0, interval.total_seconds() * 5):
            raise UpdateFailed("no frames received recently")

        return self._build_data()

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
