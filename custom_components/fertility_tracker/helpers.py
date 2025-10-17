from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any, Dict

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    RISK_LOW,
    RISK_MEDIUM,
    RISK_HIGH,
)

# ---------------- Utilities ----------------

def _get_local_tz(hass: HomeAssistant) -> dt.tzinfo:
    """Return Home Assistant's configured tzinfo."""
    return dt_util.get_time_zone(hass.config.time_zone)

def today_local(hass: HomeAssistant) -> dt.datetime:
    """Return timezone-aware 'now' in Home Assistant's configured timezone."""
    tz = _get_local_tz(hass)
    return dt_util.now(tz)

def parse_time(s: str | None) -> dt.time | None:
    if not s:
        return None
    try:
        h, m, sec = s.split(":")
        return dt.time(int(h), int(m), int(sec))
    except Exception:  # noqa: BLE001
        return None

def coerce_date(s: str | dt.date | dt.datetime) -> dt.date:
    if isinstance(s, dt.datetime):
        return s.date()
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(str(s))

# ---------------- Data Models ----------------

@dataclass
class CycleEvent:
    id: str
    start: dt.date
    end: dt.date | None = None
    notes: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "CycleEvent":
        return CycleEvent(
            id=d["id"],
            start=coerce_date(d["start"]),
            end=coerce_date(d["end"]) if d.get("end") else None,
            notes=d.get("notes"),
        )


@dataclass
class SexEvent:
    ts: dt.datetime
    protected: bool
    notes: str | None = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ts": self.ts.isoformat(),
            "protected": self.protected,
            "notes": self.notes,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "SexEvent":
        return SexEvent(
            ts=dt.datetime.fromisoformat(d["ts"]),
            protected=bool(d["protected"]),
            notes=d.get("notes"),
        )


@dataclass
class PregnancyTestEvent:
    ts: dt.datetime
    result: str

    def as_dict(self) -> Dict[str, Any]:
        return {"ts": self.ts.isoformat(), "result": self.result}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PregnancyTestEvent":
        return PregnancyTestEvent(ts=dt.datetime.fromisoformat(d["ts"]), result=d["result"])


@dataclass
class FertilityData:
    name: str
    luteal_days: int
    recent_weight: float
    long_weight: float
    recent_window: int
    notify_services: list[str]
    trigger_entities: list[str]
    quiet_hours_start: str
    quiet_hours_end: str
    daily_reminder_time: str

    cycles: list[CycleEvent] = field(default_factory=list)
    sex_events: list[SexEvent] = field(default_factory=list)
    pregnancy_tests: list[PregnancyTestEvent] = field(default_factory=list)

    last_notified_date: str | None = None  # ISO date string

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "luteal_days": self.luteal_days,
            "recent_weight": self.recent_weight,
            "long_weight": self.long_weight,
            "recent_window": self.recent_window,
            "notify_services": self.notify_services,
            "trigger_entities": self.trigger_entities,
            "quiet_hours_start": self.quiet_hours_start,
            "quiet_hours_end": self.quiet_hours_end,
            "daily_reminder_time": self.daily_reminder_time,
            "cycles": [c.as_dict() for c in self.cycles],
            "sex_events": [s.as_dict() for s in self.sex_events],
            "pregnancy_tests": [p.as_dict() for p in self.pregnancy_tests],
            "last_notified_date": self.last_notified_date,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "FertilityData":
        fd = FertilityData(
            name=d["name"],
            luteal_days=int(d.get("luteal_days", 14)),
            recent_weight=float(d.get("recent_weight", 0.7)),
            long_weight=float(d.get("long_weight", 0.3)),
            recent_window=int(d.get("recent_window", 3)),
            notify_services=list(d.get("notify_services", [])),
            trigger_entities=list(d.get("trigger_entities", [])),
            quiet_hours_start=d.get("quiet_hours_start", "22:00:00"),
            quiet_hours_end=d.get("quiet_hours_end", "07:00:00"),
            daily_reminder_time=d.get("daily_reminder_time", "09:00:00"),
        )
        fd.cycles = [CycleEvent.from_dict(x) for x in d.get("cycles", [])]
        # ✅ Fix bug: don't reference fd.sex_events in its own construction
        fd.sex_events = [SexEvent.from_dict(x) for x in d.get("sex_events", [])]
        fd.pregnancy_tests = [PregnancyTestEvent.from_dict(x) for x in d.get("pregnancy_tests", [])]
        fd.last_notified_date = d.get("last_notified_date")
        return fd

    # ---- Mutators used by WS/services ----
    def add_period(self, start: dt.date, end: dt.date | None, notes: str | None) -> None:
        self.cycles.append(CycleEvent(id=str(uuid.uuid4()), start=start, end=end, notes=notes))
        self.cycles.sort(key=lambda c: c.start)

    def edit_cycle(self, cycle_id: str, start: dt.date | None, end: dt.date | None, notes: str | None) -> bool:
        for c in self.cycles:
            if c.id == cycle_id:
                if start:
                    c.start = start
                if end is not None:
                    c.end = end
                if notes is not None:
                    c.notes = notes
                self.cycles.sort(key=lambda c: c.start)
                return True
        return False

    def delete_cycle(self, cycle_id: str) -> bool:
        for i, c in enumerate(self.cycles):
            if c.id == cycle_id:
                del self.cycles[i]
                return True
        return False


@dataclass
class Metrics:
    date: dt.date
    cycle_day: int | None
    cycle_length_avg: float | None
    cycle_length_std: float | None
    next_period_date: dt.date | None
    predicted_ovulation_date: dt.date | None
    fertile_window_start: dt.date | None
    fertile_window_end: dt.date | None
    implantation_window_start: dt.date | None
    implantation_window_end: dt.date | None
    # New: simple machine-readable level + human label
    risk_level: str | None
    risk_label: str | None


def _completed_cycle_lengths(cycles: list[CycleEvent]) -> list[int]:
    lens = []
    for i in range(1, len(cycles)):
        prev = cycles[i - 1]
        cur = cycles[i]
        lens.append((cur.start - prev.start).days)  # difference between consecutive period starts
    return lens


def _weighted_avg_length(lengths: list[int], recent_window: int, w_recent: float, w_long: float) -> float | None:
    if not lengths:
        return None
    if len(lengths) <= recent_window:
        return mean(lengths)
    recent = lengths[-recent_window:]
    long = lengths
    return w_recent * mean(recent) + w_long * mean(long)


def _std(lengths: list[int]) -> float | None:
    if len(lengths) < 2:
        return None
    try:
        return pstdev(lengths)
    except Exception:  # noqa: BLE001
        return None


def calculate_metrics_for_date(data: FertilityData, when: dt.datetime) -> Metrics:
    d = when.date()
    cycles = sorted(data.cycles, key=lambda c: c.start)
    lengths = _completed_cycle_lengths(cycles)
    avg_len = _weighted_avg_length(lengths, data.recent_window, data.recent_weight, data.long_weight)
    std_len = _std(lengths)

    last_start = cycles[-1].start if cycles else None

    cycle_day = None
    if last_start:
        cycle_day = (d - last_start).days + 1 if d >= last_start else None

    next_period = None
    if last_start and avg_len:
        next_period = last_start + dt.timedelta(days=int(round(avg_len)))

    pred_ovulation = None
    if next_period:
        pred_ovulation = next_period - dt.timedelta(days=int(data.luteal_days))

    fertile_start = fertile_end = None
    if pred_ovulation:
        fertile_start = pred_ovulation - dt.timedelta(days=5)
        fertile_end = pred_ovulation + dt.timedelta(days=1)

    implant_start = implant_end = None
    if pred_ovulation:
        implant_start = pred_ovulation + dt.timedelta(days=6)
        implant_end = pred_ovulation + dt.timedelta(days=10)

    # Risk labeling
    risk_level: str | None = None
    risk_label: str | None = None

    if fertile_start and fertile_end:
        if fertile_start <= d <= fertile_end:
            risk_level = RISK_HIGH
            risk_label = "High pregnancy risk today (fertile window)."
        elif (fertile_start - dt.timedelta(days=2)) <= d <= (fertile_end + dt.timedelta(days=2)):
            risk_level = RISK_MEDIUM
            risk_label = "Medium pregnancy risk today (near fertile window)."
        else:
            risk_level = RISK_LOW
            risk_label = "Safe to have unprotected sex today (low pregnancy risk)."

    # Implantation emphasis overrides label (keep level high)
    if implant_start and implant_end and implant_start <= d <= implant_end:
        risk_level = RISK_HIGH
        risk_label = "High implantation risk today (post-ovulation)."

    return Metrics(
        date=d,
        cycle_day=cycle_day,
        cycle_length_avg=avg_len,
        cycle_length_std=std_len,
        next_period_date=next_period,
        predicted_ovulation_date=pred_ovulation,
        fertile_window_start=fertile_start,
        fertile_window_end=fertile_end,
        implantation_window_start=implant_start,
        implantation_window_end=implant_end,
        risk_level=risk_level,
        risk_label=risk_label,
    )
