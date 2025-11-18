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
