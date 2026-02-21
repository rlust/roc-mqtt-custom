#!/usr/bin/env python3
import argparse, json, time
import paho.mqtt.client as mqtt


def load_base(args):
    if args.payload:
        return json.loads(args.payload)
    if args.payload_file:
        with open(args.payload_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    # safe default shape from captures
    return {
        "air conditioning output level": 0,
        "data": "0100FFFF0000FFFF",
        "dead band": 255,
        "dgn": "1FFE0",
        "fan speed": 0,
        "instance": 1,
        "name": "AIR_CONDITIONER_COMMAND",
        "operating mode": 0,
        "operating mode definition": "automatic",
        "second stage dead band": 255,
        "timestamp": f"{time.time():.6f}",
    }


def main():
    p = argparse.ArgumentParser(description='Publish AIR_CONDITIONER_COMMAND safely')
    p.add_argument('--host', default='100.110.189.122')
    p.add_argument('--port', type=int, default=1883)
    p.add_argument('--user', default='rc')
    p.add_argument('--password', default='rc')
    p.add_argument('--instance', type=int, required=True)
    p.add_argument('--mode', type=int)
    p.add_argument('--fan-speed', type=int)
    p.add_argument('--output-level', type=int)
    p.add_argument('--dead-band', type=int)
    p.add_argument('--second-stage-dead-band', type=int)
    p.add_argument('--payload')
    p.add_argument('--payload-file')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    msg = load_base(args)
    msg['instance'] = args.instance
    msg['name'] = 'AIR_CONDITIONER_COMMAND'
    msg['dgn'] = '1FFE0'
    if args.mode is not None:
        msg['operating mode'] = max(0, min(15, args.mode))
    if args.fan_speed is not None:
        msg['fan speed'] = max(0, min(100, args.fan_speed))
    if args.output_level is not None:
        msg['air conditioning output level'] = max(0, min(100, args.output_level))
    if args.dead_band is not None:
        msg['dead band'] = max(0, min(255, args.dead_band))
    if args.second_stage_dead_band is not None:
        msg['second stage dead band'] = max(0, min(255, args.second_stage_dead_band))
    msg['timestamp'] = f"{time.time():.6f}"

    topic = f"RVC/AIR_CONDITIONER_COMMAND/{args.instance}"
    print(json.dumps({"topic": topic, "payload": msg}, indent=2))
    if args.dry_run:
        return

    c = mqtt.Client(client_id=f"ac_cmd_pub_{int(time.time())}")
    c.username_pw_set(args.user, args.password)
    c.connect(args.host, args.port, 60)
    c.publish(topic, json.dumps(msg, separators=(',', ':')), qos=0, retain=False)
    c.disconnect()
    print('published')


if __name__ == '__main__':
    main()
