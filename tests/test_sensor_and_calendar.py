from __future__ import annotations

import datetime as dt
import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant

from custom_components.fertility_tracker.const import DOMAIN
from custom_components.fertility_tracker.helpers import coerce_date

pytestmark = pytest.mark.asyncio

async def test_sensor_states_and_calendar_events(hass: HomeAssistant, setup_integration, config_entry):
    runtime = hass.data[DOMAIN][config_entry.entry_id]

    # Add historical cycles (two starts define a length; third defines "current")
    runtime.data.add_period(start=coerce_date("2025-07-01"), end=coerce_date("2025-07-05"), notes=None)
    runtime.data.add_period(start=coerce_date("2025-08-01"), end=coerce_date("2025-08-05"), notes=None)
    runtime.data.add_period(start=coerce_date("2025-09-02"), end=coerce_date("2025-09-06"), notes=None)
    await runtime.async_save()

    # Freeze to a deterministic date
    with freeze_time("2025-09-10 12:00:00"):
        await hass.helpers.entity_component.async_update_entity(f"sensor.wife_tracker_fertility_risk")
        state = hass.states.get("sensor.wife_tracker_fertility_risk")
        assert state is not None
        assert state.state in ("low", "medium", "high")
        attrs = state.attributes
        assert "predicted_ovulation_date" in attrs
        # dates may vary depending on averages; just assert presence and type
        assert attrs.get("cycle_length_avg") is not None

        # Calendar should provide events
        calendar = hass.data["entity_components"]["calendar"].entities
        # There will be exactly one calendar entity for this entry
        cal_entity = next(iter(calendar))
        events = await cal_entity.async_get_events(
            hass,
            dt.datetime(2025, 9, 1, tzinfo=hass.config.time_zone),
            dt.datetime(2025, 10, 1, tzinfo=hass.config.time_zone),
        )
        # Should include logged Period events and predicted ranges
        summaries = [e.summary for e in events]
        assert any(s == "Period" for s in summaries)
        assert "Fertile Window" in summaries or "Implantation Window" in summaries
