"""Platform for RV-C door locks using Node-RED MQTT format."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_DISCOVERY,
    LOCK_INSTANCE_LABELS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C locks - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLock] = {}
    topic_prefix = entry.data.get("topic_prefix", "rvc")

    _LOGGER.info(
        "Pre-creating %d lock entities from mappings",
        len(LOCK_INSTANCE_LABELS),
    )

    initial_entities = []
    for inst_str, name in LOCK_INSTANCE_LABELS.items():
        entity = RVCLock(
            name=name,
            instance_id=inst_str,
            topic_prefix=topic_prefix,
        )
        entities[inst_str] = entity
        initial_entities.append(entity)
        _LOGGER.debug("Pre-created lock entity: instance=%s, name='%s'", inst_str, name)

    # Add all pre-created entities at once
    async_add_entities(initial_entities)
    _LOGGER.info("Successfully added %d lock entities", len(initial_entities))

    # Discovery callback handles MQTT updates and any unmapped instances
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":  # Locks use same DC_DIMMER_STATUS messages
            return

        instance = discovery["instance"]
        inst_str = str(instance)

        # Only process if this is a lock instance
        if inst_str not in LOCK_INSTANCE_LABELS:
            return

        payload = discovery["payload"]
        entity = entities.get(inst_str)

        if entity is not None:
            # Update entity state from MQTT payload
            entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCLock(LockEntity):
    """Representation of an RV-C door lock."""

    def __init__(self, name: str, instance_id: str, topic_prefix: str) -> None:
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_is_locked = True  # Default to locked

        # Availability and state tracking
        self._attr_available = True  # Allow immediate control
        self._attr_assumed_state = True  # Show uncertainty until MQTT confirms
        self._last_update_time: float | None = None

        # Store instance number as extra state attribute
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "rvc_topic_prefix": topic_prefix,
            "last_command": None,
            "load_status": None,
            "last_mqtt_update": None,
        }

        _LOGGER.info(
            "Initialized RVCLock: name='%s', instance=%s",
            name, instance_id
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_lock_{self._instance}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._attr_available

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, "door_system")},
            name="RVC Door System",
            manufacturer="RV-C",
            model="Door Lock Controller",
            via_device=(DOMAIN, "main_controller"),
        )

    @property
    def _command_topic(self) -> str:
        # Node-RED format: single topic for all commands
        return "node-red/rvc/commands"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        _LOGGER.debug(
            "Lock %s received MQTT payload: %s",
            self._instance, payload
        )

        # Disable assumed_state on first MQTT message
        if self._attr_assumed_state:
            _LOGGER.info(
                "Lock %s received first MQTT status - state now confirmed",
                self._instance
            )
            self._attr_assumed_state = False

        # Track last update time
        self._last_update_time = time.time()

        # Determine lock state from brightness/operating status
        # 0 = locked, >0 = unlocked
        if "operating status (brightness)" in payload:
            try:
                brightness = float(payload["operating status (brightness)"])
                self._attr_is_locked = brightness == 0
            except (TypeError, ValueError):
                pass

        # Capture diagnostic attributes
        attrs = self._attr_extra_state_attributes

        if "last command definition" in payload:
            attrs["last_command"] = payload["last command definition"]
        elif "last command" in payload:
            attrs["last_command"] = f"Code {payload['last command']}"

        if "load status definition" in payload:
            attrs["load_status"] = payload["load status definition"]

        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]

        self.async_write_ha_state()

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the door."""
        self._attr_is_locked = True

        # Node-RED format: "instance command brightness"
        # Command 3 = Turn OFF (lock)
        instance = int(self._instance)
        command = 3
        brightness = 0
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Lock %s locking: publishing to %s: '%s'",
            self._instance, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the door."""
        self._attr_is_locked = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (unlock)
        instance = int(self._instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Lock %s unlocking: publishing to %s: '%s'",
            self._instance, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()
