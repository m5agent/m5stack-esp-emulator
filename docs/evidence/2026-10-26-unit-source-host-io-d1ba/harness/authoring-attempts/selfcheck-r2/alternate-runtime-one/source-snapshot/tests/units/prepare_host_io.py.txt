#!/usr/bin/env python3
"""Prepare the twelve original IO cases for three hosts without any API call."""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import copy
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from types import SimpleNamespace
import urllib.request
from unittest.mock import patch

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / 'platform/tools'))
sys.path.insert(0, str(BASE))
import prepare_host_controls as common
import run_io_cases as original
from run_control_cases import build_control_image
from run_host_cases import HOSTS, reference_layout
from run_sensor_cases import verify_image_files
from unit_adc_fixture import load_fixture, verify_firmware
from unit_runtime import UnitError, UnitRegistry

GUEST = BASE / 'host_io_probe'
PROBE = GUEST
CASES = original.CASES
digest, write_json, freeze_toolchain = common.digest, common.write_json, common.freeze_toolchain
CONTROLLER_PATHS = {
    'pir': 'GPIO white input/IRQ; AS312 virtual hold timer',
    'dual-button': 'GPIO blue=white, red=yellow; original software click state machines',
    'limit': 'GPIO white input/IRQ counter and reset',
    'key': 'GPIO white active-low input + native RMT yellow single LED',
    'rgb': 'native RMT yellow 3xGRB; threshold/refill/completion and short-frame negative',
    'angle': 'SAR ADC white, original read_u16/read_uv and IDF curve fitting',
    'light': 'SAR ADC white read_u16 + independent GPIO yellow digital; read_uv is not called',
    'buzzer': 'LEDC channel/timer -> GPIO matrix yellow; original Haptic.once timer and natural-zero window',
    'fan': 'LEDC channel/timer -> GPIO matrix yellow; original speed transfer',
    'ir': 'native RMT TX yellow out81+channel, RX white in81+channel; original enabled GC/callback flow',
    'rs485': 'UART1 signal15 TX yellow/RX white; binary FIFO and oversized-RX rejection; UART0 log separate',
    'hub': 'passive same-pin I2C0 bus; ENV-III/NCIR/TVOC child drivers; no HUB slave address',
}


def layout_module():
    spec = importlib.util.spec_from_file_location('host_io_layout_preparation', GUEST / 'host_io_layout.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protocol_audit():
    before = (BASE / 'io_probe/io_program.py').read_text(encoding='utf-8')
    after = (GUEST / 'io_program.py').read_text(encoding='utf-8')
    left, right = ast.parse(before), ast.parse(after)
    hashes = {}
    for node in left.body:
        if isinstance(node, ast.FunctionDef) and node.name != 'show':
            other = next(x for x in right.body if isinstance(x, ast.FunctionDef) and x.name == node.name)
            a, b = ast.get_source_segment(before, node), ast.get_source_segment(after, other)
            assert a == b and ast.dump(node, include_attributes=False) == ast.dump(other, include_attributes=False), node.name
            hashes[node.name] = digest(a.encode())
    def initialization(tree):
        return next(x for x in tree.body if isinstance(x, ast.If) and isinstance(x.test, ast.Compare)
                    and isinstance(x.test.left, ast.Name) and x.test.left.id == 'CASE')
    a, b = initialization(left), initialization(right)
    assert ast.get_source_segment(before, a) == ast.get_source_segment(after, b), 'original IO initialization/negative controls changed'
    hashes['initialization_and_negative_controls'] = digest(ast.get_source_segment(before, a).encode())
    old_loop = next(x for x in left.body if isinstance(x, ast.While))
    new_loop = copy.deepcopy(next(x for x in right.body if isinstance(x, ast.While)))
    # Exactly one added observer at the outer loop boundary; all original
    # sampling/output branches and wait_ms calls remain byte-identical.
    observer = new_loop.body.pop(0)
    assert ast.dump(observer, include_attributes=False) == ast.dump(ast.parse('check_internal("loop")').body[0], include_attributes=False)
    assert ast.dump(old_loop, include_attributes=False) == ast.dump(new_loop, include_attributes=False), 'original IO sampling/output/timing changed'
    old_body = ast.get_source_segment(before, old_loop)
    new_body = ast.get_source_segment(after, next(x for x in right.body if isinstance(x, ast.While)))
    assert old_body == new_body.replace('    check_internal("loop")\n', '', 1), 'original IO loop bytes changed'
    hashes['original_io_loop'] = digest(old_body.encode())
    manifest = original.driver_manifest()
    for name in ('main.py', 'boot.py', 'probe_logging.py'):
        assert (GUEST / name).read_bytes() == (BASE / 'io_probe' / name).read_bytes(), name
    runner_tree = ast.parse((BASE / 'run_io_cases.py').read_text())
    assertions = {n.name: digest(ast.get_source_segment((BASE / 'run_io_cases.py').read_text(), n).encode())
                  for n in runner_tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                  and n.name in {'validate_io', 'run_case', 'Observations', 'validate_evidence'}}
    assert set(assertions) == {'validate_io', 'run_case', 'Observations', 'validate_evidence'}
    return {'guest_protocol_sha256': hashes, 'original_runner_segments': assertions,
            'official_drivers': manifest, 'original_guest_sha256': digest(before.encode()),
            'host_guest_sha256': digest(after.encode()),
            'scope': 'Byte/AST preservation of original protocol and assertions; no execution or PASS inferred.'}, before, after


def source_paths():
    paths, metadata = common.source_paths()
    own = [Path(__file__).resolve(), BASE / 'run_host_io_cases.py', BASE / 'test_host_io_preparation.py', BASE / 'test_host_io_execution.py']
    own += [p for d in (GUEST, BASE / 'io_probe') for p in d.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc' and p.name != '.DS_Store']
    own += [original.IR_CALLBACK_PATCH, original.BUZZER_CALLBACK_PATCH]
    own += [ROOT / 'scripts/bootstrap-unit-runtime.py',
            ROOT / 'patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch',
            ROOT / 'platform/tests/test_unit_ledc_readback_patch.py']
    closure, extra = common.local_import_closure([p for p in own if p.suffix == '.py'])
    paths = sorted(set(paths) | set(own) | closure)
    assert all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT) for p in paths)
    return paths, {'shared_dependencies': metadata, 'io_import_closure': extra,
                   'rule': 'Exact current source and inventory equality; no source-change allowlist.'}


def strict_patch(raw, patch_bytes, filename):
    """Apply the pinned single-file unified patch offline, with zero fuzz."""
    lines = patch_bytes.decode('utf-8').splitlines(keepends=True)
    assert lines[:2] == [f'--- a/{filename}\n', f'+++ b/{filename}\n']
    source, output, cursor = raw.decode('utf-8').splitlines(keepends=True), [], 0
    index = 2
    while index < len(lines):
        match = re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n', lines[index])
        assert match, 'unsupported pinned patch hunk'
        old_start, old_count, new_start, new_count = map(int, match.groups())
        start = old_start - 1
        assert cursor <= start <= len(source)
        output += source[cursor:start]
        assert len(output) == new_start - 1, 'patch target offset differs'
        cursor, removed, added, index = start, 0, 0, index + 1
        while index < len(lines) and not lines[index].startswith('@@ '):
            line = lines[index]
            assert line[:1] in {' ', '+', '-'}, 'unsupported patch line'
            if line[0] in ' -':
                assert cursor < len(source) and source[cursor] == line[1:], 'pinned patch context differs'
                cursor, removed = cursor + 1, removed + 1
            if line[0] in ' +':
                output.append(line[1:])
                added += 1
            index += 1
        assert (removed, added) == (old_count, new_count), 'patch hunk length differs'
    return ''.join(output + source[cursor:]).encode('utf-8')


def custom_driver(files, case, ir_patch=False, buzzer_patch=False):
    manifest = original.driver_manifest()
    enabled = (case == 'ir' and ir_patch) or (case == 'buzzer' and buzzer_patch)
    if not enabled:
        return None
    name = 'ir.py' if case == 'ir' else 'buzzer.py'
    patch_path = original.IR_CALLBACK_PATCH if case == 'ir' else original.BUZZER_CALLBACK_PATCH
    source = original.PROBE / 'io_drivers' / name
    target = files / 'io_drivers' / name
    raw = source.read_bytes()
    assert digest(raw) == manifest[name]['sha256'] == digest(target.read_bytes())
    target.write_bytes(strict_patch(raw, patch_path.read_bytes(), 'io_drivers/' + name))
    assert source.read_bytes() == raw
    return {'path': patch_path.relative_to(ROOT).as_posix(), 'patch_sha256': digest(patch_path.read_bytes()),
            'driver_path': 'io_drivers/' + name, 'original_driver_sha256': digest(raw),
            'patched_driver_sha256': digest(target.read_bytes()), 'original_driver_unchanged': True,
            'scope': 'Explicit generated-copy custom wrapper; frozen firmware, native module and QEMU unchanged.'}


def flavor(case, flags):
    if case == 'ir' and flags['ir_callback_root_patch']:
        return 'custom-guest-ir-callback-root-patch'
    if case == 'buzzer' and flags['buzzer_callback_arity_patch']:
        return 'custom-guest-buzzer-callback-arity-patch'
    return 'reference-app-with-original-unit-drivers-host-io-probe'


def config_bytes(device_id, case, port, profile, flags):
    values = {'CASE': case, 'WHITE': port['pins']['white'], 'YELLOW': port['pins']['yellow'],
              'IR_CALLBACK_ROOT_PATCH': case == 'ir' and flags['ir_callback_root_patch'],
              'BUZZER_CALLBACK_ARITY_PATCH': case == 'buzzer' and flags['buzzer_callback_arity_patch'],
              'DEVICE_ID': device_id, **{k.upper(): profile[k] for k in
                  ('internal_controller', 'external_controller', 'internal_sda', 'internal_scl', 'log_tx', 'log_rx')}}
    return ''.join(f'{k} = {v!r}\n' for k, v in values.items()).encode('utf-8')


def resource_preflight(device_id, case, port, profile, firmware, registry):
    grove = set(port['pins'].values())
    internal = {profile['internal_sda'], profile['internal_scl']}
    logs = {profile['log_tx'], profile['log_rx']}
    assert len(grove) == len(internal) == len(logs) == 2
    assert not (grove & internal or grove & logs or internal & logs), 'host IO/BMI/UART0 pins overlap'
    blockers, risks = [], []
    tree = original.attachments(case, port['id'])
    try:
        registry.attachments(device_id, 'qemu', tree)
    except UnitError as error:
        blockers.append({'code': error.code, 'http_status': error.status, 'reason': error.message, 'kind': 'admission'})
    if case in {'angle', 'light'}:
        fixture = load_fixture()
        try:
            verify_firmware(firmware, fixture)
        except ValueError as error:
            blockers.append({'code': 'adc_fixture_application_mismatch', 'kind': 'fixture-boundary',
                'reason': str(error) + '; original calibrated oracle is retained. Light raw/digital data plane is not inferred unsupported.'})
        if port['pins']['white'] >= 11:
            blockers.append({'code': 'adc_oracle_unit_mismatch', 'kind': 'oracle-boundary',
                'reason': 'white11 uses S3 ADC2 channel0; original validate_io fixes adc_unit=1. Do not inherit the ADC1 curve oracle.'})
    if case == 'ir':
        risks.append('Original callback GC lifetime and raw16 wrapper payload remain observed limitations; only actual host execution can classify this firmware. Custom callback-root flag is explicit.')
    if case == 'buzzer':
        risks.append('Original Haptic timer callback arity and separate LEDC getter gap remain open observations; preserve natural-zero assertion. Custom callback-arity flag is explicit.')
    return {'status': 'BLOCKED' if blockers else 'ADMITTED_NOT_EXECUTED', 'blockers': blockers,
            'known_risks': risks, 'controller_path': CONTROLLER_PATHS[case],
            'pins': copy.deepcopy(port['pins']), 'uart0_log': [43, 44], 'uart1_for_rs485': case == 'rs485',
            'internal_bmi_i2c': {'controller': 1, 'sda': profile['internal_sda'], 'scl': profile['internal_scl']},
            'adc_unit': (1 if port['pins']['white'] <= 10 else 2) if case in {'angle', 'light'} else None,
            'pin_sets_disjoint': True, 'controller_execution': 'NOT RUN'}


def prepare_one(output, device_id, case, matrix, hosts, registry, flags):
    device = next(x for x in matrix['devices'] if x['id'] == device_id)
    visual = layout_module()
    profile = {**HOSTS[device_id], 'log_tx': 43, 'log_rx': 44, 'internal_controller': 1, 'external_controller': 0}
    profile['text'] = list(visual.PROFILES[device_id]['text'])
    profile.setdefault('canvas_size', profile['size'])
    assert device['backend'] == 'qemu-esp32s3' and profile['size'] == list(visual.PROFILES[device_id]['native'])
    host = next(x for x in hosts['hosts'] if x['device_id'] == device_id)
    ports = [p for p in host['ports'] if p.get('visual_port') == 'grove' and p.get('wiring_status') == 'confirmed' and p.get('physical_presence') == 'main-device']
    assert len(ports) == 1
    port = ports[0]
    base = ROOT / device['base']
    layout = reference_layout(base, int(device['flash_size'], 0))
    resources = resource_preflight(device_id, case, port, profile, base.read_bytes(), registry)
    directory = output / device_id / case
    files = directory / 'files'
    shutil.copytree(GUEST, files, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(original.PROBE / 'io_drivers', files / 'io_drivers')
    custom = custom_driver(files, case, flags['ir_callback_root_patch'], flags['buzzer_callback_arity_patch'])
    (files / 'probe_config.py').write_bytes(config_bytes(device_id, case, port, profile, flags))
    for p in files.rglob('*.py'):
        ast.parse(p.read_text(encoding='utf-8'), filename=p.name)
    image = build_control_image(SimpleNamespace(base=base, flash_size=int(device['flash_size'], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=layout['offset'], vfs_size=layout['size'], prog_size=32, out_dir=directory))
    effective = {**device, 'vfs_offset': hex(layout['offset']), 'vfs_size': hex(layout['size'])}
    packaged = verify_image_files(image, files, effective)
    complete, sources = common.verify_full_python(image, files, layout)
    raw, initial = image.read_bytes(), base.read_bytes()
    padded = initial + b'\xff' * (len(raw) - len(initial))
    start, end = layout['offset'], layout['offset'] + layout['size']
    assert raw[:start] == padded[:start] and raw[end:] == padded[end:]
    result = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'device_id': device_id, 'unit_id': case,
        'runtime': 'qemu', 'attachments': original.attachments(case, port['id']), 'port_id': port['id'],
        'host_profile': profile, 'official_host_evidence': port['evidence'], 'reference_layout': layout,
        'layout_plan': json.loads(json.dumps(visual.planned_layout(device_id, case))),
        'display_font': {'name': visual.FONT_NAME, 'scale': visual.PROFILES[device_id]['scale'], 'height': visual.PROFILES[device_id]['font_height']},
        'custom_flags': flags, 'custom_driver_patch': custom, 'firmware_flavor': flavor(case, flags),
        'official_drivers': original.driver_manifest(), 'firmware_sha256': digest(raw), 'base_firmware_sha256': digest(initial),
        'probe_sha256': packaged, 'packaged_full_py_sha256': complete, 'packaged_full_py_sources': sources,
        'prepared_file_sha256': {p.relative_to(files).as_posix(): digest(p.read_bytes()) for p in sorted(files.rglob('*')) if p.is_file()},
        'resource_preflight': resources, 'checks': {'actual_reference_partition': True, 'outside_vfs_unchanged': True,
            'complete_vfs_bytes_and_membership': True, 'host_pin_sets_disjoint': True, 'guest_python_syntax': True},
        'guest_execution': 'NOT RUN', 'web_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN',
        'native_readability': 'NOT REVIEWED; actual font metrics and separate native captures required',
        'api_contacted': False, 'sessions_started': 0}
    write_json(directory / 'prepared.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--device', choices=(*HOSTS, 'all'), default='all')
    parser.add_argument('--case', choices=(*CASES, 'all'), default='all')
    parser.add_argument('--ir-callback-root-patch', action='store_true')
    parser.add_argument('--buzzer-callback-arity-patch', action='store_true')
    args = parser.parse_args()
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT / '.work') and not output.exists(), 'choose a fresh private .work output'
    flags = {k: getattr(args, k) for k in ('ir_callback_root_patch', 'buzzer_callback_arity_patch')}
    audit, before, after = protocol_audit()
    paths, dependencies = source_paths()
    frozen = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in paths}
    import littlefs
    tool_paths, toolchain = freeze_toolchain(littlefs)
    output.mkdir(parents=True, exist_ok=False)
    for name in frozen:
        target = output / 'source-snapshot' / (name + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    for name, data in [('source-before.json', frozen), ('source-dependencies.json', dependencies),
                       ('toolchain-before.json', toolchain), ('protocol-audit.json', audit)]:
        write_json(output / name, data)
    (output / 'guest-probe.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='original-io', tofile='host-io')), encoding='utf-8')
    matrix = json.loads((ROOT / 'tests/uiflow2/device_matrix.json').read_bytes())
    hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_bytes())
    rows = []
    devices = list(HOSTS) if args.device == 'all' else [args.device]
    cases = list(CASES) if args.case == 'all' else [args.case]
    with ExitStack() as guards:
        for owner, name in ((urllib.request, 'urlopen'), (socket.socket, 'connect'), (socket, 'create_connection'), (subprocess, 'Popen')):
            guards.enter_context(patch.object(owner, name, side_effect=AssertionError('offline IO preparation attempted HTTP/socket/process')))
        registry = UnitRegistry()
        for host in devices:
            for case in cases:
                rows.append(prepare_one(output, host, case, matrix, hosts, registry, flags))
                assert all(digest((ROOT / name).read_bytes()) == expected for name, expected in frozen.items()), 'source changed during preparation'
                write_json(output / 'partial-preparation.json', rows)
    assert {p.relative_to(ROOT).as_posix() for p in source_paths()[0]} == set(frozen)
    assert all(digest(p.read_bytes()) == toolchain['files'][name]['sha256'] for name, p in tool_paths.items())
    report = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'case_count': len(rows),
        'selection': {'devices': devices, 'cases': cases}, 'custom_flags': flags,
        'source_sha256': frozen, 'toolchain': toolchain, 'protocol_audit': audit, 'cases': rows,
        'thermal': {'status': 'SEPARATE_SENSOR_PATH_NOT_PREPARED', 'reason': 'Thermal belongs to the sensor runner, raw frame fixtures and native thermal map; never an IO validate_io fallback.'},
        'checks': {'original_protocol_bytes_and_ast': True, 'official_drivers_unchanged': True,
            'source_inventory_and_bytes_unchanged': True, 'toolchain_unchanged': True,
            'complete_vfs_verified': True, 'zero_http_socket_or_child_process_calls': True},
        'runtime_execution': 'NOT RUN', 'web_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN',
        'api_contacted': False, 'sessions_started': 0, 'admission_modified': False}
    write_json(output / 'readiness.json', report)
    print(json.dumps({'status': report['status'], 'case_count': len(rows),
        'blocked_cases': sum(bool(x['resource_preflight']['blockers']) for x in rows), 'api_contacted': False, 'sessions_started': 0}))


if __name__ == '__main__':
    main()
