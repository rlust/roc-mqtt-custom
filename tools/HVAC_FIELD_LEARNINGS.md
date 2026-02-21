# HVAC Field Learnings (Mira / VegaTouch / RV-C)

Last updated: 2026-02-21

## Confirmed Working Signatures (Instance 0 thermostat)

### Setpoint nudges
- Up 1°F: `00FFFFFFFFFAFFFF`
- Down 1°F: `00FFFFFFFFF9FFFF`

Topic:
- `RVC/THERMOSTAT_COMMAND_1/0`

Observed status progression (staged):
- Up often applies as `cool` then `heat`
- Down often applies as `cool` then `heat`

### Fan mode/speed
- Fan High (On, 100): `00DFC8FFFFFFFFFF`
- Fan Low (On, 50): `00DF64FFFFFFFFFF`
- Fan Auto: `00CFFFFFFFFFFFFF`

Status confirmation topic:
- `RVC/THERMOSTAT_STATUS_1/0`

## Gating Behavior

Commands are accepted intermittently unless the control context is active.

Best observed reliability:
1. Keep VegaTouch on HVAC page (Front zone active).
2. Send burst+retry command.
3. If no change, do one quick VegaTouch nudge and retry.

This appears to be a controller acceptance gate (not a broker/tooling failure).

## Current Recommended CLI

Use wrapper (auto-venv, confirm, retry, burst):

```bash
./tools/thermostat_step.sh up
./tools/thermostat_step.sh down
```

Nudge flow is built in:
- first attempt
- if no change, prompt for manual tap
- automatic retry

## Known Good Runtime Context

From helper status samples when successful:
- operating mode: `cool`
- fan mode: `auto` or `on`
- instance: `0`

## Open Questions

- Exact unlock/handshake sequence that removes UI gating entirely.
- Whether a second control ingress (non-echo topic/API) exists for unconditional writes.
