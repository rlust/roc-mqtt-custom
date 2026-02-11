"""Helpers for entity availability tracking."""
from __future__ import annotations

from datetime import timedelta
import time

from homeassistant.core import CALLBACK_TYPE, callback
from homeassistant.helpers.event import async_track_time_interval


class AvailabilityMixin:
    """Mixin that marks entities unavailable when data stops updating."""

    def __init__(self, availability_timeout: int) -> None:
        self._availability_timeout = max(0, int(availability_timeout))
        self._last_update_time: float | None = None
        self._awaiting_first_update = True
        self._availability_unsub: CALLBACK_TYPE | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._availability_timeout <= 0:
            return
        interval = min(self._availability_timeout, 300)
        self._availability_unsub = async_track_time_interval(
            self.hass,
            self._handle_availability_tick,
            timedelta(seconds=interval),
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._availability_unsub:
            self._availability_unsub()
            self._availability_unsub = None
        await super().async_will_remove_from_hass()

    def mark_seen_now(self) -> None:
        """Record that fresh data has been received."""
        self._last_update_time = time.time()
        if self._awaiting_first_update:
            self._awaiting_first_update = False

    @callback
    def _handle_availability_tick(self, _) -> None:
        """Periodic callback to force HA to re-evaluate availability."""
        self.async_write_ha_state()

    def _is_within_timeout(self) -> bool:
        if self._availability_timeout <= 0:
            return True
        if self._awaiting_first_update:
            return True
        if self._last_update_time is None:
            return False
        return (time.time() - self._last_update_time) <= self._availability_timeout

    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._is_within_timeout()
