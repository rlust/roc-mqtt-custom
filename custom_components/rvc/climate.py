"""Platform for RV-C climate devices."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import voluptuous as vol
from homeassistant.components import mqtt
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .availability import AvailabilityMixin
from .const import (
    CONF_AVAILABILITY_TIMEOUT,
    CONF_THERMOSTAT_BRIDGE_MODE,
    CONF_THERMOSTAT_BRIDGE_TOPIC,
    CONF_TOPIC_PREFIX,
    DEFAULT_AVAILABILITY_TIMEOUT,
    DEFAULT_THERMOSTAT_BRIDGE_MODE,
    DEFAULT_THERMOSTAT_BRIDGE_TOPIC,
    DEFAULT_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
)
from .helpers import coerce_int as _coerce_int
from .helpers import get_entry_option as _get_entry_option

# RV-C THERMOSTAT_COMMAND_1 (DGN 1FEF9) signatures for the Mira/Aspire panel,
# captured by sniffing the CAN bus while pressing the physical thermostat
# buttons (see tools/HVAC_FIELD_LEARNINGS.md and thermostat_pgn_map_aspire.json).
#
# Each value is the last 7 bytes of the 8-byte data payload as hex; the first
# byte (thermostat instance) is prepended at publish time by
# _async_publish_signature(). Byte layout per the RV-C spec:
#   byte 0: instance          byte 1: operating mode / schedule mode bits
#   byte 2: fan mode + speed  bytes 3-4: setpoint heat (0.03125 degC/bit)
#   bytes 5-6: setpoint cool  byte 7: reserved (0xFF)
# 0xFF in a field means "no change" - these signatures only touch the field
# they intend to change, which is why most bytes are FF.
#
# To recalibrate for a different thermostat: run tools/ac_status_watch.py,
# press the button on the physical panel, and copy the payload bytes seen on
# {prefix}/status/climate. Update the constants below to match.
TEMP_UP_SUFFIX = "FFFFFFFFFAFFFF"    # bump cool setpoint up one step
TEMP_DOWN_SUFFIX = "FFFFFFFFF9FFFF"  # bump cool setpoint down one step
FAN_HIGH_SUFFIX = "DFC8FFFFFFFFFF"   # fan manual, speed 0xC8 (100%)
FAN_LOW_SUFFIX = "DF64FFFFFFFFFF"    # fan manual, speed 0x64 (50%)
FAN_AUTO_SUFFIX = "CFFFFFFFFFFFFF"   # fan auto (speed field ignored)

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

        payload = discovery["payload"]
        raw_name = str(payload.get("name", "") or "")

        # Canonical zone mapping based on learned Aspire behavior:
        # - THERMOSTAT_STATUS_1 instances 0/1/2 => Front/Mid/Rear
        # - AIR_CONDITIONER_STATUS instances 1/2/3 map to thermostat 0/1/2
        mapped_instance: str | None = None
        try:
            raw_instance = int(discovery["instance"])
        except (TypeError, ValueError):
            return

        if raw_name.startswith("THERMOSTAT_STATUS_1") or raw_name.startswith("THERMOSTAT_COMMAND_1"):
            if raw_instance in (0, 1, 2):
                mapped_instance = str(raw_instance)
        elif raw_name.startswith("AIR_CONDITIONER_STATUS") or raw_name.startswith("AIR_CONDITIONER_COMMAND"):
            if raw_instance in (1, 2, 3):
                mapped_instance = str(raw_instance - 1)

        if mapped_instance is None:
            # Ignore non-zone climate-like instances (ex: 81) to avoid bogus entities.
            return

        zone_names = {"0": "AC Front", "1": "AC Mid", "2": "AC Rear"}
        name = zone_names.get(mapped_instance, f"RVC Climate {mapped_instance}")

        entity = entities.get(mapped_instance)
        if entity is None:
            entity = RVCClimate(
                name=name,
                instance_id=mapped_instance,
                topic_prefix=_get_entry_option(entry, CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX),
                availability_timeout=availability_timeout,
                bridge_mode=bool(
                    _get_entry_option(
                        entry, CONF_THERMOSTAT_BRIDGE_MODE, DEFAULT_THERMOSTAT_BRIDGE_MODE
                    )
                ),
                bridge_topic=str(
                    _get_entry_option(
                        entry, CONF_THERMOSTAT_BRIDGE_TOPIC, DEFAULT_THERMOSTAT_BRIDGE_TOPIC
                    )
                ),
            )
            entities[mapped_instance] = entity
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
        bridge_mode: bool = DEFAULT_THERMOSTAT_BRIDGE_MODE,
        bridge_topic: str = DEFAULT_THERMOSTAT_BRIDGE_TOPIC,
    ) -> None:
        AvailabilityMixin.__init__(self, availability_timeout)
        self._bridge_mode = bridge_mode
        self._bridge_topic = bridge_topic
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
            "thermostat_bridge_mode": bridge_mode,
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

    @property
    def _bridge_command_topic(self) -> str:
        """Per-zone control topic for thermostat_command_bridge.py."""
        # Example: rvcbridge/thermostat_control/1
        return f"{self._bridge_topic}/{int(self._instance)}"

    async def _async_publish_bridge_command(self, payload: dict[str, Any]) -> None:
        """Publish an absolute zone command to the thermostat bridge.

        The bridge validates it, fills unchanged fields from the zone's live
        THERMOSTAT_STATUS_1 state, encodes RV-C Table 5.3 setpoints, and
        transmits THERMOSTAT_COMMAND_1 (0x19FEF9F9) on CAN. Requires
        thermostat_command_bridge.py v2 running with --tx-enable.
        """
        await mqtt.async_publish(
            self.hass,
            self._bridge_command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

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

        if self._bridge_mode:
            await self._async_publish_bridge_command({"mode": operating_mode})
        else:
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

            if self._bridge_mode:
                # Absolute write: the bridge fills mode/fan from live zone
                # state, so this changes ONLY the setpoint (heat + cool in
                # lockstep, matching Firefly G6 behavior).
                await self._async_publish_bridge_command({"setpoint_f": requested})
            elif requested > current:
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
        """Set fan profile via the bridge (absolute) or learned signatures."""
        normalized = fan_mode.lower()
        if self._bridge_mode:
            fan_payloads = {
                "auto": {"fan_mode": "auto", "fan_speed_pct": 0},
                "low": {"fan_mode": "on", "fan_speed_pct": 50},
                "high": {"fan_mode": "on", "fan_speed_pct": 100},
            }
            payload = fan_payloads.get(normalized)
            if payload is None:
                return
            await self._async_publish_bridge_command(payload)
        else:
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
