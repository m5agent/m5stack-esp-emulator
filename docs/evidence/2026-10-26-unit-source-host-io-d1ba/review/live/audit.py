#!/usr/bin/env python3
"""Independent source-host-IO evidence audit. Network/process/guest always denied.

The final set is exactly 3 hosts x 8 Units: Fan3 plus rest21, never Fan twice.
Partial reports remain PENDING; --final requires all 24 terminal cases.
"""
from __future__ import annotations
import argparse
import ast
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
AUTHOR = ROOT / '.work/unit-source-host-io-20261026'
HOSTS = ('atoms3r', 'sticks3', 'stopwatch')
UNITS = ('pir', 'dual-button', 'limit', 'key', 'rgb', 'fan', 'rs485', 'hub')
RUNTIME = 'd1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff'
SIZE = {'atoms3r': [128, 128], 'sticks3': [135, 240], 'stopwatch': [466, 466]}
PIN = {'atoms3r': (1, 2), 'sticks3': (10, 9), 'stopwatch': (11, 10)}
FONT = {'atoms3r': (.7, 10), 'sticks3': (1., 15), 'stopwatch': (2., 30)}
EXPECTED = {(h, u) for h in HOSTS for u in UNITS}
INPUTS = {
    'pir': [('external1', {'motion': v}) for v in (True, False, True, False, True, False)],
    'dual-button': [('external1', {k: v}) for k, v in (('blue-pressed', True), ('blue-pressed', False), ('red-pressed', True), ('red-pressed', False))],
    'limit': [('external1', {'pressed': v}) for v in (True, False, True, False)],
    'key': [('external1', {'pressed': v}) for v in (True, False)],
    'rgb': [], 'fan': [],
    'rs485': [('external1', {'rx-hex': b'peer-to-guest\x00\x7f\xff'.hex()})],
    'hub': [('env', {'temperature-c': 31.5, 'humidity-pct': 67, 'pressure-pa': 98765}),
            ('ncir', {'ambient-c': 17.3, 'object-c': 37.1}), ('tvoc', {'eco2-ppm': 1250, 'tvoc-ppb': 230})],
}
CHECKS = {
    'pir': {'both_gpio_edges_and_disable_reenable_irq'},
    'dual-button': {'independent_hardware_button_pins_and_click_state_machines'},
    'limit': {'official_limit_button_alias_irq_counter_and_reset'},
    'key': {'active_low_key_and_guest_brightness_rgb_frames'},
    'rgb': {'native_rmt_grb_all_three_leds_and_short_frame_negative'},
    'fan': {'guest_ledc_frequency_and_duty_registers'},
    'rs485': {'uart1_bidirectional_binary_fifo_and_any_read_write', 'fifo_capacity_rejection_and_uart0_log_separation'},
    'hub': {'passive_hub_three_real_drivers_independent_inputs_same_bus', 'hub_has_no_i2c_address'},
}
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
LOAD = lambda path: json.loads(path.read_bytes())
CANON = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def need(value, message):
    if not value:
        raise RuntimeError(message)


def has(text, marker):
    return re.search(r'(?m)^' + re.escape(marker) + r'\r?$', text) is not None


def inventory(directory):
    return {p.relative_to(directory).as_posix(): SHA(p.read_bytes()) for p in sorted(directory.rglob('*')) if p.is_file()}


def png(raw, device):
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        need(image.format == 'PNG' and list(image.size) == SIZE[device] and image.convert('RGB').getcolors(1) is None, 'native PNG format/geometry/nonblank differs')
    return {'sha256': SHA(raw), 'bytes': len(raw), 'native_size': SIZE[device]}


def source_function(source, name):
    node = next(n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return SHA(ast.get_source_segment(source, node).encode())


def props(state, instance='external1'):
    return next(u['properties'] for u in state['units'] if u['id'] == instance)


def unit_state(state, row):
    need(state['source'] == 'live' and state['state'] == 'running' and state['contract_status'] == 'frozen', 'Unit/QOM state not running/live/frozen')
    need({u['id']: u['unit_id'] for u in state['units']} == {a['id']: a['unit_id'] for a in row['attachments']} and len(state['units']) == len(row['attachments']), 'Unit topology differs')
    need(all(u['source'] == 'guest-qom' and u['available'] and not u['errors'] for u in state['units']), 'Unit/QOM controller unavailable')


def independent_semantics(directory, row, result, observations, final_serial):
    unit, device = row['unit_id'], row['device_id']
    need(not any(word in final_serial for word in ('IO_PROBE_FAIL', 'HOST_IO_FAIL', 'Traceback (most recent call last)', 'Guru Meditation', 'Rebooting...')), 'guest failure marker')
    need(has(final_serial, 'IO_PROBE_READY ' + unit), 'original IO ready absent')
    inputs = [e for e in observations if e['kind'] == 'input' and e['accepted'] is True]
    need([(e['id'], e['values']) for e in inputs] == INPUTS[unit] and all(e['via_ui'] is True for e in inputs), 'original positive input sequence differs')
    windows = []
    for index, event in enumerate(inputs):
        before = event['before_cursor']['data']
        upper = len(inputs[index + 1]['before_cursor']['data']) if index + 1 < len(inputs) else len(final_serial)
        need(final_serial.startswith(before) and len(before) < upper <= len(final_serial), 'fresh UART lower/upper prefixes differ')
        waits = [e for e in observations if e['kind'] == 'wait-success' and e.get('input_event') == event['event_id']]
        need(waits, 'input has no original predicate completion')
        last = (directory / waits[-1]['serial_file']).read_bytes().decode()
        need(last.startswith(before) and len(last) > len(before) and final_serial.startswith(last) and len(last) <= upper, 'original wait is stale or crosses next input upper boundary')
        windows.append({'event_id': event['event_id'], 'lower': len(before), 'wait_end': len(last), 'next_input_upper': upper,
                        'segment': final_serial[len(before):upper], 'original_wait_suffix': last[len(before):]})
    states, current_marker = {}, None
    for event in observations:
        if event['kind'] == 'marker':
            current_marker = event['marker']
        elif event['kind'] == 'state':
            states.setdefault(current_marker, []).append(LOAD(directory / event['file']))
    final = LOAD(directory / 'final-units.json')
    unit_state(final, row)
    if unit == 'fan':
        for stage, frequency, speed in ((0, 1000, 0), (1, 1000, 25), (2, 1500, 100)):
            marker = f'IO_FAN {stage} {frequency} {speed}'
            need(has(final_serial, marker), 'Fan guest stage missing')
            duty = round((speed - 1) * 953 / 99 + 70) / 1023 * 100 if speed else 0
            need(any(abs(props(state)['frequency-hz'] - frequency) <= max(2, frequency * .02) and abs(props(state)['duty-pct'] - duty) <= .5 for state in states.get(marker, [])), 'Fan stage lacks matching actual LEDC QOM')
        need(props(final)['output-transitions'] >= 3 and not inputs, 'Fan original transitions/output-only contract absent')
    elif unit == 'rgb':
        marker1, short_marker, marker2 = 'IO_RGB_FULL 1', 'IO_RGB_SHORT 1', 'IO_RGB_FULL 2'
        need(all(has(final_serial, marker) for marker in (marker1, short_marker, marker2)), 'RGB guest full-short-full markers absent')
        first = [props(state) for state in states.get(marker1, []) if props(state)['led-rgb'] == [0x112233, 0x445566, 0x778899]]
        short = [props(state) for state in states.get(short_marker, [])]
        need(first and any(a['led-rgb'] == b['led-rgb'] and a['led-frames'] == b['led-frames'] and b['incomplete-frames'] > a['incomplete-frames'] for a in first for b in short), 'RGB short-frame negative/counter absent')
        need(any(props(state)['led-rgb'] == [0xA1B2C3, 0x010203, 0x040506] for state in states.get(marker2, [])), 'RGB second full chain absent')
        counters = {e['property']: e['value'] for e in observations if e['kind'] == 'qom' and e['path'] == '/machine/rmt0'}
        need(counters == result['rmt_controller'] and counters['tx-symbols'] >= 168 and counters['tx-threshold-events'] > 0 and counters['tx-completions'] >= 3 and counters['tx-errors'] == 0 and not inputs, 'RGB threshold/refill/completion or output-only contract absent')
    elif unit == 'pir':
        markers = ('IO_PIR_CALLBACK 1 1', 'IO_PIR_CALLBACK 0 1', 'IO_PIR 1 1 1 1', 'IO_PIR_DISABLED_DONE 1 1', 'IO_PIR_CALLBACK 1 2', 'IO_PIR_CALLBACK 0 2')
        need(all(has(window['original_wait_suffix'], marker) for window, marker in zip(windows, markers)), 'PIR callback/disabled fresh marker absent')
        need('IO_PIR_CALLBACK' not in windows[2]['segment'] + windows[3]['segment'] and has(windows[3]['segment'], 'IO_PIR_REENABLED'), 'PIR disable/re-enable callback contract differs')
    elif unit == 'dual-button':
        for window, (raw, click) in zip(windows, (((0, 1), None), ((1, 1), (1, 0)), ((1, 0), None), ((1, 1), (1, 1)))):
            need(re.search(r'(?m)^IO_DUAL %d %d ' % raw, window['original_wait_suffix']), 'DualButton fresh raw GPIO absent')
            if click:
                need(has(window['original_wait_suffix'], 'IO_DUAL_CLICK %d %d' % click), 'DualButton fresh click absent')
    elif unit == 'limit':
        need(has(final_serial, 'IO_LIMIT_BUTTON_ALIAS 1'), 'Limit driver alias absent')
        for window, (raw, count) in zip(windows, ((0, 0), (1, 1), (0, 2), (1, 3))):
            need(has(window['original_wait_suffix'], f'IO_LIMIT {raw} {count}'), 'Limit fresh edge counter absent')
        need(has(windows[-1]['segment'], 'IO_LIMIT_COUNT_RESET 0'), 'Limit reset absent')
    elif unit == 'key':
        for event, window, (raw, color) in zip(inputs, windows, ((0, 0x123456), (1, 0x2468AC))):
            need(has(window['original_wait_suffix'], f'IO_KEY_RAW {raw}'), 'Key fresh active-low GPIO absent')
            need(any(props(LOAD(directory / e['file']))['led-rgb'] == color for e in observations if e['kind'] == 'state' and e.get('input_event') == event['event_id']), 'Key RGB guest/native RMT frame absent')
        need(props(final)['led-frames'] >= 3, 'Key actual LED frame count absent')
    elif unit == 'rs485':
        initial, incoming = b'guest-to-peer\x00\x7f\xff', b'peer-to-guest\x00\x7f\xff'
        reply = b'echo:' + incoming
        need(has(windows[0]['original_wait_suffix'], 'IO_RS485_RX ' + incoming.hex()) and has(windows[0]['original_wait_suffix'], f'IO_RS485_ECHO {len(reply)} {reply.hex()}'), 'RS485 fresh binary UART RX/echo absent')
        need(props(final)['tx-hex'] == (initial + reply).hex() and props(final)['read-bytes'] == len(incoming) and props(final)['written-bytes'] == len(initial + reply), 'RS485 actual FIFO byte counts differ')
        rejected = [e for e in observations if e['kind'] == 'input' and e['accepted'] is False]
        need(len(rejected) == 1 and rejected[0]['via_ui'] is False and rejected[0]['values'] == {'rx-hex': (b'x' * 256).hex()} and 'FIFO' in rejected[0]['error'], 'RS485 original FIFO negative missing')
    else:
        need(has(final_serial, 'IO_HUB_SCAN 68 88 90 112'), 'HUB same bus driver scan differs')
        current = None
        # Exact initial vectors are read from the frozen original oracle below,
        # rather than inferred from a UI default or a different firmware batch.
        source = (directory.parents[1] / 'source-snapshot/tests/units/run_io_cases.py.txt').read_text()
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'HUB_INITIAL' for t in node.targets):
                current = ast.literal_eval(node.value)
        need(isinstance(current, dict) and set(current) == {'env', 'ncir', 'tvoc'}, 'frozen original HUB_INITIAL missing')
        for event, window in zip(inputs, windows):
            current[event['id']].update(event['values'])
            expected = [*current['env'].values(), *current['ncir'].values(), *current['tvoc'].values()]
            vectors = [[float(v) for v in line.split()] for line in re.findall(r'(?m)^IO_HUB ([^\r\n]+)', window['original_wait_suffix'])]
            need(any(len(vector) == 7 and all(abs(a - b) <= tolerance for a, b, tolerance in zip(vector, expected, (.2, .2, 1.5, .021, .021, 0, 0))) for vector in vectors), 'HUB fresh cumulative leaf vector absent')
        for instance in ('env', 'ncir', 'tvoc'):
            need(all(props(final, instance)[key] > 0 for key in ('transactions', 'read-bytes', 'written-bytes', 'input-events')), 'HUB independent leaf data plane missing')
    internal = [(phase, int(identity), int(count)) for phase, identity, count in re.findall(r'(?m)^HOST_IO_INTERNAL (before|after_init|loop) (\d+) (\d+)\r?$', final_serial)]
    need(internal[:2] == [('before', 36, 1), ('after_init', 36, 2)] and all(identity == 36 for _, identity, _ in internal) and all(a[2] < b[2] for a, b in zip(internal, internal[1:])), 'onboard BMI270 identity/counters differ')
    host = LOAD(directory / 'host-observation.json')
    host_serial = (directory / host['serial_file']).read_bytes().decode()
    offset = host['fresh_loop_offset']
    need(host_serial.startswith(host['before_cursor']['data']) and len(host['before_cursor']['data']) == offset and SHA(host_serial.encode()) == host['serial_sha256'] and re.search(r'(?m)^HOST_IO_INTERNAL loop 36 ([3-9]|[1-9][0-9]+)\r?$', host_serial[offset:]), 'fresh onboard BMI read after original IO absent')
    fonts = re.findall(r'(?m)^HOST_IO_FONT (\S+) (\S+) (\d+)\r?$', final_serial)
    need(len(fonts) == 1 and fonts[0][0] == 'Montserrat12' and (float(fonts[0][1]), int(fonts[0][2])) == FONT[device], 'actual host font scale/height differs')
    need(has(final_serial, host['geometry_marker']) and has(final_serial, host['layout_marker']) and re.search(r'(?m)^HOST_IO_DEFAULT_FONT_HEIGHT [1-9][0-9]*\r?$', final_serial), 'actual host canvas/layout/default metrics absent')
    return {'status': 'PASS', 'accepted_input_count': len(inputs), 'fresh_UART_windows': [{k: v for k, v in w.items() if k not in ('segment', 'original_wait_suffix')} for w in windows],
            'internal_read_log_records': len(internal), 'last_internal_counter': internal[-1][2], 'actual_font': list(FONT[device])}


def audit_case(batch, row, frozen, original_module, host_module):
    device, unit = row['device_id'], row['unit_id']
    directory = batch / device / unit
    before = inventory(directory)
    result = LOAD(directory / 'result.json')
    need((device, unit) in EXPECTED and result['status'] == 'PASS' and CHECKS[unit] <= set(result['checks']) and all(result['checks'].values()), 'original case checks incomplete')
    need(all(result[key] == row[key] for key in row if key != 'status'), 'prepared/result identity differs')
    request = LOAD(directory / 'source-request.json')
    files = request['files']
    need(len(files) == row['caller_file_count'] == 19 and SHA(CANON(files)) == row['source_cas_sha256'], 'caller set/CAS differs')
    need({p.relative_to(directory / 'files').as_posix() for p in (directory / 'files').rglob('*') if p.is_file()} == set(files), 'saved caller inventory differs')
    origins = LOAD(directory / 'guest-source-freeze.json')
    for name, text in files.items():
        raw = text.encode()
        need((directory / 'files' / name).read_bytes() == raw and SHA(raw) == row['probe_sha256'][name] == origins[name]['sha256'], 'caller source bytes differ')
        ast.parse(text, filename=name)
        if name != 'probe_config.py':
            need(SHA(raw) == frozen[origins[name]['repository_path']], 'caller not exact original host/driver frozen source')
    config = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(files['probe_config.py']).body}
    expected_config = {'CASE': unit, 'WHITE': PIN[device][0], 'YELLOW': PIN[device][1],
                       'IR_CALLBACK_ROOT_PATCH': False, 'BUZZER_CALLBACK_ARITY_PATCH': False, 'DEVICE_ID': device,
                       'INTERNAL_CONTROLLER': 1, 'EXTERNAL_CONTROLLER': 0, 'INTERNAL_SDA': 47,
                       'INTERNAL_SCL': 0 if device == 'atoms3r' else 48, 'LOG_TX': 43, 'LOG_RX': 44}
    need(config == expected_config and files['probe_config.py'] == ''.join(f'{key} = {value!r}\n' for key, value in expected_config.items()), 'exact formal caller config/pins/controller/UART0 isolation differs')
    drivers = LOAD(directory / 'official-driver-proof.json')
    for name, record in drivers.items():
        need(SHA(files['io_drivers/' + name].encode()) == record['sha256'], 'official driver manifest mismatch')
    original_source = (batch / 'source-snapshot/tests/units/run_io_cases.py.txt').read_text()
    for name in ('Observations', 'validate_io', 'validate_evidence', 'attachments'):
        need(source_function(original_source, name) == row['original_function_sha256']['tests/units/run_io_cases.py::' + name], 'original full IO oracle changed')
    firmware = LOAD(directory / 'firmware-response.json')
    source, cas = firmware['source'], row['source_cas_sha256']
    meta = source['metadata']
    need(source == result['source'] and source['kind'] == 'uiflow' and source['artifact_id'] == cas and meta['source_sha256'] == meta['effective_source_sha256'] == cas and not meta['generated_files'], 'caller/effective source provenance differs')
    need(meta['base_sha256'] == request['expected_base_sha256'] == row['base_firmware_sha256'] and meta['firmware_sha256'] == firmware['sha256'] == firmware['firmware_id'] == result['firmware_sha256'], 'host base/derived firmware identity differs')
    entries = {e['path']: e for e in meta['files']}
    need(len(entries) == len(meta['files']) == len(files) == meta['caller_file_count'] and meta['caller_source_bytes'] == sum(len(text.encode()) for text in files.values()), 'source file totals differ')
    for name, text in files.items():
        need(entries[name]['origin'] == 'caller' and entries[name]['sha256'] == SHA(text.encode()) and entries[name]['size'] == len(text.encode()), 'service source readback bytes differ')
    need(meta['vfs']['source'] == 'actual-base-partition-table' and meta['vfs']['offset'] == row['reference_layout']['offset'] and meta['vfs']['size'] == row['reference_layout']['size'] and all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged', 'existing_files_readback_verified', 'source_readback_verified')), 'actual host VFS/readback/preservation differs')
    need(meta['toolchain'] == row['expected_composer_toolchain'], 'source composer toolchain/ABI/config differs')
    actual = []
    for index, event in enumerate(LOAD(directory / 'http/index.json')):
        raw = (directory / 'http' / event['response_file']).read_bytes()
        need(SHA(raw) == event['response_sha256'] and len(raw) == event['response_size'], 'raw HTTP response bytes changed')
        try:
            body = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            body = None
        actual.append((event, body, raw, (directory / 'http' / event['request_file']).read_bytes()))
    sid, session_path = result['session_id'], '/api/v1/sessions/' + result['session_id']
    mutations = [(index, e, body, raw, req) for index, (e, body, raw, req) in enumerate(actual) if e['method'] != 'GET']
    allowed = {('POST', '/api/v1/firmware/uiflow'), ('POST', '/api/v1/sessions'), ('DELETE', session_path)}
    if unit == 'rs485':
        allowed.add(('POST', session_path + '/unit-input'))
    need(all((e['method'], e['path']) in allowed for _, e, _, _, _ in mutations), 'binary/alternate intake or extra mutation')
    compose = [a for a in mutations if a[1]['path'] == '/api/v1/firmware/uiflow']
    create = [a for a in mutations if a[1]['path'] == '/api/v1/sessions']
    stop = [a for a in mutations if a[1]['method'] == 'DELETE']
    need(len(compose) == len(create) == len(stop) == 1 and json.loads(compose[0][4]) == request and compose[0][2] == firmware, 'source compose lacks exact raw backing')
    startup, created = LOAD(directory / 'session-request.json'), LOAD(directory / 'created-session.json')
    need(json.loads(create[0][4]) == startup and create[0][2] == created and created['session_id'] == sid and startup['device_id'] == device and startup['firmware_id'] == firmware['firmware_id'] and startup['uiflow_source_sha256'] == cas and startup['units'] == row['attachments'], 'visible source-pinned session raw backing differs')
    def backed(value, suffix, method=None):
        return any(body == value and e['path'].endswith(suffix) and (method is None or e['method'] == method) for e, body, _, _ in actual)
    proof = LOAD(batch / 'browser' / sid / 'runtime-provenance.json')
    need(proof == result['runtime_provenance'] and proof['status'] == 'VERIFIED' and proof['kind'] == 'direct-pid' and proof['runtime_binary_sha256'] == row['expected_runtime_sha256'] == RUNTIME and proof['firmware_sha256'] == result['firmware_sha256'], 'actual PID/runtime/firmware proof differs')
    need(type(proof['observed_pid']) is int and proof['observed_pid'] > 0 and type(proof['worker_generation']) is int and proof['worker_generation'] == result['expected_worker_generation'] and proof['worker_id'], 'worker/PID identity missing')
    for name in ('ready-session.json', 'running-session.json', 'before-evidence-session.json'):
        value = LOAD(directory / name)
        need(backed(value, '/' + sid, 'GET') and value['state'] == 'running' and value['pid'] == proof['observed_pid'] and value['worker']['worker_id'] == proof['worker_id'] and value['worker']['generation'] == proof['worker_generation'] and value['worker']['lease_active'] and value['firmware_provenance'] == source and value['source_artifacts'][0] == cas, 'running source/PID/worker continuity differs')
    observations = LOAD(directory / 'observation-index.json')
    for event in observations:
        if event['kind'] in ('marker', 'wait-success'):
            text = (directory / event['serial_file']).read_bytes().decode()
            need(SHA(text.encode()) == event['serial_sha256'] and any(e['path'] == session_path + '/serial' and isinstance(body, dict) and body.get('data') == text for e, body, _, _ in actual), 'guest wait/marker lacks exact actual UART HTTP backing')
            need(0 <= event['offset'] <= len(text), 'original UART offset invalid')
            if event['kind'] == 'marker':
                need(has(text[event['offset']:], event['marker']), 'original marker absent from original offset suffix')
        elif event['kind'] == 'state':
            value = LOAD(directory / event['file'])
            need(backed(value, '/units', 'GET'), 'Unit/QOM state lacks actual HTTP backing')
            unit_state(value, row)
        elif event['kind'] == 'input':
            need(backed(event['before_cursor'], '/serial', 'GET') and backed(event['before_live_state'], '/units', 'GET'), 'input lower UART/QOM baseline lacks actual HTTP backing')
            if event['accepted'] is False:
                need(unit == 'rs485' and not event['via_ui'] and any(e['method'] == 'POST' and e['path'] == session_path + '/unit-input' and e['status'] in (400, 409, 422) and json.loads(req) == event['requested'] for e, _, _, req in actual), 'RS485 negative lacks actual raw API rejection')
        elif event['kind'] == 'qom':
            need(any(e['path'] == session_path + '/qom' and urllib.parse.parse_qs(e['query']) == {'path': [event['path']], 'property': [event['property']]} and isinstance(body, dict) and body.get('value') == event['value'] for e, body, _, _ in actual), 'raw scalar QOM value lacks actual HTTP backing')
    serial_response = LOAD(directory / 'final-serial-response.json')
    serial = (directory / 'serial-final.txt').read_bytes().decode()
    need(backed(serial_response, '/serial', 'GET') and serial_response['data'] == serial, 'final actual UART differs')
    host = LOAD(directory / 'host-observation.json')
    host_text = (directory / host['serial_file']).read_bytes().decode()
    need(backed(host['before_cursor'], '/serial', 'GET') and any(e['path'] == session_path + '/serial' and isinstance(body, dict) and body.get('data') == host_text for e, body, _, _ in actual), 'fresh post-IO onboard BMI interval lacks raw HTTP backing')
    browser = LOAD(batch / 'browser' / sid / 'web-report.json')
    need(all(browser[k] == result[k] for k in ('session_id', 'device_id', 'runtime', 'firmware_sha256')) and not browser['errors'], 'actual product browser identity/error differs')
    need(all(frozen.get(name) == digest for name, digest in browser['source_sha256'].items()), 'product browser source not frozen')
    snapshots = [snap for snap in browser['snapshots'] if snap.get('session_state') == 'running']
    need(snapshots, 'actual running DOM snapshot missing')
    for snap in snapshots:
        need({u['instance'] for u in snap['units']} == {a['id'] for a in row['attachments']}, 'actual DOM Unit topology differs')
        for u in snap['units']:
            values = u['readback']['properties']
            need(u['dom_matches_product_readback'] and u['readback_matches_real_http_response'] and any(any(v['id'] == u['instance'] and v['properties'] == values for v in event.get('response', {}).get('units', [])) for event in browser['readbacks'] + browser['posts']), 'DOM has no matching actual browser HTTP response')
            for key, value in values.items():
                cell = next(c for c in u['values'] if c['field'] == key)
                if key == 'led-rgb' and cell.get('rgb'):
                    need(cell['rgb'] == [f'LED[{i}] #{color:06x}' for i, color in enumerate(value if isinstance(value, list) else [value])], 'actual DOM LED chain differs')
                elif type(value) in (int, float):
                    need(float(cell['text']) == value, 'actual DOM numeric value differs')
                else:
                    text = json.dumps(value, separators=(',', ':'), ensure_ascii=False) if isinstance(value, (list, dict)) else str(value).lower() if isinstance(value, bool) else str(value)
                    need(cell['text'] == text, 'actual DOM property differs')
    positive = [e for e in observations if e['kind'] == 'input' and e['accepted'] is True]
    # Reuse the project's authoritative exact-field/time/no-op checker only as
    # an additional contract. UART semantics are rebuilt independently above.
    binding = host_module.positive_input_binding({**row, 'firmware_sha256': result['firmware_sha256']}, positive, browser, serial, result)
    if unit in ('fan', 'rgb'):
        need(not browser['actions'] and not browser['posts'] and not positive, 'output-only Unit has product input actions/POSTs')
    semantics = independent_semantics(directory, row, result, observations, serial)
    data = (directory / 'evidence.zip').read_bytes()
    need(SHA(data) == result['evidence_sha256'], 'evidence ZIP hash differs')
    original_module.validate_evidence(data, result)
    zip_events = [i for i, (e, _, raw, _) in enumerate(actual) if e['path'] == session_path + '/evidence' and raw == data and e['method'] == 'GET']
    need(len(zip_events) == 1 and zip_events[0] < stop[0][0] and urllib.parse.parse_qs(stop[0][1]['query']) == {'purge': ['0']}, 'evidence ZIP not before purge=0 stop')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        need(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'ZIP corrupted/duplicate')
        manifest = json.loads(archive.read('manifest.json'))
        need(set(manifest['files']) == set(archive.namelist()) - {'manifest.json'}, 'ZIP membership mismatch')
        for name, record in manifest['files'].items():
            need(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name, 'unsafe ZIP member')
            raw = archive.read(name)
            need(SHA(raw) == record['sha256'] and len(raw) == record['size'], 'ZIP member hash/size mismatch')
        session = manifest['session']
        need(session['state'] == 'running' and all(session[k] == result[k] for k in ('session_id', 'device_id', 'runtime', 'firmware_sha256')) and session['pid'] == proof['observed_pid'] and session['worker']['worker_id'] == proof['worker_id'] and session['worker']['generation'] == proof['worker_generation'] and session['worker']['lease_active'], 'ZIP active PID/worker/session identity differs')
        need(session['firmware_provenance'] == json.loads(archive.read('firmware/uiflow-source.json')) == source and session['source_artifacts'][0] == cas, 'ZIP source provenance/CAS differs')
        contract, state = (json.loads(archive.read(name)) for name in ('units/contract.json', 'units/state.json'))
        need(contract['source_hashes'] == state['contract_hashes'] and all(frozen['platform/units/' + name] == digest for name, digest in contract['source_hashes'].items()), 'ZIP Unit contract not frozen')
        unit_state(state, row)
        zip_serial = archive.read('serial.log').decode()
        need(zip_serial.startswith(serial), 'ZIP UART does not retain final actual serial prefix')
        zipped_frame = png(archive.read('frames/current.png'), device)
    history, stopped, health = (LOAD(directory / name) for name in ('retained-session.json', 'stop-response.json', 'cleanup-health.json'))
    need(backed(history, '/' + sid, 'GET') and backed(health, '/health', 'GET') and stopped == stop[0][2], 'cleanup lacks actual raw HTTP backing')
    need(history['state'] == stopped['state'] == 'stopped' and history['flash_retained'] is False and history['last_frame_available'] is True and history['worker']['lease_active'] is False and history['firmware_provenance'] == source, 'retained history/Flash/lease/source differs')
    need(result['cleanup'] == {'owned_pid': proof['observed_pid'], 'pid_gone': True, 'flash_retained': False, 'health_active_sessions': 0} and health['ok'] is True and health['capacity']['active_sessions'] == 0, 'saved owned PID/idle cleanup incomplete')
    running_raw, history_raw = (directory / name for name in ('frame.png', 'history-frame.png'))
    need(any(i < stop[0][0] and e['path'] == session_path + '/frame.png' and raw == running_raw.read_bytes() for i, (e, _, raw, _) in enumerate(actual)), 'running native frame lacks raw HTTP backing')
    need(any(i > stop[0][0] and e['path'] == session_path + '/frame.png' and raw == history_raw.read_bytes() for i, (e, _, raw, _) in enumerate(actual)), 'retained native frame was not fetched after stop')
    need(inventory(directory) == before, 'review changed original case artifacts')
    return {'device_id': device, 'unit_id': unit, 'status': 'PASS', 'batch': batch.name, 'session_id': sid,
            'source_context_commit': row['source_context_commit'], 'source_CAS': cas, 'firmware_SHA256': result['firmware_sha256'],
            'runtime_SHA256': proof['runtime_binary_sha256'], 'worker_generation': proof['worker_generation'], 'PID': proof['observed_pid'],
            'caller_python_files': 19, 'complete_original_IO_oracle_unchanged': True, 'original_ZIP_oracle_replayed': True,
            'independent_semantics': semantics, 'positive_input_binding': binding,
            'browser': {'running_snapshots': len(snapshots), 'actions': len(browser['actions']), 'posts': len(browser['posts'])},
            'ZIP_before_stop': True, 'history_frame_and_source_retained': True, 'mutable_Flash_released': True,
            'worker_lease_ended': True, 'owned_PID_exit': 'Verified saved runner observation; no new historical PID reprobe', 'service_idle': True,
            'frames': {'running': png(running_raw.read_bytes(), device), 'ZIP_current': zipped_frame, 'history': png(history_raw.read_bytes(), device)},
            'native_frame_readability': 'PENDING_SEPARATE_ACTUAL_VISUAL_INSPECTION',
            'original_case_artifacts_unchanged': True, 'original_case_inventory_SHA256': SHA(CANON(before))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='append', choices=('live-fan-r1', 'live-rest-r1'), required=True)
    parser.add_argument('--receipt-name', required=True)
    parser.add_argument('--final', action='store_true')
    args = parser.parse_args()
    need(Path(args.receipt_name).name == args.receipt_name and args.receipt_name.endswith('.json'), 'receipt must be a local JSON filename')
    output = HERE / args.receipt_name
    need(not output.exists(), 'never overwrite a completed review receipt')
    calls = []
    def denied(*a, **k):
        calls.append('forbidden call attempted')
        raise RuntimeError('independent offline audit forbids API/network/process/guest')
    sys.path[:0] = [str(ROOT / 'tests/units'), str(ROOT / 'platform/tools')]
    with ExitStack() as stack:
        for obj, name in ((urllib.request, 'urlopen'), (socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_output'), (os, 'system')):
            stack.enter_context(patch.object(obj, name, denied))
        import run_io_cases as original_module
        import run_host_io_cases as host_module
        stack.enter_context(patch.object(sys.modules['run_service_cases'].Client, '__init__', denied))
        results, batch_summaries = [], []
        for name in dict.fromkeys(args.batch):
            batch = AUTHOR / name
            need((batch / 'batch-result.json').is_file(), 'batch has no terminal result: ' + name)
            initial_inventory = inventory(batch)
            listed = {}
            for line in (batch / 'SHA256SUMS').read_text().splitlines():
                digest, filename = line.split('  ', 1)
                target = (batch / filename).resolve()
                need(filename not in listed and target.is_relative_to(batch.resolve()) and SHA(target.read_bytes()) == digest, 'original batch artifact checksum mismatch')
                listed[filename] = digest
            need(set(listed) == set(initial_inventory) - {'SHA256SUMS'}, 'original batch inventory differs from checksum manifest')
            batch_result, prepared = LOAD(batch / 'batch-result.json'), LOAD(batch / 'prepared.json')
            need(batch_result['status'] == 'PASS' and not batch_result['bridge_close_error'] and prepared['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC', 'batch not terminal PASS/current root source context')
            rows = prepared['cases']
            need(len(rows) == prepared['case_count'] == (3 if name == 'live-fan-r1' else 21), 'batch selection count mismatch')
            need({(r['device_id'], r['unit_id']) for r in rows} == ({(h, 'fan') for h in HOSTS} if name == 'live-fan-r1' else {(h, u) for h in HOSTS for u in UNITS if u != 'fan'}), 'Fan3/rest21 selection is not exact')
            frozen = LOAD(batch / 'tooling-source-freeze.json')
            for filename, digest in frozen.items():
                need(SHA((batch / 'source-snapshot' / (filename + '.txt')).read_bytes()) == digest, 'frozen source tooling snapshot changed')
            need(SHA(Path(original_module.__file__).read_bytes()) == frozen['tests/units/run_io_cases.py'] and SHA(Path(host_module.__file__).read_bytes()) == frozen['tests/units/run_host_io_cases.py'], 'authoritative oracle module differs from frozen execution source')
            need(host_module.preparation.protocol_audit()[0] == LOAD(batch / 'protocol-audit.json'), 'formal original initialization/loop/protocol/official-driver preservation differs')
            initial_health = LOAD(batch / 'initial-health.json')
            initial_event = LOAD(batch / 'batch-http/index.json')
            need(len(initial_event) == 1 and initial_health['ok'] is True and initial_health['capacity']['active_sessions'] == 0, 'batch startup health not idle')
            event = initial_event[0]
            raw = (batch / 'batch-http' / event['response_file']).read_bytes()
            need(event['path'] == '/api/v1/health' and event['method'] == 'GET' and event['response_sha256'] == SHA(raw) and json.loads(raw) == initial_health, 'batch initial idle health lacks actual raw backing')
            results.extend(audit_case(batch, row, frozen, original_module, host_module) for row in rows)
            need(inventory(batch) == initial_inventory, 'review modified original batch artifacts')
            batch_summaries.append({'batch': name, 'cases': len(rows), 'source_inventory_SHA256': SHA(CANON(initial_inventory)), 'original_files_unchanged': True})
    pairs = {(r['device_id'], r['unit_id']) for r in results}
    need(len(pairs) == len(results), 'duplicated host/Unit case; do not rerun/count Fan twice')
    pending = sorted(EXPECTED - pairs)
    if args.final:
        need(not pending and len(results) == 24, 'full24 not yet present; final review forbidden')
    need(not calls, 'offline audit attempted forbidden operation')
    report = {'status': 'PASS' if not pending else 'PENDING', 'scope': 'Independent actual raw source API/PID/UART/QOM/host/DOM/ZIP/cleanup audit; native visual review separately required.',
              'auditor_sha256': SHA(Path(__file__).read_bytes()),
              'expected_combinations': 24, 'reviewed_combinations': len(results), 'pending_combinations': [list(p) for p in pending],
              'batches': batch_summaries, 'cases': results, 'API_browser_guest_subprocess_calls_during_review': 0,
              'hardware_validation': 'NOT RUN', 'original_IR_Buzzer_ADC_scope': 'UNCHANGED_EXCLUDED',
              'limitations': ['Only exact firmware/controller/session/captured-frame scope; no hardware or continuous all-frame fidelity claim.',
                              'Original runtime PID exit is a saved runner observation, not a new historical PID live reprobe.']}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('status', 'expected_combinations', 'reviewed_combinations', 'pending_combinations', 'API_browser_guest_subprocess_calls_during_review')}, indent=2))


if __name__ == '__main__':
    main()
