"""Synthetic protocol tests. Never load local account data."""
import importlib.util
import json
import ssl
import unittest
from pathlib import Path

from gwm_client import GwmClientConfig, GwmSession, Region, RemoteCommandResultItem, VehicleIdentifier
from gwm_client._protocol import _TransportResponse

spec = importlib.util.spec_from_file_location("ora5_api", Path(__file__).parents[1] / "custom_components/gwm_ora5/api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


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


if __name__ == "__main__":
    unittest.main()
