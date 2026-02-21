#!/usr/bin/env bash
set -euo pipefail

# Wrapper that always uses the known-good venv on the Mac mini.
VENV_PY="/Users/randylust/.openclaw/workspace/.venv-rvc/bin/python"
HELPER="/Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools/thermostat_command_helper.py"

if [[ ! -x "$VENV_PY" ]]; then
  echo "ERROR: venv python not found: $VENV_PY" >&2
  exit 1
fi

exec "$VENV_PY" "$HELPER" send-known "$@"
