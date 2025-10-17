from __future__ import annotations

import datetime as dt
from typing import Iterable, List

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local, coerce_date

# Helper to normalize timezones for calendar events
def _ensure_aware(d: dt.datetime, hass: HomeAssistant) -> dt.datetime:
    """Return timezone-aware datetime in HA's local tz."""
    if dt_util.is_naive(d):
        return dt_util.as_local(d.replace(tzinfo=dt_util.get_time_zone(hass.config.time_zone)))
    # Convert any tz to HA local
    return dt_util.as_local(d)

def _start_of_local_day(day: dt.date, hass: HomeAssistant) -> dt.datetime:
    tz = dt_util.get_time_zone(hass.config.time_zone)
    return dt.datetime.combine(day, dt.time.min, tzinfo=tz)

def _end_exclusive_of_local_day(day: dt.date, hass: HomeAssistant) -> dt.datetime:
    # End is exclusive, so use next midnight
    return _start_of_local_day(day + dt.timedelta(days=1), hass)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityCalendar(hass, entry, runtime)])


class FertilityCalendar(CalendarEntity):
    """Calendar showing logged periods & predicted windows."""

    _attr_has_entity_name = True
    # Keep the entity simple; device name will prefix this automatically
    _attr_name = "Calendar"
    _attr_icon = "mdi:calendar-heart"
    _attr_event: CalendarEvent | None = None  # storage for current/next event

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, runtime) -> None:
        self.hass = hass
        self._entry = entry
        self._runtime = runtime
        self._attr_unique_id = f"{entry.entry_id}_calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._runtime.data.name,  # e.g. "Wife Tracker"
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    # === Required by CalendarEntity ===
    @property
    def event(self) -> CalendarEvent | None:
        """Return a single 'current/next' event for state. It's OK to be None."""
        return self._attr_event

    async def async_update(self) -> None:
        """Optionally set a current/next event for state; safe to leave None."""
        # We'll set the next upcoming event in the next 60 days (if any),
        # but leaving this as None is fine—HA will treat the calendar as 'off'.
        now = today_local(self.hass)
        future = now + dt.timedelta(days=60)
        events = await self.async_get_events(self.hass, now, future)
        self._attr_event = next((e for e in sorted(events, key=lambda e: e.start) if e.start >= now), None)

    # === API used by HA UI to fetch ranges ===
    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> List[CalendarEvent]:
        """Return events between start_date (inclusive) and end_date (exclusive)."""
        # Normalize to local tz & strip weird tzinfo inputs
        tz = dt_util.get_time_zone(hass.config.time_zone)
        if isinstance(start_date.tzinfo, str) or dt_util.is_naive(start_date):
            start_date = start_date.replace(tzinfo=tz)
        if isinstance(end_date.tzinfo, str) or dt_util.is_naive(end_date):
            end_date = end_date.replace(tzinfo=tz)

        events: list[CalendarEvent] = []

        # 1) Logged periods (from data.cycles)
        for c in self._runtime.data.cycles:
            # Start day is known; if end is None, treat as a 1-day placeholder window
            start = _start_of_local_day(c.start, hass)
            if c.end:
                end = _end_exclusive_of_local_day(c.end, hass)
            else:
                end = _end_exclusive_of_local_day(c.start, hass)

            if end <= start_date or start >= end_date:
                continue

            events.append(
                CalendarEvent(
                    summary="Period",
                    start=start,
                    end=end,
                    description=c.notes or "",
                    location=None,
                )
            )

        # 2) Predicted windows, based on current metrics (today-local snapshot)
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(hass))

        def _maybe_add_range(summary: str, start_day: dt.date | None, end_day: dt.date | None) -> None:
            if not start_day or not end_day:
                return
            start_dt = _start_of_local_day(start_day, hass)
            # end_day is inclusive by domain logic; calendar end should be exclusive
            end_dt = _end_exclusive_of_local_day(end_day, hass)
            if end_dt <= start_date or start_dt >= end_date:
                return
            events.append(
                CalendarEvent(
                    summary=summary,
                    start=start_dt,
                    end=end_dt,
                    description="Predicted",
                    location=None,
                )
            )

        _maybe_add_range("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        _maybe_add_range("Implantation Window", metrics.implantation_window_start, metrics.implantation_window_end)

        return events
