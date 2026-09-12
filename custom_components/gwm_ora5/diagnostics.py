"""Allowlisted diagnostics: never dump config entries or raw cloud records."""
async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "country": entry.data.get("country"),
        "commands_enabled": bool(entry.data.get("enable_commands")),
        "vehicle_count": len(coordinator.vehicles),
        "last_update_success": coordinator.last_update_success,
        "command_states": [r.get("state", "unknown") for r in coordinator.journal.values()],
    }
