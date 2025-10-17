from __future__ import annotations

from typing import Any, Dict
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SafeUnprotectedBinary(hass, entry.entry_id, runtime),
            ImplantationHighBinary(hass, entry.entry_id, runtime),
        ],
        True,
    )


class _BaseBinary(BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        self.hass = hass
        self._runtime = runtime
        self._entry_id = entry_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=self._runtime.data.name,
            manufacturer="Custom",
            model="Fertility Tracker",
            entry_type=DeviceEntryType.SERVICE,
        )


class SafeUnprotectedBinary(_BaseBinary):
    def __init__(self, hass, entry_id, runtime) -> None:
        super().__init__(hass, entry_id, runtime)
        self._attr_unique_id = f"{entry_id}_safe_unprotected"
        self._attr_name = f"{runtime.data.name} Safe Unprotected Sex Today"
        self._state = False

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        label = (metrics.risk_label or "").lower()
        self._state = "safe to have unprotected" in label

    @property
    def is_on(self) -> bool:
        return bool(self._state)

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        return BinarySensorDeviceClass.SAFETY


class ImplantationHighBinary(_BaseBinary):
    def __init__(self, hass, entry_id, runtime) -> None:
        super().__init__(hass, entry_id, runtime)
        self._attr_unique_id = f"{entry_id}_implantation_high"
        self._attr_name = f"{runtime.data.name} High Implantation Risk Today"
        self._state = False

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        label = (metrics.risk_label or "")
        self._state = "High implantation" in label

    @property
    def is_on(self) -> bool:
        return bool(self._state)

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        return BinarySensorDeviceClass.PROBLEM
