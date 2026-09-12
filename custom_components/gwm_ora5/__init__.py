"""GWM ORA 5 custom integration."""
from homeassistant.exceptions import ConfigEntryNotReady
from gwm_client import GwmClientError

from .const import PLATFORMS
from .coordinator import OraCoordinator


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
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.aclose()
        return True
    return False
