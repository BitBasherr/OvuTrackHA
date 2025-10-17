from __future__ import annotations

import datetime as dt

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
    _attr_supported_features = CalendarEntityFeature.CREATE_EVENT

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_calendar"
        # Only the entity part here; device name will prefix (e.g. "Wife Tracker Calendar")
        self._attr_name = "Calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def event(self):
        # Optional: current/next event for state calculation.
        # We return None; state will be "off" in most calendar cards.
        return None

    async def async_get_events(self, hass: HomeAssistant, start_date: dt.datetime, end_date: dt.datetime):
        """Return events in range."""
        events: list[CalendarEvent] = []

        # Logged periods
        tz = hass.config.time_zone
        for c in self._runtime.data.cycles:
            s = dt.datetime.combine(c.start, dt.time.min).replace(tzinfo=dt.timezone.utc).astimezone()
            e_base = c.end or c.start
            e = dt.datetime.combine(e_base, dt.time.max).replace(tzinfo=dt.timezone.utc).astimezone()
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

        # Predicted windows around "today"
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))

        def _localize_date(d: dt.date, at_hour: int = 12) -> dt.datetime:
            return dt.datetime.combine(d, dt.time(at_hour, 0)).astimezone()

        if metrics.predicted_ovulation_date:
            o = _localize_date(metrics.predicted_ovulation_date)
            if start_date <= o <= end_date:
                events.append(CalendarEvent(summary="Predicted Ovulation", start=o, end=o))

        def _add_range(name: str, d1: dt.date | None, d2: dt.date | None):
            if not d1 or not d2:
                return
            s = _localize_date(d1, 0)
            e = _localize_date(d2, 23)
            if e < start_date or s > end_date:
                return
            events.append(CalendarEvent(summary=name, start=s, end=e))

        _add_range("Fertile Window", metrics.fertile_window_start, metrics.fertile_window_end)
        _add_range("Implantation Window", metrics.implantation_window_start, metrics.implantation_window_end)

        return events

    async def async_create_event(self, **kwargs):
        """Support quick-add via calendar panel: 'Period' all-day adds that day as a period."""
        summary = kwargs.get("summary", "")
        start = kwargs["start"]
        end = kwargs.get("end", start)
        if isinstance(start, dict):  # calendar panel payloads
            start = dt.datetime.fromisoformat(start["date"] + "T00:00:00")
        if isinstance(end, dict):
            end = dt.datetime.fromisoformat(end["date"] + "T00:00:00")
        sdate = start.date()
        edate = end.date()
        if "period" in summary.lower():
            self._runtime.data.add_period(start=sdate, end=edate, notes="Added via calendar")
            await self._runtime.async_save()
