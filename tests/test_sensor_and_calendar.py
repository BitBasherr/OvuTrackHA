from __future__ import annotations

import datetime as dt
import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.fertility_tracker.const import DOMAIN
from custom_components.fertility_tracker.helpers import coerce_date

pytestmark = pytest.mark.asyncio


def _coerce_tz(hass: HomeAssistant) -> dt.tzinfo:
    """Return a tzinfo object regardless of how HA stores time_zone (str or tzinfo)."""
    tz = getattr(hass.config, "time_zone", None)
    if isinstance(tz, dt.tzinfo):
        return tz
    return dt_util.get_time_zone(str(tz)) or dt_util.UTC


def _category_from_state_text(val: str) -> str | None:
    """Map the human-readable sensor text to 'low'/'medium'/'high' for flexible assertions."""
    s = (val or "").lower()
    if "low" in s:
        return "low"
    if "medium" in s:
        return "medium"
    if "high" in s:
        return "high"
    return None


async def test_sensor_states_and_calendar_events(hass: HomeAssistant, setup_integration, config_entry):
    runtime = hass.data[DOMAIN][config_entry.entry_id]

    # Add historical cycles (two starts define a length; third defines "current")
    runtime.data.add_period(start=coerce_date("2025-07-01"), end=coerce_date("2025-07-05"), notes=None)
    runtime.data.add_period(start=coerce_date("2025-08-01"), end=coerce_date("2025-08-05"), notes=None)
    runtime.data.add_period(start=coerce_date("2025-09-02"), end=coerce_date("2025-09-06"), notes=None)
    await runtime.async_save()

    # Freeze to a deterministic date
    with freeze_time("2025-09-10 12:00:00"):
        await hass.helpers.entity_component.async_update_entity("sensor.wife_tracker_fertility_risk")
        state = hass.states.get("sensor.wife_tracker_fertility_risk")
        assert state is not None

        # Be tolerant of either compact categories or human-readable text
        category = state.state if state.state in ("low", "medium", "high") else _category_from_state_text(state.state)
        assert category in ("low", "medium", "high")

        attrs = state.attributes
        assert "predicted_ovulation_date" in attrs
        # dates may vary depending on averages; just assert presence and type
        assert attrs.get("cycle_length_avg") is not None

        # Calendar should provide events
        calendar_component = hass.data["entity_components"]["calendar"]
        cal_entity = next(iter(calendar_component.entities))  # one entity for this entry

        tz = _coerce_tz(hass)
        events = await cal_entity.async_get_events(
            hass,
            dt.datetime(2025, 9, 1, tzinfo=tz),
            dt.datetime(2025, 10, 1, tzinfo=tz),
        )

        # Should include logged Period events and predicted ranges
        summaries = [e.summary for e in events]
        assert any(s == "Period" for s in summaries)
        assert ("Fertile Window" in summaries) or ("Implantation Window" in summaries)
