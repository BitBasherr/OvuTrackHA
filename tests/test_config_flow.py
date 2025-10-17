from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.fertility_tracker.const import DOMAIN
from homeassistant.const import CONF_NAME

pytestmark = pytest.mark.asyncio

@pytest.mark.usefixtures("enable_custom_integrations")
async def test_user_flow_creates_entry(hass: HomeAssistant):
    # show form
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    # submit and create entry
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_NAME: "Wife Tracker"}
    )
    assert result["type"] == "create_entry"
    assert result["title"] == "Wife Tracker"
    assert result["data"][CONF_NAME] == "Wife Tracker"
