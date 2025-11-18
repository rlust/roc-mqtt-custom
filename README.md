# RV-C Home Assistant Integration

Custom Home Assistant integration to monitor and control RV-C devices via MQTT.

## Features

- Automatic device discovery from MQTT topics:
  - \`rvc/status/light/<instance>\`
  - \`rvc/status/climate/<instance>\`
  - \`rvc/status/sensor/<instance>\`
- Dynamic creation of:
  - Lights (dimmers) with brightness
  - Climate entities
  - Sensors
- UI-based configuration (config flow)
- Command topic pattern for bridge / CAN gateway:
  - \`rvc/command/light/<instance>\`

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
