#!/usr/bin/env bash
set -euo pipefail

# Simple wrapper: thermostat_step.sh up|down [instance]
DIR="/Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools"
ACTION="${1:-}"
INSTANCE="${2:-0}"

case "$ACTION" in
  up) DELTA=1 ;;
  down) DELTA=-1 ;;
  *)
    echo "Usage: $0 up|down [instance]" >&2
    exit 2
    ;;
esac

exec "$DIR/thermostat_action.sh" \
  --instance "$INSTANCE" \
  --delta "$DELTA" \
  --confirm \
  --retry 3 \
  --retry-delay 2 \
  --target any \
  --burst-seconds 6 \
  --burst-interval 0.35
