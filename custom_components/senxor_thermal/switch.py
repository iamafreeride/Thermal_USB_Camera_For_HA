"""Switch platform: display toggles and continuous capture."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SenXorCoordinator
from .entity import SenXorEntity

_LOGGER = logging.getLogger(__name__)


async def _set_option(coordinator: SenXorCoordinator, **changes: bool) -> None:
    await coordinator.async_update_settings(**changes)


@dataclass(frozen=True, kw_only=True)
class SenXorSwitchDescription(SwitchEntityDescription):
    """Describes a boolean setting."""

    getter: Callable[[SenXorCoordinator], bool]
    on: Callable[[SenXorCoordinator], Awaitable[None]]
    off: Callable[[SenXorCoordinator], Awaitable[None]]


SWITCHES: tuple[SenXorSwitchDescription, ...] = (
    SenXorSwitchDescription(
        key="streaming",
        translation_key="streaming",
        name="連續擷取",
        getter=lambda coord: coord.settings.streaming,
        on=lambda coord: coord.async_set_streaming(True),
        off=lambda coord: coord.async_set_streaming(False),
        icon="mdi:video",
        entity_category=None,
    ),
    SenXorSwitchDescription(
        key="auto_range",
        translation_key="auto_range",
        name="自動色階",
        getter=lambda coord: coord.settings.auto_range,
        on=lambda coord: _set_option(coord, auto_range=True),
        off=lambda coord: _set_option(coord, auto_range=False),
        icon="mdi:autorenew",
        entity_category=None,
    ),
    SenXorSwitchDescription(
        key="remove_extreme",
        translation_key="remove_extreme",
        name="移除極值",
        getter=lambda coord: coord.settings.remove_extreme,
        on=lambda coord: _set_option(coord, remove_extreme=True),
        off=lambda coord: _set_option(coord, remove_extreme=False),
        icon="mdi:chart-bell-curve",
        entity_category=None,
    ),
    SenXorSwitchDescription(
        key="show_markers",
        translation_key="show_markers",
        name="顯示極值標記",
        getter=lambda coord: coord.settings.show_markers,
        on=lambda coord: _set_option(coord, show_markers=True),
        off=lambda coord: _set_option(coord, show_markers=False),
        icon="mdi:crosshairs-gps",
        entity_category=None,
    ),
    SenXorSwitchDescription(
        key="show_colorbar",
        translation_key="show_colorbar",
        name="顯示色階條",
        getter=lambda coord: coord.settings.show_colorbar,
        on=lambda coord: _set_option(coord, show_colorbar=True),
        off=lambda coord: _set_option(coord, show_colorbar=False),
        icon="mdi:gradient-vertical",
        entity_category=None,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SenXor switches."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities(
        SenXorSwitch(coordinator, entry, description) for description in SWITCHES
    )


class SenXorSwitch(SenXorEntity, SwitchEntity):
    """A boolean setting or the camera's capture state."""

    entity_description: SenXorSwitchDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorSwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key, "switch")
        self.entity_description = description
        self._attr_translation_key = description.translation_key
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    @property
    def is_on(self) -> bool:
        return self.entity_description.getter(self.coordinator)

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.entity_description.on(self.coordinator)

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.entity_description.off(self.coordinator)
