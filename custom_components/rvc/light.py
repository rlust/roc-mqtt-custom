"""Platform for RV-C lights using Node-RED MQTT format."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .availability import AvailabilityMixin
from .const import (
    CONF_AVAILABILITY_TIMEOUT,
    CONF_COMMAND_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_LIGHT_AVAILABILITY_TIMEOUT,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
    DIMMER_INSTANCE_LABELS,
    DIMMABLE_LIGHTS,
    LIVING_AREA_LIGHTS,
    BEDROOM_AREA_LIGHTS,
    BATHROOM_AREA_LIGHTS,
    EXTERIOR_AREA_LIGHTS,
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


def _duration_schema(min_seconds: int = 1, max_seconds: int = 60) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("duration"): vol.All(
                vol.Coerce(int),
                vol.Range(min=min_seconds, max=max_seconds),
            )
        }
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C lights - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLight] = {}
    topic_prefix = _get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    command_topic = _get_entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
    availability_timeout = _coerce_int(
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_LIGHT_AVAILABILITY_TIMEOUT),
        DEFAULT_LIGHT_AVAILABILITY_TIMEOUT,
    )

    # Pre-create all mapped light entities from const.py mappings
    # They will start as "unavailable" and become available when MQTT messages arrive
    all_light_instances = dict(DIMMER_INSTANCE_LABELS)

    _LOGGER.info(
        "Pre-creating %d dimmer light entities from mappings",
        len(all_light_instances),
    )

    initial_entities = []
    for inst_str, name in all_light_instances.items():
        entity = RVCLight(
            name=name,
            instance_id=inst_str,
            topic_prefix=topic_prefix,
            command_topic=command_topic,
            availability_timeout=availability_timeout,
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
                command_topic=command_topic,
                availability_timeout=availability_timeout,
            )
            entities[inst_str] = entity
            async_add_entities([entity])

        # Update entity state from MQTT payload
        entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)

    platform = entity_platform.async_get_current_platform()
    duration_schema = _duration_schema()
    platform.async_register_entity_service("ramp_up", duration_schema, "async_ramp_up")
    platform.async_register_entity_service("ramp_down", duration_schema, "async_ramp_down")


class RVCLight(AvailabilityMixin, RestoreEntity, LightEntity):
    """Representation of an RV-C dimmer light (dimmable or relay-only)."""

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
        self._attr_has_entity_name = False  # Use our name as-is, not combined with device name
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._command_topic = command_topic
        self._attr_is_on = False
        self._attr_brightness = 255

        # Entities start with assumed state until MQTT confirms
        self._attr_assumed_state = True  # Show dashed circle until MQTT arrives

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
            "command_topic": command_topic,
            "availability_timeout": availability_timeout,
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

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        if last_state.state in (STATE_ON, STATE_OFF):
            self._attr_is_on = last_state.state == STATE_ON

        restored_brightness = last_state.attributes.get(ATTR_BRIGHTNESS)
        if restored_brightness is not None:
            try:
                self._attr_brightness = int(restored_brightness)
            except (TypeError, ValueError):
                pass

    @property
    def unique_id(self) -> str:
        return f"rvc_light_{self._instance}"

    # Availability handled by AvailabilityMixin

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities by area."""
        # Determine device grouping by area
        if self._instance in LIVING_AREA_LIGHTS:
            device_id = "living_area_lights"
            device_name = "Living Area Lights"
            model = "Living Area Lighting"
        elif self._instance in BEDROOM_AREA_LIGHTS:
            device_id = "bedroom_area_lights"
            device_name = "Bedroom Area Lights"
            model = "Bedroom Lighting"
        elif self._instance in BATHROOM_AREA_LIGHTS:
            device_id = "bathroom_area_lights"
            device_name = "Bathroom Area Lights"
            model = "Bathroom Lighting"
        elif self._instance in EXTERIOR_AREA_LIGHTS:
            device_id = "exterior_area_lights"
            device_name = "Exterior Lights"
            model = "Exterior Lighting"
        else:
            # Fallback for unmapped lights
            device_id = "other_lights"
            device_name = "Other Lights"
            model = "Miscellaneous Lighting"

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

    # Command topic set per entity from config options

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
        self.mark_seen_now()

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

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON
        instance = int(self._instance)
        command = 2

        if self._is_dimmable:
            # Dimmable lights: use brightness from kwargs or current value
            brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
            brightness = max(0, min(255, int(brightness)))
            self._attr_brightness = brightness

            # Convert HA brightness (0-255) to RV-C level (0-100)
            desired_level = int(round(brightness / 2.55))
            desired_level = max(1, min(100, desired_level))  # Ensure at least 1

            payload = f"{instance} {command} {desired_level}"

            _LOGGER.info(
                "Light %s (%s) turning ON with dimming: brightness=%d%%, publishing to %s: '%s'",
                self._instance, self._attr_name, desired_level, self._command_topic, payload
            )
        else:
            # Non-dimmable (relay) lights: always full brightness
            payload = f"{instance} {command} 100"

            _LOGGER.info(
                "Light %s (%s) turning ON (relay): publishing to %s: '%s'",
                self._instance, self._attr_name, self._command_topic, payload
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

        _LOGGER.info(
            "Light %s (%s) turning OFF: publishing to %s: '%s'",
            self._instance, self._attr_name, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_ramp_up(self, duration: int) -> None:
        """Ramp the light up over the requested duration."""
        await self._async_send_ramp_command(duration, 19)

    async def async_ramp_down(self, duration: int) -> None:
        """Ramp the light down over the requested duration."""
        await self._async_send_ramp_command(duration, 20)

    async def _async_send_ramp_command(self, duration: int, command: int) -> None:
        duration_int = max(1, min(60, int(duration)))
        instance = int(self._instance)
        payload = f"{instance} {command} {duration_int}"
        _LOGGER.info(
            "Light %s (%s) ramp command %s for %ss: publishing to %s: '%s'",
            self._instance,
            self._attr_name,
            command,
            duration_int,
            self._command_topic,
            payload,
        )
        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )
