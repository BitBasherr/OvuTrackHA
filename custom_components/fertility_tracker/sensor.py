from __future__ import annotations

import datetime as dt
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityRiskSensor(hass, entry.entry_id, runtime)])


class FertilityRiskSensor(SensorEntity):
    """Compact fertility risk sensor with verbose text attribute."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:heart-pulse"
    _attr_native_value: str | None = None

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_name = "Fertility Risk"
        self._attr_unique_id = f"{entry_id}_fertility_risk"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,  # e.g. "Wife Tracker"
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _classify_level_from_windows(self, metrics) -> str:
        """Return 'low' | 'medium' | 'high' based on date windows."""
        today = today_local(self.hass).date()

        # High if within implantation window
        if metrics.implantation_window_start and metrics.implantation_window_end:
            if metrics.implantation_window_start <= today <= metrics.implantation_window_end:
                return "high"

        # High if within fertile window
        if metrics.fertile_window_start and metrics.fertile_window_end:
            if metrics.fertile_window_start <= today <= metrics.fertile_window_end:
                return "high"
            # Medium if within ±2 days of fertile window
            before = metrics.fertile_window_start - dt.timedelta(days=2)
            after = metrics.fertile_window_end + dt.timedelta(days=2)
            if before <= today <= after:
                return "medium"

        # Default fallback
        return "low"

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))

        # Compact state
        level = self._classify_level_from_windows(metrics)
        self._attr_native_value = level

        # Long, user-friendly text (keep your existing phrasing if available)
        risk_text = metrics.risk_label
        if not risk_text:
            risk_text = {
                "high": "High pregnancy risk today (fertile/implantation window).",
                "medium": "Medium pregnancy risk today (near fertile window).",
                "low": "Safe to have unprotected sex today (low pregnancy risk).",
            }[level]

        # Extra attributes for UI/debugging
        self._attr_extra_state_attributes = {
            "risk_text": risk_text,
            "cycle_day": metrics.cycle_day,
            "cycle_length_avg": metrics.cycle_length_avg,
            "cycle_length_std": metrics.cycle_length_std,
            "next_period_date": metrics.next_period_date.isoformat() if metrics.next_period_date else None,
            "predicted_ovulation_date": metrics.predicted_ovulation_date.isoformat() if metrics.predicted_ovulation_date else None,
            "fertile_window_start": metrics.fertile_window_start.isoformat() if metrics.fertile_window_start else None,
            "fertile_window_end": metrics.fertile_window_end.isoformat() if metrics.fertile_window_end else None,
            "implantation_window_start": metrics.implantation_window_start.isoformat() if metrics.implantation_window_start else None,
            "implantation_window_end": metrics.implantation_window_end.isoformat() if metrics.implantation_window_end else None,
        }
