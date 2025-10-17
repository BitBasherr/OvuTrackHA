from __future__ import annotations

import datetime as dt

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
    CalendarEntityFeature,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local, _get_local_tz


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityCalendar(hass, entry.entry_id, runtime)])


class FertilityCalendar(CalendarEntity):
    """Calendar that exposes logged periods and predicted windows."""

    _attr_has_entity_name = True
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_calendar"
        # Entity name (device name is added automatically when has_entity_name=True)
        self._attr_name = f"{runtime.data.name} Calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    # --- Important: HA calls self.event when computing state; return None to avoid NotImplementedError
    @property
    def event(self) -> CalendarEvent | None:  # type: ignore[override]
        return None

    # --- Also safe: override state so HA won't try to infer it from self.event
    @property
    def state(self) -> str | None:
        # We don't maintain a "next/upcoming" event; advertise as "off".
        return "off"

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: dt.datetime,
        end_date: dt.datetime,
    ):
        tz = _get_local_tz(hass)
        events: list[CalendarEvent] = []

        # Logged period ranges
        for c in self._runtime.data.cycles:
            s = dt.datetime.combine(c.start, dt.time.min, tzinfo=tz)
            e = dt.datetime.combine((c.end or c.start), dt.time.max, tzinfo=tz)
            if e < start_date or s > end_date:
                continue
            events.append(
                CalendarEvent(
                    summary="Period",
                    start=s,
                    end=e,
                    description=c.notes or "",
                )
            )

        # Predicted windows (based on current metrics)
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))

        def _add_range(name: str, d1: dt.date | None, d2: dt.date | None):
            if not d1 or not d2:
                return
            s = dt.datetime.combine(d1, dt.time.min, tzinfo=tz)
            e = dt.datetime.combine(d2, dt.time.max, tzinfo=tz)
            if e < start_date or s > end_date:
                return
            events.append(CalendarEvent(summary=name, start=s, end=e))

        _add_range("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        _add_range(
            "Implantation Window",
            metrics.implantation_window_start,
            metrics.implantation_window_end,
        )

        # Optional: show ovulation as a one-day point event
        if metrics.predicted_ovulation_date:
            o = dt.datetime.combine(metrics.predicted_ovulation_date, dt.time(12, 0), tzinfo=tz)
            events.append(CalendarEvent(summary="Predicted Ovulation", start=o, end=o))

        return events

    async def async_create_event(self, **kwargs):
        """Support adding a 'Period' day via the calendar UI (optional nicety)."""
        summary = kwargs.get("summary", "") or ""
        start = kwargs.get("start")
        end = kwargs.get("end", start)

        # Handle calendar panel payloads: {"date": "YYYY-MM-DD"} etc.
        if isinstance(start, dict) and "date" in start:
            start = dt.datetime.fromisoformat(start["date"] + "T00:00:00")
        if isinstance(end, dict) and "date" in end:
            end = dt.datetime.fromisoformat(end["date"] + "T00:00:00")

        if isinstance(start, dt.datetime) and isinstance(end, dt.datetime):
            sdate = start.date()
            edate = end.date()
            if "period" in summary.lower():
                self._runtime.data.add_period(start=sdate, end=edate, notes="Added via calendar")
                await self._runtime.async_save()
