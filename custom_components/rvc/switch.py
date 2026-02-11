"""RV-C switch platform for relay-style loads."""
from __future__ import annotations

from typing import Any

from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .availability import AvailabilityMixin
from .const import (
    CONF_AVAILABILITY_TIMEOUT,
    CONF_COMMAND_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_AVAILABILITY_TIMEOUT,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
    SWITCH_DEFINITIONS,
)

import logging

_LOGGER = logging.getLogger(__name__)


def _get_entry_option(entry: ConfigEntry, key: str, default: Any) -> Any:
    return entry.options.get(key, entry.data.get(key, default))


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


def _instances() -> dict[str, dict[str, str]]:
    return SWITCH_DEFINITIONS


def _for_instance(instance: str) -> dict[str, str] | None:
    for definition in SWITCH_DEFINITIONS.values():
        if definition["instance"] == instance:
            return definition
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCSwitch] = {}
    topic_prefix = _get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    command_topic = _get_entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
    availability_timeout = _coerce_int(
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT),
        DEFAULT_AVAILABILITY_TIMEOUT,
    )

    initial_entities = []
    for switch_id, definition in _instances().items():
        instance = definition["instance"]
        entity = RVCSwitch(
            name=definition["name"],
            instance_id=instance,
            topic_prefix=topic_prefix,
            command_topic=command_topic,
            availability_timeout=availability_timeout,
        )
        entities[instance] = entity
        initial_entities.append(entity)
        _LOGGER.debug("Pre-created switch entity %s (%s)", switch_id, instance)

    if initial_entities:
        async_add_entities(initial_entities)

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":
            return

        instance = str(discovery["instance"])
        if instance not in entities:
            return

        entities[instance].handle_mqtt(discovery["payload"])

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCSwitch(AvailabilityMixin, RestoreEntity, SwitchEntity):
    """Representation of a relay-style RV-C switch."""

    def __init__(
        self,
        name: str,
        instance_id: str,
        topic_prefix: str,
        command_topic: str,
        availability_timeout: int,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._command_topic = command_topic
        self._attr_is_on = False
        self._attr_assumed_state = True
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "rvc_topic_prefix": topic_prefix,
            "availability_timeout": availability_timeout,
            "last_command": None,
            "last_mqtt_update": None,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        if last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"

    @property
    def unique_id(self) -> str:
        return f"rvc_switch_{self._instance}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "utility_switches")},
            name="RV Utility Switches",
            manufacturer="RV-C",
            model="Relay Controller",
            via_device=(DOMAIN, "main_controller"),
        )

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        self.mark_seen_now()

        if "operating status (brightness)" in payload:
            try:
                pct = float(payload["operating status (brightness)"])
                self._attr_is_on = pct > 0
            except (TypeError, ValueError):
                pass

        if "state" in payload:
            state = str(payload["state"]).upper()
            if state in ("ON", "OFF"):
                self._attr_is_on = state == "ON"

        attrs = self._attr_extra_state_attributes
        if "last command definition" in payload:
            attrs["last_command"] = payload["last command definition"]
        elif "last command" in payload:
            attrs["last_command"] = f"Code {payload['last command']}"

        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_publish(command=2, value=100)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_publish(command=3, value=0)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_toggle(self, **kwargs: Any) -> None:
        await self._async_publish(command=5, value=100)

    async def _async_publish(self, command: int, value: int) -> None:
        instance = int(self._instance)
        payload = f"{instance} {command} {value}"
        _LOGGER.info(
            "Switch %s (%s) command %s -> %s", self._instance, self._attr_name, command, payload
        )
        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )
