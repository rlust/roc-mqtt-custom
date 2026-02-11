"""Platform for RV-C door locks using Node-RED MQTT format."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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
    LOCK_DEFINITIONS,
)

_LOGGER = logging.getLogger(__name__)


def _get_entry_option(entry: ConfigEntry, key: str, default: Any) -> Any:
    """Helper to read config values from options first, then data."""
    return entry.options.get(key, entry.data.get(key, default))


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return fallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C locks - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLock] = {}
    topic_prefix = _get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    command_topic = _get_entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
    availability_timeout = _coerce_int(
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT),
        DEFAULT_AVAILABILITY_TIMEOUT,
    )

    _LOGGER.info(
        "Pre-creating %d lock entities from mappings",
        len(LOCK_DEFINITIONS),
    )

    initial_entities = []
    for lock_id, lock_config in LOCK_DEFINITIONS.items():
        entity = RVCLock(
            name=lock_config["name"],
            lock_id=lock_id,
            lock_instance=lock_config["lock"],
            unlock_instance=lock_config["unlock"],
            topic_prefix=topic_prefix,
            command_topic=command_topic,
            availability_timeout=availability_timeout,
        )
        entities[lock_id] = entity
        initial_entities.append(entity)
        _LOGGER.debug(
            "Pre-created lock entity: id=%s, name='%s', lock=%s, unlock=%s",
            lock_id, lock_config["name"],
            lock_config["lock"], lock_config["unlock"]
        )

    # Add all pre-created entities at once
    async_add_entities(initial_entities)
    _LOGGER.info("Successfully added %d lock entities", len(initial_entities))

    # Discovery callback handles MQTT updates
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":  # Locks use DC_DIMMER_STATUS messages
            return

        instance = discovery["instance"]
        inst_str = str(instance)
        payload = discovery["payload"]

        # Check if this instance belongs to any lock
        for lock_id, entity in entities.items():
            if inst_str in [entity._lock_instance, entity._unlock_instance]:
                entity.handle_mqtt(inst_str, payload)
                break

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCLock(AvailabilityMixin, LockEntity):
    """Representation of an RV-C door lock."""

    def __init__(
        self,
        name: str,
        lock_id: str,
        lock_instance: str,
        unlock_instance: str,
        topic_prefix: str,
        command_topic: str,
        availability_timeout: int,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._lock_id = lock_id
        self._lock_instance = lock_instance
        self._unlock_instance = unlock_instance
        self._topic_prefix = topic_prefix
        self._command_topic = command_topic
        self._attr_is_locked = True  # Default to locked

        # Availability and state tracking
        self._attr_assumed_state = True  # Show uncertainty until MQTT confirms

        # Store instance numbers as extra state attributes
        self._attr_extra_state_attributes = {
            "rvc_lock_id": lock_id,
            "rvc_lock_instance": lock_instance,
            "rvc_unlock_instance": unlock_instance,
            "rvc_topic_prefix": topic_prefix,
            "last_command": None,
            "load_status": None,
            "last_mqtt_update": None,
        }

        _LOGGER.info(
            "Initialized RVCLock: name='%s', lock=%s, unlock=%s",
            name, lock_instance, unlock_instance
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_lock_{self._lock_id}"

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

    def handle_mqtt(self, instance: str, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        _LOGGER.debug(
            "Lock %s received MQTT payload for instance %s: %s",
            self._lock_id, instance, payload
        )

        # Disable assumed_state on first MQTT message
        if self._attr_assumed_state:
            _LOGGER.info(
                "Lock %s received first MQTT status - state now confirmed",
                self._lock_id
            )
            self._attr_assumed_state = False

        # Track last update time
        self.mark_seen_now()

        # Determine lock state from which instance is active
        # Lock instance active = locked, Unlock instance active = unlocked
        if "operating status (brightness)" in payload:
            try:
                brightness = float(payload["operating status (brightness)"])
                if instance == self._lock_instance and brightness > 0:
                    self._attr_is_locked = True
                elif instance == self._unlock_instance and brightness > 0:
                    self._attr_is_locked = False
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
        # Fire lock instance with command 2 (ON) - momentary trigger
        instance = int(self._lock_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Lock %s locking: publishing to %s: '%s'",
            self._lock_id, self._command_topic, payload
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
        # Fire unlock instance with command 2 (ON) - momentary trigger
        instance = int(self._unlock_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Lock %s unlocking: publishing to %s: '%s'",
            self._lock_id, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()
