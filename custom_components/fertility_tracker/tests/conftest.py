from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME

DOMAIN = "fertility_tracker"

@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: "Wife Tracker"},
        options={},  # use defaults; options flow tests will set them
        title="Wife Tracker",
    )
    entry.add_to_hass(hass)
    return entry

@pytest.fixture
async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
