"""MQTT handler for RV-C integration."""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DISCOVERY, CONF_TOPIC_PREFIX, CONF_AUTO_DISCOVERY

_LOGGER = logging.getLogger(__name__)


class RVCMQTTHandler:
    """Central MQTT listener and dispatcher for RV-C."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        # This should be "RVC" for your setup (configurable via config_flow)
        self.prefix: str = config.get(CONF_TOPIC_PREFIX, "rvc")
        self.discovery_enabled: bool = config.get(CONF_AUTO_DISCOVERY, True)
        self._unsubs: list[callable] = []

    async def async_subscribe(self) -> None:
        """Subscribe to RV-C topics."""
        topic = f"{self.prefix}/#"
        _LOGGER.info("RVC MQTT: subscribing to topic: %s", topic)
        unsub = await mqtt.async_subscribe(self.hass, topic, self._message_received, 0)
        self._unsubs.append(unsub)

    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

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

        # A lot of your payloads have a "name" and "instance"
        raw_name = str(payload.get("name", "") or "")
        instance = payload.get("instance")
        if instance is None:
            _LOGGER.debug(
                "RVC MQTT: payload on %s missing 'instance' (name=%s), skipping",
                msg.topic,
                raw_name,
            )
            return

        instance_str = str(instance)

        # ---- Device type classification based on 'name' ----
        device_type: str | None = None

        # Lights (dimmer loads)
        # e.g. name: "DC_DIMMER_STATUS_3"
        if raw_name.startswith("DC_DIMMER_STATUS"):
            device_type = "light"

        # Climate – AC zones / thermostats
        elif raw_name.startswith("AIR_CONDITIONER_STATUS"):
            device_type = "climate"
        elif raw_name.startswith("THERMOSTAT_STATUS_1"):
            device_type = "climate"

        # Sensors – temperatures, tanks, inverter, etc.
        elif raw_name.startswith("TANK_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("THERMOSTAT_AMBIENT_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("INVERTER_DC_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("INVERTER_AC_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("INVERTER_TEMPERATURE_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("AC_LOAD_STATUS"):
            device_type = "sensor"
        elif raw_name.startswith("CHARGER_STATUS"):
            device_type = "sensor"

        if device_type is None:
            # Not something we map yet – safe to ignore
            _LOGGER.debug(
                "RVC MQTT: ignoring message on %s (name=%s, instance=%s) - no mapped device type",
                msg.topic,
                raw_name,
                instance_str,
            )
            return

        discovery = {
            "type": device_type,
            "instance": instance_str,
            "name": raw_name,
            "payload": payload,
        }

        _LOGGER.info(
            "RVC MQTT: dispatching discovery: type=%s instance=%s name=%s",
            device_type,
            instance_str,
            raw_name,
        )
        async_dispatcher_send(self.hass, SIGNAL_DISCOVERY, discovery)
