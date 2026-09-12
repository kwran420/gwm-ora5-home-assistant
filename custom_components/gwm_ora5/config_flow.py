"""Private account setup and email verification through Home Assistant."""
import hashlib
import uuid

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from gwm_client import GwmClientError
from gwm_client.anz_auth import AnzAuthenticated, AnzVerificationRequired

from .api import decode_state, encode_state, is_ora5, make_credentials, new_client, reclaim_state
from .const import DOMAIN, NAME


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()

    def __init__(self):
        self._data = {}
        self._state = None
        self._reauth_entry = None

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            pin = user_input.get("pin", "")
            if pin and (len(pin) != 6 or not pin.isascii() or not pin.isdigit()):
                errors["pin"] = "invalid_pin"
            elif user_input.get("enable_commands") and not pin:
                errors["pin"] = "invalid_pin"
            else:
                self._data.update(user_input)
                self._data.setdefault("device_id", uuid.uuid4().hex)
                self._data["account"] = self._data["account"].strip()
                unique = hashlib.sha256((self._data["country"] + ":" + self._data["account"].casefold()).encode()).hexdigest()
                await self.async_set_unique_id(unique)
                if self._reauth_entry is None:
                    self._abort_if_unique_id_configured()
                elif unique != self._reauth_entry.unique_id:
                    return self.async_abort(reason="account_mismatch")
                self._state = reclaim_state(decode_state(self._data.get("auth_state")))
                return await self._authenticate()
        return self.async_show_form(step_id="user", errors=errors, data_schema=vol.Schema({
            vol.Required("country", default=self._data.get("country", "AU")): vol.In(["AU", "NZ"]),
            vol.Required("account", default=self._data.get("account", "")): str,
            vol.Required("password"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional("pin"): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Required("enable_commands", default=self._data.get("enable_commands", False)): bool,
        }))

    async def _authenticate(self, code=None):
        try:
            async with new_client() as client:
                result = await client.authenticate_anz(
                    make_credentials(self._data), state=self._state,
                    verification_code=code, allow_session_reclaim=True,
                )
                self._state = result.state
                if isinstance(result, AnzVerificationRequired):
                    return await self.async_step_verify()
                if not isinstance(result, AnzAuthenticated):
                    return self.async_abort(reason="cannot_authenticate")
                vehicles = await client.acquire_vehicles()
                if not any(is_ora5(vehicle) for vehicle in vehicles):
                    return self.async_abort(reason="no_ora5")
                self._data["auth_state"] = encode_state(result.state)
        except (GwmClientError, ValueError):
            return self.async_show_form(step_id="retry", data_schema=vol.Schema({}), errors={"base": "cannot_connect"})
        if self._reauth_entry is not None:
            return self.async_update_reload_and_abort(self._reauth_entry, data_updates=self._data)
        return self.async_create_entry(title=NAME, data=self._data)

    async def async_step_verify(self, user_input=None):
        if user_input is not None:
            return await self._authenticate(user_input["code"].strip())
        return self.async_show_form(step_id="verify", data_schema=vol.Schema({vol.Required("code"): str}))

    async def async_step_retry(self, user_input=None):
        return await self.async_step_user()

    async def async_step_reauth(self, entry_data):
        self._reauth_entry = self._get_reauth_entry()
        self._data = dict(entry_data)
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None):
        self._reauth_entry = self._get_reconfigure_entry()
        self._data = dict(self._reauth_entry.data)
        return await self.async_step_user(user_input)


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get('enable_vehicle_controls') and not self.config_entry.data.get('pin'):
                errors['base'] = 'pin_required'
            else:
                return self.async_create_entry(title='', data=user_input)
        options = self.config_entry.options
        return self.async_show_form(step_id='init', errors=errors, data_schema=vol.Schema({
            vol.Required('enable_vehicle_controls', default=options.get('enable_vehicle_controls', False)): bool,
            vol.Required('climate_temperature', default=options.get('climate_temperature', 25)): vol.All(vol.Coerce(int), vol.Range(min=16, max=32)),
            vol.Required('control_duration', default=options.get('control_duration', 5)): vol.All(vol.Coerce(int), vol.Range(min=5, max=30)),
            vol.Required('seat_level', default=options.get('seat_level', 1)): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
        }))
