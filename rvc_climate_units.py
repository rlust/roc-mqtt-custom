"""
RV-C climate unit conversions and enums (Aspire/Firefly profile).

Ported from the CoachIQ project (https://github.com/carpenike/coachiq,
Apache-2.0, backend/integrations/rvc/climate_units.py), whose byte layouts
and scales were verified on a live 2021 Entegra Aspire 44R Firefly G6 bus.
Modifications: trimmed to the subset needed by thermostat_command_bridge.py.

Key facts (RV-C spec "Table 5.3"):
  * Temperatures on the wire are uint16 in 1/32 K steps:
        raw = (degC + 273) * 32          celsius = raw * 0.03125 - 273
    NOT degC*100 -- sending degC*100 produces nonsense setpoints.
  * Fan speed is half-percent, 0-200 (0xC8 = 100%). 0 = automatic.
  * A full THERMOSTAT_COMMAND_1 frame carries the ENTIRE zone state;
    unchanged fields must be filled from the last observed status.
"""
from __future__ import annotations

from typing import Any

RAW_TEMP_UNAVAILABLE = 0xFFFF

# THERMOSTAT_STATUS_1 / THERMOSTAT_COMMAND_1 operating_mode (4-bit)
OPERATING_MODE_LABELS: dict[int, str] = {
    0: "off",
    1: "cool",
    2: "heat",
    3: "auto",
    4: "fan_only",
    5: "aux_heat",
    6: "window_defrost",
}
OPERATING_MODE_RAW: dict[str, int] = {v: k for k, v in OPERATING_MODE_LABELS.items()}

# fan_mode (2-bit)
FAN_MODE_LABELS: dict[int, str] = {0: "auto", 1: "on"}
FAN_MODE_RAW: dict[str, int] = {v: k for k, v in FAN_MODE_LABELS.items()}

# Fan speed percentage is encoded 0-200 raw (half-percent). 0 = automatic.
FAN_SPEED_MAX_PCT = 100
FAN_SPEED_ON_RAW = 0xC8  # 200 = 100%

# Sanity bounds for setpoint commands, Fahrenheit. Floor-heat zones
# legitimately run to ~100F, so the cap sits above that.
SETPOINT_MIN_F = 40.0
SETPOINT_MAX_F = 105.0

# Readings below this are treated as "sensor absent".
_MIN_PLAUSIBLE_C = -40.0


def f_to_c(vf: float) -> float:
    return (float(vf) - 32.0) * 5.0 / 9.0


def c_to_f(vc: float) -> float:
    return float(vc) * 9.0 / 5.0 + 32.0


def c_to_raw_temp(vc: float) -> int:
    """Celsius -> RV-C Table 5.3 uint16 (1/32 K steps)."""
    return int(round((float(vc) + 273.0) * 32.0)) & 0xFFFF


def f_to_raw_temp(vf: float) -> int:
    """Fahrenheit -> RV-C Table 5.3 uint16 (1/32 K steps)."""
    return c_to_raw_temp(f_to_c(vf))


def raw_temp_to_c(raw: Any) -> float | None:
    """RV-C Table 5.3 uint16 -> Celsius (None if unavailable/implausible)."""
    try:
        raw_int = int(raw)
    except (TypeError, ValueError):
        return None
    if raw_int == RAW_TEMP_UNAVAILABLE:
        return None
    celsius = raw_int * 0.03125 - 273.0
    if celsius < _MIN_PLAUSIBLE_C:
        return None
    return celsius


def raw_temp_to_f(raw: Any) -> float | None:
    """RV-C Table 5.3 uint16 -> Fahrenheit rounded to 0.1 (None if n/a)."""
    celsius = raw_temp_to_c(raw)
    if celsius is None:
        return None
    return round(c_to_f(celsius) * 10) / 10


def pct_to_halfpct(pct: Any) -> int:
    """Fan percent 0-100 -> raw half-percent 0-200 (0 = automatic)."""
    try:
        p = int(pct)
    except (TypeError, ValueError):
        return 0
    return min(max(p, 0), FAN_SPEED_MAX_PCT) * 2


def halfpct_to_pct(raw: Any) -> int | None:
    """Raw half-percent 0-200 -> percent 0-100."""
    try:
        r = int(raw)
    except (TypeError, ValueError):
        return None
    return min(max(r, 0), 200) // 2


def mode_to_raw(mode: Any) -> int | None:
    """Accept an int (0-6) or label ('cool', 'heat', ...) -> raw mode."""
    if isinstance(mode, str) and not mode.isdigit():
        return OPERATING_MODE_RAW.get(mode.strip().lower())
    try:
        m = int(mode)
    except (TypeError, ValueError):
        return None
    return m if m in OPERATING_MODE_LABELS else None


def fan_mode_to_raw(fan_mode: Any) -> int | None:
    """Accept an int (0/1) or label ('auto'/'on') -> raw fan mode."""
    if isinstance(fan_mode, str) and not fan_mode.isdigit():
        return FAN_MODE_RAW.get(fan_mode.strip().lower())
    try:
        f = int(fan_mode)
    except (TypeError, ValueError):
        return None
    return f if f in FAN_MODE_LABELS else None


def build_thermostat_command_payload(
    instance: int,
    operating_mode: int,
    fan_mode: int,
    schedule_mode: int,
    fan_speed_raw: int,
    setpoint_heat_raw: int,
    setpoint_cool_raw: int,
) -> bytes:
    """
    THERMOSTAT_COMMAND_1 (DGN 0x1FEF9) 8-byte payload. Mirrors the
    THERMOSTAT_STATUS_1 layout the Firefly G6 broadcasts: instance, packed
    mode byte, fan speed (half-percent), heat then cool setpoints as
    little-endian uint16 in 1/32 K steps, byte 7 unused (0xFF).
    """
    mode_byte = (
        (operating_mode & 0x0F)
        | ((fan_mode & 0x03) << 4)
        | ((schedule_mode & 0x03) << 6)
    )
    return bytes(
        [
            instance & 0xFF,
            mode_byte,
            fan_speed_raw & 0xFF,
            setpoint_heat_raw & 0xFF,
            (setpoint_heat_raw >> 8) & 0xFF,
            setpoint_cool_raw & 0xFF,
            (setpoint_cool_raw >> 8) & 0xFF,
            0xFF,
        ]
    )


def rvc_arbitration_id(pgn: int, source_address: int, priority: int = 6) -> int:
    """29-bit RV-C CAN arbitration ID: (prio << 26) | (PGN << 8) | SA."""
    return ((priority & 0x7) << 26) | ((pgn & 0x3FFFF) << 8) | (source_address & 0xFF)


THERMOSTAT_COMMAND_1_PGN = 0x1FEF9
THERMOSTAT_STATUS_1_PGN = 0x1FFE2
DEFAULT_SOURCE_ADDRESS = 0xF9  # matches CoachIQ's verified-accepted SA
DEFAULT_PRIORITY = 6
