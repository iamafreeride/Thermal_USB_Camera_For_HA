"""Switch platform: display toggles mirrored from the vendor viewer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SenXorCoordinator
from .entity import SenXorEntity

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SenXorSwitchDescription:
    """Description of a boolean setting."""

    key: str
    name: str
    setting: str
    getter: Callable[[SenXorCoordinator], bool]
    icon: str


SWITCHES: tuple[SenXorSwitchDescription, ...] = (
    SenXorSwitchDescription(
        key="auto_range",
        name="Automatic temperature range",
        setting="auto_range",
        getter=lambda coord: coord.settings.auto_range,
        icon="mdi:autorenew",
    ),
    SenXorSwitchDescription(
        key="remove_extreme",
        name="Remove extreme values",
        setting="remove_extreme",
        getter=lambda coord: coord.settings.remove_extreme,
        icon="mdi:chart-bell-curve",
    ),
    SenXorSwitchDescription(
        key="show_markers",
        name="Show min/max markers",
        setting="show_markers",
        getter=lambda coord: coord.settings.show_markers,
        icon="mdi:crosshairs-gps",
    ),
    SenXorSwitchDescription(
        key="show_colorbar",
        name="Show colour bar",
        setting="show_colorbar",
        getter=lambda coord: coord.settings.show_colorbar,
        icon="mdi:gradient-vertical",
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
    """A boolean display setting."""

    entity_description: SenXorSwitchDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorSwitchDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_icon = description.icon

    @property
    def is_on(self) -> bool:
        return self.entity_description.getter(self.coordinator)

    async def async_turn_on(self, **kwargs: object) -> None:
        await self.coordinator.async_update_settings(
            **{self.entity_description.setting: True}
        )

    async def async_turn_off(self, **kwargs: object) -> None:
        await self.coordinator.async_update_settings(
            **{self.entity_description.setting: False}
        )
