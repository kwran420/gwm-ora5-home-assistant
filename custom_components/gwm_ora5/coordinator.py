"""Read polling and serialized, journaled charging commands."""
import asyncio
import logging
import uuid
import time
import math
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from gwm_client import GwmAuthenticationError, GwmClientError
from gwm_client.anz_auth import AnzAuthenticated

from .api import (charging_result, decode_state, encode_state, is_ora5,
                  make_credentials, new_client, telemetry, vehicle_key)
from .const import DOMAIN, POLL_SECONDS
from .controls import command_body, expected_state

LOGGER = logging.getLogger(__name__)
AUTH_CODES = {"607501", "550004", "551004", "551006", "607124", "-101"}


class CommandNotSent(HomeAssistantError):
    """A local precondition rejected the action before journal or transmission."""
    command_not_sent = True


class OraCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, LOGGER, name=DOMAIN, config_entry=entry,
                         update_interval=timedelta(seconds=POLL_SECONDS))
        self.entry = entry
        self.client = new_client()
        self.vehicles = {}
        self.command_lock = asyncio.Lock()
        self.journal = {}
        self.detail_cache = {}
        self.detail_polled = {}
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
            if time.monotonic() - self.detail_polled.get(key, -1000) > 900:
                self.detail_polled[key] = time.monotonic()
                try:
                    self.detail_cache[key] = await self.client.charging_details(vehicle.identifier)
                except (GwmClientError, ValueError):
                    self.detail_cache[key] = {}
                try:
                    self.detail_cache[key].update(await self.client.remote_history(vehicle.identifier))
                except (GwmClientError, ValueError):
                    pass  # Optional history must not hide live vehicle telemetry.
            values[key].update(self.detail_cache.get(key, {}))
            await self._reconcile_command(key, vehicle.identifier, values[key])
            record = self.journal.get(key, {})
            values[key]["command_status"] = record.get("state", "idle")
            values[key]["command_action"] = record.get("action")
            values[key]["command_expected_charging"] = record.get("expected", {}).get("charging")
            values[key]["command_resolution"] = record.get("resolution")
        return values

    async def _reconcile_command(self, key, identifier, values):
        """Resolve late outcomes by reading, including requests with unknown results.

        Only an unresolved charging Stop may settle from fresh, repeated off
        telemetry without an OEM result. Unknown Starts and other controls
        continue to require their scoped result and expected-state feedback.
        """
        if self.command_lock.locked():
            return
        record = self.journal.get(key)
        if not record or record.get("state") not in {"accepted", "submitting", "pending", "unknown", "awaiting_feedback"}:
            return
        before = dict(record)
        if record.get("state") != "awaiting_feedback" and record.get("sequence"):
            try:
                items = await self.client.charge_result(identifier, record["sequence"])
            except (GwmClientError, ValueError) as error:
                if isinstance(error, GwmAuthenticationError) or getattr(error, "api_code", None) in AUTH_CODES:
                    raise
                # A failed result read must not hide successfully read telemetry.
                items = None
            if self.journal.get(key) is not record or self.command_lock.locked():
                return  # A newer command owns the journal now.
            if items is not None:
                state = charging_result(items, record.get("remote_type", "0x01"))
                if state == "completed":
                    record["state"] = "awaiting_feedback" if record.get("expected") else "completed"
                elif state == "failed":
                    record["state"] = "failed"

        expected = record.get("expected", {})
        if record.get("state") == "awaiting_feedback" and expected and all(values.get(k) == v for k, v in expected.items()):
            record["state"] = "completed"
            record["resolution"] = "remote_result_and_feedback"
        elif (record.get("state") in {"unknown", "pending", "accepted", "submitting"}
              and record.get("action") == "stop" and record.get("remote_type") == "0x01"
              and expected == {"charging": False}):
            now = time.time()
            stamp = values.get("vehicle_updated_ms")
            submitted = record.get("submitted_at_ms")
            fresh_off = (values.get("charging") is False
                and type(stamp) in (int, float) and math.isfinite(stamp)
                and 0 <= now-stamp/1000 <= 120
                and (submitted is None or (type(submitted) in (int, float)
                     and math.isfinite(submitted) and stamp >= submitted)))
            if fresh_off:
                since = record.setdefault("stopped_observed_at", now)
                if type(since) in (int, float) and 15 <= now-since <= 300:
                    record["state"] = "completed"
                    record["resolution"] = "observed_stopped"
                elif type(since) not in (int, float) or not 0 <= now-since <= 300:
                    record["stopped_observed_at"] = now
            else:
                record.pop("stopped_observed_at", None)
        if record != before:
            await self.store.async_save(self.journal)

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
                except GwmClientError as refresh_error:
                    if (isinstance(refresh_error, GwmAuthenticationError)
                        or getattr(refresh_error, "api_code", None) in AUTH_CODES):
                        raise ConfigEntryAuthFailed("GWM session needs sign-in") from None
                    # A network/server failure is not evidence that credentials
                    # were rejected. Keep normal coordinator retries available.
                    raise UpdateFailed("GWM session refresh is temporarily unavailable") from None
            raise UpdateFailed("GWM cloud data is unavailable") from None

    async def charge(self, key, enabled):
        return await self._command(key, enabled=enabled)

    async def control(self, key, action, **settings):
        return await self._command(key, action=action, settings=settings)

    async def _command(self, key, *, enabled=None, action=None, settings=None):
        vehicle_control = action is not None
        options = dict(self.entry.options)
        if vehicle_control:
            if not self.entry.options.get("enable_vehicle_controls", False):
                raise CommandNotSent("Enable vehicle controls in integration options first")
            from .controls import comfort_settings
            try:
                options.update(comfort_settings(action, settings or {}))
            except ValueError as error:
                raise CommandNotSent(str(error)) from None
            instruction, body = command_body(action,
                temperature=options.get("climate_temperature", 25),
                duration=options.get("control_duration", 5),
                level=options.get("seat_level", 1))
        else:
            instruction, body = "0x01", {"switchOrder": "1" if enabled else "2"}
        if not vehicle_control and not self.entry.data.get("enable_commands"):
            raise CommandNotSent("Enable charging commands in integration configuration first")
        if key not in self.vehicles:
            raise CommandNotSent("ORA 5 is unavailable")
        if self.command_lock.locked():
            raise CommandNotSent("A vehicle command is still running")
        if action == 'cabin_clean' and (self.data or {}).get(key, {}).get('plugged_in') is not False:
            raise CommandNotSent("Unplug the charging cable before refreshing cabin air")
        if enabled and not vehicle_control:
            if not self.last_update_success or not self.data or self.data.get(key, {}).get("plugged_in") is not True:
                raise CommandNotSent("A connected charging cable has not been confirmed")
        is_stop = (not vehicle_control and enabled is False) or (vehicle_control and (action.endswith("_off") or action in {"lock", "windows_close", "boot_close"}))
        if not is_stop and self.journal.get(key, {}).get("state") in {"submitting", "accepted", "pending", "unknown", "awaiting_feedback"}:
            raise CommandNotSent("Resolve the previous command before starting another operation")
        if not self.last_update_success and not is_stop:
            raise CommandNotSent("Fresh vehicle telemetry is required")
        async with self.command_lock:
            vehicle = self.vehicles[key]
            sequence = uuid.uuid4().hex + "1234"
            self.journal[key] = {"state": "submitting", "sequence": sequence,
                                 "submitted_at_ms": int(time.time()*1000),
                                 "action": action if vehicle_control else "start" if enabled else "stop",
                                 "remote_type": instruction,
                                 "expected": expected_state(action, level=options.get("seat_level", 1)) if vehicle_control else {"charging": enabled}}
            await self.store.async_save(self.journal)
            try:
                try:
                    await self.client.send_control(vehicle.identifier, instruction=instruction, body=body,
                                                   pin=self.entry.data.get("pin", ""), sequence=sequence)
                except GwmClientError as error:
                    # A definitive auth rejection occurred before acceptance.
                    # Refresh once; never retry timeouts or ambiguous outcomes.
                    if getattr(error, "api_code", None) not in AUTH_CODES:
                        raise
                    result = await self.client.refresh_current_anz_session(
                        make_credentials(self.entry.data), decode_state(self.entry.data.get("auth_state")))
                    self._save_auth(result.state)
                    await self.client.send_control(vehicle.identifier, instruction=instruction, body=body,
                                                   pin=self.entry.data.get("pin", ""), sequence=sequence)
                self.journal[key]["state"] = "accepted"
                await self.store.async_save(self.journal)
                for _ in range(12):
                    await asyncio.sleep(5)
                    state = charging_result(await self.client.charge_result(vehicle.identifier, sequence), instruction)
                    self.journal[key]["state"] = state
                    await self.store.async_save(self.journal)
                    if state == "failed":
                        raise HomeAssistantError("GWM reported that the vehicle command failed")
                    if state == "completed":
                        self.journal[key]["state"] = "awaiting_feedback"
                        await self.store.async_save(self.journal)
                        for _ in range(7):
                            values = telemetry(await self.client.get_last_status(vehicle.identifier))
                            if all(values.get(k) == v for k, v in self.journal[key]["expected"].items()):
                                self.journal[key]["state"] = "completed"
                                await self.store.async_save(self.journal)
                                break
                            await asyncio.sleep(5)
                        else:
                            raise HomeAssistantError("Cloud accepted the command, but the vehicle state has not confirmed it")
                        break
                else:
                    raise HomeAssistantError("Vehicle result is pending; the command will not be resent")
            except (GwmClientError, ValueError):
                self.journal[key]["state"] = "unknown"
                await self.store.async_save(self.journal)
                raise HomeAssistantError("Vehicle outcome is unknown; the command was not blindly retried") from None
            finally:
                await self.async_request_refresh()
