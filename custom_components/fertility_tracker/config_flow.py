from __future__ import annotations

from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectOptionDict,
    TimeSelector,
    TimeSelectorConfig,
)

from .const import (
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
    DEFAULT_LUTEAL_DAYS,
    DEFAULT_RECENT_WEIGHT,
    DEFAULT_LONG_WEIGHT,
    DEFAULT_RECENT_WINDOW,
    DEFAULT_DAILY_REMINDER_TIME,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
)

# Keep this to satisfy the tests that expect "Wife Tracker"
DEFAULT_NAME = "Wife Tracker"


def _list_notify_services(hass: HomeAssistant) -> list[str]:
    """Return notify services in 'notify.x' form, sorted."""
    services = hass.services.async_services().get("notify", {})
    return [f"notify.{name}" for name in sorted(services.keys())]


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: Dict[str, Any] | None = None):
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector(
                        TextSelectorConfig(type="text")
                    ),
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        # Singleton: only one instance allowed
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        name = user_input[CONF_NAME]
        return self.async_create_entry(
            title=name,
            data={CONF_NAME: name},
        )

    async def async_step_import(self, config: Dict[str, Any]):
        # Support YAML import if needed
        return await self.async_step_user(config)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(OptionsFlow):
    """Options for Fertility Tracker."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # IMPORTANT: Do NOT assign to self.config_entry (deprecated in 2025.12)
        self._entry = config_entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        if user_input is not None:
            # Clamp weights to [0, 1]
            rw = float(user_input.get(CONF_RECENT_WEIGHT, DEFAULT_RECENT_WEIGHT))
            lw = float(user_input.get(CONF_LONG_WEIGHT, DEFAULT_LONG_WEIGHT))
            user_input[CONF_RECENT_WEIGHT] = max(0.0, min(1.0, rw))
            user_input[CONF_LONG_WEIGHT] = max(0.0, min(1.0, lw))
            return self.async_create_entry(title="", data=user_input)

        o = self._entry.options or {}

        notify_options = [
            SelectOptionDict(label=s, value=s) for s in _list_notify_services(self.hass)
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_LUTEAL_DAYS, default=o.get(CONF_LUTEAL_DAYS, DEFAULT_LUTEAL_DAYS)
                ): NumberSelector(
                    NumberSelectorConfig(min=8, max=20, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_RECENT_WEIGHT,
                    default=o.get(CONF_RECENT_WEIGHT, DEFAULT_RECENT_WEIGHT),
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_LONG_WEIGHT, default=o.get(CONF_LONG_WEIGHT, DEFAULT_LONG_WEIGHT)
                ): NumberSelector(
                    NumberSelectorConfig(min=0.0, max=1.0, step=0.05, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_RECENT_WINDOW,
                    default=o.get(CONF_RECENT_WINDOW, DEFAULT_RECENT_WINDOW),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=12, step=1, mode=NumberSelectorMode.BOX)
                ),
                vol.Optional(
                    CONF_DAILY_REMINDER_TIME,
                    default=o.get(CONF_DAILY_REMINDER_TIME, DEFAULT_DAILY_REMINDER_TIME),
                ): TimeSelector(TimeSelectorConfig()),
                vol.Optional(
                    CONF_QUIET_HOURS_START,
                    default=o.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START),
                ): TimeSelector(TimeSelectorConfig()),
                vol.Optional(
                    CONF_QUIET_HOURS_END,
                    default=o.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END),
                ): TimeSelector(TimeSelectorConfig()),
                vol.Optional(
                    CONF_TRIGGER_ENTITIES,
                    default=o.get(CONF_TRIGGER_ENTITIES, []),
                ): EntitySelector(
                    EntitySelectorConfig(
                        # Keep domains broad to remain compatible with HA selector behavior
                        domain=["device_tracker", "binary_sensor"],
                        multiple=True,
                    )
                ),
                vol.Optional(
                    CONF_NOTIFY_SERVICES,
                    default=o.get(CONF_NOTIFY_SERVICES, []),
                ): SelectSelector(
                    SelectSelectorConfig(multiple=True, mode="list", options=notify_options)
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
