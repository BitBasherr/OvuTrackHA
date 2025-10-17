from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from custom_components.fertility_tracker.const import DOMAIN

pytestmark = pytest.mark.asyncio

@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_creates_entry(hass: HomeAssistant):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Wife Tracker"}
    )
    assert result2["type"] == "create_entry"
    assert result2["title"] == "Wife Tracker"
    assert result2["data"][CONF_NAME] == "Wife Tracker"
