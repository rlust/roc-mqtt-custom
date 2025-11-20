#!/usr/bin/env python3
"""
MQTT Test Script for RV-C Sink Light (Instance 46)

Connects to MQTT broker and monitors/tests commands for instance 46.
Usage: python3 test_mqtt_sink.py
"""

import json
import time
import sys
import paho.mqtt.client as mqtt

# MQTT Configuration
BROKER = "192.168.100.125"
PORT = 1883
USERNAME = "rc"
PASSWORD = "rc"
TOPIC_PREFIX = "RVC"  # Change if needed

# Instance 46 = Sink light
INSTANCE = 46

# Topics to monitor
STATUS_TOPIC = f"{TOPIC_PREFIX}/DC_DIMMER_STATUS_3/{INSTANCE}"
COMMAND_TOPIC = f"{TOPIC_PREFIX}/DC_DIMMER_COMMAND_2/{INSTANCE}"
ALL_STATUS_TOPIC = f"{TOPIC_PREFIX}/DC_DIMMER_STATUS_3/#"
ALL_COMMAND_TOPIC = f"{TOPIC_PREFIX}/DC_DIMMER_COMMAND_2/#"


def on_connect(client, userdata, flags, rc):
    """Called when connected to MQTT broker."""
    if rc == 0:
        print(f"✅ Connected to MQTT broker at {BROKER}:{PORT}")
        print(f"📡 Subscribing to topics...")

        # Subscribe to instance 46 topics
        client.subscribe(STATUS_TOPIC)
        print(f"   - {STATUS_TOPIC}")

        client.subscribe(COMMAND_TOPIC)
        print(f"   - {COMMAND_TOPIC}")

        # Subscribe to all dimmer topics for debugging
        client.subscribe(ALL_STATUS_TOPIC)
        print(f"   - {ALL_STATUS_TOPIC}")

        client.subscribe(ALL_COMMAND_TOPIC)
        print(f"   - {ALL_COMMAND_TOPIC}")

        print("\n" + "="*80)
        print("🎧 Listening for MQTT messages... (Press Ctrl+C to exit)")
        print("="*80 + "\n")
    else:
        print(f"❌ Connection failed with code {rc}")
        sys.exit(1)


def on_message(client, userdata, msg):
    """Called when a message is received."""
    global monitoring_active

    # Skip printing if monitoring is paused
    if not monitoring_active:
        return

    timestamp = time.strftime("%H:%M:%S")

    try:
        payload = json.loads(msg.payload.decode())
        payload_str = json.dumps(payload, indent=2)
    except:
        payload_str = msg.payload.decode()

    # Determine message type
    if "STATUS_3" in msg.topic:
        msg_type = "📊 STATUS"
        color = "\033[92m"  # Green
    elif "COMMAND_2" in msg.topic:
        msg_type = "📤 COMMAND"
        color = "\033[94m"  # Blue
    else:
        msg_type = "📨 MESSAGE"
        color = "\033[93m"  # Yellow

    reset = "\033[0m"

    print(f"\r{color}[{timestamp}] {msg_type} - Topic: {msg.topic}{reset}")
    print(f"{payload_str}")
    print("-" * 80)
    print(">>> ", end='', flush=True)  # Redisplay prompt


def on_disconnect(client, userdata, rc):
    """Called when disconnected from broker."""
    if rc != 0:
        print(f"⚠️  Unexpected disconnection (code {rc})")


def generate_command(command_code, desired_level=100, duration=255):
    """Generate RV-C command payload with CAN data field."""
    # Generate CAN bus data bytes (8 bytes)
    instance_hex = f"{INSTANCE:02X}"
    group_hex = "FF"  # All groups
    level_hex = f"{desired_level:02X}"
    command_hex = f"{command_code:02X}"
    duration_hex = f"{duration:02X}"
    interlock_hex = "00"
    padding = "FFFF"

    can_data = (
        instance_hex + group_hex + level_hex +
        command_hex + duration_hex + interlock_hex + padding
    )

    # Command definitions
    command_names = {
        0: "set brightness",
        1: "on duration",
        2: "on delay",
        3: "off",
        4: "stop",
        5: "toggle",
        19: "ramp up",
        20: "ramp down"
    }

    payload = {
        "command": command_code,
        "command definition": command_names.get(command_code, "unknown"),
        "data": can_data,
        "delay/duration": duration,
        "desired level": desired_level,
        "dgn": "1FEDB",
        "group": "11111111",
        "instance": INSTANCE,
        "interlock": "00",
        "interlock definition": "no interlock active",
        "name": "DC_DIMMER_COMMAND_2",
        "timestamp": f"{time.time():.6f}"
    }

    return payload


def send_command(client, command_code, desired_level=100, duration=255):
    """Send a command to the light."""
    payload = generate_command(command_code, desired_level, duration)
    payload_json = json.dumps(payload)

    print(f"\n{'='*80}")
    print(f"📤 SENDING COMMAND to {COMMAND_TOPIC}")
    print(f"{'='*80}")
    print(json.dumps(payload, indent=2))
    print(f"{'='*80}\n")

    result = client.publish(COMMAND_TOPIC, payload_json, qos=0, retain=False)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("✅ Command published successfully\n")
    else:
        print(f"❌ Command publish failed with code {result.rc}\n")


def show_menu():
    """Display command menu."""
    print("\n" + "="*80)
    print("🎛️  COMMAND MENU - Sink Light (Instance 46)")
    print("="*80)
    print("1. Turn ON (Set Brightness 100%)")
    print("2. Turn ON (50% brightness)")
    print("3. Turn OFF")
    print("4. Toggle")
    print("5. Ramp Up (5 seconds)")
    print("6. Ramp Down (5 seconds)")
    print("7. Custom brightness (0-100)")
    print("p. Pause/Resume monitoring")
    print("m. Show this menu")
    print("q. Quit")
    print("="*80 + "\n")


# Global flag for pausing message display
monitoring_active = True


def interactive_menu(client):
    """Handle interactive command input."""
    global monitoring_active

    show_menu()

    while True:
        try:
            # Use a more visible prompt
            print("\n>>> ", end='', flush=True)
            choice = input().strip().lower()

            if choice == 'q':
                print("👋 Exiting...")
                return False
            elif choice == 'm':
                show_menu()
            elif choice == 'p':
                monitoring_active = not monitoring_active
                if monitoring_active:
                    print("✅ Monitoring RESUMED")
                else:
                    print("⏸️  Monitoring PAUSED (commands will still work)")
                show_menu()
            elif choice == '1':
                send_command(client, command_code=0, desired_level=100)
            elif choice == '2':
                send_command(client, command_code=0, desired_level=50)
            elif choice == '3':
                send_command(client, command_code=3, desired_level=0)
            elif choice == '4':
                send_command(client, command_code=5, desired_level=100)
            elif choice == '5':
                send_command(client, command_code=19, desired_level=100, duration=5)
            elif choice == '6':
                send_command(client, command_code=20, desired_level=0, duration=5)
            elif choice == '7':
                try:
                    print("Enter brightness (0-100): ", end='', flush=True)
                    level = int(input())
                    level = max(0, min(100, level))
                    send_command(client, command_code=0, desired_level=level)
                except ValueError:
                    print("❌ Invalid brightness value")
            elif choice == '':
                continue  # Empty input, just show prompt again
            else:
                print(f"❌ Invalid choice '{choice}'. Press 'm' for menu.")
        except EOFError:
            print("\n👋 Exiting...")
            return False
        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            return False


def main():
    """Main function."""
    print("\n" + "="*80)
    print("🔌 RV-C MQTT Test Script - Sink Light (Instance 46)")
    print("="*80)
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Username: {USERNAME}")
    print(f"Instance: {INSTANCE} (Sink)")
    print(f"Topic Prefix: {TOPIC_PREFIX}")
    print("="*80 + "\n")

    # Create MQTT client
    client = mqtt.Client(client_id="rvc_test_sink")
    client.username_pw_set(USERNAME, PASSWORD)

    # Set callbacks
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    try:
        print(f"🔌 Connecting to {BROKER}:{PORT}...")
        client.connect(BROKER, PORT, 60)

        # Start network loop in background
        client.loop_start()

        # Wait for connection
        time.sleep(2)

        # Interactive menu
        if not interactive_menu(client):
            raise KeyboardInterrupt

        # Keep listening
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
        print("✅ Disconnected from broker")


if __name__ == "__main__":
    main()
