"""Test setup: stub the Home Assistant modules the integration imports.

This lets the pure-logic parts of the integration (helpers, MQTT
classification/validation) be tested with plain pytest, without installing
the full homeassistant package in CI.
"""
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# Make the repo root importable so `custom_components.rvc` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _StubModule(types.ModuleType):
    """Module that fabricates a MagicMock for any missing attribute."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, value)
        return value


_HA_MODULES = [
    "homeassistant",
    "homeassistant.components",
    "homeassistant.components.mqtt",
    "homeassistant.components.button",
    "homeassistant.components.climate",
    "homeassistant.components.climate.const",
    "homeassistant.components.cover",
    "homeassistant.components.device_tracker",
    "homeassistant.components.device_tracker.config_entry",
    "homeassistant.components.diagnostics",
    "homeassistant.components.light",
    "homeassistant.components.lock",
    "homeassistant.components.sensor",
    "homeassistant.components.switch",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.dispatcher",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.event",
    "homeassistant.helpers.restore_state",
    "homeassistant.helpers.typing",
    "voluptuous",
]

for name in _HA_MODULES:
    if name not in sys.modules:
        mod = _StubModule(name)
        mod.__path__ = []  # mark as package so submodule imports work
        sys.modules[name] = mod
        parent, _, child = name.rpartition(".")
        if parent:
            setattr(sys.modules[parent], child, mod)

# Entity base classes must be real classes so platform classes can subclass them.
for mod_name, cls_name in [
    ("homeassistant.components.button", "ButtonEntity"),
    ("homeassistant.components.climate", "ClimateEntity"),
    ("homeassistant.components.lock", "LockEntity"),
    ("homeassistant.components.switch", "SwitchEntity"),
    ("homeassistant.components.device_tracker.config_entry", "TrackerEntity"),
    ("homeassistant.helpers.restore_state", "RestoreEntity"),
]:
    setattr(sys.modules[mod_name], cls_name, type(cls_name, (), {}))

# Record dispatcher sends so tests can assert on discovery events.
_dispatch_calls = []


def _record_dispatch(hass, signal, data):
    _dispatch_calls.append((signal, data))


sys.modules["homeassistant.helpers.dispatcher"].async_dispatcher_send = _record_dispatch


def get_dispatch_calls():
    return _dispatch_calls
