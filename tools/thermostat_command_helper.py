#!/usr/bin/env python3
"""
Thermostat command helper for RV-C MQTT.

Use cases:
- Publish a known-good "down 1°F" command signature.
- Publish any raw THERMOSTAT_COMMAND_1 payload data.
- Capture command+status traffic for a short window to discover new signatures.
"""

import argparse
import json
import time
from pathlib import Path

import paho.mqtt.client as mqtt


def build_command_payload(instance: int, data_hex: str) -> dict:
    return {
        "name": "THERMOSTAT_COMMAND_1",
        "instance": instance,
        "dgn": "1FEF9",
        "data": data_hex.upper(),
        "timestamp": f"{time.time():.6f}",
    }


def publish(host: str, port: int, user: str, password: str, topic: str, payload: dict) -> None:
    c = mqtt.Client(client_id=f"therm_cmd_helper_{int(time.time())}")
    c.username_pw_set(user, password)
    c.connect(host, port, 60)
    c.publish(topic, json.dumps(payload, separators=(",", ":")), qos=0, retain=False)
    c.disconnect()


def get_latest_status(host: str, port: int, user: str, password: str, instance: int, timeout_s: float = 6.0):
    topic = f"RVC/THERMOSTAT_STATUS_1/{instance}"
    latest = {"payload": None}

    def on_message(_c, _u, m):
        try:
            latest["payload"] = json.loads(m.payload.decode())
        except Exception:
            latest["payload"] = {"raw": m.payload.decode(errors="ignore")}

    c = mqtt.Client(client_id=f"therm_status_once_{int(time.time()*1000)}")
    c.username_pw_set(user, password)
    c.on_message = on_message
    c.connect(host, port, 60)
    c.subscribe(topic)
    c.loop_start()
    start = time.time()
    while time.time() - start < timeout_s:
        if latest["payload"] is not None:
            break
        time.sleep(0.05)
    c.loop_stop()
    c.disconnect()
    return latest["payload"]


def _extract_setpoints(status_payload):
    if not isinstance(status_payload, dict):
        return None, None
    return status_payload.get("setpoint temp cool F"), status_payload.get("setpoint temp heat F")


def action_to_data(instance: int, action: str) -> str:
    # Known-good signatures captured during manual VegaTouch setpoint actions.
    # First byte tracks instance.
    prefix = f"{instance:02X}"
    if action == "down1":
        return prefix + "FFFFFFFFF9FFFF"
    if action == "up1":
        return prefix + "FFFFFFFFFAFFFF"
    raise ValueError(f"Unsupported action: {action}")


def cmd_send_known(args):
    action = args.action
    if args.delta is not None:
        if args.delta == 1:
            action = "up1"
        elif args.delta == -1:
            action = "down1"
        else:
            raise ValueError("--delta supports only +1 or -1")

    data_hex = action_to_data(args.instance, action)
    payload = build_command_payload(args.instance, data_hex)
    topic = f"RVC/THERMOSTAT_COMMAND_1/{args.instance}"
    print(json.dumps({"topic": topic, "payload": payload, "resolved_action": action}, indent=2))
    if args.dry_run:
        return

    before = None
    if args.confirm:
        before = get_latest_status(args.host, args.port, args.user, args.password, args.instance, args.confirm_timeout)

    publish(args.host, args.port, args.user, args.password, topic, payload)
    print("published")

    if args.confirm:
        after = get_latest_status(args.host, args.port, args.user, args.password, args.instance, args.confirm_timeout)
        before_cool, before_heat = _extract_setpoints(before)
        after_cool, after_heat = _extract_setpoints(after)
        changed = (before_cool != after_cool) or (before_heat != after_heat)
        print(json.dumps({
            "confirm": {
                "instance": args.instance,
                "before": {"cool_f": before_cool, "heat_f": before_heat},
                "after": {"cool_f": after_cool, "heat_f": after_heat},
                "changed": changed,
                "timeout_s": args.confirm_timeout
            }
        }, indent=2))


def cmd_send_raw(args):
    payload = build_command_payload(args.instance, args.data)
    topic = f"RVC/THERMOSTAT_COMMAND_1/{args.instance}"
    print(json.dumps({"topic": topic, "payload": payload}, indent=2))
    if args.dry_run:
        return
    publish(args.host, args.port, args.user, args.password, topic, payload)
    print("published")


def cmd_capture(args):
    rows = []
    topics = [
        f"RVC/THERMOSTAT_COMMAND_1/{args.instance}",
        f"RVC/THERMOSTAT_STATUS_1/{args.instance}",
    ]

    def on_message(_c, _u, m):
        try:
            payload = json.loads(m.payload.decode())
        except Exception:
            payload = {"raw": m.payload.decode(errors="ignore")}
        row = {
            "ts": time.time(),
            "topic": m.topic,
            "payload": payload,
        }
        rows.append(row)
        print(json.dumps(row, separators=(",", ":")))

    c = mqtt.Client(client_id=f"therm_cmd_capture_{int(time.time())}")
    c.username_pw_set(args.user, args.password)
    c.on_message = on_message
    c.connect(args.host, args.port, 60)
    for t in topics:
        c.subscribe(t)
    c.loop_start()
    time.sleep(args.seconds)
    c.loop_stop()
    c.disconnect()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8")
    print(f"saved={out} messages={len(rows)}")



def main():
    ap = argparse.ArgumentParser(description="Thermostat command helper")
    ap.add_argument("--host", default="100.110.189.122")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--user", default="rc")
    ap.add_argument("--password", default="rc")

    sub = ap.add_subparsers(dest="cmd", required=True)

    p_known = sub.add_parser("send-known", help="Send known-good action signature")
    p_known.add_argument("--instance", type=int, default=0)
    p_known.add_argument("--action", choices=["down1", "up1"], default="down1")
    p_known.add_argument("--delta", type=int, choices=[-1, 1], help="Alternative to --action: -1=down1, +1=up1")
    p_known.add_argument("--confirm", action="store_true", help="Read status before/after publish and report setpoint change")
    p_known.add_argument("--confirm-timeout", type=float, default=6.0, help="Seconds to wait for each status read")
    p_known.add_argument("--dry-run", action="store_true")
    p_known.set_defaults(func=cmd_send_known)

    p_raw = sub.add_parser("send-raw", help="Send raw THERMOSTAT_COMMAND_1 data")
    p_raw.add_argument("--instance", type=int, default=0)
    p_raw.add_argument("--data", required=True, help="16-hex-byte data field, e.g. 00FFFFFFFFF9FFFF")
    p_raw.add_argument("--dry-run", action="store_true")
    p_raw.set_defaults(func=cmd_send_raw)

    p_cap = sub.add_parser("capture", help="Capture command/status for instance")
    p_cap.add_argument("--instance", type=int, default=0)
    p_cap.add_argument("--seconds", type=int, default=20)
    p_cap.add_argument("--out", default="captures/thermostat-capture.jsonl")
    p_cap.set_defaults(func=cmd_capture)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
