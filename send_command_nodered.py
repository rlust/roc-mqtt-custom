#!/usr/bin/env python3
"""
Simple MQTT Command Sender for Node-RED RVC format
Topic: node-red/rvc/commands
Payload: "instance command brightness" (space-separated)
"""

import time
import sys
import paho.mqtt.client as mqtt

# MQTT Configuration
BROKER = "192.168.100.125"
PORT = 1883
USERNAME = "rc"
PASSWORD = "rc"

# Node-RED format
COMMAND_TOPIC = "node-red/rvc/commands"
INSTANCE = 46  # Sink light


def send_command(client, instance, command, brightness):
    """Send command in Node-RED format: 'instance command brightness'"""
    # Simple space-separated format
    payload = f"{instance} {command} {brightness}"

    print("\n" + "="*80)
    print(f"📤 SENDING to: {COMMAND_TOPIC}")
    print("="*80)
    print(f"Instance: {instance}")
    print(f"Command:  {command}")
    print(f"Brightness: {brightness}")
    print(f"\nPayload: '{payload}'")
    print("="*80)

    result = client.publish(COMMAND_TOPIC, payload, qos=0, retain=False)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("✅ Command sent successfully!\n")
        return True
    else:
        print(f"❌ Failed with code {result.rc}\n")
        return False


def main():
    """Main function."""
    print("\n" + "="*80)
    print("🎛️  Node-RED RVC Command Sender - Instance 46 (Sink)")
    print("="*80)
    print(f"Broker: {BROKER}:{PORT}")
    print(f"Topic: {COMMAND_TOPIC}")
    print(f"Format: 'instance command brightness'")
    print("="*80 + "\n")

    # Create MQTT client
    client = mqtt.Client(client_id="rvc_nodered_sender")
    client.username_pw_set(USERNAME, PASSWORD)

    try:
        print("🔌 Connecting to broker...")
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        time.sleep(1)
        print("✅ Connected!\n")

        while True:
            print("\n" + "="*80)
            print("🎛️  COMMAND MENU - Node-RED Format")
            print("="*80)
            print("1. Turn ON (brightness 65)  - Command 2")
            print("2. Turn ON (brightness 100) - Command 2")
            print("3. Turn OFF (brightness 0)  - Command 3")
            print("4. Toggle                   - Command 5")
            print("5. Custom brightness (0-100)")
            print("q. Quit")
            print("="*80)
            print("\nPayload format: 'instance command brightness'")

            choice = input("\n>>> Enter choice: ").strip().lower()

            if choice == 'q':
                print("\n👋 Goodbye!")
                break
            elif choice == '1':
                # Turn ON with 65% brightness
                send_command(client, INSTANCE, 2, 65)
            elif choice == '2':
                # Turn ON with 100% brightness
                send_command(client, INSTANCE, 2, 100)
            elif choice == '3':
                # Turn OFF
                send_command(client, INSTANCE, 3, 0)
            elif choice == '4':
                # Toggle
                send_command(client, INSTANCE, 5, 100)
            elif choice == '5':
                try:
                    level = int(input("Enter brightness (0-100): "))
                    level = max(0, min(100, level))
                    cmd = 2 if level > 0 else 3
                    send_command(client, INSTANCE, cmd, level)
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
