from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.storage import Store
from homeassistant.helpers import event as hass_event, device_registry as dr
from homeassistant.components import frontend
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.components import websocket_api

from .const import (
    DOMAIN,
    PLATFORMS,
    STORAGE_VERSION,
    STORAGE_KEY_PREFIX,
    CONF_NAME,
    CONF_LUTEAL_DAYS,
    CONF_RECENT_WEIGHT,
    CONF_LONG_WEIGHT,
    CONF_RECENT_WINDOW,
    CONF_NOTIFY_SERVICES,
    CONF_TRIGGER_ENTITIES,
    CONF_DAILY_REMINDER_TIME,
    CONF_QUIET_HOURS_START,
    CONF_QUIET_HOURS_END,
    DEFAULT_LUTEAL_DAYS,
    DEFAULT_RECENT_WEIGHT,
    DEFAULT_LONG_WEIGHT,
    DEFAULT_RECENT_WINDOW,
    DEFAULT_DAILY_REMINDER_TIME,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
)

from .helpers import (
    FertilityData,
    CycleEvent,
    calculate_metrics_for_date,
    today_local,
    parse_time,
    coerce_date,
)

_LOGGER = logging.getLogger(__name__)


class EntryRuntime:
    """Runtime state per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry.entry_id}"
        )
        self.data: FertilityData = FertilityData(
            name=entry.data.get(CONF_NAME, entry.title or "Fertility"),
            luteal_days=entry.options.get(CONF_LUTEAL_DAYS, DEFAULT_LUTEAL_DAYS),
            recent_weight=entry.options.get(CONF_RECENT_WEIGHT, DEFAULT_RECENT_WEIGHT),
            long_weight=entry.options.get(CONF_LONG_WEIGHT, DEFAULT_LONG_WEIGHT),
            recent_window=entry.options.get(CONF_RECENT_WINDOW, DEFAULT_RECENT_WINDOW),
            notify_services=list(entry.options.get(CONF_NOTIFY_SERVICES, [])),
            trigger_entities=list(entry.options.get(CONF_TRIGGER_ENTITIES, [])),
            quiet_hours_start=entry.options.get(
                CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START
            ),
            quiet_hours_end=entry.options.get(
                CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END
            ),
            daily_reminder_time=entry.options.get(
                CONF_DAILY_REMINDER_TIME, DEFAULT_DAILY_REMINDER_TIME
            ),
            cycles=[],
            sex_events=[],
            pregnancy_tests=[],
            last_notified_date=None,
        )
        self._listeners: list[callable] = []
        self._timer_unsub: Optional[callable] = None

    async def async_load(self) -> None:
        saved = await self.store.async_load()
        if saved:
            self.data = FertilityData.from_dict(saved)
            _LOGGER.debug("Loaded fertility data for %s", self.entry.entry_id)

    async def async_save(self) -> None:
        await self.store.async_save(self.data.as_dict())
        _LOGGER.debug("Saved fertility data for %s", self.entry.entry_id)

    async def async_setup_timers_and_triggers(self) -> None:
        # Daily reminder timer
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None

        target_time = parse_time(self.data.daily_reminder_time)
        if target_time is None:
            target_time = parse_time(DEFAULT_DAILY_REMINDER_TIME)

        @callback
        def _daily_reminder(now: dt.datetime) -> None:
            self.hass.async_create_task(self._maybe_send_expected_period_prompt())

        self._timer_unsub = hass_event.async_track_time_change(
            self.hass,
            _daily_reminder,
            hour=target_time.hour,
            minute=target_time.minute,
            second=target_time.second,
        )

        # Trigger entities (arrival / on) for risk notification
        if self._listeners:
            for unsub in self._listeners:
                try:
                    unsub()
                except Exception:  # noqa: BLE001
                    pass
            self._listeners.clear()

        for ent_id in self.data.trigger_entities:
            unsub = self.hass.helpers.event.async_track_state_change_event(
                ent_id, self._trigger_entity_changed
            )
            self._listeners.append(unsub)

    async def async_unload(self) -> None:
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        for unsub in self._listeners:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._listeners.clear()
        await self.async_save()

    async def _trigger_entity_changed(self, event) -> None:
        """On arrival (home) or binary_sensor turns on, notify today's risk."""
        new_state = event.data.get("new_state")
        if not new_state:
            return
        state = new_state.state
        domain = new_state.domain
        if domain == "device_tracker" and state == "home":
            await self._notify_today_risk(reason=f"{new_state.entity_id} is home")
        elif domain == "binary_sensor" and state == "on":
            await self._notify_today_risk(reason=f"{new_state.entity_id} turned on")

    async def _maybe_send_expected_period_prompt(self) -> None:
        """If expected period date is today±1 and not logged, ask via notify.*"""
        metrics = calculate_metrics_for_date(self.data, today_local(self.hass))
        if metrics.next_period_date is None:
            return

        today = today_local(self.hass).date()
        if abs((metrics.next_period_date - today).days) <= 1:
            # Check if a period event already logged covering around today
            already = any(
                c.start <= today <= (c.end or c.start) for c in self.data.cycles
            )
            if not already:
                await self._send_notifications(
                    title=f"{self.data.name}: Period check",
                    message=(
                        f"Is your period starting around {metrics.next_period_date.isoformat()}? "
                        "You can correct or confirm in: Settings → Devices & Services → Fertility Tracker panel."
                    ),
                )

    def _quiet_hours(self, now: dt.datetime) -> bool:
        """Check if now is within quiet hours range (may span midnight)."""
        try:
            start = parse_time(self.data.quiet_hours_start)
            end = parse_time(self.data.quiet_hours_end)
            if start is None or end is None:
                return False
            start_dt = now.replace(hour=start.hour, minute=start.minute, second=start.second, microsecond=0)
            end_dt = now.replace(hour=end.hour, minute=end.minute, second=end.second, microsecond=0)
            if start_dt <= end_dt:
                return start_dt <= now <= end_dt
            # spans midnight
            return now >= start_dt or now <= end_dt
        except Exception:  # noqa: BLE001
            return False

    async def _notify_today_risk(self, reason: str) -> None:
        now = dt.datetime.now(self.hass.config.time_zone)
        if self._quiet_hours(now):
            return
        if self.data.last_notified_date == now.date().isoformat():
            return
        metrics = calculate_metrics_for_date(self.data, now)
        if metrics.risk_label:
            await self._send_notifications(
                title=f"{self.data.name}: Today's fertility risk",
                message=f"{metrics.risk_label} (triggered by {reason}). "
                        f"Cycle day {metrics.cycle_day}. Ovulation ~ {metrics.predicted_ovulation_date}."
            )
            self.data.last_notified_date = now.date().isoformat()
            await self.async_save()

    async def _send_notifications(self, title: str, message: str) -> None:
        for svc in self.data.notify_services:
            try:
                domain, service = svc.split(".")
            except ValueError:
                domain, service = "notify", svc
            await self.hass.services.async_call(
                domain, service, {"title": title, "message": message}, blocking=False
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    # Serve static frontend (panel)
    path = hass.http.register_static_path(
        "/fertility_tracker_frontend",
        hass.config.path("custom_components/fertility_tracker/frontend"),
        cache_headers=True,
        require_auth=True,
        name="Fertility Tracker Frontend",
        allow_directory=True,
    )
    assert isinstance(path, StaticPathConfig)
    # Register custom panel
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="Fertility Tracker",
        sidebar_icon="mdi:calendar-heart",
        frontend_url_path="fertility-tracker",
        config={
            "module_url": "/fertility_tracker_frontend/panel.js",
            "embed_iframe": False,
            "trust_external": False,
        },
        require_admin=False,
    )

    # Websocket: expose CRUD for frontend
    websocket_api.async_register_command(hass, ws_list_cycles)
    websocket_api.async_register_command(hass, ws_add_period)
    websocket_api.async_register_command(hass, ws_edit_cycle)
    websocket_api.async_register_command(hass, ws_delete_cycle)
    websocket_api.async_register_command(hass, ws_export_data)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = EntryRuntime(hass, entry)
    await runtime.async_load()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await runtime.async_setup_timers_and_triggers()

    @callback
    def _on_stop(event):
        hass.async_create_task(runtime.async_unload())

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime: EntryRuntime = hass.data[DOMAIN].pop(entry.entry_id)
    await runtime.async_unload()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    return unload_ok


def _get_runtime(hass: HomeAssistant, entry_id: str) -> EntryRuntime:
    return hass.data[DOMAIN][entry_id]


# -------------------- WebSocket API for Panel --------------------

@websocket_api.websocket_command(
    {
        "type": "fertility_tracker/list_cycles",
        "entry_id": str,
    }
)
@websocket_api.async_response
async def ws_list_cycles(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    payload = runtime.data.as_dict()
    connection.send_result(msg["id"], payload)


@websocket_api.websocket_command(
    {
        "type": "fertility_tracker/add_period",
        "entry_id": str,
        "start": str,
        "end": str | None,
        "notes": str | None,
    }
)
@websocket_api.async_response
async def ws_add_period(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    start = coerce_date(msg.get("start"))
    end = coerce_date(msg.get("end")) if msg.get("end") else None
    notes = msg.get("notes")
    runtime.data.add_period(start=start, end=end, notes=notes)
    await runtime.async_save()
    connection.send_result(msg["id"], {"ok": True})


@websocket_api.websocket_command(
    {
        "type": "fertility_tracker/edit_cycle",
        "entry_id": str,
        "cycle_id": str,
        "start": str | None,
        "end": str | None,
        "notes": str | None,
    }
)
@websocket_api.async_response
async def ws_edit_cycle(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    ok = runtime.data.edit_cycle(
        cycle_id=msg["cycle_id"],
        start=coerce_date(msg.get("start")) if msg.get("start") else None,
        end=coerce_date(msg.get("end")) if msg.get("end") else None,
        notes=msg.get("notes"),
    )
    if ok:
        await runtime.async_save()
    connection.send_result(msg["id"], {"ok": ok})


@websocket_api.websocket_command(
    {
        "type": "fertility_tracker/delete_cycle",
        "entry_id": str,
        "cycle_id": str,
    }
)
@websocket_api.async_response
async def ws_delete_cycle(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    ok = runtime.data.delete_cycle(msg["cycle_id"])
    if ok:
        await runtime.async_save()
    connection.send_result(msg["id"], {"ok": ok})


@websocket_api.websocket_command(
    {
        "type": "fertility_tracker/export_data",
        "entry_id": str,
    }
)
@websocket_api.async_response
async def ws_export_data(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    connection.send_result(msg["id"], runtime.data.as_dict())
