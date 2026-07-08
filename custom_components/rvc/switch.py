"""RV-C switch platform for relay-style loads."""
from __future__ import annotations

import json
import logging
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
    AQUA_HOT_LOAD_DEFINITIONS,
    CONF_AVAILABILITY_TIMEOUT,
    CONF_COMMAND_TOPIC,
    CONF_THERMOSTAT_BRIDGE_MODE,
    CONF_TOPIC_PREFIX,
    DEFAULT_ACLOAD_BRIDGE_TOPIC,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_SWITCH_AVAILABILITY_TIMEOUT,
    DEFAULT_THERMOSTAT_BRIDGE_MODE,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
    SWITCH_DEFINITIONS,
)
from .helpers import coerce_int as _coerce_int
from .helpers import get_entry_option as _get_entry_option

_LOGGER = logging.getLogger(__name__)




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
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_SWITCH_AVAILABILITY_TIMEOUT),
        DEFAULT_SWITCH_AVAILABILITY_TIMEOUT,
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

    bridge_mode = bool(
        _get_entry_option(entry, CONF_THERMOSTAT_BRIDGE_MODE, DEFAULT_THERMOSTAT_BRIDGE_MODE)
    )
    acload_entities: dict[str, RVCAcLoadSwitch] = {}
    if bridge_mode:
        for load_id, definition in AQUA_HOT_LOAD_DEFINITIONS.items():
            entity = RVCAcLoadSwitch(
                name=definition["name"],
                instance_id=definition["instance"],
                availability_timeout=availability_timeout,
            )
            acload_entities[definition["instance"]] = entity
            initial_entities.append(entity)
            _LOGGER.debug("Pre-created Aqua-Hot load switch %s (%s)", load_id, definition["instance"])

    if initial_entities:
        async_add_entities(initial_entities)

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        instance = str(discovery["instance"])

        # AC_LOAD_STATUS messages arrive classified as 'sensor'; feed the
        # Aqua-Hot switches their live state (including shed detection).
        if (
            discovery["type"] == "sensor"
            and str(discovery.get("name", "")).startswith("AC_LOAD_STATUS")
            and instance in acload_entities
        ):
            acload_entities[instance].handle_mqtt(discovery["payload"])
            return

        if discovery["type"] != "light":
            return

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


class RVCAcLoadSwitch(AvailabilityMixin, RestoreEntity, SwitchEntity):
    """Energy-managed AC load (Aqua-Hot electric element / diesel burner).

    Commands go to the thermostat/AC-load bridge as AC_LOAD_COMMAND (0x1FFBE):
    OFF latches; ON is a request the Firefly energy manager may shed. State
    comes from AC_LOAD_STATUS (0x1FFBF): byte 2 level 0xC8=on, 0x00=off,
    0xFC/0xFD=requested-but-shed (shown via the 'shed' attribute).
    Only created when Thermostat bridge mode is enabled.
    """

    def __init__(self, name: str, instance_id: str, availability_timeout: int) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False
        self._instance = instance_id
        self._attr_is_on = False
        self._attr_assumed_state = False
        self._attr_icon = "mdi:water-boiler"
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "shed": False,
            "level_raw": None,
            "last_mqtt_update": None,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in ("on", "off"):
            self._attr_is_on = last_state.state == "on"

    @property
    def unique_id(self) -> str:
        return f"rvc_acload_{self._instance}"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "aqua_hot")},
            name="Aqua-Hot",
            manufacturer="RV-C",
            model="Hydronic Heater (AC loads)",
            via_device=(DOMAIN, "main_controller"),
        )

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        self.mark_seen_now()
        attrs = self._attr_extra_state_attributes

        level = None
        data_hex = payload.get("data")
        if isinstance(data_hex, str) and len(data_hex) >= 6:
            try:
                level = bytes.fromhex(data_hex[:6])[2]
            except ValueError:
                level = None
        if level is None:
            try:
                level = int(float(payload.get("operating status", "")))
            except (TypeError, ValueError):
                level = None

        if level is not None:
            attrs["level_raw"] = level
            shed = level in (0xFC, 0xFD)
            attrs["shed"] = shed
            self._attr_is_on = shed or level > 0

        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]
        self.async_write_ha_state()

    async def _async_publish_acload(self, state: str) -> None:
        await mqtt.async_publish(
            self.hass,
            f"{DEFAULT_ACLOAD_BRIDGE_TOPIC}/{int(self._instance)}",
            json.dumps({"state": state}),
            qos=0,
            retain=False,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_publish_acload("on")
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_publish_acload("off")
        self._attr_is_on = False
        self.async_write_ha_state()
