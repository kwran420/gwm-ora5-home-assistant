"""Cable connection and actual reported charging state."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from .entity import OraEntity

METRICS = [('plugged_in', 'Charging cable'), ('charging', 'Charging'),
           ('ac_active', 'Climate active'), ('steering_heating', 'Steering wheel heating'),
           ('unlocked', 'Lock'), ('boot_open', 'Boot'),
           ('front_demister', 'Front demister'), ('rear_demister', 'Rear demister'),
           ('air_circulation', 'Air circulation'), ('gps_authorized', 'GPS permission')]
METRICS += [(f'window_{p}', f'{p.replace("_", " ").capitalize()} window')
            for p in ('front_left', 'front_right', 'rear_left', 'rear_right')]
METRICS += [(f'door_{p}', f'{p.replace("_", " ").capitalize()} door')
            for p in ('driver', 'passenger', 'rear_driver', 'rear_passenger')]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        OraBinarySensor(entry.runtime_data, key, metric, name)
        for key in entry.runtime_data.vehicles
        for metric, name in METRICS
    ])


class OraBinarySensor(OraEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, metric, name):
        super().__init__(coordinator, key, metric, name)
        if metric == 'plugged_in':
            self._attr_device_class = BinarySensorDeviceClass.PLUG
        elif metric == 'charging':
            self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
        elif metric == 'unlocked':
            self._attr_device_class = BinarySensorDeviceClass.LOCK
        elif metric.startswith('window_'):
            self._attr_device_class = BinarySensorDeviceClass.WINDOW
        elif metric.startswith('door_') or metric == 'boot_open':
            self._attr_device_class = BinarySensorDeviceClass.DOOR

    @property
    def is_on(self):
        return self.values.get(self.metric)
