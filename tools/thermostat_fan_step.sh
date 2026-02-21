#!/usr/bin/env bash
set -euo pipefail

# Usage: thermostat_fan_step.sh high|low|auto [instance]
DIR="/Users/randylust/.openclaw/workspace/roc-mqtt-custom/tools"
ACTION="${1:-}"
INSTANCE="${2:-0}"
HOST="100.110.189.122"
PORT="1883"
USER="rc"
PASS="rc"

case "$ACTION" in
  high)
    DATA="00DFC8FFFFFFFFFF"
    EXPECT_MODE="on"
    EXPECT_SPEED="100"
    ;;
  low)
    DATA="00DF64FFFFFFFFFF"
    EXPECT_MODE="on"
    EXPECT_SPEED="50"
    ;;
  auto)
    DATA="00CFFFFFFFFFFFFF"
    EXPECT_MODE="auto"
    EXPECT_SPEED="50"
    ;;
  *)
    echo "Usage: $0 high|low|auto [instance]" >&2
    exit 2
    ;;
esac

read_mode_speed() {
  local payload
  payload="$(mosquitto_sub -h "$HOST" -p "$PORT" -u "$USER" -P "$PASS" -t "RVC/THERMOSTAT_STATUS_1/${INSTANCE}" -C 1 -W 8 2>/dev/null || true)"
  if [[ -z "$payload" ]]; then
    echo "unknown unknown"
    return 0
  fi
  python3 - <<'PY' "$payload"
import json,sys
try:
    j=json.loads(sys.argv[1])
    print(str(j.get('fan mode definition','unknown')), str(j.get('fan speed','unknown')))
except Exception:
    print('unknown unknown')
PY
}

publish_burst() {
  local end=$((SECONDS+6))
  while [ $SECONDS -lt $end ]; do
    mosquitto_pub -h "$HOST" -p "$PORT" -u "$USER" -P "$PASS" \
      -t "RVC/THERMOSTAT_COMMAND_1/${INSTANCE}" \
      -m "{\"name\":\"THERMOSTAT_COMMAND_1\",\"instance\":${INSTANCE},\"dgn\":\"1FEF9\",\"data\":\"${DATA}\",\"timestamp\":\"$(python3 - <<'PY'
import time
print(f"{time.time():.6f}")
PY
)\"}" >/dev/null 2>&1 || true
    sleep 0.35
  done
}

attempt() {
  echo "▶ Fan $ACTION attempt..."
  local bmode bspeed amode aspeed
  read -r bmode bspeed <<<"$(read_mode_speed)"
  echo "before: mode=$bmode speed=$bspeed"

  publish_burst

  read -r amode aspeed <<<"$(read_mode_speed)"
  echo "after:  mode=$amode speed=$aspeed"

  if [[ "$amode" == "$EXPECT_MODE" && "$aspeed" == "$EXPECT_SPEED" ]]; then
    echo "✅ Fan applied ($ACTION)."
    return 0
  fi
  echo "⚠️ Fan not applied yet."
  return 1
}

if attempt; then
  exit 0
fi

read -r -p "Open VegaTouch HVAC page, tap fan once (High/Low/Auto area), then press Enter to retry... " _

if attempt; then
  echo "✅ Fan applied after nudge."
  exit 0
fi

echo "❌ Fan still not applied after nudge."
exit 1
