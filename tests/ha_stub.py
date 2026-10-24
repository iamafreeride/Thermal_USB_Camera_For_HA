"""Minimal Home Assistant stubs so the integration's glue code can be unit tested.

Only the API surface used by this integration is implemented; behaviour is
faithful enough to construct entities and read their properties, but this is not
a Home Assistant emulator.
"""

from __future__ import annotations

import enum
import sys
import types
from dataclasses import dataclass, field
from typing import Any


def _module(name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def install() -> None:  # noqa: PLR0915 - one flat block of stubs is clearer
    if "homeassistant" in sys.modules:
        return

    ha = _module("homeassistant")
    ha.__path__ = []  # mark as a package

    # -- homeassistant.const ------------------------------------------------
    const = _module("homeassistant.const")

    class Platform(str, enum.Enum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        CAMERA = "camera"
        NUMBER = "number"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"

    class UnitOfTemperature(str, enum.Enum):
        CELSIUS = "°C"
        FAHRENHEIT = "°F"
        KELVIN = "K"

    class UnitOfElectricPotential(str, enum.Enum):
        VOLT = "V"

    class EntityCategory(str, enum.Enum):
        CONFIG = "config"
        DIAGNOSTIC = "diagnostic"

    const.Platform = Platform
    const.UnitOfTemperature = UnitOfTemperature
    const.UnitOfElectricPotential = UnitOfElectricPotential
    const.EntityCategory = EntityCategory
    const.CONF_HOST = "host"
    const.CONF_NAME = "name"

    # -- homeassistant.core -------------------------------------------------
    core = _module("homeassistant.core")

    class HomeAssistant:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}
            self.config_entries = ConfigEntriesManager()
            self.services = Services()

        async def async_add_executor_job(self, func, *args):
            return func(*args)

        def config_path(self, *parts: str) -> str:
            import os
            import tempfile

            return os.path.join(tempfile.gettempdir(), *parts)

    class ServiceCall:
        def __init__(self, data: dict[str, Any] | None = None) -> None:
            self.data = data or {}

    class SupportsResponse(str, enum.Enum):
        NONE = "none"
        OPTIONAL = "optional"
        ONLY = "only"

    class HomeAssistantError(Exception):
        pass

    def callback(func):
        return func

    core.HomeAssistant = HomeAssistant
    core.ServiceCall = ServiceCall
    core.SupportsResponse = SupportsResponse
    core.callback = callback
    core.HomeAssistantError = HomeAssistantError

    _module("homeassistant.exceptions").HomeAssistantError = HomeAssistantError

    # -- homeassistant.config_entries --------------------------------------
    config_entries = _module("homeassistant.config_entries")

    class ConfigEntry:
        def __init__(self, data=None, options=None, title="Thermal Camera") -> None:
            self.entry_id = "test-entry"
            self.data = data or {}
            self.options = options or {}
            self.title = title
            self.runtime_data = None

    class ConfigFlowResult(dict):
        pass

    class ConfigFlow:
        domain = None

        def __init_subclass__(cls, domain=None, **kwargs):
            super().__init_subclass__(**kwargs)
            if domain:
                cls.domain = domain

        async def async_set_unique_id(self, unique_id: str) -> None:
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self) -> None:
            return None

        def async_create_entry(self, **kwargs) -> ConfigFlowResult:
            return ConfigFlowResult(kwargs)

        def async_show_form(self, **kwargs) -> ConfigFlowResult:
            return ConfigFlowResult(kwargs)

    class OptionsFlow:
        def async_create_entry(self, **kwargs) -> ConfigFlowResult:
            return ConfigFlowResult(kwargs)

        def async_show_form(self, **kwargs) -> ConfigFlowResult:
            return ConfigFlowResult(kwargs)

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.ConfigFlowResult = ConfigFlowResult
    config_entries.OptionsFlow = OptionsFlow

    # -- homeassistant.helpers ---------------------------------------------
    helpers = _module("homeassistant.helpers")
    helpers.__path__ = []

    update_coordinator = _module("homeassistant.helpers.update_coordinator")

    class UpdateFailed(Exception):
        pass

    class DataUpdateCoordinator:
        def __init__(
            self,
            hass,
            logger,
            *,
            name: str | None = None,
            update_interval=None,
            update_method=None,
            **kwargs,
        ) -> None:
            self.hass = hass
            self.logger = logger
            self.name = name
            self.update_interval = update_interval
            self.data = None
            self.last_update_success = True

        @classmethod
        def __class_getitem__(cls, item):
            return cls

        async def _async_update_data(self):
            raise NotImplementedError

        async def async_config_entry_first_refresh(self) -> None:
            self.data = await self._async_update_data()
            self.last_update_success = True

        async def async_request_refresh(self) -> None:
            self.data = await self._async_update_data()

        def async_set_updated_data(self, data) -> None:
            self.data = data

    class CoordinatorEntity:
        @classmethod
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, coordinator) -> None:
            self.coordinator = coordinator

        @property
        def available(self) -> bool:
            return True

        def async_write_ha_state(self) -> None:
            return None

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.UpdateFailed = UpdateFailed

    device_registry = _module("homeassistant.helpers.device_registry")
    device_registry.DeviceInfo = dict

    entity_registry = _module("homeassistant.helpers.entity_registry")

    class _Registry:
        def __init__(self) -> None:
            self.removed: list[str] = []

        def async_get_entity_id(self, domain: str, integration: str, unique_id: str):
            return None

        def async_remove(self, entity_id: str) -> None:
            self.removed.append(entity_id)

    entity_registry.async_get = lambda hass: _Registry()

    entity_platform = _module("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = Any

    _module("homeassistant.helpers.config_validation")
    config_validation = sys.modules["homeassistant.helpers.config_validation"]
    config_validation.string = str
    config_validation.port = int
    config_validation.positive_int = int

    # -- homeassistant.components.* ---------------------------------------
    components = _module("homeassistant.components")
    components.__path__ = []

    camera = _module("homeassistant.components.camera")

    class CameraEntityFeature(enum.IntFlag):
        ON_OFF = 1
        STREAM = 2

    class Camera:
        def __init__(self) -> None:
            pass

        @property
        def available(self) -> bool:
            return True

        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

        @property
        def name(self):
            return getattr(self, "_attr_name", None)

    camera.Camera = Camera
    camera.CameraEntityFeature = CameraEntityFeature

    sensor = _module("homeassistant.components.sensor")

    class SensorDeviceClass(str, enum.Enum):
        TEMPERATURE = "temperature"
        VOLTAGE = "voltage"

    class SensorStateClass(str, enum.Enum):
        MEASUREMENT = "measurement"
        TOTAL_INCREASING = "total_increasing"

    @dataclass(frozen=True, kw_only=True)
    class SensorEntityDescription:
        key: str
        name: str | None = None
        translation_key: str | None = None
        device_class: Any = None
        state_class: Any = None
        native_unit_of_measurement: str | None = None
        suggested_display_precision: int | None = None
        icon: str | None = None
        entity_category: Any = None

    class SensorEntity:
        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

        @property
        def name(self):
            return getattr(self, "_attr_name", None)

    sensor.SensorDeviceClass = SensorDeviceClass
    sensor.SensorStateClass = SensorStateClass
    sensor.SensorEntityDescription = SensorEntityDescription
    sensor.SensorEntity = SensorEntity

    number = _module("homeassistant.components.number")

    class NumberDeviceClass(str, enum.Enum):
        TEMPERATURE = "temperature"

    class NumberMode(str, enum.Enum):
        BOX = "box"
        SLIDER = "slider"

    class NumberEntity:
        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

        @property
        def name(self):
            return getattr(self, "_attr_name", None)

    number.NumberDeviceClass = NumberDeviceClass
    number.NumberMode = NumberMode
    number.NumberEntity = NumberEntity

    select = _module("homeassistant.components.select")

    class SelectEntity:
        @property
        def name(self):
            return getattr(self, "_attr_name", None)

        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

        @property
        def options(self):
            return getattr(self, "_attr_options", [])

        @property
        def current_option(self):  # pragma: no cover - overridden by the entity
            return None

    select.SelectEntity = SelectEntity

    switch = _module("homeassistant.components.switch")

    class SwitchEntity:
        @property
        def name(self):
            return getattr(self, "_attr_name", None)

        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

    switch.SwitchEntity = SwitchEntity

    button = _module("homeassistant.components.button")

    class ButtonEntity:
        @property
        def name(self):
            return getattr(self, "_attr_name", None)

        @property
        def unique_id(self):
            return getattr(self, "_attr_unique_id", None)

    button.ButtonEntity = ButtonEntity

    # -- voluptuous --------------------------------------------------------
    voluptuous = _module("voluptuous")

    class _Marker:
        def __init__(self, key, default=None):
            self.key = key
            self.default = default

    class Schema:
        def __init__(self, schema, extra=None):
            self.schema = schema

        def __call__(self, data):
            return data

    class _All:
        def __init__(self, *validators):
            self.validators = validators

    class _Range:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _Coerce:
        def __init__(self, kind):
            self.kind = kind

    voluptuous.Schema = Schema
    voluptuous.Required = lambda key, default=None: _Marker(key, default)
    voluptuous.Optional = lambda key, default=None: _Marker(key, default)
    voluptuous.All = _All
    voluptuous.Range = _Range
    voluptuous.Coerce = _Coerce
    voluptuous.In = lambda *args, **kwargs: None

    # -- keep references to helpers used by the coordinator ----------------
    ha.const = const
    ha.core = core


class ConfigEntriesManager:
    """Stands in for ``hass.config_entries``."""

    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}
        self.updated: list[dict[str, Any]] = []

    def async_update_entry(self, entry, **kwargs) -> None:
        self.updated.append(kwargs)
        if "options" in kwargs:
            entry.options = kwargs["options"]

    async def async_forward_entry_setups(self, entry, platforms) -> None:
        return None

    async def async_unload_platforms(self, entry, platforms) -> bool:
        return True


class Services:
    """Stands in for ``hass.services``."""

    def __init__(self) -> None:
        self.registered: dict[tuple[str, str], Any] = {}

    def has_service(self, domain: str, service: str) -> bool:
        return (domain, service) in self.registered

    def async_register(self, domain, service, handler, **kwargs) -> None:
        self.registered[(domain, service)] = (handler, kwargs)
