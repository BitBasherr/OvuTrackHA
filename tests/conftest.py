from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME

from custom_components.fertility_tracker.const import DOMAIN

# ✅ Critical: expose ./custom_components to Home Assistant during tests
@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    # The fixture from PHACC patches Home Assistant loader to discover
    # integrations under the repo's ./custom_components directory.
    yield

@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_NAME: "Wife Tracker"},
        options={},
        title="Wife Tracker",
    )
    entry.add_to_hass(hass)
    return entry

@pytest.fixture
async def setup_integration(hass: HomeAssistant, config_entry: MockConfigEntry):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
