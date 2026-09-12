"""Battery, range, charging status and command outcome."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfLength

from .entity import OraEntity


async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    for key in entry.runtime_data.vehicles:
        for metric, name in [("soc", "Battery"), ("range", "Range"),
                             ("charging_status", "Charging status"), ("command_status", "Command status")]:
            entities.append(OraSensor(entry.runtime_data, key, metric, name))
    async_add_entities(entities)


class OraSensor(OraEntity, SensorEntity):
    def __init__(self, coordinator, key, metric, name):
        super().__init__(coordinator, key, metric, name)
        if metric == "soc":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif metric == "range":
            self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        return self.values.get(self.metric)
