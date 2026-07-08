#!/usr/bin/env python3
"""
RV-C Thermostat Command Bridge (Aspire profile) - v2

Subscribes to: rvcbridge/thermostat_control/+  (absolute zone commands)
           and RVC/THERMOSTAT_STATUS_1/+       (zone state cache + ack echo)
Validates + rate-limits control messages, fills unchanged fields from the
zone's live state, builds THERMOSTAT_COMMAND_1 (0x1FEF9) frames with correct
RV-C Table 5.3 temperature encoding and a proper 29-bit arbitration ID, and
transmits on CAN (or dry-run / MQTT handoff).

v2 changes (ported from CoachIQ, github.com/carpenike/coachiq, Apache-2.0,
verified on a live Entegra Aspire Firefly G6 bus):
  * Setpoints encoded as uint16 1/32-K steps (raw=(degC+273)*32), NOT degC*100
  * Arbitration ID = (prio<<26)|(PGN<<8)|SA  -> 0x19FEF9F9, not bare PGN
  * Fan speed encoded half-percent 0-200; 0 = automatic (new default)
  * Full-state fill-in: THERMOSTAT_COMMAND_1 carries the entire zone state,
    so unchanged fields come from the last observed THERMOSTAT_STATUS_1.
    A zone that has never been seen on the bus is NACKed (no invented
    defaults) unless --allow-unseeded is given.
  * Command confirmation: the next matching status echo publishes
    {"status": "confirmed"} on the ack topic (dgn pair 1FEF9 -> 1FFE2).

Usage:
  python3 thermostat_command_bridge.py --dry-run
  python3 thermostat_command_bridge.py --broker 192.168.100.234 --tx-enable

Safe by default: monitor-only unless --tx-enable is provided.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import rvc_climate_units as cu

try:
    import paho.mqtt.client as mqtt  # type: ignore
except Exception:  # pragma: no cover - exercised only without paho installed
    mqtt = None

try:
    import can  # type: ignore
except Exception:
    can = None


DEFAULT_PROFILE_PATH = os.path.join(
    os.path.dirname(__file__), "thermostat_pgn_map_aspire.json"
)

DEFAULT_STATUS_TOPICS = (
    "RVC/THERMOSTAT_STATUS_1/+",
    "rvc/status/climate/+",
)


@dataclass
class Limits:
    min_temp_f: float = cu.SETPOINT_MIN_F
    max_temp_f: float = cu.SETPOINT_MAX_F
    min_instance: int = 0
    max_instance: int = 6
    max_fan_speed_pct: int = cu.FAN_SPEED_MAX_PCT


@dataclass
class ZoneState:
    """Last observed raw THERMOSTAT_STATUS_1 fields for one zone."""

    operating_mode: int
    fan_mode: int
    schedule_mode: int
    fan_speed_raw: int
    setpoint_heat_raw: int
    setpoint_cool_raw: int
    ts: float = field(default_factory=time.time)


def parse_status_payload(payload: dict) -> Optional[dict]:
    """
    Extract raw thermostat fields from a status JSON message.

    Prefers the raw 8-byte `data` hex (exact), falls back to named fields
    produced by common RVC MQTT decoders ("operating mode", "fan mode",
    "schedule mode", "fan speed", "setpoint temp heat F" / "... heat" degC).
    Returns dict of raw fields or None if not enough information.
    """
    data_hex = payload.get("data")
    if isinstance(data_hex, str) and len(data_hex) >= 16:
        try:
            b = bytes.fromhex(data_hex[:16])
            return {
                "instance": b[0],
                "operating_mode": b[1] & 0x0F,
                "fan_mode": (b[1] >> 4) & 0x03,
                "schedule_mode": (b[1] >> 6) & 0x03,
                "fan_speed_raw": b[2],
                "setpoint_heat_raw": b[3] | (b[4] << 8),
                "setpoint_cool_raw": b[5] | (b[6] << 8),
            }
        except ValueError:
            pass

    out: dict = {}
    if "instance" in payload:
        try:
            out["instance"] = int(payload["instance"])
        except (TypeError, ValueError):
            return None

    mode = cu.mode_to_raw(payload.get("operating mode", payload.get("operating_mode")))
    fan_mode = cu.fan_mode_to_raw(payload.get("fan mode", payload.get("fan_mode")))
    if mode is None or fan_mode is None:
        return None
    out["operating_mode"] = mode
    out["fan_mode"] = fan_mode
    try:
        out["schedule_mode"] = int(payload.get("schedule mode", payload.get("schedule_mode", 0)))
    except (TypeError, ValueError):
        out["schedule_mode"] = 0
    out["fan_speed_raw"] = cu.pct_to_halfpct(payload.get("fan speed", payload.get("fan_speed", 0)))

    heat_f = payload.get("setpoint temp heat F", payload.get("setpoint_heat_f"))
    cool_f = payload.get("setpoint temp cool F", payload.get("setpoint_cool_f"))
    heat_c = payload.get("setpoint temp heat", payload.get("setpoint_heat_c"))
    cool_c = payload.get("setpoint temp cool", payload.get("setpoint_cool_c"))
    try:
        if heat_f is not None:
            out["setpoint_heat_raw"] = cu.f_to_raw_temp(float(heat_f))
        elif heat_c is not None:
            out["setpoint_heat_raw"] = cu.c_to_raw_temp(float(heat_c))
        else:
            return None
        if cool_f is not None:
            out["setpoint_cool_raw"] = cu.f_to_raw_temp(float(cool_f))
        elif cool_c is not None:
            out["setpoint_cool_raw"] = cu.c_to_raw_temp(float(cool_c))
        else:
            return None
    except (TypeError, ValueError):
        return None
    return out


def resolve_command(payload: dict, current: ZoneState, limits: Limits) -> Tuple[Optional[dict], str]:
    """
    Overlay the requested changes onto the zone's current raw state.

    Recognized keys: setpoint_f (drives heat AND cool together, matching how
    the Firefly G6 keeps them in lockstep), setpoint_heat_f, setpoint_cool_f,
    setpoint_heat_c, setpoint_cool_c, mode / hvac_mode / operating_mode,
    fan_mode, fan_speed_pct (0-100; 0 = automatic), schedule_mode.
    Returns (resolved raw fields, "ok") or (None, reason).
    """
    resolved = {
        "operating_mode": current.operating_mode,
        "fan_mode": current.fan_mode,
        "schedule_mode": current.schedule_mode,
        "fan_speed_raw": current.fan_speed_raw,
        "setpoint_heat_raw": current.setpoint_heat_raw,
        "setpoint_cool_raw": current.setpoint_cool_raw,
    }
    changed = False

    mode_req = payload.get("mode", payload.get("hvac_mode", payload.get("operating_mode")))
    if mode_req is not None:
        mode = cu.mode_to_raw(mode_req)
        if mode is None:
            return None, f"bad_mode:{mode_req}"
        resolved["operating_mode"] = mode
        changed = True

    fan_req = payload.get("fan_mode")
    if fan_req is not None:
        fan = cu.fan_mode_to_raw(fan_req)
        if fan is None:
            return None, f"bad_fan_mode:{fan_req}"
        resolved["fan_mode"] = fan
        changed = True

    fs = payload.get("fan_speed_pct", payload.get("fan_speed"))
    if fs is not None:
        try:
            fs_i = int(fs)
        except (TypeError, ValueError):
            return None, f"bad_fan_speed:{fs}"
        if not (0 <= fs_i <= limits.max_fan_speed_pct):
            return None, f"bad_fan_speed:{fs}"
        resolved["fan_speed_raw"] = cu.pct_to_halfpct(fs_i)
        changed = True

    sched = payload.get("schedule_mode")
    if sched is not None:
        try:
            resolved["schedule_mode"] = int(sched) & 0x03
            changed = True
        except (TypeError, ValueError):
            return None, f"bad_schedule_mode:{sched}"

    def temp_f(key_f: str, key_c: str, combined) -> Tuple[Optional[float], Optional[str]]:
        v = payload.get(key_f, combined)
        if v is not None:
            try:
                vf = float(v)
            except (TypeError, ValueError):
                return None, f"bad_{key_f}:{v}"
            if not (limits.min_temp_f <= vf <= limits.max_temp_f):
                return None, f"out_of_range_{key_f}:{vf}"
            return vf, None
        vc = payload.get(key_c)
        if vc is not None:
            try:
                vf = cu.c_to_f(float(vc))
            except (TypeError, ValueError):
                return None, f"bad_{key_c}:{vc}"
            if not (limits.min_temp_f <= vf <= limits.max_temp_f):
                return None, f"out_of_range_{key_c}:{vc}"
            return vf, None
        return None, None

    combined = payload.get("setpoint_f")
    heat_f, err = temp_f("setpoint_heat_f", "setpoint_heat_c", combined)
    if err:
        return None, err
    cool_f, err = temp_f("setpoint_cool_f", "setpoint_cool_c", combined)
    if err:
        return None, err
    if heat_f is not None:
        resolved["setpoint_heat_raw"] = cu.f_to_raw_temp(heat_f)
        changed = True
    if cool_f is not None:
        resolved["setpoint_cool_raw"] = cu.f_to_raw_temp(cool_f)
        changed = True

    if not changed:
        return None, "no_recognized_fields"
    return resolved, "ok"


class ThermostatBridge:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.profile = self._load_profile(args.profile)
        self.limits = Limits()
        self.last_sent_by_instance: Dict[int, float] = {}
        self.zone_state: Dict[int, ZoneState] = {}
        self.pending_confirm: Dict[int, dict] = {}
        self.min_interval_s = args.min_interval
        self.tx_enabled = bool(args.tx_enable)
        self.source_address = int(args.source_address, 0) if isinstance(args.source_address, str) else args.source_address
        self.priority = args.priority
        self.status_max_age = args.status_max_age

        self.pgn = cu.THERMOSTAT_COMMAND_1_PGN

        if mqtt is None:
            raise RuntimeError("paho-mqtt is required to run the bridge (pip install paho-mqtt)")
        self.mqtt = mqtt.Client(client_id="rvc_thermostat_bridge")
        if args.username and args.password:
            self.mqtt.username_pw_set(args.username, args.password)
        self.mqtt.on_connect = self.on_connect
        self.mqtt.on_message = self.on_message

        self.can_bus = None
        if self.tx_enabled and not args.dry_run and not args.handoff:
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
        control_topic = self.profile["default_topics"]["control"]
        client.subscribe(control_topic)
        for t in self.args.status_topics:
            client.subscribe(t)
        print(f"✅ MQTT connected; control={control_topic} status={list(self.args.status_topics)}")
        print(
            f"🔒 TX enabled={self.tx_enabled} dry_run={self.args.dry_run} "
            f"handoff={self.args.handoff} min_interval={self.min_interval_s}s "
            f"SA=0x{self.source_address:02X} prio={self.priority}"
        )

    # ------------------------------------------------------------------ RX

    def on_message(self, client, _userdata, msg):
        topic = msg.topic
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            if self._is_control_topic(topic):
                self.publish_nack("invalid_json", topic, msg.payload.decode("utf-8", "ignore"))
            return

        if self._is_control_topic(topic):
            self.handle_control(topic, payload)
        else:
            self.handle_status(topic, payload)

    # Feedback topics share the control prefix (rvcbridge/thermostat_control/ack
    # etc.), so the control wildcard subscription also receives our own acks.
    # These tails must be ignored silently -- publishing a NACK about them
    # would create an MQTT feedback loop (NACK -> control handler -> NACK...).
    RESERVED_TAILS = frozenset({"ack", "nack", "audit"})

    def _is_control_topic(self, topic: str) -> bool:
        parts = topic.split("/")
        return (
            len(parts) == 3
            and parts[0] == "rvcbridge"
            and parts[1] == "thermostat_control"
            and parts[2] not in self.RESERVED_TAILS
        )

    def handle_status(self, topic: str, payload: dict) -> None:
        fields = parse_status_payload(payload)
        if not fields:
            return
        instance = fields.get("instance")
        if instance is None:
            tail = topic.rsplit("/", 1)[-1]
            if not tail.isdigit():
                return
            instance = int(tail)
        state = ZoneState(
            operating_mode=fields["operating_mode"],
            fan_mode=fields["fan_mode"],
            schedule_mode=fields["schedule_mode"],
            fan_speed_raw=fields["fan_speed_raw"],
            setpoint_heat_raw=fields["setpoint_heat_raw"],
            setpoint_cool_raw=fields["setpoint_cool_raw"],
        )
        self.zone_state[instance] = state
        self._check_confirmation(instance, state)

    def _check_confirmation(self, instance: int, state: ZoneState) -> None:
        pending = self.pending_confirm.get(instance)
        if not pending:
            return
        if time.time() - pending["ts"] > self.args.confirm_window:
            del self.pending_confirm[instance]
            return
        sent = pending["resolved"]
        if (
            state.operating_mode == sent["operating_mode"]
            and state.setpoint_heat_raw == sent["setpoint_heat_raw"]
            and state.setpoint_cool_raw == sent["setpoint_cool_raw"]
        ):
            del self.pending_confirm[instance]
            self.publish_ack("confirmed", pending["topic"], pending["payload"], pending["frame"])

    # ------------------------------------------------------------------ TX

    def handle_control(self, topic: str, payload: dict) -> None:
        now = time.time()
        tail = topic.rsplit("/", 1)[-1]
        if not tail.isdigit():
            # Never NACK here: a non-numeric tail may be our own feedback
            # topic or another consumer's -- responding would risk a loop.
            print(f"ignoring non-instance control topic: {topic}")
            return
        instance = int(tail)

        allowed = self.profile.get("safety", {}).get("allowed_instances")
        if allowed is not None and instance not in allowed:
            self.publish_nack(f"instance_not_allowed:{instance}", topic, payload)
            return
        if not (self.limits.min_instance <= instance <= self.limits.max_instance):
            self.publish_nack(f"instance_out_of_range:{instance}", topic, payload)
            return

        last = self.last_sent_by_instance.get(instance)
        if last and (now - last) < self.min_interval_s:
            self.publish_nack(f"rate_limited:{instance}", topic, payload)
            return

        current = self.zone_state.get(instance)
        if current is None or (now - current.ts) > self.status_max_age:
            if not self.args.allow_unseeded:
                reason = "no_status_seen" if current is None else "status_stale"
                self.publish_nack(f"{reason}:{instance}", topic, payload)
                return
            current = ZoneState(  # explicit opt-in fallback defaults
                operating_mode=0,
                fan_mode=0,
                schedule_mode=0,
                fan_speed_raw=0,
                setpoint_heat_raw=cu.f_to_raw_temp(68.0),
                setpoint_cool_raw=cu.f_to_raw_temp(72.0),
            )

        resolved, reason = resolve_command(payload, current, self.limits)
        if resolved is None:
            self.publish_nack(reason, topic, payload)
            return

        frame = self.build_frame(instance, resolved)
        self.publish_audit(topic, payload, frame)

        if not self.tx_enabled:
            self.publish_ack("monitor_only", topic, payload, frame)
            return

        sent, status = self.send_frame(frame)
        self.publish_ack(status, topic, payload, frame)
        if sent:
            self.pending_confirm[instance] = {
                "resolved": resolved,
                "frame": frame,
                "topic": topic,
                "payload": payload,
                "ts": time.time(),
            }

    def build_frame(self, instance: int, resolved: dict) -> dict:
        data = cu.build_thermostat_command_payload(
            instance=instance,
            operating_mode=resolved["operating_mode"],
            fan_mode=resolved["fan_mode"],
            schedule_mode=resolved["schedule_mode"],
            fan_speed_raw=resolved["fan_speed_raw"],
            setpoint_heat_raw=resolved["setpoint_heat_raw"],
            setpoint_cool_raw=resolved["setpoint_cool_raw"],
        )
        arbitration_id = cu.rvc_arbitration_id(self.pgn, self.source_address, self.priority)
        return {
            "pgn": self.pgn,
            "pgn_hex": f"0x{self.pgn:05X}",
            "arbitration_id": arbitration_id,
            "arbitration_id_hex": f"0x{arbitration_id:08X}",
            "instance": instance,
            "data": list(data),
            "data_hex": data.hex().upper(),
            "mode": resolved["operating_mode"],
            "fan_mode": resolved["fan_mode"],
            "fan_speed_raw": resolved["fan_speed_raw"],
            "setpoint_heat_raw": resolved["setpoint_heat_raw"],
            "setpoint_cool_raw": resolved["setpoint_cool_raw"],
            "setpoint_heat_f": cu.raw_temp_to_f(resolved["setpoint_heat_raw"]),
            "setpoint_cool_f": cu.raw_temp_to_f(resolved["setpoint_cool_raw"]),
        }

    def send_frame(self, frame: dict) -> tuple[bool, str]:
        self.last_sent_by_instance[frame["instance"]] = time.time()

        if self.args.handoff:
            ok = self.publish_handoff(frame)
            return (ok, "handoff_published" if ok else "handoff_failed")

        if self.args.dry_run or self.can_bus is None:
            print(
                f"🧪 DRY/LOG TX {frame['arbitration_id_hex']} "
                f"({frame['pgn_hex']}) data={frame['data_hex']}"
            )
            return (False, "logged_only")

        try:
            msg = can.Message(
                arbitration_id=frame["arbitration_id"],
                data=frame["data"],
                is_extended_id=True,
            )
            self.can_bus.send(msg)
            print(f"✅ CAN TX {frame['arbitration_id_hex']} data={frame['data_hex']}")
            return (True, "sent")
        except Exception as e:
            print(f"❌ CAN send failed: {e}")
            return (False, "send_failed")

    def publish_handoff(self, frame: dict) -> bool:
        topic = self.args.handoff_topic.format(instance=frame["instance"])
        payload = {
            "name": "THERMOSTAT_COMMAND_1",
            "instance": frame["instance"],
            "dgn": frame["pgn_hex"].replace("0x", ""),
            "arbitration_id": frame["arbitration_id_hex"],
            "data": frame["data_hex"],
            "mode": frame["mode"],
            "fan mode": frame["fan_mode"],
            "fan speed": frame["fan_speed_raw"],
            "setpoint temp heat F": frame["setpoint_heat_f"],
            "setpoint temp cool F": frame["setpoint_cool_f"],
            "timestamp": f"{time.time():.6f}",
        }
        try:
            self.mqtt.publish(topic, json.dumps(payload), qos=0, retain=False)
            print(f"🔁 HANDOFF MQTT {topic} data={frame['data_hex']}")
            return True
        except Exception as e:
            print(f"❌ Handoff publish failed: {e}")
            return False

    # ------------------------------------------------------------- ack/audit

    def publish_ack(self, status: str, topic: str, payload: dict, frame: dict):
        ack_topic = self.profile["default_topics"]["ack"]
        msg = {"status": status, "topic": topic, "payload": payload, "frame": frame, "ts": time.time()}
        self.mqtt.publish(ack_topic, json.dumps(msg), qos=0, retain=False)

    def publish_nack(self, reason: str, topic: str, payload):
        nack_topic = self.profile["default_topics"]["nack"]
        msg = {"status": "nack", "reason": reason, "topic": topic, "payload": payload, "ts": time.time()}
        self.mqtt.publish(nack_topic, json.dumps(msg), qos=0, retain=False)
        print(f"⛔ NACK {reason} topic={topic}")

    def publish_audit(self, topic: str, payload: dict, frame: dict):
        audit_topic = self.profile["default_topics"]["audit"]
        msg = {"topic": topic, "payload": payload, "frame": frame, "tx_enabled": self.tx_enabled, "ts": time.time()}
        self.mqtt.publish(audit_topic, json.dumps(msg), qos=0, retain=False)

    def run(self):
        self.mqtt.connect(self.args.broker, self.args.port, 60)
        self.mqtt.loop_forever()


def parse_args(argv=None) -> argparse.Namespace:
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

    p.add_argument("--source-address", default="0xF9", help="RV-C source address for TX frames")
    p.add_argument("--priority", type=int, default=6, help="RV-C priority bits (default 6)")
    p.add_argument(
        "--status-topics", nargs="*", default=list(DEFAULT_STATUS_TOPICS),
        help="MQTT topics carrying THERMOSTAT_STATUS_1 state for the fill-in cache",
    )
    p.add_argument(
        "--status-max-age", type=float, default=300.0,
        help="Seconds before cached zone state is considered stale",
    )
    p.add_argument(
        "--allow-unseeded", action="store_true",
        help="Permit commanding a zone whose status has never been seen (uses defaults; NOT recommended)",
    )
    p.add_argument(
        "--confirm-window", type=float, default=5.0,
        help="Seconds to wait for a status echo before dropping confirmation tracking",
    )

    p.add_argument("--handoff", action="store_true", help="Publish prebuilt frames to MQTT instead of CAN TX")
    p.add_argument("--handoff-topic", default="RVC/THERMOSTAT_COMMAND_1/{instance}")
    return p.parse_args(argv)


if __name__ == "__main__":
    bridge = ThermostatBridge(parse_args())
    bridge.run()
