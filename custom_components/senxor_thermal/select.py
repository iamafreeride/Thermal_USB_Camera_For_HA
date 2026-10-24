"""Select platform: palette, image temperature unit and spatial filtering."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FILTER_MODES, TEMPERATURE_UNITS
from .protocol import FPS_LEVELS
from .coordinator import SenXorCoordinator
from .entity import SenXorEntity
from .palette import PALETTE_NAMES

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class SenXorSelectDescription:
    """Description of a select entity."""

    key: str
    name: str
    options: list[str]
    getter: Callable[[SenXorCoordinator], str]
    setting: str
    icon: str
    convert: Callable[[str], Any] | None = None


SELECTS: tuple[SenXorSelectDescription, ...] = (
    SenXorSelectDescription(
        key="palette",
        name="Colour palette",
        options=PALETTE_NAMES,
        getter=lambda coord: coord.settings.palette,
        setting="palette",
        icon="mdi:palette",
    ),
    SenXorSelectDescription(
        key="temperature_unit",
        name="Image temperature unit",
        options=TEMPERATURE_UNITS,
        getter=lambda coord: coord.settings.unit,
        setting="unit",
        icon="mdi:temperature-celsius",
    ),
    SenXorSelectDescription(
        key="filtering",
        name="Filtering",
        options=FILTER_MODES,
        getter=lambda coord: coord.settings.filtering,
        setting="filtering",
        icon="mdi:blur",
    ),
    SenXorSelectDescription(
        key="frame_rate_level",
        name="Frame rate level",
        options=[str(level) for level in FPS_LEVELS],
        getter=lambda coord: str(coord.settings.fps_level),
        setting="fps_level",
        icon="mdi:speedometer",
        convert=int,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SenXor selects."""
    coordinator: SenXorCoordinator = entry.runtime_data
    async_add_entities(
        SenXorSelect(coordinator, entry, description) for description in SELECTS
    )


class SenXorSelect(SenXorEntity, SelectEntity):
    """A select backed by a coordinator setting."""

    entity_description: SenXorSelectDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorSelectDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_options = description.options
        self._attr_icon = description.icon

    @property
    def current_option(self) -> str:
        return self.entity_description.getter(self.coordinator)

    async def async_select_option(self, option: str) -> None:
        """Apply the selected option."""
        description = self.entity_description
        if description.key == "frame_rate_level":
            await self.coordinator.async_set_fps_level(int(option))
            return
        value = description.convert(option) if description.convert else option
        await self.coordinator.async_update_settings(**{description.setting: value})
