"""Initialize RVC integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

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
    PLATFORMS,
)
from .mqtt_handler import RVCMQTTHandler

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (currently unused, but kept for compatibility)."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle config entry migration for updated defaults."""
    version = entry.version

    if version == 1:
        new_options = dict(entry.options)
        if new_options.get(CONF_AVAILABILITY_TIMEOUT) == DEFAULT_AVAILABILITY_TIMEOUT:
            new_options.pop(CONF_AVAILABILITY_TIMEOUT)
        hass.config_entries.async_update_entry(entry, version=2, options=new_options)
        _LOGGER.info(
            "RVC config entry %s migrated from v1 to v2 (availability timeout defaults)",
            entry.entry_id,
        )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RVC from a config entry."""
    _LOGGER.info("Setting up RVC integration entry %s", entry.entry_id)

    config = _ensure_entry_options(hass, entry)

    handler = RVCMQTTHandler(hass, config)
    await handler.async_subscribe()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "handler": handler,
        "unsub_dispatchers": [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Note: Services are registered via entity platform in light.py

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading RVC integration entry %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        handler: RVCMQTTHandler | None = data.get("handler")
        if handler:
            await handler.async_unsubscribe()
        for unsub in data.get("unsub_dispatchers", []):
            unsub()

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle config entry updates by reloading the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


def _ensure_entry_options(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Ensure topic prefix and discovery flags live in entry.options."""
    desired = dict(entry.options)
    updated = False

    defaults: dict[str, object] = {
        CONF_TOPIC_PREFIX: entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
        CONF_AUTO_DISCOVERY: entry.data.get(CONF_AUTO_DISCOVERY, DEFAULT_AUTO_DISCOVERY),
        CONF_COMMAND_TOPIC: entry.data.get(CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC),
        CONF_GPS_TOPIC: entry.data.get(CONF_GPS_TOPIC, DEFAULT_GPS_TOPIC),
    }

    for key, value in defaults.items():
        if key not in desired:
            desired[key] = value
            updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, options=desired)

    return desired
