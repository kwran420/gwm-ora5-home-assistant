"""Shared ORA 5 entity identity without publishing cloud identifiers."""
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME


class OraEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, metric, name):
        super().__init__(coordinator)
        self.vehicle_key = key
        self.metric = metric
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}_{metric}"
        self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.entry.entry_id}_{key}")},
            name=NAME, manufacturer="GWM", model="ORA 5",
        )

    @property
    def values(self):
        return (self.coordinator.data or {}).get(self.vehicle_key, {})

    @property
    def available(self):
        return super().available and self.vehicle_key in (self.coordinator.data or {})
