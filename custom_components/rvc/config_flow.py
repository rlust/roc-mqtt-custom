"""Handle the config flow for RVC integration."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .const import DOMAIN, CONF_TOPIC_PREFIX, CONF_AUTO_DISCOVERY


class RVCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the RVC integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="RV-C", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC_PREFIX, default="rvc"): str,
                vol.Optional(CONF_AUTO_DISCOVERY, default=True): bool,
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

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOPIC_PREFIX,
                    default=self._entry.data.get(CONF_TOPIC_PREFIX, "rvc"),
                ): str,
                vol.Optional(
                    CONF_AUTO_DISCOVERY,
                    default=self._entry.data.get(CONF_AUTO_DISCOVERY, True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)
