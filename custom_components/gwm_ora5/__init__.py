"""GWM ORA 5 custom integration."""
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import service
import voluptuous as vol
from gwm_client import GwmClientError

from .const import DOMAIN, PLATFORMS
from .controls import COMFORT_START_ACTIONS
from .coordinator import OraCoordinator


async def _start_comfort(entity, call):
    """Require one explicit start button so a whole-device target cannot fan out."""
    targets = call.data.get('entity_id', [])
    if isinstance(targets, str):
        targets = [targets]
    if (len(targets) != 1 or targets[0] != entity.entity_id
        or any(call.data.get(k) for k in ('device_id', 'area_id', 'floor_id', 'label_id'))
        or getattr(entity, 'action', None) not in COMFORT_START_ACTIONS):
        raise HomeAssistantError('Select exactly one ORA comfort start button')
    await entity.coordinator.control(entity.vehicle_key, entity.action,
        **{k:call.data[k] for k in ('temperature', 'duration', 'level') if k in call.data})


async def async_setup(hass, config):
    service.async_register_platform_entity_service(hass, DOMAIN, 'start_comfort',
        entity_domain='button', func=_start_comfort, schema={
            vol.Optional('temperature'): vol.All(int, vol.Range(min=16, max=32)),
            vol.Optional('duration'): vol.All(int, vol.Range(min=5, max=30)),
            vol.Optional('level'): vol.All(int, vol.Range(min=1, max=3)),
        })
    return True


async def async_setup_entry(hass, entry):
    coordinator = OraCoordinator(hass, entry)
    try:
        await coordinator.initialize()
        await coordinator.async_config_entry_first_refresh()
    except GwmClientError:
        await coordinator.client.aclose()
        raise ConfigEntryNotReady("GWM cloud is unavailable") from None
    except BaseException:
        await coordinator.client.aclose()
        raise
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_options))
    return True


async def _reload_options(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.aclose()
        return True
    return False
