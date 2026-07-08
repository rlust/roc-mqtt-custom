"""Tests for thermostat_command_bridge v2 (state fill-in + frame building)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rvc_climate_units as cu
from thermostat_command_bridge import Limits, ZoneState, parse_status_payload, resolve_command


@pytest.fixture
def zone():
    """A zone last seen: heat mode, fan auto, heat 68F / cool 74F."""
    return ZoneState(
        operating_mode=2,
        fan_mode=0,
        schedule_mode=0,
        fan_speed_raw=0,
        setpoint_heat_raw=cu.f_to_raw_temp(68.0),
        setpoint_cool_raw=cu.f_to_raw_temp(74.0),
    )


@pytest.fixture
def limits():
    return Limits()


class TestResolveCommand:
    def test_setpoint_only_preserves_mode_and_fan(self, zone, limits):
        resolved, reason = resolve_command({"setpoint_f": 71}, zone, limits)
        assert reason == "ok"
        assert resolved["operating_mode"] == 2  # heat preserved, NOT forced to cool
        assert resolved["fan_mode"] == 0
        assert resolved["fan_speed_raw"] == 0
        assert resolved["setpoint_heat_raw"] == cu.f_to_raw_temp(71)
        assert resolved["setpoint_cool_raw"] == cu.f_to_raw_temp(71)

    def test_mode_only_preserves_setpoints(self, zone, limits):
        resolved, reason = resolve_command({"mode": "cool"}, zone, limits)
        assert reason == "ok"
        assert resolved["operating_mode"] == 1
        assert resolved["setpoint_heat_raw"] == cu.f_to_raw_temp(68.0)
        assert resolved["setpoint_cool_raw"] == cu.f_to_raw_temp(74.0)

    def test_split_setpoints(self, zone, limits):
        resolved, reason = resolve_command(
            {"setpoint_heat_f": 66, "setpoint_cool_f": 76}, zone, limits
        )
        assert reason == "ok"
        assert resolved["setpoint_heat_raw"] == cu.f_to_raw_temp(66)
        assert resolved["setpoint_cool_raw"] == cu.f_to_raw_temp(76)

    def test_legacy_operating_mode_key(self, zone, limits):
        # HA climate.py <= v2.3.x published {"operating_mode": 1}
        resolved, reason = resolve_command({"operating_mode": 1}, zone, limits)
        assert reason == "ok"
        assert resolved["operating_mode"] == 1

    def test_fan_speed_pct_half_percent(self, zone, limits):
        resolved, reason = resolve_command({"fan_mode": "on", "fan_speed_pct": 100}, zone, limits)
        assert reason == "ok"
        assert resolved["fan_mode"] == 1
        assert resolved["fan_speed_raw"] == 0xC8

    def test_out_of_range_setpoint_rejected(self, zone, limits):
        resolved, reason = resolve_command({"setpoint_f": 120}, zone, limits)
        assert resolved is None
        assert "out_of_range" in reason

    def test_bad_mode_rejected(self, zone, limits):
        resolved, reason = resolve_command({"mode": "turbo"}, zone, limits)
        assert resolved is None
        assert reason.startswith("bad_mode")

    def test_empty_command_rejected(self, zone, limits):
        resolved, reason = resolve_command({}, zone, limits)
        assert resolved is None
        assert reason == "no_recognized_fields"


class TestParseStatusPayload:
    def test_raw_data_hex_preferred(self):
        # zone 0, cool(1)/fan auto/sched 0, fan 0, heat+cool 72F (0x24E7 LE)
        fields = parse_status_payload({"data": "000100E724E724FF"})
        assert fields is not None
        assert fields["instance"] == 0
        assert fields["operating_mode"] == 1
        assert fields["fan_mode"] == 0
        assert fields["setpoint_heat_raw"] == 9447
        assert fields["setpoint_cool_raw"] == 9447

    def test_named_fields_fahrenheit(self):
        fields = parse_status_payload({
            "instance": 2,
            "operating mode": 2,
            "fan mode": 0,
            "schedule mode": 0,
            "fan speed": 0,
            "setpoint temp heat F": 68.0,
            "setpoint temp cool F": 74.0,
        })
        assert fields is not None
        assert fields["operating_mode"] == 2
        assert fields["setpoint_heat_raw"] == cu.f_to_raw_temp(68.0)

    def test_insufficient_payload_returns_none(self):
        assert parse_status_payload({"instance": 1}) is None
        assert parse_status_payload({}) is None


class TestFeedbackLoopGuard:
    """The ack/nack/audit topics share the control prefix; they must never be
    treated as control messages (regression: NACK-of-own-NACK MQTT loop)."""

    def _bridge_topic_check(self, tail):
        from thermostat_command_bridge import ThermostatBridge
        # Use the classmethod logic without constructing (needs no mqtt):
        parts = ["rvcbridge", "thermostat_control", tail]
        return (
            len(parts) == 3
            and parts[0] == "rvcbridge"
            and parts[1] == "thermostat_control"
            and parts[2] not in ThermostatBridge.RESERVED_TAILS
        )

    def test_reserved_tails_not_control(self):
        assert not self._bridge_topic_check("ack")
        assert not self._bridge_topic_check("nack")
        assert not self._bridge_topic_check("audit")

    def test_zone_topics_are_control(self):
        assert self._bridge_topic_check("0")
        assert self._bridge_topic_check("6")


class TestAcLoadCommand:
    """AC_LOAD_COMMAND (Aqua-Hot burner/electric) support, per CoachIQ wire
    verification: [inst, 0xFF, level, 0xC0, 0,0,0,0], arb 0x19FFBEF9."""

    def test_resolve_on_off(self):
        from thermostat_command_bridge import resolve_acload_level
        assert resolve_acload_level({"state": "on"}) == (0xC8, "ok")
        assert resolve_acload_level({"state": "off"}) == (0x00, "ok")
        assert resolve_acload_level({"command": "on"}) == (0xC8, "ok")

    def test_resolve_level_pct(self):
        from thermostat_command_bridge import resolve_acload_level
        assert resolve_acload_level({"level_pct": 100}) == (0xC8, "ok")
        assert resolve_acload_level({"level_pct": 0}) == (0x00, "ok")

    def test_resolve_rejects_garbage(self):
        from thermostat_command_bridge import resolve_acload_level
        level, reason = resolve_acload_level({"state": "maybe"})
        assert level is None and reason.startswith("bad_state")
        level, reason = resolve_acload_level({})
        assert level is None and reason == "no_recognized_fields"

    def test_frame_bytes(self):
        data = cu.build_ac_load_command_payload(212, cu.AC_LOAD_LEVEL_ON)
        assert data == bytes([0xD4, 0xFF, 0xC8, 0xC0, 0, 0, 0, 0])
        data = cu.build_ac_load_command_payload(210, cu.AC_LOAD_LEVEL_OFF)
        assert data == bytes([0xD2, 0xFF, 0x00, 0xC0, 0, 0, 0, 0])

    def test_arbitration_id(self):
        assert cu.rvc_arbitration_id(cu.AC_LOAD_COMMAND_PGN, 0xF9, 6) == 0x19FFBEF9

    def test_shed_levels(self):
        assert 0xFD in cu.AC_LOAD_SHED_LEVELS
        assert 0xFC in cu.AC_LOAD_SHED_LEVELS
        assert 0xC8 not in cu.AC_LOAD_SHED_LEVELS
