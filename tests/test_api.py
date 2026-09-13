"""Synthetic protocol tests. Never load local account data."""
import importlib.util
import json
import ssl
import unittest
from pathlib import Path

from gwm_client import GwmClientConfig, GwmSession, Region, RemoteCommandResultItem, VehicleIdentifier
from gwm_client._protocol import _TransportResponse
from gwm_client.models import CloudStatusItem, CloudVehicleStatus

spec = importlib.util.spec_from_file_location("ora5_api", Path(__file__).parents[1] / "custom_components/gwm_ora5/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
spec_controls = importlib.util.spec_from_file_location("ora5_controls", Path(__file__).parents[1] / "custom_components/gwm_ora5/controls.py")
controls = importlib.util.module_from_spec(spec_controls)
spec_controls.loader.exec_module(controls)


class Transport:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    async def execute(self, request, **kwargs):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return _TransportResponse(200, {"content-type": "application/json"}, json.dumps(response).encode())

    async def aclose(self):
        pass


def client(transport):
    return api.OraClient(
        GwmClientConfig(Region.ANZ, anz_authentication_method="current_v2"),
        GwmSession(country="AU", device_id="a" * 32, access_token="SYNTHETIC-TOKEN",
                   gw_id="SYNTHETIC-ID", app_ssl_context=ssl.create_default_context()),
        transport=transport,
    )


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_history_retains_only_safe_summary(self):
        transport = Transport([{'code': '000000', 'data': {'total': 9, 'list': [
            {'createdAt': 1789269000000, 'remoteType': '0x01', 'resultCode': '0',
             'vin': 'PRIVATE-SENTINEL', 'nick': 'PRIVATE-SENTINEL', 'params': 'PRIVATE-SENTINEL'},
            {'createdAt': 1789269100000, 'remoteType': '0x04', 'resultCode': '1014'},
            {'createdAt': True, 'remoteType': '0x05', 'resultCode': '0'}]}}])
        async with client(transport) as c:
            result = await c.remote_history(VehicleIdentifier('SYNTHETIC-VEHICLE'))
        self.assertNotIn('PRIVATE-SENTINEL', str(result))
        self.assertEqual(result['remote_history_last_ms'], 1789269100000)
        self.assertEqual(result['remote_history_summary']['instruction'], '0x04')
        self.assertEqual(result['remote_history_summary']['provider_result_code'], '1014')
        self.assertEqual(result['remote_history_summary']['record_count'], 9)
        self.assertEqual(json.loads(transport.requests[0].body)['pageSize'], 3)
        self.assertTrue(transport.requests[0].url.endswith('/vehicle/getWeyVrcHistory'))

    async def test_remote_history_empty_and_malformed_responses(self):
        from gwm_client import GwmClientError
        for value in (None, {}, {'list': 'bad'}):
            async with client(Transport([{'code':'000000', 'data':value}])) as c:
                with self.assertRaises(GwmClientError):
                    await c.remote_history(VehicleIdentifier('SYNTHETIC-VEHICLE'))
        async with client(Transport([{'code':'000000', 'data':{'total':0, 'list':[]}}])) as c:
            result = await c.remote_history(VehicleIdentifier('SYNTHETIC-VEHICLE'))
        self.assertIsNone(result['remote_history_last_ms'])

    def test_comfort_settings_are_action_specific_and_strict(self):
        self.assertEqual(controls.comfort_settings('climate_on', {'temperature':24,'duration':10}),
                         {'climate_temperature':24,'control_duration':10})
        self.assertEqual(controls.comfort_settings('seat_vent_on', {'level':3}), {'seat_level':3})
        for action, settings in [('horn',{'duration':5}), ('climate_on',{'level':2}),
            ('seat_heat_on',{'temperature':24}), ('seat_vent_on',{'level':True}),
            ('climate_on',{'temperature':24.5}), ('climate_on',{'duration':31}),
            ('steering_on',{'raw_body':'unsafe'})]:
            with self.assertRaises(ValueError):
                controls.comfort_settings(action, settings)

    async def test_both_charge_actions_have_exact_payload(self):
        for enabled, order in [(True, "1"), (False, "2")]:
            transport = Transport([{"code": "000000"}])
            async with client(transport) as api_client:
                sequence = await api_client.charge(VehicleIdentifier("SYNTHETIC-VEHICLE"), enabled=enabled, pin="123456")
            request = transport.requests[0]
            body = json.loads(request.body)
            self.assertEqual(body["instructions"], {"0x01": {"switchOrder": order}})
            self.assertEqual(body["securityPassword"], "e10adc3949ba59abbe56e057f20f883e")
            self.assertEqual(body["seqNo"], sequence)
            self.assertEqual(body["type"], 2)
            self.assertTrue(request.url.endswith("/vehicle/T5/sendCmd"))
            self.assertEqual(len(transport.requests), 1)

    async def test_poll_uses_native_signing_and_keeps_sequence(self):
        transport = Transport([{"code": "000000", "data": [{"hwCommandId": "DIFFERENT-HARDWARE-ID", "remoteType": "0x01", "resultCode": "0"}]}])
        async with client(transport) as api_client:
            result = await api_client.charge_result(VehicleIdentifier("SYNTHETIC-VEHICLE"), "b" * 32 + "1234")
        self.assertEqual(api.charging_result(result), "completed")
        self.assertEqual(len(transport.requests[0].headers["bt-auth-nonce"]), 16)
        self.assertTrue(transport.requests[0].url.endswith("seqNo=" + "b" * 32 + "1234"))
        self.assertEqual(transport.requests[0].headers["vin"], "SYNTHETIC-VEHICLE")

    async def test_failed_transport_does_not_resend(self):
        transport = Transport([TimeoutError()])
        async with client(transport) as api_client:
            with self.assertRaises(Exception):
                await api_client.charge(VehicleIdentifier("SYNTHETIC-VEHICLE"), enabled=False, pin="123456")
        self.assertEqual(len(transport.requests), 1)

    async def test_invalid_pin_and_boolean_fail_before_io(self):
        transport = Transport([])
        async with client(transport) as api_client:
            for enabled, pin in [(1, "123456"), (False, ""), (True, "12345"), (False, "abcdef")]:
                with self.assertRaises(ValueError):
                    await api_client.charge(VehicleIdentifier("SYNTHETIC-VEHICLE"), enabled=enabled, pin=pin)
        self.assertEqual(transport.requests, [])

    def test_unrelated_and_duplicate_results_cannot_report_success(self):
        success = RemoteCommandResultItem(remote_type="0x01", result_code="0")
        other = RemoteCommandResultItem(remote_type="0x04", result_code="0")
        self.assertEqual(api.charging_result((other,)), "pending")
        self.assertEqual(api.charging_result((success, success)), "pending")
        self.assertEqual(api.charging_result((RemoteCommandResultItem(remote_type="0x01", result_code="10"),)), "failed")

    def test_credentials_preserve_password(self):
        credentials = api.make_credentials({"account": "user@example.invalid", "password": "synthetic-password!", "country": "AU", "device_id": "a" * 32})
        self.assertEqual(credentials.password, "synthetic-password!")

    def test_climate_off_matches_anz_app(self):
        code, body = controls.command_body('climate_off')
        self.assertEqual(code, '0x04')
        self.assertEqual(body, {'airConditioner': {'switchOrder': '2', 'operationTime': '0'}})

    def test_seat_payload_does_not_address_nonexistent_rows(self):
        _, body = controls.command_body('seat_heat_on', level=2)
        self.assertEqual(body['seat']['leftFront'], '2')
        self.assertEqual(body['seat']['leftBack'], '0')
        self.assertNotIn('leftThirdRow', body['seat'])

    def test_controls_reject_unknown_actions_and_bad_parameters(self):
        for args in [dict(action='engine_start'), dict(action='climate_on', duration=0),
                     dict(action='seat_heat_on', level=4), dict(action='climate_on', temperature=True)]:
            with self.assertRaises(ValueError):
                controls.command_body(**args)

    def test_result_is_scoped_to_requested_control(self):
        result = (RemoteCommandResultItem(remote_type='0x04', result_code='0'),)
        self.assertEqual(api.charging_result(result, '0x04'), 'completed')
        self.assertEqual(api.charging_result(result, '0x05'), 'pending')

    def test_extended_telemetry_decodes_zero_and_missing_correctly(self):
        status = CloudVehicleStatus(items=(CloudStatusItem('2208001', '0'),
            CloudStatusItem('2206001', '1'), CloudStatusItem('2101001', '250.5'),
            CloudStatusItem('2220001', '2'), CloudStatusItem('2013023', '0')))
        result = api.telemetry(status)
        self.assertIs(result['unlocked'], False)
        self.assertIs(result['boot_open'], True)
        self.assertEqual(result['tyre_pressure_front_left'], 250.5)
        self.assertEqual(result['seat_heat_driver'], 2)
        self.assertIsNone(result['window_front_left'])
        self.assertEqual(result['charging_mode_code'], 0)

    def test_unknown_or_invalid_signal_values_remain_unknown(self):
        result = api.telemetry(CloudVehicleStatus(items=(CloudStatusItem('2208001', '255'),
            CloudStatusItem('2101001', 'nan'), CloudStatusItem('2220001', '255'))))
        self.assertIsNone(result['unlocked'])
        self.assertIsNone(result['tyre_pressure_front_left'])
        self.assertIsNone(result['seat_heat_driver'])

    async def test_charging_details_accept_null_schedule_and_redact_identifiers(self):
        transport = Transport([
            {'code': '000000', 'data': {'chargePlanList': [{'planType': '-1', 'startTime': None, 'vin': 'PRIVATE-SENTINEL'}]}},
            {'code': '000000', 'data': {'total': 3, 'list': [{'vin': 'PRIVATE-SENTINEL'}]}},
        ])
        async with client(transport) as c:
            details = await c.charging_details(VehicleIdentifier('SYNTHETIC-VEHICLE'))
        self.assertEqual(details['recorded_charging_sessions'], 3)
        self.assertEqual(details['charging_plans'][0]['planType'], '-1')
        self.assertNotIn('PRIVATE-SENTINEL', str(details))


if __name__ == "__main__":
    unittest.main()
