#!/usr/bin/env python3
"""
RV-C Thermostat Command Bridge (Aspire profile)

Subscribes to: rvcbridge/thermostat_control/+
Validates + rate-limits control messages
Builds PGN 0x1FFE2 thermostat command payloads
Transmits on CAN1 (or dry-run)

Usage:
  python3 thermostat_command_bridge.py --dry-run
  python3 thermostat_command_bridge.py --broker 192.168.100.234 --tx-enable

Notes:
- Safe by default: monitor-only unless --tx-enable is provided
- CAN send uses python-can when available; otherwise logs the frame
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import paho.mqtt.client as mqtt

try:
    import can  # type: ignore
except Exception:
    can = None


DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(__file__), "thermostat_pgn_map_aspire.json"
)


@dataclass
class Limits:
    min_temp_f: float = 50.0
    max_temp_f: float = 95.0
    min_instance: int = 0
    max_instance: int = 6
    max_fan_speed: int = 100


class ThermostatBridge:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.profile = self._load_profile(args.profile)
        self.limits = Limits()
        self.last_sent_by_instance: Dict[int, float] = {}
        self.min_interval_s = args.min_interval
        self.tx_enabled = bool(args.tx_enable)

        self.pgn = int(self.profile["pgns"]["thermostat_status_1"]["hex"], 16)

        self.mqtt = mqtt.Client(client_id="rvc_thermostat_bridge")
        if args.username and args.password:
            self.mqtt.username_pw_set(args.username, args.password)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message

        self.can_bus = None
        if self.tx_enabled and not args.dry_run:
            self.can_bus = self._setup_can_bus()

    @staticmethod
    def _load_profile(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _setup_can_bus(self):
        if can is None:
            print("⚠️ python-can not installed; falling back to log-only mode")
            return None
        try:
            bus = can.interface.Bus(
                interface=self.args.can_interface,
                channel=self.args.can_channel,
                bitrate=self.args.can_bitrate,
            )
            print(
                f"✅ CAN ready: interface={self.args.can_interface} "
                f"channel={self.args.can_channel} bitrate={self.args.can_bitrate}"
            )
            return bus
        except Exception as e:
            print(f"⚠️ CAN init failed ({e}); falling back to log-only mode")
            return None

    def on_connect(self, client, _userdata, _flags, rc):
        if rc != 0:
            print(f"❌ MQTT connect failed rc={rc}")
            return
        topic = self.profile["default_topics"]["control"]
        client.subscribe(topic)
        print(f"✅ MQTT connected; subscribed to {topic}")
        print(
            f"🔒 TX enabled={self.tx_enabled} dry_run={self.args.dry_run} "
            f"min_interval={self.min_interval_s}s"
        )

    def on_message(self, client, _userdata, msg):
        now = time.time()
        topic = msg.topic

        # Guard: only process per-instance control topics like
        # rvcbridge/thermostat_control/<instance>
        ok, instance_or_err = self.parse_instance(topic)
        if not ok:
            return
        instance = instance_or_err

        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            self.publish_nack("invalid_json", topic, msg.payload.decode("utf-8", "ignore"))
            return

        valid, reason = self.validate(instance, payload, now)
        if not valid:
            self.publish_nack(reason, topic, payload)
            return

        frame = self.build_frame(instance, payload)
        self.publish_audit(topic, payload, frame)

        if not self.tx_enabled:
            self.publish_ack("monitor_only", topic, payload, frame)
            return

        sent = self.send_can(frame)
        self.publish_ack("sent" if sent else "logged_only", topic, payload, frame)

    @staticmethod
    def parse_instance(topic: str) -> Tuple[bool, int | str]:
        parts = topic.split("/")
        if len(parts) != 3:
            return False, "bad_topic_shape"
        if parts[0] != "rvcbridge" or parts[1] != "thermostat_control":
            return False, "not_control_topic"
        if not parts[2].isdigit():
            return False, "bad_instance"
        return True, int(parts[2])

    def validate(self, instance: int, payload: dict, now: float) -> Tuple[bool, str]:
        if not (self.limits.min_instance <= instance <= self.limits.max_instance):
            return False, f"instance_out_of_range:{instance}"

        last = self.last_sent_by_instance.get(instance)
        if last and (now - last) < self.min_interval_s:
            return False, f"rate_limited:{instance}"

        mode = payload.get("mode")
        if mode is not None and int(mode) not in (0, 1, 2, 3, 4):
            return False, f"bad_mode:{mode}"

        fan_mode = payload.get("fan_mode")
        if fan_mode is not None and int(fan_mode) not in (0, 1):
            return False, f"bad_fan_mode:{fan_mode}"

        fan_speed = payload.get("fan_speed", 50)
        if not isinstance(fan_speed, (int, float)) or not (0 <= int(fan_speed) <= self.limits.max_fan_speed):
            return False, f"bad_fan_speed:{fan_speed}"

        # Temperature validation supports either combined or split setpoints
        setpoint_f = payload.get("setpoint_f")
        heat_f = payload.get("setpoint_heat_f", setpoint_f)
        cool_f = payload.get("setpoint_cool_f", setpoint_f)

        if heat_f is None and payload.get("setpoint_heat_c") is None:
            heat_f = 72.0
        if cool_f is None and payload.get("setpoint_cool_c") is None:
            cool_f = 72.0

        def in_range_f(v: Optional[float]) -> bool:
            return v is None or (self.limits.min_temp_f <= float(v) <= self.limits.max_temp_f)

        if not in_range_f(heat_f):
            return False, f"bad_setpoint_heat_f:{heat_f}"
        if not in_range_f(cool_f):
            return False, f"bad_setpoint_cool_f:{cool_f}"

        return True, "ok"

    @staticmethod
    def f_to_c100(vf: float) -> int:
        return int(round((vf - 32.0) * 5.0 / 9.0 * 100.0))

    @staticmethod
    def c_to_c100(vc: float) -> int:
        return int(round(vc * 100.0))

    def build_frame(self, instance: int, payload: dict) -> dict:
        mode = int(payload.get("mode", 1))  # default cool
        fan_mode = int(payload.get("fan_mode", 0))  # default auto
        schedule_mode = int(payload.get("schedule_mode", 0))
        fan_speed = int(payload.get("fan_speed", 50))

        setpoint_f = payload.get("setpoint_f")
        heat_f = payload.get("setpoint_heat_f", setpoint_f)
        cool_f = payload.get("setpoint_cool_f", setpoint_f)

        heat_c = payload.get("setpoint_heat_c")
        cool_c = payload.get("setpoint_cool_c")

        heat_c100 = self.c_to_c100(float(heat_c)) if heat_c is not None else self.f_to_c100(float(heat_f or 72.0))
        cool_c100 = self.c_to_c100(float(cool_c)) if cool_c is not None else self.f_to_c100(float(cool_f or 72.0))

        b1 = (mode & 0x0F) | ((fan_mode & 0x03) << 4) | ((schedule_mode & 0x03) << 6)

        data = [
            instance & 0xFF,
            b1,
            fan_speed & 0xFF,
            heat_c100 & 0xFF,
            (heat_c100 >> 8) & 0xFF,
            cool_c100 & 0xFF,
            (cool_c100 >> 8) & 0xFF,
            0xFF,
        ]

        return {
            "pgn": self.pgn,
            "pgn_hex": f"0x{self.pgn:05X}",
            "instance": instance,
            "data": data,
            "data_hex": "".join(f"{b:02X}" for b in data),
            "mode": mode,
            "fan_mode": fan_mode,
            "fan_speed": fan_speed,
            "setpoint_heat_c100": heat_c100,
            "setpoint_cool_c100": cool_c100,
        }

    def send_can(self, frame: dict) -> bool:
        self.last_sent_by_instance[frame["instance"]] = time.time()
        if self.args.dry_run or self.can_bus is None:
            print(f"🧪 DRY/LOG TX CAN1 {frame['pgn_hex']} data={frame['data_hex']}")
            return False

        try:
            arbitration_id = frame["pgn"]
            msg = can.Message(arbitration_id=arbitration_id, data=frame["data"], is_extended_id=True)
            self.can_bus.send(msg)
            print(f"✅ CAN1 TX {frame['pgn_hex']} data={frame['data_hex']}")
            return True
        except Exception as e:
            print(f"❌ CAN send failed: {e}")
            return False

    def publish_ack(self, status: str, topic: str, payload: dict, frame: dict):
        ack_topic = self.profile["default_topics"]["ack"]
        msg = {
            "status": status,
            "topic": topic,
            "payload": payload,
            "frame": frame,
            "ts": time.time(),
        }
        self.mqtt.publish(ack_topic, json.dumps(msg), qos=0, retain=False)

    def publish_nack(self, reason: str, topic: str, payload):
        nack_topic = self.profile["default_topics"]["nack"]
        msg = {
            "status": "nack",
            "reason": reason,
            "topic": topic,
            "payload": payload,
            "ts": time.time(),
        }
        self.mqtt.publish(nack_topic, json.dumps(msg), qos=0, retain=False)
        print(f"⛔ NACK {reason} topic={topic}")

    def publish_audit(self, topic: str, payload: dict, frame: dict):
        audit_topic = self.profile["default_topics"]["audit"]
        msg = {
            "topic": topic,
            "payload": payload,
            "frame": frame,
            "tx_enabled": self.tx_enabled,
            "ts": time.time(),
        }
        self.mqtt.publish(audit_topic, json.dumps(msg), qos=0, retain=False)

    def run(self):
        self.mqtt.connect(self.args.broker, self.args.port, 60)
        self.mqtt.loop_forever()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RV-C thermostat command bridge")
    p.add_argument("--broker", default="192.168.100.234")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--username", default="rc")
    p.add_argument("--password", default="rc")
    p.add_argument("--profile", default=DEFAULT_PROFILE_PATH)

    p.add_argument("--tx-enable", action="store_true", help="Enable CAN transmit (default monitor-only)")
    p.add_argument("--dry-run", action="store_true", help="Never transmit on CAN; log frames only")
    p.add_argument("--min-interval", type=float, default=0.25, help="Per-zone minimum command interval (seconds)")

    p.add_argument("--can-interface", default="socketcan")
    p.add_argument("--can-channel", default="can0")
    p.add_argument("--can-bitrate", type=int, default=250000)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    bridge = ThermostatBridge(args)
    bridge.run()
