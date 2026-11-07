"""Lightweight HA API stubs for isolated local regression tests.

These do NOT replace an actual Home Assistant instance / integration test.
"""

from __future__ import annotations

from enum import Enum
import sys
from types import ModuleType, SimpleNamespace


def _module(name: str) -> ModuleType:
    module = ModuleType(name)
    module.__path__ = []
    sys.modules[name] = module
    return module


homeassistant = _module("homeassistant")
ha_const = _module("homeassistant.const")


class Platform(str, Enum):
    SENSOR = "sensor"


ha_const.Platform = Platform
ha_core = _module("homeassistant.core")
ha_core.HomeAssistant = object
ha_core.callback = lambda func: func
ha_entries = _module("homeassistant.config_entries")


class ConfigEntry:
    @classmethod
    def __class_getitem__(cls, _item):
        return cls


ha_entries.ConfigEntry = ConfigEntry
ha_entries.ConfigSubentry = SimpleNamespace
ha_entries.ConfigEntryError = type("ConfigEntryError", (Exception,), {})
ha_entries.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})
ha_loader = _module("homeassistant.loader")


async def async_get_integration(_hass, _domain):
    return SimpleNamespace(version="2026.11.0")


ha_loader.async_get_integration = async_get_integration
ha_components = _module("homeassistant.components")
ha_frontend = _module("homeassistant.components.frontend")
ha_frontend.add_extra_js_url = lambda hass, url: hass.extras.append(url)
