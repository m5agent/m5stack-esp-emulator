#!/usr/bin/env python3
"""Package device-local control probes offline; never contact Device Service."""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import sysconfig
from types import SimpleNamespace
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'platform/tools'))
sys.path.insert(0, str(ROOT / 'tests/units'))
from run_control_cases import build_control_image  # noqa: E402
from run_host_cases import HOSTS, reference_layout  # noqa: E402
from run_sensor_cases import verify_image_files  # noqa: E402
from unit_runtime import UnitError, UnitRegistry  # noqa: E402
from host_controls_probe import host_control_layout as display  # noqa: E402

PROBE = Path(__file__).parent / 'host_controls_probe'
CASES = {'joystick-v11': 0x52, 'encoder': 0x40, '8encoder': 0x41, 'cardkb': 0x5F, 'rfid2': 0x28}
COMMON = ROOT / 'tests/uiflow2/lib'
LOCAL_IMPORT_ROOTS = (ROOT / 'platform/tools', ROOT / 'tests/units', ROOT / 'tests/uiflow2', ROOT)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def protocol_ast(source):
    run = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == 'run')
    init = next(node for node in run.body if isinstance(node, ast.If))
    # The host canvas guard precedes the unchanged protocol initialization.
    init = next(node for node in run.body if isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == 'CASE')
    loop = next(node for node in run.body if isinstance(node, ast.While))
    sample = next(node for node in loop.body if isinstance(node, ast.If))
    class StripHostObserver(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'check_internal':
                return None
            return self.generic_visit(node)
    return [ast.dump(StripHostObserver().visit(node), include_attributes=False) for node in (init, sample)]


def original_source_paths():
    # Freeze the current implementation and product surface, never an old run's
    # manifest. Inventory equality also detects newly introduced dependencies.
    paths = [Path(__file__).resolve(), Path(__file__).with_name('run_host_control_cases.py'),
             ROOT / 'tests/uiflow2/device_matrix.json',
             ROOT / 'tests/uiflow2/run_profile_ui_test.py', ROOT / 'tests/uiflow2/esp_flash.py']
    for directory in (ROOT / 'platform/web', ROOT / 'platform/units', PROBE,
                      ROOT / 'tests/units/controls_probe'):
        paths += [path for path in directory.rglob('*') if path.is_file()
                  and '__pycache__' not in path.parts and path.name != '.DS_Store' and path.suffix != '.pyc']
    paths += list((ROOT / 'platform/tools').glob('*.py'))
    paths += list((ROOT / 'tests/units').glob('*.py'))
    paths += list((ROOT / 'platform/tests').glob('unit*bridge*.mjs'))
    paths += list((ROOT / 'platform/tests').glob('package*.json'))
    return sorted(set(paths))


def local_import_closure(seeds):
    """Resolve syntactic repository imports without importing discovered modules.

    Function-local and conditional imports are included conservatively. A local
    import edge records source availability, not execution of that code path.
    Firmware modules and third-party/stdlib imports are listed as unresolved;
    they must not be mistaken for host-side substitutes for guest drivers.
    """
    def candidates(base):
        return (base.with_suffix('.py'), base / '__init__.py')

    def resolve(importer, module, level=0):
        if level:
            anchor = importer.parent
            for _ in range(level - 1):
                anchor = anchor.parent
            roots = (anchor,)
        else:
            roots = (importer.parent, *LOCAL_IMPORT_ROOTS)
        for root in roots:
            base = root.joinpath(*module.split('.')) if module else root
            for path in candidates(base) if module else (base / '__init__.py',):
                if path.is_file() and path.resolve().is_relative_to(ROOT):
                    return path.resolve()
        return None

    pending = list(seeds)
    visited, edges, external = set(), [], []
    while pending:
        importer = pending.pop().resolve()
        if importer in visited or importer.suffix != '.py':
            continue
        visited.add(importer)
        tree = ast.parse(importer.read_text(encoding='utf-8'), filename=str(importer.relative_to(ROOT)))
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            owner = parents.get(node)
            contexts = []
            while owner is not None:
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    contexts.append(owner.name)
                owner = parents.get(owner)
            scope = 'module-level' if not contexts else '/'.join(reversed(contexts))
            if isinstance(node, ast.Import):
                modules = [(alias.name, 0) for alias in node.names]
            else:
                base = node.module or ''
                modules = [(base, node.level)] if base else []
                modules += [('.'.join(filter(None, (base, alias.name))), node.level)
                            for alias in node.names if alias.name != '*']
            resolved = set()
            for module, level in modules:
                target = resolve(importer, module, level)
                if target is not None:
                    resolved.add(target)
            record = {'importer': importer.relative_to(ROOT).as_posix(), 'line': node.lineno,
                      'statement': ast.unparse(node), 'scope': scope}
            if resolved:
                record['targets'] = sorted(path.relative_to(ROOT).as_posix() for path in resolved)
                edges.append(record)
                pending.extend(resolved - visited)
            else:
                external.append(record)
    return visited, {
        'method': 'AST-recursive repository-local imports; discovered modules are read, never imported',
        'resolution_roots': [path.relative_to(ROOT).as_posix() or '.' for path in LOCAL_IMPORT_ROOTS],
        'scope': 'Conservative syntactic closure including imports inside functions/conditions; an edge does not prove invocation',
        'local_python_sources': sorted(path.relative_to(ROOT).as_posix() for path in visited),
        'local_import_edges': sorted(edges, key=lambda row: (row['importer'], row['line'])),
        'nonlocal_or_firmware_imports': sorted(external, key=lambda row: (row['importer'], row['line'])),
    }


def source_paths(littlefs=None):
    seeds = original_source_paths()
    common = sorted(COMMON.rglob('*.py'))
    closure, metadata = local_import_closure([*seeds, *common])
    paths = sorted(set(seeds) | closure | set(common))
    assert all(path.is_file() and path.resolve().is_relative_to(ROOT) for path in paths)
    metadata.update({'seed_source_count': len(seeds),
        'common_guest_sources': [path.relative_to(ROOT).as_posix() for path in common],
        'littlefs_wrapper_scope': 'Sources, native extension and interpreter are independently bound in toolchain-before.json.',
        'guest_common_execution_scope': 'rtc_probe.py is injected by the shared builder; controls do not import it.'})
    return paths, metadata


def freeze_toolchain(littlefs):
    package = Path(littlefs.__file__).resolve().parent
    artifacts = {'python-interpreter': Path(sys.executable).resolve(),
                 'littlefs-native-extension': Path(littlefs.lfs.__file__).resolve()}
    artifacts.update({'littlefs/' + name: package / name for name in ('__init__.py', 'context.py', 'errors.py')})
    for metadata in sorted(package.parent.glob('littlefs_python-*.dist-info')):
        for name in ('METADATA', 'WHEEL', 'RECORD'):
            if (metadata / name).is_file():
                artifacts[metadata.name + '/' + name] = metadata / name
    for label, path in (('python-pyconfig.h', sysconfig.get_config_h_filename()),
                        ('python-Makefile', sysconfig.get_makefile_filename())):
        if Path(path).is_file():
            artifacts[label] = Path(path).resolve()
    records = {label: {'filename': path.name, 'size': path.stat().st_size, 'sha256': digest(path.read_bytes())}
               for label, path in sorted(artifacts.items())}
    report = {'python_version': sys.version.split()[0], 'python_executable': Path(sys.executable).name,
              'python_executable_sha256': records['python-interpreter']['sha256'],
              'littlefs_extension': Path(littlefs.lfs.__file__).name,
              'littlefs_extension_sha256': records['littlefs-native-extension']['sha256'],
              'abi': {'python_implementation': sys.implementation.name, 'cache_tag': sys.implementation.cache_tag,
                      'soabi': sysconfig.get_config_var('SOABI'), 'extension_suffix': sysconfig.get_config_var('EXT_SUFFIX'),
                      'multiarch': sysconfig.get_config_var('MULTIARCH'), 'platform': sysconfig.get_platform(),
                      'byteorder': sys.byteorder, 'pointer_bits': 64 if sys.maxsize > 2**32 else 32},
              'files': records}
    return artifacts, report


def verify_full_python(image, files, layout):
    """Require the complete VFS whitelist, including shared builder injection."""
    import littlefs
    expected = {path.relative_to(COMMON).as_posix(): path for path in COMMON.rglob('*.py')}
    expected.update({path.relative_to(files).as_posix(): path for path in files.rglob('*.py')})
    raw = image.read_bytes()[layout['offset']:layout['offset'] + layout['size']]
    fs = littlefs.LittleFS(context=littlefs.UserContext(buffer=bytearray(raw)), block_size=4096,
        block_count=layout['size'] // 4096, read_size=128, prog_size=32, lookahead_size=128, block_cycles=100, mount=False)
    fs.mount()
    hashes, sources, actual = {}, {}, set()
    try:
        def walk(directory):
            for name in fs.listdir(directory):
                path = directory.rstrip('/') + '/' + name
                if fs.stat(path).type == 2:
                    walk(path)
                else:
                    actual.add(path.lstrip('/'))
        walk('/')
        assert actual == set(expected), ('unexpected or missing packaged files', sorted(actual - set(expected)), sorted(set(expected) - actual))
        for name, source in sorted(expected.items()):
            with fs.open('/' + name, 'rb') as stream:
                content = stream.read()
            assert content == source.read_bytes(), 'packaged Python bytes differ: ' + name
            hashes[name] = digest(content)
            sources[name] = {'source': source.relative_to(ROOT).as_posix(), 'sha256': hashes[name],
                             'role': 'shared-common-injection' if source.is_relative_to(COMMON) else 'prepared-probe-source'}
    finally:
        fs.unmount()
    return hashes, sources





def layout_preflight(profile, case, device_id):
    # These are the validated display settings, not host-emulated font metrics.
    # The unchanged guest independently measures every header and value line.
    evidence = json.loads((PROBE / 'font-source.json').read_text(encoding='utf-8'))
    configured = display.DISPLAY_PROFILES[device_id]
    assert list(configured['native']) == profile['size']
    assert list(configured['canvas']) == profile['canvas_size']
    assert configured['font_height'] == profile['font_height']
    x, y, width = configured['text']
    headers = (device_id, case) if case in evidence['split_headers'].get(device_id, []) else (device_id + ' ' + case,)
    lines = display.value_lines(case, display.worst_value(case))
    line_height = profile['font_height'] + 1
    body_y = y + len(headers) * line_height + 2
    rows = 10 if case == '8encoder' else len(lines)
    bottom = body_y + rows * line_height
    native_width, native_height = configured['native']
    assert 0 <= x < x + width <= native_width and 0 <= y < bottom <= native_height
    if device_id == 'stopwatch':
        center = native_width / 2
        assert all((cx - center) ** 2 + (cy - center) ** 2 <= center ** 2
                   for cx in (x, x + width) for cy in (y, bottom))
    return {'x': x, 'y': y, 'width': width, 'headers': list(headers),
            'font_height': profile['font_height'], 'line_height': line_height,
            'body_y': body_y, 'body_rows': rows, 'bottom': bottom,
            'worst_case_lines': list(lines), 'font_source': 'tests/units/host_controls_probe/font-source.json',
            'measurement': 'Validated configuration only; guest fontHeight/textWidth and final native readability require new execution.'}


def prepare_one(output, device_id, case, matrix, hosts, registry):
    device = next(row for row in matrix['devices'] if row['id'] == device_id)
    profile = {**HOSTS[device_id], 'log_tx': 43, 'log_rx': 44, 'internal_controller': 1, 'external_controller': 0}
    profile.setdefault('canvas_size', profile['size'])
    font_profile = display.DISPLAY_PROFILES[device_id]
    profile.update(text=list(font_profile['text']), text_size=font_profile['text_size'], font_name=display.FONT_NAME,
                   font_height=font_profile['font_height'], header_line_height=font_profile['font_height'] + 1,
                   line_height=font_profile['font_height'] + 1, body_rows=10)
    layout_check = layout_preflight(profile, case, device_id)
    profile['body_rows'] = layout_check['body_rows']
    assert device['backend'] == 'qemu-esp32s3'
    assert profile['size'] == [int(value) for value in device['expected_size'].split('x')]
    host = next(row for row in hosts['hosts'] if row['device_id'] == device_id)
    ports = [row for row in host['ports'] if row.get('visual_port') == 'grove'
             and row.get('wiring_status') == 'confirmed' and row.get('physical_presence') == 'main-device']
    assert len(ports) == 1
    port = ports[0]
    assert not {port['pins']['white'], port['pins']['yellow']} & {profile['internal_scl'], profile['internal_sda'], 43, 44}
    base = ROOT / device['base']
    layout = reference_layout(base, int(device['flash_size'], 0))
    directory = output / device_id / case
    directory.mkdir(parents=True, exist_ok=False)
    files = directory / 'files'
    shutil.copytree(PROBE, files, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'tests/units/controls_probe/control_drivers', files / 'control_drivers',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    config = {'CASE': case, 'DEVICE_ID': device_id, 'WHITE': port['pins']['white'], 'YELLOW': port['pins']['yellow'],
              'ROTATION': profile['rotation'], 'CANVAS_WIDTH': profile['canvas_size'][0], 'CANVAS_HEIGHT': profile['canvas_size'][1],
              'TEXT_X': profile['text'][0], 'TEXT_Y': profile['text'][1], 'TEXT_WIDTH': profile['text'][2],
              'EXPECTED_ADDRESS': CASES[case]}
    config.update({key.upper(): profile[key] for key in ('text_size', 'header_line_height', 'line_height', 'body_rows',
                  'internal_sda', 'internal_scl', 'internal_controller', 'external_controller', 'log_tx', 'log_rx')})
    (files / 'probe_config.py').write_text(''.join(f'{key} = {value!r}\n' for key, value in config.items()), encoding='utf-8')
    for path in files.rglob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path.relative_to(files)))
    image = build_control_image(SimpleNamespace(base=base, flash_size=int(device['flash_size'], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=layout['offset'], vfs_size=layout['size'], prog_size=32, out_dir=directory))
    effective_device = {**device, 'vfs_offset': hex(layout['offset']), 'vfs_size': hex(layout['size'])}
    packaged = verify_image_files(image, files, effective_device)
    full_packaged, full_sources = verify_full_python(image, files, layout)
    assert all(full_packaged[name] == sha for name, sha in packaged.items())
    raw, original = image.read_bytes(), base.read_bytes()
    start, end = layout['offset'], layout['offset'] + layout['size']
    padded = original + b'\xff' * (len(raw) - len(original))
    assert raw[:start] == padded[:start] and raw[end:] == padded[end:], 'packaging changed bytes outside actual VFS'
    attachment = {'id': 'external1', 'unit_id': case, 'port_id': port['id']}
    try:
        registry.attachments(device_id, 'qemu', [attachment])
        admission = {'status': 'ADMITTED', 'validation': 'NOT RUN'}
    except UnitError as error:
        assert error.code == 'runtime_model_gap' and error.status == 409
        admission = {'status': 'BLOCKED', 'code': error.code, 'http_status': error.status, 'reason': error.message}
    result = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'device_id': device_id, 'unit_id': case,
              'runtime': 'qemu', 'attachments': [attachment], 'host_profile': profile, 'official_host_evidence': port['evidence'],
              'reference_layout': layout, 'matrix_vfs_matches_reference': (int(device['vfs_offset'], 0), int(device['vfs_size'], 0)) == (layout['offset'], layout['size']),
              'layout_preflight': layout_check,
              'firmware_sha256': digest(raw), 'base_firmware_sha256': digest(original), 'probe_sha256': packaged,
              'prepared_file_sha256': {path.relative_to(files).as_posix(): digest(path.read_bytes())
                  for path in sorted(files.rglob('*')) if path.is_file()},
              'packaged_full_py_sha256': full_packaged, 'packaged_full_py_sources': full_sources,
              'checks': {'actual_partition_layout_checked': True, 'packaged_guest_bytes_verified': True,
                         'complete_vfs_python_whitelist_and_bytes_verified': True,
                         'bytes_outside_vfs_unchanged': True, 'host_pin_sets_do_not_overlap': True,
                         'probe_python_syntax': True}, 'admission': admission, 'hardware_execution': 'NOT RUN',
              'guest_execution': 'NOT RUN', 'web_execution': 'NOT RUN', 'adc_fixture': 'NOT USED',
              'session_request_template': {'device_id': device_id, 'runtime': 'qemu', 'firmware_id': '<prepared-upload-firmware-id>',
                 'ttl_seconds': 1200, 'ready_marker': 'CONTROL_PROBE_READY', 'ready_timeout_seconds': 150, 'units': [attachment]}}
    write_json(directory / 'prepared.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', required=True, type=Path)
    parser.add_argument('--device', choices=(*HOSTS, 'all'), default='all')
    parser.add_argument('--case', choices=(*CASES, 'all'), default='all')
    args = parser.parse_args()
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT / '.work') and not output.exists(), 'choose a fresh private .work output directory'
    import littlefs
    toolchain_artifacts, toolchain = freeze_toolchain(littlefs)
    output.mkdir(parents=True, exist_ok=False)
    paths, dependencies = source_paths(littlefs)
    frozen = {}
    for path in paths:
        name = path.relative_to(ROOT).as_posix()
        data = path.read_bytes()
        frozen[name] = digest(data)
        target = output / 'source-snapshot' / (name + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_json(output / 'source-before.json', frozen)
    write_json(output / 'source-dependencies.json', dependencies)
    write_json(output / 'toolchain-before.json', toolchain)
    source = (ROOT / 'tests/units/controls_probe/main.py').read_text()
    candidate = (PROBE / 'host_control_program.py').read_text()
    assert protocol_ast(source) == protocol_ast(candidate), 'Unit initialization/sampling semantics changed beyond host observer calls'
    (output / 'guest-probe.diff').write_text(''.join(difflib.unified_diff(source.splitlines(True), candidate.splitlines(True),
        fromfile='tests/units/controls_probe/main.py', tofile='tests/units/host_controls_probe/host_control_program.py')), encoding='utf-8')
    manifest = json.loads((ROOT / 'tests/units/controls_probe/control_drivers/source-manifest.json').read_text())
    for name, entry in manifest.items():
        assert digest((ROOT / 'tests/units/controls_probe/control_drivers' / name).read_bytes()) == entry['sha256'], name
    matrix = json.loads((ROOT / 'tests/uiflow2/device_matrix.json').read_text())
    hosts = json.loads((ROOT / 'platform/units/host-ports.json').read_text())
    results = []
    with patch.object(urllib.request, 'urlopen', side_effect=AssertionError('offline preparer attempted HTTP')) as http, \
         patch.object(socket.socket, 'connect', side_effect=AssertionError('offline preparer attempted socket')) as connection, \
         patch.object(subprocess, 'Popen', side_effect=AssertionError('offline preparer attempted child process')) as child:
        registry = UnitRegistry()
        for device_id in HOSTS if args.device == 'all' else (args.device,):
            for case in CASES if args.case == 'all' else (args.case,):
                results.append(prepare_one(output, device_id, case, matrix, hosts, registry))
        assert http.call_count == connection.call_count == child.call_count == 0
    assert all(digest((ROOT / name).read_bytes()) == sha for name, sha in frozen.items()), 'frozen source drift'
    assert {path.relative_to(ROOT).as_posix() for path in source_paths()[0]} == set(frozen), 'source dependency inventory drift'
    assert {path.relative_to(ROOT).as_posix() for path in COMMON.rglob('*.py')} == set(dependencies['common_guest_sources']), 'shared common injection inventory drift'
    assert all(digest(path.read_bytes()) == toolchain['files'][label]['sha256'] for label, path in toolchain_artifacts.items()), 'frozen toolchain drift'
    report = {'schema_version': 1, 'status': 'PREPARED_NOT_EXECUTED', 'case_count': len(results),
              'selection': {'devices': list(HOSTS) if args.device == 'all' else [args.device],
                            'cases': list(CASES) if args.case == 'all' else [args.case]},
              'checks': {'original_control_protocol_ast_preserved': True, 'all_ten_official_driver_hashes_verified': True,
                         'sources_frozen_before_first_package': True, 'frozen_sources_unchanged': True,
                         'complete_vfs_python_whitelist_and_bytes_verified': True, 'toolchain_files_unchanged': True,
                         'zero_http_socket_or_child_process_calls': True},
              'runtime_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN', 'api_contacted': False, 'sessions_started': 0,
              'toolchain': toolchain, 'source_sha256': frozen, 'source_dependency_metadata': dependencies, 'cases': results}
    write_json(output / 'readiness.json', report)
    print(json.dumps({'status': report['status'], 'case_count': len(results), 'blocked_admission_count': sum(
        row['admission']['status'] == 'BLOCKED' for row in results), 'api_contacted': False, 'sessions_started': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
