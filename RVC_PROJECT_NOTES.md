# RV-C Home Assistant Integration – Knowledge Base & Roadmap

This document captures the current understanding of the RV-C → MQTT → Home Assistant integration, how the system is wired today, and a roadmap for improving and extending the custom integration in the `roc-mqtt-custom` repository.

---

## Outline

1. [Project Overview](#1-project-overview)
2. [Current Repository & Integration Layout](#2-current-repository--integration-layout)
3. [RV-C MQTT Topic & Payload Model](#3-rv-c-mqtt-topic--payload-model)
   - [3.1 Base Topic / Prefix](#31-base-topic--prefix)
   - [3.2 Dimmer Commands & Status](#32-dimmer-commands--status)
   - [3.3 Climate & Thermostat Messages](#33-climate--thermostat-messages)
   - [3.4 Tank, Inverter, and Other Status Messages](#34-tank-inverter-and-other-status-messages)
4. [Current Integration Design](#4-current-integration-design)
   - [4.1 Config Flow & Options](#41-config-flow--options)
   - [4.2 MQTT Handler & Discovery](#42-mqtt-handler--discovery)
   - [4.3 Entity Platforms (Light, Climate, Sensor)](#43-entity-platforms-light-climate-sensor)
5. [Device Naming & Instance Mapping](#5-device-naming--instance-mapping)
6. [Known Limitations & Open Questions](#6-known-limitations--open-questions)
7. [Next Steps & Improvement Plan](#7-next-steps--improvement-plan)
   - [7.1 Lights / Dimmers](#71-lights--dimmers)
   - [7.2 Climate / Thermostats](#72-climate--thermostats)
   - [7.3 Sensors (Tanks, Inverter, Temperatures)](#73-sensors-tanks-inverter-temperatures)
   - [7.4 Additional Platforms (Switch, Cover, Water Heater, Generator)](#74-additional-platforms-switch-cover-water-heater-generator)
   - [7.5 Integration Polish, Testing, and Packaging](#75-integration-polish-testing-and-packaging)

---

## 1. Project Overview

**Goal:**  
Create a robust, reusable custom Home Assistant integration that consumes RV-C data via MQTT and exposes RV devices (lights, climate zones, tanks, inverter, etc.) as native Home Assistant entities.

**Key pieces:**

- An RV-C → MQTT bridge that:
  - Listens to RV-C CAN traffic.
  - Decodes messages into JSON payloads.
  - Publishes them under a shared MQTT topic prefix (currently `RVC`).
- A Home Assistant custom integration (`domain: rvc`) that:
  - Subscribes to `RVC/#`.
  - Classifies messages by payload `name` and `instance` into HA domains (light, climate, sensor).
  - Creates entities automatically via a discovery/dispatcher mechanism.
  - (Future) Sends commands back (e.g., dimmer commands, AC commands) in a format the bridge can convert to RV-C frames.

The long-term intention is to have **full round-trip control** for:

- Interior and exterior lights (dimmers).
- AC / climate zones.
- Slides, awnings, and AC loads.
- Generators, water heaters, pumps, etc.
- Status monitoring (tanks, inverters, temperatures, power).

---

## 2. Current Repository & Integration Layout

**Repo:** `https://github.com/rlust/roc-mqtt-custom`

**Home Assistant install path:**

- Integration code lives under:

  ```text
  /config/custom_components/rvc/
  ```

Key files (expected):

- `__init__.py` – integration setup (`async_setup_entry`, `async_unload_entry`).
- `config_flow.py` – config & options flow for setting MQTT prefix and discovery behavior.
- `mqtt_handler.py` – central MQTT subscription and classification layer.
- `light.py` – creation/handling of light entities for dimmers.
- `climate.py` – creation/handling of climate entities for AC/thermostat data.
- `sensor.py` – creation/handling of sensors (tanks, inverters, ambient temps, etc.).
- `const.py` – shared constants (`DOMAIN`, `CONF_TOPIC_PREFIX`, `CONF_AUTO_DISCOVERY`, `SIGNAL_DISCOVERY`, etc.).
- `services.yaml` – defines integration services (e.g., ramp up).
- `INSTALL.md` – installation & configuration instructions.

The integration is installed either manually or via HACS as a custom repository and configured through the standard “Add Integration” flow.

---

## 3. RV-C MQTT Topic & Payload Model

### 3.1 Base Topic / Prefix

The RV-C bridge publishes all decoded messages under the **`RVC`** topic prefix, with one topic per RV-C PGN / message type, for example:

- `RVC/DC_DIMMER_STATUS_3`
- `RVC/DC_DIMMER_COMMAND_2`
- `RVC/AIR_CONDITIONER_STATUS`
- `RVC/TANK_STATUS`
- `RVC/THERMOSTAT_AMBIENT_STATUS`
- `RVC/THERMOSTAT_STATUS_1`
- `RVC/INVERTER_DC_STATUS`
- `RVC/INVERTER_AC_STATUS_1`
- `RVC/INVERTER_TEMPERATURE_STATUS`
- `RVC/AC_LOAD_STATUS`
- `RVC/CHARGER_STATUS`
- etc.

Each topic uses JSON payloads with at least:

- `name` – the RV-C message type (e.g. `"DC_DIMMER_STATUS_3"`).
- `instance` – the instance ID (load, zone, or sensor index).
- Additional typed fields relevant to that message (brightness, temperatures, levels, voltages, etc.).

The Home Assistant integration uses a configurable **topic prefix**, currently set to `RVC` via the config flow.

### 3.2 Dimmer Commands & Status

Dimmer-related topics:

- `RVC/DC_DIMMER_COMMAND_2`
- `RVC/DC_DIMMER_STATUS_3`

**Command payload example** (`DC_DIMMER_COMMAND_2`):

```json
{
  "command": 5,
  "command definition": "toggle",
  "data": "24FFFA05FF00FFFF",
  "delay/duration": 255,
  "desired level": 125,
  "dgn": "1FEDB",
  "group": "11111111",
  "instance": 36,
  "interlock": "00",
  "interlock definition": "no interlock active",
  "name": "DC_DIMMER_COMMAND_2",
  "timestamp": "1763485729.679936"
}
```

**Status payload example** (`DC_DIMMER_STATUS_3`):

```json
{
  "data": "247C00FCFF0500FF",
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
  "load status": "00",
  "load status definition": "operating status is zero",
  "name": "DC_DIMMER_STATUS_3",
  "timestamp": "1763498877.XXX..."
}
```

Additional dimmer-related fields (in previous samples):

- `"operating status (brightness)"`: numeric 0–100 brightness.
- `load status` and related definitions.

**Command codes (`CC`) from earlier RV-C notes:**

- `00` – Set Brightness (0–100%)
- `01` – On
- `02` – Off
- `03` – Ramp Up
- `04` – Ramp Down
- `05` – Stop
- `24` – Toggle

These map naturally to Home Assistant light operations.

### 3.3 Climate & Thermostat Messages

Climate-related topics include:

- `RVC/AIR_CONDITIONER_STATUS`
- `RVC/AIR_CONDITIONER_COMMAND`
- `RVC/THERMOSTAT_AMBIENT_STATUS`
- `RVC/THERMOSTAT_STATUS_1`

**Examples:**

**`AIR_CONDITIONER_STATUS`**:

```json
{
  "air conditioning output level": 100,
  "data": "0101FFFFC8C8FFFC",
  "dead band": 255,
  "dgn": "1FFE1",
  "fan speed": 100,
  "instance": 1,
  "max air conditioning output level": "n/a",
  "max fan speed": "n/a",
  "name": "AIR_CONDITIONER_STATUS",
  "operating mode": 1,
  "operating mode definition": "manual",
  "second stage dead band": 252,
  "timestamp": "1763498874.772529"
}
```

**`THERMOSTAT_AMBIENT_STATUS`** (per-zone ambient temps):

```json
{
  "ambient temp": 26.7,
  "ambient temp F": 80.0,
  "data": "0075250000000000",
  "dgn": "1FF9C",
  "instance": 0,
  "name": "THERMOSTAT_AMBIENT_STATUS",
  "timestamp": "1763498875.984698"
}
```

**`THERMOSTAT_STATUS_1`** (setpoints, modes, fan, etc.):

```json
{
  "data": "0001005A255A2500",
  "dgn": "1FFE2",
  "fan mode": "00",
  "fan mode definition": "auto",
  "fan speed": 0,
  "instance": 0,
  "name": "THERMOSTAT_STATUS_1",
  "operating mode": "0001",
  "operating mode definition": "cool",
  "schedule mode": "00",
  "schedule mode definition": "disabled",
  "setpoint temp cool": 25.8,
  "setpoint temp cool F": 78.4,
  "setpoint temp heat": 25.8,
  "setpoint temp heat F": 78.4,
  "timestamp": "1763498875.601585"
}
```

These will feed the `climate` platform and potentially separate `sensor` entities for richer telemetry.

### 3.4 Tank, Inverter, and Other Status Messages

Examples of additional data sources:

- `RVC/TANK_STATUS` – fresh, black, gray tanks; fields include `relative level`, `instance definition`, etc.
- `RVC/INVERTER_DC_STATUS` – DC voltage, DC current.
- `RVC/INVERTER_AC_STATUS_1` – frequency, fault conditions.
- `RVC/INVERTER_TEMPERATURE_STATUS` – FET/transformer temps.
- `RVC/AC_LOAD_STATUS` – AC load usage and priorities.
- `RVC/CHARGER_STATUS`, `RVC/CHARGER_CONFIGURATION_STATUS_2` – charger state.
- `RVC/GENERATOR_STATUS_1` – generator running state, runtime, etc.
- `RVC/WATERHEATER_STATUS`, `RVC/WATERHEATER_STATUS_2`, `RVC/WATERHEATER_COMMAND2` – water heater states and commands.

These are all naturally exposed as **sensors** (with future potential for `switch`, `water_heater`, and `binary_sensor` entities).

---

## 4. Current Integration Design

### 4.1 Config Flow & Options

`config_flow.py` implements:

- **User step (`async_step_user`)**:
  - Collects:
    - `topic_prefix` (default: `"rvc"`, overridden to `"RVC"` for this project).
    - `auto_discovery` (bool, default: `True`).
  - Creates a config entry titled `"RV-C"` with these values in `entry.data`.

- **Options flow (`RVCOptionsFlow`)**:
  - Allows editing `topic_prefix` and `auto_discovery` from the integration’s **Configure** button.
  - Reads defaults from `entry.options` or falls back to `entry.data`.

- **`async_get_options_flow`** is correctly implemented as a `@staticmethod`, which is required by current Home Assistant core and fixes the earlier `TypeError: missing 1 required positional argument: 'config_entry'` issue.

### 4.2 MQTT Handler & Discovery

`mqtt_handler.py` is now responsible for:

- Subscribing to all RV-C MQTT topics:

  ```python
  topic = f"{self.prefix}/#"
  await mqtt.async_subscribe(self.hass, topic, self._message_received, 0)
  ```

- For each incoming message:
  - Parse JSON payload.
  - Extract `name` and `instance`.
  - Classify into an HA **device type**:

    ```python
    # Lights
    if raw_name.startswith("DC_DIMMER_STATUS"):
        device_type = "light"

    # Climate
    elif raw_name.startswith("AIR_CONDITIONER_STATUS"):
        device_type = "climate"
    elif raw_name.startswith("THERMOSTAT_STATUS_1"):
        device_type = "climate"

    # Sensors
    elif raw_name.startswith("TANK_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("THERMOSTAT_AMBIENT_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("INVERTER_DC_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("INVERTER_AC_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("INVERTER_TEMPERATURE_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("AC_LOAD_STATUS"):
        device_type = "sensor"
    elif raw_name.startswith("CHARGER_STATUS"):
        device_type = "sensor"
    ```

  - Emit a discovery signal via Home Assistant’s dispatcher:

    ```python
    discovery = {
        "type": device_type,
        "instance": instance_str,
        "name": raw_name,
        "payload": payload,
    }
    async_dispatcher_send(self.hass, SIGNAL_DISCOVERY, discovery)
    ```

The individual platforms (light, climate, sensor) listen for `SIGNAL_DISCOVERY` and create/update entities based on the discovered instance and payload.

### 4.3 Entity Platforms (Light, Climate, Sensor)

While not fully documented here, the expectation is:

- **Light platform**:
  - Listens for `type == "light"`.
  - Creates entities keyed by instance: e.g. `unique_id = f"rvc_light_{instance}"`.
  - Maps RV-C brightness / status to HA’s `LightEntity` state.
  - Sends commands to an agreed MQTT command topic (TBD) or to `RVC/DC_DIMMER_COMMAND_2` with the correct RV-C fields.

- **Climate platform**:
  - Listens for `type == "climate"`.
  - Creates a climate entity per `AIR_CONDITIONER_STATUS` / `THERMOSTAT_STATUS_1` instance.
  - Uses ambient temps, setpoints, and operating modes to fill HA climate properties.
  - (Future) Issues `AIR_CONDITIONER_COMMAND` messages for mode and setpoint changes.

- **Sensor platform**:
  - Listens for `type == "sensor"`.
  - Creates:
    - Tank level sensors from `TANK_STATUS`.
    - Ambient temperature sensors from `THERMOSTAT_AMBIENT_STATUS`.
    - Power/voltage/current sensors from `INVERTER_*` and `AC_LOAD_STATUS`.
    - Charger state sensors from `CHARGER_STATUS`.

---

## 5. Device Naming & Instance Mapping

There are two parallel naming schemes:

1. **Raw RV-C instance/name mapping** from the coach’s configuration:
   - Instances map to functions like:
     - 13: Satellite Dome
     - 14: Entry Door
     - 16: Water Pump
     - 25–60: Various ceiling/accent/vanity lights.
     - 181–188: Slide extend/retract, etc.
   - Slide-related instances (181–188) correspond to kitchen, super, vanity, and bed slide operations.

2. **MQTT command label mapping** (from earlier JS mapping):

   ```js
   export const deviceNameMapping = {
     'DC_DIMMER_COMMAND_2_25': 'Bedroom Ceiling Lights A',
     'DC_DIMMER_COMMAND_2_26': 'Over Bed Ceiling Lights B',
     'DC_DIMMER_COMMAND_2_27': 'Bedroom Accent Lights',
     'DC_DIMMER_COMMAND_2_28': 'Bedroom Vanity',
     'DC_DIMMER_COMMAND_2_29': 'Courtesy Lights',
     'DC_DIMMER_COMMAND_2_30': 'Rear Bath Ceiling Lights',
     'DC_DIMMER_COMMAND_2_32': 'Bedroom Floor Lights A',
     'DC_DIMMER_COMMAND_2_33': 'Over Bed Floor Lights B',
     'DC_DIMMER_COMMAND_2_34': 'Living Room Ceiling Lights C',
     'DC_DIMMER_COMMAND_2_35': 'Living Room Accent Lights D',
     'DC_DIMMER_COMMAND_2_36': 'Living Room Vanity E',
     ...
   };
   ```

The integration should eventually consolidate these into a single mapping table, used to assign friendly names on entity creation:

- `light.rvc_light_36` → **Living Room Vanity E**
- `light.rvc_light_30` → **Rear Bath Ceiling Lights**
- etc.

---

## 6. Known Limitations & Open Questions

1. **MQTT dependency handling**
   - Initially, the integration threw an error if MQTT wasn’t set up.
   - Ideal behavior is to raise `ConfigEntryNotReady` when MQTT is unavailable, so HA retries gracefully.

2. **Command path is not fully defined**
   - Currently, RV-C command messages are seen on `RVC/DC_DIMMER_COMMAND_2`, `RVC/AIR_CONDITIONER_COMMAND`, etc.
   - The HA integration needs a clear outbound command topic structure and mapping logic (either reuse the existing topics or introduce a dedicated HA → RV-C command namespace).

3. **Limited classification**
   - Only a subset of RV-C messages are mapped to HA device types.
   - Many potentially useful messages (`GENERATOR_STATUS_1`, `WATERHEATER_STATUS`, `CIRCULATION_PUMP_STATUS`, etc.) are not yet turned into entities.

4. **No explicit handling for binary states**
   - Many things are effectively binary (e.g., generator running vs. stopped, pump on vs. off) but currently only considered as generic sensors.

5. **Instance/zone grouping logic not implemented**
   - Multiple instances (e.g., A/C zones, tanks) could be grouped logically (e.g., “Front Zone”, “Bedroom Zone”), requiring a more sophisticated config or mapping table.

6. **Testing and CI**
   - Limited or no automated tests (unit tests) for the integration.
   - CI is mentioned conceptually but not fully wired (e.g. GitHub Actions for `flake8` and pytest).

---

## 7. Next Steps & Improvement Plan

### 7.1 Lights / Dimmers

**Goals:**

- Full two-way control of all dimmer-based lighting loads.
- Friendly names and stable unique IDs.

**Tasks:**

1. **Solidify brightness mapping:**
   - Use `operating status (brightness)` (0–100) from `DC_DIMMER_STATUS_3` when present.
   - Convert 0–100 → 0–255 for HA brightness.

2. **Define command path:**
   - Either:
     - Publish to `RVC/DC_DIMMER_COMMAND_2` with RV-C correct fields (`command`, `desired level`, etc.), **or**
     - Define `RVC/command/light/<instance>` as an HA-friendly command topic and let the bridge translate to RV-C.
   - Map HA `turn_on`, `turn_off`, and `brightness` calls to the appropriate `command` codes (`01`, `02`, `00` with brightness).

3. **Complete device name mapping:**
   - Add a comprehensive mapping table of instance → friendly name using the existing JS `deviceNameMapping` and the original RV instance list.
   - Apply this at entity creation time.

4. **Ramp / scene support (optional):**
   - Expose custom services (e.g. `rvc.ramp_up`) that send ramp commands (03/04/05) with duration.

### 7.2 Climate / Thermostats

**Goals:**

- Represent each HVAC zone as a Home Assistant `climate` entity.
- Reflect ambient temperatures and setpoints correctly.
- Allow mode and setpoint changes from HA to propagate back to the coach.

**Tasks:**

1. **Define climate model per instance:**
   - Use:
     - `THERMOSTAT_AMBIENT_STATUS` → current temperature per instance.
     - `THERMOSTAT_STATUS_1` → setpoints, fan mode, operating mode.

2. **Map to HA climate fields:**
   - `current_temperature` from ambient temp.
   - `target_temperature` / `target_temperature_low` / `target_temperature_high` from setpoints.
   - `hvac_mode` from `operating mode definition` (`off`, `cool`, `heat`, etc.).
   - `fan_mode` from `fan mode` definition.

3. **Define outbound control:**
   - Use `AIR_CONDITIONER_COMMAND` and/or thermostat command PGNs to:
     - Change setpoints.
     - Change operating mode.
     - Adjust fan mode.

4. **Implement climate entity update logic:**
   - Merge `THERMOSTAT_AMBIENT_STATUS` + `THERMOSTAT_STATUS_1` for a zone-aware climate view.

### 7.3 Sensors (Tanks, Inverter, Temperatures)

**Goals:**

- Make tank levels, inverter metrics, AC loads, and charger status visible and useful in HA dashboards and automations.

**Tasks:**

1. **Tank sensors:**
   - Create `sensor` entities for each `TANK_STATUS` instance:
     - Set `device_class = "volume" or "none"`.
     - Use `relative level` as percentage.
     - Friendly names: `Fresh Tank`, `Black Tank`, `Gray Tank` based on `instance definition`.

2. **Inverter sensors:**
   - From `INVERTER_DC_STATUS`, `INVERTER_AC_STATUS_1`, `INVERTER_TEMPERATURE_STATUS`:
     - Voltage, current, frequency, temperature sensors.
   - Set sensible units (`V`, `A`, `Hz`, `°C/°F`) and device classes (`voltage`, `current`, `temperature`, etc.).

3. **AC load sensors:**
   - `AC_LOAD_STATUS` -> sensors for load percentage / demanded current per instance (for power management dashboards).

4. **Thermostat ambient temps:**
   - In addition to climate entities, expose per-zone `sensor` entities for `ambient temp F`/`ambient temp`.

### 7.4 Additional Platforms (Switch, Cover, Water Heater, Generator)

**Goals:**

- Bring non-dimmer loads and actuators into HA with appropriate entity types.

**Targets:**

1. **Slides and awnings as `cover` entities:**
   - Use `DC_DIMMER_COMMAND_2` / related PGNs and instance IDs (181–188, etc.) that represent slide extend/retract commands.
   - Represent extend/retract/stop as cover controls with position if possible.

2. **Water heater & circulation pump:**
   - `WATERHEATER_STATUS`, `WATERHEATER_COMMAND2`, `CIRCULATION_PUMP_STATUS`:
     - Map ON/OFF and mode fields to either `water_heater` or `switch` entities.

3. **Generator control & status:**
   - `GENERATOR_STATUS_1`:
     - Create sensors for runtime and a `binary_sensor` or `switch` for running state.
   - If there is a corresponding command PGN, expose start/stop functions via `switch` or service calls.

### 7.5 Integration Polish, Testing, and Packaging

**Goals:**

- Make the integration safe, robust, and easy to maintain.

**Tasks:**

1. **Error handling & retries:**
   - In `__init__.py`, ensure missing MQTT raises `ConfigEntryNotReady` instead of hard failures.
   - Improve logging around classification and entity creation (already partially done via `RVC MQTT:` logs).

2. **Unit tests:**
   - Add pytest-based tests for:
     - MQTT classification logic (given payload → expected `device_type` and instance).
     - Entity creation from discovery events.

3. **Continuous Integration:**
   - Add GitHub Actions workflow for:
     - `flake8` / `ruff` linting.
     - `pytest` against HA’s integration test harness or a simple mock harness.

4. **Docs & examples:**
   - Keep `INSTALL.md` up to date with:
     - Current topic conventions.
     - Example payloads.
     - How to test discovery using `mqtt.publish` in HA.
   - Add a `README.md` section explaining the mapping from RV-C `name`/`instance` to HA entities.

5. **HACS polish:**
   - Ensure `hacs.json` is present and correct.
   - Add proper version tags (e.g. `v0.1.0`, `v0.2.0`) as the integration matures.

---

This file should live in the repo as a living design/roadmap document (e.g. `RVC_PROJECT_NOTES.md` or `DESIGN.md`) and be kept updated as the integration evolves.
