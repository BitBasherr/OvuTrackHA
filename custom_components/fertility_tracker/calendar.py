from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEvent,
    CalendarEntityFeature,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityCalendar(hass, entry.entry_id, runtime)])


class FertilityCalendar(CalendarEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_calendar"
        self._attr_name = f"{runtime.data.name} Calendar"
        self._attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_get_events(self, hass, start_date: dt.datetime, end_date: dt.datetime):
        # Build events for periods, predicted ovulation, fertile & implantation windows
        events: list[CalendarEvent] = []

        # Logged periods
        for c in self._runtime.data.cycles:
            s = dt.datetime.combine(c.start, dt.time.min, tzinfo=hass.config.time_zone)
            e = dt.datetime.combine((c.end or c.start), dt.time.max, tzinfo=hass.config.time_zone)
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

        # Predicted windows computed daily, show rough ranges around “today”
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        if metrics.predicted_ovulation_date:
            o = dt.datetime.combine(metrics.predicted_ovulation_date, dt.time(12, 0), tzinfo=hass.config.time_zone)
            events.append(CalendarEvent(summary="Predicted Ovulation", start=o, end=o))

        def _add_range(name: str, d1: dt.date | None, d2: dt.date | None):
            if not d1 or not d2:
                return
            s = dt.datetime.combine(d1, dt.time.min, tzinfo=hass.config.time_zone)
            e = dt.datetime.combine(d2, dt.time.max, tzinfo=hass.config.time_zone)
            if e < start_date or s > end_date:
                return
            events.append(CalendarEvent(summary=name, start=s, end=e))

        _add_range("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        _add_range("Implantation Window", metrics.implantation_window_start, metrics.implantation_window_end)

        return events

    async def async_create_event(self, **kwargs):
        # Coming from calendar UI → add a period day (start=end)
        summary = kwargs.get("summary", "")
        start = kwargs["start"]
        end = kwargs.get("end", start)
        if isinstance(start, dict):  # calendar panel payloads
            start = dt.datetime.fromisoformat(start["date"] + "T00:00:00")
        if isinstance(end, dict):
            end = dt.datetime.fromisoformat(end["date"] + "T00:00:00")
        sdate = start.date()
        edate = end.date()
        # interpret "Period" summary as period entry
        if "period" in summary.lower():
            self._runtime.data.add_period(start=sdate, end=edate, notes="Added via calendar")
            await self._runtime.async_save()
