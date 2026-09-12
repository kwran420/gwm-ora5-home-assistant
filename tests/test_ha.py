"""Home Assistant runtime checks; skipped in client-only environments."""
import importlib.util
import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HAS_HA = importlib.util.find_spec("homeassistant") is not None


@unittest.skipUnless(HAS_HA, "Run in a Home Assistant Python environment")
class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
    def command_coordinator(self):
        from custom_components.gwm_ora5.coordinator import OraCoordinator
        from gwm_client.models import CloudVehicleStatus, CloudStatusItem
        c = object.__new__(OraCoordinator)
        c.entry = SimpleNamespace(options={'enable_vehicle_controls': True}, data={'pin': '123456'})
        c.vehicles = {'vehicle': SimpleNamespace(identifier=object())}
        c.command_lock = asyncio.Lock()
        c.journal = {}
        c.store = SimpleNamespace(async_save=AsyncMock())
        c.last_update_success = True
        c.data = {'vehicle': {}}
        c.client = SimpleNamespace(send_control=AsyncMock(),
            refresh_current_anz_session=AsyncMock(return_value=SimpleNamespace(state={})),
            charge_result=AsyncMock(return_value=[SimpleNamespace(remote_type='0x04', result_code='0')]),
            get_last_status=AsyncMock(return_value=CloudVehicleStatus(items=(CloudStatusItem('2202001', '1'),))))
        c._save_auth = lambda state: None
        c.async_request_refresh = AsyncMock()
        return c

    async def test_explicit_auth_rejection_refreshes_and_retries_once(self):
        from gwm_client import GwmApiError
        c = self.command_coordinator()
        c.client.send_control.side_effect = [GwmApiError(api_code='550004'), None]
        with patch('custom_components.gwm_ora5.coordinator.asyncio.sleep', new=AsyncMock()), \
             patch('custom_components.gwm_ora5.coordinator.make_credentials'), \
             patch('custom_components.gwm_ora5.coordinator.decode_state'):
            await c.control('vehicle', 'climate_on')
        self.assertEqual(c.client.send_control.await_count, 2)
        self.assertEqual(c.client.refresh_current_anz_session.await_count, 1)
        self.assertEqual(c.journal['vehicle']['state'], 'completed')

    async def test_network_failure_does_not_resend_control(self):
        from gwm_client import GwmNetworkError
        from homeassistant.exceptions import HomeAssistantError
        c = self.command_coordinator()
        c.client.send_control.side_effect = GwmNetworkError()
        with self.assertRaises(HomeAssistantError):
            await c.control('vehicle', 'climate_on')
        c.client.send_control.assert_awaited_once()
        c.client.refresh_current_anz_session.assert_not_called()
        self.assertEqual(c.journal['vehicle']['state'], 'unknown')

    async def test_lock_reports_actual_state_and_routes_commands(self):
        from custom_components.gwm_ora5.lock import OraLock
        coordinator = SimpleNamespace(entry=SimpleNamespace(entry_id='synthetic', options={'enable_vehicle_controls': True}),
            data={'synthetic': {'unlocked': False}}, last_update_success=True, control=AsyncMock())
        entity = OraLock(coordinator, 'synthetic', 'door_lock', 'Door lock')
        self.assertTrue(entity.is_locked)
        await entity.async_unlock()
        coordinator.control.assert_awaited_once_with('synthetic', 'unlock')
        self.assertTrue(entity.is_locked)  # No optimistic state change.

    async def test_alarm_button_is_disabled_by_default(self):
        from custom_components.gwm_ora5.button import OraControlButton
        coordinator = SimpleNamespace(entry=SimpleNamespace(entry_id='synthetic', options={}), data={})
        entity = OraControlButton(coordinator, 'synthetic', 'horn', 'Sound loud alarm')
        self.assertFalse(entity.entity_registry_enabled_default)

    async def test_acknowledgement_without_vehicle_feedback_is_not_completed(self):
        from custom_components.gwm_ora5.coordinator import OraCoordinator
        from gwm_client.models import CloudVehicleStatus, CloudStatusItem
        from homeassistant.exceptions import HomeAssistantError
        c = object.__new__(OraCoordinator)
        c.entry = SimpleNamespace(options={'enable_vehicle_controls': True}, data={'pin': '123456'})
        c.vehicles = {'vehicle': SimpleNamespace(identifier=object())}
        c.command_lock = asyncio.Lock()
        c.journal = {}
        c.store = SimpleNamespace(async_save=AsyncMock())
        c.last_update_success = True
        c.client = SimpleNamespace(send_control=AsyncMock(),
            charge_result=AsyncMock(return_value=[SimpleNamespace(remote_type='0x04', result_code='0')]),
            get_last_status=AsyncMock(return_value=CloudVehicleStatus(items=(CloudStatusItem('2202001', '0'),))))
        c.async_request_refresh = AsyncMock()
        with patch('custom_components.gwm_ora5.coordinator.asyncio.sleep', new=AsyncMock()):
            with self.assertRaises(HomeAssistantError):
                await c.control('vehicle', 'climate_on')
        self.assertEqual(c.journal['vehicle']['state'], 'awaiting_feedback')
        c.client.send_control.assert_awaited_once()
    async def test_buttons_construct_and_send_the_requested_state(self):
        from custom_components.gwm_ora5.button import OraChargeButton
        coordinator = SimpleNamespace(
            entry=SimpleNamespace(entry_id="synthetic", data={"enable_commands": True}),
            data={"synthetic": {}}, last_update_success=True, charge=AsyncMock(),
        )
        for requested in (True, False):
            button = OraChargeButton(coordinator, "synthetic", requested)
            self.assertTrue(button.available)
            await button.async_press()
            coordinator.charge.assert_awaited_with("synthetic", requested)

    async def test_form_selectors_and_pin_validation(self):
        from custom_components.gwm_ora5.config_flow import ConfigFlow
        flow = ConfigFlow()
        result = await flow.async_step_user()
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        result = await flow.async_step_user({"pin": "123", "enable_commands": True})
        self.assertEqual(result["errors"], {"pin": "invalid_pin"})
        result = await flow.async_step_verify()
        self.assertEqual(result["step_id"], "verify")

    async def test_unknown_telemetry_does_not_become_charging(self):
        from custom_components.gwm_ora5.binary_sensor import OraBinarySensor
        coordinator = SimpleNamespace(entry=SimpleNamespace(entry_id="synthetic"), data={}, last_update_success=True)
        entity = OraBinarySensor(coordinator, "synthetic", "charging", "Charging")
        self.assertIsNone(entity.is_on)
        self.assertFalse(entity.available)

    async def test_diagnostics_never_dump_entry_data(self):
        from custom_components.gwm_ora5.diagnostics import async_get_config_entry_diagnostics
        entry = SimpleNamespace(
            data={"country": "AU", "password": "SECRET-SENTINEL", "pin": "654321", "auth_state": {"access_token": "SECRET-SENTINEL"}},
            runtime_data=SimpleNamespace(vehicles={"PRIVATE-ID": object()}, last_update_success=True,
                                         journal={"PRIVATE-ID": {"state": "accepted", "sequence": "PRIVATE-SEQ"}}),
        )
        result = await async_get_config_entry_diagnostics(None, entry)
        self.assertNotIn("SECRET-SENTINEL", str(result))
        self.assertNotIn("PRIVATE-ID", str(result))
        self.assertNotIn("PRIVATE-SEQ", str(result))

    async def test_setup_closes_client_if_initialization_fails(self):
        from homeassistant.exceptions import ConfigEntryAuthFailed
        from custom_components.gwm_ora5 import async_setup_entry
        coordinator = SimpleNamespace(initialize=AsyncMock(side_effect=ConfigEntryAuthFailed()),
                                      client=SimpleNamespace(aclose=AsyncMock()))
        with patch("custom_components.gwm_ora5.OraCoordinator", return_value=coordinator):
            with self.assertRaises(ConfigEntryAuthFailed):
                await async_setup_entry(None, None)
        coordinator.client.aclose.assert_awaited_once()
