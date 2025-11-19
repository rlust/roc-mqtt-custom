"""Platform for RV-C lights."""
from __future__ import annotations

import json
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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_DISCOVERY,
    DIMMER_INSTANCE_LABELS,
    DIMMABLE_LIGHTS,
    CC_SET_BRIGHTNESS,
    CC_ON_DELAY,
    CC_OFF,
    CC_RAMP_UP,
    CC_RAMP_DOWN,
    CC_STOP,
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

    # Register custom services
    platform = entity_platform.async_get_current_platform()

    platform.async_register_entity_service(
        "ramp_up",
        {
            "duration": {
                "type": int,
                "required": True,
                "min": 1,
                "max": 60,
            }
        },
        "async_ramp_up",
    )

    platform.async_register_entity_service(
        "ramp_down",
        {
            "duration": {
                "type": int,
                "required": True,
                "min": 1,
                "max": 60,
            }
        },
        "async_ramp_down",
    )


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
            "Initialized RVCLight: name='%s', instance=%s, dimmable=%s, topic_prefix='%s'",
            name, instance_id, self._is_dimmable, topic_prefix
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_light_{self._instance}"

    @property
    def _command_topic(self) -> str:
        # Use configured topic prefix (case-sensitive)
        # NOTE: No /set suffix - RV-C MQTT bridge expects direct topic
        return f"{self._topic_prefix}/DC_DIMMER_COMMAND_2/{self._instance}"

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
        """Turn the light on (with optional brightness for dimmable lights)."""

        self._attr_is_on = True

        if self._is_dimmable:
            # Dimmable light: use command 0 with desired level
            brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
            brightness = max(0, min(255, int(brightness)))
            self._attr_brightness = brightness

            # Convert HA brightness (0-255) to RV-C desired level (0-100)
            desired_level = int(round(brightness / 2.55))
            desired_level = max(0, min(100, desired_level))

            # Match exact payload format from RVC_PROJECT_NOTES.md
            payload = {
                "command": CC_SET_BRIGHTNESS,  # 0: Set Brightness
                "command definition": "set brightness",
                "delay/duration": 255,  # 255 = immediate/max
                "desired level": desired_level,  # 0–100
                "dgn": "1FEDB",
                "group": "11111111",  # All groups
                "instance": int(self._instance),
                "interlock": "00",  # No interlock
                "interlock definition": "no interlock active",
                "name": "DC_DIMMER_COMMAND_2",
                "timestamp": f"{time.time():.6f}",
            }

            _LOGGER.debug(
                "Dimmable light %s turning ON: desired_level=%d (HA=%d), publishing to %s: %s",
                self._instance, desired_level, brightness, self._command_topic, payload
            )
        else:
            # Non-dimmable (relay): use command 2 (on delay) with full brightness
            # Match exact payload format from RVC_PROJECT_NOTES.md
            payload = {
                "command": CC_ON_DELAY,  # 2: On (Delay)
                "command definition": "on delay",
                "delay/duration": 255,  # 255 = immediate/max
                "desired level": 100,  # Always full for relays
                "dgn": "1FEDB",
                "group": "11111111",  # All groups
                "instance": int(self._instance),
                "interlock": "00",  # No interlock
                "interlock definition": "no interlock active",
                "name": "DC_DIMMER_COMMAND_2",
                "timestamp": f"{time.time():.6f}",
            }

            _LOGGER.debug(
                "Relay light %s turning ON (non-dimmable), publishing to %s: %s",
                self._instance, self._command_topic, payload
            )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""

        self._attr_is_on = False
        self._attr_brightness = 0

        # Match exact payload format from RVC_PROJECT_NOTES.md
        payload = {
            "command": CC_OFF,  # 3: Off
            "command definition": "off",
            "delay/duration": 255,  # 255 = immediate/max
            "desired level": 0,  # 0 for off
            "dgn": "1FEDB",
            "group": "11111111",  # All groups
            "instance": int(self._instance),
            "interlock": "00",  # No interlock
            "interlock definition": "no interlock active",
            "name": "DC_DIMMER_COMMAND_2",
            "timestamp": f"{time.time():.6f}",
        }

        _LOGGER.debug(
            "Light %s turning OFF: publishing to %s: %s",
            self._instance, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_ramp_up(self, duration: int = 5) -> None:
        """Ramp brightness up over specified duration."""
        # Match exact payload format from RVC_PROJECT_NOTES.md
        payload = {
            "command": CC_RAMP_UP,  # 19: Ramp Up
            "command definition": "ramp up",
            "delay/duration": duration,  # Use specified duration
            "desired level": 100,  # Ramp to full
            "dgn": "1FEDB",
            "group": "11111111",  # All groups
            "instance": int(self._instance),
            "interlock": "00",  # No interlock
            "interlock definition": "no interlock active",
            "name": "DC_DIMMER_COMMAND_2",
            "timestamp": f"{time.time():.6f}",
        }

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

    async def async_ramp_down(self, duration: int = 5) -> None:
        """Ramp brightness down over specified duration."""
        # Match exact payload format from RVC_PROJECT_NOTES.md
        payload = {
            "command": CC_RAMP_DOWN,  # 20: Ramp Down
            "command definition": "ramp down",
            "delay/duration": duration,  # Use specified duration
            "desired level": 0,  # Ramp to off
            "dgn": "1FEDB",
            "group": "11111111",  # All groups
            "instance": int(self._instance),
            "interlock": "00",  # No interlock
            "interlock definition": "no interlock active",
            "name": "DC_DIMMER_COMMAND_2",
            "timestamp": f"{time.time():.6f}",
        }

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )
