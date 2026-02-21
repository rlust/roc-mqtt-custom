# AC Command Path Runbook (Aspire)

Use this path first for HVAC control:
- Command: `RVC/AIR_CONDITIONER_COMMAND/<instance>`
- Status: `RVC/AIR_CONDITIONER_STATUS/<instance>`
- Broker: `100.110.189.122:1883` (`rc`/`rc`)

## 1) Watch status (example instance 1)

```bash
python3 tools/ac_status_watch.py --instance 1 --seconds 20
```

## 2) Publish command safely (dry-run first)

```bash
python3 tools/ac_command_publish.py --instance 1 --mode 0 --fan-speed 50 --dry-run
```

## 3) Publish actual command

```bash
python3 tools/ac_command_publish.py --instance 1 --mode 0 --fan-speed 50
```

## 4) Verify

Watch for correlated update on `RVC/AIR_CONDITIONER_STATUS/1` within 2–5 seconds.

## Thermostat helper (recommended for setpoint testing)

Use the helper for `THERMOSTAT_COMMAND_1` signatures discovered from live VegaTouch actions:

```bash
# Dry run known-good signatures (instance 0)
python3 tools/thermostat_command_helper.py send-known --instance 0 --action down1 --dry-run
python3 tools/thermostat_command_helper.py send-known --instance 0 --action up1 --dry-run

# Publish one
python3 tools/thermostat_command_helper.py send-known --instance 0 --action down1
# or
python3 tools/thermostat_command_helper.py send-known --instance 0 --action up1

# New shortcut form
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta -1
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta 1

# Publish + auto-verify status changed
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta -1 --confirm
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta 1 --confirm

# 1) Inspect current HVAC mode + fan + setpoints (recommended first)
python3 tools/thermostat_command_helper.py status --instance 0 --seconds 6

# 2) Retry mode (sticky controller handling)
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta 1 --confirm --retry 3 --retry-delay 2 --target any

# 3) Auto-probe on fail (captures broad topics when retries don't move status)
python3 tools/thermostat_command_helper.py send-known --instance 0 --delta 1 --confirm --retry 3 --auto-probe-on-fail --probe-seconds 20 --probe-out captures/auto-probe-on-fail.jsonl

# Mac mini convenience wrapper (uses .venv-rvc automatically)
./tools/thermostat_action.sh --instance 0 --delta 1 --confirm --retry 3 --auto-probe-on-fail

# 4) Manual capture command/status for live reverse engineering
python3 tools/thermostat_command_helper.py capture --instance 0 --seconds 20 --out captures/thermostat-capture.jsonl
```

## Notes

- Keep one-zone-at-a-time changes.
- Space commands by >=2s.
- If command publishes but no status delta, inspect downstream CAN transmitter filters.
