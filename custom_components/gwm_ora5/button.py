"""Explicit, opt-in charging commands."""
from homeassistant.components.button import ButtonEntity

from .entity import OraEntity
from .controls import CONTROL_NAMES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        OraChargeButton(entry.runtime_data, key, enabled)
        for key in entry.runtime_data.vehicles for enabled in (True, False)
    ] + [OraControlButton(entry.runtime_data, key, action, name)
         for key in entry.runtime_data.vehicles for action, name in CONTROL_NAMES.items()
         if action not in {'lock', 'unlock'}])


class OraChargeButton(OraEntity, ButtonEntity):
    def __init__(self, coordinator, key, enabled):
        super().__init__(coordinator, key, "start_charging" if enabled else "stop_charging",
                         "Start charging" if enabled else "Stop charging")
        self._charge_enabled = enabled
        self._attr_icon = "mdi:ev-station" if enabled else "mdi:stop-circle-outline"

    @property
    def available(self):
        return super().available and bool(self.coordinator.entry.data.get("enable_commands"))

    async def async_press(self):
        await self.coordinator.charge(self.vehicle_key, self._charge_enabled)


class OraControlButton(OraEntity, ButtonEntity):
    def __init__(self, coordinator, key, action, name):
        super().__init__(coordinator, key, action, name)
        self.action = action
        self._attr_entity_registry_enabled_default = action not in {'horn', 'horn_lights', 'boot_open'}

    @property
    def available(self):
        return super().available and bool(self.coordinator.entry.options.get('enable_vehicle_controls', False))

    async def async_press(self):
        await self.coordinator.control(self.vehicle_key, self.action)
