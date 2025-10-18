from __future__ import annotations

import datetime as dt
from typing import List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
)

from .const import DOMAIN
from .helpers import FertilityData

# How many days ahead to search when picking the "current/next" event for .event
_LOOKAHEAD_DAYS_FOR_EVENT = 60
# Default period length (only used if a cycle is open-ended)
_DEFAULT_PERIOD_LENGTH_DAYS = 5


def _as_local_datetime(d: dt.date | dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Return a timezone-aware local datetime for either a date or datetime."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            return d.replace(tzinfo=tz)
        return d.astimezone(tz)
    # date → local midnight
    return dt.datetime(d.year, d.month, d.day, tzinfo=tz)


def _end_exclusive(end_like: dt.date | dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Return an exclusive end datetime (HA calendar treats end as exclusive)."""
    if isinstance(end_like, dt.datetime):
        if end_like.tzinfo is None:
            end_like = end_like.replace(tzinfo=tz)
        else:
            end_like = end_like.astimezone(tz)
        # push a microsecond to make it exclusive
        return end_like + dt.timedelta(microseconds=1)
    # For dates, end-exclusive is next day 00:00
    return _as_local_datetime(end_like, tz) + dt.timedelta(days=1)


class FertilityTrackerCalendar(CalendarEntity):
    """Calendar that exposes period days (and can be extended later)."""

    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, data: FertilityData) -> None:
        self.hass = hass
        self._entry_id = entry_id
        self._data = data
        self._attr_unique_id = f"{entry_id}_calendar"
        self._attr_name = f"{data.name} Calendar"
        self._event: Optional[CalendarEvent] = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=data.name,
            manufacturer="Fertility Tracker",
            model="Cycle calendar",
        )

    # ---------- Core Calendar API ----------

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next event for HA to show as entity state."""
        return self._event

    async def async_update(self) -> None:
        """Set .event to the current ongoing or next upcoming event.

        HA calls this to decide if the entity is 'on' and what to show.
        """
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        now = dt_util.now(tz)
        # Look back a little to catch events that started just before now.
        start = now - dt.timedelta(days=1)
        end = now + dt.timedelta(days=_LOOKAHEAD_DAYS_FOR_EVENT)
        events = await self.async_get_events(self.hass, start, end)

        current: Optional[CalendarEvent] = None
        upcoming: Optional[CalendarEvent] = None
        for ev in events:
            ev_start = _as_local_datetime(ev.start, tz)
            ev_end = _as_local_datetime(ev.end, tz)
            # CalendarEvent should be end-exclusive; be defensive:
            if ev_end <= ev_start:
                ev_end = ev_start + dt.timedelta(minutes=1)

            if ev_start <= now < ev_end and current is None:
                current = ev
            if ev_start >= now and upcoming is None:
                upcoming = ev

            if current and upcoming:
                break

        self._event = current or upcoming

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ) -> List[CalendarEvent]:
        """Return events between start_date (inclusive) and end_date (exclusive).

        Currently exposes period days based on stored cycles. You can enrich this
        later with predicted ovulation/fertility windows, tests, etc.
        """
        tz = dt_util.get_time_zone(hass.config.time_zone)

        # Normalize window to local-aware datetimes
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=tz)
        else:
            start_date = start_date.astimezone(tz)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=tz)
        else:
            end_date = end_date.astimezone(tz)

        events: List[CalendarEvent] = []

        # Build period events from cycles
        for c in self._data.cycles:
            if not c.start:
                continue

            # Start datetime (inclusive)
            p_start = _as_local_datetime(c.start, tz)

            # If the cycle has an explicit end, use it; otherwise default length
            if c.end:
                p_end_exclusive = _end_exclusive(c.end, tz)
            else:
                # open-ended cycle → assume default period length
                assumed_end = c.start + dt.timedelta(days=_DEFAULT_PERIOD_LENGTH_DAYS - 1)
                p_end_exclusive = _end_exclusive(assumed_end, tz)

            # Window overlap test (event intersects the query range)
            if p_start < end_date and p_end_exclusive > start_date:
                events.append(
                    CalendarEvent(
                        summary="Period",
                        start=p_start,
                        end=p_end_exclusive,
                        description=(c.notes or ""),
                    )
                )

        # (Optional) Here is where you could add ovulation/implantation windows,
        # using your existing helpers.calculate_metrics_for_date across a range.

        # Sort chronologically
        events.sort(key=lambda ev: _as_local_datetime(ev.start, tz))
        return events


# ---------- Platform setup ----------

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the calendar entity for an entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityTrackerCalendar(hass, entry.entry_id, runtime.data)], True)
