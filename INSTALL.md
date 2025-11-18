# RV-C Home Assistant Integration – Install & Setup

This document explains how to **install**, **configure**, and **test** the RV-C MQTT custom integration with Home Assistant.

---

## 1. Prerequisites

Before installing, you should have:

1. **Home Assistant**  
   - Recommended: 2024.8.0 or newer.

2. **MQTT Broker & HA MQTT Integration**
   - An MQTT broker (e.g. Mosquitto).
   - Home Assistant configured with the built-in **MQTT** integration.

3. **RV-C ⇄ MQTT Bridge**
   - A process (e.g. Node, Python, or other) that:
     - Listens on the RV-C CAN bus.
     - Publishes JSON status messages to MQTT topics like:
       - `rvc/status/light/<instance>`
       - `rvc/status/climate/<instance>`
       - `rvc/status/sensor/<instance>`
     - Consumes command messages from:
       - `rvc/command/light/<instance>`  
       …and converts them into RV-C CAN frames.

> The specifics of the CAN bridge are up to you; this integration only deals with MQTT.

---

## 2. Install Options

You can install this integration either **manually** or **via HACS** as a custom repository.

### Option A – Manual Install (quickest for testing)

1. On your Home Assistant host, go to your config directory:

   ```bash
   cd /config
   ```

2. Make sure `custom_components` exists:

   ```bash
   mkdir -p custom_components
   cd custom_components
   ```

3. Clone this repo and move the integration:

   ```bash
   git clone https://github.com/rlust/roc-mqtt-custom.git tmp-rvc
   mv tmp-rvc/custom_components/rvc ./rvc
   rm -rf tmp-rvc
   ```

   You should now have:

   ```text
   /config/custom_components/rvc/...
   ```

4. **Restart Home Assistant** from the UI or via CLI.

5. Continue with [Configuration](#3-configuration-in-home-assistant).

---

### Option B – Install via HACS (Custom Repository)

If you use HACS, you can add this repo as a custom integration:

1. In Home Assistant, go to **HACS → Integrations**.
2. Click the **three dots** (⋮) → **Custom repositories**.
3. Add:

   - **Repository URL:** `https://github.com/rlust/roc-mqtt-custom`
   - **Category:** `Integration`

4. After adding, search for **“RV-C Integration”** in HACS → Integrations and install it.
5. **Restart Home Assistant**.
6. Continue with [Configuration](#3-configuration-in-home-assistant).

---

## 3. Configuration in Home Assistant

Once the code is installed and Home Assistant has restarted:

1. Go to **Settings → Devices & Services**.
2. Click **“Add Integration”**.
3. Search for **RV-C**.
4. In the config dialog, you’ll see:

   - **MQTT topic prefix**  
     - Default: `rvc`  
     - This should match whatever your RV-C bridge uses for publishing status topics.
   - **Enable auto discovery**  
     - If enabled, the integration will automatically create entities when it sees new MQTT status messages.

5. Click **Submit** to create the config entry.

You can change these settings later via **Configure** on the integration (options flow).

---

## 4. MQTT Topic & Payload Format

### 4.1 Status Topics (From Bridge → Home Assistant)

The integration expects status topics in this pattern:

- `rvc/status/light/<instance>`
- `rvc/status/climate/<instance>`
- `rvc/status/sensor/<instance>`

Where:

- `rvc` is the **topic prefix** (configurable).
- `light|climate|sensor` is the device type.
- `<instance>` is an identifier for the specific load/zone/sensor (e.g. `36`).

#### Example – Dimmer Status (Instance 36)

```text
topic: rvc/status/light/36
payload:
{
  "data": "247CC8FCFF0504FF",
  "delay/duration": 255,
  "dgn": "1FEDA",
  "enable status": "11",
  "enable status definition": "enable status is unavailable or not supported",
  "group": "01111100",
  "instance": 36,
  "interlock status": "00",
  "interlock status definition": "interlock command is not active",
  "last command": 5,
  "last command definition": "toggle",
  "load status": "01",
  "load status definition": "operating status is non-zero or flashing",
  "lock status": "00",
  "lock status definition": "load is unlocked",
  "name": "DC_DIMMER_STATUS_3",
  "operating status (brightness)": 100,
  "overcurrent status": "11",
  "overcurrent status definition": "overcurrent status is unavailable or not supported",
  "override status": "11",
  "override status definition": "override status is unavailable or not supported",
  "timestamp": "1763484440.817181"
}
```

The integration will:

- Treat `"operating status (brightness)"` as a **0–100% brightness** value.
- Convert it to Home Assistant brightness (0–255).
- Consider brightness > 0 as **ON**.

#### Example – Climate Status

```text
topic: rvc/status/climate/1
payload:
{
  "current_temperature": 72.5,
  "target_temperature": 70,
  "hvac_mode": "cool"
}
```

#### Example – Sensor Status

```text
topic: rvc/status/sensor/inside_temp
payload:
{
  "value": 72.5,
  "unit": "°F",
  "device_class": "temperature"
}
```

---

### 4.2 Command Topics (From Home Assistant → Bridge)

Lights (dimmers) will publish commands to:

- `rvc/command/light/<instance>`

Payloads are JSON with:

- `cc` – command code (from RV-C spec)
- `brightness` – 0–100 % (for brightness-related commands)

#### Command Codes (CC)

| Code | Command       | Description                          |
|------|---------------|--------------------------------------|
| 00   | Set Brightness| Set to specific level (0–100%)       |
| 01   | On            | Turn fully on                        |
| 02   | Off           | Turn fully off                       |
| 03   | Ramp Up       | Gradually increase brightness        |
| 04   | Ramp Down     | Gradually decrease brightness        |
| 05   | Stop          | Stop an active ramp operation        |
| 24   | Toggle        | Switch between on and off            |

Example command payloads sent by Home Assistant:

- **Set brightness to 75% on instance 36:**

  ```json
  {
    "cc": 0,
    "brightness": 75
  }
  ```

- **Turn instance 36 off:**

  ```json
  {
    "cc": 2,
    "brightness": 0
  }
  ```

Your RV-C bridge is responsible for converting these JSON commands into actual CAN frames (e.g. `cansend can0 ...`).

---

## 5. Entity Naming & Instance Mapping

Dimmers are auto-named based on an internal mapping of instances to friendly names. Example:

- Instance `36` → `Living Room Vanity E`
- Instance `25` → `Bedroom Ceiling Lights A`
- etc.

If an instance is not in the mapping, the integration falls back to:

- A name from the payload (e.g. `"name": "DC_DIMMER_STATUS_3"`), or
- `RVC Light <instance>`.

Climate and sensor entities use their payload `name` or a generic fallback.

---

## 6. Verifying the Integration

After installing and adding the integration:

### 6.1 Check that the integration loaded

1. Go to **Settings → Devices & Services**.
2. Confirm you see **RV-C** under Integrations.
3. If you see errors, check **Settings → System → Logs** for any traceback from `custom_components.rvc`.

### 6.2 Test a Light (Instance 36) via HA’s MQTT Tools

In Home Assistant:

1. Go to **Developer Tools → Services**.
2. Choose the service: `mqtt.publish`.
3. Use this data:

   ```yaml
   service: mqtt.publish
   data:
     topic: rvc/status/light/36
     payload: >
       {"data":"247CC8FCFF0504FF","delay/duration":255,"dgn":"1FEDA",
        "enable status":"11","enable status definition":"enable status is unavailable or not supported",
        "group":"01111100","instance":36,"interlock status":"00",
        "interlock status definition":"interlock command is not active",
        "last command":5,"last command definition":"toggle",
        "load status":"01","load status definition":"operating status is non-zero or flashing",
        "lock status":"00","lock status definition":"load is unlocked",
        "name":"DC_DIMMER_STATUS_3",
        "operating status (brightness)":100,
        "overcurrent status":"11","overcurrent status definition":"overcurrent status is unavailable or not supported",
        "override status":"11","override status definition":"override status is unavailable or not supported",
        "timestamp":"1763484440.817181"}
   ```

4. After calling the service:

   - A new entity `light.rvc_light_36` should appear.
   - Name: **Living Room Vanity E**.
   - Brightness: 100%.
   - State: `on`.

5. Toggling this light in the UI or adjusting brightness should result in commands being published to:

   ```text
   rvc/command/light/36
   ```

   with JSON payloads containing `cc` and `brightness`.

---

## 7. Troubleshooting

- **Integration not showing in “Add Integration”**
  - Ensure `custom_components/rvc` exists directly under `/config/custom_components`.
  - Restart Home Assistant.
  - Check logs for any import errors.

- **Entities not appearing**
  - Verify that MQTT messages are actually being published to the expected topics:
    - Use an MQTT client (e.g. MQTT Explorer) to confirm `rvc/status/...` messages.
  - Make sure the **topic prefix** in the integration config matches the one used by your bridge.

- **Commands not affecting RV hardware**
  - Confirm your RV-C bridge subscribes to `rvc/command/light/#`.
  - Log or print the JSON command payloads to ensure it’s receiving `cc` and `brightness`.
  - Map these to your CC/BB logic when generating CAN frames.

---

## 8. Development Notes

- Integration domain: `rvc`.
- Code location: `custom_components/rvc/`.
- Platforms implemented:
  - `light`
  - `climate`
  - `sensor`
- CI: GitHub Actions pipeline with `flake8` linting.

Contributions and improvements (e.g. support for slides/awnings as `cover`/`switch`, or more detailed climate commands) are welcome via pull requests.
