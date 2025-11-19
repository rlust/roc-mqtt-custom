"""Platform for RV-C climate devices."""
from __future__ import annotations

import json
from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVERY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C climate entities from discovery."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCClimate] = {}

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "climate":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)
        name = payload.get("name") or f"RVC Climate {inst_str}"

        entity = entities.get(inst_str)
        if entity is None:
            entity = RVCClimate(
                name=name,
                instance_id=inst_str,
                topic_prefix=entry.data.get("topic_prefix", "rvc"),
            )
            entities[inst_str] = entity
            async_add_entities([entity])

        entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCClimate(ClimateEntity):
    """Representation of an RV-C climate zone."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(self, name: str, instance_id: str, topic_prefix: str) -> None:
        self._attr_name = name
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_target_temperature = 22.0
        self._attr_current_temperature = None
        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT  # RV-C uses Fahrenheit

    @property
    def unique_id(self) -> str:
        return f"rvc_climate_{self._instance}"

    @property
    def _command_topic(self) -> str:
        """MQTT command topic for this climate zone."""
        # Example: rvc/command/climate/1
        return f"{self._topic_prefix}/command/climate/{self._instance}"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        if "current_temperature" in payload:
            try:
                self._attr_current_temperature = float(payload["current_temperature"])
            except (TypeError, ValueError):
                pass

        if "target_temperature" in payload:
            try:
                self._attr_target_temperature = float(payload["target_temperature"])
            except (TypeError, ValueError):
                pass

        if "hvac_mode" in payload:
            mode = str(payload["hvac_mode"]).lower()
            for m in self._attr_hvac_modes:
                if m.value == mode:
                    self._attr_hvac_mode = m
                    break

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode and publish to MQTT."""
        self._attr_hvac_mode = hvac_mode

        # Map HA HVAC mode to RV-C operating mode
        # RV-C modes: off=0, cool=1, heat=2, auto=3 (typical values)
        mode_map = {
            HVACMode.OFF: 0,
            HVACMode.COOL: 1,
            HVACMode.HEAT: 2,
            HVACMode.AUTO: 3,
        }

        operating_mode = mode_map.get(hvac_mode, 0)

        payload = {
            "operating_mode": operating_mode,
            "hvac_mode": hvac_mode.value,  # Also include string for bridge compatibility
        }

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature and publish to MQTT."""
        if "temperature" in kwargs:
            temp = float(kwargs["temperature"])
            self._attr_target_temperature = temp

            # Publish temperature setpoint command
            # Include both Celsius and Fahrenheit for bridge compatibility
            payload = {
                "target_temperature": temp,
                "setpoint_temp_cool": temp,  # RV-C field name
                "setpoint_temp_heat": temp,  # RV-C field name
            }

            # If HVAC mode is also being set
            if "hvac_mode" in kwargs:
                hvac_mode = kwargs["hvac_mode"]
                self._attr_hvac_mode = hvac_mode
                mode_map = {
                    HVACMode.OFF: 0,
                    HVACMode.COOL: 1,
                    HVACMode.HEAT: 2,
                    HVACMode.AUTO: 3,
                }
                payload["operating_mode"] = mode_map.get(hvac_mode, 0)
                payload["hvac_mode"] = hvac_mode.value

            await mqtt.async_publish(
                self.hass,
                self._command_topic,
                json.dumps(payload),
                qos=0,
                retain=False,
            )

            self.async_write_ha_state()
