"""Read polling and serialized, journaled charging commands."""
import asyncio
import logging
import uuid
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from gwm_client import GwmAuthenticationError, GwmClientError
from gwm_client.anz_auth import AnzAuthenticated

from .api import (charging_result, decode_state, encode_state, is_ora5,
                  make_credentials, new_client, telemetry, vehicle_key)
from .const import DOMAIN, POLL_SECONDS

LOGGER = logging.getLogger(__name__)
AUTH_CODES = {"607501", "550004", "551004", "551006", "607124", "-101"}


class OraCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=POLL_SECONDS))
        self.entry = entry
        self.client = new_client()
        self.vehicles = {}
        self.command_lock = asyncio.Lock()
        self.journal = {}
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.commands", private=True)

    async def initialize(self):
        self.journal = await self.store.async_load() or {}
        result = await self.client.authenticate_anz(
            make_credentials(self.entry.data),
            state=decode_state(self.entry.data.get("auth_state")),
            allow_session_reclaim=False,
        )
        if not isinstance(result, AnzAuthenticated):
            raise ConfigEntryAuthFailed("GWM sign-in needs verification")
        self._save_auth(result.state)

    def _save_auth(self, state):
        data = {**self.entry.data, "auth_state": encode_state(state)}
        if data != self.entry.data:
            self.hass.config_entries.async_update_entry(self.entry, data=data)

    async def _read_vehicles(self):
        records = await self.client.acquire_vehicles()
        self.vehicles = {vehicle_key(v.identifier): v for v in records if is_ora5(v)}
        values = {}
        for key, vehicle in self.vehicles.items():
            values[key] = telemetry(await self.client.get_last_status(vehicle.identifier))
            record = self.journal.get(key, {})
            if record.get("state") in {"accepted", "submitting", "pending"} and record.get("sequence"):
                items = await self.client.charge_result(vehicle.identifier, record["sequence"])
                record["state"] = charging_result(items)
                await self.store.async_save(self.journal)
            values[key]["command_status"] = record.get("state", "idle")
        return values

    async def _async_update_data(self):
        try:
            return await self._read_vehicles()
        except GwmClientError as error:
            if isinstance(error, GwmAuthenticationError) or getattr(error, "api_code", None) in AUTH_CODES:
                # Refresh the current session once. Never reclaim the phone's
                # session or send a verification email from background polling.
                try:
                    result = await self.client.refresh_current_anz_session(
                        make_credentials(self.entry.data), decode_state(self.entry.data.get("auth_state"))
                    )
                    self._save_auth(result.state)
                    return await self._read_vehicles()
                except GwmClientError:
                    raise ConfigEntryAuthFailed("GWM session needs sign-in") from None
            raise UpdateFailed("GWM cloud data is unavailable") from None

    async def charge(self, key, enabled):
        if not self.entry.data.get("enable_commands"):
            raise HomeAssistantError("Enable charging commands in integration configuration first")
        if key not in self.vehicles:
            raise HomeAssistantError("ORA 5 is unavailable")
        if self.command_lock.locked():
            raise HomeAssistantError("A charging command is still running")
        if enabled:
            if not self.last_update_success or not self.data or self.data.get(key, {}).get("plugged_in") is not True:
                raise HomeAssistantError("A connected charging cable has not been confirmed")
            if self.journal.get(key, {}).get("state") in {"submitting", "accepted", "pending", "unknown"}:
                raise HomeAssistantError("Resolve the previous command before starting charging")
        async with self.command_lock:
            vehicle = self.vehicles[key]
            sequence = uuid.uuid4().hex + "1234"
            self.journal[key] = {"state": "submitting", "sequence": sequence,
                                 "action": "start" if enabled else "stop"}
            await self.store.async_save(self.journal)
            try:
                await self.client.charge(vehicle.identifier, enabled=enabled,
                                         pin=self.entry.data.get("pin", ""), sequence=sequence)
                self.journal[key]["state"] = "accepted"
                await self.store.async_save(self.journal)
                for _ in range(12):
                    await asyncio.sleep(5)
                    state = charging_result(await self.client.charge_result(vehicle.identifier, sequence))
                    self.journal[key]["state"] = state
                    await self.store.async_save(self.journal)
                    if state == "failed":
                        raise HomeAssistantError("GWM reported that the charging command failed")
                    if state == "completed":
                        break
                else:
                    raise HomeAssistantError("Charging result is pending; the command will not be resent")
            except (GwmClientError, ValueError):
                self.journal[key]["state"] = "unknown"
                await self.store.async_save(self.journal)
                raise HomeAssistantError("Charging outcome is unknown; the command was not retried") from None
            finally:
                await self.async_request_refresh()
