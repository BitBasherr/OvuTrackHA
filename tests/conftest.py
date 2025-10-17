from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_NAME

# ----- constants -----
INTEGRATION_DOMAIN = "fertility_tracker"

# repo root:  <repo>/tests/conftest.py  -> parents[1] = <repo>
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "custom_components" / INTEGRATION_DOMAIN

# HA test runner always scans tests/custom_components/*
TESTS_CC_ROOT = Path(__file__).resolve().parent / "custom_components"
DST = TESTS_CC_ROOT / INTEGRATION_DOMAIN


# 0) Hardpoint PHACC to your repo's custom_components as well (belt + suspenders)
#    This env var must be set before the PHACC fixture initializes. Doing it here
#    works because conftest is imported before tests run.
os.environ.setdefault(
    "PYTEST_HOMEASSISTANT_CUSTOM_COMPONENTS",
    str(REPO_ROOT / "custom_components"),
)

# 1) Mirror the integration under tests/custom_components so HA finds it for sure
@pytest.fixture(autouse=True, scope="session")
def _mirror_integration_into_tests_path():
    assert SRC.exists(), f"Expected integration at: {SRC}"
    TESTS_CC_ROOT.mkdir(parents=True, exist_ok=True)
    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)
    yield
    # Keep the mirror for post-failure inspection


# 2) Enable custom integrations for the whole session (PHACC)
@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    yield


# 3) Standard entry + setup fixtures for your tests
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
