from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN
from .helpers import calculate_metrics_for_date, today_local


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SafeUnprotectedSexTodayBinary(hass, entry.entry_id, runtime),
            HighImplantationRiskTodayBinary(hass, entry.entry_id, runtime),
        ]
    )


class _BaseFertilityBinary(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY  # closest fit; informational

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


class SafeUnprotectedSexTodayBinary(_BaseFertilityBinary):
    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        super().__init__(hass, entry_id, runtime)
        self._attr_name = "Safe unprotected sex today"
        self._attr_unique_id = f"{entry_id}_safe_unprotected_sex_today"
        self._attr_is_on = False

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        # Safe when risk label explicitly low
        self._attr_is_on = metrics.risk_label is not None and "Safe" in metrics.risk_label


class HighImplantationRiskTodayBinary(_BaseFertilityBinary):
    def __init__(self, hass: HomeAssistant, entry_id: str, runtime) -> None:
        super().__init__(hass, entry_id, runtime)
        self._attr_name = "High implantation risk today"
        self._attr_unique_id = f"{entry_id}_high_implantation_risk_today"
        self._attr_is_on = False

    async def async_update(self) -> None:
        metrics = calculate_metrics_for_date(self._runtime.data, today_local(self.hass))
        self._attr_is_on = metrics.risk_label is not None and "implantation" in metrics.risk_label.lower()
