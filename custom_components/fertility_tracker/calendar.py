from __future__ import annotations

import datetime as dt
from typing import List

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local, FertilityData


# ---------------- Time helpers ----------------


def _local_tz(hass: HomeAssistant) -> dt.tzinfo:
    """Return Home Assistant's configured timezone object."""
    return dt_util.get_time_zone(hass.config.time_zone)


def _is_naive(d: dt.datetime) -> bool:
    """Return True if datetime is naive (no tzinfo)."""
    return d.tzinfo is None or d.tzinfo.utcoffset(d) is None


def _as_local(hass: HomeAssistant, value: dt.date | dt.datetime) -> dt.datetime:
    """Coerce a date/datetime to a timezone-aware local datetime.

    - date -> local midnight
    - naive datetime -> assume local tz
    - aware datetime -> convert to local tz
    """
    tz = _local_tz(hass)

    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return dt.datetime(value.year, value.month, value.day, tzinfo=tz)

    assert isinstance(value, dt.datetime)
    if _is_naive(value):
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _overlaps(a_start: dt.datetime, a_end: dt.datetime, b_start: dt.datetime, b_end: dt.datetime) -> bool:
    """Return True if [a_start, a_end) overlaps [b_start, b_end)."""
    return a_start < b_end and a_end > b_start


def _clamp_to_range(start: dt.datetime, end: dt.datetime, r_start: dt.datetime, r_end: dt.datetime) -> tuple[dt.datetime, dt.datetime] | None:
    """Clamp an interval to a range, return None if no overlap."""
    if not _overlaps(start, end, r_start, r_end):
        return None
    return max(start, r_start), min(end, r_end)


# ---------------- Platform setup ----------------


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityCalendarEntity(hass, runtime, entry.entry_id, runtime.data.name)])


# ---------------- Entity ----------------


class FertilityCalendarEntity(CalendarEntity):
    """Calendar exposing period history + predicted fertile/implantation windows."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, runtime, entry_id: str, name: str) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._name = f"{name} Calendar"
        self._unique_id = f"{entry_id}_calendar"
        # Keep event state simple; we return None and only serve ranges via async_get_events
        self._event: CalendarEvent | None = None

        # Device metadata (keeps calendar grouped with the rest of the integration)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Fertility Tracker",
            name=name,
        )

    # ---- CalendarEntity required bits

    @property
    def name(self) -> str | None:  # entity display name
        return self._name

    @property
    def unique_id(self) -> str | None:
        return self._unique_id

    @property
    def event(self) -> CalendarEvent | None:
        # We do not persist a "next event" for the on/off state; leaving None is fine.
        # (HA will show "off" state; tests only use async_get_events)
        return self._event

    # ---- Event production

    def _build_static_events(self, data: FertilityData, range_start: dt.datetime, range_end: dt.datetime) -> list[CalendarEvent]:
        """Convert stored cycle history into all-day 'Period' events."""
        tz = _local_tz(self.hass)
        events: list[CalendarEvent] = []
        for c in data.cycles:
            start = _as_local(self.hass, c.start)  # local midnight
            # Periods are all-day; end is exclusive (next day after the last logged date).
            period_end_date = c.end if c.end else c.start  # if end missing, treat as 1-day
            end = _as_local(self.hass, period_end_date) + dt.timedelta(days=1)

            clamped = _clamp_to_range(start, end, range_start, range_end)
            if not clamped:
                continue
            s, e = clamped
            events.append(CalendarEvent(summary="Period", start=s.astimezone(tz), end=e.astimezone(tz)))
        return events

    def _build_predicted_events(self, data: FertilityData, range_start: dt.datetime, range_end: dt.datetime) -> list[CalendarEvent]:
        """Add predicted fertile and implantation windows (all-day ranges)."""
        tz = _local_tz(self.hass)
        events: list[CalendarEvent] = []

        # Use "today" to compute next ovulation / windows (freezegun in tests fixes this)
        metrics = calculate_metrics_for_date(data, today_local(self.hass))

        # Helper to push an all-day range if present
        def push(summary: str, start_d: dt.date | None, end_d: dt.date | None):
            if not start_d or not end_d:
                return
            start = _as_local(self.hass, start_d)
            end = _as_local(self.hass, end_d)  # end is inclusive date -> +1 day below
            # Make event exclusive at end of range
            end = end + dt.timedelta(days=1)
            clamped = _clamp_to_range(start, end, range_start, range_end)
            if not clamped:
                return
            s, e = clamped
            events.append(CalendarEvent(summary=summary, start=s.astimezone(tz), end=e.astimezone(tz)))

        push("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        push("Implantation Window", metrics.implantation_window_start, metrics.implantation_window_end)

        return events

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> List[CalendarEvent]:
        """Return events between start_date (inclusive) and end_date (exclusive)."""
        # Normalize boundaries to local tz
        start_local = _as_local(hass, start_date)
        end_local = _as_local(hass, end_date)

        data: FertilityData = self._runtime.data

        events: list[CalendarEvent] = []
        events.extend(self._build_static_events(data, start_local, end_local))
        events.extend(self._build_predicted_events(data, start_local, end_local))

        # Sort deterministically by start
        events.sort(key=lambda e: (e.start, e.end, e.summary))
        return events
