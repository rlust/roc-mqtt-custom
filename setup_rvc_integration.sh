#!/usr/bin/env bash
set -e

echo "Creating directories..."
mkdir -p custom_components/rvc/translations
mkdir -p .github/workflows

#######################################
# custom_components/rvc/const.py
#######################################
cat << 'EOF' > custom_components/rvc/const.py
"""Constants for the RVC integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rvc"

CONF_TOPIC_PREFIX = "topic_prefix"
CONF_AUTO_DISCOVERY = "auto_discovery"

SIGNAL_DISCOVERY = "rvc_discovery_event"

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.SENSOR,
]

# Command codes for dimmer control (CC) — from RV-C spec
CC_SET_BRIGHTNESS = 0
CC_ON = 1
CC_OFF = 2
CC_RAMP_UP = 3
CC_RAMP_DOWN = 4
CC_STOP = 5
CC_TOGGLE = 24

# Human-friendly labels for dimmer instances (from deviceNameMapping)
DIMMER_INSTANCE_LABELS: dict[str, str] = {
    "25": "Bedroom Ceiling Lights A",
    "26": "Over Bed Ceiling Lights B",
    "27": "Bedroom Accent Lights",
    "28": "Bedroom Vanity",
    "29": "Courtesy Lights",
    "30": "Rear Bath Ceiling Lights",
    # 31 not present in mapping
    "32": "Bedroom Floor Lights A",
    "33": "Over Bed Floor Lights B",
    "34": "Living Room Ceiling Lights C",
    "35": "Living Room Accent Lights D",
    "36": "Living Room Vanity E",
    "37": "Kitchen Ceiling Lights F",
    "38": "Kitchen Accent Lights G",
    "39": "Kitchen Vanity H",
    "40": "Hallway Ceiling Lights I",
    "41": "Hallway Accent Lights J",
    "42": "Hallway Vanity K",
    "43": "Front Bedroom Ceiling Lights L",
    "44": "Front Bedroom Accent Lights M",
    "45": "Front Bedroom Vanity N",
    "46": "Back Bath Ceiling Lights O",
    "47": "Living Room Floor Lights P",
    "48": "Kitchen Floor Lights Q",
    "49": "Hallway Floor Lights R",
    "50": "Front Bedroom Floor Lights S",
    "51": "Bedroom Floor Lights T",
    "52": "Living Room Accent Lights U",
    "53": "Kitchen Vanity V",
    "54": "Kitchen Accent Lights W",
    "55": "Hallway Vanity X",
    "56": "Back Bath Ceiling Lights Y",
    "57": "Hallway Accent Lights Z",
    "58": "Kitchen Vanity A",
}
EOF

#######################################
# custom_components/rvc/__init__.py
#######################################
cat << 'EOF' > custom_components/rvc/__init__.py
"""Initialize RVC integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, PLATFORMS
from .mqtt_handler import RVCMQTTHandler

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (currently unused, but kept for compatibility)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RVC from a config entry."""
    _LOGGER.info("Setting up RVC integration entry %s", entry.entry_id)

    handler = RVCMQTTHandler(hass, entry.data)
    await handler.async_subscribe()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "handler": handler,
        "unsub_dispatchers": [],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading RVC integration entry %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if data:
        handler: RVCMQTTHandler | None = data.get("handler")
        if handler:
            await handler.async_unsubscribe()
        for unsub in data.get("unsub_dispatchers", []):
            unsub()

    return unload_ok
EOF

#######################################
# custom_components/rvc/config_flow.py
#######################################
cat << 'EOF' > custom_components/rvc/config_flow.py
"""Handle the config flow for RVC integration."""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
import voluptuous as vol

from .const import DOMAIN, CONF_TOPIC_PREFIX, CONF_AUTO_DISCOVERY


class RVCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for the RVC integration."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title="RV-C", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TOPIC_PREFIX, default="rvc"): str,
                vol.Optional(CONF_AUTO_DISCOVERY, default=True): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema)

    @callback
    def async_get_options_flow(
        self, config_entry: config_entries.ConfigEntry  # type: ignore[override]
    ):
        return RVCOptionsFlow(config_entry)


class RVCOptionsFlow(config_entries.OptionsFlow):
    """Options flow for RVC entries."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Required(
                    CONF_TOPIC_PREFIX,
                    default=self._entry.data.get(CONF_TOPIC_PREFIX, "rvc"),
                ): str,
                vol.Optional(
                    CONF_AUTO_DISCOVERY,
                    default=self._entry.data.get(CONF_AUTO_DISCOVERY, True),
                ): bool,
            }
        )

        return self.async_show_form(step_id="init", data_schema=data_schema)
EOF

#######################################
# custom_components/rvc/manifest.json
#######################################
cat << 'EOF' > custom_components/rvc/manifest.json
{
  "domain": "rvc",
  "name": "RV-C Integration",
  "version": "1.0.0",
  "documentation": "https://github.com/rlust/roc-mqtt-custom",
  "dependencies": ["mqtt"],
  "codeowners": ["@rlust"],
  "config_flow": true,
  "iot_class": "local_push",
  "requirements": []
}
EOF

#######################################
# custom_components/rvc/mqtt_handler.py
#######################################
cat << 'EOF' > custom_components/rvc/mqtt_handler.py
"""MQTT handler for RV-C integration."""
from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import SIGNAL_DISCOVERY, CONF_TOPIC_PREFIX, CONF_AUTO_DISCOVERY

_LOGGER = logging.getLogger(__name__)


class RVCMQTTHandler:
    """Central MQTT listener and dispatcher for RV-C."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self.hass = hass
        self.prefix: str = config.get(CONF_TOPIC_PREFIX, "rvc")
        self.discovery_enabled: bool = config.get(CONF_AUTO_DISCOVERY, True)
        self._unsubs: list[callable] = []

    async def async_subscribe(self) -> None:
        """Subscribe to RV-C status topics."""
        topic = f"{self.prefix}/status/#"
        _LOGGER.debug("Subscribing to topic: %s", topic)
        unsub = await mqtt.async_subscribe(self.hass, topic, self._message_received, 0)
        self._unsubs.append(unsub)

    async def async_unsubscribe(self) -> None:
        """Unsubscribe from all topics."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    async def _message_received(self, msg: mqtt.ReceiveMessage) -> None:  # type: ignore[name-defined]
        """Handle an incoming MQTT message."""
        _LOGGER.debug("Received MQTT message: %s => %s", msg.topic, msg.payload)

        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            _LOGGER.warning("Invalid JSON payload on %s: %s", msg.topic, msg.payload)
            return

        parts = msg.topic.split("/")
        # Expect: <prefix>/status/<device_type>/<instance>
        if len(parts) < 4:
            _LOGGER.debug("Ignoring unexpected topic format: %s", msg.topic)
            return

        _, status_word, device_type, instance = parts[:4]
        if status_word != "status":
            _LOGGER.debug("Ignoring non-status topic: %s", msg.topic)
            return

        discovery = {
            "type": device_type,
            "instance": instance,
            "payload": payload,
        }

        _LOGGER.debug("Dispatching discovery event: %s", discovery)
        async_dispatcher_send(self.hass, SIGNAL_DISCOVERY, discovery)
EOF

#######################################
# custom_components/rvc/light.py
#######################################
cat << 'EOF' > custom_components/rvc/light.py
"""Platform for RV-C lights."""
from __future__ import annotations

import json
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
)
from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_DISCOVERY,
    DIMMER_INSTANCE_LABELS,
    CC_SET_BRIGHTNESS,
    CC_OFF,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C lights dynamically from discovery events."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCLight] = {}

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "light":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)

        # Prefer your dimmer mapping; fall back to payload name; then generic
        label = DIMMER_INSTANCE_LABELS.get(inst_str)
        name = label or payload.get("name") or f"RVC Light {inst_str}"

        entity = entities.get(inst_str)
        if entity is None:
            entity = RVCLight(
                name=name,
                instance_id=inst_str,
                topic_prefix=entry.data.get("topic_prefix", "rvc"),
            )
            entities[inst_str] = entity
            async_add_entities([entity])

        entity.handle_mqtt(payload)

    unsub = await async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCLight(LightEntity):
    """Representation of an RV-C dimmer light."""

    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, name: str, instance_id: str, topic_prefix: str) -> None:
        self._attr_name = name
        self._instance = instance_id
        self._topic_prefix = topic_prefix
        self._attr_is_on = False
        self._attr_brightness = 255

    @property
    def unique_id(self) -> str:
        return f"rvc_light_{self._instance}"

    @property
    def _command_topic(self) -> str:
        # Example: rvc/command/light/36
        return f"{self._topic_prefix}/command/light/{self._instance}"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload.

        Supports both:
        - Raw RV-C JSON (with 'operating status (brightness)')
        - Simplified payloads with 'state' and 'brightness'
        """

        # Raw RV-C dimmer payload: "operating status (brightness)" 0–100
        if "operating status (brightness)" in payload:
            try:
                pct = float(payload["operating status (brightness)"])
                pct = max(0.0, min(100.0, pct))
                self._attr_brightness = int(round(pct * 2.55))
            except (TypeError, ValueError):
                pass

            # Consider >0 brightness as ON
            self._attr_is_on = self._attr_brightness > 0

        # Optional explicit 'state'
        if "state" in payload:
            state_str = str(payload["state"]).upper()
            if state_str in ("ON", "OFF"):
                self._attr_is_on = state_str == "ON"

        # Optional direct brightness 0–255
        if "brightness" in payload:
            try:
                self._attr_brightness = int(payload["brightness"])
            except (TypeError, ValueError):
                pass

        # Optional human-readable name override
        if "name" in payload:
            self._attr_name = str(payload["name"])

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on (with optional brightness)."""

        brightness = kwargs.get(ATTR_BRIGHTNESS, self._attr_brightness or 255)
        brightness = max(0, min(255, int(brightness)))
        self._attr_brightness = brightness
        self._attr_is_on = True

        # Convert to 0–100% for RV-C
        pct = int(round(brightness / 2.55))
        pct = max(0, min(100, pct))

        payload = {
            "cc": CC_SET_BRIGHTNESS,  # 00: Set Brightness
            "brightness": pct,        # 0–100
        }

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""

        self._attr_is_on = False
        self._attr_brightness = 0

        payload = {
            "cc": CC_OFF,  # 02: Off
            "brightness": 0,
        }

        await mqtt.async_publish(
            self.hass,
            self._command_topic,
            json.dumps(payload),
            qos=0,
            retain=False,
        )

        self.async_write_ha_state()
EOF

#######################################
# custom_components/rvc/climate.py
#######################################
cat << 'EOF' > custom_components/rvc/climate.py
"""Platform for RV-C climate devices."""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVERY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C climate entities from discovery."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCClimate] = {}

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "climate":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)
        name = payload.get("name") or f"RVC Climate {inst_str}"

        entity = entities.get(inst_str)
        if entity is None:
            entity = RVCClimate(name=name, instance_id=inst_str)
            entities[inst_str] = entity
            async_add_entities([entity])

        entity.handle_mqtt(payload)

    unsub = await async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCClimate(ClimateEntity):
    """Representation of an RV-C climate zone."""

    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.AUTO]

    def __init__(self, name: str, instance_id: str) -> None:
        self._attr_name = name
        self._instance = instance_id
        self._attr_hvac_mode = HVACMode.AUTO
        self._attr_target_temperature = 22.0
        self._attr_current_temperature = None

    @property
    def unique_id(self) -> str:
        return f"rvc_climate_{self._instance}"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update internal state from an MQTT payload."""
        if "current_temperature" in payload:
            try:
                self._attr_current_temperature = float(payload["current_temperature"])
            except (TypeError, ValueError):
                pass

        if "target_temperature" in payload:
            try:
                self._attr_target_temperature = float(payload["target_temperature"])
            except (TypeError, ValueError):
                pass

        if "hvac_mode" in payload:
            mode = str(payload["hvac_mode"]).lower()
            for m in self._attr_hvac_modes:
                if m.value == mode:
                    self._attr_hvac_mode = m
                    break

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._attr_hvac_mode = hvac_mode
        # TODO: publish MQTT command for HVAC mode
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        if "temperature" in kwargs:
            self._attr_target_temperature = float(kwargs["temperature"])
            # TODO: publish MQTT command for target temperature
            self.async_write_ha_state()
EOF

#######################################
# custom_components/rvc/sensor.py
#######################################
cat << 'EOF' > custom_components/rvc/sensor.py
"""Platform for RV-C sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVERY


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C sensors from discovery."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCSensor] = {}

    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "sensor":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]
        inst_str = str(instance)
        name = payload.get("name") or f"RVC Sensor {inst_str}"

        entity = entities.get(inst_str)
        if entity is None:
            entity = RVCSensor(name=name, instance_id=inst_str)
            entities[inst_str] = entity
            async_add_entities([entity])

        entity.handle_mqtt(payload)

    unsub = await async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCSensor(SensorEntity):
    """Generic RV-C sensor entity."""

    def __init__(self, name: str, instance_id: str) -> None:
        self._attr_name = name
        self._instance = instance_id
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = None

    @property
    def unique_id(self) -> str:
        return f"rvc_sensor_{self._instance}"

    def handle_mqtt(self, payload: dict[str, Any]) -> None:
        """Update state from MQTT payload.

        Expected payload keys:
          - value: numeric or string
          - unit: optional unit (e.g. "°C", "°F", "%")
          - device_class: optional device class (temperature, humidity, etc.)
        """
        if "value" in payload:
            self._attr_native_value = payload["value"]

        if "unit" in payload:
            self._attr_native_unit_of_measurement = payload["unit"]

        if "device_class" in payload:
            self._attr_device_class = payload["device_class"]

        self.async_write_ha_state()
EOF

#######################################
# custom_components/rvc/services.yaml
#######################################
cat << 'EOF' > custom_components/rvc/services.yaml
rvc.ramp_up:
  description: "Ramp brightness up to target"
  fields:
    entity_id:
      description: "Target light"
      example: "light.rvc_light_36"
    duration:
      description: "Ramp duration in seconds"
      example: 5
      required: true
      selector:
        number:
          min: 1
          max: 60
EOF

#######################################
# custom_components/rvc/translations/en.json
#######################################
cat << 'EOF' > custom_components/rvc/translations/en.json
{
  "config": {
    "step": {
      "user": {
        "title": "Set up RV-C",
        "description": "Configure MQTT options for RV-C integration.",
        "data": {
          "topic_prefix": "MQTT topic prefix",
          "auto_discovery": "Enable auto discovery"
        }
      }
    }
  },
  "title": "RV-C Integration"
}
EOF

#######################################
# hacs.json
#######################################
cat << 'EOF' > hacs.json
{
  "name": "RV-C Integration",
  "content_in_root": false,
  "domain": "rvc",
  "country": "US",
  "homeassistant": "2024.8.0"
}
EOF

#######################################
# README.md
#######################################
cat << 'EOF' > README.md
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
EOF

#######################################
# LICENSE (MIT stub)
#######################################
cat << 'EOF' > LICENSE
MIT License

Copyright (c) 2025 Randy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF

#######################################
# CHANGELOG.md
#######################################
cat << 'EOF' > CHANGELOG.md
# Changelog

## 1.0.0

- Initial release of RV-C custom integration.
- MQTT-based discovery for lights, climate, and sensors.
- Dimmer naming based on instance mapping.
- Command topic for dimmers with CC and brightness percent.
EOF

#######################################
# .github/workflows/ci.yaml
#######################################
cat << 'EOF' > .github/workflows/ci.yaml
name: CI

on:
  push:
  pull_request:

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install tools
        run: |
          pip install flake8
      - name: Lint
        run: flake8 custom_components/rvc
EOF

echo "All files written. Next steps:"
echo "  git add ."
echo "  git commit -m \"Initial RV-C custom HA integration\""
echo "  git push origin main   # or 'master' depending on your default"

