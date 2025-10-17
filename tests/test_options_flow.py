from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant import config_entries

from custom_components.fertility_tracker.const import (
    DOMAIN,
    CONF_LUTEAL_DAYS,
    CONF_RECENT_WEIGHT,
    CONF_LONG_WEIGHT,
    CONF_RECENT_WINDOW,
    CONF_NOTIFY_SERVICES,
    CONF_TRIGGER_ENTITIES,
    CONF_DAILY_REMINDER_TIME,
    CONF_QUIET_HOURS_START,
    CONF_QUIET_HOURS_END,
)

pytestmark = pytest.mark.asyncio

async def test_options_flow_sets_values(hass: HomeAssistant, setup_integration, config_entry):
    # Open options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == "form"

    # No notify services may exist in vanilla test env; pass empty list
    user_input = {
        CONF_LUTEAL_DAYS: 14,
        CONF_RECENT_WEIGHT: 0.6,
        CONF_LONG_WEIGHT: 0.4,
        CONF_RECENT_WINDOW: 4,
        CONF_DAILY_REMINDER_TIME: "08:30:00",
        CONF_QUIET_HOURS_START: "22:00:00",
        CONF_QUIET_HOURS_END: "07:00:00",
        CONF_TRIGGER_ENTITIES: [],
        CONF_NOTIFY_SERVICES: [],
    }
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result2["type"] == "create_entry"
    assert config_entry.options[CONF_RECENT_WEIGHT] == 0.6
    assert config_entry.options[CONF_RECENT_WINDOW] == 4
    assert config_entry.options[CONF_DAILY_REMINDER_TIME] == "08:30:00"
