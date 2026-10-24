"""SenXor thermal camera integration for Home Assistant.

Ports the feature set of Meridian Innovation's ``SenXorEvkViewer`` to Home
Assistant: live thermogram, palettes, temperature range control, spatial
filtering, emissivity/offset calibration and frame statistics.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_JPEG_QUALITY,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_SNAPSHOT,
)
from .coordinator import SenXorCoordinator
from .rendering import frame_to_csv

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

SNAPSHOT_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Optional("filename"): str,
        vol.Optional("csv", default=True): bool,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a SenXor camera from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    scan_interval = float(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    coordinator = SenXorCoordinator(hass, entry, host, port, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: SenXorCoordinator = entry.runtime_data
        await coordinator.async_shutdown()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the snapshot service once."""
    if hass.services.has_service(DOMAIN, SERVICE_SNAPSHOT):
        return

    async def async_handle_snapshot(call: ServiceCall) -> dict[str, Any]:
        coordinators: dict[str, SenXorCoordinator] = hass.data.get(DOMAIN, {})
        entry_id = call.data.get("entry_id")
        if entry_id:
            coordinator = coordinators.get(entry_id)
            if coordinator is None:
                raise HomeAssistantError(f"unknown config entry {entry_id}")
        elif len(coordinators) == 1:
            coordinator = next(iter(coordinators.values()))
        else:
            raise HomeAssistantError("multiple cameras configured, pass entry_id")

        rendered = await coordinator.async_render()
        frame = coordinator.data.frame if coordinator.data else None
        if rendered is None or frame is None:
            raise HomeAssistantError("no thermal frame available")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        name = call.data.get("filename") or f"senxor-{stamp}"
        folder = hass.config.path("www", "senxor_thermal")
        await hass.async_add_executor_job(os.makedirs, folder, True)

        image_path = os.path.join(folder, f"{name}.jpg")
        await hass.async_add_executor_job(_write_binary, image_path, rendered.jpeg)

        result: dict[str, Any] = {
            "image": image_path,
            "sequence": frame.sequence,
            "min_dk": frame.min_dk,
            "max_dk": frame.max_dk,
        }
        if call.data.get("csv", True):
            csv_path = os.path.join(folder, f"{name}.csv")
            csv_data = frame_to_csv(frame, coordinator.settings.render_options())
            await hass.async_add_executor_job(_write_text, csv_path, csv_data)
            result["csv"] = csv_path
        return result

    hass.services.async_register(
        DOMAIN,
        SERVICE_SNAPSHOT,
        async_handle_snapshot,
        schema=SNAPSHOT_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _write_binary(path: str, data: bytes) -> None:
    with open(path, "wb") as handle:
        handle.write(data)


def _write_text(path: str, data: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(data)
