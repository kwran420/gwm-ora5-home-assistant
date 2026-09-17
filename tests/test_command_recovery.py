"""Late command recovery. Fake transport only; never sends real controls."""
import asyncio
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


@unittest.skipUnless(importlib.util.find_spec('homeassistant'), 'Requires HA runtime')
class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def make_coordinator(self, action='stop'):
        from custom_components.gwm_ora5.coordinator import OraCoordinator
        c = object.__new__(OraCoordinator)
        c.command_lock = asyncio.Lock()
        c.journal = {'v': {'state':'unknown', 'sequence':'synthetic-sequence',
            'action':action, 'remote_type':'0x01', 'expected':{'charging':action=='start'},
            'submitted_at_ms':1999999900000}}
        c.client = SimpleNamespace(charge_result=AsyncMock(return_value=[]), send_control=AsyncMock())
        c.store = SimpleNamespace(async_save=AsyncMock())
        return c

    async def read(self, c, now=2000000000, **values):
        state = {'charging':False, 'vehicle_updated_ms':now*1000, **values}
        with patch('custom_components.gwm_ora5.coordinator.time.time', return_value=now):
            await c._reconcile_command('v', 'synthetic-vehicle', state)

    async def test_unknown_stop_checks_same_sequence_and_recovers_late_result(self):
        c = self.make_coordinator()
        c.client.charge_result.return_value = [SimpleNamespace(remote_type='0x01', result_code='0')]
        await self.read(c, vehicle_updated_ms=1900000000000)
        c.client.charge_result.assert_awaited_once_with('synthetic-vehicle', 'synthetic-sequence')
        self.assertEqual(c.journal['v']['state'], 'completed')
        self.assertEqual(c.journal['v']['resolution'], 'remote_result_and_feedback')
        c.client.send_control.assert_not_called()

    async def test_unknown_start_requires_result_and_feedback(self):
        c = self.make_coordinator('start')
        c.client.charge_result.return_value = [SimpleNamespace(remote_type='0x01', result_code='0')]
        await self.read(c)
        self.assertEqual(c.journal['v']['state'], 'awaiting_feedback')
        await self.read(c, now=2000000030, charging=True)
        self.assertEqual(c.journal['v']['state'], 'completed')
        c.client.send_control.assert_not_called()

    async def test_fresh_state_alone_never_resolves_unknown_start(self):
        c = self.make_coordinator('start')
        for now in [2000000000, 2000000030, 2000000100]:
            await self.read(c, now=now, charging=True)
        self.assertEqual(c.journal['v']['state'], 'unknown')
        c.client.send_control.assert_not_called()

    async def test_repeated_fresh_off_can_resolve_stop_without_result(self):
        c = self.make_coordinator()
        await self.read(c)
        self.assertEqual(c.journal['v']['state'], 'unknown')
        await self.read(c, now=2000000030)
        self.assertEqual(c.journal['v']['state'], 'completed')
        self.assertEqual(c.journal['v']['resolution'], 'observed_stopped')

    async def test_legacy_stop_also_requires_repeated_fresh_off(self):
        c = self.make_coordinator()
        del c.journal['v']['submitted_at_ms']
        await self.read(c, vehicle_updated_ms=1900000000000)
        self.assertEqual(c.journal['v']['state'], 'unknown')
        await self.read(c)
        await self.read(c, now=2000000030)
        self.assertEqual(c.journal['v']['state'], 'completed')

    async def test_normal_two_minute_poll_interval_can_confirm_off(self):
        c = self.make_coordinator()
        await self.read(c)
        await self.read(c, now=2000000125)
        self.assertEqual(c.journal['v']['state'], 'completed')

    async def test_cached_pre_command_future_and_invalid_snapshots_do_not_clear_stop(self):
        for stamp in [1900000000000, 1999999899999, 2000000100000, float('nan'), None, True]:
            c = self.make_coordinator()
            await self.read(c, vehicle_updated_ms=stamp)
            await self.read(c, now=2000000030, vehicle_updated_ms=stamp)
            self.assertEqual(c.journal['v']['state'], 'unknown')

    async def test_unreliable_off_feedback_breaks_observation_window(self):
        c = self.make_coordinator()
        await self.read(c)
        await self.read(c, now=2000000010, charging=None)
        await self.read(c, now=2000000030)
        self.assertEqual(c.journal['v']['state'], 'unknown')
        await self.read(c, now=2000000060)
        self.assertEqual(c.journal['v']['state'], 'completed')

    async def test_old_observation_window_must_restart(self):
        c = self.make_coordinator()
        await self.read(c)
        await self.read(c, now=2000000500)
        self.assertEqual(c.journal['v']['state'], 'unknown')

    async def test_other_controls_do_not_use_charge_stop_recovery(self):
        c = self.make_coordinator()
        c.journal['v']['action'] = 'windows_close'
        for now in [2000000000, 2000000030]:
            await self.read(c, now=now)
        self.assertEqual(c.journal['v']['state'], 'unknown')

    async def test_transient_result_failure_keeps_record_and_telemetry_usable(self):
        from gwm_client import GwmNetworkError
        c = self.make_coordinator()
        c.client.charge_result.side_effect = GwmNetworkError()
        await self.read(c, vehicle_updated_ms=1900000000000)
        self.assertEqual(c.journal['v']['state'], 'unknown')
        c.store.async_save.assert_not_called()

    async def test_authentication_failure_still_reaches_session_refresh(self):
        from gwm_client import GwmAuthenticationError
        c = self.make_coordinator()
        c.client.charge_result.side_effect = GwmAuthenticationError()
        with self.assertRaises(GwmAuthenticationError):
            await self.read(c)

    async def test_rejected_result_resolves_as_failed(self):
        c = self.make_coordinator()
        c.client.charge_result.return_value = [SimpleNamespace(remote_type='0x01', result_code='1014')]
        await self.read(c)
        self.assertEqual(c.journal['v']['state'], 'failed')

    async def test_result_reader_cannot_overwrite_newer_command(self):
        c = self.make_coordinator()
        newer = {'state':'pending', 'sequence':'newer-synthetic'}
        async def late_result(*args):
            c.journal['v'] = newer
            return [SimpleNamespace(remote_type='0x01', result_code='0')]
        c.client.charge_result.side_effect = late_result
        await self.read(c)
        self.assertIs(c.journal['v'], newer)
        self.assertEqual(newer['state'], 'pending')
        c.store.async_save.assert_not_called()

    async def test_active_command_owns_its_result_polling(self):
        c = self.make_coordinator()
        async with c.command_lock:
            await self.read(c)
        c.client.charge_result.assert_not_called()

    async def test_blocked_start_is_explicitly_not_transmitted(self):
        from custom_components.gwm_ora5.coordinator import CommandNotSent
        c = self.make_coordinator()
        c.entry = SimpleNamespace(options={}, data={'enable_commands':True})
        c.vehicles = {'v':SimpleNamespace(identifier='synthetic')}
        c.last_update_success = True
        c.data = {'v':{'plugged_in':True}}
        with self.assertRaises(CommandNotSent) as caught:
            await c.charge('v', True)
        self.assertTrue(caught.exception.command_not_sent)
        c.client.send_control.assert_not_called()
        c.store.async_save.assert_not_called()

    async def test_vehicle_read_survives_command_result_network_failure(self):
        from gwm_client import GwmNetworkError
        c = self.make_coordinator()
        c.client.acquire_vehicles = AsyncMock(return_value=[SimpleNamespace(identifier='synthetic')])
        c.client.get_last_status = AsyncMock(return_value=object())
        c.client.charge_result.side_effect = GwmNetworkError()
        c.detail_polled = {'v':10**12}
        c.detail_cache = {}
        with patch('custom_components.gwm_ora5.coordinator.is_ora5', return_value=True), \
             patch('custom_components.gwm_ora5.coordinator.vehicle_key', return_value='v'), \
             patch('custom_components.gwm_ora5.coordinator.telemetry', return_value={'charging':False}):
            values = await c._read_vehicles()
        self.assertFalse(values['v']['charging'])
        self.assertEqual(values['v']['command_status'], 'unknown')
