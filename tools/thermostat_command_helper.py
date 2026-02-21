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
    data_hex = action_to_data(args.instance, args.action)
    payload = build_command_payload(args.instance, data_hex)
    topic = f"RVC/THERMOSTAT_COMMAND_1/{args.instance}"
    print(json.dumps({"topic": topic, "payload": payload}, indent=2))
    if args.dry_run:
        return
    publish(args.host, args.port, args.user, args.password, topic, payload)
    print("published")


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
