"""Platform for RV-C lights using Node-RED MQTT format."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
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
    DIMMER_INSTANCE_LABELS,
    SWITCH_INSTANCE_LABELS,
    DIMMABLE_LIGHTS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C lights - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLight] = {}
    topic_prefix = entry.data.get("topic_prefix", "rvc")

    # Pre-create all mapped light entities from const.py mappings
    # They will start as "unavailable" and become available when MQTT messages arrive
    all_light_instances = {**DIMMER_INSTANCE_LABELS, **SWITCH_INSTANCE_LABELS}

    _LOGGER.info(
        "Pre-creating %d light entities from mappings (dimmers: %d, switches: %d)",
        len(all_light_instances),
        len(DIMMER_INSTANCE_LABELS),
        len(SWITCH_INSTANCE_LABELS),
    )

    initial_entities = []
    for inst_str, name in all_light_instances.items():
        entity = RVCLight(
            name=name,
            instance_id=inst_str,
            topic_prefix=topic_prefix,
        )
        entities[inst_str] = entity
        initial_entities.append(entity)
        _LOGGER.debug("Pre-created light entity: instance=%s, name='%s'", inst_str, name)

    # Add all pre-created entities at once
    async_add_entities(initial_entities)
    _LOGGER.info("Successfully added %d light entities", len(initial_entities))

    # Discovery callback handles MQTT updates and any unmapped instances
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)

        entity = entities.get(inst_str)
        if entity is None:
            # Unmapped instance - create it dynamically
            name = payload.get("name") or f"RVC Light {inst_str}"
            _LOGGER.info(
                "Discovered unmapped light instance %s (name='%s') - creating dynamically",
                inst_str, name
            )
            entity = RVCLight(
                name=name,
                instance_id=inst_str,
                topic_prefix=topic_prefix,
            )
            entities[inst_str] = entity
            async_add_entities([entity])

        # Update entity state from MQTT payload
        entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCLight(LightEntity):
    """Representation of an RV-C dimmer light (dimmable or relay-only)."""

    def __init__(self, name: str, instance_id: str, topic_prefix: str) -> None:
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is, not combined with device name
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_is_on = False
        self._attr_brightness = 255

        # Availability and state tracking
        # Entities start as "available" but with "assumed_state" until MQTT confirms
        self._attr_available = True  # Allow immediate control
        self._attr_assumed_state = True  # Show dashed circle until MQTT arrives
        self._last_update_time: float | None = None

        # Determine if this is a dimmable light or relay-only
        self._is_dimmable = instance_id in DIMMABLE_LIGHTS

        # Set color mode based on dimmable capability
        if self._is_dimmable:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        # Store instance number and type as extra state attributes
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "rvc_type": "dimmable" if self._is_dimmable else "relay",
            "rvc_topic_prefix": topic_prefix,
            "last_command": None,
            "load_status": None,
            "enable_status": None,
            "interlock_status": None,
            "group_bits": None,
            "last_mqtt_update": None,
        }

        _LOGGER.info(
            "Initialized RVCLight: name='%s', instance=%s, dimmable=%s",
            name, instance_id, self._is_dimmable
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_light_{self._instance}"

    @property
    def available(self) -> bool:
        """Return True if entity is available.

        Entities are always available for control, but use assumed_state
        to indicate uncertainty until first MQTT status message arrives.
        """
        return self._attr_available

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities."""
        # Determine device grouping by instance range and type
        instance_num = int(self._instance)

        if self._is_dimmable:
            # Dimmable lights (instances 25-35)
            device_id = "dimmer_module"
            device_name = "RVC Dimmer Module"
            model = "DC Dimmer Controller"
        else:
            # Relay lights (instances 36+)
            device_id = "relay_module"
            device_name = "RVC Relay Module"
            model = "DC Relay Controller"

        return DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="RV-C",
            model=model,
            via_device=(DOMAIN, "main_controller"),
        )

    @property
    def icon(self) -> str:
        """Return icon based on light name."""
        name = self._attr_name.lower()

        if "accent" in name:
            return "mdi:lightbulb-spot"
        elif "ceiling" in name:
            return "mdi:ceiling-light"
        elif "security" in name or "motion" in name:
            return "mdi:security"
        elif "awning" in name:
            return "mdi:awning-outline"
        elif "porch" in name:
            return "mdi:porch-light"
        elif "vanity" in name or "lav" in name:
            return "mdi:vanity-light"
        elif "reading" in name:
            return "mdi:book-open-page-variant"
        elif "cargo" in name:
            return "mdi:garage"
        elif "slide" in name:
            return "mdi:wall-sconce-flat"
        else:
            return "mdi:lightbulb"

    @property
    def _command_topic(self) -> str:
        # Node-RED format: single topic for all light commands
        return "node-red/rvc/commands"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload.

        Supports both:
        - Raw RV-C JSON (with 'operating status (brightness)')
        - Simplified payloads with 'state' and 'brightness'
        """
        _LOGGER.debug(
            "Light %s received MQTT payload: %s",
            self._instance, payload
        )

        # Disable assumed_state on first MQTT message
        # Entity transitions from "assumed" (dashed circle) to "known" (normal icon)
        if self._attr_assumed_state:
            _LOGGER.info(
                "Light %s received first MQTT status - state now confirmed (no longer assumed)",
                self._instance
            )
            self._attr_assumed_state = False

        # Track last update time for availability monitoring
        self._last_update_time = time.time()

        # Raw RV-C dimmer payload: "operating status (brightness)" 0–100
        if "operating status (brightness)" in payload:
            try:
                pct = float(payload["operating status (brightness)"])
                pct = max(0.0, min(100.0, pct))
                self._attr_brightness = int(round(pct * 2.55))
            except (TypeError, ValueError):
                pass

            # Consider >0 brightness as ON
            self._attr_is_on = self._attr_brightness > 0

        # Optional explicit 'state'
        if "state" in payload:
            state_str = str(payload["state"]).upper()
            if state_str in ("ON", "OFF"):
                self._attr_is_on = state_str == "ON"

        # Optional direct brightness 0–255
        if "brightness" in payload:
            try:
                self._attr_brightness = int(payload["brightness"])
            except (TypeError, ValueError):
                pass

        # DO NOT override the name from payload - we use our mapped names from DIMMER_INSTANCE_LABELS

        # Capture diagnostic attributes from RV-C payload
        attrs = self._attr_extra_state_attributes

        # Last command executed
        if "last command definition" in payload:
            attrs["last_command"] = payload["last command definition"]
        elif "last command" in payload:
            # Fallback to numeric code if definition not available
            attrs["last_command"] = f"Code {payload['last command']}"

        # Load status (electrical load state)
        if "load status definition" in payload:
            attrs["load_status"] = payload["load status definition"]

        # Enable status (if light is enabled/disabled)
        if "enable status definition" in payload:
            attrs["enable_status"] = payload["enable status definition"]

        # Interlock status (safety interlock)
        if "interlock status definition" in payload:
            attrs["interlock_status"] = payload["interlock status definition"]

        # Group membership (for scene control)
        if "group" in payload:
            attrs["group_bits"] = payload["group"]

        # Timestamp for diagnostics and availability tracking
        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on using Node-RED format."""

        self._attr_is_on = True

        # Get brightness from kwargs or use current/default
        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        brightness = max(0, min(255, int(brightness)))
        self._attr_brightness = brightness

        # Convert HA brightness (0-255) to RV-C level (0-100)
        desired_level = int(round(brightness / 2.55))
        desired_level = max(1, min(100, desired_level))  # Ensure at least 1

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON
        instance = int(self._instance)
        command = 2
        payload = f"{instance} {command} {desired_level}"

        _LOGGER.debug(
            "Light %s turning ON: brightness=%d%%, publishing to %s: '%s'",
            self._instance, desired_level, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off using Node-RED format."""

        self._attr_is_on = False
        self._attr_brightness = 0

        # Node-RED format: "instance command brightness"
        # Command 3 = Turn OFF
        instance = int(self._instance)
        command = 3
        brightness = 0
        payload = f"{instance} {command} {brightness}"

        _LOGGER.debug(
            "Light %s turning OFF: publishing to %s: '%s'",
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
