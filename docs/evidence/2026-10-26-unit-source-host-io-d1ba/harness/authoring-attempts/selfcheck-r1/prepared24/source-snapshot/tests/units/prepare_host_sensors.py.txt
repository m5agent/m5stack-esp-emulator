#!/usr/bin/env python3
"""Package six sensor probes for three hosts offline; never contact Device Service."""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import difflib
import importlib.util
import json
from pathlib import Path
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
sys.path.insert(0, str(ROOT / 'tests/units'))
import prepare_host_controls as common
from run_control_cases import build_control_image
from run_host_cases import HOSTS, reference_layout
from run_sensor_cases import CASES as SENSOR_CASES, verify_image_files, verify_drivers
from unit_runtime import UnitRegistry, UnitError

GUEST = BASE / 'host_sensors_probe'
PROBE = GUEST
DRIVERS = BASE / 'sensors_probe/sensor_drivers'
freeze_toolchain = common.freeze_toolchain
ADDRESSES = {'color': 0x29, 'tof': 0x29, 'ncir': 0x5A, 'heart': 0x57,
             'tvoc': 0x58, 'ultrasonic-i2c': 0x57}
digest = common.digest
write_json = common.write_json


def layout_module():
    spec = importlib.util.spec_from_file_location('host_sensor_layout_preparation', GUEST / 'host_sensor_layout.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def protocol_audit():
    original = (ROOT / 'tests/units/sensors_probe/sensor_probe.py').read_text(encoding='utf-8')
    candidate = (GUEST / 'sensor_probe.py').read_text(encoding='utf-8')
    left, right = ast.parse(original), ast.parse(candidate)
    details = {}
    for node in left.body:
        if isinstance(node, ast.FunctionDef):
            other = next(item for item in right.body if isinstance(item, ast.FunctionDef) and item.name == node.name)
            before, after = ast.get_source_segment(original, node), ast.get_source_segment(candidate, other)
            assert before == after and ast.dump(node, include_attributes=False) == ast.dump(other, include_attributes=False), node.name
            details[node.name] = digest(before.encode())
    def branches(tree):
        initialization = next(node for node in tree.body if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                              and isinstance(node.test.left, ast.Name) and node.test.left.id == 'CASE')
        loop = next(node for node in tree.body if isinstance(node, ast.While))
        sample = next(node for node in loop.body if isinstance(node, ast.If))
        return initialization, sample
    for name, before, after in zip(('initialization_and_negative_checks', 'sampling_chain'), branches(left), branches(right)):
        original_bytes = ast.get_source_segment(original, before).encode()
        candidate_bytes = ast.get_source_segment(candidate, after).encode()
        assert original_bytes == candidate_bytes and ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False), name
        details[name] = digest(original_bytes)
    assert 'pause(1000)' in ast.get_source_segment(candidate, branches(right)[0]), 'real SGP30 warmup removed'
    assert 'time.sleep_ms(1000 if CASE == "tvoc" else 150)' in candidate
    manifest = verify_drivers()
    assert len(manifest) == 9
    for name, record in manifest.items():
        assert digest((DRIVERS / name).read_bytes()) == record['sha256'], name
    for name in ('main.py', 'boot.py'):
        assert (GUEST / name).read_bytes() == (ROOT / 'tests/units/sensors_probe' / name).read_bytes()
    return {'original_helpers_and_protocol_segments': details, 'official_driver_count': len(manifest),
            'official_drivers': manifest, 'original_protocol_source_sha256': digest(original.encode()),
            'candidate_protocol_source_sha256': digest(candidate.encode()),
            'scope': 'Source/AST identity only; no sensor assertion or guest execution is inferred.'}, original, candidate


def source_paths():
    paths, metadata = common.source_paths()
    own = [Path(__file__).resolve(), BASE / 'run_host_sensor_cases.py', BASE / 'test_host_sensor_preparation.py']
    own += [path for directory in (GUEST, BASE / 'sensors_probe') for path in directory.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != '.DS_Store']
    closure, extra = common.local_import_closure([path for path in own if path.suffix == '.py'])
    paths = sorted(set(paths) | set(own) | closure)
    assert all(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT) for path in paths)
    return paths, {'shared_current_dependencies': metadata, 'sensor_import_closure': extra,
        'sensor_sources': sorted(path.relative_to(ROOT).as_posix() for path in own),
        'rule': 'Exact current source/inventory equality; no historical freeze or source-change allowlist.'}


def config_bytes(device_id, case, port, profile):
    config = {'CASE': case, 'DEVICE_ID': device_id, 'WHITE': port['pins']['white'], 'YELLOW': port['pins']['yellow'],
              'NO_FIXTURE': False, 'EXPECTED_ADDRESS': ADDRESSES[case],
              **{key.upper(): profile[key] for key in ('internal_controller', 'external_controller', 'internal_sda', 'internal_scl', 'log_tx', 'log_rx')}}
    return ''.join(f'{key} = {value!r}\n' for key, value in config.items()).encode('utf-8')


def prepare_one(output, device_id, case, matrix, hosts, registry, display=None):
    display = display or layout_module()
    device = next(row for row in matrix['devices'] if row['id'] == device_id)
    profile = {**HOSTS[device_id], 'log_tx': 43, 'log_rx': 44,
               'internal_controller': 1, 'external_controller': 0}
    profile.setdefault('canvas_size', profile['size'])
    visual = display.PROFILES[device_id]
    assert device['backend'] == 'qemu-esp32s3'
    assert profile['size'] == list(visual['native']) == [int(value) for value in device['expected_size'].split('x')]
    assert profile['canvas_size'] == list(visual['canvas']) and profile['rotation'] == visual['rotation']
    host = next(row for row in hosts['hosts'] if row['device_id'] == device_id)
    ports = [row for row in host['ports'] if row.get('visual_port') == 'grove' and row.get('wiring_status') == 'confirmed'
             and row.get('physical_presence') == 'main-device']
    assert len(ports) == 1
    port = ports[0]
    assert not {port['pins']['white'], port['pins']['yellow']} & {profile['internal_sda'], profile['internal_scl'], 43, 44}
    base = ROOT / device['base']
    layout = reference_layout(base, int(device['flash_size'], 0))
    directory = output / device_id / case
    directory.mkdir(parents=True, exist_ok=False)
    files = directory / 'files'
    shutil.copytree(GUEST, files, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(DRIVERS, files / 'sensor_drivers', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (files / 'probe_config.py').write_bytes(config_bytes(device_id, case, port, profile))
    for path in files.rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=path.relative_to(files).as_posix())
    image = build_control_image(SimpleNamespace(base=base, flash_size=int(device['flash_size'], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=layout['offset'], vfs_size=layout['size'], prog_size=32, out_dir=directory))
    effective = {**device, 'vfs_offset': hex(layout['offset']), 'vfs_size': hex(layout['size'])}
    packaged = verify_image_files(image, files, effective)
    complete, sources = common.verify_full_python(image, files, layout)
    assert all(complete[name] == value for name, value in packaged.items())
    raw, original = image.read_bytes(), base.read_bytes()
    padded = original + b'\xff' * (len(raw) - len(original))
    start, end = layout['offset'], layout['offset'] + layout['size']
    assert raw[:start] == padded[:start] and raw[end:] == padded[end:], 'packager changed bytes outside actual VFS'
    attachment = {'id': 'external1', 'unit_id': case, 'port_id': port['id'], 'initial': SENSOR_CASES[case]['initial']}
    try:
        registry.attachments(device_id, 'qemu', [attachment])
    except UnitError as error:
        assert error.code == 'runtime_model_gap' and error.status == 409
        admission = {'status': 'BLOCKED', 'code': error.code, 'http_status': error.status, 'reason': error.message}
    else:
        admission = {'status': 'ADMITTED', 'validation': 'NOT RUN'}
    planned = json.loads(json.dumps(display.planned_layout(device_id, case)))
    result = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'device_id': device_id, 'unit_id': case,
        'runtime': 'qemu', 'attachments': [attachment], 'host_profile': profile, 'official_host_evidence': port['evidence'],
        'reference_layout': layout, 'matrix_vfs_matches_reference': (int(device['vfs_offset'], 0), int(device['vfs_size'], 0)) == (layout['offset'], layout['size']),
        'layout_plan': planned, 'display_font': {'name': display.FONT_NAME, 'scale': visual['scale'], 'height': visual['font_height']},
        'width_guard_and_native_readability': 'NOT EXECUTED; actual guest fontHeight/textWidth and native frame are required',
        'firmware_sha256': digest(raw), 'base_firmware_sha256': digest(original), 'probe_sha256': packaged,
        'packaged_full_py_sha256': complete, 'packaged_full_py_sources': sources,
        'prepared_file_sha256': {path.relative_to(files).as_posix(): digest(path.read_bytes()) for path in sorted(files.rglob('*')) if path.is_file()},
        'admission': admission, 'checks': {'real_reference_partition': True, 'complete_vfs_membership_and_bytes': True,
            'outside_vfs_unchanged': True, 'host_pin_sets_disjoint': True, 'guest_python_syntax': True},
        'required_negative_markers': SENSOR_CASES[case]['negative'], 'future_input_vectors': SENSOR_CASES[case]['changes'],
        'guest_execution': 'NOT RUN', 'web_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN', 'api_contacted': False, 'sessions_started': 0,
        'builtin_symbol_occurrences': {name.decode(): original.count(name) for name in (b'cdriver', b'MAX30100', b'get_ir', b'get_red')},
        'builtin_symbol_scope': 'Static byte occurrences only; not callable API or cdriver algorithm execution proof.'}
    write_json(directory / 'prepared.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--device', choices=(*HOSTS, 'all'), default='all')
    parser.add_argument('--case', choices=(*ADDRESSES, 'all'), default='all')
    args = parser.parse_args()
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT / '.work') and not output.exists(), 'choose a fresh private .work output directory'
    import littlefs
    audit, original, candidate = protocol_audit()
    paths, dependencies = source_paths()
    frozen = {path.relative_to(ROOT).as_posix(): digest(path.read_bytes()) for path in paths}
    toolchain_paths, toolchain = common.freeze_toolchain(littlefs)
    output.mkdir(parents=True, exist_ok=False)
    for name in frozen:
        target = output / 'source-snapshot' / (name + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    write_json(output / 'source-before.json', frozen)
    write_json(output / 'source-dependencies.json', dependencies)
    write_json(output / 'toolchain-before.json', toolchain)
    write_json(output / 'protocol-audit.json', audit)
    (output / 'guest-probe.diff').write_text(''.join(difflib.unified_diff(original.splitlines(True), candidate.splitlines(True),
        fromfile='original-sensor-probe', tofile='host-candidate-sensor-probe')), encoding='utf-8')
    matrix = json.loads((ROOT / 'tests/uiflow2/device_matrix.json').read_text())
    hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_text())
    results, display = [], layout_module()
    with ExitStack() as guards:
        for owner, name in ((urllib.request, 'urlopen'), (socket.socket, 'connect'), (socket, 'create_connection'), (subprocess, 'Popen')):
            guards.enter_context(patch.object(owner, name, side_effect=AssertionError('offline preparer attempted HTTP/socket/process')))
        registry = UnitRegistry()
        for host in HOSTS if args.device == 'all' else (args.device,):
            for case in ADDRESSES if args.case == 'all' else (args.case,):
                results.append(prepare_one(output, host, case, matrix, hosts, registry, display))
                assert all(digest((ROOT / name).read_bytes()) == value for name, value in frozen.items()), 'source changed during packaging'
                write_json(output / 'partial-preparation.json', results)
    assert {path.relative_to(ROOT).as_posix() for path in source_paths()[0]} == set(frozen), 'source inventory drift'
    assert all(digest(path.read_bytes()) == toolchain['files'][name]['sha256'] for name, path in toolchain_paths.items()), 'toolchain drift'
    report = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'case_count': len(results),
        'selection': {'devices': list(HOSTS) if args.device == 'all' else [args.device], 'cases': list(ADDRESSES) if args.case == 'all' else [args.case]},
        'source_sha256': frozen, 'toolchain': toolchain, 'protocol_audit': audit, 'cases': results,
        'checks': {'original_protocol_bytes_and_ast': True, 'nine_driver_bytes': True, 'source_inventory_and_bytes_unchanged': True,
                   'complete_vfs_verified': True, 'toolchain_unchanged': True, 'zero_http_socket_or_child_process_calls': True},
        'runtime_execution': 'NOT RUN', 'web_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN',
        'api_contacted': False, 'sessions_started': 0, 'admission_modified': False}
    write_json(output / 'readiness.json', report)
    print(json.dumps({'status': report['status'], 'case_count': len(results), 'blocked_admission_count': sum(row['admission']['status'] == 'BLOCKED' for row in results),
        'source_count': len(frozen), 'api_contacted': False, 'sessions_started': 0}))


if __name__ == '__main__':
    main()
