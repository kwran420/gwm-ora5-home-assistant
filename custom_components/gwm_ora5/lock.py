"""A real lock entity for HA dashboards and secure voice-assistant exposure."""
from homeassistant.components.lock import LockEntity
from .entity import OraEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OraLock(entry.runtime_data, key, 'door_lock', 'Door lock')
                        for key in entry.runtime_data.vehicles])


class OraLock(OraEntity, LockEntity):
    @property
    def available(self):
        return super().available and bool(self.coordinator.entry.options.get('enable_vehicle_controls', False))

    @property
    def is_locked(self):
        unlocked = self.values.get('unlocked')
        return not unlocked if type(unlocked) is bool else None

    async def async_lock(self, **kwargs):
        await self.coordinator.control(self.vehicle_key, 'lock')

    async def async_unlock(self, **kwargs):
        await self.coordinator.control(self.vehicle_key, 'unlock')
