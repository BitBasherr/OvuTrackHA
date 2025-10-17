from __future__ import annotations

import datetime as dt
from typing import List

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
    CalendarEntityFeature,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityCalendar(hass, entry.entry_id, runtime)])

def _local_tz(hass: HomeAssistant) -> dt.tzinfo:
    return dt_util.get_time_zone(hass.config.time_zone) or dt_util.DEFAULT_TIME_ZONE

class FertilityCalendar(CalendarEntity):
    _attr_has_entity_name = True
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_calendar"
        self._attr_name = f"{runtime.data.name} Calendar"
        self._current_event: CalendarEvent | None = None

    # ---- prevent NotImplementedError on add ----
    @property
    def event(self) -> CalendarEvent | None:
        """Return current/next event (optional for state)."""
        return self._current_event

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime
    ) -> List[CalendarEvent]:
        """Return events within the requested range."""
        tz = _local_tz(hass)
        events: list[CalendarEvent] = []

        # Logged periods
        for c in self._runtime.data.cycles:
            start_dt = dt.datetime.combine(c.start, dt.time.min, tzinfo=tz)
            end_day = c.end or c.start
            end_dt = dt.datetime.combine(end_day, dt.time.max, tzinfo=tz)
            if end_dt < start_date or start_dt > end_date:
                continue
            events.append(
                CalendarEvent(
                    summary="Period",
                    start=start_dt,
                    end=end_dt,
                    description=c.notes or "",
                )
            )

        # Predicted windows (based on today's metrics)
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))

        if metrics.predicted_ovulation_date:
            o = dt.datetime.combine(
                metrics.predicted_ovulation_date, dt.time(12, 0), tzinfo=tz
            )
            if start_date <= o <= end_date:
                events.append(CalendarEvent(summary="Predicted Ovulation", start=o, end=o))

        def _add_range(name: str, d1: dt.date | None, d2: dt.date | None):
            if not d1 or not d2:
                return
            s = dt.datetime.combine(d1, dt.time.min, tzinfo=tz)
            e = dt.datetime.combine(d2, dt.time.max, tzinfo=tz)
            if e < start_date or s > end_date:
                return
            events.append(CalendarEvent(summary=name, start=s, end=e))

        _add_range("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        _add_range("Implantation Window", metrics.implantation_window_start, metrics.implantation_window_end)

        return events

    async def async_create_event(self, **kwargs):
        """Create a simple 'Period' event from the UI to add a period day/range."""
        tz = _local_tz(self.hass)
        summary = kwargs.get("summary", "")
        start = kwargs.get("start")
        end = kwargs.get("end", start)

        # Calendar panel may pass {"date": "YYYY-MM-DD"} dicts
        def _coerce_to_aware_date(d) -> dt.date:
            if isinstance(d, dict) and "date" in d:
                return dt.date.fromisoformat(d["date"])
            if isinstance(d, dt.datetime):
                # ensure local date
                return dt_util.as_local(d).date()
            if isinstance(d, str):
                # best-effort ISO parse
                parsed = dt_util.parse_datetime(d)
                if parsed is not None:
                    return dt_util.as_local(parsed).date()
                return dt.date.fromisoformat(d.split("T")[0])
            if isinstance(d, dt.date):
                return d
            raise ValueError("Unsupported start/end payload")

        sdate = _coerce_to_aware_date(start)
        edate = _coerce_to_aware_date(end)

        if "period" in str(summary).lower():
            self._runtime.data.add_period(start=sdate, end=edate, notes="Added via calendar")
            await self._runtime.async_save()
