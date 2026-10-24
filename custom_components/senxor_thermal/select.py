"""Select platform: palette, image temperature unit, filtering and module gain."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import FILTER_MODES, GAIN_MODES, TEMPERATURE_UNITS
from .coordinator import SenXorCoordinator
from .entity import SenXorEntity
from .palette import PALETTE_NAMES

_LOGGER = logging.getLogger(__name__)


async def _set_option(coordinator: SenXorCoordinator, **changes: Any) -> None:
    await coordinator.async_update_settings(**changes)


@dataclass(frozen=True, kw_only=True)
class SenXorSelectDescription:
    """Description of a select entity."""

    key: str
    name: str
    options: list[str]
    getter: Callable[[SenXorCoordinator], str]
    setter: Callable[[SenXorCoordinator, str], Awaitable[None]]
    icon: str
    entity_category: EntityCategory | None = EntityCategory.CONFIG


SELECTS: tuple[SenXorSelectDescription, ...] = (
    SenXorSelectDescription(
        key="palette",
        name="調色盤",
        options=PALETTE_NAMES,
        getter=lambda coord: coord.settings.palette,
        setter=lambda coord, value: _set_option(coord, palette=value),
        icon="mdi:palette",
    ),
    SenXorSelectDescription(
        key="temperature_unit",
        name="影像溫度單位",
        options=TEMPERATURE_UNITS,
        getter=lambda coord: coord.settings.unit,
        setter=lambda coord, value: _set_option(coord, unit=value),
        icon="mdi:temperature-celsius",
    ),
    SenXorSelectDescription(
        key="filtering",
        name="濾波",
        options=FILTER_MODES,
        getter=lambda coord: coord.settings.filtering,
        setter=lambda coord, value: _set_option(coord, filtering=value),
        icon="mdi:blur",
    ),
    SenXorSelectDescription(
        key="gain",
        name="增益",
        options=GAIN_MODES,
        getter=lambda coord: coord.settings.gain,
        setter=lambda coord, value: coord.async_set_gain(value),
        icon="mdi:amplifier",
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
    """A select backed by a coordinator setting or a camera register."""

    entity_description: SenXorSelectDescription

    def __init__(
        self,
        coordinator: SenXorCoordinator,
        entry: ConfigEntry,
        description: SenXorSelectDescription,
    ) -> None:
        super().__init__(coordinator, entry, description.key, "select")
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_name = description.name
        self._attr_options = description.options
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category

    @property
    def current_option(self) -> str:
        return self.entity_description.getter(self.coordinator)

    async def async_select_option(self, option: str) -> None:
        """Apply the selected option."""
        await self.entity_description.setter(self.coordinator, option)
