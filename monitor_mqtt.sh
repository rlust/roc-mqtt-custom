#!/bin/bash
# Simple MQTT monitor for RV-C instance 46 (Sink light)

BROKER="192.168.100.125"
USERNAME="rc"
PASSWORD="rc"
INSTANCE="46"

echo "================================================================================"
echo "🎧 Monitoring MQTT for Instance 46 (Sink)"
echo "================================================================================"
echo "Broker: $BROKER"
echo "Topics: RVC/DC_DIMMER_STATUS_3/$INSTANCE and RVC/DC_DIMMER_COMMAND_2/$INSTANCE"
echo "================================================================================"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Check if mosquitto_sub is installed
if ! command -v mosquitto_sub &> /dev/null; then
    echo "❌ mosquitto_sub not found. Installing..."
    echo "   Run: brew install mosquitto"
    exit 1
fi

# Subscribe to both status and command topics
mosquitto_sub -h $BROKER -u $USERNAME -P $PASSWORD \
    -t "RVC/DC_DIMMER_STATUS_3/$INSTANCE" \
    -t "RVC/DC_DIMMER_COMMAND_2/$INSTANCE" \
    -F '%I %t: %p' \
    -v
