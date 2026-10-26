#!/usr/bin/env python3
"""Run prepared device-local sensors through visible Device Service + Web sessions.

Default is offline preflight; only --execute contacts the service. Preparation
source and toolchain changes require a fresh preparation; old results confer no PASS."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
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
from check_batch_evidence import Checker  # noqa: E402
from run_service_cases import Client, png_metrics, wait_for  # noqa: E402
from unit_runtime import UnitRegistry, UnitError  # noqa: E402
from web_ui_bridge import WebUIBridge  # noqa: E402
import prepare_host_sensors as preparation  # noqa: E402

DEVICES = ('atoms3r', 'sticks3', 'stopwatch')
CASES = tuple(preparation.ADDRESSES)
REQUIRED_PREPARATION = {'tests/uiflow2/lib/rtc_probe.py', 'tests/uiflow2/esp_flash.py',
    'tests/uiflow2/run_profile_ui_test.py', 'tests/units/run_control_cases.py',
    'tests/units/run_service_cases.py', 'tests/units/run_sensor_cases.py',
    'tests/units/sensors_probe/sensor_drivers/source-manifest.json', 'platform/tools/firmware_analysis.py'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def display_contract(record):
    profile = record['host_profile']
    display = preparation.layout_module()
    layout = display.planned_layout(record['device_id'], record['unit_id'])
    assert json.loads(json.dumps(layout)) == json.loads(json.dumps(record['layout_plan'])), 'prepared display configuration differs'
    visual = display.PROFILES[record['device_id']]
    assert profile['size'] == list(visual['native']) and profile['canvas_size'] == list(visual['canvas'])
    expected_font = {'name': display.FONT_NAME, 'scale': visual['scale'], 'height': visual['font_height']}
    assert record['display_font'] == expected_font, 'prepared font configuration differs'
    values = [layout[key] for key in ('x', 'y', 'width', 'body_y', 'line_height', 'body_rows', 'bottom')]
    contract = {'expected_native_frame_size': profile['size'], 'expected_canvas_size': profile['canvas_size'],
        'expected_font': {'name': display.FONT_NAME, 'size': visual['scale'], 'height': visual['font_height']},
        'expected_headers': list(layout['headers']),
        'expected_layout_marker': 'HOST_SENSOR_LAYOUT ' + ' '.join(map(str, [*values, len(layout['headers'])]))}
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
    default = single('HOST_SENSOR_DEFAULT_FONT_HEIGHT')
    assert len(default) == 2 and re.fullmatch('[1-9][0-9]*', default[1])
    observed = single('HOST_SENSOR_FONT')
    expected = contract['expected_font']
    assert len(observed) == 4 and observed[1] == expected['name'], 'guest selected another font'
    scale = float(observed[2])
    assert math.isfinite(scale) and math.isclose(scale, expected['size'], rel_tol=0, abs_tol=1e-6), 'guest font scale differs'
    assert re.fullmatch('[1-9][0-9]*', observed[3]) and int(observed[3]) == expected['height'], 'guest font height differs'
    assert single('HOST_SENSOR_LAYOUT') == contract['expected_layout_marker'].split(), 'guest native layout differs'
    assert not any(error in serial for error in ('SENSOR_PROBE_FAIL', 'HOST_SENSOR_FAIL',
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
    sources = {path.relative_to(preparation.common.COMMON).as_posix(): sha(path.read_bytes())
               for path in preparation.common.COMMON.rglob('*.py')}
    sources.update(record['probe_sha256'])
    assert expected == sources, 'VFS whitelist differs from current frozen probe/common sources'
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
        assert snapshot.is_file() and not snapshot.is_symlink() and sha(snapshot.read_bytes()) == expected, 'preparation snapshot missing or changed: ' + name
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
    assert files.is_dir() and not files.is_symlink() and not directory.is_symlink() and not any(path.is_symlink() for path in paths), 'prepared guest tree is unavailable or aliased'
    actual = {path.relative_to(files).as_posix(): sha(path.read_bytes()) for path in paths if path.is_file()}
    assert actual == record['prepared_file_sha256'], 'prepared guest file tree changed'
    assert {name: value for name, value in actual.items() if name.endswith('.py')} == record['probe_sha256'], 'prepared Python membership/hash differs'
    image = directory / 'uiflow2-ui-test.bin'
    assert image.is_file() and not image.is_symlink(), 'prepared firmware is unavailable or aliased'
    assert sha(image.read_bytes()) == record['firmware_sha256'], 'prepared firmware bytes differ'
    return image


def verify_reference_image(image, record):
    matrix = json.loads((ROOT / 'tests/uiflow2/device_matrix.json').read_bytes())
    device = next(row for row in matrix['devices'] if row['id'] == record['device_id'])
    base = ROOT / device['base']
    layout = preparation.reference_layout(base, int(device['flash_size'], 0))
    assert layout == record['reference_layout'], 'current reference partition/layout differs'
    raw, original = image.read_bytes(), base.read_bytes()
    assert sha(original) == record['base_firmware_sha256'], 'current reference firmware differs'
    assert len(raw) == int(device['flash_size'], 0), 'prepared flash size differs'
    padded = original + b'\xff' * (len(raw) - len(original))
    start, end = layout['offset'], layout['offset'] + layout['size']
    assert raw[:start] == padded[:start] and raw[end:] == padded[end:], 'prepared bytes outside actual VFS differ'
    profile = {**preparation.HOSTS[record['device_id']], 'log_tx': 43, 'log_rx': 44,
               'internal_controller': 1, 'external_controller': 0}
    profile.setdefault('canvas_size', profile['size'])
    assert profile == record['host_profile'], 'prepared host wiring/profile differs'
    hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_bytes())['hosts']
    host = next(row for row in hosts if row['device_id'] == record['device_id'])
    ports = [row for row in host['ports'] if row.get('visual_port') == 'grove'
             and row.get('wiring_status') == 'confirmed' and row.get('physical_presence') == 'main-device']
    assert len(ports) == 1, 'exactly one confirmed main-device Grove port is required'
    port = ports[0]
    attachment = {'id': 'external1', 'unit_id': record['unit_id'], 'port_id': port['id'],
                  'initial': preparation.SENSOR_CASES[record['unit_id']]['initial']}
    assert record['attachments'] == [attachment], 'prepared attachment/initial fixture differs'
    config = image.parent / 'files/probe_config.py'
    assert config.read_bytes() == preparation.config_bytes(record['device_id'], record['unit_id'], port, profile), 'prepared configuration differs from current host/Unit'
    return device, port


def load_sensor_runner():
    """Load a private namespace; never monkey-patch the imported shared runner."""
    path = ROOT / 'tests/units/run_sensor_cases.py'
    spec = importlib.util.spec_from_file_location('_host_sensor_execution', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreparedSensorAdapter:
    """Restore frozen host config at the original runner's build boundary.

    The original runner records its minimal config hash before calling build.
    Keep that record intact and bind it explicitly to both restored source and
    actual packaged hashes; no field is silently rewritten to hide a mismatch.
    """
    def __init__(self, prepared, record, directory, sensor):
        self.prepared, self.record, self.directory, self.sensor = prepared, record, directory, sensor
        self.source = prepared / record['device_id'] / record['unit_id']
        self.original_verify = sensor.verify_image_files
        self.report = {'schema_version': 1, 'status': 'NOT BUILT',
            'scope': 'Adapter-generated source/image handoff; original sensor runtime assertions remain unchanged.'}
        sensor.PROBE = self.source / 'files'
        sensor.build_control_image = self.build
        sensor.verify_image_files = self.verify

    def build(self, options):
        assert self.report['status'] == 'NOT BUILT', 'prepared image handoff may occur only once'
        source_image = validate_prepared_files(self.prepared, self.record)
        device, port = verify_reference_image(source_image, self.record)
        full_vfs(source_image, self.record)
        destination = self.directory / 'controller' / self.record['unit_id']
        assert options.out_dir == destination and options.files_dir == destination / 'files'
        assert options.base == ROOT / device['base'] and sha(options.base.read_bytes()) == self.record['base_firmware_sha256']
        assert options.flash_size == int(device['flash_size'], 0) and options.prog_size == 32
        assert options.preserve_vfs is False and options.mklittlefs is None
        # The legacy runner's matrix VFS can differ (StickS3); it is never used
        # to rebuild. The validated actual-reference image is copied verbatim.
        assert (options.vfs_offset, options.vfs_size) == (int(device['vfs_offset'], 0), int(device['vfs_size'], 0))
        files = options.files_dir
        assert not files.is_symlink() and not any(path.is_symlink() for path in files.rglob('*'))
        before = {path.relative_to(files).as_posix(): sha(path.read_bytes()) for path in files.rglob('*') if path.is_file()}
        case, host = self.record['unit_id'], self.record['device_id']
        legacy = (f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\n"
                  f"DEVICE_ID = {host!r}\nNO_FIXTURE = False\n").encode()
        assert (files / 'probe_config.py').read_bytes() == legacy, 'original runner configuration boundary changed'
        expected_before = dict(self.record['prepared_file_sha256'], **{'probe_config.py': sha(legacy)})
        assert before == expected_before, 'original runner copied unexpected prepared source bytes'
        (files / 'probe_config.py').write_bytes((self.source / 'files/probe_config.py').read_bytes())
        after = {path.relative_to(files).as_posix(): sha(path.read_bytes()) for path in files.rglob('*') if path.is_file()}
        assert after == self.record['prepared_file_sha256'], 'restored prepared guest tree differs'
        image = destination / 'uiflow2-ui-test.bin'
        assert not image.exists(), 'refuse to overwrite execution evidence'
        shutil.copyfile(source_image, image)
        full_vfs(image, self.record)
        verify_reference_image(image, self.record)
        self.report.update(status='IMAGE VERIFIED',
            original_runner_prebuild_probe_sha256={key: value for key, value in before.items() if key.endswith('.py')},
            restored_probe_sha256={key: value for key, value in after.items() if key.endswith('.py')},
            original_runner_config_sha256=sha(legacy), restored_config_sha256=after['probe_config.py'],
            firmware_sha256=sha(image.read_bytes()), complete_vfs_sha256=self.record['packaged_full_py_sha256'])
        return image

    def verify(self, image, files, _legacy_device):
        assert self.report['status'] == 'IMAGE VERIFIED' and files == image.parent / 'files'
        layout = self.record['reference_layout']
        effective = {'vfs_offset': hex(layout['offset']), 'vfs_size': hex(layout['size'])}
        packaged = self.original_verify(image, files, effective)
        assert packaged == self.record['probe_sha256'] == self.report['restored_probe_sha256'], 'actual packaged probe differs'
        full_vfs(image, self.record)
        self.report['actual_packaged_probe_sha256'] = packaged
        return packaged

    def bind_result(self, result):
        assert self.report.get('actual_packaged_probe_sha256'), 'original runner never verified the prepared image'
        assert result['probe_sha256'] == self.report['original_runner_prebuild_probe_sha256'], 'original runner prebuild record differs'
        assert result['packaged_python_sha256'] == self.report['actual_packaged_probe_sha256'], 'original runner packaged record differs'
        assert result['firmware_sha256'] == self.record['firmware_sha256'] == self.report['firmware_sha256']
        assert result['base_firmware_sha256'] == self.record['base_firmware_sha256']
        self.report['status'] = 'VERIFIED'
        result['preparation_adapter'] = copy.deepcopy(self.report)
        result['firmware_flavor'] = 'reference-app-with-vendored-official-sensor-drivers-host-probe'


def sensor_adapter(prepared, record, directory):
    sensor = load_sensor_runner()
    return sensor, PreparedSensorAdapter(prepared, record, directory, sensor)


def same_input_value(actual, expected):
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def same_input_vector(actual, expected):
    return type(actual) is dict and set(actual) == set(expected) and all(
        same_input_value(actual[key], value) for key, value in expected.items())


def input_time(value):
    assert isinstance(value, str) and value, 'input event timestamp is missing'
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    assert parsed.tzinfo is not None, 'input event timestamp must be timezone aware'
    return parsed


def sensor_marker_lines(case, values, serial):
    spec = preparation.SENSOR_CASES[case]
    expected = ([values['distance-mm'], values['distance-mm'] / 10] if case in {'tof', 'ultrasonic-i2c'}
                else [values[field] for field in spec['fields']])
    result = []
    for match in re.finditer(r'(?m)^' + re.escape(spec['marker']) + r' ([^\r\n]+)\r?$', serial):
        try:
            observed = [float(value) for value in match.group(1).split()]
        except ValueError:
            continue
        if len(observed) == len(expected) and all(math.isfinite(actual) and abs(actual - wanted) <= tolerance
                for actual, wanted, tolerance in zip(observed, expected, spec['tolerances'])):
            result.append(match.group(0).rstrip('\r'))
    return result


def positive_input_binding(record, fresh_inputs, web, serial, controller):
    """Bind every real product POST and fresh guest window to the original vectors."""
    case, sid = record['unit_id'], controller.get('session_id')
    expected = preparation.SENSOR_CASES[case]['changes']
    assert len(expected) == 2 and len(fresh_inputs) == 2, 'exactly two requested sensor vectors are required'
    assert isinstance(sid, str) and sid and web.get('session_id') == sid, 'positive inputs have another session'
    for key in ('device_id', 'firmware_sha256', 'runtime'):
        assert web.get(key) == controller.get(key) == record.get(key), 'positive inputs have another ' + key
    injections = controller.get('injections', [])
    assert len(injections) == 2 and all(type(row.get('sequence')) is int and row['sequence'] == index and row.get('guest_observed') is True
        and same_input_vector(row.get('values'), values)
        for index, (row, values) in enumerate(zip(injections, expected), 1)), 'original sensor injection records differ'
    wanted_posts = [(field, value) for values in expected for field, value in values.items()]
    posts = web.get('posts', [])
    assert len(posts) == len(wanted_posts), 'product POST count differs from the original two vectors'
    full_hash, vectors, post_start, previous_end, previous_returned = sha(serial.encode('utf-8')), [], 0, 0, None
    for index, (row, values) in enumerate(zip(fresh_inputs, expected)):
        request = row.get('requested', {})
        assert set(request) == {'id', 'values'} and request['id'] == 'external1' and same_input_vector(
            request.get('values'), values), 'requested sensor vector differs'
        offset = row.get('serial_offset_before_ui')
        end = fresh_inputs[index + 1].get('serial_offset_before_ui') if index + 1 < len(fresh_inputs) else len(serial)
        assert type(offset) is int and type(end) is int and previous_end <= offset < end <= len(serial), 'fresh sensor serial offsets differ'
        assert row.get('before_serial_sha256') == sha(serial[:offset].encode('utf-8')), 'pre-UI serial prefix changed or reset'
        started, returned = input_time(row.get('request_started_at')), input_time(row.get('request_returned_at'))
        assert started <= returned, 'product input interval is reversed'
        assert previous_returned is None or previous_returned <= started, 'requested product input intervals overlap'
        stop = post_start + len(values)
        for post, (field, value) in zip(posts[post_start:stop], values.items()):
            assert post.get('method') == 'POST' and type(post.get('status')) is int and post['status'] == 200
            assert post.get('path') == f'/api/v1/sessions/{sid}/unit-input', 'product input has another endpoint/session'
            actual = post.get('request', {})
            assert set(actual) == {'id', 'values'} and actual['id'] == 'external1' and same_input_vector(
                actual.get('values'), {field: value}), 'product POST field/order/value/type differs'
            assert started <= input_time(post.get('at')) <= returned, 'product POST is outside its requested vector'
            response = post.get('response', {})
            assert response.get('session_id') == sid and response.get('state') == 'running' and response.get('source') == 'live'
            units = response.get('units', [])
            assert len(units) == 1 and units[0].get('id') == 'external1' and units[0].get('unit_id') == case
            assert units[0].get('available') is True and units[0].get('source') == 'guest-qom'
            assert same_input_value(units[0].get('properties', {}).get(field), value), 'product POST response did not apply its input'
        fresh = serial[offset:end]
        lines = sensor_marker_lines(case, values, fresh)
        assert lines, 'no complete matching guest marker after the actual pre-UI serial offset'
        vectors.append({**copy.deepcopy(row), 'sequence': index + 1, 'serial_end_offset': end,
            'full_serial_sha256': full_hash, 'fresh_serial_sha256': sha(fresh.encode('utf-8')),
            'guest_observed': True, 'guest_marker_lines': lines,
            'post_start_index': post_start, 'post_end_index': stop})
        previous_end, post_start, previous_returned = end, stop, returned
    return {'schema_version': 1, 'status': 'VERIFIED', 'session_id': sid, 'device_id': record['device_id'],
        'unit_id': case, 'firmware_sha256': record['firmware_sha256'], 'runtime': record['runtime'],
        'serial_artifact': f'controller/{case}/serial.txt', 'full_serial_sha256': full_hash,
        'post_count': len(posts), 'vectors': vectors,
        'scope': 'Raw UTF-8/CRLF serial windows start at actual pre-UI snapshots; end at the next pre-UI offset or final controller serial. Original guest assertions are retained.'}


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
        marker('HOST_SENSOR_GEOMETRY %d %d %d' % (*profile['canvas_size'], profile['rotation']))
        marker('HOST_SENSOR_INTERNAL before 36 1')
        marker('HOST_SENSOR_INTERNAL after_init 36 2')
        address = preparation.ADDRESSES[self.record['unit_id']]
        marker('HOST_SENSOR_EXTERNAL_SCAN %d' % address)
        marker('HOST_SENSOR_EXTERNAL_AFTER_INIT %d' % address)
        offset = len(serial)
        serial = wait_for(self, sid, lambda text: bool(re.search(
            r'(?m)^HOST_SENSOR_INTERNAL after_op 36 ([3-9]|[1-9][0-9]+)\r?$', text[offset:])), 10)
        display = verify_display_markers(serial, self.record)
        assert not any(failure in serial for failure in ('SENSOR_PROBE_FAIL', 'HOST_SENSOR_FAIL', 'Traceback (most recent call last)', 'Guru Meditation'))
        self.host_checks = {'canvas_geometry': True, 'internal_bmi_before_after_init': True,
            'external_scan_and_address_change': True, 'fresh_internal_after_all_sensor_assertions': True,
            'no_guest_exception': True, 'fresh_after_op_offset': offset, 'strict_display_contract': display}

    def raw(self, path, method='GET', **kwargs):
        parts = path.split('?')[0].split('/')
        input_row = None
        if method == 'POST' and len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'unit-input':
            before = self.serial_now(parts[1])
            input_row = {'serial_offset_before_ui': len(before), 'before_serial_sha256': sha(before.encode('utf-8')),
                         'requested': copy.deepcopy(kwargs.get('payload')),
                         'request_started_at': datetime.now(timezone.utc).isoformat()}
            self.fresh_inputs.append(input_row)
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
        try:
            data = super().raw(path, method=method, **kwargs)
        finally:
            if input_row is not None:
                input_row['request_returned_at'] = datetime.now(timezone.utc).isoformat()
        if method == 'POST' and path == 'sessions':
            self.owned_session_ids.append(json.loads(data)['session_id'])
        return data


def execution_sources(report):
    # Preparation already freezes the full current Web and local import graph.
    return sorted(ROOT / name for name in report['source_sha256'])


def run_one(args, original, prepared_root, output):
    directory = output / original['device_id'] / original['unit_id']
    directory.mkdir(parents=True, exist_ok=False)
    os.environ['M5_UNIT_WEB_BRIDGE_OUT'] = str(directory / 'browser')
    sensor, adapter = sensor_adapter(prepared_root, original, directory)
    client = HostClient(args.api_url, original)
    result = {'status': 'FAIL'}
    try:
        # A private module retains the original run_case and every runtime
        # assertion. Only its file/image preparation boundary is adapted.
        result = sensor.run_case(client, argparse.Namespace(device=original['device_id'],
            out_dir=directory / 'controller', build_only=False, base=None, thermal_no_fixture=False), original['unit_id'])
        adapter.bind_result(result)
    except Exception as error:
        result['error'] = str(error)
        result['status'] = 'FAIL'
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
    controller_result = directory / 'controller' / original['unit_id'] / 'result.json'
    if controller_result.is_file():
        write_json(controller_result, result)
    sid = result.get('session_id')
    web_path = directory / 'browser' / str(sid) / 'web-report.json'
    web = json.loads(web_path.read_text()) if web_path.is_file() else {}
    proof_path = web_path.with_name('runtime-provenance.json')
    proof = json.loads(proof_path.read_text()) if proof_path.is_file() else {}
    checks = {'original_sensor_assertions': result.get('status') == 'PASS',
        'prepared_image_and_config_binding': adapter.report.get('status') == 'VERIFIED',
        'host_observations': bool(client.host_checks) and not client.host_errors,
        'actual_web': bool(web.get('snapshots')) and not web.get('errors'),
        'same_host_session_firmware': all(web.get(key) == result.get(key) == original.get(key)
            for key in ('device_id', 'firmware_sha256', 'runtime')) and web.get('session_id') == sid,
        'positive_inputs_used_product_posts': False,
        'no_emergency_cleanup_needed': not client.cleanup_errors,
        'retained_stopped_history': False,
        'flash_released_by_default': False,
        'zip_requested_before_stop': client.stop_order[:2] == ['evidence-request-before-stop', 'stop-purge-zero']}
    report = {'schema_version': 1, 'category': 'virtual-device-browser-host-sensors', 'status': 'FAIL',
        'device_id': original['device_id'], 'unit_id': original['unit_id'], 'runtime': 'qemu', 'session_id': sid,
        'firmware_sha256': result.get('firmware_sha256'), 'evidence_sha256': result.get('evidence_sha256'),
        'firmware_flavor': result.get('firmware_flavor'),
        'checks': checks, 'host_observations': client.host_checks, 'host_errors': client.host_errors,
        'fresh_inputs': client.fresh_inputs, 'runtime_provenance': proof, 'hardware_execution': 'NOT RUN',
        'cleanup_errors': client.cleanup_errors, 'controller_error': result.get('error'), 'preparation_adapter': adapter.report,
        'native_readability': 'NOT REVIEWED',
        'controller_result': f"controller/{original['unit_id']}/result.json",
        'browser_report': str(web_path.relative_to(directory)), 'evidence': f"controller/{original['unit_id']}/evidence.zip"}
    try:
        # read_bytes preserves the actual UART CRLF bytes for all prefix hashes.
        serial = (directory / 'controller' / original['unit_id'] / 'serial.txt').read_bytes().decode('utf-8')
        report['positive_input_binding'] = positive_input_binding(original, client.fresh_inputs, web, serial, result)
        checks['positive_inputs_used_product_posts'] = True
    except Exception as error:
        report['positive_input_error'] = str(error)
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
    current_protocol, _, _ = preparation.protocol_audit()
    assert current_protocol == readiness['protocol_audit'], 'prepared protocol audit differs'
    assert json.loads((prepared / 'source-before.json').read_bytes()) == readiness['source_sha256'], 'preparation source manifest differs'
    assert json.loads((prepared / 'source-dependencies.json').read_bytes()) == preparation.source_paths()[1], 'preparation dependency manifest differs'
    assert json.loads((prepared / 'toolchain-before.json').read_bytes()) == toolchain, 'preparation toolchain manifest differs'
    assert json.loads((prepared / 'protocol-audit.json').read_bytes()) == current_protocol, 'preparation protocol manifest differs'
    selected = select_cases(readiness, args.device, args.case)
    registry = UnitRegistry()
    blocked = []
    for row in selected:
        image = validate_prepared_files(prepared, row)
        full_vfs(image, row)
        verify_reference_image(image, row)
        display_contract(row)
        try:
            registry.attachments(row['device_id'], 'qemu', row['attachments'])
        except UnitError as error:
            blocked.append({'device_id': row['device_id'], 'unit_id': row['unit_id'], 'code': error.code, 'http_status': error.status, 'reason': error.message})
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
        print(f"HOST SENSOR {row['device_id']}/{row['unit_id']}: {result['status']}", flush=True)
        if result['status'] != 'PASS':
            break
    return 0 if len(reports) == len(selected) and all(row['status'] == 'PASS' for row in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
