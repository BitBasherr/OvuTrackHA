from __future__ import annotations

import datetime as dt
import logging
import os
import shutil
from typing import Optional, Callable, Any, Dict

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers.storage import Store
from homeassistant.helpers import event as hass_event
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.components import websocket_api
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
from homeassistant.setup import async_when_setup

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
    calculate_metrics_for_date,
    today_local,
    parse_time,
    coerce_date,
    SexEvent,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _copy_tree(src: str, dst: str) -> None:
    """Copy files from src to dst (update only if changed)."""
    if not os.path.isdir(src):
        return
    os.makedirs(dst, exist_ok=True)
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        out_dir = os.path.join(dst, "" if rel == "." else rel)
        os.makedirs(out_dir, exist_ok=True)
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join(out_dir, f)
            try:
                if not os.path.exists(d) or os.path.getmtime(s) > os.path.getmtime(d):
                    shutil.copy2(s, d)
            except Exception as exc:  # pragma: no cover
                _LOGGER.debug("Copy failed for %s -> %s: %s", s, d, exc)


async def _ensure_www_bundle(hass: HomeAssistant) -> None:
    """Mirror our frontend into /config/www/fertility_tracker for /local/ serving."""
    src = hass.config.path("custom_components/fertility_tracker/frontend")
    dst = hass.config.path("www/fertility_tracker")
    try:
        await hass.async_add_executor_job(_copy_tree, src, dst)
        _LOGGER.debug("Frontend copied to %s", dst)
    except Exception as exc:  # pragma: no cover
        _LOGGER.debug("Failed copying frontend: %s", exc)


class EntryRuntime:
    """Runtime state per config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}{entry.entry_id}")
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
        self._listeners: list[Callable[[], None]] = []
        self._timer_unsub: Optional[Callable[[], None]] = None

    async def async_load(self) -> None:
        saved = await self.store.async_load()
        if saved:
            self.data = FertilityData.from_dict(saved)
            _LOGGER.debug("Loaded fertility data for %s", self.entry.entry_id)

    async def async_save(self) -> None:
        await self.store.async_save(self.data.as_dict())
        _LOGGER.debug("Saved fertility data for %s", self.entry.entry_id)

    async def async_setup_timers_and_triggers(self) -> None:
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None

        target_time = parse_time(self.data.daily_reminder_time) or parse_time(
            DEFAULT_DAILY_REMINDER_TIME
        )

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

        if self._listeners:
            for unsub in self._listeners:
                try:
                    unsub()
                except Exception:
                    pass
            self._listeners.clear()

        for ent_id in self.data.trigger_entities:
            unsub = async_track_state_change_event(
                self.hass, ent_id, self._trigger_entity_changed
            )
            self._listeners.append(unsub)

    async def async_unload(self) -> None:
        if self._timer_unsub:
            self._timer_unsub()
            self._timer_unsub = None
        for unsub in self._listeners:
            try:
                unsub()
            except Exception:
                pass
        self._listeners.clear()
        await self.async_save()

    async def _trigger_entity_changed(self, event) -> None:
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
        metrics = calculate_metrics_for_date(self.data, today_local(self.hass))
        if metrics.next_period_date is None:
            return

        today = today_local(self.hass).date()
        if abs((metrics.next_period_date - today).days) <= 1:
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
        try:
            start = parse_time(self.data.quiet_hours_start)
            end = parse_time(self.data.quiet_hours_end)
            if start is None or end is None:
                return False
            start_dt = now.replace(
                hour=start.hour, minute=start.minute, second=start.second, microsecond=0
            )
            end_dt = now.replace(
                hour=end.hour, minute=end.minute, second=end.second, microsecond=0
            )
            if start_dt <= end_dt:
                return start_dt <= now <= end_dt
            return now >= start_dt or now <= end_dt
        except Exception:
            return False

    async def _notify_today_risk(self, reason: str) -> None:
        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        now = dt_util.now(tz)

        if self._quiet_hours(now):
            return
        if self.data.last_notified_date == now.date().isoformat():
            return

        metrics = calculate_metrics_for_date(self.data, now)
        if metrics.risk_label:
            await self._send_notifications(
                title=f"{self.data.name}: Today's fertility risk",
                message=(
                    f"{metrics.risk_label} (triggered by {reason}). "
                    f"Cycle day {metrics.cycle_day}. Ovulation ~ {metrics.predicted_ovulation_date}."
                ),
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
                domain, service, {"title": title, "message": message}, blocking=True
            )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Bootstrap frontend (copy → /local), register panel, and WS API."""
    # 1) Ensure /local bundle is in place (works on all HA versions)
    await _ensure_www_bundle(hass)

    # 2) Register sidebar panel (load from /local)
    async def _register_panel(_hass: HomeAssistant, _component: str) -> None:
        try:
            # Remove if already there (avoid duplicates on reload)
            try:
                _hass.components.frontend.async_remove_panel("fertility-tracker")
            except Exception:
                pass
            _hass.components.frontend.async_register_panel(
                _hass,
                component_name="custom",
                frontend_url_path="fertility-tracker",
                sidebar_title="Fertility Tracker",
                sidebar_icon="mdi:calendar-heart",
                require_admin=False,
                config={
                    "module_url": "/local/fertility_tracker/panel.js",
                    "embed_iframe": False,
                    "trust_external": False,
                },
                update=False,
            )
            _LOGGER.info("Sidebar panel registered at /fertility-tracker")
        except Exception as exc:  # pragma: no cover
            _LOGGER.debug("Failed to register panel: %s", exc)

    if "frontend" in hass.config.components:
        await _register_panel(hass, "frontend")
    else:
        async_when_setup(hass, "frontend", _register_panel)

    # 3) WebSocket API
    websocket_api.async_register_command(hass, ws_discover_entry)
    websocket_api.async_register_command(hass, ws_list_cycles)
    websocket_api.async_register_command(hass, ws_add_period)
    websocket_api.async_register_command(hass, ws_edit_cycle)
    websocket_api.async_register_command(hass, ws_delete_cycle)
    websocket_api.async_register_command(hass, ws_export_data)

    # 4) Services
    async def _get_runtime_for_service(call: ServiceCall) -> EntryRuntime | None:
        entry_id = call.data.get("entry_id")
        runtime = None
        if entry_id and entry_id in hass.data.get(DOMAIN, {}):
            runtime = hass.data[DOMAIN][entry_id]
        else:
            entries = hass.data.get(DOMAIN, {})
            if len(entries) == 1:
                runtime = list(entries.values())[0]
        if runtime is None:
            _LOGGER.warning(
                "fertility_tracker service called but entry not found. entry_id=%s",
                entry_id,
            )
        return runtime

    async def _svc_log_period_start(call: ServiceCall) -> None:
        runtime = await _get_runtime_for_service(call)
        if not runtime:
            return
        date = coerce_date(call.data["date"])
        notes = call.data.get("notes")
        runtime.data.add_period(start=date, end=None, notes=notes)
        await runtime.async_save()

    async def _svc_log_period_end(call: ServiceCall) -> None:
        runtime = await _get_runtime_for_service(call)
        if not runtime:
            return
        date = coerce_date(call.data["date"])
        cycle_id = call.data.get("cycle_id")
        if cycle_id:
            ok = runtime.data.edit_cycle(
                cycle_id=cycle_id, start=None, end=date, notes=None
            )
            if not ok:
                _LOGGER.warning("cycle_id %s not found for period_end", cycle_id)
        else:
            if runtime.data.cycles:
                runtime.data.cycles[-1].end = date
        await runtime.async_save()

    async def _svc_log_sex(call: ServiceCall) -> None:
        runtime = await _get_runtime_for_service(call)
        if not runtime:
            return
        protected = bool(call.data["protected"])
        notes = call.data.get("notes")
        runtime.data.sex_events.append(
            SexEvent(ts=today_local(hass), protected=protected, notes=notes)
        )
        await runtime.async_save()

    hass.services.async_register(DOMAIN, "log_period_start", _svc_log_period_start)
    hass.services.async_register(DOMAIN, "log_period_end", _svc_log_period_end)
    hass.services.async_register(DOMAIN, "log_sex", _svc_log_sex)

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


# -------------------- WebSocket API --------------------

@websocket_api.websocket_command(
    {vol.Required("type"): "fertility_tracker/discover_entry"}
)
@websocket_api.async_response
async def ws_discover_entry(hass: HomeAssistant, connection, msg: Dict[str, Any]):
    entries: dict[str, EntryRuntime] = hass.data.get(DOMAIN, {})
    if not entries:
        connection.send_result(msg["id"], {"found": False})
        return
    entry_id, runtime = next(iter(entries.items()))
    connection.send_result(
        msg["id"], {"found": True, "entry_id": entry_id, "name": runtime.data.name}
    )


@websocket_api.websocket_command(
    {vol.Required("type"): "fertility_tracker/list_cycles", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_list_cycles(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    connection.send_result(msg["id"], runtime.data.as_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): "fertility_tracker/add_period",
        vol.Required("entry_id"): str,
        vol.Required("start"): str,
        vol.Optional("end"): str,
        vol.Optional("notes"): str,
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
        vol.Required("type"): "fertility_tracker/edit_cycle",
        vol.Required("entry_id"): str,
        vol.Required("cycle_id"): str,
        vol.Optional("start"): str,
        vol.Optional("end"): str,
        vol.Optional("notes"): str,
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
        vol.Required("type"): "fertility_tracker/delete_cycle",
        vol.Required("entry_id"): str,
        vol.Required("cycle_id"): str,
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
    {vol.Required("type"): "fertility_tracker/export_data", vol.Required("entry_id"): str}
)
@websocket_api.async_response
async def ws_export_data(hass, connection, msg):
    runtime = _get_runtime(hass, msg["entry_id"])
    connection.send_result(msg["id"], runtime.data.as_dict())