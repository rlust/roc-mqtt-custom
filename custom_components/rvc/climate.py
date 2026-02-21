"""Platform for RV-C climate devices."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import voluptuous as vol

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
from homeassistant.helpers import entity_platform
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


# Learned Mira thermostat command signatures (instance byte is prepended)
TEMP_UP_SUFFIX = "FFFFFFFFFAFFFF"
TEMP_DOWN_SUFFIX = "FFFFFFFFF9FFFF"
FAN_HIGH_SUFFIX = "DFC8FFFFFFFFFF"
FAN_LOW_SUFFIX = "DF64FFFFFFFFFF"
FAN_AUTO_SUFFIX = "CFFFFFFFFFFFFF"

FAN_MODE_SIGNATURES: dict[str, str] = {
    "high": FAN_HIGH_SUFFIX,
    "low": FAN_LOW_SUFFIX,
    "auto": FAN_AUTO_SUFFIX,
}


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

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service("step_temperature_up", {}, "async_step_temperature_up")
    platform.async_register_entity_service("step_temperature_down", {}, "async_step_temperature_down")
    platform.async_register_entity_service(
        "set_fan_profile",
        vol.Schema({vol.Required("fan_profile"): vol.In(["auto", "low", "high"])}),
        "async_set_fan_profile",
    )


class RVCClimate(AvailabilityMixin, RestoreEntity, ClimateEntity):
    """Representation of an RV-C climate zone."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO]
    _attr_fan_modes = ["auto", "low", "high"]

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
        self._attr_fan_mode = "auto"
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
            "setpoint_cool_f": None,
            "setpoint_heat_f": None,
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

        if (fan_mode := last_state.attributes.get("fan_mode")) in ("auto", "low", "high"):
            self._attr_fan_mode = fan_mode

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
        # Current temperature (if provided by upstream payload)
        if "current_temperature" in payload:
            try:
                self._attr_current_temperature = float(payload["current_temperature"])
            except (TypeError, ValueError):
                pass
        elif "ambient temp F" in payload:
            try:
                self._attr_current_temperature = float(payload["ambient temp F"])
            except (TypeError, ValueError):
                pass

        # Target temperature mapping
        if "target_temperature" in payload:
            try:
                self._attr_target_temperature = float(payload["target_temperature"])
            except (TypeError, ValueError):
                pass
        elif "setpoint temp cool F" in payload:
            try:
                self._attr_target_temperature = float(payload["setpoint temp cool F"])
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

        # Fan mode (from THERMOSTAT_STATUS_1) + HA fan mode mapping
        fan_def = payload.get("fan mode definition")
        fan_speed = payload.get("fan speed")
        if fan_def is not None:
            attrs["fan_mode"] = fan_def
            fan_def_l = str(fan_def).lower()
            if fan_def_l == "auto":
                self._attr_fan_mode = "auto"
            elif fan_def_l == "on":
                # RV-C only exposes on + speed; map to low/high for HA UX
                try:
                    self._attr_fan_mode = "high" if int(fan_speed) >= 100 else "low"
                except (TypeError, ValueError):
                    self._attr_fan_mode = "high"
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

        if "setpoint temp cool F" in payload:
            attrs["setpoint_cool_f"] = payload["setpoint temp cool F"]
        if "setpoint temp heat F" in payload:
            attrs["setpoint_heat_f"] = payload["setpoint temp heat F"]

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
        """Set new target temperature and publish to MQTT.

        For Mira/Firefly controllers, deterministic absolute writes are state-gated.
        We map requested temperature deltas to learned 1°F signatures.
        """
        if "temperature" in kwargs:
            requested = float(kwargs["temperature"])
            current = self._attr_target_temperature or requested

            # Update optimistic target for UI responsiveness
            self._attr_target_temperature = requested

            if requested > current:
                await self._async_publish_signature(TEMP_UP_SUFFIX)
            elif requested < current:
                await self._async_publish_signature(TEMP_DOWN_SUFFIX)

            # If HVAC mode is also being set, keep legacy bridge compatibility
            if "hvac_mode" in kwargs:
                hvac_mode = kwargs["hvac_mode"]
                self._attr_hvac_mode = hvac_mode
                mode_map = {
                    HVACMode.OFF: 0,
                    HVACMode.COOL: 1,
                    HVACMode.HEAT: 2,
                    HVACMode.AUTO: 3,
                }
                payload = {
                    "operating_mode": mode_map.get(hvac_mode, 0),
                    "hvac_mode": hvac_mode.value,
                }
                await mqtt.async_publish(
                    self.hass,
                    self._command_topic,
                    json.dumps(payload),
                    qos=0,
                    retain=False,
                )

            self.async_write_ha_state()

    async def _async_publish_signature(self, suffix: str, *, burst_seconds: float = 2.5, burst_interval: float = 0.35) -> None:
        """Publish learned THERMOSTAT_COMMAND_1 signature with short burst for gate reliability."""
        prefix = f"{int(self._instance):02X}"
        data_hex = f"{prefix}{suffix}"
        topic = f"RVC/THERMOSTAT_COMMAND_1/{self._instance}"

        end = self.hass.loop.time() + burst_seconds
        while self.hass.loop.time() < end:
            payload = {
                "name": "THERMOSTAT_COMMAND_1",
                "instance": int(self._instance),
                "dgn": "1FEF9",
                "data": data_hex,
            }
            await mqtt.async_publish(
                self.hass,
                topic,
                json.dumps(payload),
                qos=0,
                retain=False,
            )
            await asyncio.sleep(burst_interval)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan profile via learned signatures."""
        normalized = fan_mode.lower()
        suffix = FAN_MODE_SIGNATURES.get(normalized)
        if suffix is None:
            return
        await self._async_publish_signature(suffix)
        self._attr_fan_mode = normalized
        self.async_write_ha_state()

    async def async_set_fan_profile(self, fan_profile: str) -> None:
        """Entity service: set fan profile (auto/low/high)."""
        await self.async_set_fan_mode(fan_profile)

    async def async_step_temperature_up(self) -> None:
        """Entity service: nudge target temp up by one learned step."""
        await self._async_publish_signature(TEMP_UP_SUFFIX)

    async def async_step_temperature_down(self) -> None:
        """Entity service: nudge target temp down by one learned step."""
        await self._async_publish_signature(TEMP_DOWN_SUFFIX)
