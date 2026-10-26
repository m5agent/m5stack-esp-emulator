#!/usr/bin/env python3
"""Run prepared device-local controls through visible Device Service + Web sessions.

Default is offline preflight; only --execute contacts the service. Preparation
source and toolchain changes require a fresh preparation; old results confer no PASS."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import select
import shutil
import sys
import time
from unittest.mock import patch
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'platform/tools'))
sys.path.insert(0, str(ROOT / 'tests/units'))
import run_control_cases as controls  # noqa: E402
from check_batch_evidence import Checker  # noqa: E402
from run_service_cases import Client, png_metrics, wait_for  # noqa: E402
from unit_runtime import UnitRegistry, UnitError  # noqa: E402
from web_ui_bridge import WebUIBridge  # noqa: E402
import prepare_host_controls as preparation  # noqa: E402

DEVICES = ('atoms3r', 'sticks3', 'stopwatch')
CASES = ('joystick-v11', 'encoder', '8encoder', 'cardkb', 'rfid2')
REQUIRED_PREPARATION = {'tests/uiflow2/lib/rtc_probe.py', 'tests/uiflow2/esp_flash.py',
    'tests/uiflow2/run_profile_ui_test.py', 'tests/units/run_control_cases.py',
    'tests/units/run_service_cases.py', 'platform/tools/firmware_analysis.py'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def display_contract(record):
    profile, layout = record['host_profile'], record['layout_preflight']
    assert layout == preparation.layout_preflight(profile, record['unit_id'], record['device_id']), 'prepared display configuration differs'
    values = [layout[key] for key in ('x', 'y', 'width', 'body_y', 'line_height', 'body_rows', 'bottom')]
    contract = {'expected_native_frame_size': profile['size'], 'expected_canvas_size': profile['canvas_size'],
        'expected_font': {'name': profile['font_name'], 'size': profile['text_size'], 'height': profile['font_height']},
        'expected_headers': layout['headers'],
        'expected_layout_marker': 'HOST_CONTROL_LAYOUT ' + ' '.join(map(str, [*values, len(layout['headers'])]))}
    contract['configuration_sha256'] = sha(json.dumps(contract, sort_keys=True).encode())
    return contract


def verify_display_markers(serial, record):
    contract = display_contract(record)
    def single(name):
        lines = [line.rstrip('\r') for line in serial.splitlines() if line.startswith(name)]
        assert len(lines) == 1, 'missing, duplicate or malformed guest display marker: ' + name
        tokens = lines[0].split()
        assert tokens[0] == name, 'malformed guest display marker: ' + name
        return tokens
    default = single('HOST_CONTROL_DEFAULT_FONT_HEIGHT')
    assert len(default) == 2 and re.fullmatch('[1-9][0-9]*', default[1])
    observed = single('HOST_CONTROL_FONT')
    expected = contract['expected_font']
    assert len(observed) == 4 and observed[1] == expected['name'], 'guest selected another font'
    scale = float(observed[2])
    assert math.isfinite(scale) and math.isclose(scale, expected['size'], rel_tol=0, abs_tol=1e-6), 'guest font scale differs'
    assert re.fullmatch('[1-9][0-9]*', observed[3]) and int(observed[3]) == expected['height'], 'guest font height differs'
    assert single('HOST_CONTROL_LAYOUT') == contract['expected_layout_marker'].split(), 'guest native layout differs'
    assert not any(error in serial for error in ('CONTROL_PROBE_ERROR', 'HOST_CONTROL_FAIL',
        'Traceback (most recent call last)', 'Guru Meditation', 'Rebooting...')), 'guest error in display evidence'
    return {'font_name': observed[1], 'font_scale': scale, 'font_height': int(observed[3]),
            'default_font_height_observed': int(default[1]),
            'layout_marker': contract['expected_layout_marker'], 'display_configuration_sha256': contract['configuration_sha256']}


def full_vfs(image, record):
    """Independent complete Python membership/hash check; never execute guest code."""
    import littlefs
    raw = image.read_bytes()
    assert sha(raw) == record['firmware_sha256'], 'prepared firmware bytes differ'
    layout = record['reference_layout']
    offset, size = layout['offset'], layout['size']
    fs = littlefs.LittleFS(context=littlefs.UserContext(buffer=bytearray(raw[offset:offset + size])),
        block_size=4096, block_count=size // 4096, read_size=128, prog_size=32,
        lookahead_size=128, block_cycles=100, mount=False)
    fs.mount()
    result = {}
    try:
        def visit(directory):
            for entry in fs.scandir(directory):
                name = directory.rstrip('/') + '/' + entry.name
                if entry.type == 2:
                    visit(name)
                elif entry.type == 1:
                    with fs.open(name, 'rb') as stream:
                        result[name.lstrip('/')] = sha(stream.read())
                else:
                    raise AssertionError('unknown VFS entry type')
        visit('/')
    finally:
        fs.unmount()
    expected = record.get('packaged_full_py_sha256')
    assert isinstance(expected, dict) and expected, 'full packaged file whitelist is required'
    assert result == expected, 'VFS contains missing, unknown or changed file bytes'
    assert 'rtc_probe.py' in result, 'shared-builder common injection must be explicit'
    return result


def preparation_module():
    return preparation


def toolchain_preflight(readiness):
    import littlefs
    paths, current = preparation_module().freeze_toolchain(littlefs)
    assert current == readiness['toolchain'], 'packaging/verification ABI or toolchain changed'
    assert {'littlefs/__init__.py', 'littlefs/context.py', 'littlefs/errors.py',
            'littlefs-native-extension', 'python-interpreter'} <= set(current['files'])
    return paths, current





def preparation_continuity(prepared, report):
    original = report['source_sha256']
    assert isinstance(original, dict) and REQUIRED_PREPARATION <= set(original), 'preparation freeze omits a direct packager/common dependency'
    paths, _ = preparation.source_paths()
    assert {path.relative_to(ROOT).as_posix() for path in paths} == set(original), 'preparation source inventory changed; prepare again'
    for name, expected in original.items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT), 'prepared source escapes repository'
        snapshot = prepared / 'source-snapshot' / (name + '.txt')
        assert snapshot.is_file() and sha(snapshot.read_bytes()) == expected, 'preparation snapshot missing or changed: ' + name
        assert sha(path.read_bytes()) == expected, 'prepared source changed; prepare again: ' + name
    return {'source_sha256': original, 'status': 'EXACT_CURRENT_SOURCE_MATCH', 'allowed_changes': []}


def select_cases(readiness, device='all', case='all'):
    assert readiness.get('schema_version') == 1 and readiness.get('status') == 'PREPARED_NOT_EXECUTED', 'preparation is incomplete or has another schema'
    rows, selection = readiness.get('cases'), readiness.get('selection', {})
    assert isinstance(rows, list) and type(readiness.get('case_count')) is int and readiness['case_count'] == len(rows), 'prepared case count differs'
    devices, cases = selection.get('devices'), selection.get('cases')
    assert isinstance(devices, list) and devices and len(devices) == len(set(devices)) and set(devices) <= set(DEVICES), 'invalid prepared device selection'
    assert isinstance(cases, list) and cases and len(cases) == len(set(cases)) and set(cases) <= set(CASES), 'invalid prepared Unit selection'
    pairs = [(row['device_id'], row['unit_id']) for row in rows]
    assert len(pairs) == len(set(pairs)) and set(pairs) == {(host, unit) for host in devices for unit in cases}, 'prepared selection has missing, duplicate or unexpected cases'
    assert all(row.get('status') == 'PREPARED_NOT_EXECUTED' and row.get('runtime') == 'qemu' for row in rows), 'prepared case status/runtime differs'
    requested = {(host, unit) for host in (DEVICES if device == 'all' else (device,))
                 for unit in (CASES if case == 'all' else (case,))}
    assert requested <= set(pairs), 'requested host/Unit selection is not completely prepared'
    return [row for row in rows if (row['device_id'], row['unit_id']) in requested]


def validate_prepared_files(prepared, record):
    directory = prepared / record['device_id'] / record['unit_id']
    assert json.loads((directory / 'prepared.json').read_text()) == record, 'case metadata differs from readiness'
    files = directory / 'files'
    paths = list(files.rglob('*'))
    assert files.is_dir() and not any(path.is_symlink() for path in paths), 'prepared guest tree is unavailable or aliased'
    actual = {path.relative_to(files).as_posix(): sha(path.read_bytes()) for path in paths if path.is_file()}
    assert actual == record['prepared_file_sha256'], 'prepared guest file tree changed'
    assert {name: value for name, value in actual.items() if name.endswith('.py')} == record['probe_sha256'], 'prepared Python membership/hash differs'
    image = directory / 'uiflow2-ui-test.bin'
    assert sha(image.read_bytes()) == record['firmware_sha256'], 'prepared firmware bytes differ'
    return image


class DeadlineBridge(WebUIBridge):
    command_timeout = 240
    shutdown_timeout = 15

    def __init__(self, url):
        self.dead = False
        self._response_buffer = bytearray()
        super().__init__(url)

    def call(self, command, **values):
        if self.dead or self.process.poll() is not None:
            raise RuntimeError('browser transport unavailable')
        self.process.stdin.write(json.dumps({'command': command, **values}, allow_nan=False) + '\n')
        self.process.stdin.flush()
        timeout = self.shutdown_timeout if command == 'shutdown' else self.command_timeout
        deadline = time.monotonic() + timeout
        # Bound the entire JSON line, including a peer that sends one byte and
        # then stalls. No TextIO.readline() may outlive this command deadline.
        while b'\n' not in self._response_buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                self.dead = True
                self.process.terminate()
                raise RuntimeError(f'browser transport command exceeded {timeout}s: {command}')
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                self.dead = True
                raise RuntimeError('browser transport closed without acknowledgement')
            self._response_buffer.extend(chunk)
            if len(self._response_buffer) > 4 << 20:
                self.dead = True
                self.process.terminate()
                raise RuntimeError('browser acknowledgement exceeded bounded size')
        end = self._response_buffer.index(b'\n') + 1
        line = bytes(self._response_buffer[:end])
        del self._response_buffer[:end]
        response = json.loads(line)
        if not response.get('ok'):
            raise RuntimeError(response.get('error', 'browser action failed'))
        return response.get('result')


class HostClient(Client):
    def __init__(self, url, record):
        super().__init__(url)
        self.record = record
        self.web_ui = DeadlineBridge(url)
        self.host_checks, self.host_errors, self.fresh_inputs = {}, [], []
        self.owned_session_ids = []
        self.stop_order = []
        self.cleanup_errors = []

    def serial_now(self, sid):
        return self.json(f'sessions/{sid}/serial?limit=262144', via_ui=False)['data']

    def verify_host(self, sid):
        serial = self.serial_now(sid)
        profile = self.record['host_profile']
        def marker(text):
            assert re.search(r'(?m)^' + re.escape(text) + r'\r?$', serial), 'missing real guest marker: ' + text
        marker('HOST_CONTROL_GEOMETRY %d %d %d' % (*profile['canvas_size'], profile['rotation']))
        marker('HOST_CONTROL_INTERNAL before 36 1')
        marker('HOST_CONTROL_INTERNAL after_init 36 2')
        address = {'joystick-v11': 82, 'encoder': 64, '8encoder': 65, 'cardkb': 95, 'rfid2': 40}[self.record['unit_id']]
        marker('HOST_CONTROL_EXTERNAL_SCAN %d' % address)
        marker('HOST_CONTROL_EXTERNAL_AFTER_INIT %d' % (66 if self.record['unit_id'] == '8encoder' else address))
        offset = len(serial)
        serial = wait_for(self, sid, lambda text: bool(re.search(
            r'(?m)^HOST_CONTROL_INTERNAL after_op 36 ([3-9]|[1-9][0-9]+)\r?$', text[offset:])), 10)
        display = verify_display_markers(serial, self.record)
        assert not any(failure in serial for failure in ('CONTROL_PROBE_ERROR', 'HOST_CONTROL_FAIL', 'Traceback (most recent call last)', 'Guru Meditation'))
        self.host_checks = {'canvas_geometry': True, 'internal_bmi_before_after_init': True,
            'external_scan_and_address_change': True, 'fresh_internal_after_all_control_assertions': True,
            'no_guest_exception': True, 'fresh_after_op_offset': offset, 'strict_display_contract': display}

    def raw(self, path, method='GET', **kwargs):
        parts = path.split('?')[0].split('/')
        if method == 'POST' and len(parts) == 3 and parts[2] == 'unit-input':
            self.fresh_inputs.append({'serial_offset_before_ui': len(self.serial_now(parts[1])),
                                      'requested': kwargs.get('payload')})
        if method == 'GET' and len(parts) == 3 and parts[2] == 'evidence':
            try:
                self.verify_host(parts[1])
            except Exception as error:
                self.host_errors.append(str(error))
            self.stop_order.append('evidence-request-before-stop')
            if self.web_ui.dead:
                bridge, self.web_ui = self.web_ui, None
                try:
                    return super().raw(path, method=method, **kwargs)
                finally:
                    self.web_ui = bridge
        if method == 'DELETE' and len(parts) == 2 and parts[0] == 'sessions':
            self.stop_order.append('stop-purge-zero')
        data = super().raw(path, method=method, **kwargs)
        if method == 'POST' and path == 'sessions':
            self.owned_session_ids.append(json.loads(data)['session_id'])
        return data


def execution_sources(report):
    # Preparation already freezes the full current Web and local import graph.
    return sorted(ROOT / name for name in report['source_sha256'])


def run_one(args, original, prepared_root, output):
    directory = output / original['device_id'] / original['unit_id']
    directory.mkdir(parents=True, exist_ok=False)
    source = prepared_root / original['device_id'] / original['unit_id']
    os.environ['M5_UNIT_WEB_BRIDGE_OUT'] = str(directory / 'browser')
    client = HostClient(args.api_url, original)
    def inject_prepared(options, case):
        assert options.device == original['device_id'] and case == original['unit_id']
        validate_prepared_files(prepared_root, original)
        destination = directory / 'controller' / case
        destination.mkdir(parents=True, exist_ok=False)
        image = destination / 'uiflow2-ui-test.bin'
        shutil.copyfile(source / 'uiflow2-ui-test.bin', image)
        shutil.copytree(source / 'files', destination / 'files')
        actual_files = {str(path.relative_to(destination / 'files')): sha(path.read_bytes())
                        for path in (destination / 'files').rglob('*.py')}
        assert actual_files == original['probe_sha256'], 'prepared guest file tree changed'
        full_vfs(image, original)
        record = {**copy.deepcopy(original), 'category': 'virtual-device-validation', 'status': 'PREPARED',
                  'expected_size': original['host_profile']['size'], 'checks': {},
                  'firmware_flavor': 'reference-app-with-vendored-official-control-drivers-host-probe'}
        hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_text())['hosts']
        host = next(row for row in hosts if row['device_id'] == original['device_id'])
        port = next(row for row in host['ports'] if row['id'] == original['attachments'][0]['port_id'])
        return destination, image, port, record
    result = {'status': 'FAIL'}
    try:
        # Only the packaging callback is injected. Every original CONTROL test,
        # input, wait, readback and ZIP-before-stop/finally statement runs intact.
        with patch.object(controls, 'prepare', inject_prepared):
            result = controls.run_case(client, argparse.Namespace(device=original['device_id'],
                out_dir=directory / 'controller', prepare_only=False), original['unit_id'])
    except Exception as error:
        result['error'] = str(error)
    finally:
        try:
            client.web_ui.close()
        except Exception as error:
            client.cleanup_errors.append('browser transport close failed: ' + str(error))
        # Only this client's explicit lease IDs may be cleaned up. A failed
        # browser/DELETE must not hide a live owned process behind a failed test.
        plain = Client(args.api_url)
        for owned in client.owned_session_ids:
            try:
                state = plain.json(f'sessions/{owned}')['state']
            except Exception as error:
                state = None
                client.cleanup_errors.append('owned lease state could not be confirmed: ' + str(error))
            if state not in {'stopped', 'failed'}:
                try:
                    try:
                        (directory / 'emergency-evidence.zip').write_bytes(plain.raw(f'sessions/{owned}/evidence'))
                    finally:
                        plain.json(f'sessions/{owned}?purge=0', method='DELETE')
                    client.cleanup_errors.append('owned lease required emergency stop; result remains FAIL')
                except Exception as error:
                    client.cleanup_errors.append(str(error))
    sid = result.get('session_id')
    web_path = directory / 'browser' / str(sid) / 'web-report.json'
    web = json.loads(web_path.read_text()) if web_path.is_file() else {}
    proof_path = web_path.with_name('runtime-provenance.json')
    proof = json.loads(proof_path.read_text()) if proof_path.is_file() else {}
    checks = {'original_control_assertions': result.get('status') == 'PASS',
        'host_observations': bool(client.host_checks) and not client.host_errors,
        'actual_web': bool(web.get('snapshots')) and not web.get('errors'),
        'same_host_session_firmware': all(web.get(key) == result.get(key) == original.get(key)
            for key in ('device_id', 'firmware_sha256', 'runtime')) and web.get('session_id') == sid,
        'positive_inputs_used_product_posts': bool(client.fresh_inputs) and bool(web.get('posts')),
        'no_emergency_cleanup_needed': not client.cleanup_errors,
        'retained_stopped_history': False,
        'flash_released_by_default': False,
        'zip_requested_before_stop': client.stop_order[:2] == ['evidence-request-before-stop', 'stop-purge-zero']}
    report = {'schema_version': 1, 'category': 'virtual-device-browser-host-controls', 'status': 'FAIL',
        'device_id': original['device_id'], 'unit_id': original['unit_id'], 'runtime': 'qemu', 'session_id': sid,
        'firmware_sha256': result.get('firmware_sha256'), 'evidence_sha256': result.get('evidence_sha256'),
        'firmware_flavor': result.get('firmware_flavor'),
        'checks': checks, 'host_observations': client.host_checks, 'host_errors': client.host_errors,
        'fresh_inputs': client.fresh_inputs, 'runtime_provenance': proof, 'hardware_execution': 'NOT RUN',
        'cleanup_errors': client.cleanup_errors, 'controller_error': result.get('error'),
        'native_readability': 'NOT REVIEWED',
        'controller_result': f"controller/{original['unit_id']}/result.json",
        'browser_report': str(web_path.relative_to(directory)), 'evidence': f"controller/{original['unit_id']}/evidence.zip"}
    try:
        plain = Client(args.api_url)
        history_body = plain.raw(f'sessions/{sid}')
        (directory / 'history.json').write_bytes(history_body)
        history = json.loads(history_body)
        checks['retained_stopped_history'] = history.get('state') == 'stopped' and history.get('firmware_sha256') == result.get('firmware_sha256')
        checks['flash_released_by_default'] = history.get('flash_retained') is False
        assert checks['retained_stopped_history'], 'history must retain the same firmware in stopped state'
        assert checks['flash_released_by_default'], 'default stop must explicitly release virtual Flash'
        frame = plain.raw(f'sessions/{sid}/frame.png')
        metrics = png_metrics(frame)
        assert [metrics['width'], metrics['height']] == original['host_profile']['size'] and metrics['unique_colors'] > 1
        (directory / 'history-frame.png').write_bytes(frame)
        checks['retained_history_and_native_frame'] = True
        health_body = plain.raw('health')
        (directory / 'history-health.json').write_bytes(health_body)
        checks['active_zero_after_case'] = json.loads(health_body)['capacity']['active_sessions'] == 0
    except Exception as error:
        checks['retained_history_and_native_frame'] = False
        report['history_error'] = str(error)
    report['artifact_sha256'] = {str(path.relative_to(directory)): sha(path.read_bytes()) for path in sorted(directory.rglob('*'))
        if path.is_file() and path.suffix != '.bin' and 'files' not in path.parts}
    try:
        checker = Checker(directory)
        manifest, count = checker.zip_manifest(directory / report['evidence'], report, original['unit_id'])
        assert manifest['session']['device_id'] == original['device_id']
        report['strict_runtime_proof'] = checker.direct_record(proof, manifest['session'], original['unit_id'], args.expected_runtime_sha256)
        worker = manifest['session'].get('worker', {})
        assert proof.get('worker_id') and proof['worker_id'] == worker.get('worker_id')
        assert type(proof.get('worker_generation')) is int and proof['worker_generation'] == worker.get('generation')
        verified = checker.artifacts(report, {}, directory / 'report.json')
        report['strict_controller_detail'] = checker.controller_detail(report, directory / 'report.json', verified)
        report['strict_browser_detail'] = checker.browser_detail(report, directory / 'report.json', verified, manifest)
        report['zip_members'] = count
        checks['strict_zip_host_pid_worker_browser_binding'] = True
    except Exception as error:
        checks['strict_zip_host_pid_worker_browser_binding'] = False
        report['strict_error'] = str(error)
    report['status'] = 'PASS' if all(checks.values()) else 'FAIL'
    write_json(directory / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir', type=Path, required=True)
    parser.add_argument('--device', choices=(*DEVICES, 'all'), default='all')
    parser.add_argument('--case', choices=(*CASES, 'all'), default='all')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--api-url', default='http://127.0.0.1:8787')
    parser.add_argument('--expected-runtime-sha256')
    args = parser.parse_args()
    if args.execute and (not args.out_dir or not re.fullmatch('[a-f0-9]{64}', args.expected_runtime_sha256 or '')):
        parser.error('--execute requires a fresh --out-dir and exact --expected-runtime-sha256')
    prepared = args.prepared_dir.resolve()
    readiness = json.loads((prepared / 'readiness.json').read_text())
    continuity = preparation_continuity(prepared, readiness)
    toolchain_paths, toolchain = toolchain_preflight(readiness)
    selected = select_cases(readiness, args.device, args.case)
    registry = UnitRegistry()
    blocked = []
    for row in selected:
        full_vfs(validate_prepared_files(prepared, row), row)
        display_contract(row)
        try:
            registry.attachments(row['device_id'], 'qemu', row['attachments'])
        except UnitError as error:
            blocked.append({'device_id': row['device_id'], 'unit_id': row['unit_id'], 'code': error.code})
    if not args.execute:
        print(json.dumps({'status': 'PREFLIGHT_ONLY', 'selected_cases': len(selected), 'blocked_admission': blocked,
            'api_contacted': False, 'sessions_started': 0, 'execution_freeze': 'NOT TAKEN; --execute freezes the exact current preparation sources',
            'preparation_source_count': len(readiness['source_sha256']), 'source_continuity': continuity['status']}, ensure_ascii=False))
        return 0
    assert not blocked, 'selected host/Unit combinations are not admitted by the current registry'
    assert os.environ.get('M5_UNIT_WEB_BRIDGE') != '1', 'this wrapper owns the explicit Web bridge'
    assert urlparse(args.api_url).hostname in {'127.0.0.1', 'localhost', '::1'}
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT / '.work'), 'execution output must use a fresh private .work path'
    output.mkdir(parents=True, exist_ok=False)
    frozen = {}
    freeze_paths = execution_sources(readiness)
    freeze_paths += [prepared / name for name in ('readiness.json', 'source-before.json', 'source-dependencies.json',
                                                'toolchain-before.json')]
    for path in freeze_paths:
        name, data = path.relative_to(ROOT).as_posix(), path.read_bytes()
        frozen[name] = sha(data)
        if path.suffix.lower() in {'.py', '.js', '.mjs', '.css', '.html', '.json', '.md', '.yaml', '.txt'}:
            target = output / 'source-snapshot' / (name + '.txt')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    write_json(output / 'source-before.json', frozen)
    write_json(output / 'preparation-continuity.json', continuity)
    write_json(output / 'prepared-readiness.json', readiness)
    write_json(output / 'execution-toolchain-before.json', toolchain)
    os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256'] = args.expected_runtime_sha256
    plain = Client(args.api_url)
    assert plain.json('health')['capacity']['active_sessions'] == 0, 'coordinate idle service before execution'
    reports = []
    for row in selected:
        result = run_one(args, row, prepared, output)
        try:
            result['checks']['frozen_execution_sources_unchanged'] = all(sha((ROOT / name).read_bytes()) == expected for name, expected in frozen.items())
        except Exception as error:
            result['checks']['frozen_execution_sources_unchanged'] = False
            result['execution_source_error'] = str(error)
        try:
            toolchain_preflight(readiness)
            result['checks']['execution_toolchain_unchanged'] = True
        except Exception as error:
            result['checks']['execution_toolchain_unchanged'] = False
            result['toolchain_error'] = str(error)
        try:
            preparation_continuity(prepared, readiness)
            result['checks']['preparation_sources_still_exact'] = True
        except Exception as error:
            result['checks']['preparation_sources_still_exact'] = False
            result['source_error'] = str(error)
        result['source_sha256'] = frozen
        result['source_binding_scope'] = 'Local SHA for all frozen assets; actual product HTTP/DOM evidence is captured by the common bridge, which this wrapper does not patch. This does not claim every served asset body was independently HTTP-hashed.'
        if not all(result['checks'].values()):
            result['status'] = 'FAIL'
        write_json(output / row['device_id'] / row['unit_id'] / 'report.json', result)
        reports.append(result)
        write_json(output / 'summary.json', reports)
        print(f"HOST CONTROL {row['device_id']}/{row['unit_id']}: {result['status']}", flush=True)
        if result['status'] != 'PASS':
            break
    return 0 if len(reports) == len(selected) and all(row['status'] == 'PASS' for row in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
