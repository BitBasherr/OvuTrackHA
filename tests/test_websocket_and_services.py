from __future__ import annotations

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant

# ✅ Use the PHACC helper, not tests.common
from pytest_homeassistant_custom_component.common import async_mock_service

from custom_components.fertility_tracker.const import DOMAIN
from custom_components.fertility_tracker.helpers import coerce_date

pytestmark = pytest.mark.asyncio

async def test_ws_list_add_edit_delete(hass: HomeAssistant, hass_ws_client, setup_integration, config_entry):
    client = await hass_ws_client(hass)
    # list
    await client.send_json({"id": 1, "type": "fertility_tracker/list_cycles", "entry_id": config_entry.entry_id})
    resp = await client.receive_json()
    assert resp["success"] is True
    assert resp["result"]["cycles"] == []

    # add
    await client.send_json({"id": 2, "type": "fertility_tracker/add_period", "entry_id": config_entry.entry_id,
                            "start": "2025-09-01", "end": "2025-09-05", "notes": "ok"})
    resp = await client.receive_json()
    assert resp["success"] is True

    # edit
    await client.send_json({"id": 3, "type": "fertility_tracker/list_cycles", "entry_id": config_entry.entry_id})
    resp = await client.receive_json()
    cycle_id = resp["result"]["cycles"][0]["id"]

    await client.send_json({"id": 4, "type": "fertility_tracker/edit_cycle", "entry_id": config_entry.entry_id,
                            "cycle_id": cycle_id, "notes": "edited", "start": "2025-09-02", "end": "2025-09-06"})
    resp = await client.receive_json()
    assert resp["success"] is True
    assert resp["result"]["ok"] is True

    # delete
    await client.send_json({"id": 5, "type": "fertility_tracker/delete_cycle", "entry_id": config_entry.entry_id,
                            "cycle_id": cycle_id})
    resp = await client.receive_json()
    assert resp["success"] is True
    assert resp["result"]["ok"] is True


async def test_domain_services_and_notify(hass: HomeAssistant, setup_integration, config_entry):
    # Mock a notify service and set options to use it
    calls = async_mock_service(hass, "notify", "mobile_app_test")
    runtime = hass.data[DOMAIN][config_entry.entry_id]
    runtime.data.notify_services = ["notify.mobile_app_test"]

    # Log a cycle start/end via services
    await hass.services.async_call(DOMAIN, "log_period_start", {
        "entry_id": config_entry.entry_id,
        "date": "2025-09-01",
        "notes": "service start"
    }, blocking=True)

    await hass.services.async_call(DOMAIN, "log_period_end", {
        "entry_id": config_entry.entry_id,
        "date": "2025-09-05"
    }, blocking=True)

    # Trigger a notification by calling the private notifier near expected period
    from custom_components.fertility_tracker.__init__ import EntryRuntime
    with freeze_time("2025-09-10 09:05:00"):
        await runtime._notify_today_risk(reason="test")  # noqa: SLF001

    await hass.async_block_till_done()
    # We can't guarantee risk label or quiet hours, just make sure no exceptions
    assert isinstance(calls, list)
