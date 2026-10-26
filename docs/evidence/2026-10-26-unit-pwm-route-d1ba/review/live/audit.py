#!/usr/bin/env python3
"""Independent raw-evidence replay only. No API/process/guest or input mutation."""
from __future__ import annotations
import ast
from contextlib import ExitStack
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
SOURCE = ROOT / '.work/unit-pwm-route-acceptance-20261026'
SHA = lambda raw: hashlib.sha256(raw).hexdigest()
LOAD = lambda path: json.loads(path.read_bytes())
CANON = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
HOLD = re.compile(r'(?m)^PWMR_HOLD (\d+) (\d+) (\d+) (\d+)\r?$')
EXPECTED = {
    'baseline-r1': {'frequency': 0, 'status': 'FAIL_REPRODUCED', 'generation': 11,
                    'runtime': '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'},
    'candidate-r1': {'frequency': 2000, 'status': 'PASS', 'generation': 12,
                     'runtime': 'd1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff'},
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def inventory(directory):
    return {p.relative_to(directory).as_posix(): {'sha256': SHA(p.read_bytes()), 'size': p.stat().st_size}
            for p in sorted(directory.rglob('*')) if p.is_file()}


def png(raw):
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as image:
        image.load()
        require(image.format == 'PNG' and image.size == (320, 240), 'invalid native PNG')
        require(image.convert('RGB').getcolors(1) is None, 'single-color native frame')
    return {'sha256': SHA(raw), 'bytes': len(raw), 'native_size': [320, 240]}


def guest_source(files):
    require(set(files) == {'boot.py', 'main.py', 'probe_logging.py', 'probe_config.py', 'pwm_route_program.py'}, 'caller file set differs')
    constructors, getters, imports, aliases = [], [], [], []
    for filename, source in files.items():
        tree = ast.parse(source, filename=filename)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(x.name for x in node.names)
                aliases.extend(x.asname for x in node.names if x.asname)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module)
                aliases.extend(x.asname for x in node.names if x.asname)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'PWM':
                    constructors.append(ast.unparse(node))
                if isinstance(node.func, ast.Name):
                    require(node.func.id not in {'exec', 'eval', '__import__', 'getattr', 'setattr'}, 'dynamic code/attribute path in caller')
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'pwm':
                    require(node.func.attr in {'freq', 'duty_u16'} and not node.args and not node.keywords, 'post-construction PWM setter/operation')
                    getters.append(node.func.attr)
    require(not aliases and set(imports) == {'time', 'M5', 'machine', 'probe_logging', 'probe_config', 'io', 'sys', 'pwm_route_program'}, 'unexpected caller imports or aliases')
    require(constructors == ['PWM(Pin(PWM_GPIO), freq=PWM_FREQUENCY_HZ, duty_u16=0)'] and sorted(getters) == ['duty_u16', 'freq'], 'PWM constructor/getters differ')
    config = {node.targets[0].id: ast.literal_eval(node.value) for node in ast.parse(files['probe_config.py']).body}
    require(config == {'PWM_GPIO': 2, 'PWM_FREQUENCY_HZ': 2000, 'HOLD_MS': 60000, 'HEARTBEAT_MS': 250}, 'caller config differs')
    return {'pwm_constructor': constructors[0], 'post_constructor_PWM_setters': 0, 'getter_forms': getters,
            'BuzzerUnit_Haptic_SoftTimer_imported': False, 'configured_hold_ms': 60000, 'config': config,
            'scope': 'Caller source audit only; no dynamic native MMIO trace claimed.'}


def audit_case(tag):
    directory = SOURCE / tag
    before_inventory = inventory(directory)
    expected = EXPECTED[tag]
    listed = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        path = (directory / name).resolve()
        require(name not in listed and path.is_relative_to(directory.resolve()), 'duplicate/unsafe artifact checksum entry')
        require(SHA(path.read_bytes()) == digest, 'artifact checksum mismatch: ' + name)
        listed[name] = digest
    require(set(listed) == set(before_inventory) - {'SHA256SUMS'}, 'artifact inventory differs from checksums')
    result = LOAD(directory / 'result.json')
    require(result['status'] == result['initialization_status'] == expected['status'] and result['harness_check_status'] == 'PASS', 'result relabeled')
    require(not any(result.get(key) for key in ('error', 'evidence_error', 'cleanup_error', 'browser_error', 'bridge_close_error')), 'case recorded an execution error')
    request = LOAD(directory / 'source-request.json')
    require(request['device_id'] == 'cores3' and set(request) == {'device_id', 'files', 'expected_base_sha256'}, 'source request schema differs')
    caller_audit = guest_source(request['files'])
    require({p.relative_to(directory / 'files').as_posix() for p in (directory / 'files').rglob('*') if p.is_file()} == set(request['files']), 'saved caller file inventory differs')
    for name, text in request['files'].items():
        require((directory / 'files' / name).read_bytes() == text.encode() == (SOURCE / 'guest' / name).read_bytes(), 'caller source bytes changed')
    cas = SHA(CANON(request['files']))
    require(cas == result['source_cas_sha256'] and SHA(CANON(request)) == result['caller_request_sha256'], 'canonical source/request CAS differs')
    firmware = LOAD(directory / 'firmware-response.json')
    source = firmware['source']
    meta = source['metadata']
    require(source == result['source'] and source['kind'] == 'uiflow' and source['artifact_id'] == cas, 'source provenance identity differs')
    require(firmware['sha256'] == firmware['firmware_id'] == result['firmware_sha256'] == result['firmware_id'] == meta['firmware_sha256'], 'derived firmware identity differs')
    require(meta['base_sha256'] == request['expected_base_sha256'] == result['base_sha256'], 'reference firmware base differs')
    require(meta['source_sha256'] == meta['effective_source_sha256'] == cas and not meta['generated_files'], 'effective/caller source differs')
    entries = {item['path']: item for item in meta['files']}
    require(len(entries) == len(meta['files']) == len(request['files']) == meta['caller_file_count'] == 5, 'metadata caller count differs')
    for name, text in request['files'].items():
        require(entries[name]['origin'] == 'caller' and entries[name]['sha256'] == SHA(text.encode()) and entries[name]['size'] == len(text.encode()), 'source file readback metadata differs')
    require(all(meta['preservation'][key] is True for key in ('outside_vfs_unchanged', 'existing_files_readback_verified', 'source_readback_verified')), 'readback/preservation missing')
    require(meta['status'] == 'COMPOSED_NOT_EXECUTED' and meta['vfs']['source'] == 'actual-base-partition-table', 'source stage/VFS overclaimed')
    actual = []
    for index, event in enumerate(LOAD(directory / 'http/index.json')):
        request_raw = (directory / 'http' / event['request_file']).read_bytes()
        response_raw = (directory / 'http' / event['response_file']).read_bytes()
        require(len(response_raw) == event['response_size'] and SHA(response_raw) == event['response_sha256'], 'raw HTTP byte hash/size differs')
        require(urllib.parse.urlsplit(event['url']).hostname in {'127.0.0.1', 'localhost', '::1'}, 'HTTP escaped local service')
        try:
            payload = json.loads(response_raw)
        except (ValueError, UnicodeDecodeError):
            payload = None
        actual.append({'index': index, 'event': event, 'body': payload, 'raw': response_raw, 'request_raw': request_raw})
    sid = result['session_id']
    session_path = '/api/v1/sessions/' + sid
    mutations = [a for a in actual if a['event']['method'] != 'GET']
    require([(a['event']['method'], a['event']['path'], a['event']['query']) for a in mutations] == [('POST', '/api/v1/firmware/uiflow', ''), ('POST', '/api/v1/sessions', ''), ('DELETE', session_path, 'purge=0')], 'unexpected API mutation/binary upload/Unit input')
    require(json.loads(mutations[0]['request_raw']) == request and mutations[0]['body'] == firmware, 'source POST lacks actual raw request/response backing')
    startup = LOAD(directory / 'session-request.json')
    created = LOAD(directory / 'created-session.json')
    require(json.loads(mutations[1]['request_raw']) == startup and mutations[1]['body'] == created and created['session_id'] == sid, 'session creation lacks actual raw backing')
    require(startup['device_id'] == 'cores3' and startup['runtime'] == 'qemu' and startup['firmware_id'] == firmware['firmware_id'] and startup['uiflow_source_sha256'] == cas and startup['units'] == [{'id': 'external1', 'unit_id': 'buzzer', 'port_id': 'port-a'}], 'session source pin/topology differs')
    def backed(value, path, method='GET'):
        return [a for a in actual if a['event']['method'] == method and a['event']['path'] == path and a['body'] == value]
    proof = LOAD(directory / 'browser' / sid / 'runtime-provenance.json')
    require(proof == result['runtime_provenance'] and proof['status'] == 'VERIFIED' and proof['kind'] == 'direct-pid' and proof['runtime_binary_sha256'] == expected['runtime'] == result['expected_runtime_sha256'], 'runtime executable identity differs')
    require(proof['worker_generation'] == expected['generation'] == result['expected_worker_generation'] and type(proof['observed_pid']) is int and proof['observed_pid'] > 0 and proof['firmware_sha256'] == firmware['sha256'], 'runtime PID/worker/firmware differs')
    session_records = [a for a in actual if a['event']['path'] == session_path and a['event']['method'] == 'GET' and isinstance(a['body'], dict) and a['body'].get('state') == 'running']
    require(len(session_records) >= 2 and all(a['body']['pid'] == proof['observed_pid'] and a['body']['worker'] == {'worker_id': proof['worker_id'], 'generation': proof['worker_generation'], 'lease_active': True} and a['body']['firmware_provenance'] == source and a['body']['source_artifacts'][0] == cas for a in session_records), 'running PID/worker/source continuity differs')
    for name in ('ready-session.json', 'before-evidence-session.json'):
        require(backed(LOAD(directory / name), session_path), 'saved running session lacks raw backing')
    def serial_row(value):
        require(value['session_id'] == sid and value['offset'] == 0 and value['bytes'] == value['next_offset'] == len(value['data'].encode()), 'UART cursor/byte length differs')
        require('PWMR_READY\r\n' in value['data'] and 'PWMR_HOLD_DONE' not in value['data'], 'UART outside no-setter hold')
        require(not any(marker in value['data'] for marker in ('PWMR_FAIL', 'Traceback (most recent call last)', 'Guru Meditation', 'Rebooting...')), 'guest failure in no-setter window')
        rows = [tuple(map(int, item)) for item in HOLD.findall(value['data'])]
        require(rows and all(freq == 2000 and duty == 0 and 0 <= elapsed < 60000 for _, elapsed, freq, duty in rows), 'getter/hold heartbeat differs')
        require(all(left[0] < right[0] and left[1] < right[1] for left, right in zip(rows, rows[1:])), 'guest heartbeat ordering differs')
        return rows
    windows = []
    previous_after = -1
    for index in range(8):
        saved = result['samples'][index]
        ids = saved['http_indices']
        before, state, after = (LOAD(directory / f'samples/{index:02d}-{kind}.json') for kind in ('before', 'state', 'after'))
        require(previous_after < ids['before'] < ids['state'] < ids['after'], 'sample HTTP order/next-window boundary differs')
        for kind, value in (('before', before), ('state', state), ('after', after)):
            item = actual[ids[kind]]
            require(item['event']['method'] == 'GET' and item['event']['status'] == 200 and item['event']['path'] == session_path + ('/units' if kind == 'state' else '/serial') and item['body'] == value, 'sample lacks exact raw HTTP backing')
        prior_rows, later_rows = serial_row(before), serial_row(after)
        require(after['data'].startswith(before['data']) and after['next_offset'] > before['next_offset'], 'sample serial prefix reset/stale')
        fresh = [tuple(map(int, item)) for item in HOLD.findall(after['data'][len(before['data']):])]
        require(fresh and fresh[0][0] > prior_rows[-1][0] and fresh[-1] == later_rows[-1], 'no genuine fresh hold heartbeat after QOM sample')
        require(state['session_id'] == sid and state['state'] == 'running' and state['source'] == 'live' and state['contract_status'] == 'frozen' and len(state['units']) == 1, 'Unit/QOM identity differs')
        unit = state['units'][0]
        require(unit['id'] == 'external1' and unit['unit_id'] == 'buzzer' and unit['pins'] == {'yellow': 2, 'white': 1} and unit['source'] == 'guest-qom' and unit['available'] is True and not unit['errors'], 'Unit/QOM endpoint unavailable')
        props = unit['properties']
        frequency, duty = props['frequency-hz'], props['duty-pct']
        require(type(frequency) in (int, float) and math.isfinite(frequency) and abs(frequency - expected['frequency']) <= 1e-9 and duty == 0 and props['input-events'] == 0, 'actual initialized QOM frequency/duty/input differs')
        require(saved['frequency-hz'] == frequency and saved['duty-pct'] == duty and saved['fresh_uart_interval'] == [before['next_offset'], after['next_offset']], 'summary sample differs from actual evidence')
        windows.append({'sequence': index, 'HTTP_indices': ids, 'UART_lower': before['next_offset'], 'UART_upper': after['next_offset'],
                        'guest_sample_before': prior_rows[-1][0], 'guest_sample_after': later_rows[-1][0],
                        'guest_elapsed_before_ms': prior_rows[-1][1], 'guest_elapsed_after_ms': later_rows[-1][1],
                        'fresh_heartbeats': len(fresh), 'getter_frequency_hz': 2000, 'getter_duty_u16': 0,
                        'QOM_frequency_hz': frequency, 'QOM_duty_pct': duty, 'input_events': 0, 'output_transitions': props['output-transitions']})
        previous_after = ids['after']
    require(len(result['samples']) == len(windows) == 8, 'sample window count differs')
    require(len({w['output_transitions'] for w in windows}) == 1, 'frequency/duty observer changed across no-setter sample windows')
    browser = LOAD(directory / 'browser' / sid / 'web-report.json')
    require(browser['session_id'] == sid and browser['device_id'] == 'cores3' and browser['runtime'] == 'qemu' and browser['firmware_sha256'] == firmware['sha256'] and not browser['errors'] and not browser['posts'] and not browser['actions'], 'browser identity/error/zero-input contract differs')
    snapshots = [snap for snap in browser['snapshots'] if snap['session_state'] == 'running']
    require(len(snapshots) == 10 and browser['readbacks'], 'running DOM snapshots missing')
    for snap in snapshots:
        require(len(snap['units']) == 1, 'DOM topology differs')
        unit = snap['units'][0]
        props = unit['readback']['properties']
        require(unit['instance'] == 'external1' and unit['dom_matches_product_readback'] and unit['readback_matches_real_http_response'], 'DOM not actual product readback')
        require(any(event['method'] == 'GET' and event['path'] == session_path + '/units' and event['status'] == 200 and any(u['id'] == 'external1' and u['properties'] == props and u['source'] == 'guest-qom' for u in event['response']['units']) for event in browser['readbacks']), 'DOM lacks matching actual browser HTTP')
        for key, value in props.items():
            cell = next(cell for cell in unit['values'] if cell['field'] == key)
            require(float(cell['text']) == value if type(value) in (int, float) else cell['text'] == str(value).lower() if isinstance(value, bool) else cell['text'] == str(value), 'DOM visible property differs')
        require(props['frequency-hz'] == expected['frequency'] and props['duty-pct'] == 0, 'DOM frequency/duty differs')
    frozen = LOAD(directory / 'tooling-source-freeze.json')
    for name, digest in frozen.items():
        require(SHA((directory / 'source-snapshot' / (name + '.txt')).read_bytes()) == digest, 'frozen tooling snapshot changed')
    known_browser = {name: digest for name, digest in browser['source_sha256'].items() if name in frozen}
    require(known_browser and all(frozen[name] == digest for name, digest in known_browser.items()), 'browser frozen source hashes differ')
    zip_data = (directory / 'evidence.zip').read_bytes()
    require(SHA(zip_data) == result['evidence_sha256'], 'evidence ZIP identity differs')
    zip_event = next(a for a in actual if a['event']['method'] == 'GET' and a['event']['path'] == session_path + '/evidence' and a['raw'] == zip_data)
    stop_event = mutations[2]
    require(previous_after < zip_event['index'] < stop_event['index'], 'evidence ZIP not before actual stop')
    with zipfile.ZipFile(io.BytesIO(zip_data)) as archive:
        require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'ZIP corrupt/duplicate member')
        manifest = json.loads(archive.read('manifest.json'))
        require(set(manifest['files']) == set(archive.namelist()) - {'manifest.json'}, 'ZIP member inventory differs')
        for name, record in manifest['files'].items():
            require(not PurePosixPath(name).is_absolute() and '..' not in PurePosixPath(name).parts and '\\' not in name, 'unsafe ZIP member')
            raw = archive.read(name)
            require(len(raw) == record['size'] and SHA(raw) == record['sha256'], 'ZIP inner member hash/length differs')
        session = manifest['session']
        require(session['state'] == 'running' and session['session_id'] == sid and session['device_id'] == 'cores3' and session['runtime'] == 'qemu' and session['pid'] == proof['observed_pid'] and session['firmware_sha256'] == firmware['sha256'], 'ZIP running session identity differs')
        require(session['worker'] == {'worker_id': proof['worker_id'], 'generation': expected['generation'], 'lease_active': True} and session['firmware_provenance'] == json.loads(archive.read('firmware/uiflow-source.json')) == source and session['source_artifacts'][0] == cas, 'ZIP worker/source pin differs')
        contract, unit_state = (json.loads(archive.read(name)) for name in ('units/contract.json', 'units/state.json'))
        require(contract['source_hashes'] == unit_state['contract_hashes'] == LOAD(directory / 'samples/00-state.json')['contract_hashes'], 'ZIP Unit contract hash binding differs')
        for name, digest in contract['source_hashes'].items():
            require(frozen['platform/units/' + name] == digest, 'ZIP Unit contract not frozen to exact source')
        require(contract['profiles']['buzzer']['inputs'] == {} and json.loads(archive.read('units/runtime.json'))['attachments'][0]['pins'] == {'yellow': 2, 'white': 1}, 'ZIP Unit output-only profile/wiring differs')
        zip_serial = archive.read('serial.log').decode()
        final_serial = LOAD(directory / 'final-serial-response.json')
        require(backed(final_serial, session_path + '/serial') and zip_serial.startswith(final_serial['data']), 'final/ZIP serial continuity differs')
        zip_rows = serial_row({'session_id': sid, 'offset': 0, 'next_offset': len(zip_serial.encode()), 'bytes': len(zip_serial.encode()), 'data': zip_serial})
        require(zip_serial.startswith(LOAD(directory / 'samples/07-after.json')['data']), 'ZIP does not retain sampled UART')
        zipped_frame = png(archive.read('frames/current.png'))
        qom_snapshot = json.loads(archive.read('qom/snapshot.json'))
        qom_truncated = bool(qom_snapshot['nodes'].get('__truncated__'))
    history, stopped, health, initial = (LOAD(directory / name) for name in ('retained-session.json', 'stop-response.json', 'cleanup-health.json', 'initial-health.json'))
    require(backed(history, session_path) and stopped == stop_event['body'] and backed(health, '/api/v1/health') and backed(initial, '/api/v1/health'), 'history/stop/health lack actual raw backing')
    require(history['state'] == stopped['state'] == 'stopped' and history['flash_retained'] is False and history['last_frame_available'] is True and history['worker']['lease_active'] is False and history['firmware_provenance'] == source and history['firmware_sha256'] == firmware['sha256'], 'history/Flash/frame/source/lease differs')
    require(initial['ok'] is True and initial['capacity']['active_sessions'] == 0 and health['ok'] is True and health['capacity']['active_sessions'] == 0 and result['cleanup'] == {'pid': proof['observed_pid'], 'pid_gone': True, 'flash_retained': False, 'active_sessions': 0}, 'owned PID/idle cleanup record differs')
    running_frame, history_frame = (directory / name for name in ('frame.png', 'history-frame.png'))
    require(any(a['index'] < stop_event['index'] and a['event']['path'] == session_path + '/frame.png' and a['raw'] == running_frame.read_bytes() for a in actual), 'running native frame lacks actual HTTP backing')
    require(any(a['index'] > stop_event['index'] and a['event']['path'] == session_path + '/frame.png' and a['raw'] == history_frame.read_bytes() for a in actual), 'history native frame not actually fetched after stop')
    require(inventory(directory) == before_inventory, 'review changed source evidence')
    return {'batch': tag, 'independent_review': 'PASS_WITH_SCOPE_LIMITS', 'observed_result': expected['status'],
            'session_id': sid, 'firmware_sha256': firmware['sha256'], 'caller_cas_sha256': cas,
            'request_canonical_sha256': SHA(CANON(request)), 'request_file_sha256': SHA((directory / 'source-request.json').read_bytes()),
            'effective_source_sha256': meta['effective_source_sha256'], 'runtime_sha256': expected['runtime'], 'worker_generation': expected['generation'],
            'owned_pid': proof['observed_pid'], 'guest_audit': caller_audit, 'sample_windows': windows,
            'guest_elapsed_sampling_bounds_ms': [windows[0]['guest_elapsed_before_ms'], windows[-1]['guest_elapsed_after_ms']],
            'last_ZIP_heartbeat': list(zip_rows[-1]), 'HTTP_events': len(actual), 'API_Unit_input_POSTs': 0,
            'browser': {'running_snapshots': len(snapshots), 'readbacks': len(browser['readbacks']), 'actions': 0, 'posts': 0},
            'ZIP': {'sha256': SHA(zip_data), 'members': len(manifest['files']) + 1, 'before_stop': True,
                    'GET_HTTP_index': zip_event['index'], 'DELETE_HTTP_index': stop_event['index'], 'QOM_snapshot_truncated': qom_truncated,
                    'QOM_Unit_endpoint_source': 'Frozen UnitRegistry.state calls qom(/machine/units/external1, descriptor.property); per-window actual /units is authoritative for fields outside truncated generic snapshot.'},
            'cleanup': {'history_retained': True, 'source_and_frame_retained': True, 'mutable_flash_released': True,
                        'owned_PID_exit_recorded': True, 'worker_lease_ended': True, 'service_idle': True,
                        'PID_exit_independent_live_reprobe': 'NOT PERFORMED; historical process exit is a saved runner observation'},
            'frames': {'running': png(running_frame.read_bytes()), 'ZIP_current': zipped_frame, 'history': png(history_frame.read_bytes())},
            'startup_warning': 'i2c.master port not initialized before PWMR_READY appears in both batches; no guest exception markers in reviewed hold interval.',
            'source_files_unchanged': True, 'source_inventory_sha256': SHA(CANON(before_inventory)), 'source_artifact_files': len(before_inventory)}


def main():
    output = HERE / 'independent-live-review.json'
    require(not output.exists(), 'review result already frozen')
    calls = []
    def denied(*args, **kwargs):
        calls.append('forbidden operation attempted')
        raise RuntimeError('independent offline review forbids network/API/process/guest execution')
    with ExitStack() as stack:
        for obj, name in ((urllib.request, 'urlopen'), (socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_output'), (os, 'system')):
            stack.enter_context(patch.object(obj, name, denied))
        rows = [audit_case(name) for name in EXPECTED]
        require(len({r['firmware_sha256'] for r in rows}) == len({r['caller_cas_sha256'] for r in rows}) == len({r['request_canonical_sha256'] for r in rows}) == len({r['request_file_sha256'] for r in rows}) == len({r['effective_source_sha256'] for r in rows}) == 1, 'A/B firmware/source/request bytes differ')
        require(rows[0]['runtime_sha256'] != rows[1]['runtime_sha256'] and rows[0]['worker_generation'] != rows[1]['worker_generation'], 'A/B runtime/worker did not change')
        sys.path.insert(0, str(SOURCE))
        spec = importlib.util.spec_from_file_location('supplemental_pwm_acceptance', SOURCE / 'run_acceptance.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        supplemental = {name: module.check_saved((SOURCE / name).resolve()) for name in EXPECTED}
    require(not calls, 'offline audit attempted prohibited operations')
    report = {'status': 'PASS_WITH_SCOPE_LIMITS', 'cases': rows, 'supplemental_original_check_saved': supplemental,
              'actual_API_browser_guest_subprocess_calls_during_review': 0, 'original_files_modified': False,
              'conclusion': 'Identical raw-PWM caller/request/effective source/derived firmware reproduces old-runtime initialization observer 0 Hz and candidate 2000 Hz at exact zero duty in eight fresh ordered windows each.',
              'limits': ['Only sampled no-setter initialization windows; not a completed 60000 ms hold or earliest post-constructor instant continuous proof.',
                         'Caller PWM setters absent; native getter/source reasoning is static and not a dynamic MMIO trace.',
                         'Generic ZIP QOM snapshot is node-limited/truncated; per-window actual /units QOM reads carry the frequency/duty evidence.',
                         'Raw PWM diagnostic does not close original BuzzerUnit.once callback/timer risk, complete waveform-period semantics, full shared-runtime regression, or hardware/acoustic/electrical behavior.',
                         'Native PNG readability is assessed separately for exact captured bytes; frames show getter 2000 Hz in both batches and do not themselves classify route QOM.']}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'cases': [{k: row[k] for k in ('batch', 'observed_result', 'guest_elapsed_sampling_bounds_ms', 'runtime_sha256', 'worker_generation')} for row in rows], 'API_process_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
