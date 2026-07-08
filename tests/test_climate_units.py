"""Tests for rvc_climate_units (RV-C Table 5.3 encoding, ported from CoachIQ)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import rvc_climate_units as cu


class TestTemperatureEncoding:
    def test_72f_encodes_to_table_5_3_raw(self):
        # 72F = 22.222C -> (22.222+273)*32 = 9447 (NOT 2222 = degC*100)
        assert cu.f_to_raw_temp(72.0) == 9447

    def test_round_trip_across_setpoint_range(self):
        for f in range(40, 106):
            raw = cu.f_to_raw_temp(float(f))
            back = cu.raw_temp_to_f(raw)
            assert back is not None
            assert abs(back - f) < 0.1, f"{f}F -> {raw} -> {back}"

    def test_unavailable_sentinel(self):
        assert cu.raw_temp_to_f(0xFFFF) is None

    def test_implausible_reading_rejected(self):
        # Bay zone broadcasts ~-88C with sensor disconnected
        assert cu.raw_temp_to_f(cu.c_to_raw_temp(-88.0)) is None

    def test_bad_input(self):
        assert cu.raw_temp_to_f("garbage") is None
        assert cu.raw_temp_to_f(None) is None


class TestFanSpeed:
    def test_half_percent_scale(self):
        assert cu.pct_to_halfpct(100) == 200  # 0xC8
        assert cu.pct_to_halfpct(50) == 100
        assert cu.pct_to_halfpct(0) == 0  # automatic

    def test_clamping(self):
        assert cu.pct_to_halfpct(150) == 200
        assert cu.pct_to_halfpct(-5) == 0

    def test_reverse(self):
        assert cu.halfpct_to_pct(0xC8) == 100


class TestModes:
    def test_mode_labels(self):
        assert cu.mode_to_raw("cool") == 1
        assert cu.mode_to_raw("heat") == 2
        assert cu.mode_to_raw("auto") == 3
        assert cu.mode_to_raw("off") == 0
        assert cu.mode_to_raw("fan_only") == 4

    def test_mode_ints_and_bad_values(self):
        assert cu.mode_to_raw(1) == 1
        assert cu.mode_to_raw("1") == 1
        assert cu.mode_to_raw(9) is None
        assert cu.mode_to_raw("banana") is None

    def test_fan_mode(self):
        assert cu.fan_mode_to_raw("auto") == 0
        assert cu.fan_mode_to_raw("on") == 1
        assert cu.fan_mode_to_raw(2) is None


class TestFrameConstruction:
    def test_known_frame_zone0_cool_72(self):
        raw = cu.f_to_raw_temp(72.0)  # 9447 = 0x24E7
        data = cu.build_thermostat_command_payload(
            instance=0, operating_mode=1, fan_mode=0, schedule_mode=0,
            fan_speed_raw=0, setpoint_heat_raw=raw, setpoint_cool_raw=raw,
        )
        assert data == bytes([0x00, 0x01, 0x00, 0xE7, 0x24, 0xE7, 0x24, 0xFF])

    def test_mode_byte_packing(self):
        data = cu.build_thermostat_command_payload(
            instance=2, operating_mode=3, fan_mode=1, schedule_mode=0,
            fan_speed_raw=0xC8, setpoint_heat_raw=0, setpoint_cool_raw=0,
        )
        assert data[1] == (3 | (1 << 4))  # mode 3, fan on
        assert data[2] == 0xC8

    def test_arbitration_id(self):
        # CoachIQ-verified: prio 6, PGN 1FEF9, SA F9 -> 0x19FEF9F9
        assert cu.rvc_arbitration_id(0x1FEF9, 0xF9, 6) == 0x19FEF9F9
        # Bare PGN (the old bug) must NOT equal the proper ID
        assert cu.rvc_arbitration_id(0x1FEF9, 0xF9, 6) != 0x1FEF9
