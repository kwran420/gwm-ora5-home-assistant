"""Opt-in location entity; coordinates are never included in diagnostics."""
from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from .entity import OraEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([OraTracker(entry.runtime_data, key, 'location', 'Location')
                        for key in entry.runtime_data.vehicles])


class OraTracker(OraEntity, TrackerEntity):
    _attr_entity_registry_enabled_default = False

    @property
    def available(self):
        lat, lon = self.latitude, self.longitude
        return (super().available and self.values.get('gps_authorized') is True
                and type(lat) in (float, int) and -90 <= lat <= 90
                and type(lon) in (float, int) and -180 <= lon <= 180)

    @property
    def source_type(self):
        return SourceType.GPS

    @property
    def latitude(self):
        return self.values.get('latitude')

    @property
    def longitude(self):
        return self.values.get('longitude')
