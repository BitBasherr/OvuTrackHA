from __future__ import annotations

from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
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
    EntityFilterSelector,
    EntityFilterSelectorConfig,
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

DEFAULT_NAME = "Fertility Tracker"


def _list_notify_services(hass: HomeAssistant) -> list[str]:
    """Return notify services in 'notify.x' form, sorted."""
    services = hass.services.async_services().get("notify", {})
    # services is a dict of {service_name: schema}
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

        # singleton: only one instance
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=user_input[CONF_NAME],
            data={CONF_NAME: user_input[CONF_NAME]},
        )

    async def async_step_import(self, config: Dict[str, Any]):
        # Support YAML import if you ever add it
        return await self.async_step_user(config)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Options for Fertility Tracker."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Dict[str, Any] | None = None):
        if user_input is not None:
            # basic sanity: clamp weights to [0,1]; (optional) you could also
            # enforce recent_weight + long_weight <= 1.0 if you want.
            rw = float(user_input.get(CONF_RECENT_WEIGHT, DEFAULT_RECENT_WEIGHT))
            lw = float(user_input.get(CONF_LONG_WEIGHT, DEFAULT_LONG_WEIGHT))
            user_input[CONF_RECENT_WEIGHT] = max(0.0, min(1.0, rw))
            user_input[CONF_LONG_WEIGHT] = max(0.0, min(1.0, lw))
            return self.async_create_entry(title="", data=user_input)

        o = self.config_entry.options
        notify_options = [
            SelectOptionDict(label=s, value=s) for s in _list_notify_services(self.hass)
        ]

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_LUTEAL_DAYS, default=o.get(CONF_LUTEAL_DAYS, DEFAULT_LUTEAL_DAYS)
                ): NumberSelector(
                    NumberSelectorConfig(min=8, max=18, step=1, mode=NumberSelectorMode.BOX)
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
                        multiple=True,
                        filter=EntityFilterSelector(
                            EntityFilterSelectorConfig(domain=["device_tracker", "binary_sensor"])
                        ),
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
