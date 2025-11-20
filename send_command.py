#!/usr/bin/env python3
"""
Simple MQTT Command Sender for RV-C Sink Light (Instance 46)
Sends commands without monitoring - cleaner for testing.
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
TOPIC_PREFIX = "RVC"

# Instance 46 = Sink light (relay-only, NOT dimmable)
INSTANCE = 46
COMMAND_TOPIC = f"{TOPIC_PREFIX}/DC_DIMMER_COMMAND_2/{INSTANCE}"

# Instance 46 is NOT dimmable, so we use command 2 (ON_DELAY) not command 0
IS_DIMMABLE = False  # Change this to True for dimmable lights (25-35)


def generate_command(command_code, desired_level=100, duration=255):
    """Generate RV-C command payload - MATCHES WORKING RVC-HA IMPLEMENTATION."""
    command_names = {
        3: "off",
        5: "toggle",
        19: "ramp up",
        20: "ramp down"
    }

    # Simple payload matching working RVC-HA integration
    payload = {
        "command": command_code,
        "command definition": command_names.get(command_code, "unknown"),
        "instance": INSTANCE,
        "desired level": desired_level,
        "delay/duration": duration
    }

    return payload


def send_command(client, command_code, desired_level=100, duration=255):
    """Send a command to the light."""
    payload = generate_command(command_code, desired_level, duration)
    payload_json = json.dumps(payload)

    print("\n" + "="*80)
    print(f"📤 SENDING to: {COMMAND_TOPIC}")
    print("="*80)
    print(json.dumps(payload, indent=2))
    print("="*80)

    result = client.publish(COMMAND_TOPIC, payload_json, qos=0, retain=False)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("✅ Command sent successfully!\n")
        return True
    else:
        print(f"❌ Failed with code {result.rc}\n")
        return False


def main():
    """Main function."""
    print("\n" + "="*80)
    print("🎛️  RV-C MQTT Command Sender - Sink Light (Instance 46)")
    print("="*80)
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Topic: {COMMAND_TOPIC}")
    print("="*80 + "\n")

    # Create MQTT client
    client = mqtt.Client(client_id="rvc_command_sender")
    client.username_pw_set(USERNAME, PASSWORD)

    try:
        print("🔌 Connecting to broker...")
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        time.sleep(1)
        print("✅ Connected!\n")

        while True:
            print("\n" + "="*80)
            print("🎛️  COMMAND MENU - Instance 46 (Sink - Relay Only)")
            print("="*80)
            if IS_DIMMABLE:
                print("1. Turn ON (100% brightness) - Command 0")
                print("2. Turn ON (50% brightness) - Command 0")
                print("3. Turn OFF - Command 3")
                print("4. Toggle - Command 5")
                print("5. Ramp Up (5 seconds) - Command 19")
                print("6. Ramp Down (5 seconds) - Command 20")
                print("7. Custom brightness (0-100) - Command 0")
            else:
                print("1. Turn ON - Command 19 (RAMP_UP)")
                print("2. Turn OFF - Command 3 (OFF)")
                print("3. Toggle - Command 5 (TOGGLE)")
                print("")
                print("ℹ️  Using WORKING RVC-HA implementation format")
            print("q. Quit")
            print("="*80)

            choice = input("\n>>> Enter choice: ").strip().lower()

            if choice == 'q':
                print("\n👋 Goodbye!")
                break
            elif choice == '1':
                if IS_DIMMABLE:
                    send_command(client, command_code=0, desired_level=100)
                else:
                    # Use command 19 (RAMP_UP) - matches working RVC-HA
                    send_command(client, command_code=19, desired_level=100)
            elif choice == '2':
                if IS_DIMMABLE:
                    send_command(client, command_code=0, desired_level=50)
                else:
                    # Relay-only: Turn OFF
                    send_command(client, command_code=3, desired_level=0)
            elif choice == '3':
                if IS_DIMMABLE:
                    send_command(client, command_code=3, desired_level=0)
                else:
                    # Relay-only: Toggle
                    send_command(client, command_code=5, desired_level=100)
            elif choice == '4' and IS_DIMMABLE:
                send_command(client, command_code=5, desired_level=100)
            elif choice == '5' and IS_DIMMABLE:
                send_command(client, command_code=19, desired_level=100, duration=5)
            elif choice == '6' and IS_DIMMABLE:
                send_command(client, command_code=20, desired_level=0, duration=5)
            elif choice == '7' and IS_DIMMABLE:
                try:
                    level = int(input("Enter brightness (0-100): "))
                    level = max(0, min(100, level))
                    send_command(client, command_code=0, desired_level=level)
                except ValueError:
                    print("❌ Invalid brightness value")
            elif choice == '':
                continue
            else:
                print(f"❌ Invalid choice: '{choice}'")

    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
