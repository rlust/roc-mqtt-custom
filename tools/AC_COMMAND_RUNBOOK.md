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

## Notes

- Keep one-zone-at-a-time changes.
- Space commands by >=2s.
- If command publishes but no status delta, inspect downstream CAN transmitter filters.
