"""ORA 5 command bodies verified against the ANZ app and supervised tests."""

CONTROL_NAMES = {
    'climate_on': 'Start climate', 'climate_off': 'Stop climate',
    'lock': 'Lock', 'unlock': 'Unlock', 'windows_close': 'Close windows',
    'steering_on': 'Start steering wheel heating', 'steering_off': 'Stop steering wheel heating',
    'seat_heat_on': 'Start front seat heating', 'seat_heat_off': 'Stop front seat heating',
    'seat_vent_on': 'Start front seat ventilation', 'seat_vent_off': 'Stop front seat ventilation',
    'front_demister_on': 'Start front demister', 'front_demister_off': 'Stop front demister',
    'rear_demister_on': 'Start rear demister', 'rear_demister_off': 'Stop rear demister',
    'lights': 'Flash lights', 'horn': 'Sound loud alarm', 'horn_lights': 'Sound loud alarm and flash lights',
    'boot_open': 'Open boot', 'boot_close': 'Close boot',
    'cabin_clean': 'Refresh cabin air',
}

COMFORT_START_ACTIONS = {'climate_on', 'seat_heat_on', 'seat_vent_on',
                         'steering_on', 'front_demister_on', 'rear_demister_on'}


def comfort_settings(action, settings):
    """Validate per-command overrides without changing saved account options."""
    if not settings:
        return {}
    if action not in COMFORT_START_ACTIONS:
        raise ValueError('Settings apply only to comfort start controls')
    fields = {'duration': ('control_duration', 5, 30)}
    if action == 'climate_on':
        fields['temperature'] = ('climate_temperature', 16, 32)
    if action in {'seat_heat_on', 'seat_vent_on'}:
        fields['level'] = ('seat_level', 1, 3)
    result = {}
    for key, value in settings.items():
        if key not in fields:
            raise ValueError('This setting does not apply to the selected control')
        target, low, high = fields[key]
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'{key.capitalize()} must be a whole number from {low} to {high}')
        result[target] = value
    return result


def command_body(action, *, temperature=25, duration=5, level=1):
    if action not in CONTROL_NAMES:
        raise ValueError('Unsupported ORA control')
    if type(temperature) is not int or not 16 <= temperature <= 32:
        raise ValueError('Temperature must be 16–32 degrees C')
    if type(duration) is not int or not 5 <= duration <= 30:
        raise ValueError('Duration must be 5–30 minutes')
    if type(level) is not int or not 1 <= level <= 3:
        raise ValueError('Seat level must be 1–3')
    on = action.endswith('_on')
    order = '1' if on else '2'
    if action.startswith('climate_'):
        body = {'switchOrder': order, 'operationTime': str(duration) if on else '0'}
        if on:
            body['temperature'] = str(temperature)
        return '0x04', {'airConditioner': body}
    if action == 'cabin_clean':
        return '0x11', {'switchOrder': '1', 'operationTime': '60'}
    if action in ('lock', 'unlock'):
        return '0x05', {'switchOrder': '2' if action == 'lock' else '1', 'operationTime': '0'}
    if action in ('boot_open', 'boot_close'):
        return '0x09', {'switchOrder': '1' if action == 'boot_open' else '2', 'operationTime': '0'}
    if action == 'windows_close':
        return '0x08', {'window': {key: 0 for key in ('leftFront', 'leftBack', 'rightFront', 'rightBack')}}
    if action.startswith('steering_'):
        return '0x19', {'switchOrder': order, 'operationTime': str(duration) if on else '0'}
    if action.startswith('seat_'):
        return '0x0A', {'seat': {
            'operationMode': '1' if action.startswith('seat_heat_') else '2',
            'switchOrder': order, 'operationTime': str(duration) if on else '0',
            'leftFront': str(level) if on else '0', 'rightFront': str(level) if on else '0',
            'leftBack': '0', 'rightBack': '0',
        }}
    if 'demister_' in action:
        body = {'switchOrder': order, 'defrostFront' if action.startswith('front_') else 'defrostBack': '1'}
        if on:
            body['operationTime'] = str(duration)
        return '0x0B', {'defrost': body}
    return '0x06', {'search': {'whistle': '0' if action == 'lights' else '1',
                              'flashing': '0' if action == 'horn' else '1'}}


def expected_state(action, *, level=1):
    on = action.endswith('_on')
    if action.startswith('climate_'):
        return {'ac_active': on}
    if action == 'cabin_clean':
        return {'ac_active': True, 'air_circulation': True}
    if action in ('lock', 'unlock'):
        return {'unlocked': action == 'unlock'}
    if action.startswith('boot_'):
        return {'boot_open': action == 'boot_open'}
    if action.startswith('steering_'):
        return {'steering_heating': on}
    if 'demister_' in action:
        return {'front_demister' if action.startswith('front_') else 'rear_demister': on}
    if action.startswith('seat_'):
        kind = 'heat' if action.startswith('seat_heat_') else 'vent'
        return {f'seat_{kind}_{side}': level if on else 0 for side in ('driver', 'passenger')}
    if action == 'windows_close':
        return {f'window_{p}': False for p in ('front_left', 'front_right', 'rear_left', 'rear_right')}
    return {}  # Horn/lights have no continuous state in this vehicle's status.
