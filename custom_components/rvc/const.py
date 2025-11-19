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

# Command codes for dimmer control (CC) — from dimmer command usage doc
# See: dimmer command useage.md for full command reference
CC_SET_BRIGHTNESS = 0  # Set Level (with brightness 0-100)
CC_ON = 1              # On (Duration)
CC_ON_DELAY = 2        # On (Delay)
CC_OFF = 3             # Off (Delay)
CC_STOP = 4            # Stop
CC_TOGGLE = 5          # Toggle
CC_MEMORY_OFF = 6      # Memory Off
CC_RAMP_BRIGHTNESS = 17  # Ramp Brightness
CC_RAMP_TOGGLE = 18    # Ramp Toggle
CC_RAMP_UP = 19        # Ramp Up
CC_RAMP_DOWN = 20      # Ramp Down
CC_RAMP_UP_DOWN = 21   # Ramp Down/Up

# Dimmable light instances (can adjust brightness with command 0)
# Non-dimmable instances (25-35) are relays that only support on/off with command 2
DIMMABLE_LIGHTS = {
    "25", "26", "27", "28", "29",  # Bedroom area
    "30", "31", "32", "33", "34",  # Bathroom areas
    "35",                           # Entry
}

# Human-friendly labels for dimmer/light instances (from actual RV device mapping)
DIMMER_INSTANCE_LABELS: dict[str, str] = {
    # Lights (25-60)
    "25": "Bed Ceiling Lts A",
    "26": "Bed Ceiling Lts B",
    "27": "Bed Accent",
    "28": "Bed Vanity",
    "29": "Courtesy",
    "30": "RR Bath Ceiling",
    "31": "RR Bath Lav Lts",
    "32": "RR Bath Accent",
    "33": "Mid Bath Ceiling",
    "34": "Mid Bath Accent",
    "35": "Entry Ceiling",
    "36": "Living Edge",
    "37": "Livrm Ceiling A",
    "38": "Livrm Ceiling B",
    "39": "Livrm Accent A",
    "40": "Livrm Accent B",
    "41": "Sofa Ceiling",
    "42": "Kitchen Ceiling",
    # 43 missing
    "44": "D/S Slide",
    "45": "Dinette",
    "46": "Sink",
    "47": "Midship",
    # 48 missing
    "49": "Door Awning Extend",
    "50": "Door Awning Retract",
    "51": "Awning D/S",
    "52": "Awning P/S",
    "53": "Cargo",
    "54": "Under Slide",
    # 55 missing
    "56": "Bed Reading",
    "57": "Security D/S",
    "58": "Security P/S",
    "59": "Security Motion",
    "60": "Porch",
}

# Switch/relay instance labels (non-dimmable devices)
SWITCH_INSTANCE_LABELS: dict[str, str] = {
    "13": "Satellite Dome",
    "14": "Entry Door",
    "15": "Gen Stop",
    "16": "Water Pump",
    "17": "Entry Door Unlock",
    "18": "Gen Start",
}

# Cover/slide/awning instance labels
COVER_INSTANCE_LABELS: dict[str, str] = {
    # Awnings (extend/retract/stop)
    "19": "Rear Awning",
    "22": "Front Awning",
    "49": "Door Awning",
    # Slides (extend/retract)
    "181": "Kitchen Slide",
    "182": "Kitchen Slide",  # Retract command
    "183": "Super Slide",
    "184": "Super Slide",  # Retract command
    "185": "Vanity Slide",
    "186": "Vanity Slide",  # Retract command
    "187": "Bed Slide",
    "188": "Bed Slide",  # Retract command
}
