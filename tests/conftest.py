from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME

# ----- constants -----
INTEGRATION_DOMAIN = "fertility_tracker"
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "custom_components" / INTEGRATION_DOMAIN
TESTS_CC_ROOT = Path(__file__).resolve().parent / "custom_components"
DST = TESTS_CC_ROOT / INTEGRATION_DOMAIN


# ✅ Always mirror the real integration into tests/custom_components/
# Home Assistant test loader *always* scans this path.
@pytest.fixture(autouse=True, scope="session")
def _mirror_integration_into_tests_path():
    assert SRC.exists(), f"Expected integration at: {SRC}"
    TESTS_CC_ROOT.mkdir(parents=True, exist_ok=True)
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    yield
    # leave the copied tree for post-failure debugging


# ✅ Enable custom integrations for the whole session
@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    # Provided by pytest-homeassistant-custom-component
    yield


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=INTEGRATION_DOMAIN,
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
