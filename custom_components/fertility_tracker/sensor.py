from __future__ import annotations

from typing import Any, Dict, Optional
import datetime as dt

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DOMAIN,
    ATTR_CYCLE_DAY,
    ATTR_CYCLE_LEN_AVG,
    ATTR_CYCLE_LEN_STD,
    ATTR_NEXT_PERIOD,
    ATTR_PRED_OVULATION,
    ATTR_FERTILE_START,
    ATTR_FERTILE_END,
    ATTR_IMPLANT_START,
    ATTR_IMPLANT_END,
    ATTR_RISK_LABEL,
)
from .helpers import calculate_metrics_for_date, today_local


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FertilityRiskSensor(hass, entry.entry_id, runtime)], True)


class FertilityRiskSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_risk"
        self._attr_name = f"{runtime.data.name} Fertility Risk"
        self._state: str | None = None
        self._attrs: Dict[str, Any] = {}

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
    def native_value(self) -> str | None:
        return self._state

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        return self._attrs

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        # Normalize risk to low/medium/high
        label = metrics.risk_label or ""
        if "High implantation" in label or "High pregnancy" in label:
            self._state = "high"
        elif "Medium" in label:
            self._state = "medium"
        else:
            self._state = "low"
        self._attrs = {
            ATTR_RISK_LABEL: metrics.risk_label,
            ATTR_CYCLE_DAY: metrics.cycle_day,
            ATTR_CYCLE_LEN_AVG: metrics.cycle_length_avg,
            ATTR_CYCLE_LEN_STD: metrics.cycle_length_std,
            ATTR_NEXT_PERIOD: metrics.next_period_date,
            ATTR_PRED_OVULATION: metrics.predicted_ovulation_date,
            ATTR_FERTILE_START: metrics.fertile_window_start,
            ATTR_FERTILE_END: metrics.fertile_window_end,
            ATTR_IMPLANT_START: metrics.implantation_window_start,
            ATTR_IMPLANT_END: metrics.implantation_window_end,
        }
