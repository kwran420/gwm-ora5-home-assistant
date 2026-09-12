"""Explicit, opt-in charging commands."""
from homeassistant.components.button import ButtonEntity

from .entity import OraEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        OraChargeButton(entry.runtime_data, key, enabled)
        for key in entry.runtime_data.vehicles for enabled in (True, False)
    ])


class OraChargeButton(OraEntity, ButtonEntity):
    def __init__(self, coordinator, key, enabled):
        super().__init__(coordinator, key, "start_charging" if enabled else "stop_charging",
                         "Start charging" if enabled else "Stop charging")
        self.enabled = enabled
        self._attr_icon = "mdi:ev-station" if enabled else "mdi:stop-circle-outline"

    @property
    def available(self):
        return super().available and bool(self.coordinator.entry.data.get("enable_commands"))

    async def async_press(self):
        await self.coordinator.charge(self.vehicle_key, self.enabled)
