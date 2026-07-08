# Release Notes — v2.4.0 "Correct Thermostat Wire Protocol"

**Date:** 2026-07-08

This release rewrites the thermostat command path based on findings from the
[CoachIQ](https://github.com/carpenike/coachiq) project (Apache-2.0), whose
RV-C climate implementation was verified on a live Entegra Aspire Firefly G6
bus — the same platform this integration targets.

## Why this release matters

The previous `thermostat_command_bridge.py` built frames the Firefly G6 could
never act on:

| Bug | Before | After |
|---|---|---|
| Setpoint encoding | °C×100 (72°F → 2222) | RV-C Table 5.3: (°C+273)×32 (72°F → 9447 / `0x24E7`) |
| CAN arbitration ID | bare PGN `0x0001FEF9` | `0x19FEF9F9` (prio 6, PGN 1FEF9, SA 0xF9) |
| Fan speed | 0–100, default 50 | half-percent 0–200 (`0xC8`=100%), default 0 = auto |
| Missing fields | invented defaults (cool/50%/72°F) | filled from live THERMOSTAT_STATUS_1 state |

## New: state cache and fill-in

THERMOSTAT_COMMAND_1 carries the entire zone state in one frame. The bridge
now caches each zone's last status (from `RVC/THERMOSTAT_STATUS_1/+` and
`rvc/status/climate/+`) and overlays only the fields you send — so
`{"setpoint_f": 71}` changes the setpoint and nothing else. Commands to a
zone never seen on the bus are NACKed (`no_status_seen`).

## New: HA "Thermostat bridge mode" (opt-in)

Settings → Devices & Services → RV-C → Configure → enable
**Thermostat bridge mode**. Climate entities then publish absolute commands
(`{"setpoint_f": 72}`, `{"mode": 1}`, `{"fan_mode": "on", "fan_speed_pct": 100}`)
to `rvcbridge/thermostat_control/<zone>`. Disabled by default — the legacy
learned-signature burst path is untouched.

## Upgrade & rollout (do this in order)

1. Install v2.4.0 (HACS or copy `custom_components/rvc/`), restart HA.
   `rvc_climate_units.py` must sit next to `thermostat_command_bridge.py`.
2. Run the bridge in **dry-run** and watch the audit topic:
   `python3 thermostat_command_bridge.py --broker <ip> --dry-run`
3. **Golden-frame check** (recommended): `candump can1 | grep 19FEF9` while
   pressing a temp button on the physical panel; compare against the bridge's
   dry-run frame for the same change. Bytes should match (except SA).
4. Enable TX: `--tx-enable`. Test ONE setpoint change on ONE zone; confirm the
   panel reflects it and the ack topic shows `"confirmed"`.
5. Enable "Thermostat bridge mode" in the HA integration options.

## Compatibility

- Legacy `{"operating_mode": n}` payloads on the old command topic still work.
- The learned-signature path is unchanged when bridge mode is off.
- 25 new unit tests: `python3 -m pytest tests/test_climate_units.py tests/test_thermostat_bridge.py`

## Attribution

Encoding logic ported from CoachIQ (`backend/integrations/rvc/climate_units.py`,
`backend/integrations/can/message_factory.py`), Apache-2.0, © carpenike.
