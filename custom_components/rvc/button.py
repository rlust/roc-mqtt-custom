"""RV-C button platform for momentary actions (e.g., generator start/stop)."""
from __future__ import annotations

from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_COMMAND_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    BUTTON_DEFINITIONS,
)

import logging

_LOGGER = logging.getLogger(__name__)


def _get_entry_option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    command_topic = _get_entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
    topic_prefix = _get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)

    entities = [
        RVCButton(
            key,
            definition["name"],
            definition["instance"],
            int(definition.get("command", "2")),
            command_topic,
            topic_prefix,
            definition.get("icon"),
        )
        for key, definition in BUTTON_DEFINITIONS.items()
    ]

    if entities:
        async_add_entities(entities)


class RVCButton(ButtonEntity):
    """Representation of a momentary RV-C command."""

    _attr_should_poll = False

    def __init__(
        self,
        key: str,
        name: str,
        instance_id: str,
        command: int,
        command_topic: str,
        topic_prefix: str,
        icon: str | None,
    ) -> None:
        self._key = key
        self._instance = instance_id
        self._command = command
        self._command_topic = command_topic
        self._topic_prefix = topic_prefix
        self._attr_name = name
        self._attr_has_entity_name = False
        if icon:
            self._attr_icon = icon
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "rvc_topic_prefix": topic_prefix,
            "command_code": command,
        }

    @property
    def unique_id(self) -> str:
        return f"rvc_button_{self._key}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "generator_controls")},
            name="RV Generator Controls",
            manufacturer="RV-C",
            model="Generator Panel",
            via_device=(DOMAIN, "main_controller"),
        )

    async def async_press(self) -> None:
        instance = int(self._instance)
        payload = f"{instance} {self._command} 100"
        _LOGGER.info(
            "Button %s (%s) publishing command '%s'", self.entity_id, self._attr_name, payload
        )
        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )
