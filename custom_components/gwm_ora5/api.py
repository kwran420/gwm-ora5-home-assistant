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
    values = {
        "soc": soc if soc is not None and 0 <= soc <= 100 else None,
        "range": number("2011501"),
        "plugged_in": bool(plug) if plug in (0, 1) else None,
        "charging": True if charge == 1 else False if charge in states else None,
        "charging_status": "disconnected" if charge == 0 and plug == 0 else states.get(charge),
        "vehicle_updated_ms": status.update_time_ms or status.acquisition_time_ms,
    }
    for metric, code in {
        'odometer': '2103010', 'remaining_charge_time': '2013022',
        'charging_mode_code': '2013023', 'away_mode_code': '2012881',
        'steering_heating': '2060016', 'ac_active': '2202001',
        'unlocked': '2208001', 'boot_open': '2206001',
        'front_demister': '2222001', 'rear_demister': '2210032',
        'air_circulation': '2078020', 'gps_authorized': '2310001',
    }.items():
        values[metric] = number(code)
    for metric in ('steering_heating', 'ac_active', 'unlocked', 'boot_open',
                   'front_demister', 'rear_demister', 'air_circulation', 'gps_authorized'):
        value = values[metric]
        values[metric] = bool(value) if value in (0, 1) else None
    for index, position in enumerate(('front_left', 'front_right', 'rear_left', 'rear_right'), 1):
        pressure, temperature = number(f'210100{index}'), number(f'210100{index+4}')
        values[f'tyre_pressure_{position}'] = pressure if pressure is not None and 0 <= pressure <= 600 else None
        values[f'tyre_temperature_{position}'] = temperature if temperature is not None and -40 <= temperature <= 150 else None
        window = number(f'221000{index}')
        values[f'window_{position}'] = window != 1 if window in (0, 1, 2, 3) else None
    for metric, code in {'door_driver':'2206002', 'door_passenger':'2206004',
                         'door_rear_driver':'2206003', 'door_rear_passenger':'2206005'}.items():
        value = number(code)
        values[metric] = bool(value) if value in (0, 1) else None
    for metric, code in {'seat_heat_driver':'2220001', 'seat_heat_passenger':'2220002',
                         'seat_vent_driver':'2220003', 'seat_vent_passenger':'2220004'}.items():
        value = number(code)
        values[metric] = int(value) if value in (0, 1, 2, 3) else None
    values['raw_signals'] = {code: number(code) for code in raw
                            if isinstance(code, str) and code.isdigit() and len(code) == 7 and number(code) is not None}
    values['latitude'], values['longitude'] = status.latitude, status.longitude
    return values


def charging_result(items, remote_type="0x01"):
    """Result response is already scoped by the request's seqNo.

    The official app selects remoteType. hwCommandId is a different identifier,
    not a request-sequence echo. Refuse ambiguous duplicate charging results.
    """
    matches = [item for item in items if item.remote_type == remote_type]
    if len(matches) != 1:
        return "pending"
    code = matches[0].result_code
    if code in ("0", "6"):
        return "completed"
    if code in (None, "", "2000"):
        return "pending"
    return "failed"


class OraClient(GwmClient):
    async def remote_history(self, identifier):
        """Read a small history page; retain no actors, identifiers or payloads."""
        async def read(session, deadline):
            request = self._prepare_command_request(operation='get_vehicle_basics',
                gateway_role=GatewayRole.APP_V1, method='POST', path='vehicle/getWeyVrcHistory',
                body=self._encode_request_json({'vin': identifier.value, 'pageNum': 1, 'pageSize': 3}),
                session=session, vin_header=identifier)
            data = await self._send_command_request(request, deadline=deadline)
            if not isinstance(data, dict) or not isinstance(data.get('list'), list):
                raise ValueError('Unexpected remote history')
            records = []
            for row in data['list'][:3]:
                if not isinstance(row, dict):
                    continue
                stamp, instruction, code = row.get('createdAt'), row.get('remoteType'), row.get('resultCode')
                if type(stamp) is not int or not 946684800000 <= stamp <= 4102444800000:
                    continue
                records.append({'timestamp_ms': stamp,
                    'instruction': instruction if isinstance(instruction, str) and len(instruction) == 4 and instruction.startswith('0x') and all(c in '0123456789abcdefABCDEF' for c in instruction[2:]) else None,
                    'provider_result_code': code if isinstance(code, str) and code.isascii() and code.isdigit() and len(code) <= 8 else None})
            latest = max(records, key=lambda r:r['timestamp_ms']) if records else {}
            total = data.get('total')
            return {'remote_history_last_ms': latest.get('timestamp_ms'),
                    'remote_history_summary': {**latest, 'record_count': total if type(total) is int and total >= 0 else None}}
        return await self._execute_authenticated_command('get_vehicle_basics', timeout=None, action=read)

    async def charging_details(self, identifier):
        """Read the observed ANZ schedule shape and paginated history summary."""
        async def read(session, deadline):
            request = self._prepare_command_request(operation='get_charging_plan', gateway_role=GatewayRole.H5_V1,
                method='GET', path='vehicleCharge/getChargingInfos?vin=' + quote(identifier.value, safe=''),
                body=None, session=session, vin_header=identifier)
            schedule = await self._send_command_request(request, deadline=deadline)
            request = self._prepare_command_request(operation='get_charging_plan', gateway_role=GatewayRole.H5_V1,
                method='POST', path='vehicleCharge/getChargeLogs',
                body=self._encode_request_json({'vin': identifier.value, 'pageNum': 1, 'pageSize': 1}),
                session=session, vin_header=identifier)
            history = await self._send_command_request(request, deadline=deadline)
            if not isinstance(schedule, dict) or not isinstance(history, dict):
                raise ValueError('Unexpected charging details')
            plans = schedule.get('chargePlanList')
            if not isinstance(plans, list) or any(not isinstance(p, dict) for p in plans):
                raise ValueError('Unexpected charging schedule')
            public_plans = [{key: plan.get(key) for key in ('planType', 'startTime', 'endTime', 'weeks')
                             if plan.get(key) is None or type(plan.get(key)) in (str, int)} for plan in plans]
            count = history.get('total')
            return {'schedule_plan_count': len(plans), 'charging_plans': public_plans,
                    'recorded_charging_sessions': count if type(count) is int and count >= 0 else None}
        return await self._execute_authenticated_command('get_charging_plan', timeout=None, action=read)

    async def charge(self, identifier, *, enabled, pin, sequence=None):
        if type(enabled) is not bool:
            raise ValueError("An explicit charging state is required")
        return await self.send_control(identifier, instruction="0x01",
            body={"switchOrder": "1" if enabled else "2"}, pin=pin, sequence=sequence)

    async def send_control(self, identifier, *, instruction, body, pin, sequence=None):
        if instruction not in {"0x01", "0x04", "0x05", "0x06", "0x08", "0x09", "0x0A", "0x0B", "0x11", "0x19"}:
            raise ValueError("Unsupported instruction")
        if not isinstance(pin, str) or len(pin) != 6 or not pin.isascii() or not pin.isdigit():
            raise ValueError("A six-digit PIN is required")
        sequence = sequence or uuid.uuid4().hex + "1234"
        if len(sequence) != 36 or not sequence.endswith("1234") or any(c not in "0123456789abcdef" for c in sequence):
            raise ValueError("Invalid command sequence")
        payload = self._encode_request_json({
            "vin": identifier.value, "seqNo": sequence, "remoteType": "0",
            "instructions": {instruction: body},
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
