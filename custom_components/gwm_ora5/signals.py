"""Display names for decoded numeric status fields; unknown codes stay visible."""

SIGNAL_LABELS = {
    '2013021': 'Battery (%)', '2011501': 'Reported range (km)',
    '2041142': 'Charging state code', '2042082': 'Cable connected code',
    '2013022': 'Estimated charging time (min)',
    '2013023': 'Charging mode (enumeration unverified)',
    '2012881': 'Away mode (enumeration unverified)',
    '2103010': 'Odometer (km)', '2060016': 'Steering-wheel heating code',
    '2202001': 'Climate active code', '2208001': 'Unlocked code',
    '2206001': 'Boot open code', '2222001': 'Front demister code',
    '2210032': 'Rear demister code', '2078020': 'Air circulation code',
    '2310001': 'GPS permission code',
    '2206002': 'Driver door code', '2206004': 'Passenger door code',
    '2206003': 'Rear driver door code', '2206005': 'Rear passenger door code',
    '2220001': 'Driver seat heat level', '2220002': 'Passenger seat heat level',
    '2220003': 'Driver seat ventilation level', '2220004': 'Passenger seat ventilation level',
}
for index, position in enumerate(('Front left', 'Front right', 'Rear left', 'Rear right'), 1):
    SIGNAL_LABELS[f'210100{index}'] = f'{position} tyre pressure (kPa)'
    SIGNAL_LABELS[f'210100{index + 4}'] = f'{position} tyre temperature (C)'
    SIGNAL_LABELS[f'221000{index}'] = f'{position} window code'


def signal_metadata(raw):
    """Describe only numeric fields already admitted by telemetry's privacy filter."""
    return {
        'signal_labels': {code: SIGNAL_LABELS.get(code, 'Unknown / unmapped') for code in raw},
        'unmapped_codes': sorted(code for code in raw if code not in SIGNAL_LABELS),
        'meaning': 'Number of numeric fields in the latest response, not an error count. '
                   'Raw codes have field-specific meanings; 1 is not universally on or a fault.',
    }
