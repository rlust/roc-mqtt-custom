"""Constants for the RVC integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rvc"

CONF_TOPIC_PREFIX = "topic_prefix"
CONF_AUTO_DISCOVERY = "auto_discovery"
CONF_COMMAND_TOPIC = "command_topic"
CONF_GPS_TOPIC = "gps_topic"
CONF_AVAILABILITY_TIMEOUT = "availability_timeout"

DEFAULT_TOPIC_PREFIX = "rvc"
DEFAULT_AUTO_DISCOVERY = True
DEFAULT_COMMAND_TOPIC = "node-red/rvc/commands"
DEFAULT_GPS_TOPIC = "CP/#"
DEFAULT_AVAILABILITY_TIMEOUT = 300  # seconds
DEFAULT_LIGHT_AVAILABILITY_TIMEOUT = 0
DEFAULT_SWITCH_AVAILABILITY_TIMEOUT = 0
DEFAULT_LOCK_AVAILABILITY_TIMEOUT = 0
DEFAULT_COVER_AVAILABILITY_TIMEOUT = 0

SIGNAL_DISCOVERY = "rvc_discovery_event"

PLATFORMS: list[Platform] = [
    Platform.LIGHT,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.LOCK,
    Platform.COVER,
    Platform.DEVICE_TRACKER,
    Platform.SWITCH,
    Platform.BUTTON,
]

# Node-RED MQTT Command Format
# Topic: node-red/rvc/commands
# Payload: "instance command brightness" (space-separated)
# Commands: 2 = ON, 3 = OFF, 5 = TOGGLE

# Dimmable light instances (support brightness control)
# All lights use command 2 (ON) with brightness 0-100
# Non-dimmable lights ignore brightness and use ON/OFF commands
DIMMABLE_LIGHTS = {
    "25", "26", "27", "28", "29",  # Bedroom area
    "30", "31", "32", "33", "34",  # Bathroom areas
    "35",                           # Entry
}

# Light area groupings for device organization
# Lights in these sets will be grouped together in Home Assistant
LIVING_AREA_LIGHTS = {
    "35",  # Entry Ceiling
    "36",  # Living Edge
    "37",  # Livrm Ceiling A
    "38",  # Livrm Ceiling B
    "39",  # Livrm Accent A
    "40",  # Livrm Accent B
    "41",  # Sofa Ceiling
    "42",  # Kitchen Ceiling
    "44",  # D/S Slide
    "45",  # Dinette
    "46",  # Sink
    "47",  # Midship
}

BEDROOM_AREA_LIGHTS = {
    "25",  # Bed Ceiling Lts A
    "26",  # Bed Ceiling Lts B
    "27",  # Bed Accent
    "28",  # Bed Vanity
    "29",  # Courtesy
    "56",  # Bed Reading
}

BATHROOM_AREA_LIGHTS = {
    "30",  # RR Bath Ceiling
    "31",  # RR Bath Lav Lts
    "32",  # RR Bath Accent
    "33",  # Mid Bath Ceiling
    "34",  # Mid Bath Accent
}

EXTERIOR_AREA_LIGHTS = {
    "51",  # Awning D/S
    "52",  # Awning P/S
    "53",  # Cargo
    "54",  # Under Slide
    "57",  # Security D/S
    "58",  # Security P/S
    "59",  # Security Motion
    "60",  # Porch
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
    # 48-50 are awning controls (handled by cover platform)
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
    "16": "Water Pump",
}

BUTTON_DEFINITIONS: dict[str, dict[str, str]] = {
    "generator_start": {
        "name": "Generator Start",
        "instance": "18",
        "command": "2",
        "icon": "mdi:play-circle"
    },
    "generator_stop": {
        "name": "Generator Stop",
        "instance": "15",
        "command": "2",
        "icon": "mdi:stop-circle"
    },
}

SWITCH_DEFINITIONS: dict[str, dict[str, str]] = {
    "satellite_dome": {
        "name": "Satellite Dome",
        "instance": "13",
    },
    "water_pump": {
        "name": "Water Pump",
        "instance": "16",
    },
}

# Lock definitions for door lock entities
# Each lock has separate lock and unlock instance IDs (momentary triggers)
LOCK_DEFINITIONS: dict[str, dict[str, str]] = {
    "entry_door": {
        "name": "Entry Door",
        "lock": "14",    # Instance to lock the door
        "unlock": "17",  # Instance to unlock the door
    },
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

# Awning definitions for cover entities
# Each awning has extend, retract, and optional stop instance IDs
AWNING_DEFINITIONS: dict[str, dict[str, str]] = {
    "rear_awning": {
        "name": "Rear Awning",
        "extend": "19",
        "retract": "20",
        "stop": "21",
    },
    "front_awning": {
        "name": "Front Awning",
        "extend": "22",
        "retract": "23",
        "stop": "24",
    },
    "door_awning": {
        "name": "Door Awning",
        "extend": "49",
        "retract": "50",
        "stop": "",  # No stop instance for door awning
    },
}

# Slide definitions for cover entities
# WARNING: Slides control heavy motors - ensure area is clear before operating!
# Each slide has extend and retract instance IDs (no stop function)
SLIDE_DEFINITIONS: dict[str, dict[str, str]] = {
    "kitchen_slide": {
        "name": "Kitchen Slide",
        "extend": "181",
        "retract": "182",
    },
    "super_slide": {
        "name": "Super Slide",
        "extend": "183",
        "retract": "184",
    },
    "vanity_slide": {
        "name": "Vanity Slide",
        "extend": "185",
        "retract": "186",
    },
    "bed_slide": {
        "name": "Bed Slide",
        "extend": "187",
        "retract": "188",
    },
}
