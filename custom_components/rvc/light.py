"""Platform for RV-C lights using Node-RED MQTT format."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_DISCOVERY,
    DIMMER_INSTANCE_LABELS,
    DIMMABLE_LIGHTS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C lights dynamically from discovery events."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLight] = {}

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)

        # Prefer your dimmer mapping; fall back to payload name; then generic
        label = DIMMER_INSTANCE_LABELS.get(inst_str)
        name = label or payload.get("name") or f"RVC Light {inst_str}"

        entity = entities.get(inst_str)
        if entity is None:
            _LOGGER.debug(
                "Creating new light entity: instance=%s, name='%s', label='%s'",
                inst_str, name, label
            )
            entity = RVCLight(
                name=name,
                instance_id=inst_str,
                topic_prefix=entry.data.get("topic_prefix", "rvc"),
            )
            entities[inst_str] = entity
            async_add_entities([entity])
        else:
            _LOGGER.debug("Updating existing light entity: instance=%s", inst_str)

        entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCLight(LightEntity):
    """Representation of an RV-C dimmer light (dimmable or relay-only)."""

    def __init__(self, name: str, instance_id: str, topic_prefix: str) -> None:
        self._attr_name = name
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_is_on = False
        self._attr_brightness = 255

        # Determine if this is a dimmable light or relay-only
        self._is_dimmable = instance_id in DIMMABLE_LIGHTS

        # Set color mode based on dimmable capability
        if self._is_dimmable:
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
            self._attr_color_mode = ColorMode.BRIGHTNESS
        else:
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        _LOGGER.info(
            "Initialized RVCLight: name='%s', instance=%s, dimmable=%s",
            name, instance_id, self._is_dimmable
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_light_{self._instance}"

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

        # Optional human-readable name override
        if "name" in payload:
            self._attr_name = str(payload["name"])

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
