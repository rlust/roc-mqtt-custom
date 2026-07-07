"""Tests for the RVC MQTT handler: classification and payload validation."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.rvc.mqtt_handler import RVCMQTTHandler, _coerce_float
from tests.conftest import get_dispatch_calls


def make_handler():
    return RVCMQTTHandler(hass=MagicMock(), config={})


def msg(topic, payload):
    if isinstance(payload, (dict, list)):
        payload = json.dumps(payload)
    return SimpleNamespace(topic=topic, payload=payload)


def receive(handler, message):
    before = len(get_dispatch_calls())
    asyncio.get_event_loop().run_until_complete(handler._message_received(message))
    return get_dispatch_calls()[before:]


class TestCoerceFloat:
    def test_numeric(self):
        assert _coerce_float("26.15") == pytest.approx(26.15)

    def test_none(self):
        assert _coerce_float(None) is None

    def test_garbage(self):
        assert _coerce_float("n/a") is None


class TestPayloadValidation:
    def test_invalid_json_is_dropped(self):
        assert receive(make_handler(), msg("rvc/status/light/24", "{not json")) == []

    def test_non_dict_json_is_dropped(self):
        assert receive(make_handler(), msg("rvc/status/light/24", [1, 2, 3])) == []
        assert receive(make_handler(), msg("rvc/status/light/24", "42")) == []

    def test_missing_instance_is_dropped(self):
        assert receive(make_handler(), msg("rvc/other", {"name": "DC_DIMMER_STATUS_3"})) == []

    def test_unmapped_name_is_dropped(self):
        assert receive(make_handler(), msg("rvc/other", {"name": "MYSTERY", "instance": 1})) == []


class TestClassification:
    def test_topic_layout_classification(self):
        calls = receive(make_handler(), msg("rvc/status/light/24", {"load status": "01"}))
        assert len(calls) == 1
        assert calls[0][1]["type"] == "light"
        assert calls[0][1]["instance"] == "24"

    def test_legacy_name_classification(self):
        calls = receive(
            make_handler(),
            msg("rvc/legacy", {"name": "DC_DIMMER_STATUS_3", "instance": 24}),
        )
        assert len(calls) == 1
        assert calls[0][1]["type"] == "light"

    def test_sensor_name_prefixes(self):
        calls = receive(
            make_handler(),
            msg("rvc/legacy", {"name": "TANK_STATUS", "instance": 1}),
        )
        assert calls[0][1]["type"] == "sensor"

    def test_thermostat_maps_to_climate(self):
        calls = receive(
            make_handler(),
            msg("rvc/legacy", {"name": "THERMOSTAT_STATUS_1", "instance": 0}),
        )
        assert calls[0][1]["type"] == "climate"


class TestGPS:
    def test_valid_gps_dispatches_tracker(self):
        calls = receive(
            make_handler(),
            msg("CP/GPSDATA", {"lat": 26.15, "lon": -81.79}),
        )
        assert len(calls) == 1
        assert calls[0][1]["type"] == "device_tracker"

    def test_gps_without_coords_is_dropped(self):
        assert receive(make_handler(), msg("CP/GPSDATA", {"fix": "none"})) == []

    def test_gps_with_string_coords_still_works(self):
        calls = receive(
            make_handler(),
            msg("CP/GPSDATA", {"lat": "26.15", "lon": "-81.79"}),
        )
        assert len(calls) == 1
