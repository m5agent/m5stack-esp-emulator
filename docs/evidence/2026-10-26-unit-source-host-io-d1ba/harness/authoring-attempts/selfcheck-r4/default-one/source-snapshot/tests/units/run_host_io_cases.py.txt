#!/usr/bin/env python3
"""Preflight prepared host IO offline; --execute uses the original runner + Web."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from urllib.parse import urlparse

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'platform/tools'))
sys.path.insert(0, str(ROOT / 'tests/units'))
import prepare_host_io as preparation
import run_host_sensor_cases as shared
from check_batch_evidence import Checker
from run_service_cases import Client, wait_for
from unit_runtime import UnitRegistry

DEVICES, CASES = tuple(preparation.HOSTS), preparation.CASES
sha, write_json = preparation.digest, preparation.write_json
INPUTS = {
    'pir': [('external1', {'motion': x}) for x in (True, False, True, False, True, False)],
    'dual-button': [('external1', {k: x}) for k, x in [('blue-pressed', True), ('blue-pressed', False), ('red-pressed', True), ('red-pressed', False)]],
    'limit': [('external1', {'pressed': x}) for x in (True, False, True, False)],
    'key': [('external1', {'pressed': x}) for x in (True, False)],
    'angle': [('external1', {'voltage-mv': x}) for x in (0, 1250, 2500)],
    'light': [('external1', {'analog-mv': x, 'digital-level': bool(i % 2)}) for i, x in enumerate((310, 1550, 3100))],
    'rs485': [('external1', {'rx-hex': b'peer-to-guest\x00\x7f\xff'.hex()})],
    'hub': [('env', {'temperature-c': 31.5, 'humidity-pct': 67, 'pressure-pa': 98765}),
            ('ncir', {'ambient-c': 17.3, 'object-c': 37.1}), ('tvoc', {'eco2-ppm': 1250, 'tvoc-ppb': 230})],
    'rgb': [], 'fan': [], 'buzzer': [],
}
_bad_nec = preparation.original.nec_pulses(0x12, 0x34)
_bad_nec[0] = 200
INPUTS['ir'] = [('external1', {'rx-pulses-us': x}) for x in (
    preparation.original.nec_pulses(0x12, 0x34), _bad_nec, [9000, 2250, 562], preparation.original.nec_pulses(0x56, 0x78))]


def source_continuity(prepared, readiness):
    paths, _ = preparation.source_paths()
    frozen = readiness['source_sha256']
    assert {p.relative_to(ROOT).as_posix() for p in paths} == set(frozen), 'source inventory changed; prepare again'
    required = {'tests/units/run_io_cases.py', 'tests/units/io_probe/io_drivers/source-manifest.json',
                'tests/uiflow2/lib/rtc_probe.py', 'platform/tools/unit_runtime.py', 'platform/tools/device_service.py'}
    assert required <= set(frozen)
    for name, expected in frozen.items():
        path = ROOT / name
        snapshot = prepared / 'source-snapshot' / (name + '.txt')
        assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
        assert snapshot.is_file() and not snapshot.is_symlink() and sha(snapshot.read_bytes()) == expected, 'source snapshot differs: ' + name
        assert sha(path.read_bytes()) == expected, 'prepared source changed; prepare again: ' + name
    import littlefs
    paths, current = preparation.freeze_toolchain(littlefs)
    assert current == readiness['toolchain'], 'toolchain or ABI changed; prepare again'
    assert json.loads((prepared / 'source-before.json').read_bytes()) == frozen
    assert json.loads((prepared / 'toolchain-before.json').read_bytes()) == current
    assert json.loads((prepared / 'protocol-audit.json').read_bytes()) == readiness['protocol_audit'] == preparation.protocol_audit()[0]
    assert json.loads((prepared / 'source-dependencies.json').read_bytes()) == preparation.source_paths()[1]
    return paths, current


def select_cases(readiness, device='all', case='all'):
    assert readiness.get('schema_version') == 1 and readiness.get('status') == 'PREPARED_NOT_EXECUTED'
    rows = readiness.get('cases')
    assert isinstance(rows, list) and type(readiness.get('case_count')) is int and len(rows) == readiness['case_count']
    selected = readiness['selection']
    flags = readiness.get('custom_flags')
    assert isinstance(flags, dict) and set(flags) == {'ir_callback_root_patch','buzzer_callback_arity_patch'} and all(type(v) is bool for v in flags.values()), 'custom flags must be explicit booleans'
    devices, cases = selected['devices'], selected['cases']
    assert devices and len(set(devices)) == len(devices) and set(devices) <= set(DEVICES)
    assert cases and len(set(cases)) == len(cases) and set(cases) <= set(CASES)
    pairs = [(x['device_id'], x['unit_id']) for x in rows]
    assert len(set(pairs)) == len(pairs) and set(pairs) == {(h, c) for h in devices for c in cases}, 'prepared selection incomplete or duplicated'
    assert all(x['status'] == 'PREPARED_NOT_EXECUTED' and x['runtime'] == 'qemu' and x['custom_flags'] == readiness['custom_flags'] for x in rows)
    desired = {(h, c) for h in (DEVICES if device == 'all' else (device,)) for c in (CASES if case == 'all' else (case,))}
    assert desired <= set(pairs), 'requested selection not fully prepared'
    return [x for x in rows if (x['device_id'], x['unit_id']) in desired]


def validate_case(prepared, record, registry):
    image = shared.validate_prepared_files(prepared, record)
    shared.full_vfs(image, record)
    matrix = json.loads((ROOT / 'tests/uiflow2/device_matrix.json').read_bytes())
    device = next(x for x in matrix['devices'] if x['id'] == record['device_id'])
    base = ROOT / device['base']
    layout = preparation.reference_layout(base, int(device['flash_size'], 0))
    assert layout == record['reference_layout'] and sha(base.read_bytes()) == record['base_firmware_sha256']
    raw, original = image.read_bytes(), base.read_bytes()
    assert len(raw) == int(device['flash_size'], 0)
    padded = original + b'\xff' * (len(raw) - len(original))
    start, end = layout['offset'], layout['offset'] + layout['size']
    assert raw[:start] == padded[:start] and raw[end:] == padded[end:], 'bytes outside actual VFS changed'
    hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_bytes())['hosts']
    host = next(x for x in hosts if x['device_id'] == record['device_id'])
    ports = [x for x in host['ports'] if x.get('visual_port') == 'grove' and x.get('wiring_status') == 'confirmed' and x.get('physical_presence') == 'main-device']
    assert len(ports) == 1
    port, profile = ports[0], record['host_profile']
    visual = preparation.layout_module()
    expected = {**preparation.HOSTS[record['device_id']], 'log_tx': 43, 'log_rx': 44, 'internal_controller': 1, 'external_controller': 0}
    expected['text'] = list(visual.PROFILES[record['device_id']]['text'])
    expected.setdefault('canvas_size', expected['size'])
    assert profile == expected
    assert record['attachments'] == preparation.original.attachments(record['unit_id'], port['id'])
    assert record['firmware_flavor'] == preparation.flavor(record['unit_id'], record['custom_flags'])
    assert (image.parent / 'files/probe_config.py').read_bytes() == preparation.config_bytes(record['device_id'], record['unit_id'], port, profile, record['custom_flags'])
    assert record['layout_plan'] == json.loads(json.dumps(visual.planned_layout(record['device_id'], record['unit_id'])))
    resources = preparation.resource_preflight(record['device_id'], record['unit_id'], port, profile, raw, registry)
    assert resources == record['resource_preflight'], 'admission/resource contract changed; prepare again'
    return image, resources


def io_adapter(prepared, record, directory):
    """Adapt only prepare(), in a private original-runner namespace."""
    path = ROOT / 'tests/units/run_io_cases.py'
    spec = importlib.util.spec_from_file_location('_host_io_original_execution', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    used = []
    def handoff(args, case):
        assert not used and case == record['unit_id'] and args.device == record['device_id']
        assert all(getattr(args,k) is v for k,v in record['custom_flags'].items()), 'execution custom flags differ from prepared flavor'
        used.append(case)
        source_continuity(prepared, json.loads((prepared / 'readiness.json').read_bytes()))
        source, _ = validate_case(prepared, record, UnitRegistry())
        destination = args.out_dir / case
        assert destination == directory / 'controller' / case and not destination.exists()
        destination.mkdir(parents=True, exist_ok=False)
        shutil.copytree(source.parent / 'files', destination / 'files')
        image = destination / 'uiflow2-ui-test.bin'
        shutil.copyfile(source, image)
        assert sha(image.read_bytes()) == record['firmware_sha256']
        shared.full_vfs(image, record)
        adapter = {'schema_version': 1, 'status': 'VERIFIED', 'boundary': 'private-runner-prepare-only',
            'prepared_record_sha256': sha((source.parent / 'prepared.json').read_bytes()),
            'firmware_sha256': record['firmware_sha256'], 'actual_packaged_python_sha256': record['probe_sha256'],
            'scope': 'Original run_case/validate_io/Observations/evidence assertions unchanged; no legacy metadata rewrite.'}
        result = {key: copy.deepcopy(record[key]) for key in ('device_id', 'unit_id', 'runtime', 'port_id',
            'base_firmware_sha256', 'firmware_sha256', 'official_drivers', 'attachments', 'firmware_flavor', 'probe_sha256')}
        result.update(schema_version=1, date=datetime.now(timezone.utc).isoformat(), validation='virtual-device validation',
            status='PREPARED', expected_size=record['host_profile']['size'], checks={'packaged_guest_bytes_verified': True},
            preparation_adapter=adapter, injections=[], required_markers=[])
        # Preserve original custom metadata names and original flavor checks.
        if record['custom_driver_patch']:
            result['ir_callback_patch' if case == 'ir' else 'buzzer_callback_patch'] = copy.deepcopy(record['custom_driver_patch'])
        result['runner_sha256'] = {name: sha((ROOT / name).read_bytes()) for name in (
            'tests/units/run_io_cases.py', 'tests/units/run_control_cases.py', 'tests/units/run_sensor_cases.py',
            'tests/units/run_service_cases.py', 'tests/uiflow2/run_profile_ui_test.py', 'tests/uiflow2/esp_flash.py')}
        write_json(destination / 'prepared.json', result)
        return destination, image, result
    module.prepare = handoff
    return module


def same_value(actual, expected):
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(same_value(a, b) for a, b in zip(actual, expected))
    return type(actual) is type(expected) and actual == expected


def fresh_markers(case, index, values, serial):
    lines = [x.rstrip('\r') for x in serial.splitlines()]
    if case == 'pir':
        target = ('IO_PIR_CALLBACK 1 1', 'IO_PIR_CALLBACK 0 1', 'IO_PIR 1 1 1 1', 'IO_PIR_DISABLED_DONE 1 1', 'IO_PIR_CALLBACK 1 2', 'IO_PIR_CALLBACK 0 2')[index]
    elif case == 'dual-button':
        target = ('IO_DUAL 0 1 ', 'IO_DUAL_CLICK 1 0', 'IO_DUAL 1 0 ', 'IO_DUAL_CLICK 1 1')[index]
        return [x for x in lines if x.startswith(target)]
    elif case == 'limit': target = ('IO_LIMIT 0 0', 'IO_LIMIT 1 1', 'IO_LIMIT 0 2', 'IO_LIMIT 1 3')[index]
    elif case == 'key': target = ('IO_KEY_RAW 0', 'IO_KEY_RAW 1')[index]
    elif case == 'ir':
        if index == 1:
            assert not any(x.startswith('IO_IR_RX ') for x in lines), 'bad leader produced a fresh callback'
            found = [x for x in lines if x == 'IO_IR_HEARTBEAT 1']
            return found if len(found) >= 2 else []
        target = {0: 'IO_IR_RX 52 18 0 1', 2: 'IO_IR_RX 52 18 -1 2', 3: 'IO_IR_RX 120 86 0 3'}[index]
    elif case == 'rs485': target = 'IO_RS485_RX ' + values['rx-hex']
    elif case in {'angle', 'light'}:
        voltage = values['voltage-mv' if case == 'angle' else 'analog-mv']
        expected = preparation.original.expected_ideal_input(voltage, attenuation=3, adc_unit=1)
        if case == 'light': target = 'IO_LIGHT %d %d' % (expected['read_u16'], values['digital-level'])
        else: target = 'IO_ANGLE %d %.6f %d' % (expected['read_u16'], expected['read_uv'] / 1000000, expected['read_uv'])
    elif case == 'hub':
        state = copy.deepcopy(preparation.original.HUB_INITIAL)
        for instance, vector in INPUTS['hub'][:index+1]: state[instance].update(vector)
        expected = [*state['env'].values(), *state['ncir'].values(), *state['tvoc'].values()]
        found = []
        for line in lines:
            if not line.startswith('IO_HUB '): continue
            observed = [float(x) for x in line.split()[1:]]
            if len(observed) == 7 and all(math.isfinite(a) and abs(a-b) <= t for a,b,t in zip(observed, expected, (.2,.2,1.5,.021,.021,0,0))): found.append(line)
        return found
    else: return []
    return [x for x in lines if x == target]


def positive_input_binding(record, fresh, web, serial, controller):
    case, sid = record['unit_id'], controller['session_id']
    expected = INPUTS[case]
    assert all(web.get(k) == controller.get(k) == record.get(k) for k in ('device_id', 'runtime', 'firmware_sha256')) and web.get('session_id') == sid
    assert len(fresh) == len(expected) == len(controller['injections']), 'original input count differs'
    posts, actions = web.get('posts'), web.get('actions')
    assert isinstance(posts, list) and isinstance(actions, list), 'actual browser POST/action records required even for zero-input cases'
    windows, post_index, noops, previous_end, previous_time = [], 0, 0, 0, None
    for index, (row, (instance, values), injection) in enumerate(zip(fresh, expected, controller['injections'])):
        request = {'id': instance, 'values': values}
        assert set(row['requested']) == {'id', 'values'}
        for item in (row['requested'], injection):
            assert item.get('id') == instance and set(item.get('values', {})) == set(values) and all(same_value(item['values'][k], v) for k,v in values.items()), 'original requested vector differs'
        start = row['serial_offset_before_ui']
        end = fresh[index+1]['serial_offset_before_ui'] if index+1 < len(fresh) else len(serial)
        assert type(start) is int and type(end) is int and previous_end <= start < end <= len(serial)
        assert row['before_serial_sha256'] == sha(serial[:start].encode()), 'pre-UI serial prefix reset or changed'
        begin, finish = shared.input_time(row['request_started_at']), shared.input_time(row['request_returned_at'])
        assert begin <= finish and (previous_time is None or previous_time <= begin)
        first_post = post_index
        noop_fields = []
        for field, value in values.items():
            candidate = posts[post_index] if post_index < len(posts) else {}
            if (candidate.get('request', {}).get('id') == instance and
                    set(candidate.get('request', {}).get('values', {})) == {field} and
                    same_value(candidate['request']['values'][field], value)):
                assert candidate.get('method') == 'POST' and type(candidate.get('status')) is int and candidate['status'] == 200
                assert candidate.get('path') == f'/api/v1/sessions/{sid}/unit-input'
                assert begin <= shared.input_time(candidate['at']) <= finish
                response = candidate.get('response', {})
                assert response.get('session_id') == sid and response.get('state') == 'running' and response.get('source') == 'live'
                units = [u for u in response.get('units', []) if u.get('id') == instance]
                assert len(units) == 1 and units[0].get('available') is True and units[0].get('source') == 'guest-qom' and not units[0].get('errors')
                expected_unit = next(a['unit_id'] for a in record['attachments'] if a['id'] == instance)
                assert units[0].get('unit_id') == expected_unit
                # Native RMT can consume its injected pulse queue before the
                # response snapshot. The exact POST plus fresh decoder/negative
                # markers bind delivery; an empty consumed queue is not echoed.
                if not (case == 'ir' and field == 'rx-pulses-us' and units[0].get('properties', {}).get(field) == []):
                    assert same_value(units[0].get('properties', {}).get(field), value)
                post_index += 1
            else:
                matches = [a for a in actions if a.get('kind') == 'already-equal-noop' and a.get('instance') == instance and a.get('field') == field
                           and same_value(a.get('value'), value) and begin <= shared.input_time(a['at']) <= finish]
                before = row['before_live_state']
                units = [u for u in before.get('units', []) if u.get('id') == instance]
                assert len(matches) == 1 and before.get('session_id') == sid and before.get('source') == 'live'
                assert len(units) == 1 and units[0].get('source') == 'guest-qom' and units[0].get('available') is True and same_value(units[0].get('properties', {}).get(field), value), 'missing real POST or explicit verified no-op'
                noop_fields.append(field)
                noops += 1
        segment = serial[start:end]
        observed = fresh_markers(case, index, values, segment)
        assert observed, 'fresh original guest observation absent after input/no-op'
        adc_delta = None
        if case in {'angle', 'light'}:
            before = next(u for u in row['before_live_state']['units'] if u['id'] == instance)['properties']['adc-samples']
            after_state = fresh[index+1]['before_live_state'] if index+1 < len(fresh) else controller['unit_state']
            after = next(u for u in after_state['units'] if u['id'] == instance)['properties']['adc-samples']
            assert type(before) is int and type(after) is int and after > before, 'ADC controller did not sample during fresh vector window'
            adc_delta = {'before': before, 'after': after, 'delta': after-before}
        windows.append({**copy.deepcopy(row), 'sequence': index+1, 'serial_end_offset': end,
            'fresh_serial_sha256': sha(segment.encode()), 'guest_marker_lines': observed,
            'post_start_index': first_post, 'post_end_index': post_index, 'already_equal_noop_fields': noop_fields,
            'adc_samples_delta': adc_delta,
            'scope': 'Fresh guest readback; explicit no-op fields do not claim an injection POST.'})
        previous_end, previous_time = end, finish
    assert post_index == len(posts), 'unaccounted product POST'
    assert noops == sum(a.get('kind') == 'already-equal-noop' for a in actions), 'unaccounted explicit UI no-op'
    assert expected or not fresh and not posts, 'output-only case must have zero positive input POSTs'
    return {'schema_version': 1, 'status': 'VERIFIED' if expected else 'VERIFIED_OUTPUT_ONLY_ZERO_POSTS',
        'session_id': sid, 'unit_id': case, 'device_id': record['device_id'], 'runtime': 'qemu',
        'firmware_sha256': record['firmware_sha256'], 'full_serial_sha256': sha(serial.encode()),
        'serial_artifact': f'controller/{case}/serial.txt', 'post_count': post_index, 'verified_noop_fields': noops, 'vectors': windows}


class HostClient(Client):
    def __init__(self, url, record):
        super().__init__(url)
        self.record, self.web_ui = record, shared.DeadlineBridge(url)
        self.fresh_inputs, self.api_negative_inputs, self.owned_session_ids = [], [], []
        self.host_errors, self.cleanup_errors, self.stop_order = [], [], []
        self.host_checks = {}

    def verify_host(self, sid):
        serial = self.json(f'sessions/{sid}/serial?limit=262144', via_ui=False)['data']
        for marker in ('HOST_IO_INTERNAL before 36 1', 'HOST_IO_INTERNAL after_init 36 2'):
            assert re.search(r'(?m)^' + re.escape(marker) + r'\r?$', serial), marker
        offset = len(serial)
        serial = wait_for(self, sid, lambda text: bool(re.search(r'(?m)^HOST_IO_INTERNAL loop 36 ([3-9]|[1-9][0-9]+)\r?$', text[offset:])), 15)
        visual = preparation.layout_module().PROFILES[self.record['device_id']]
        expected_font = f"HOST_IO_FONT Montserrat12 {visual['scale']} {visual['font_height']}"
        # MicroPython can serialize 1.0/2.0 differently; compare numeric tokens.
        fonts = re.findall(r'(?m)^HOST_IO_FONT (\S+) (\S+) (\d+)\r?$', serial)
        assert len(fonts) == 1 and fonts[0][0] == 'Montserrat12' and float(fonts[0][1]) == visual['scale'] and int(fonts[0][2]) == visual['font_height'], expected_font
        geometry = 'HOST_IO_GEOMETRY %d %d %d' % (*visual['canvas'], visual['rotation'])
        layout = self.record['layout_plan']
        layout_marker = 'HOST_IO_LAYOUT ' + ' '.join(str(layout[k]) for k in ('x','y','width','body_y','line_height','body_rows','bottom')) + ' 2'
        assert geometry in serial and layout_marker in serial and re.search(r'(?m)^HOST_IO_DEFAULT_FONT_HEIGHT [1-9][0-9]*\r?$', serial)
        assert not any(x in serial for x in preparation.original.GUEST_FAILURES)
        self.host_checks = {'internal_bmi_before_after_init': True, 'fresh_loop_after_original_io_assertions': True,
            'actual_font_and_native_canvas': True, 'fresh_loop_offset': offset, 'layout_marker': layout_marker}

    def raw(self, path, method='GET', **kwargs):
        parts = path.split('?')[0].split('/')
        row, positive = None, kwargs.get('via_ui', True)
        if method == 'POST' and len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'unit-input':
            before = self.json(f'sessions/{parts[1]}/serial?limit=262144', via_ui=False)['data']
            state = self.json(f'sessions/{parts[1]}/units', via_ui=False)
            row = {'requested': copy.deepcopy(kwargs.get('payload')), 'serial_offset_before_ui': len(before),
                'before_serial_sha256': sha(before.encode()), 'before_live_state': state,
                'request_started_at': datetime.now(timezone.utc).isoformat()}
            (self.fresh_inputs if positive else self.api_negative_inputs).append(row)
        if method == 'GET' and len(parts) == 3 and parts[2] == 'evidence':
            try: self.verify_host(parts[1])
            except Exception as error: self.host_errors.append(str(error))
            self.stop_order.append('evidence-before-stop')
        if method == 'DELETE' and len(parts) == 2:
            self.stop_order.append('stop-purge-zero' if 'purge=0' in path else 'unexpected-stop-mode')
        try:
            data = super().raw(path, method=method, **kwargs)
            if method == 'POST' and path == 'sessions': self.owned_session_ids.append(json.loads(data)['session_id'])
            return data
        except Exception as error:
            if row is not None: row['request_error'] = str(error)
            raise
        finally:
            if row is not None: row['request_returned_at'] = datetime.now(timezone.utc).isoformat()


def frame_observations(checker, directory, record, controller, manifest):
    import zipfile
    with zipfile.ZipFile(directory / f"controller/{record['unit_id']}/evidence.zip") as archive:
        zipped = archive.read('frames/current.png')
    paths = {'controller': directory / f"controller/{record['unit_id']}/frame.png", 'stopped_history': directory / f"controller/{record['unit_id']}/history-frame.png"}
    pixels = {name: path.read_bytes() for name,path in paths.items()}
    pixels['running_evidence'] = zipped
    assert sha(pixels['controller']) == controller['frame_sha256']
    result = {}
    for channel, raw in pixels.items():
        dims = checker.png(raw, channel)
        assert [dims['width'], dims['height']] == record['host_profile']['size']
        with Image.open(io.BytesIO(raw)) as image:
            assert any(a != b for a,b in image.convert('RGB').getextrema()), 'blank IO frame'
        result[channel] = {'sha256': sha(raw), 'bytes': len(raw), **dims, 'nonblank': True, 'session_id': manifest['session']['session_id']}
    return {'capture_contract': 'separate-captures-no-atomic-frame-claim', 'channels': result, 'native_readability': 'NOT REVIEWED'}


def run_one(args, record, prepared, output):
    directory = output / record['device_id'] / record['unit_id']
    directory.mkdir(parents=True, exist_ok=False)
    os.environ['M5_UNIT_WEB_BRIDGE_OUT'] = str(directory / 'browser')
    module, client = io_adapter(prepared, record, directory), HostClient(args.api_url, record)
    result = {'status': 'FAIL'}
    try:
        result = module.run_case(client, argparse.Namespace(device=record['device_id'], out_dir=directory/'controller',
            prepare_only=False, base=None, **record['custom_flags']), record['unit_id'])
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        try: client.web_ui.close()
        except Exception as error: client.cleanup_errors.append(str(error))
        plain = Client(args.api_url)
        for owned in client.owned_session_ids:
            try:
                if plain.json(f'sessions/{owned}')['state'] not in {'stopped', 'failed'}:
                    try: (directory / 'emergency-evidence.zip').write_bytes(plain.raw(f'sessions/{owned}/evidence'))
                    finally: plain.json(f'sessions/{owned}?purge=0', method='DELETE')
                    client.cleanup_errors.append('owned lease required emergency stop; remains FAIL')
            except Exception as error: client.cleanup_errors.append(str(error))
    sid = result.get('session_id')
    web_path = directory / 'browser' / str(sid) / 'web-report.json'
    web = json.loads(web_path.read_bytes()) if web_path.is_file() else {}
    proof_path = web_path.with_name('runtime-provenance.json')
    proof = json.loads(proof_path.read_bytes()) if proof_path.is_file() else {}
    checks = {'original_io_assertions': result.get('status') == 'PASS', 'host_observations': bool(client.host_checks) and not client.host_errors,
        'no_emergency_cleanup': not client.cleanup_errors, 'evidence_before_stop': client.stop_order[:2] == ['evidence-before-stop','stop-purge-zero'],
        'actual_browser': bool(web.get('snapshots')) and not web.get('errors')}
    report = {'schema_version': 1, 'category': 'virtual-device-browser-host-io', 'status': 'FAIL',
        **{k: result.get(k, record.get(k)) for k in ('device_id','unit_id','runtime','firmware_sha256','firmware_flavor','evidence_sha256')},
        'session_id': sid, 'checks': checks, 'runtime_provenance': proof, 'fresh_inputs': client.fresh_inputs,
        'api_negative_inputs': client.api_negative_inputs, 'host_observations': client.host_checks, 'host_errors': client.host_errors,
        'cleanup_errors': client.cleanup_errors, 'controller_error': result.get('error'), 'hardware_execution': 'NOT RUN',
        'controller_result': f"controller/{record['unit_id']}/result.json", 'browser_report': str(web_path.relative_to(directory)),
        'evidence': f"controller/{record['unit_id']}/evidence.zip", 'native_readability': 'NOT REVIEWED'}
    report['artifact_sha256'] = {p.relative_to(directory).as_posix(): sha(p.read_bytes()) for p in directory.rglob('*')
        if p.is_file() and p.suffix != '.bin' and 'files' not in p.parts}
    try:
        serial = (directory / f"controller/{record['unit_id']}/serial.txt").read_bytes().decode('utf-8')
        report['positive_input_binding'] = positive_input_binding(record, client.fresh_inputs, web, serial, result)
        checker = Checker(directory)
        manifest, count = checker.zip_manifest(directory / report['evidence'], report, record['unit_id'])
        report['strict_runtime_proof'] = checker.direct_record(proof, manifest['session'], record['unit_id'], args.expected_runtime_sha256)
        worker = manifest['session']['worker']
        assert proof['kind'] == 'direct-pid' and proof['status'] == 'VERIFIED' and proof['firmware_sha256'] == report['firmware_sha256'] and proof['worker_id'] == worker['worker_id'] and type(proof['worker_generation']) is int and proof['worker_generation'] == worker['generation'] and worker['lease_active'] is True
        verified = checker.artifacts(report, {}, directory/'report.json')
        report['strict_controller_detail'] = checker.controller_detail(report, directory/'report.json', verified)
        report['strict_browser_detail'] = checker.browser_detail(report, directory/'report.json', verified, manifest)
        report['frame_observations'] = frame_observations(checker, directory, record, result, manifest)
        plain = Client(args.api_url)
        history = plain.raw(f'sessions/{sid}')
        (directory/'history.json').write_bytes(history)
        data = json.loads(history)
        assert data['state'] == 'stopped' and data['flash_retained'] is False and all(data[k] == report[k] for k in ('session_id','device_id','runtime','firmware_sha256'))
        health = plain.raw('health')
        (directory/'history-health.json').write_bytes(health)
        assert json.loads(health)['capacity']['active_sessions'] == 0
        report['zip_members'] = count
        checks['strict_inputs_pid_worker_browser_frames_and_history'] = True
    except Exception as error:
        checks['strict_inputs_pid_worker_browser_frames_and_history'] = False
        report['strict_error'] = str(error)
    report['artifact_sha256'] = {p.relative_to(directory).as_posix(): sha(p.read_bytes()) for p in directory.rglob('*')
        if p.is_file() and p.suffix != '.bin' and p.name != 'report.json' and 'files' not in p.parts}
    report['status'] = 'PASS' if all(checks.values()) else 'FAIL'
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepared-dir', type=Path, required=True)
    parser.add_argument('--device', choices=(*DEVICES,'all'), default='all')
    parser.add_argument('--case', choices=(*CASES,'all'), default='all')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--api-url', default='http://127.0.0.1:8787')
    parser.add_argument('--expected-runtime-sha256')
    args = parser.parse_args()
    if args.execute and (not args.out_dir or not re.fullmatch('[a-f0-9]{64}', args.expected_runtime_sha256 or '')):
        parser.error('--execute requires fresh --out-dir and exact --expected-runtime-sha256')
    prepared = args.prepared_dir.resolve()
    readiness = json.loads((prepared/'readiness.json').read_bytes())
    source_continuity(prepared, readiness)
    selected = select_cases(readiness, args.device, args.case)
    registry, blocked = UnitRegistry(), []
    for row in selected:
        _, resources = validate_case(prepared, row, registry)
        if resources['blockers']: blocked.append({'device_id':row['device_id'], 'unit_id':row['unit_id'], 'blockers':resources['blockers']})
    if not args.execute:
        print(json.dumps({'status':'PREFLIGHT_ONLY', 'selected_cases':len(selected), 'blocked_cases':blocked, 'api_contacted':False, 'sessions_started':0},ensure_ascii=False))
        return 0
    assert not blocked, 'blocked host/IO selection; no API contacted: ' + json.dumps(blocked, ensure_ascii=False)
    assert os.environ.get('M5_UNIT_WEB_BRIDGE') != '1', 'host wrapper owns the Web bridge'
    assert urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'}
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT/'.work') and not output.exists()
    output.mkdir(parents=True, exist_ok=False)
    frozen = dict(readiness['source_sha256'])
    for name in ('readiness.json','source-before.json','source-dependencies.json','toolchain-before.json'):
        frozen[(prepared/name).relative_to(ROOT).as_posix()] = sha((prepared/name).read_bytes())
    for name, expected in frozen.items():
        target = output/'source-snapshot'/(name+'.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT/name).read_bytes()
        assert sha(raw) == expected
        target.write_bytes(raw)
    write_json(output/'source-before.json',frozen)
    write_json(output/'prepared-readiness.json',readiness)
    os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256'] = args.expected_runtime_sha256
    assert Client(args.api_url).json('health')['capacity']['active_sessions'] == 0
    reports = []
    for record in selected:
        result = run_one(args,record,prepared,output)
        try:
            source_continuity(prepared,readiness)
            assert all(sha((ROOT/name).read_bytes()) == expected for name,expected in frozen.items())
            result['checks']['exact_frozen_sources_and_toolchain'] = True
        except Exception as error:
            result['checks']['exact_frozen_sources_and_toolchain'] = False
            result['source_error'] = str(error)
        result['source_sha256'] = frozen
        result['source_binding_scope'] = 'Exact local frozen source hashes; real product DOM/HTTP evidence from unchanged common bridge. Served asset body hashes are not independently captured.'
        if not all(result['checks'].values()): result['status'] = 'FAIL'
        write_json(output/record['device_id']/record['unit_id']/'report.json', result)
        reports.append(result)
        write_json(output/'summary.json',reports)
        print(f"HOST IO {record['device_id']}/{record['unit_id']}: {result['status']}",flush=True)
        if result['status'] != 'PASS': break
    return 0 if len(reports) == len(selected) and all(x['status'] == 'PASS' for x in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
