#!/usr/bin/env python3
import argparse, json, time
import paho.mqtt.client as mqtt


def main():
    ap = argparse.ArgumentParser(description='Watch AIR_CONDITIONER_STATUS for one instance')
    ap.add_argument('--host', default='100.110.189.122')
    ap.add_argument('--port', type=int, default=1883)
    ap.add_argument('--user', default='rc')
    ap.add_argument('--password', default='rc')
    ap.add_argument('--instance', type=int, required=True)
    ap.add_argument('--seconds', type=int, default=20)
    args = ap.parse_args()

    topic = f"RVC/AIR_CONDITIONER_STATUS/{args.instance}"
    rows = []

    def on_message(_c, _u, m):
        try:
            p = json.loads(m.payload.decode())
        except Exception:
            p = {"raw": m.payload.decode(errors='ignore')}
        rows.append((time.time(), p))
        print(json.dumps(p, separators=(',', ':')))

    c = mqtt.Client(client_id=f"ac_status_watch_{int(time.time())}")
    c.username_pw_set(args.user, args.password)
    c.on_message = on_message
    c.connect(args.host, args.port, 60)
    c.subscribe(topic)
    c.loop_start()
    time.sleep(args.seconds)
    c.loop_stop()
    c.disconnect()

    print(f"messages={len(rows)} topic={topic}")


if __name__ == '__main__':
    main()
