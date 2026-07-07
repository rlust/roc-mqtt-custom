"""Shared helpers for the RV-C integration.

Consolidates small utilities that were previously duplicated across the
platform modules (light, climate, cover, lock, switch, button).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


def get_entry_option(entry: "ConfigEntry", key: str, default: Any) -> Any:
    """Read a config value, preferring options over the original entry data."""
    return entry.options.get(key, entry.data.get(key, default))


def coerce_int(value: Any, fallback: int) -> int:
    """Coerce ``value`` to a non-negative int, returning ``fallback`` on failure."""
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback
