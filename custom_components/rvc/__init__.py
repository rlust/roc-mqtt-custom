"""Initialize RVC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .mqtt_handler import RVCMQTTHandler

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (currently unused, but kept for compatibility)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RVC from a config entry."""
    _LOGGER.info("Setting up RVC integration entry %s", entry.entry_id)

    handler = RVCMQTTHandler(hass, entry.data)
    await handler.async_subscribe()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "handler": handler,
        "unsub_dispatchers": [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
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
