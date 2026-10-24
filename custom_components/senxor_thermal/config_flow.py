"""Config and options flow for the SenXor thermal camera integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_JPEG_QUALITY,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    NAME,
)
from .protocol import SenXorProtocolError, async_probe

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


class SenXorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI setup of a SenXor thermal camera."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the camera address and verify that it streams frames."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                frame = await async_probe(host, port)
            except (SenXorProtocolError, TimeoutError, OSError) as err:
                _LOGGER.debug("Probe of %s:%s failed: %r", host, port, err)
                errors["base"] = "cannot_connect"
            else:
                _LOGGER.info(
                    "SenXor camera at %s:%s streaming %sx%s frames (min %s dK, max %s dK)",
                    host,
                    port,
                    80,
                    62,
                    frame.min_dk,
                    frame.max_dk,
                )
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or f"{NAME} ({host})",
                    data={CONF_HOST: host, CONF_PORT: port},
                    options={
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_JPEG_QUALITY: DEFAULT_JPEG_QUALITY,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={"default_port": str(DEFAULT_PORT)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return SenXorOptionsFlow(config_entry)


class SenXorOptionsFlow(OptionsFlow):
    """Configure polling and image quality."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(float), vol.Range(min=MIN_SCAN_INTERVAL, max=60)),
                vol.Optional(
                    CONF_JPEG_QUALITY,
                    default=options.get(CONF_JPEG_QUALITY, DEFAULT_JPEG_QUALITY),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=95)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
