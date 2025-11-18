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
