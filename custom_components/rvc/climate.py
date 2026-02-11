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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .availability import AvailabilityMixin
from .const import (
    CONF_AVAILABILITY_TIMEOUT,
    CONF_TOPIC_PREFIX,
    DEFAULT_AVAILABILITY_TIMEOUT,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
)


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
    """Set up RV-C climate entities from discovery."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCClimate] = {}
    availability_timeout = _coerce_int(
        _get_entry_option(entry, CONF_AVAILABILITY_TIMEOUT, DEFAULT_AVAILABILITY_TIMEOUT),
        DEFAULT_AVAILABILITY_TIMEOUT,
    )

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
                topic_prefix=_get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                availability_timeout=availability_timeout,
            )
            entities[inst_str] = entity
            async_add_entities([entity])

        entity.handle_mqtt(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCClimate(AvailabilityMixin, RestoreEntity, ClimateEntity):
    """Representation of an RV-C climate zone."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(
        self,
        name: str,
        instance_id: str,
        topic_prefix: str,
        availability_timeout: int,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_target_temperature = 22.0
        self._attr_current_temperature = None
        self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT  # RV-C uses Fahrenheit

        # Enhanced diagnostic attributes
        self._attr_extra_state_attributes = {
            "rvc_instance": instance_id,
            "rvc_topic_prefix": topic_prefix,
            "availability_timeout": availability_timeout,
            "ac_output_level": None,
            "fan_speed_actual": None,
            "fan_mode": None,
            "schedule_mode": None,
            "dead_band": None,
            "last_mqtt_update": None,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None:
            return

        state = last_state.state
        for mode in self._attr_hvac_modes:
            if mode.value == state:
                self._attr_hvac_mode = mode
                break

        if (temp := last_state.attributes.get("temperature")) is not None:
            try:
                self._attr_target_temperature = float(temp)
            except (TypeError, ValueError):
                pass

        if (curr := last_state.attributes.get("current_temperature")) is not None:
            try:
                self._attr_current_temperature = float(curr)
            except (TypeError, ValueError):
                pass

    @property
    def unique_id(self) -> str:
        return f"rvc_climate_{self._instance}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group climate entities."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"climate_zone_{self._instance}")},
            name=f"Climate Zone {self._instance}",
            manufacturer="RV-C",
            model="HVAC Controller",
            via_device=(DOMAIN, "main_controller"),
        )

    @property
    def icon(self) -> str:
        """Return icon for climate entity."""
        if self._attr_hvac_mode == HVACMode.COOL:
            return "mdi:snowflake"
        elif self._attr_hvac_mode == HVACMode.HEAT:
            return "mdi:fire"
        elif self._attr_hvac_mode == HVACMode.OFF:
            return "mdi:hvac-off"
        else:
            return "mdi:thermostat"

    @property
    def _command_topic(self) -> str:
        """MQTT command topic for this climate zone."""
        # Example: rvc/command/climate/1
        return f"{self._topic_prefix}/command/climate/{self._instance}"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        self.mark_seen_now()
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

        # Capture diagnostic attributes from RV-C payload
        attrs = self._attr_extra_state_attributes

        # AC output level (from AIR_CONDITIONER_STATUS)
        if "air conditioning output level" in payload:
            attrs["ac_output_level"] = payload["air conditioning output level"]

        # Fan speed (actual from AIR_CONDITIONER_STATUS or THERMOSTAT)
        if "fan speed" in payload:
            attrs["fan_speed_actual"] = payload["fan speed"]

        # Fan mode (from THERMOSTAT_STATUS_1)
        if "fan mode definition" in payload:
            attrs["fan_mode"] = payload["fan mode definition"]
        elif "fan mode" in payload:
            attrs["fan_mode"] = f"Mode {payload['fan mode']}"

        # Schedule mode (from THERMOSTAT_STATUS_1)
        if "schedule mode definition" in payload:
            attrs["schedule_mode"] = payload["schedule mode definition"]
        elif "schedule mode" in payload:
            attrs["schedule_mode"] = f"Mode {payload['schedule mode']}"

        # Dead band (temperature dead band from AIR_CONDITIONER_STATUS)
        if "dead band" in payload:
            attrs["dead_band"] = payload["dead band"]

        # Timestamp for diagnostics
        if "timestamp" in payload:
            attrs["last_mqtt_update"] = payload["timestamp"]

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
