"""Diagnostics support for the RV-C integration."""
from __future__ import annotations

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_AVAILABILITY_TIMEOUT,
    CONF_COMMAND_TOPIC,
    CONF_GPS_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_AUTO_DISCOVERY,
    DEFAULT_AVAILABILITY_TIMEOUT,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_GPS_TOPIC,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
)

TO_REDACT: set[str] = set()


def _entry_option(entry: ConfigEntry, key: str, default: object) -> object:
    return entry.options.get(key, entry.data.get(key, default))


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return diagnostics for a config entry."""
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    handler = stored.get("handler")

    data = {
        "config_entry": {
            "topic_prefix": _entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
            "auto_discovery": _entry_option(entry, CONF_AUTO_DISCOVERY, DEFAULT_AUTO_DISCOVERY),
            "command_topic": _entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC),
            "gps_topic": _entry_option(entry, CONF_GPS_TOPIC, DEFAULT_GPS_TOPIC),
            "availability_timeout": _entry_option(
                entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
            ),
        }
    }

    if handler is not None:
        data["mqtt"] = handler.diagnostics_snapshot()

    return async_redact_data(data, TO_REDACT)
