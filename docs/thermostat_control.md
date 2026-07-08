# Thermostat Control — Architecture, Wire Protocol, and Rollout

*Added in v2.4.0. This document explains how absolute thermostat control works
in this integration, the RV-C wire protocol details it depends on, and the
safe process for enabling it on a coach.*

## Background

Through v2.3.x, climate control used **learned signatures**: byte patterns
captured by sniffing the CAN bus while pressing the physical Firefly panel
buttons, replayed as short MQTT bursts (temp up/down nudges). That works but
can't set an absolute temperature, can't set mode and setpoint together, and
depends on panel-specific captures.

In v2.4.0 the command path was rewritten using findings from the
[CoachIQ](https://github.com/carpenike/coachiq) project (Apache-2.0), whose
RV-C climate implementation was verified byte-for-byte on a live Entegra
Aspire Firefly G6 bus — the same platform this integration targets. That
comparison exposed three wire-level bugs in our old bridge (see
[Bugs found and fixed](#bugs-found-and-fixed)) and one design gap.

## Architecture

```
Home Assistant climate entity
        │  {"setpoint_f": 72}            (bridge mode ON, absolute commands)
        ▼
MQTT: rvcbridge/thermostat_control/<zone>
        │
thermostat_command_bridge.py
        │  validate → rate-limit → fill unchanged fields from state cache
        │  → encode THERMOSTAT_COMMAND_1 → TX
        ▼
CAN bus: 0x19FEF9F9  [instance|mode/fan|speed|heat_lo|heat_hi|cool_lo|cool_hi|FF]
        │
Firefly G6 (owns all safety interlocks; may honor, shed, or ignore)
        │
        ▼  THERMOSTAT_STATUS_1 (1FFE2) echo
MQTT: RVC/THERMOSTAT_STATUS_1/<zone>  →  bridge state cache + "confirmed" ack
                                      →  HA entity state update
```

Key principle (from CoachIQ): **we never command the rooftop AC units
directly** (AIR_CONDITIONER_COMMAND, 1FFE0). The G6 rebroadcasts AC commands
at 1 Hz per unit, so commanding units directly fights the master controller.
We command the *thermostat zones* and let the G6 drive the hardware.

## Wire protocol

### THERMOSTAT_COMMAND_1 (DGN 0x1FEF9)

29-bit arbitration ID: `(priority << 26) | (PGN << 8) | source_address`
- priority 6, PGN 0x1FEF9, SA 0xF9 → **0x19FEF9F9**

8-byte payload (mirrors THERMOSTAT_STATUS_1, 0x1FFE2):

| Byte | Field | Encoding |
|---|---|---|
| 0 | instance | zone number (0–6 on Aspire) |
| 1 | mode byte | bits 0–3 operating mode, 4–5 fan mode, 6–7 schedule mode |
| 2 | fan speed | **half-percent, 0–200** (0xC8 = 100%, 0 = automatic) |
| 3–4 | heat setpoint | **uint16 LE, 1/32 K steps**: raw = (°C + 273) × 32 |
| 5–6 | cool setpoint | same encoding |
| 7 | reserved | 0xFF |

Operating modes: 0=off, 1=cool, 2=heat, 3=auto, 4=fan_only, 5=aux_heat.
Fan modes: 0=auto, 1=on.

Worked example — zone 0, cool, 72 °F, fan auto:
72 °F = 22.22 °C → raw = (22.22 + 273) × 32 = **9447** = 0x24E7 (LE: `E7 24`)
→ payload `00 01 00 E7 24 E7 24 FF`, arbitration ID `0x19FEF9F9`.

### Full-state semantics (why the state cache exists)

THERMOSTAT_COMMAND_1 carries the **entire zone state** in one frame — there
are no reliable per-field "no change" sentinels with the G6. The bridge
therefore caches each zone's last observed THERMOSTAT_STATUS_1 and overlays
only the fields present in your MQTT payload. Consequences:

- `{"setpoint_f": 71}` changes only the setpoint; mode and fan are preserved.
- A zone whose status has never been seen on the bus is **NACKed**
  (`no_status_seen`) rather than commanded with invented defaults.
  Override with `--allow-unseeded` (not recommended).
- `setpoint_f` drives heat and cool setpoints together, matching how the G6
  keeps them in lockstep.

### Command confirmation

Command/status DGN pair: 1FEF9 → 1FFE2. After a transmit, the bridge watches
for the zone's next status echo; if mode and setpoints match, it publishes
`{"status": "confirmed"}` on `rvcbridge/thermostat_control/ack` (window:
`--confirm-window`, default 5 s).

## Bugs found and fixed (v2.4.0)

| # | Bug (≤ v2.3.x) | Fix |
|---|---|---|
| 1 | Setpoints encoded as °C×100 (72 °F → 2222) | Table 5.3: (°C+273)×32 (72 °F → 9447) |
| 2 | Arbitration ID was the bare PGN (`0x0001FEF9`) | `(6<<26)\|(PGN<<8)\|0xF9` = `0x19FEF9F9` |
| 3 | Fan speed sent 0–100, default 50 | half-percent 0–200, default 0 (auto) |
| 4 | Missing fields defaulted (cool/50%/72 °F) | filled from live zone state; NACK if unseen |

Frames with bugs 1–2 were never actionable by the G6 — which is why the
learned-signature approach was needed at the time.

## MQTT interface

**Control** (publish): `rvcbridge/thermostat_control/<zone>`

```json
{"setpoint_f": 72}
{"mode": "cool"}
{"mode": 1, "setpoint_f": 70}
{"fan_mode": "on", "fan_speed_pct": 100}
{"setpoint_heat_f": 66, "setpoint_cool_f": 76}
```

Legacy `{"operating_mode": 1}` payloads are still accepted.

**Feedback** (subscribe): `rvcbridge/thermostat_control/ack`, `.../nack`,
`rvcbridge/audit/thermostat_control`.

Zone map (Entegra Aspire, verify per coach): 0=Front, 1=Mid, 2=Rear (cool);
3=Front heat, 4=Rear heat (Aqua-Hot); 5=Bay heat; 6=Floor heat.

## Running the bridge

```bash
# 1. Monitor-only (default): validates and audits, never transmits
python3 thermostat_command_bridge.py --broker <mqtt-ip>

# 2. Dry-run with TX logging
python3 thermostat_command_bridge.py --broker <mqtt-ip> --dry-run

# 3. Live
python3 thermostat_command_bridge.py --broker <mqtt-ip> --tx-enable
```

Useful flags: `--source-address 0xF9`, `--priority 6`,
`--status-topics RVC/THERMOSTAT_STATUS_1/+ rvc/status/climate/+`,
`--status-max-age 300`, `--min-interval 0.25`, `--handoff` (publish prebuilt
frames to MQTT instead of CAN TX).

`rvc_climate_units.py` must be in the same directory.

## Home Assistant setup

1. Update to v2.4.0+ and restart HA.
2. Settings → Devices & Services → RV-C → **Configure**.
3. Enable **Thermostat bridge mode** and confirm the bridge control topic
   (default `rvcbridge/thermostat_control`).
4. Climate entities now send absolute setpoint/mode/fan commands. With the
   toggle off, the legacy learned-signature behavior is unchanged.

## Safe rollout process (do this in order)

1. **Bridge in monitor-only** — send test commands, review the audit topic.
2. **Golden-frame check** — `candump can1 | grep 19FEF9` while pressing a
   temperature button on the physical panel; compare against the bridge's
   dry-run frame for the same change. Bytes should match (except source
   address).
3. **One zone, one change** — `--tx-enable`, single setpoint change, confirm
   the panel reflects it and the ack topic shows `"confirmed"`.
4. **Panel override test** — immediately change the same zone from the
   physical panel; it must win without a fight.
5. Enable bridge mode in HA.

Remember: this is convenience automation. The Firefly G6 owns all safety
interlocks and may shed or ignore any command (status level 0xFC/0xFD =
requested but shed).

## Tests

```bash
python3 -m pytest tests/test_climate_units.py tests/test_thermostat_bridge.py -v
```

25 cases: encoding round-trips (40–105 °F), golden frame bytes, arbitration
ID construction, state fill-in behavior, validation/NACK paths, status
parsing (raw `data` hex preferred, named decoder fields as fallback).

## Attribution

Encoding logic ported from CoachIQ
(`backend/integrations/rvc/climate_units.py`,
`backend/integrations/can/message_factory.py`), Apache-2.0, © carpenike.
Wire behavior (Table 5.3 encoding, SA acceptance, full-state semantics, G6
AC-command rebroadcast, load-shed sentinels) was verified in that project on
a live 2021 Entegra Aspire 44R.
