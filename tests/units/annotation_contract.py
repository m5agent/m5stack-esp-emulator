"""Independent guest and coverage checks for the twelve existing scalar rails."""
from __future__ import annotations

import math
import re
import json
from datetime import datetime

import run_sensor_cases as sensors
from unit_adc_fixture import expected_ideal_input

SENSOR_CASES = ('color', 'tof', 'ncir', 'heart', 'tvoc', 'ultrasonic-i2c')
CASES = ('env-iii', 'relay', *SENSOR_CASES, 'pir', 'light', 'thermal', 'buzzer')
FIRST = {'temperature-c': 31.5, 'humidity-pct': 67.0, 'pressure-pa': 98765.0}
SECOND = {'temperature-c': 18.75, 'humidity-pct': 45.5, 'pressure-pa': 103200.0}


def env_rows(serial, vector):
    fields = ('temperature-c', 'humidity-pct', 'pressure-pa')
    if set(vector) != set(fields) or any(type(vector[key]) not in (int, float)
                                       or not math.isfinite(vector[key]) for key in fields):
        return []
    rows = []
    for row in re.findall(r'(?m)^UNIT_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$', serial):
        try:
            numbers = list(map(float, row))
        except ValueError:
            continue
        if all(math.isfinite(value) and abs(value - vector[field]) < tolerance
               for value, field, tolerance in zip(numbers, fields, (0.2, 0.2, 1.0))):
            rows.append(numbers)
    return rows


def guest_marker_matches(case, values, serial):
    """Caller supplies only serial after its pre-input offset, never old rows."""
    if case in SENSOR_CASES:
        if set(values) != set(sensors.CASES[case]['changes'][0]) or any(
                type(value) not in (int, float) or not math.isfinite(value) for value in values.values()):
            return False
        return sensors.reading_matches(case, values, serial)
    if case == 'env-iii':
        return bool(env_rows(serial, values))
    if case == 'pir':
        return set(values) == {'motion'} and type(values['motion']) is bool and bool(re.search(
            rf'(?m)^IO_PIR {int(values["motion"])} \d+ \d+ \d+\r?$', serial))
    if case == 'light':
        if set(values) != {'analog-mv', 'digital-level'} or type(values['digital-level']) is not bool:
            return False
        voltage = values['analog-mv']
        if type(voltage) not in (int, float) or not math.isfinite(voltage) or not 0 <= voltage <= 3300:
            return False
        raw = expected_ideal_input(voltage, attenuation=3, adc_unit=1)['read_u16']
        return bool(re.search(rf'(?m)^IO_LIGHT {raw} {int(values["digital-level"])}\r?$', serial))
    raise ValueError('no input-marker contract for ' + case)


def required_phases(case):
    if case == 'env-iii':
        return ('env-vector-1', 'env-vector-2')
    if case == 'relay':
        return ('relay-0', 'relay-1')
    if case in SENSOR_CASES:
        return ('input-1', 'input-2')
    if case in {'pir', 'light'}:
        return tuple(f'input-{index}' for index in range(1, 7 if case == 'pir' else 4))
    if case == 'thermal':
        return ('thermal-reference', 'thermal-variant')
    if case == 'buzzer':
        return ('buzzer-0', 'buzzer-1', 'buzzer-2', 'buzzer-once', 'buzzer-timer-zero', 'buzzer-off')
    raise ValueError('no scalar-rail contract for ' + case)


def expected_posts(case):
    if case == 'env-iii':
        return [(key, value) for vector in (FIRST, SECOND) for key, value in vector.items()]
    if case in SENSOR_CASES:
        return [(key, value) for vector in sensors.CASES[case]['changes'] for key, value in vector.items()]
    if case == 'pir':
        return [('motion', value) for value in (True, False, True, False, True, False)]
    if case == 'light':
        # The product checkbox starts false. Checking false is an intentional
        # no-op; the first vector still proves the unchanged digital input.
        return [('analog-mv', 310), ('analog-mv', 1550), ('digital-level', True),
                ('analog-mv', 3100), ('digital-level', False)]
    if case == 'thermal':
        variant = json.loads((sensors.THERMAL / 'synthetic-plus16.json').read_text())
        return [(key, variant['initial'][key]) for key in ('frame0-hex', 'frame1-hex')]
    return []


def _event_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return result if result.tzinfo is not None else None


def annotation_checks(case, web, guest_vectors):
    snapshots = web.get('annotation_snapshots', [])
    phases = [snapshot.get('phase') for snapshot in snapshots]
    wanted = required_phases(case)
    checks = {
        'annotation_phase_coverage': (phases == list(wanted) if case != 'relay' else
            len(phases) == len(wanted) and len(set(phases)) == len(phases) and set(phases) == set(wanted)),
        'annotation_exact_alignment': bool(snapshots) and all(snapshot.get('exact_http_controller_dom_alignment') is True for snapshot in snapshots),
        'terminal_clears_live_values': type(web.get('annotation_terminal', {}).get('live_annotation_fields')) is int
            and web['annotation_terminal']['live_annotation_fields'] == 0,
        'phase_evidence_modes': all(snapshot.get('evidence_mode', 'full') == (
            'state' if case == 'buzzer' and snapshot.get('phase') != 'buzzer-off' else 'full') for snapshot in snapshots),
    }
    full = [snapshot for snapshot in snapshots if snapshot.get('evidence_mode', 'full') == 'full']
    checks['readout_gestures_and_screenshots'] = bool(full) and all(
        snapshot.get('readout_gesture', {}).get('unit_post_delta') == 0
        and snapshot.get('readout_gesture', {}).get('all_mutation_delta') == 0
        and snapshot.get('readout_screenshot') and snapshot.get('screenshot') for snapshot in full)
    posts = web.get('posts', [])
    actual = [(field, value) for post in posts for field, value in post.get('request', {}).get('values', {}).items()]
    wanted_posts = expected_posts(case)
    checks['exact_original_product_input_posts'] = len(posts) == len(wanted_posts) and actual == wanted_posts and all(
        type(observed) is bool if type(wanted_value) is bool else type(observed) is not bool
        for (_, observed), (_, wanted_value) in zip(actual, wanted_posts))
    if case == 'light':
        first_post = _event_time(posts[0].get('at')) if posts else None
        session_id = web.get('session_id')
        checks['initial_false_digital_input_observed_before_first_post'] = first_post is not None and bool(session_id) and any(
            event.get('method') == 'GET' and event.get('status') == 200
            and event.get('path') == f'/api/v1/sessions/{session_id}/units'
            and (at := _event_time(event.get('at'))) is not None and at < first_post
            and event.get('response', {}).get('session_id') == session_id
            and event.get('response', {}).get('state') == 'running'
            and event.get('response', {}).get('source') == 'live'
            and any(unit.get('id') == 'external1' and unit.get('unit_id') == 'light'
                    and unit.get('source') == 'guest-qom' and unit.get('available') is True
                    and unit.get('properties', {}).get('digital-level') is False
                    for unit in event.get('response', {}).get('units', []))
            for event in web.get('readbacks', []))
    if case in SENSOR_CASES or case in {'env-iii', 'pir', 'light', 'thermal'}:
        checks['fresh_guest_observations'] = [row.get('phase') for row in guest_vectors] == list(wanted) and all(
            row.get('guest_observed') is True and type(row.get('serial_offset')) is int
            and row['serial_offset'] >= 0 and row.get('fresh_serial_sha256') for row in guest_vectors)
    return checks


def buzzer_observation(phase, properties, serial, offset):
    """Only the next phase in this observed cycle can authorize a rail sample.

    The automatic timer's zero is sampled after once, before TIMER_DONE/manual
    writes. It has no new serial print; the preceding once marker is its anchor.
    """
    frequency, duty = properties.get('frequency-hz'), properties.get('duty-pct')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in (frequency, duty)):
        return None
    if type(offset) is not int or not 0 <= offset <= len(serial):
        return None
    phase_markers = {
        'buzzer-0': ('IO_BUZZER 0 1200 0', 1200, 0),
        'buzzer-1': ('IO_BUZZER 1 2400 25', 2400, 25),
        'buzzer-2': ('IO_BUZZER 2 3600 75', 3600, 75),
        'buzzer-once': ('IO_BUZZER_ONCE 2000 50', 2000, 50),
        'buzzer-off': ('IO_BUZZER_OFF', 2000, 0),
    }
    next_event = r'(?m)^IO_BUZZER(?: |_)'
    if phase == 'buzzer-timer-zero':
        previous = list(re.finditer(r'(?m)^IO_BUZZER_ONCE 2000 50\r?$', serial[:offset]))
        if not previous or previous[-1].end() != offset or re.search(next_event, serial[offset:]):
            return None
        if abs(frequency - 2000) > 40 or duty != 0:
            return None
        return {'serial_offset': offset, 'marker_end': offset,
                'marker': 'IO_BUZZER_ONCE 2000 50', 'before_timer_done_and_manual_output': True}
    marker, wanted_frequency, wanted_duty = phase_markers[phase]
    matches = list(re.finditer(r'(?m)^' + re.escape(marker) + r'\r?$', serial[offset:]))
    if not matches:
        return None
    match = matches[-1]
    end = offset + match.end()
    if re.search(next_event, serial[end:]) or abs(frequency - wanted_frequency) > max(2, wanted_frequency * 0.02) or abs(duty - wanted_duty) > 0.5:
        return None
    return {'serial_offset': offset, 'marker_end': end, 'marker': marker}
