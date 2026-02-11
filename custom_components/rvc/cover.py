"""Platform for RV-C awning and slide covers using Node-RED MQTT format."""
from __future__ import annotations

import logging
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
    AWNING_DEFINITIONS,
    SLIDE_DEFINITIONS,
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
    """Set up RV-C covers - pre-create all mapped entities on startup."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, CoverEntity] = {}
    topic_prefix = _get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)
    command_topic = _get_entry_option(entry, CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
    availability_timeout = _coerce_int(
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT),
        DEFAULT_AVAILABILITY_TIMEOUT,
    )

    initial_entities = []

    # Create awning entities
    _LOGGER.info(
        "Pre-creating %d awning cover entities from mappings",
        len(AWNING_DEFINITIONS),
    )

    for awning_id, awning_config in AWNING_DEFINITIONS.items():
        entity = RVCAwning(
            name=awning_config["name"],
            awning_id=awning_id,
            extend_instance=awning_config["extend"],
            retract_instance=awning_config["retract"],
            stop_instance=awning_config["stop"],
            topic_prefix=topic_prefix,
            command_topic=command_topic,
            availability_timeout=availability_timeout,
        )
        entities[f"awning_{awning_id}"] = entity
        initial_entities.append(entity)
        _LOGGER.debug(
            "Pre-created awning entity: id=%s, name='%s', extend=%s, retract=%s, stop=%s",
            awning_id, awning_config["name"],
            awning_config["extend"], awning_config["retract"], awning_config["stop"]
        )

    # Create slide entities
    _LOGGER.info(
        "Pre-creating %d slide cover entities from mappings",
        len(SLIDE_DEFINITIONS),
    )

    for slide_id, slide_config in SLIDE_DEFINITIONS.items():
        entity = RVCSlide(
            name=slide_config["name"],
            slide_id=slide_id,
            extend_instance=slide_config["extend"],
            retract_instance=slide_config["retract"],
            topic_prefix=topic_prefix,
            command_topic=command_topic,
            availability_timeout=availability_timeout,
        )
        entities[f"slide_{slide_id}"] = entity
        initial_entities.append(entity)
        _LOGGER.debug(
            "Pre-created slide entity: id=%s, name='%s', extend=%s, retract=%s",
            slide_id, slide_config["name"],
            slide_config["extend"], slide_config["retract"]
        )

    # Add all pre-created entities at once
    async_add_entities(initial_entities)
    _LOGGER.info(
        "Successfully added %d cover entities (%d awnings, %d slides)",
        len(initial_entities), len(AWNING_DEFINITIONS), len(SLIDE_DEFINITIONS)
    )

    # Discovery callback handles MQTT updates
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":  # Covers use DC_DIMMER_STATUS messages
            return

        instance = discovery["instance"]
        inst_str = str(instance)
        payload = discovery["payload"]

        # Check if this instance belongs to any cover entity
        for entity_id, entity in entities.items():
            instances = [entity._extend_instance, entity._retract_instance]
            # Add stop_instance for awnings that have it
            if hasattr(entity, '_stop_instance') and entity._stop_instance:
                instances.append(entity._stop_instance)
            if inst_str in instances:
                entity.handle_mqtt(inst_str, payload)
                break

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCAwning(AvailabilityMixin, CoverEntity):
    """Representation of an RV-C awning cover."""

    def __init__(
        self,
        name: str,
        awning_id: str,
        extend_instance: str,
        retract_instance: str,
        stop_instance: str,
        topic_prefix: str,
        command_topic: str,
        availability_timeout: int,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._awning_id = awning_id
        self._extend_instance = extend_instance
        self._retract_instance = retract_instance
        self._stop_instance = stop_instance
        self._topic_prefix = topic_prefix
        self._command_topic = command_topic

        # Cover attributes
        self._attr_device_class = CoverDeviceClass.AWNING
        # Only include STOP feature if stop_instance is defined
        if stop_instance:
            self._attr_supported_features = (
                CoverEntityFeature.OPEN |
                CoverEntityFeature.CLOSE |
                CoverEntityFeature.STOP
            )
        else:
            self._attr_supported_features = (
                CoverEntityFeature.OPEN |
                CoverEntityFeature.CLOSE
            )

        # State tracking
        self._attr_is_closed = True  # Default to retracted
        self._attr_is_closing = False
        self._attr_is_opening = False
        self._attr_assumed_state = True  # Until MQTT confirms

        # Store instance numbers as extra state attributes
        self._attr_extra_state_attributes = {
            "rvc_awning_id": awning_id,
            "rvc_extend_instance": extend_instance,
            "rvc_retract_instance": retract_instance,
            "rvc_stop_instance": stop_instance if stop_instance else "N/A",
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
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, "awning_system")},
            name="RVC Awning System",
            manufacturer="RV-C",
            model="Awning Controller",
            via_device=(DOMAIN, "main_controller"),
        )

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
        self.mark_seen_now()

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
        # Guard: only process if stop_instance is defined
        if not self._stop_instance:
            _LOGGER.warning(
                "Awning %s has no stop instance - stop command ignored",
                self._awning_id
            )
            return

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


class RVCSlide(AvailabilityMixin, CoverEntity):
    """Representation of an RV-C slide cover.

    WARNING: Slides control heavy motors. Ensure the area is clear before operating!
    """

    def __init__(
        self,
        name: str,
        slide_id: str,
        extend_instance: str,
        retract_instance: str,
        topic_prefix: str,
        command_topic: str,
        availability_timeout: int,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._slide_id = slide_id
        self._extend_instance = extend_instance
        self._retract_instance = retract_instance
        self._topic_prefix = topic_prefix
        self._command_topic = command_topic

        # Cover attributes - slides are like shades (extend out/retract in)
        self._attr_device_class = CoverDeviceClass.SHADE
        self._attr_supported_features = (
            CoverEntityFeature.OPEN |
            CoverEntityFeature.CLOSE
        )

        # State tracking
        self._attr_is_closed = True  # Default to retracted
        self._attr_is_closing = False
        self._attr_is_opening = False
        self._attr_assumed_state = True  # Until MQTT confirms

        # Store instance numbers as extra state attributes
        self._attr_extra_state_attributes = {
            "rvc_slide_id": slide_id,
            "rvc_extend_instance": extend_instance,
            "rvc_retract_instance": retract_instance,
            "rvc_topic_prefix": topic_prefix,
            "warning": "CAUTION: Motor control - ensure area is clear!",
            "last_command": None,
            "last_mqtt_update": None,
        }

        _LOGGER.info(
            "Initialized RVCSlide: name='%s', extend=%s, retract=%s",
            name, extend_instance, retract_instance
        )

    @property
    def unique_id(self) -> str:
        return f"rvc_slide_{self._slide_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, "slide_system")},
            name="RVC Slide System",
            manufacturer="RV-C",
            model="Slide Controller",
            via_device=(DOMAIN, "main_controller"),
        )

    def handle_mqtt(self, instance: str, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        _LOGGER.debug(
            "Slide %s received MQTT payload for instance %s: %s",
            self._slide_id, instance, payload
        )

        # Disable assumed_state on first MQTT message
        if self._attr_assumed_state:
            _LOGGER.info(
                "Slide %s received first MQTT status - state now confirmed",
                self._slide_id
            )
            self._attr_assumed_state = False

        # Track last update time
        self.mark_seen_now()

        # Determine state from brightness/operating status
        if "operating status (brightness)" in payload:
            try:
                brightness = float(payload["operating status (brightness)"])
                # If extend instance is active (>0), slide is extending
                if instance == self._extend_instance:
                    if brightness > 0:
                        self._attr_is_opening = True
                        self._attr_is_closing = False
                    else:
                        self._attr_is_opening = False
                # If retract instance is active (>0), slide is retracting
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
        """Extend the slide.

        WARNING: Ensure the area is clear before extending!
        """
        # Log warning for motor operation
        _LOGGER.warning(
            "SLIDE MOTOR: %s extending - ensure area is clear!",
            self._attr_name
        )

        self._attr_is_opening = True
        self._attr_is_closing = False
        self._attr_is_closed = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (extend)
        instance = int(self._extend_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.info(
            "Slide %s extending: publishing to %s: '%s'",
            self._slide_id, self._command_topic, payload
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
        """Retract the slide.

        WARNING: Ensure the area is clear before retracting!
        """
        # Log warning for motor operation
        _LOGGER.warning(
            "SLIDE MOTOR: %s retracting - ensure area is clear!",
            self._attr_name
        )

        self._attr_is_closing = True
        self._attr_is_opening = False

        # Node-RED format: "instance command brightness"
        # Command 2 = Turn ON (retract)
        instance = int(self._retract_instance)
        command = 2
        brightness = 100
        payload = f"{instance} {command} {brightness}"

        _LOGGER.info(
            "Slide %s retracting: publishing to %s: '%s'",
            self._slide_id, self._command_topic, payload
        )

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            payload,
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()
