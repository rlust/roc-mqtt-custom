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

run_once() {
  "$DIR/thermostat_action.sh" \
    --instance "$INSTANCE" \
    --delta "$DELTA" \
    --confirm \
    --retry 3 \
    --retry-delay 2 \
    --target any \
    --burst-seconds 6 \
    --burst-interval 0.35
}

echo "▶ Running thermostat $ACTION (instance $INSTANCE)..."
out1="$(run_once 2>&1)"
echo "$out1"

if echo "$out1" | grep -q '"changed": true'; then
  echo "✅ Applied without nudge."
  exit 0
fi

echo "⚠️ No change detected."
read -r -p "Open VegaTouch HVAC page, tap once (any temp nudge), then press Enter to retry... " _

out2="$(run_once 2>&1)"
echo "$out2"

if echo "$out2" | grep -q '"changed": true'; then
  echo "✅ Applied after nudge."
  exit 0
fi

echo "❌ Still no change after nudge."
exit 1
