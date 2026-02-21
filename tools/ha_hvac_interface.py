#!/usr/bin/env python3
import argparse
import json
import sys
import time

import paho.mqtt.client as mqtt


def capture_status_series(host, port, user, password, instance, seconds):
    topic = f"RVC/THERMOSTAT_STATUS_1/{instance}"
    rows = []

    def on_message(_c, _u, m):
        try:
            payload = json.loads(m.payload.decode())
        except Exception:
            payload = {"raw": m.payload.decode(errors="ignore")}
        rows.append(payload)

    c = mqtt.Client(client_id=f"ha_hvac_status_{int(time.time()*1000)}")
    c.username_pw_set(user, password)
    c.on_message = on_message
    c.connect(host, port, 60)
    c.subscribe(topic)
    c.loop_start()
    time.sleep(seconds)
    c.loop_stop()
    c.disconnect()
    return rows


def publish_burst(host, port, user, password, instance, data_hex, burst_seconds, burst_interval):
    topic = f"RVC/THERMOSTAT_COMMAND_1/{instance}"
    c = mqtt.Client(client_id=f"ha_hvac_cmd_{int(time.time())}")
    c.username_pw_set(user, password)
    c.connect(host, port, 60)
    sent = 0
    end = time.time() + burst_seconds
    while time.time() < end:
        payload = {
            "name": "THERMOSTAT_COMMAND_1",
            "instance": instance,
            "dgn": "1FEF9",
            "data": data_hex,
            "timestamp": f"{time.time():.6f}",
        }
        c.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0, retain=False)
        sent += 1
        time.sleep(burst_interval)
    c.disconnect()
    return sent


def status_view(status):
    return {
        "mode": status.get("operating mode definition"),
        "fan_mode": status.get("fan mode definition"),
        "fan_speed": status.get("fan speed"),
        "cool_f": status.get("setpoint temp cool F"),
        "heat_f": status.get("setpoint temp heat F"),
        "data": status.get("data"),
        "timestamp": status.get("timestamp"),
    }


def changed_for_action(action, baseline, candidate):
    bc, bh = baseline.get("cool_f"), baseline.get("heat_f")
    cc, ch = candidate.get("cool_f"), candidate.get("heat_f")

    if action == "temp_up":
        return (cc is not None and bc is not None and cc > bc) or (ch is not None and bh is not None and ch > bh)
    if action == "temp_down":
        return (cc is not None and bc is not None and cc < bc) or (ch is not None and bh is not None and ch < bh)
    if action == "fan_high":
        return candidate.get("fan_mode") == "on" and str(candidate.get("fan_speed")) == "100"
    if action == "fan_low":
        return candidate.get("fan_mode") == "on" and str(candidate.get("fan_speed")) == "50"
    if action == "fan_auto":
        return candidate.get("fan_mode") == "auto"
    return False


def action_data(action):
    return {
        "temp_up": "00FFFFFFFFFAFFFF",
        "temp_down": "00FFFFFFFFF9FFFF",
        "fan_high": "00DFC8FFFFFFFFFF",
        "fan_low": "00DF64FFFFFFFFFF",
        "fan_auto": "00CFFFFFFFFFFFFF",
    }[action]


def run_action(args):
    before = capture_status_series(args.host, args.port, args.user, args.password, args.instance, args.confirm_seconds)
    baseline = status_view(before[-1]) if before else {}

    observed = []
    success = False
    for attempt in range(1, args.retry + 1):
        sent = publish_burst(
            args.host,
            args.port,
            args.user,
            args.password,
            args.instance,
            action_data(args.action),
            args.burst_seconds,
            args.burst_interval,
        )
        after = capture_status_series(args.host, args.port, args.user, args.password, args.instance, args.confirm_seconds)
        views = [status_view(x) for x in after]
        observed.extend(views)
        if any(changed_for_action(args.action, baseline, v) for v in views):
            success = True
            break
        if attempt < args.retry:
            time.sleep(args.retry_delay)

    uniq = []
    seen = set()
    for v in observed:
        key = (v.get("cool_f"), v.get("heat_f"), v.get("fan_mode"), v.get("fan_speed"))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)

    result = {
        "ok": success,
        "action": args.action,
        "instance": args.instance,
        "baseline": baseline,
        "observed": uniq,
        "retry": args.retry,
        "burst_seconds": args.burst_seconds,
    }
    print(json.dumps(result, indent=2))
    return 0 if success else 1


def run_status(args):
    rows = capture_status_series(args.host, args.port, args.user, args.password, args.instance, args.confirm_seconds)
    latest = status_view(rows[-1]) if rows else {}
    print(json.dumps({"ok": bool(rows), "instance": args.instance, "latest": latest}, indent=2))
    return 0 if rows else 1


def main():
    ap = argparse.ArgumentParser(description="Home Assistant HVAC interface")
    ap.add_argument("--host", default="100.110.189.122")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="rc")
    ap.add_argument("--password", default="rc")
    ap.add_argument("--instance", type=int, default=0)
    ap.add_argument("--confirm-seconds", type=float, default=6.0)
    ap.add_argument("--retry", type=int, default=3)
    ap.add_argument("--retry-delay", type=float, default=2.0)
    ap.add_argument("--burst-seconds", type=float, default=6.0)
    ap.add_argument("--burst-interval", type=float, default=0.35)

    sub = ap.add_subparsers(dest="cmd", required=True)
    p_action = sub.add_parser("action")
    p_action.add_argument("--action", required=True, choices=["temp_up", "temp_down", "fan_high", "fan_low", "fan_auto"])
    p_status = sub.add_parser("status")

    args = ap.parse_args()
    rc = run_action(args) if args.cmd == "action" else run_status(args)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
