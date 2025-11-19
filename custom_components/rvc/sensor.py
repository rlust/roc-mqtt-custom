"""Platform for RV-C sensors."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfFrequency,
    PERCENTAGE,
)

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
        message_name = payload.get("name", "")

        # Extract multiple sensor values from RV-C payload based on message type
        sensors_to_create = _extract_sensor_definitions(message_name, instance, payload)

        new_entities = []
        for sensor_def in sensors_to_create:
            unique_key = sensor_def["unique_key"]

            entity = entities.get(unique_key)
            if entity is None:
                entity = RVCSensor(
                    name=sensor_def["name"],
                    unique_id=sensor_def["unique_id"],
                    device_class=sensor_def.get("device_class"),
                    unit=sensor_def.get("unit"),
                    state_class=sensor_def.get("state_class"),
                )
                entities[unique_key] = entity
                new_entities.append(entity)

            # Update value
            entity.update_value(sensor_def["value"])

        if new_entities:
            async_add_entities(new_entities)

    unsub = await async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
    data["unsub_dispatchers"].append(unsub)


def _extract_sensor_definitions(
    message_name: str, instance: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Extract sensor definitions from RV-C payload based on message type."""
    sensors = []
    inst_str = str(instance)

    # TANK_STATUS - relative level, instance definition
    if message_name.startswith("TANK_STATUS"):
        if "relative level" in payload:
            tank_type = payload.get("instance definition", "Tank").replace(" tank", "")
            # BACKWARD COMPATIBILITY: Use old unique_id format to avoid orphaning existing entities
            sensors.append({
                "unique_key": f"{inst_str}_tank_level",
                "unique_id": f"rvc_sensor_{inst_str}",  # Keep old format for compatibility
                "name": f"{tank_type} Tank Level",
                "value": payload["relative level"],
                "unit": PERCENTAGE,
                "device_class": None,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # THERMOSTAT_AMBIENT_STATUS - ambient temperature
    elif message_name.startswith("THERMOSTAT_AMBIENT_STATUS"):
        if "ambient temp F" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_ambient_temp",
                "unique_id": f"rvc_thermostat_{inst_str}_ambient",
                "name": f"Zone {inst_str} Ambient Temperature",
                "value": payload["ambient temp F"],
                "unit": UnitOfTemperature.FAHRENHEIT,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        elif "ambient temp" in payload:  # Celsius fallback
            sensors.append({
                "unique_key": f"{inst_str}_ambient_temp",
                "unique_id": f"rvc_thermostat_{inst_str}_ambient",
                "name": f"Zone {inst_str} Ambient Temperature",
                "value": payload["ambient temp"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # INVERTER_DC_STATUS - DC voltage and current
    elif message_name.startswith("INVERTER_DC_STATUS"):
        if "DC_voltage" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_dc_voltage",
                "unique_id": f"rvc_inverter_{inst_str}_dc_voltage",
                "name": f"Inverter {inst_str} DC Voltage",
                "value": payload["DC_voltage"],
                "unit": UnitOfElectricPotential.VOLT,
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "DC_current" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_dc_current",
                "unique_id": f"rvc_inverter_{inst_str}_dc_current",
                "name": f"Inverter {inst_str} DC Current",
                "value": payload["DC_current"],
                "unit": UnitOfElectricCurrent.AMPERE,
                "device_class": SensorDeviceClass.CURRENT,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # INVERTER_AC_STATUS_1 - frequency
    elif message_name.startswith("INVERTER_AC_STATUS"):
        if "frequency" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_ac_frequency",
                "unique_id": f"rvc_inverter_{inst_str}_ac_frequency",
                "name": f"Inverter {inst_str} AC Frequency",
                "value": payload["frequency"],
                "unit": UnitOfFrequency.HERTZ,
                "device_class": SensorDeviceClass.FREQUENCY,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # INVERTER_TEMPERATURE_STATUS - temperatures
    elif message_name.startswith("INVERTER_TEMPERATURE_STATUS"):
        if "FET_temperature" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_fet_temp",
                "unique_id": f"rvc_inverter_{inst_str}_fet_temp",
                "name": f"Inverter {inst_str} FET Temperature",
                "value": payload["FET_temperature"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "transformer_temperature" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_transformer_temp",
                "unique_id": f"rvc_inverter_{inst_str}_transformer_temp",
                "name": f"Inverter {inst_str} Transformer Temperature",
                "value": payload["transformer_temperature"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # AC_LOAD_STATUS - load percentage
    elif message_name.startswith("AC_LOAD_STATUS"):
        if "AC_load" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_ac_load",
                "unique_id": f"rvc_ac_load_{inst_str}",
                "name": f"AC Load {inst_str}",
                "value": payload["AC_load"],
                "unit": PERCENTAGE,
                "device_class": SensorDeviceClass.POWER_FACTOR,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # CHARGER_STATUS - charger state
    elif message_name.startswith("CHARGER_STATUS"):
        if "charger_state" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_charger_state",
                "unique_id": f"rvc_charger_{inst_str}_state",
                "name": f"Charger {inst_str} State",
                "value": payload["charger_state"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })

    # Fallback for generic sensor payloads (with "value" field)
    if not sensors and "value" in payload:
        sensors.append({
            "unique_key": inst_str,
            "unique_id": f"rvc_sensor_{inst_str}",
            "name": payload.get("name", f"RVC Sensor {inst_str}"),
            "value": payload["value"],
            "unit": payload.get("unit"),
            "device_class": payload.get("device_class"),
            "state_class": SensorStateClass.MEASUREMENT if payload.get("value") is not None else None,
        })

    return sensors


class RVCSensor(SensorEntity):
    """RV-C sensor entity with proper field extraction."""

    def __init__(
        self,
        name: str,
        unique_id: str,
        device_class: str | None = None,
        unit: str | None = None,
        state_class: str | None = None,
    ) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_unique_id = unique_id
        self._attr_native_value = None
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._attr_unique_id

    def update_value(self, value: Any) -> None:
        """Update the sensor value and write state."""
        self._attr_native_value = value
        self.async_write_ha_state()
