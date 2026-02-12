"""Handle the config flow for RVC integration."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

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


class RVCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the RVC integration."""

    VERSION = 2

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="RV-C", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC_PREFIX, default=DEFAULT_TOPIC_PREFIX): str,
                vol.Optional(CONF_AUTO_DISCOVERY, default=DEFAULT_AUTO_DISCOVERY): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    @callback
    def async_get_options_flow(
        self, config_entry: config_entries.ConfigEntry  # type: ignore[override]
    ):
        return RVCOptionsFlow(config_entry)


class RVCOptionsFlow(config_entries.OptionsFlow):
    """Options flow for RVC entries."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        def _entry_value(key: str, default: Any) -> Any:
            return self._entry.options.get(key, self._entry.data.get(key, default))

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOPIC_PREFIX,
                    default=_entry_value(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                ): str,
                vol.Optional(
                    CONF_AUTO_DISCOVERY,
                    default=_entry_value(CONF_AUTO_DISCOVERY, DEFAULT_AUTO_DISCOVERY),
                ): bool,
                vol.Required(
                    CONF_COMMAND_TOPIC,
                    default=_entry_value(CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC),
                ): str,
                vol.Required(
                    CONF_GPS_TOPIC,
                    default=_entry_value(CONF_GPS_TOPIC, DEFAULT_GPS_TOPIC),
                ): str,
                vol.Required(
                    CONF_AVAILABILITY_TIMEOUT,
                    default=_entry_value(
                        CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=86400)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)
