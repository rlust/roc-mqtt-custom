"""Platform for RV-C GPS device tracking."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.device_tracker import SourceType
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_DISCOVERY

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RV-C GPS device tracker."""

    data = hass.data[DOMAIN][entry.entry_id]
    entities: dict[str, RVCGPSTracker] = {}

    _LOGGER.info("Setting up RV-C GPS device tracker")

    # Discovery callback handles GPS updates
    async def _discovery_callback(discovery: dict[str, Any]) -> None:
        if discovery["type"] != "device_tracker":
            return

        instance = discovery["instance"]
        payload = discovery["payload"]

        entity = entities.get(instance)
        if entity is None:
            # Create GPS tracker entity
            _LOGGER.info("Creating GPS device tracker entity")
            entity = RVCGPSTracker()
            entities[instance] = entity
            async_add_entities([entity])

        # Update GPS location from MQTT payload
        entity.handle_gps(payload)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


class RVCGPSTracker(TrackerEntity):
    """Representation of an RV-C GPS tracker."""

    def __init__(self) -> None:
        self._attr_name = "RV GPS"
        self._attr_has_entity_name = False
        self._latitude: float | None = None
        self._longitude: float | None = None
        self._altitude: float | None = None
        self._speed: float | None = None
        self._heading: float | None = None
        self._gps_accuracy: float | None = None
        self._attr_available = False  # Start as unavailable until GPS data arrives

        # Store GPS data as extra state attributes
        self._attr_extra_state_attributes = {
            "altitude": None,
            "speed": None,
            "heading": None,
            "climb": None,
            "gps_time": None,
            "gps_mode": None,
            "gps_status": None,
            "position_error": None,
            "speed_error": None,
        }

        _LOGGER.info("Initialized RVCGPSTracker")

    @property
    def unique_id(self) -> str:
        return "rvc_gps_tracker"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for GPS tracker."""
        return DeviceInfo(
            identifiers={(DOMAIN, "gps_system")},
            name="RV GPS System",
            manufacturer="RV-C",
            model="GPS Receiver",
            via_device=(DOMAIN, "main_controller"),
        )

    @property
    def source_type(self) -> SourceType:
        """Return the source type (GPS)."""
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        """Return latitude value of the device."""
        return self._latitude

    @property
    def longitude(self) -> float | None:
        """Return longitude value of the device."""
        return self._longitude

    @property
    def location_accuracy(self) -> int:
        """Return the GPS accuracy in meters."""
        if self._gps_accuracy is not None:
            return int(self._gps_accuracy)
        return 0

    def handle_gps(self, payload: dict[str, Any]) -> None:
        """Update GPS location from MQTT payload."""
        _LOGGER.debug("GPS tracker received payload: %s", payload)

        # GPSD TPV (Time Position Velocity) format
        if "lat" in payload and "lon" in payload:
            self._latitude = float(payload["lat"])
            self._longitude = float(payload["lon"])
            self._attr_available = True

            _LOGGER.info(
                "GPS location updated: lat=%.6f, lon=%.6f",
                self._latitude,
                self._longitude,
            )

        # Optional fields
        if "alt" in payload:
            self._altitude = float(payload["alt"])
            self._attr_extra_state_attributes["altitude"] = f"{self._altitude:.2f} m"

        if "speed" in payload:
            # Convert m/s to km/h for speed attribute
            self._speed = float(payload["speed"])
            speed_kmh = self._speed * 3.6
            self._attr_extra_state_attributes["speed"] = f"{speed_kmh:.1f} km/h"

        if "track" in payload:
            self._heading = float(payload["track"])
            self._attr_extra_state_attributes["heading"] = f"{self._heading:.1f}°"

        if "climb" in payload:
            climb = float(payload["climb"])
            self._attr_extra_state_attributes["climb"] = f"{climb:.2f} m/s"

        if "time" in payload:
            self._attr_extra_state_attributes["gps_time"] = payload["time"]

        if "mode" in payload:
            mode_names = {1: "No Fix", 2: "2D Fix", 3: "3D Fix"}
            mode = payload["mode"]
            self._attr_extra_state_attributes["gps_mode"] = mode_names.get(mode, f"Mode {mode}")

        if "status" in payload:
            status_names = {0: "No Fix", 1: "Fix", 2: "DGPS Fix"}
            status = payload["status"]
            self._attr_extra_state_attributes["gps_status"] = status_names.get(status, f"Status {status}")

        # Position accuracy (use horizontal position error)
        if "epx" in payload and "epy" in payload:
            epx = float(payload["epx"])
            epy = float(payload["epy"])
            # Calculate horizontal accuracy as RMS of x and y errors
            self._gps_accuracy = (epx**2 + epy**2) ** 0.5
            self._attr_extra_state_attributes["position_error"] = f"{self._gps_accuracy:.1f} m"

        if "eps" in payload:
            eps = float(payload["eps"])
            self._attr_extra_state_attributes["speed_error"] = f"{eps:.2f} m/s"

        self.async_write_ha_state()
