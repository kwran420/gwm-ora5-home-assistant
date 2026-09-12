"""Home Assistant runtime checks; skipped in client-only environments."""
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

HAS_HA = importlib.util.find_spec("homeassistant") is not None


@unittest.skipUnless(HAS_HA, "Run in a Home Assistant Python environment")
class HomeAssistantTests(unittest.IsolatedAsyncioTestCase):
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
