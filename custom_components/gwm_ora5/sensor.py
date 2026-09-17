"""Battery, range, charging status and command outcome."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfLength
from datetime import datetime, UTC

from .entity import OraEntity
from .signals import signal_metadata

METRICS = [('soc', 'Battery'), ('range', 'Range'), ('charging_status', 'Charging status'),
           ('command_status', 'Command status'), ('odometer', 'Odometer'),
           ('remaining_charge_time', 'Estimated remaining charging time'),
           ('charging_mode_code', 'Charging mode code'), ('away_mode_code', 'Away mode code'),
           ('vehicle_updated_ms', 'Vehicle data timestamp'), ('raw_signals', 'Raw status signals'),
           ('recorded_charging_sessions', 'Recorded charging sessions'), ('schedule_plan_count', 'Charging schedule records'),
           ('remote_history_last_ms', 'Last recorded remote command')]
METRICS += [(f'tyre_{kind}_{position}', f'{position.replace("_", " ").capitalize()} tyre {kind}')
            for kind in ('pressure', 'temperature')
            for position in ('front_left', 'front_right', 'rear_left', 'rear_right')]
METRICS += [(f'seat_{kind}_{side}', f'{side.capitalize()} seat {"heating" if kind == "heat" else "ventilation"} level')
            for kind in ('heat', 'vent') for side in ('driver', 'passenger')]


async def async_setup_entry(hass, entry, async_add_entities):
    entities = []
    for key in entry.runtime_data.vehicles:
        for metric, name in METRICS:
            entities.append(OraSensor(entry.runtime_data, key, metric, name))
    async_add_entities(entities)


class OraSensor(OraEntity, SensorEntity):
    def __init__(self, coordinator, key, metric, name):
        super().__init__(coordinator, key, metric, name)
        if metric == 'raw_signals':
            self._attr_native_unit_of_measurement = 'signals'
        if metric == "soc":
            self._attr_native_unit_of_measurement = PERCENTAGE
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif metric in ("range", "odometer"):
            self._attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
            self._attr_device_class = SensorDeviceClass.DISTANCE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif metric == 'remaining_charge_time':
            self._attr_native_unit_of_measurement = 'min'
            self._attr_device_class = SensorDeviceClass.DURATION
        elif metric.startswith('tyre_pressure_'):
            self._attr_native_unit_of_measurement = 'kPa'
            self._attr_device_class = SensorDeviceClass.PRESSURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif metric.startswith('tyre_temperature_'):
            self._attr_native_unit_of_measurement = '°C'
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif metric in ('vehicle_updated_ms', 'remote_history_last_ms'):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if metric in ('raw_signals', 'charging_mode_code', 'away_mode_code', 'schedule_plan_count', 'remote_history_last_ms'):
            self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self):
        if self.metric == 'raw_signals':
            return len(self.values.get('raw_signals', {}))
        if self.metric in ('vehicle_updated_ms', 'remote_history_last_ms'):
            value = self.values.get(self.metric)
            try:
                return datetime.fromtimestamp(value / 1000, UTC) if value else None
            except (TypeError, ValueError, OverflowError, OSError):
                return None
        return self.values.get(self.metric)

    @property
    def extra_state_attributes(self):
        if self.metric == 'command_status':
            from .controls import CONTROL_NAMES
            action = self.values.get('command_action')
            expected = self.values.get('command_expected_charging')
            attrs = {'last_action': action if action in {*CONTROL_NAMES, 'start', 'stop'} else None,
                     'expected_charging': expected if type(expected) is bool else None}
            resolution = self.values.get('command_resolution')
            if resolution in {'remote_result_and_feedback', 'observed_stopped'}:
                attrs['resolution'] = resolution
            return attrs
        if self.metric == 'remote_history_last_ms':
            return {**self.values.get('remote_history_summary', {}),
                    'meaning': 'Provider history only; completion is not physical-state confirmation'}
        if self.metric == 'schedule_plan_count':
            return {'plans': self.values.get('charging_plans', [])}
        if self.metric == 'raw_signals':
            raw = self.values.get('raw_signals', {})
            return {**raw, **signal_metadata(raw)}
        return {}
