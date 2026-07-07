"""Tests for custom_components.rvc.helpers."""
from types import SimpleNamespace

from custom_components.rvc.helpers import coerce_int, get_entry_option


def _entry(options=None, data=None):
    return SimpleNamespace(options=options or {}, data=data or {})


class TestGetEntryOption:
    def test_option_wins_over_data(self):
        entry = _entry(options={"k": "opt"}, data={"k": "dat"})
        assert get_entry_option(entry, "k", "def") == "opt"

    def test_falls_back_to_data(self):
        entry = _entry(data={"k": "dat"})
        assert get_entry_option(entry, "k", "def") == "dat"

    def test_falls_back_to_default(self):
        assert get_entry_option(_entry(), "k", "def") == "def"


class TestCoerceInt:
    def test_int_passthrough(self):
        assert coerce_int(30, 5) == 30

    def test_string_number(self):
        assert coerce_int("30", 5) == 30

    def test_negative_clamped_to_zero(self):
        assert coerce_int(-4, 5) == 0

    def test_none_uses_fallback(self):
        assert coerce_int(None, 5) == 5

    def test_garbage_uses_fallback(self):
        assert coerce_int("abc", 5) == 5
