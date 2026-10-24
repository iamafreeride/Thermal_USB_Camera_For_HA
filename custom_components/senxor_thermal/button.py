"""Button platform: capture and stream control of the SenXor camera."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SenXorCoordinator
from .entity import SenXorEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SenXorButtonDescription:
    """Description of an action button."""

    key: str
    name: str
    action: Callable[[SenXorCoordinator], Awaitable[None]]
    icon: str


BUTTONS: tuple[SenXorButtonDescription, ...] = (
    SenXorButtonDescription(
        key="single_frame",
        name="Single frame",
        action=lambda coord: coord.async_single_frame(),
        icon="mdi:camera-iris",
    ),
    SenXorButtonDescription(
        key="restart_stream",
        name="Restart stream",
        action=lambda coord: coord.async_connect(),
        icon="mdi:restart",
    ),
    SenXorButtonDescription(
        key="frame_rate_up",
        name="Increase frame rate",
        action=lambda coord: coord.async_frame_rate_up(),
        icon="mdi:speedometer",
    ),
    SenXorButtonDescription(
        key="frame_rate_down",
        name="Decrease frame rate",
        action=lambda coord: coord.async_frame_rate_down(),
        icon="mdi:speedometer-slow",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SenXor buttons."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities(
        SenXorButton(coordinator, entry, description) for description in BUTTONS
    )


class SenXorButton(SenXorEntity, ButtonEntity):
    """A button that sends a command register write."""

    entity_description: SenXorButtonDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorButtonDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon

    @property
    def available(self) -> bool:
        """Buttons stay usable while the stream is down so they can recover it."""
        return True

    async def async_press(self) -> None:
        """Run the configured action, reconnecting first when necessary."""
        coordinator = self.coordinator
        if not coordinator.connected:
            try:
                await coordinator.async_connect()
            except Exception as err:  # noqa: BLE001 - surfaced to the user
                raise HomeAssistantError(f"Camera is not reachable: {err}") from err
        await self.entity_description.action(coordinator)
