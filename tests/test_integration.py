"""Home Assistant-native tests for the RV-C custom component."""

from __future__ import annotations

import time
from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_CLOSING, STATE_OPENING, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.rvc.climate import (
    TEMP_DOWN_SUFFIX,
    TEMP_UP_SUFFIX,
    RVCClimate,
)
from custom_components.rvc.const import (
    CONF_AUTO_DISCOVERY,
    CONF_AVAILABILITY_TIMEOUT,
    CONF_COMMAND_TOPIC,
    CONF_GPS_TOPIC,
    CONF_THERMOSTAT_BRIDGE_MODE,
    CONF_TOPIC_PREFIX,
    DOMAIN,
    SIGNAL_DISCOVERY,
)
from custom_components.rvc.device_tracker import RVCGPSTracker
from custom_components.rvc.light import RVCLight
from custom_components.rvc.sensor import _extract_sensor_definitions

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


def test_ac_load_operating_status_is_a_percentage_not_power_factor() -> None:
    """AC load operating status retains its documented percentage semantics."""
    definitions = _extract_sensor_definitions("AC_LOAD_STATUS", "212", {"operating status": 75})
    operating_status = next(item for item in definitions if item["unique_key"] == "212_ac_load")
    assert operating_status["unit"] == "%"
    assert operating_status["device_class"] is None


@pytest.fixture
def rvc_entry() -> MockConfigEntry:
    """Return a representative RV-C config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="RV-C",
        data={CONF_TOPIC_PREFIX: "RVC", CONF_AUTO_DISCOVERY: True},
        options={
            CONF_TOPIC_PREFIX: "RVC",
            CONF_AUTO_DISCOVERY: True,
            CONF_COMMAND_TOPIC: "node-red/rvc/commands",
            CONF_GPS_TOPIC: "CP/#",
            CONF_AVAILABILITY_TIMEOUT: 300,
            CONF_THERMOSTAT_BRIDGE_MODE: True,
        },
        version=2,
    )


@pytest.fixture
async def loaded_entry(hass: HomeAssistant, rvc_entry: MockConfigEntry):
    """Set up RV-C with MQTT I/O replaced by in-process mocks."""
    unsubscribe = Mock()
    with (
        patch(
            "homeassistant.components.mqtt.async_subscribe",
            AsyncMock(return_value=unsubscribe),
        ),
        patch("homeassistant.components.mqtt.async_publish", AsyncMock()) as publish,
    ):
        rvc_entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(rvc_entry.entry_id)
        await hass.async_block_till_done()
        yield rvc_entry, publish, unsubscribe


async def test_setup_unload_and_reload(hass: HomeAssistant, loaded_entry) -> None:
    """The real component and all platforms support their entry lifecycle."""
    entry, _, unsubscribe = loaded_entry
    assert entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data
    assert hass.states.get("switch.aqua_hot_electric").state == STATE_UNAVAILABLE
    assert hass.states.get("switch.water_pump").state == STATE_UNAVAILABLE

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert unsubscribe.called

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_config_and_options_flow(hass: HomeAssistant) -> None:
    """Config and options flows run through Home Assistant's flow manager."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TOPIC_PREFIX: "RVC", CONF_AUTO_DISCOVERY: True},
    )
    assert result["type"] == "create_entry"

    entry = result["result"]
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["type"] == "form"
    assert options["step_id"] == "init"


async def test_dynamic_sensor_availability_and_sentinel(hass: HomeAssistant, loaded_entry) -> None:
    """Sensors are fresh only after valid telemetry and sentinels are unknown."""
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "1",
            "payload": {
                "name": "DC_SOURCE_STATUS_2",
                "instance": 1,
                "time remaining": 0xFFFF,
            },
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.battery_1_time_remaining")
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "1",
            "payload": {
                "name": "DC_SOURCE_STATUS_2",
                "instance": 1,
                "time remaining": 125,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.battery_1_time_remaining").state == "125"

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "1",
            "payload": {
                "name": "DC_SOURCE_STATUS_2",
                "instance": 1,
                "time remaining": 0xFFFF,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.battery_1_time_remaining").state == STATE_UNKNOWN

    with patch("custom_components.rvc.availability.time.time", return_value=time.time() + 301):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=301), fire_all=True)
        await hass.async_block_till_done()
    assert hass.states.get("sensor.battery_1_time_remaining").state == STATE_UNAVAILABLE

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "8",
            "payload": {
                "name": "TANK_STATUS",
                "instance": 8,
                "instance definition": "fresh water tank",
                "relative level": 0xFF,
                "resolution": 100,
            },
        },
    )
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "99",
            "payload": {
                "name": "Generic Measurement",
                "instance": 99,
                "value": 255,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.fresh_water_tank_level").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.generic_measurement").state == "255"


async def test_rapid_dynamic_sensor_discovery_keeps_newest_payload(hass: HomeAssistant, loaded_entry) -> None:
    """Repeated discovery before entity attachment preserves the newest value."""
    for value in (10, 20, 30):
        async_dispatcher_send(
            hass,
            SIGNAL_DISCOVERY,
            {
                "type": "sensor",
                "instance": "98",
                "payload": {
                    "name": "Rapid Measurement",
                    "instance": 98,
                    "value": value,
                    "unit": "%",
                },
            },
        )

    await hass.async_block_till_done()
    state = hass.states.get("sensor.rapid_measurement")
    assert state is not None
    assert state.state == "30"

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "98",
            "payload": {
                "name": "Rapid Measurement",
                "instance": 98,
                "value": 40,
                "unit": "%",
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.rapid_measurement").state == "40"


async def test_rapid_gps_discovery_keeps_newest_payload(hass: HomeAssistant, loaded_entry) -> None:
    """GPS updates may race entity attachment without losing the newest fix."""
    for latitude, longitude in ((26.10, -81.70), (26.20, -81.80)):
        async_dispatcher_send(
            hass,
            SIGNAL_DISCOVERY,
            {
                "type": "device_tracker",
                "instance": "gps",
                "payload": {
                    "lat": latitude,
                    "lon": longitude,
                    "mode": 3,
                },
            },
        )

    await hass.async_block_till_done()
    state = hass.states.get("device_tracker.rv_gps")
    assert state is not None
    assert state.attributes["latitude"] == pytest.approx(26.20)
    assert state.attributes["longitude"] == pytest.approx(-81.80)

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "device_tracker",
            "instance": "gps",
            "payload": {"lat": 26.30, "lon": -81.90, "mode": 3},
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("device_tracker.rv_gps")
    assert state.attributes["latitude"] == pytest.approx(26.30)
    assert state.attributes["longitude"] == pytest.approx(-81.90)


async def test_parent_device_exists_before_child_registration(hass: HomeAssistant, loaded_entry) -> None:
    """Every RV-C child device resolves its stable main-controller parent."""
    registry = dr.async_get(hass)
    parent = registry.async_get_device(identifiers={(DOMAIN, "main_controller")})
    assert parent is not None

    child_devices = [
        device
        for device in registry.devices.values()
        if device.id != parent.id and any(identifier[0] == DOMAIN for identifier in device.identifiers)
    ]
    assert child_devices
    assert all(device.via_device_id == parent.id for device in child_devices)


async def test_custom_entity_services_register_and_invoke(hass: HomeAssistant, loaded_entry) -> None:
    """Custom light and climate services accept HA entity targets and invoke entities."""
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "35",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 35,
                "operating status (brightness)": 50,
            },
        },
    )
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "climate",
            "instance": "0",
            "payload": {
                "name": "THERMOSTAT_STATUS_1",
                "instance": 0,
                "operating mode definition": "cool",
                "setpoint temp cool F": 72.0,
                "fan mode definition": "auto",
            },
        },
    )
    await hass.async_block_till_done()

    for service in (
        "ramp_up",
        "ramp_down",
        "step_temperature_up",
        "step_temperature_down",
        "set_fan_profile",
    ):
        assert hass.services.has_service(DOMAIN, service)

    with (
        patch.object(RVCLight, "_async_send_ramp_command", new_callable=AsyncMock) as ramp,
        patch.object(RVCClimate, "_async_publish_signature", new_callable=AsyncMock) as step,
        patch.object(RVCClimate, "async_set_fan_mode", new_callable=AsyncMock) as fan,
    ):
        await hass.services.async_call(
            DOMAIN,
            "ramp_up",
            {"entity_id": "light.entry_ceiling", "duration": 5},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "ramp_down",
            {"entity_id": "light.entry_ceiling", "duration": 6},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "step_temperature_up",
            {"entity_id": "climate.ac_front"},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "step_temperature_down",
            {"entity_id": "climate.ac_front"},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "set_fan_profile",
            {"entity_id": "climate.ac_front", "fan_profile": "low"},
            blocking=True,
        )

    assert [call.args for call in ramp.await_args_list] == [(5, 19), (6, 20)]
    assert [call.args[0] for call in step.await_args_list] == [
        TEMP_UP_SUFFIX,
        TEMP_DOWN_SUFFIX,
    ]
    fan.assert_awaited_once_with("low")
    assert issubclass(RVCGPSTracker, TrackerEntity)


async def test_climate_ambient_correlation_and_heat_only_shape(hass: HomeAssistant, loaded_entry) -> None:
    """Ambient status feeds the matching zone and heat zones expose no fan."""
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "3",
            "payload": {
                "name": "THERMOSTAT_AMBIENT_STATUS",
                "instance": 3,
                "ambient temp F": 71.5,
            },
        },
    )
    await hass.async_block_till_done()

    state = hass.states.get("climate.front_heat_aqua_hot")
    assert state is not None
    assert state.state == STATE_UNKNOWN
    assert state.attributes["current_temperature"] == pytest.approx(21.9)
    assert state.attributes["hvac_modes"] == ["off", "heat"]
    assert "fan_modes" not in state.attributes


async def test_unrelated_climate_telemetry_keeps_command_pending(hass: HomeAssistant, loaded_entry) -> None:
    """Ambient telemetry must not imply a pending setpoint was confirmed."""
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "climate",
            "instance": "0",
            "payload": {
                "name": "THERMOSTAT_STATUS_1",
                "instance": 0,
                "operating mode definition": "cool",
                "setpoint temp cool F": 72.0,
                "fan mode definition": "auto",
            },
        },
    )
    await hass.async_block_till_done()

    prior_target = hass.states.get("climate.ac_front").attributes["temperature"]
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.ac_front", "temperature": prior_target},
        blocking=True,
    )
    pending = hass.states.get("climate.ac_front").attributes["command_pending"]
    assert pending["type"] == "temperature"

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "sensor",
            "instance": "0",
            "payload": {
                "name": "THERMOSTAT_AMBIENT_STATUS",
                "instance": 0,
                "ambient temp F": 71.0,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("climate.ac_front").attributes["command_pending"] == pending


async def test_command_publish_does_not_confirm_switch_state(hass: HomeAssistant, loaded_entry) -> None:
    """A successful MQTT publish records pending intent, not physical state."""
    _, publish, _ = loaded_entry
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "16",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 16,
                "operating status (brightness)": 100,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.water_pump").state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.water_pump"}, blocking=True)
    state = hass.states.get("switch.water_pump")
    assert state.state == "on"
    assert state.attributes["command_pending"] == {"type": "turn_off"}
    publish.assert_awaited()

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "16",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 16,
                "operating status (brightness)": 100,
            },
        },
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.water_pump").attributes["command_pending"] == {"type": "turn_off"}

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "16",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 16,
                "operating status (brightness)": 0,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get("switch.water_pump")
    assert state.state == "off"
    assert state.attributes["command_pending"] is None


async def test_awning_reports_confirmed_motion_without_inventing_endpoints(hass: HomeAssistant, loaded_entry) -> None:
    """Awning relay telemetry confirms motion, never an open/closed endpoint."""
    _, publish, _ = loaded_entry
    entity_id = "cover.rear_awning"

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == STATE_UNAVAILABLE

    # An inactive relay is valid/fresh telemetry, but it does not prove position.
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "19",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 19,
                "operating status (brightness)": 0,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["assumed_state"] is True

    await hass.services.async_call("cover", "open_cover", {"entity_id": entity_id}, blocking=True)
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["command_pending"] == {"type": "open"}
    publish.assert_awaited()

    # Zero/unrelated traffic neither confirms the requested motion nor clears it.
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "20",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 20,
                "operating status (brightness)": 0,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["command_pending"] == {"type": "open"}

    # Matching active relay telemetry confirms motion and clears matching intent.
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "19",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 19,
                "operating status (brightness)": 100,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_OPENING
    assert state.attributes["command_pending"] is None

    # Relay-off confirms only that motion stopped, not that the awning is open.
    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "19",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 19,
                "operating status (brightness)": 0,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["assumed_state"] is True

    publish.reset_mock()
    await hass.services.async_call("cover", "close_cover", {"entity_id": entity_id}, blocking=True)
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["command_pending"] == {"type": "close"}
    publish.assert_awaited()

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "20",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 20,
                "operating status (brightness)": 100,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_CLOSING
    assert state.attributes["command_pending"] is None

    async_dispatcher_send(
        hass,
        SIGNAL_DISCOVERY,
        {
            "type": "light",
            "instance": "20",
            "payload": {
                "name": "DC_DIMMER_STATUS_3",
                "instance": 20,
                "operating status (brightness)": 0,
            },
        },
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["assumed_state"] is True

    with patch("custom_components.rvc.availability.time.time", return_value=time.time() + 301):
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=301), fire_all=True)
        await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE
