"""ANZ ORA 5 adapter over the pinned upstream GWM client.

No OEM signing constants, app assets, or user credentials belong in this file.
The adapter uses private upstream transport interfaces, so the dependency is
pinned to an exact source commit and tested independently of Home Assistant.
"""
import hashlib
import math
import uuid
from dataclasses import asdict, replace
from datetime import datetime
from urllib.parse import quote

from gwm_client import GwmClient, GwmClientConfig, Region
from gwm_client.anz_auth import AnzAuthState, AnzCredentials
from gwm_client.regions import GatewayRole
from gwm_client.signing import sign_request


def encode_state(state):
    data = asdict(state)
    if data.get("verification_requested_at"):
        data["verification_requested_at"] = data["verification_requested_at"].isoformat()
    return data


def decode_state(data):
    if not data:
        return None
    data = dict(data)
    if data.get("verification_requested_at"):
        data["verification_requested_at"] = datetime.fromisoformat(data["verification_requested_at"])
    return AnzAuthState(**data)


def make_credentials(data):
    credentials = AnzCredentials(
        data["account"], data["password"], data["country"], data["device_id"], "current_v2"
    )
    # Send the user's actual password. The upstream Flutter input formatter
    # silently removes punctuation, which is inappropriate for an API form.
    object.__setattr__(credentials, "password", data["password"])
    return credentials


def new_client():
    return OraClient(GwmClientConfig(Region.ANZ, anz_authentication_method="current_v2"))


def reclaim_state(state):
    if state is None:
        return None
    return replace(state, access_token=None, refresh_token=None, gw_id=None,
                   session_reclaim_required=True)


def is_ora5(vehicle):
    names = (vehicle.app_show_series_name, vehicle.model_name, vehicle.vehicle_type_name)
    return any("ora5" in "".join(c for c in (name or "").lower() if c.isalnum()) for name in names)


def vehicle_key(identifier):
    return hashlib.sha256(identifier.value.encode()).hexdigest()[:24]


def telemetry(status):
    raw = {item.code: item.value for item in status.items}

    def number(code):
        try:
            value = float(raw[code])
            return value if math.isfinite(value) else None
        except (KeyError, ValueError, TypeError):
            return None

    charge = number("2041142")
    plug = number("2042082")
    states = {0: "connected", 1: "charging", 2: "awaiting_charging",
              3: "complete", 5: "waiting_for_power", 6: "error"}
    soc = number("2013021")
    return {
        "soc": soc if soc is not None and 0 <= soc <= 100 else None,
        "range": number("2011501"),
        "plugged_in": bool(plug) if plug in (0, 1) else None,
        "charging": True if charge == 1 else False if charge in states else None,
        "charging_status": "disconnected" if charge == 0 and plug == 0 else states.get(charge),
        "vehicle_updated_ms": status.update_time_ms or status.acquisition_time_ms,
    }


def charging_result(items):
    """Result response is already scoped by the request's seqNo.

    The official app selects remoteType. hwCommandId is a different identifier,
    not a request-sequence echo. Refuse ambiguous duplicate charging results.
    """
    matches = [item for item in items if item.remote_type == "0x01"]
    if len(matches) != 1:
        return "pending"
    code = matches[0].result_code
    if code in ("0", "6"):
        return "completed"
    if code in (None, "", "2000"):
        return "pending"
    return "failed"


class OraClient(GwmClient):
    async def charge(self, identifier, *, enabled, pin, sequence=None):
        if type(enabled) is not bool or not isinstance(pin, str) or len(pin) != 6 or not pin.isascii() or not pin.isdigit():
            raise ValueError("A six-digit PIN and explicit charging state are required")
        sequence = sequence or uuid.uuid4().hex + "1234"
        if len(sequence) != 36 or not sequence.endswith("1234") or any(c not in "0123456789abcdef" for c in sequence):
            raise ValueError("Invalid command sequence")
        payload = self._encode_request_json({
            "vin": identifier.value, "seqNo": sequence, "remoteType": "0",
            "instructions": {"0x01": {"switchOrder": "1" if enabled else "2"}},
            "securityPassword": hashlib.md5(pin.encode()).hexdigest(), "type": 2,
        })

        async def send(session, deadline):
            request = self._prepare_command_request(
                operation="send_command", gateway_role=GatewayRole.APP_V1,
                method="POST", path="vehicle/T5/sendCmd", body=payload,
                session=session, vin_header=None,
            )
            await self._send_command_request(request, deadline=deadline)
            return sequence

        # Never retry a write after a timeout or authentication error.
        return await self._execute_authenticated_command("send_command", timeout=None, action=send)

    async def charge_result(self, identifier, sequence):
        from gwm_client.commands import parse_remote_command_results

        async def read(session, deadline):
            gateway = self._protocol.gateway(GatewayRole.APP_V1)
            path = "vehicle/getRemoteCtrlResultT5?seqNo=" + quote(sequence, safe="")
            request = self._prepare_command_request(
                operation="get_remote_command_result", gateway_role=GatewayRole.APP_V1,
                method="GET", path=path, body=None, session=session, vin_header=identifier,
            )
            # ANZ authentication is Flutter; T5 result queries use native signing.
            signed = sign_request(gateway.signing_profile, "GET", gateway.base_url + path)
            request = replace(request, url=signed.url, headers={**request.headers, **signed.headers})
            data = await self._send_command_request(request, deadline=deadline)
            return parse_remote_command_results(data, allow_integer_strings=False)

        return await self._execute_authenticated_command("get_remote_command_result", timeout=None, action=read)
