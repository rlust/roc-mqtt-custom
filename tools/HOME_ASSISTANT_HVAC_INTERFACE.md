# Home Assistant HVAC Interface (Mira / RV-C)

This interface exposes the field-proven thermostat/fan command flow to Home Assistant.

## Files

- `tools/ha_hvac_interface.py` — machine-friendly command/status interface (JSON output + exit code)
- `tools/thermostat_action.sh` — venv-safe helper wrapper
- `tools/thermostat_step.sh` — interactive temp step tool (human-driven)
- `tools/thermostat_fan_step.sh` — interactive fan step tool (human-driven)

Use `ha_hvac_interface.py` for HA automations/scripts (non-interactive).

---

## Actions supported

`ha_hvac_interface.py action --action <name>`

- `temp_up`
- `temp_down`
- `fan_high`
- `fan_low`
- `fan_auto`

And status:

- `ha_hvac_interface.py status`

---

## Command examples (on Mac mini)

```bash
# Status
/Users/randylust/.openclaw/workspace/.venv-rvc/bin/python \
  /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py \
  --instance 0 status

# Temp up
/Users/randylust/.openclaw/workspace/.venv-rvc/bin/python \
  /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py \
  --instance 0 action --action temp_up

# Fan low
/Users/randylust/.openclaw/workspace/.venv-rvc/bin/python \
  /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py \
  --instance 0 action --action fan_low
```

Exit code:
- `0` => success (`ok: true`)
- `1` => command did not apply (`ok: false`, likely gate active)

---

## Home Assistant YAML (example)

Add to `configuration.yaml` (or split packages):

```yaml
shell_command:
  mira_hvac_temp_up: >-
    /Users/randylust/.openclaw/workspace/.venv-rvc/bin/python
    /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py
    --instance 0 action --action temp_up
  mira_hvac_temp_down: >-
    /Users/randylust/.openclaw/workspace/.venv-rvc/bin/python
    /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py
    --instance 0 action --action temp_down
  mira_hvac_fan_high: >-
    /Users/randylust/.openclaw/workspace/.venv-rvc/bin/python
    /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py
    --instance 0 action --action fan_high
  mira_hvac_fan_low: >-
    /Users/randylust/.openclaw/workspace/.venv-rvc/bin/python
    /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py
    --instance 0 action --action fan_low
  mira_hvac_fan_auto: >-
    /Users/randylust/.openclaw/workspace/.venv-rvc/bin/python
    /Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/ha_hvac_interface.py
    --instance 0 action --action fan_auto
```

Then scripts (example):

```yaml
script:
  mira_temp_up:
    alias: Mira HVAC Temp Up
    mode: restart
    sequence:
      - action: shell_command.mira_hvac_temp_up

  mira_temp_down:
    alias: Mira HVAC Temp Down
    mode: restart
    sequence:
      - action: shell_command.mira_hvac_temp_down

  mira_fan_high:
    alias: Mira HVAC Fan High
    mode: restart
    sequence:
      - action: shell_command.mira_hvac_fan_high

  mira_fan_low:
    alias: Mira HVAC Fan Low
    mode: restart
    sequence:
      - action: shell_command.mira_hvac_fan_low

  mira_fan_auto:
    alias: Mira HVAC Fan Auto
    mode: restart
    sequence:
      - action: shell_command.mira_hvac_fan_auto
```

---

## Reliability notes

- Commands are still state-gated by controller/UI context.
- This interface uses burst + retry + confirm to maximize reliability.
- If `ok: false`, command was published but not accepted in that window.
- Best results when VegaTouch HVAC page is active.

See also: `tools/HVAC_FIELD_LEARNINGS.md`.
