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
from homeassistant.helpers.device_registry import DeviceInfo
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
                    initial_value=sensor_def["value"],  # Set initial value
                )
                entities[unique_key] = entity
                new_entities.append(entity)
            else:
                # Only update existing entities (they have hass set)
                entity.update_value(sensor_def["value"])

        if new_entities:
            async_add_entities(new_entities)

    unsub = async_dispatcher_connect(hass, SIGNAL_DISCOVERY, _discovery_callback)
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
        if "dc voltage" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_dc_voltage",
                "unique_id": f"rvc_inverter_{inst_str}_dc_voltage",
                "name": f"Inverter {inst_str} DC Voltage",
                "value": payload["dc voltage"],
                "unit": UnitOfElectricPotential.VOLT,
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "dc amperage" in payload:  # Note: RV-C uses "amperage" not "current"
            sensors.append({
                "unique_key": f"{inst_str}_dc_current",
                "unique_id": f"rvc_inverter_{inst_str}_dc_current",
                "name": f"Inverter {inst_str} DC Current",
                "value": payload["dc amperage"],
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
        if "fet temperature" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_fet_temp",
                "unique_id": f"rvc_inverter_{inst_str}_fet_temp",
                "name": f"Inverter {inst_str} FET Temperature",
                "value": payload["fet temperature"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "transformer temperature" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_transformer_temp",
                "unique_id": f"rvc_inverter_{inst_str}_transformer_temp",
                "name": f"Inverter {inst_str} Transformer Temperature",
                "value": payload["transformer temperature"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # AC_LOAD_STATUS - load percentage
    elif message_name.startswith("AC_LOAD_STATUS"):
        if "operating status" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_ac_load",
                "unique_id": f"rvc_ac_load_{inst_str}",
                "name": f"AC Load {inst_str}",
                "value": payload["operating status"],
                "unit": PERCENTAGE,
                "device_class": SensorDeviceClass.POWER_FACTOR,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # CHARGER_STATUS - charger state
    elif message_name.startswith("CHARGER_STATUS"):
        if "operating state" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_charger_state",
                "unique_id": f"rvc_charger_{inst_str}_state",
                "name": f"Charger {inst_str} State",
                "value": payload["operating state"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })

    # DC_SOURCE_STATUS_1 - Battery voltage and current (CRITICAL NEW SENSORS)
    elif message_name.startswith("DC_SOURCE_STATUS_1"):
        if "dc voltage" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_battery_voltage",
                "unique_id": f"rvc_battery_{inst_str}_voltage",
                "name": f"Battery {inst_str} Voltage",
                "value": payload["dc voltage"],
                "unit": UnitOfElectricPotential.VOLT,
                "device_class": SensorDeviceClass.VOLTAGE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "dc current" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_battery_current",
                "unique_id": f"rvc_battery_{inst_str}_current",
                "name": f"Battery {inst_str} Current",
                "value": payload["dc current"],
                "unit": UnitOfElectricCurrent.AMPERE,
                "device_class": SensorDeviceClass.CURRENT,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # DC_SOURCE_STATUS_2 - State of charge, temperature, time remaining (CRITICAL!)
    elif message_name.startswith("DC_SOURCE_STATUS_2"):
        if "state of charge" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_battery_soc",
                "unique_id": f"rvc_battery_{inst_str}_soc",
                "name": f"Battery {inst_str} State of Charge",
                "value": payload["state of charge"],
                "unit": PERCENTAGE,
                "device_class": SensorDeviceClass.BATTERY,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "source temperature" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_battery_temp",
                "unique_id": f"rvc_battery_{inst_str}_temperature",
                "name": f"Battery {inst_str} Temperature",
                "value": payload["source temperature"],
                "unit": UnitOfTemperature.CELSIUS,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "time remaining" in payload:
            # Time remaining in minutes
            sensors.append({
                "unique_key": f"{inst_str}_battery_time_remaining",
                "unique_id": f"rvc_battery_{inst_str}_time_remaining",
                "name": f"Battery {inst_str} Time Remaining",
                "value": payload["time remaining"],
                "unit": "min",
                "device_class": SensorDeviceClass.DURATION,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # DC_SOURCE_STATUS_3 - State of health, capacity remaining
    elif message_name.startswith("DC_SOURCE_STATUS_3"):
        if "state of health" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_battery_soh",
                "unique_id": f"rvc_battery_{inst_str}_soh",
                "name": f"Battery {inst_str} State of Health",
                "value": payload["state of health"],
                "unit": PERCENTAGE,
                "device_class": None,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "capacity remaining" in payload:
            # Capacity in Amp-hours
            sensors.append({
                "unique_key": f"{inst_str}_battery_capacity_remaining",
                "unique_id": f"rvc_battery_{inst_str}_capacity",
                "name": f"Battery {inst_str} Capacity Remaining",
                "value": payload["capacity remaining"],
                "unit": "Ah",
                "device_class": None,
                "state_class": SensorStateClass.MEASUREMENT,
            })

    # WATERHEATER_STATUS - water temperature and operating status
    elif message_name.startswith("WATERHEATER_STATUS"):
        if "water temperature F" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_temp",
                "unique_id": f"rvc_waterheater_{inst_str}_temperature",
                "name": f"Water Heater {inst_str} Temperature",
                "value": payload["water temperature F"],
                "unit": UnitOfTemperature.FAHRENHEIT,
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
            })
        if "operating modes definition" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_mode",
                "unique_id": f"rvc_waterheater_{inst_str}_mode",
                "name": f"Water Heater {inst_str} Mode",
                "value": payload["operating modes definition"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })
        if "burner status definition" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_burner",
                "unique_id": f"rvc_waterheater_{inst_str}_burner",
                "name": f"Water Heater {inst_str} Burner",
                "value": payload["burner status definition"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })
        if "thermostat status definition" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_thermostat",
                "unique_id": f"rvc_waterheater_{inst_str}_thermostat",
                "name": f"Water Heater {inst_str} Thermostat",
                "value": payload["thermostat status definition"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })
        if "dc power failure status definition" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_dc_power",
                "unique_id": f"rvc_waterheater_{inst_str}_dc_power",
                "name": f"Water Heater {inst_str} DC Power",
                "value": payload["dc power failure status definition"],
                "unit": None,
                "device_class": None,
                "state_class": None,
            })
        if "failure to ignite status definition" in payload:
            sensors.append({
                "unique_key": f"{inst_str}_water_heater_ignite",
                "unique_id": f"rvc_waterheater_{inst_str}_ignite_status",
                "name": f"Water Heater {inst_str} Ignite Status",
                "value": payload["failure to ignite status definition"],
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
        initial_value: Any = None,
    ) -> None:
        """Initialize the sensor."""
        self._attr_name = name
        self._attr_has_entity_name = False  # Use our name as-is
        self._attr_unique_id = unique_id
        self._attr_native_value = initial_value
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_state_class = state_class

        # Extract instance and sensor type from unique_id for device grouping
        # unique_id format examples: "rvc_battery_1_voltage", "rvc_inverter_0_dc_voltage"
        self._determine_device_info()

    def _determine_device_info(self) -> None:
        """Determine device info based on unique_id pattern."""
        uid = self._attr_unique_id

        if "waterheater" in uid:
            self._device_id = "water_heater"
            self._device_name = "RVC Water Heater"
            self._device_model = "Water Heater System"
        elif "battery" in uid or "dc_source" in uid:
            self._device_id = "power_system"
            self._device_name = "RVC Power System"
            self._device_model = "Battery & Power Management"
        elif "inverter" in uid:
            self._device_id = "power_system"
            self._device_name = "RVC Power System"
            self._device_model = "Inverter & Power Management"
        elif "tank" in uid or uid.startswith("rvc_sensor_"):
            # Tank sensors use old format "rvc_sensor_{instance}"
            self._device_id = "tank_system"
            self._device_name = "RVC Tank System"
            self._device_model = "Tank Monitoring"
        elif "thermostat" in uid or "ambient" in uid:
            self._device_id = "climate_system"
            self._device_name = "RVC Climate System"
            self._device_model = "Temperature Monitoring"
        elif "charger" in uid:
            self._device_id = "power_system"
            self._device_name = "RVC Power System"
            self._device_model = "Charger Management"
        else:
            self._device_id = "sensors"
            self._device_name = "RVC Sensors"
            self._device_model = "Monitoring System"

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._attr_unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group sensors."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer="RV-C",
            model=self._device_model,
            via_device=(DOMAIN, "main_controller"),
        )

    def update_value(self, value: Any) -> None:
        """Update the sensor value and write state."""
        self._attr_native_value = value
        self.async_write_ha_state()
