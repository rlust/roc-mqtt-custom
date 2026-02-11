"""MQTT handler for RV-C integration."""
from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    CONF_AUTO_DISCOVERY,
    CONF_COMMAND_TOPIC,
    CONF_GPS_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_COMMAND_TOPIC,
    DEFAULT_GPS_TOPIC,
    SIGNAL_DISCOVERY,
)

_LOGGER = logging.getLogger(__name__)


class RVCMQTTHandler:
    """Central MQTT listener and dispatcher for RV-C."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.prefix: str = config.get(CONF_TOPIC_PREFIX, "rvc")
        self.discovery_enabled: bool = config.get(CONF_AUTO_DISCOVERY, True)
        self.command_topic: str = config.get(CONF_COMMAND_TOPIC, DEFAULT_COMMAND_TOPIC)
        self.gps_topic: str = config.get(CONF_GPS_TOPIC, DEFAULT_GPS_TOPIC)
        self._unsubs: list[callable] = []
        self._subscriptions: list[str] = []
        self._recent_messages: deque[dict[str, Any]] = deque(maxlen=25)

    async def async_subscribe(self) -> None:
        """Subscribe to RV-C topics."""
        topic = f"{self.prefix}/#"
        _LOGGER.info(
            "RVC MQTT Handler: subscribing to topic pattern '%s' (prefix='%s', discovery=%s)",
            topic, self.prefix, self.discovery_enabled
        )
        unsub = await mqtt.async_subscribe(self.hass, topic, self._message_received, 0)
        self._unsubs.append(unsub)
        self._subscriptions.append(topic)

        gps_topic = self.gps_topic.strip()
        if gps_topic:
            _LOGGER.info(
                "RVC MQTT Handler: also subscribing to GPS topic pattern '%s'",
                gps_topic,
            )
            unsub_gps = await mqtt.async_subscribe(
                self.hass, gps_topic, self._message_received, 0
            )
            self._unsubs.append(unsub_gps)
            self._subscriptions.append(gps_topic)

    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._subscriptions.clear()

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """Return a diagnostics-friendly view of the handler state."""
        return {
            "prefix": self.prefix,
            "command_topic": self.command_topic,
            "gps_topic": self.gps_topic,
            "discovery_enabled": self.discovery_enabled,
            "subscriptions": list(self._subscriptions),
            "recent_messages": list(self._recent_messages),
        }

    async def _message_received(self, msg: mqtt.ReceiveMessage) -> None:  # type: ignore[name-defined]
        """Handle an incoming MQTT message."""
        _LOGGER.debug("RVC MQTT: message on %s => %s", msg.topic, msg.payload)

        if not self.discovery_enabled:
            return

        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            _LOGGER.warning("RVC MQTT: invalid JSON payload on %s: %s", msg.topic, msg.payload)
            return

        # Special handling for GPS data (CP/GPSDATA topic)
        if "GPSDATA" in msg.topic:
            _LOGGER.info(
                "RVC MQTT: GPS data received on %s - lat=%.6f, lon=%.6f",
                msg.topic,
                payload.get("lat", 0),
                payload.get("lon", 0),
            )
            discovery = {
                "type": "device_tracker",
                "instance": "gps",
                "name": "GPS",
                "payload": payload,
            }
            self._remember_message(msg.topic, discovery["type"], discovery["instance"], payload)
            async_dispatcher_send(self.hass, SIGNAL_DISCOVERY, discovery)
            return

        raw_name = str(payload.get("name", "") or "")
        instance_from_payload = payload.get("instance")

        type_from_topic, instance_from_topic = self._classify_from_topic(msg.topic)
        instance_str = instance_from_topic or (
            str(instance_from_payload)
            if instance_from_payload is not None
            else None
        )

        if instance_str is None:
            _LOGGER.debug(
                "RVC MQTT: payload on %s missing 'instance' (name=%s), skipping",
                msg.topic,
                raw_name,
            )
            return

        device_type = type_from_topic or self._classify_from_name(raw_name)
        if device_type is None:
            _LOGGER.debug(
                "RVC MQTT: ignoring message on %s (name=%s, instance=%s) - no mapped device type",
                msg.topic,
                raw_name,
                instance_str,
            )
            return

        _LOGGER.debug(
            "RVC MQTT: classified message as type='%s' (topic=%s, name=%s, instance=%s)",
            device_type,
            msg.topic,
            raw_name,
            instance_str,
        )

        discovery = {
            "type": device_type,
            "instance": instance_str,
            "name": raw_name,
            "payload": payload,
        }

        self._remember_message(msg.topic, device_type, instance_str, payload)
        async_dispatcher_send(self.hass, SIGNAL_DISCOVERY, discovery)

    def _classify_from_topic(self, topic: str) -> tuple[str | None, str | None]:
        """Infer device type/instance from standard topic layouts."""
        status_prefix = f"{self.prefix}/status/"
        if topic.startswith(status_prefix):
            remainder = topic[len(status_prefix):]
            parts = remainder.split("/")
            if len(parts) >= 2:
                return parts[0], parts[1]
        return None, None

    def _classify_from_name(self, raw_name: str) -> str | None:
        """Fallback classification using legacy name prefixes."""
        if raw_name.startswith("DC_DIMMER_STATUS"):
            return "light"
        if raw_name.startswith("AIR_CONDITIONER_STATUS"):
            return "climate"
        if raw_name.startswith("THERMOSTAT_STATUS_1"):
            return "climate"
        sensor_prefixes = (
            "TANK_STATUS",
            "THERMOSTAT_AMBIENT_STATUS",
            "INVERTER_DC_STATUS",
            "INVERTER_AC_STATUS",
            "INVERTER_TEMPERATURE_STATUS",
            "AC_LOAD_STATUS",
            "CHARGER_STATUS",
            "DC_SOURCE_STATUS",
            "WATERHEATER_STATUS",
            "CIRCULATION_PUMP_STATUS",
        )
        if raw_name.startswith(sensor_prefixes):
            return "sensor"
        return None

    def _remember_message(
        self,
        topic: str,
        device_type: str | None,
        instance: str | None,
        payload: dict[str, Any],
    ) -> None:
        """Record a compact message summary for diagnostics."""
        summary = {
            "topic": topic,
            "device_type": device_type,
            "instance": instance,
            "keys": list(payload.keys()),
        }
        self._recent_messages.appendleft(summary)
