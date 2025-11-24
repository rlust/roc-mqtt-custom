"""Platform for RV-C awning covers using Node-RED MQTT format."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass,
)
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_DISCOVERY,
    AWNING_DEFINITIONS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C covers - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCAwning] = {}
    topic_prefix = entry.data.get("topic_prefix", "rvc")

    _LOGGER.info(
        "Pre-creating %d awning cover entities from mappings",
        len(AWNING_DEFINITIONS),
    )

    initial_entities = []
    for awning_id, awning_config in AWNING_DEFINITIONS.items():
        entity = RVCAwning(
            name=awning_config["name"],
            awning_id=awning_id,
            extend_instance=awning_config["extend"],
            retract_instance=awning_config["retract"],
            stop_instance=awning_config["stop"],
            topic_prefix=topic_prefix,
        )
        entities[awning_id] = entity
        initial_entities.append(entity)
        _LOGGER.debug(
            "Pre-created awning entity: id=%s, name='%s', extend=%s, retract=%s, stop=%s",
            awning_id, awning_config["name"],
            awning_config["extend"], awning_config["retract"], awning_config["stop"]
        )

    # Add all pre-created entities at once
    async_add_entities(initial_entities)
    _LOGGER.info("Successfully added %d awning cover entities", len(initial_entities))

    # Discovery callback handles MQTT updates
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":  # Awnings use DC_DIMMER_STATUS messages
            return

        instance = discovery["instance"]
        inst_str = str(instance)
        payload = discovery["payload"]

        # Check if this instance belongs to any awning
        for awning_id, entity in entities.items():
            if inst_str in [entity._extend_instance, entity._retract_instance, entity._stop_instance]:
                entity.handle_mqtt(inst_str, payload)
                break

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCAwning(CoverEntity):
    """Representation of an RV-C awning cover."""

    def __init__(
        self,
        name: str,
        awning_id: str,
        extend_instance: str,
        retract_instance: str,
        stop_instance: str,
        topic_prefix: str,
    ) -> None:
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._awning_id = awning_id
        self._extend_instance = extend_instance
        self._retract_instance = retract_instance
        self._stop_instance = stop_instance
        self._topic_prefix = topic_prefix

        # Cover attributes
        self._attr_device_class = CoverDeviceClass.AWNING
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE |
            CoverEntityFeature.STOP
        )

        # State tracking
        self._attr_is_closed = True  # Default to retracted
        self._attr_is_closing = False
        self._attr_is_opening = False
        self._attr_available = True
        self._attr_assumed_state = True  # Until MQTT confirms
        self._last_update_time: float | None = None

        # Store instance numbers as extra state attributes
        self._attr_extra_state_attributes = {
            "rvc_awning_id": awning_id,
            "rvc_extend_instance": extend_instance,
            "rvc_retract_instance": retract_instance,
            "rvc_stop_instance": stop_instance,
            "rvc_topic_prefix": topic_prefix,
            "last_command": None,
            "last_mqtt_update": None,
        }

        _LOGGER.info(
            "Initialized RVCAwning: name='%s', extend=%s, retract=%s, stop=%s",
            name, extend_instance, retract_instance, stop_instance
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_awning_{self._awning_id}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._attr_available

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, "awning_system")},
            name="RVC Awning System",
            manufacturer="RV-C",
            model="Awning Controller",
            via_device=(DOMAIN, "main_controller"),
        )

    @property
    def _command_topic(self) -> str:
        # Node-RED format: single topic for all commands
        return "node-red/rvc/commands"

    def handle_mqtt(self, instance: str, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        _LOGGER.debug(
            "Awning %s received MQTT payload for instance %s: %s",
            self._awning_id, instance, payload
        )

        # Disable assumed_state on first MQTT message
        if self._attr_assumed_state:
            _LOGGER.info(
                "Awning %s received first MQTT status - state now confirmed",
                self._awning_id
            )
            self._attr_assumed_state = False

        # Track last update time
        self._last_update_time = time.time()

        # Determine state from brightness/operating status
        if "operating status (brightness)" in payload:
            try:
                brightness = float(payload["operating status (brightness)"])
                # If extend instance is active (>0), awning is extending/extended
                if instance == self._extend_instance:
                    if brightness > 0:
                        self._attr_is_opening = True
                        self._attr_is_closing = False
                    else:
                        self._attr_is_opening = False
                # If retract instance is active (>0), awning is retracting/retracted
                elif instance == self._retract_instance:
                    if brightness > 0:
                        self._attr_is_closing = True
                        self._attr_is_opening = False
                    else:
                        self._attr_is_closing = False
            except (TypeError, ValueError):
                pass

        # Capture diagnostic attributes
        attrs = self._attr_extra_state_attributes

        if "last command definition" in payload:
            attrs["last_command"] = payload["last command definition"]
        elif "last command" in payload:
            attrs["last_command"] = f"Code {payload['last command']}"

        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]

        self.async_write_ha_state()

    async def async_open_cover(self, **kwargs: Any) -> None:
        """Extend the awning."""
        self._attr_is_opening = True
        self._attr_is_closing = False
        self._attr_is_closed = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (extend)
        instance = int(self._extend_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Awning %s extending: publishing to %s: '%s'",
            self._awning_id, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        """Retract the awning."""
        self._attr_is_closing = True
        self._attr_is_opening = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (retract)
        instance = int(self._retract_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Awning %s retracting: publishing to %s: '%s'",
            self._awning_id, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        """Stop the awning."""
        self._attr_is_opening = False
        self._attr_is_closing = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (stop - momentary)
        instance = int(self._stop_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Awning %s stopping: publishing to %s: '%s'",
            self._awning_id, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()
