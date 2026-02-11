# RV-C Home Assistant Integration

Custom Home Assistant integration to monitor and control RV-C devices via MQTT.

## Features

- Automatic device discovery from MQTT topics:
  - \`rvc/status/light/<instance>\`
  - \`rvc/status/climate/<instance>\`
  - \`rvc/status/sensor/<instance>\`
- Dynamic creation of:
  - Lights (dimmers) with brightness + ramp services
  - Climate entities
  - Sensors
  - Relay switches (satellite dome, water pump, etc.)
  - Generator control buttons (start/stop)
- UI-based configuration (config flow + options flow)
- Built-in availability monitoring for every platform
- Command topic pattern for bridge / CAN gateway (default `node-red/rvc/commands`):
  - `rvc/command/light/<instance>`

## MQTT Topic Format

### Status Topics

\`\`\`text
rvc/status/light/36
{
  "instance": 36,
  "name": "DC_DIMMER_STATUS_3",
  "operating status (brightness)": 100,
  ...
}

rvc/status/climate/1
{
  "current_temperature": 72.5,
  "target_temperature": 70,
  "hvac_mode": "cool"
}

rvc/status/sensor/inside_temp
{
  "value": 72.5,
  "unit": "°F",
  "device_class": "temperature"
}
\`\`\`

### Command Topics (for your bridge)

\`\`\`text
rvc/command/light/<instance>
{
  "cc": 0,         // Command code (e.g. 0 = set brightness, 2 = off)
  "brightness": 75 // Percent 0–100
}
\`\`\`

The bridge is responsible for translating these JSON commands into the actual CAN frames (e.g. \`cansend can0 ...\`).


## Configuration Options

Use the integration options flow (Settings → Devices & Services → RV-C → Configure) to adjust runtime behavior without editing YAML:

- **MQTT topic prefix** – Root of the RV-C status tree (default `rvc`).
- **Auto discovery** – Toggle automatic entity creation from incoming topics.
- **Command topic** – Where control payloads are published (default `node-red/rvc/commands`).
- **GPS topic** – Topic filter for CP/GPSDATA messages (default `CP/#`).
- **Availability timeout** – Seconds before entities are marked unavailable when no telemetry is received (default 300s).

## Installation

1. Copy \`custom_components/rvc/\` into your Home Assistant \`config/custom_components\` directory  
   **or** add this repo as a custom repository in HACS and install **RV-C Integration**.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search for **RV-C**.
4. Enter your MQTT topic prefix (default: \`rvc\`) and enable/disable auto discovery.

## Naming

Dimmers are automatically named using your instance mapping, e.g.:

- Instance \`36\` → **Living Room Vanity E**
- Instance \`25\` → **Bedroom Ceiling Lights A**

## License

See [LICENSE](LICENSE).
