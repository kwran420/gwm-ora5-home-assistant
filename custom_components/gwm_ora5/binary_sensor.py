"""Cable connection and actual reported charging state."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .entity import OraEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        OraBinarySensor(entry.runtime_data, key, metric, name)
        for key in entry.runtime_data.vehicles
        for metric, name in [("plugged_in", "Charging cable"), ("charging", "Charging")]
    ])


class OraBinarySensor(OraEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, metric, name):
        super().__init__(coordinator, key, metric, name)
        self._attr_device_class = (BinarySensorDeviceClass.PLUG if metric == "plugged_in"
                                   else BinarySensorDeviceClass.BATTERY_CHARGING)

    @property
    def is_on(self):
        return self.values.get(self.metric)
