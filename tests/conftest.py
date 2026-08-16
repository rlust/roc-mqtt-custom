"""Shared Home Assistant test fixtures for the RV-C integration."""

from __future__ import annotations

import asyncio
import sys
import warnings
from pathlib import Path

from homeassistant.components import http as ha_http

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest_plugins = "pytest_homeassistant_custom_component"

# The custom-component fixture still patches this removed HA 2026.8 symbol.
# Restoring a placeholder lets that fixture preserve its no-HTTP-server contract.
if not hasattr(ha_http, "start_http_server_and_save_config"):
    ha_http.start_http_server_and_save_config = None


def pytest_runtest_setup() -> None:
    """Ensure HA's loop policy has a loop before autouse cleanup fixtures run."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
    if loop is None or loop.is_closed():
        asyncio.set_event_loop(asyncio.new_event_loop())
