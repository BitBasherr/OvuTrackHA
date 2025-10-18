from __future__ import annotations

import datetime as dt
from typing import List, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.util import dt as dt_util
from homeassistant.components.calendar import CalendarEntity, CalendarEvent

from .const import DOMAIN
from .helpers import FertilityData, calculate_metrics_for_date

# How far ahead we look when choosing the current/next event for .event
_LOOKAHEAD_DAYS_FOR_EVENT = 60
# Default period length when an open-ended period is encountered
_DEFAULT_PERIOD_LENGTH_DAYS = 5
# Fertile window: 5 days before ovulation + ovulation day (inclusive)
_FERTILE_BEFORE_DAYS = 5
# Implantation window: 6–10 days after ovulation (inclusive)
_IMPLANT_START_OFFSET = 6
_IMPLANT_END_OFFSET = 10


def _as_local_datetime(d: dt.date | dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Return a timezone-aware local datetime for either a date or datetime."""
    if isinstance(d, dt.datetime):
        if d.tzinfo is None:
            return d.replace(tzinfo=tz)
        return d.astimezone(tz)
    # date -> local midnight
    return dt.datetime(d.year, d.month, d.day, tzinfo=tz)


def _end_exclusive(end_like: dt.date | dt.datetime, tz: dt.tzinfo) -> dt.datetime:
    """Return an exclusive end datetime (HA calendar uses exclusive end)."""
    if isinstance(end_like, dt.datetime):
        if end_like.tzinfo is None:
            end_like = end_like.replace(tzinfo=tz)
        else:
            end_like = end_like.astimezone(tz)
        return end_like + dt.timedelta(microseconds=1)
    # For dates, end-exclusive is next day 00:00
    return _as_local_datetime(end_like, tz) + dt.timedelta(days=1)


def _coerce_date_like(x) -> Optional[dt.date]:
    """Coerce helper metrics' date into dt.date (accepts str/date/datetime/None)."""
    if x is None:
        return None
    if isinstance(x, dt.date) and not isinstance(x, dt.datetime):
        return x
    if isinstance(x, dt.datetime):
        return x.date()
    if isinstance(x, str):
        try:
            return dt.date.fromisoformat(x)
        except Exception:
            return None
    return None


class FertilityTrackerCalendar(CalendarEntity):
    """Calendar that exposes period days + predicted fertile/implantation windows."""

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
        """Set .event to the current ongoing or next upcoming event."""
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
        """Return events between start_date (inclusive) and end_date (exclusive)."""
        tz = dt_util.get_time_zone(hass.config.time_zone)

        # Normalize window to local-aware datetimes
        start_date = start_date.astimezone(tz) if start_date.tzinfo else start_date.replace(tzinfo=tz)
        end_date = end_date.astimezone(tz) if end_date.tzinfo else end_date.replace(tzinfo=tz)

        events: List[CalendarEvent] = []

        # ---- Period events from stored cycles ----
        for c in self._data.cycles:
            if not c.start:
                continue
            p_start = _as_local_datetime(c.start, tz)
            if c.end:
                p_end_excl = _end_exclusive(c.end, tz)
            else:
                assumed_end = c.start + dt.timedelta(days=_DEFAULT_PERIOD_LENGTH_DAYS - 1)
                p_end_excl = _end_exclusive(assumed_end, tz)

            if p_start < end_date and p_end_excl > start_date:
                events.append(
                    CalendarEvent(
                        summary="Period",
                        start=p_start,
                        end=p_end_excl,
                        description=(c.notes or ""),
                    )
                )

        # ---- Predicted ranges (Fertile Window + Implantation Window) ----
        # Find predicted ovulation dates that fall around the requested window.
        # We scan the requested range day-by-day and collect distinct predictions.
        ovul_dates: set[dt.date] = set()
        cur = start_date.date()
        end_d = (end_date - dt.timedelta(seconds=1)).date()
        while cur <= end_d:
            # midday local to avoid DST edge cases
            probe_dt = dt.datetime(cur.year, cur.month, cur.day, 12, tzinfo=tz)
            m = calculate_metrics_for_date(self._data, probe_dt)
            ov = _coerce_date_like(getattr(m, "predicted_ovulation_date", None))
            if ov:
                ovul_dates.add(ov)
            cur += dt.timedelta(days=1)

        # For each distinct ovulation date, add the windows if they overlap the query
        for ov in sorted(ovul_dates):
            # Fertile window: [ov - 5, ov] inclusive -> exclusive end ov + 1
            fert_start_d = ov - dt.timedelta(days=_FERTILE_BEFORE_DAYS)
            fert_end_d = ov  # inclusive
            fert_start = _as_local_datetime(fert_start_d, tz)
            fert_end_excl = _end_exclusive(fert_end_d, tz)
            if fert_start < end_date and fert_end_excl > start_date:
                events.append(
                    CalendarEvent(
                        summary="Fertile Window",
                        start=fert_start,
                        end=fert_end_excl,
                        description="Predicted fertile days",
                    )
                )

            # Implantation window: [ov + 6, ov + 10] inclusive
            impl_start_d = ov + dt.timedelta(days=_IMPLANT_START_OFFSET)
            impl_end_d = ov + dt.timedelta(days=_IMPLANT_END_OFFSET)
            impl_start = _as_local_datetime(impl_start_d, tz)
            impl_end_excl = _end_exclusive(impl_end_d, tz)
            if impl_start < end_date and impl_end_excl > start_date:
                events.append(
                    CalendarEvent(
                        summary="Implantation Window",
                        start=impl_start,
                        end=impl_end_excl,
                        description="Predicted implantation likelihood window",
                    )
                )

        # Sort chronologically for stability
        events.sort(key=lambda ev: _as_local_datetime(ev.start, tz))
        return events


# ---------- Platform setup ----------

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    """Set up the calendar entity for an entry."""
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityTrackerCalendar(hass, entry.entry_id, runtime.data)], True)
