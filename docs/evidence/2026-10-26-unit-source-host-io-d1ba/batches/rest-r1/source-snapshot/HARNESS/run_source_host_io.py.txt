#!/usr/bin/env python3
"""Source API harness for three hosts and eight unchanged original IO cases.

Default/--prepare-only are offline and deny network, processes and BIN builders.
Only root selects --execute; it always prepares a fresh, current source context.
--check replays actual saved evidence offline. It does not execute a guest.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack, contextmanager
import copy
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.parse
import urllib.request
from unittest.mock import patch
import zipfile

import source_api_common as common

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path[:0] = [str(ROOT / 'tests/units'), str(ROOT / 'platform/tools')]
import prepare_host_io as preparation
import run_host_io_cases as host_contract
import run_io_cases as original
from unit_runtime import UnitRegistry

DEFAULT_RUNTIME = '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
DEVICES = ('atoms3r', 'sticks3', 'stopwatch')
CASES = ('pir', 'dual-button', 'limit', 'key', 'rgb', 'fan', 'rs485', 'hub')
FLAGS = {'ir_callback_root_patch': False, 'buzzer_callback_arity_patch': False}
EXPECTED = {
    'pir': {'both_gpio_edges_and_disable_reenable_irq'},
    'dual-button': {'independent_hardware_button_pins_and_click_state_machines'},
    'limit': {'official_limit_button_alias_irq_counter_and_reset'},
    'key': {'active_low_key_and_guest_brightness_rgb_frames'},
    'rgb': {'native_rmt_grb_all_three_leds_and_short_frame_negative'},
    'fan': {'guest_ledc_frequency_and_duty_registers'},
    'rs485': {'uart1_bidirectional_binary_fifo_and_any_read_write', 'fifo_capacity_rejection_and_uart0_log_separation'},
    'hub': {'passive_hub_three_real_drivers_independent_inputs_same_bus', 'hub_has_no_i2c_address'},
}
need, sha, canonical, save, load, now = common.need, common.sha, common.canonical, common.save, common.load, common.now


def git_head():
    """Read the exact checkout commit without spawning Git or modifying refs."""
    location = ROOT / '.git'
    if location.is_file():
        line = location.read_text().strip()
        need(line.startswith('gitdir: '), 'unsupported .git pointer')
        gitdir = (ROOT / line[8:]).resolve()
    else:
        gitdir = location
    head = (gitdir / 'HEAD').read_text().strip()
    if not head.startswith('ref: '):
        value = head
    else:
        reference = head[5:]
        need(reference.startswith('refs/') and '..' not in reference, 'invalid HEAD reference')
        common_dir = (gitdir / (gitdir / 'commondir').read_text().strip()).resolve() if (gitdir / 'commondir').exists() else gitdir
        value = next((p.read_text().strip() for p in (gitdir / reference, common_dir / reference) if p.exists()), None)
        if value is None:
            for path in (gitdir / 'packed-refs', common_dir / 'packed-refs'):
                if path.exists():
                    value = next((line.split()[0] for line in path.read_text().splitlines()
                                  if line and not line.startswith(('#', '^')) and line.split()[-1] == reference), None)
                    if value:
                        break
    need(re.fullmatch('[0-9a-f]{40}', value or ''), 'cannot resolve exact checkout commit')
    return value


@contextmanager
def offline_guard():
    """Fail on an accidental network, browser/process or legacy BIN operation."""
    def denied(*args, **kwargs):
        raise RuntimeError('offline mode forbids API/network/process/browser/BIN operations')
    with ExitStack() as stack:
        targets = [(urllib.request, 'urlopen'), (socket, 'socket'), (socket, 'create_connection'),
                   (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'call'),
                   (subprocess, 'check_call'), (subprocess, 'check_output'), (os, 'system')]
        targets += [(os, name) for name in ('posix_spawn', 'posix_spawnp', 'fork', 'forkpty') if hasattr(os, name)]
        targets += [(original, 'prepare'), (original, 'run_case'), (preparation, 'prepare_one'),
                    (preparation, 'build_control_image'), (host_contract, 'io_adapter'), (host_contract, 'run_one')]
        targets += [(sys.modules['run_service_cases'].Client, '__init__')]
        for obj, name in targets:
            stack.enter_context(patch.object(obj, name, denied))
        yield


def function_hashes():
    selected = {
        'tests/units/run_io_cases.py': {'Observations', 'validate_io', 'validate_evidence', 'attachments'},
        'tests/units/run_host_io_cases.py': {'same_value', 'fresh_markers', 'positive_input_binding', 'INPUTS'},
        'tests/units/prepare_host_io.py': {'protocol_audit', 'resource_preflight', 'config_bytes'},
    }
    hashes = {}
    for name, wanted in selected.items():
        source = (ROOT / name).read_text()
        for node in ast.parse(source).body:
            key = node.name if isinstance(node, (ast.FunctionDef, ast.ClassDef)) else node.targets[0].id if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) else None
            if key in wanted:
                hashes[name + '::' + key] = sha(ast.get_source_segment(source, node).encode())
    need(len(hashes) == sum(len(x) for x in selected.values()), 'original IO/host source contracts missing')
    return hashes


def source_paths():
    paths, dependencies = preparation.source_paths()
    extras = [ROOT / 'platform/tests/unit_web_bridge.mjs', ROOT / 'platform/tools/uiflow_source.py',
              ROOT / 'tests/uiflow2/device_matrix.json']
    extras += [p for p in (ROOT / 'platform/web').rglob('*') if p.is_file() and p.suffix in {'.js', '.css', '.html'}]
    extras += list((ROOT / 'patches/qemu-m5stack-peripherals').glob('*.patch'))
    extras += list((ROOT / 'patches/qemu-unit-runtime').rglob('*.patch'))
    paths = sorted(set(paths) | set(extras))
    need(all(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(ROOT) for p in paths), 'unsafe source inventory')
    return paths, dependencies


def toolchain():
    """Read hashes/ABI only; never invoke the filesystem builder or a process."""
    import littlefs
    paths, report = preparation.freeze_toolchain(littlefs)
    # Freeze the executables used by the explicitly enabled browser bridge too.
    extra = {'node': os.environ.get('M5_UNIT_WEB_BRIDGE_NODE') or shutil.which('node'),
             'chromium': os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}
    report = copy.deepcopy(report)
    report['browser_executables'] = {}
    for label, name in extra.items():
        path = Path(name).resolve() if name else None
        record = {'available': bool(path and path.is_file())}
        if record['available']:
            record.update(filename=path.name, size=path.stat().st_size, sha256=sha(path.read_bytes()))
            paths['browser-' + label] = path
        report['browser_executables'][label] = record
    chrome = Path(extra['chromium'])
    info = chrome.parent.parent / 'Info.plist'
    if info.is_file():
        raw = info.read_bytes()
        report['browser_application'] = {'info_plist_sha256': sha(raw),
                                         'version': str(plistlib.loads(raw)['CFBundleShortVersionString'])}
    report['littlefs_versions'] = {'python': str(getattr(littlefs, '__version__', 'unknown')),
                                  'library': str(littlefs.__LFS_VERSION__), 'disk': str(littlefs.__LFS_DISK_VERSION__)}
    report['playwright_packages'] = {}
    for name in ('playwright', 'playwright-core'):
        package = next((parent / 'node_modules' / name for parent in (ROOT / 'platform/tests', ROOT / 'platform', ROOT, *ROOT.parents)
                        if (parent / 'node_modules' / name / 'package.json').is_file()), None)
        need(package is not None, 'actual browser bridge dependency unavailable: ' + name)
        entries = {}
        for path in sorted(package.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                entries[path.relative_to(package).as_posix()] = {'size': path.stat().st_size, 'sha256': sha(path.read_bytes())}
        report['playwright_packages'][name] = {'version': load(package / 'package.json')['version'], 'files': entries}
    from uiflow_source import FS_CONFIG
    report['source_composer_metadata'] = {'builder': 'uiflow_source/1', 'python': report['python_version'],
                                         'python_abi': report['abi']['cache_tag'],
                                         'littlefs_python': report['littlefs_versions']['python'],
                                         'littlefs_library': report['littlefs_versions']['library'],
                                         'littlefs_disk': report['littlefs_versions']['disk'], 'config': dict(FS_CONFIG)}
    return paths, report


def host_data(device_id):
    matrix = load(ROOT / 'tests/uiflow2/device_matrix.json')['devices']
    device = next(d for d in matrix if d['id'] == device_id)
    visual = preparation.layout_module()
    profile = {**preparation.HOSTS[device_id], 'log_tx': 43, 'log_rx': 44, 'internal_controller': 1, 'external_controller': 0}
    profile['text'] = list(visual.PROFILES[device_id]['text'])
    profile.setdefault('canvas_size', profile['size'])
    need(device['backend'] == 'qemu-esp32s3' and profile['size'] == list(visual.PROFILES[device_id]['native']), 'host backend/native profile drift')
    need(profile['size'] == [int(x) for x in device['expected_size'].split('x')], 'host/matrix native geometry differs')
    host = next(h for h in load(ROOT / 'platform/units/host-ports.json')['hosts'] if h['device_id'] == device_id)
    ports = [p for p in host['ports'] if p.get('visual_port') == 'grove' and p.get('wiring_status') == 'confirmed' and p.get('physical_presence') == 'main-device']
    need(len(ports) == 1, 'host requires one confirmed main-device Grove')
    base = ROOT / device['base']
    layout = preparation.reference_layout(base, int(device['flash_size'], 0))
    return device, profile, ports[0], base, layout


def admission_inventory():
    rows = []
    registry = UnitRegistry()
    for device_id in DEVICES:
        _, profile, port, base, _ = host_data(device_id)
        raw = base.read_bytes()
        for case in preparation.CASES:
            row = preparation.resource_preflight(device_id, case, port, profile, raw, registry)
            rows.append({'device_id': device_id, 'unit_id': case, 'selected': case in CASES,
                         'selection_reason': 'selected unchanged source IO' if case in CASES else
                         'ADC fixture/oracle blocked' if case in {'angle', 'light'} else
                         'explicitly excluded original IR/Buzzer risk; historical result preserved', **row})
    need(sum(r['selected'] for r in rows) == 24 and all(r['status'] == 'ADMITTED_NOT_EXECUTED' for r in rows if r['selected']), 'selected host IO admission changed')
    return {'status': 'READ_ONLY_ADMISSION_NOT_EXECUTION', 'selected_unit_count': 8, 'selected_combinations': 24,
            'controller_runtime': 'NOT RUN', 'rows': rows}


def caller_files(device_id, case, profile, port):
    files, origins = {}, {}
    sources = [(p.relative_to(preparation.GUEST).as_posix(), p) for p in sorted(preparation.GUEST.rglob('*.py'))]
    need({name for name, _ in sources} == {'main.py', 'boot.py', 'probe_logging.py', 'io_program.py', 'host_io_layout.py'}, 'unexpected host IO guest inventory')
    sources += [('io_drivers/' + p.relative_to(original.PROBE / 'io_drivers').as_posix(), p)
                for p in sorted((original.PROBE / 'io_drivers').rglob('*.py'))]
    for name, source in sources:
        need(not source.is_symlink(), 'guest source symlink forbidden')
        data = source.read_bytes()
        text = data.decode('utf-8')
        need(text.encode() == data, 'guest UTF-8 bytes changed')
        ast.parse(text, filename=name)
        files[name] = text
        origins[name] = {'repository_path': source.relative_to(ROOT).as_posix(), 'sha256': sha(data), 'size': len(data), 'origin': 'byte-exact-original-host-IO-or-official-driver'}
    config = preparation.config_bytes(device_id, case, port, profile, FLAGS)
    files['probe_config.py'] = config.decode()
    ast.parse(files['probe_config.py'])
    origins['probe_config.py'] = {'origin': 'exact-formal-host-IO-config-generator', 'sha256': sha(config), 'size': len(config)}
    drivers = original.driver_manifest()
    for name, record in drivers.items():
        need(sha(files['io_drivers/' + name].encode()) == record['sha256'], 'official driver bytes changed: ' + name)
    need(len(files) == 19, 'full host IO caller source count changed; review explicitly')
    return dict(sorted(files.items())), origins, drivers


def fresh_sources(output):
    if (output / 'prepared.json').is_file():
        need(load(output / 'prepared.json')['source_context_commit'] == git_head(), 'checkout commit drift; fresh prepare required')
    frozen = load(output / 'tooling-source-freeze.json')
    paths, dependencies = source_paths()
    current = {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths}
    current.update({'HARNESS/' + name: sha((HERE / name).read_bytes()) for name in ('run_source_host_io.py', 'source_api_common.py')})
    need(current == frozen, 'source inventory/bytes drift; fresh prepare required')
    for name, expected in frozen.items():
        need(sha((output / 'source-snapshot' / (name + '.txt')).read_bytes()) == expected, 'source snapshot bytes changed: ' + name)
    need(dependencies == load(output / 'source-dependencies.json'), 'source dependency closure drift; fresh prepare required')
    need(toolchain()[1] == load(output / 'toolchain-before.json'), 'toolchain/ABI drift; fresh prepare required')
    need(preparation.protocol_audit()[0] == load(output / 'protocol-audit.json'), 'guest/official driver/oracle drift; fresh prepare required')
    need(function_hashes() == load(output / 'original-functions.json'), 'original IO/host assertions drift; fresh prepare required')
    return frozen


def prepare(output, devices, cases, runtime=DEFAULT_RUNTIME, source_context_commit=None):
    need(output.is_relative_to(HERE) and output != HERE and not output.exists(), 'choose a fresh harness child; previous evidence is immutable')
    need(devices and len(devices) == len(set(devices)) and set(devices) <= set(DEVICES), 'unsupported/duplicate device selection')
    need(cases and len(cases) == len(set(cases)) and set(cases) <= set(CASES), 'unsupported/duplicate IO selection')
    need(re.fullmatch('[0-9a-f]{64}', runtime), 'expected runtime must be a full SHA256')
    head = git_head()
    if source_context_commit is not None:
        need(source_context_commit == head, 'source context must be the exact current root post-sync commit')
    output.mkdir(parents=True)
    audit = preparation.protocol_audit()[0]
    functions = function_hashes()
    paths, dependencies = source_paths()
    frozen = {}
    for name, source in [(p.relative_to(ROOT).as_posix(), p) for p in paths] + [('HARNESS/' + name, HERE / name) for name in ('run_source_host_io.py', 'source_api_common.py')]:
        data = source.read_bytes()
        frozen[name] = sha(data)
        target = output / 'source-snapshot' / (name + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    save(output / 'tooling-source-freeze.json', frozen)
    save(output / 'source-dependencies.json', dependencies)
    frozen_toolchain = toolchain()[1]
    save(output / 'toolchain-before.json', frozen_toolchain)
    save(output / 'protocol-audit.json', audit)
    save(output / 'original-functions.json', functions)
    save(output / 'admission-inventory.json', admission_inventory())
    rows = []
    registry = UnitRegistry()
    for device_id in devices:
        device, profile, port, base, layout = host_data(device_id)
        base_sha = sha(base.read_bytes())
        need(base_sha == layout['base_firmware_sha256'], 'reference changed while reading actual partitions')
        for case in cases:
            directory = output / device_id / case
            files, origins, drivers = caller_files(device_id, case, profile, port)
            resources = preparation.resource_preflight(device_id, case, port, profile, base.read_bytes(), registry)
            need(resources['status'] == 'ADMITTED_NOT_EXECUTED', 'host IO is blocked: ' + json.dumps(resources))
            request = {'device_id': device_id, 'files': files, 'expected_base_sha256': base_sha}
            need(len(canonical(request)) <= 1048576, 'source HTTP body exceeds intake limit')
            for name, text in files.items():
                path = directory / 'files' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(text.encode())
            row = {'schema_version': 1, 'device_id': device_id, 'unit_id': case, 'runtime': 'qemu',
                   'source_intake': 'uiflow-source-api', 'source_context_commit': head,
                   'source_context_stage': 'ROOT_SUPPLIED_POST_SYNC' if source_context_commit else 'AUTHORING_ONLY_REPREPARE_AFTER_ROOT_SYNC',
                   'port_id': port['id'], 'host_profile': profile, 'official_host_evidence': port['evidence'],
                   'attachments': original.attachments(case, port['id']), 'layout_plan': json.loads(json.dumps(preparation.layout_module().planned_layout(device_id, case))),
                   'reference_layout': layout, 'reference_file': device['base'], 'flash_size': int(device['flash_size'], 0),
                   'expected_size': profile['size'], 'base_firmware_sha256': base_sha, 'expected_runtime_sha256': runtime,
                   'source_cas_sha256': sha(canonical(files)), 'probe_sha256': {name: sha(text.encode()) for name, text in files.items()},
                   'expected_composer_toolchain': frozen_toolchain['source_composer_metadata'],
                   'official_drivers': drivers, 'original_function_sha256': functions, 'resource_preflight': resources,
                   'firmware_flavor': preparation.flavor(case, FLAGS), 'custom_flags': dict(FLAGS), 'custom_driver_modification': False,
                   'adc_fixture': 'NOT USED', 'host_admission_modified': False, 'caller_file_count': len(files),
                   'ready_marker': 'IO_PROBE_READY ' + case, 'status': 'PREPARED_NO_API_OR_RUNTIME'}
            save(directory / 'source-request.json', request)
            save(directory / 'guest-source-freeze.json', origins)
            save(directory / 'official-driver-proof.json', drivers)
            save(directory / 'prepared.json', row)
            target = directory / 'license-evidence/LICENSE.MIT'
            target.parent.mkdir(parents=True)
            target.write_bytes((original.PROBE / 'io_drivers/LICENSE.MIT').read_bytes())
            rows.append(row)
    save(output / 'prepared.json', {'schema_version': 1, 'status': 'PREPARED_NO_API_OR_RUNTIME', 'created_at': now(),
                                  'source_context_commit': head, 'source_context_stage': rows[0]['source_context_stage'],
                                  'expected_runtime_sha256': runtime, 'cases': rows, 'case_count': len(rows),
                                  'binary_build_or_upload': False, 'network_browser_guest_process_calls': 0,
                                  'final_runtime_source_context_freeze': False if source_context_commit is None else True,
                                  'fresh_prepare_required_after_source_or_toolchain_change': True})
    fresh_sources(output)
    return rows


def source_provenance(firmware, request, row):
    source, files = firmware['source'], request['files']
    meta = source['metadata']
    cas = sha(canonical(files))
    need(source['kind'] == 'uiflow' and source['artifact_id'] == cas == row['source_cas_sha256'], 'source CAS differs')
    need(meta['base_sha256'] == request['expected_base_sha256'] == row['base_firmware_sha256'], 'host-specific source base differs')
    need(meta['firmware_sha256'] == firmware['sha256'] == firmware['firmware_id'], 'derived firmware identity differs')
    entries = {e['path']: e for e in meta['files']}
    need(len(entries) == len(meta['files']) and set(entries) == set(files), 'caller/effective source inventory differs')
    for name, text in files.items():
        need(entries[name]['sha256'] == sha(text.encode()) and entries[name]['size'] == len(text.encode()) and entries[name]['origin'] == 'caller', 'caller source bytes differ: ' + name)
    need(meta['source_sha256'] == meta['effective_source_sha256'] == cas and meta['generated_files'] == [], 'unexpected generated/effective source')
    need(meta['caller_file_count'] == row['caller_file_count'] == len(files) and meta['caller_source_bytes'] == sum(len(v.encode()) for v in files.values()), 'caller source totals differ')
    need(meta['status'] == 'COMPOSED_NOT_EXECUTED' and meta['kind'] == 'uiflow2-source-composition', 'composition overclaims execution')
    need(meta['vfs']['filesystem'] == 'LittleFS' and meta['vfs']['source'] == 'actual-base-partition-table' and
         meta['vfs']['offset'] == row['reference_layout']['offset'] and meta['vfs']['size'] == row['reference_layout']['size'], 'actual host VFS partition differs')
    need(all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged', 'existing_files_readback_verified', 'source_readback_verified')), 'source readback/preservation not proven')
    need(meta['toolchain'] == row['expected_composer_toolchain'], 'actual source API composer toolchain/ABI/config differs from fresh preparation')
    return source


def state_valid(state, row):
    need(state['source'] == 'live' and state['contract_status'] == 'frozen', 'Unit state is not live/frozen')
    need({u['id']: u['unit_id'] for u in state['units']} == {a['id']: a['unit_id'] for a in row['attachments']}, 'Unit attachment topology differs')
    need(len(state['units']) == len(row['attachments']), 'duplicate Unit attachment')
    need(all(u['source'] == 'guest-qom' and u['available'] and not u.get('errors') for u in state['units']), 'Unit controller data plane unavailable')


def properties(state, instance='external1'):
    return next(u['properties'] for u in state['units'] if u['id'] == instance)


def frame(data, row):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        need(image.format == 'PNG' and list(image.size) == row['expected_size'], 'native host framebuffer geometry differs')
        need(image.convert('RGB').getcolors(maxcolors=1) is None, 'host framebuffer is blank/single-color')
    return {'sha256': sha(data), 'size_bytes': len(data), 'native_size': row['expected_size'], 'readability': 'NOT REVIEWED'}


def original_and_fresh(predicate, text, full_serial, prior, offset):
    if not predicate(text):
        return False
    return prior is None or (full_serial.startswith(prior) and len(full_serial) > len(prior) and predicate(text[max(0, len(prior) - offset):]))


def recorded_type(directory):
    class Recorded(original.Observations):
        def __init__(self, *values):
            super().__init__(*values)
            self.trace, self.last_input, self.phase = [], None, 'startup'

        def record(self, event):
            event = {'at': now(), 'event_id': len(self.trace), **event}
            self.trace.append(event)
            save(directory / 'observation-index.json', self.trace)
            return event

        def serial_file(self, text, kind):
            name = f'observations/{len(self.trace):05d}-{kind}.txt'
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(text.encode())
            return name

        def wait(self, predicate, *, offset=0, timeout=60):
            prior = self.trace[self.last_input]['before_cursor']['data'] if self.last_input is not None else None
            value = super().wait(lambda text: original_and_fresh(predicate, text, self.serial, prior, offset), offset=offset, timeout=timeout)
            self.record({'kind': 'wait-success', 'phase': self.phase, 'offset': offset, 'input_event': self.last_input,
                         'serial_file': self.serial_file(self.serial, 'serial'), 'serial_sha256': sha(self.serial.encode())})
            return value

        def marker(self, marker, *, offset=0, timeout=60):
            super().marker(marker, offset=offset, timeout=timeout)
            self.phase = marker
            self.record({'kind': 'marker', 'marker': marker, 'offset': offset, 'input_event': self.last_input,
                         'serial_file': self.serial_file(self.serial, 'marker'), 'serial_sha256': sha(self.serial.encode())})

        def state(self):
            value = super().state()
            name = f'observations/{len(self.trace):05d}-state.json'
            save(directory / name, value)
            self.record({'kind': 'state', 'file': name, 'phase': self.phase, 'input_event': self.last_input})
            return value

        def input(self, values, instance='external1', *, via_ui=True):
            before = self.client.json(f'sessions/{self.session_id}/serial?offset=0&limit=262144', via_ui=False)
            state = self.client.json(f'sessions/{self.session_id}/units', via_ui=False)
            event = self.record({'kind': 'input', 'id': instance, 'values': copy.deepcopy(values), 'via_ui': via_ui,
                                 'before_cursor': before, 'before_live_state': state, 'accepted': None,
                                 'requested': {'id': instance, 'values': copy.deepcopy(values)},
                                 'serial_offset_before_ui': len(before['data']), 'before_serial_sha256': sha(before['data'].encode()),
                                 'request_started_at': now()})
            try:
                value = super().input(values, instance, via_ui=via_ui)
            except Exception as error:
                event.update(accepted=False, error=str(error))
                raise
            else:
                event['accepted'] = True
                self.last_input = event['event_id']
                return value
            finally:
                event['request_returned_at'] = now()
                save(directory / 'observation-index.json', self.trace)

        def qom(self, path, prop):
            value = super().qom(path, prop)
            self.record({'kind': 'qom', 'path': path, 'property': prop, 'value': value})
            return value
    return Recorded


def host_observation(observed, row):
    before = observed.client.json(f'sessions/{observed.session_id}/serial?offset=0&limit=262144', via_ui=False)
    offset = len(before['data'])
    observed.wait(lambda text: bool(re.search(r'(?m)^HOST_IO_INTERNAL loop 36 ([3-9]|[1-9][0-9]+)\r?$', text)), offset=offset, timeout=15)
    visual = preparation.layout_module().PROFILES[row['device_id']]
    fonts = re.findall(r'(?m)^HOST_IO_FONT (\S+) (\S+) (\d+)\r?$', observed.serial)
    need(len(fonts) == 1 and fonts[0][0] == 'Montserrat12' and float(fonts[0][1]) == visual['scale'] and int(fonts[0][2]) == visual['font_height'], 'actual host IO font differs')
    geometry = 'HOST_IO_GEOMETRY %d %d %d' % (*visual['canvas'], visual['rotation'])
    layout = row['layout_plan']
    marker = 'HOST_IO_LAYOUT ' + ' '.join(str(layout[k]) for k in ('x', 'y', 'width', 'body_y', 'line_height', 'body_rows', 'bottom')) + ' 2'
    has = lambda value: re.search(r'(?m)^' + re.escape(value) + r'\r?$', observed.serial) is not None
    need(all(has(value) for value in ('HOST_IO_INTERNAL before 36 1', 'HOST_IO_INTERNAL after_init 36 2', geometry, marker)), 'host BMI/font/canvas/layout marker missing')
    need(re.search(r'(?m)^HOST_IO_DEFAULT_FONT_HEIGHT [1-9][0-9]*\r?$', observed.serial), 'actual default host font metrics missing')
    return {'status': 'VERIFIED', 'before_cursor': before, 'fresh_loop_offset': offset,
            'serial_file': observed.serial_file(observed.serial, 'host-final'), 'serial_sha256': sha(observed.serial.encode()),
            'layout_marker': marker, 'geometry_marker': geometry}


def browser_check(report, row):
    need(all(report[k] == row[k] for k in ('session_id', 'device_id', 'runtime', 'firmware_sha256')) and not report['errors'], 'actual browser identity/errors differ')
    ids = {a['id'] for a in row['attachments']}
    snapshots = [s for s in report['snapshots'] if s.get('session_state') == 'running']
    need(snapshots, 'no actual running DOM snapshot')
    for snap in snapshots:
        need({u['instance'] for u in snap['units']} == ids, 'DOM omits a Unit attachment')
        for unit in snap['units']:
            need(unit['dom_matches_product_readback'] and unit['readback_matches_real_http_response'], 'DOM/product HTTP mismatch')
            props = unit['readback']['properties']
            need(any(any(u['id'] == unit['instance'] and u['properties'] == props for u in e.get('response', {}).get('units', [])) for e in report['readbacks'] + report['posts']), 'DOM has no real browser HTTP backing')
            for key, value in props.items():
                cell = next((c for c in unit['values'] if c['field'] == key), None)
                need(cell is not None, 'DOM property absent: ' + key)
                if key == 'led-rgb' and cell.get('rgb'):
                    colors = value if isinstance(value, list) else [value]
                    need(cell['rgb'] == [f'LED[{i}] #{v:06x}' for i, v in enumerate(colors)], 'actual DOM LED colors differ')
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    need(float(cell['text']) == value, 'numeric DOM output differs: ' + key)
                else:
                    expected = json.dumps(value, separators=(',', ':'), ensure_ascii=False) if isinstance(value, (dict, list)) else str(value).lower() if isinstance(value, bool) else str(value)
                    need(cell['text'] == expected, 'DOM output differs: ' + key)
    if host_contract.INPUTS[row['unit_id']]:
        need(report['actions'] and report['posts'], 'positive input lacks actual browser actions/HTTP')
    else:
        need(not report['posts'], 'output-only RGB/Fan must have zero input POSTs')
    if row['unit_id'] == 'hub':
        need({'env', 'ncir', 'tvoc'} <= {p['request']['id'] for p in report['posts'] if p['status'] == 200}, 'HUB leaf lacks own actual product POST')
    return {'running_snapshots': len(snapshots), 'real_posts': len(report['posts']), 'actions': len(report['actions'])}


def mutation_allowed(path, method):
    """Only the source composition, lease, original Unit input and stop paths."""
    value = urllib.parse.urlsplit(path)
    need(not value.scheme and not value.netloc and not value.path.startswith('/') and '%' not in value.path and '..' not in value.path.split('/'), 'unsafe API path')
    if method in ('GET', 'HEAD'):
        return
    allowed = method == 'POST' and (value.path in ('firmware/uiflow', 'sessions') or re.fullmatch(r'sessions/[A-Za-z0-9_-]+/unit-input', value.path))
    allowed = allowed or method == 'DELETE' and re.fullmatch(r'sessions/[A-Za-z0-9_-]+', value.path) and urllib.parse.parse_qs(value.query) == {'purge': ['0']}
    need(allowed, 'BIN/merged/alternate intake or unsupported API mutation is prohibited')


def evidence_check(data, result, request):
    checked = original.validate_evidence(data, result)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        session, proof = manifest['session'], result['runtime_provenance']
        source = source_provenance(load(Path(result['case_directory']) / 'firmware-response.json'), request, result)
        need(session['firmware_provenance'] == json.loads(archive.read('firmware/uiflow-source.json')) == source and session['source_artifacts'][0] == result['source_cas_sha256'], 'ZIP source provenance differs')
        need(session['pid'] == proof['observed_pid'] and session['worker']['worker_id'] == proof['worker_id'] and session['worker']['generation'] == proof['worker_generation'] and session['worker']['lease_active'], 'ZIP PID/worker/lease differs')
        state = json.loads(archive.read('units/state.json'))
        state_valid(state, result)
        need(json.loads(archive.read('units/contract.json'))['source_hashes'] == state['contract_hashes'], 'ZIP frozen Unit hashes differ')
        frame(archive.read('frames/current.png'), result)
    return {'original': checked, 'source_cas_sha256': source['artifact_id'], 'pid': session['pid']}


def run_case(client, args, row):
    directory = args.out_dir / row['device_id'] / row['unit_id']
    request = load(directory / 'source-request.json')
    result = {**row, 'case_directory': str(directory), 'expected_worker_generation': args.expected_worker_generation,
              'status': 'FAIL', 'checks': {'actual_partition_layout_checked': True}, 'required_markers': [], 'injections': [],
              'started_at': now(), 'hardware_validation': 'NOT RUN'}
    sid, pid = None, None
    with common.HTTPRecorder(directory / 'http'):
        try:
            fresh_sources(args.out_dir)
            need(validate_caller(directory, row) == request, 'caller request changed between preparation and execution')
            inventory = client.json('units?device_id=' + row['device_id'], via_ui=False)
            save(directory / 'live-unit-inventory.json', inventory)
            by_id = {u['id']: u for u in inventory['units']}
            need(all(by_id[a['unit_id']]['runtime']['status'] in ('implemented', 'validated') and row['device_id'] in by_id[a['unit_id']]['runtime'].get('hosts', []) for a in row['attachments']), 'live host/Unit topology is not admitted')
            firmware = client.json('firmware/uiflow', method='POST', payload=request, via_ui=False)
            save(directory / 'firmware-response.json', firmware)
            result['source'] = source_provenance(firmware, request, row)
            result['firmware_sha256'] = firmware['sha256']
            result['firmware_id'] = firmware['firmware_id']
            artifact = client.json('artifacts/' + row['source_cas_sha256'], via_ui=False)
            save(directory / 'source-artifact-metadata.json', artifact)
            need(artifact['artifact_id'] == row['source_cas_sha256'] and artifact['size'] == len(canonical(request['files'])), 'source artifact metadata differs')
            result['checks']['source_api_caller_bytes_base_cas_and_readback'] = True
            payload = {'device_id': row['device_id'], 'runtime': 'qemu', 'firmware_id': firmware['firmware_id'],
                       'uiflow_source_sha256': row['source_cas_sha256'], 'ttl_seconds': 900,
                       'ready_marker': 'IO_PROBE_READY', 'ready_timeout_seconds': 180, 'units': row['attachments']}
            save(directory / 'session-request.json', payload)
            client.web_ui.call('prepare')
            session = client.json('sessions', method='POST', payload=payload)
            sid = result['session_id'] = session['session_id']
            save(directory / 'created-session.json', session)
            print(row['device_id'] + '/' + row['unit_id'] + ': visible source session ' + sid, flush=True)
            observed = recorded_type(directory)(client, sid, result)
            observed.marker(row['ready_marker'], timeout=180)
            current = client.json(f'sessions/{sid}', via_ui=False)
            pid = current['pid']
            save(directory / 'ready-session.json', current)
            proof = client.web_ui.runtime_provenance(current, lambda: client.json(f'sessions/{sid}', via_ui=False))
            need(proof['status'] == 'VERIFIED' and proof['runtime_binary_sha256'] == args.expected_runtime_sha256 and type(proof['worker_generation']) is int and proof['worker_id'], 'direct runtime PID/SHA/worker missing')
            if args.expected_worker_generation is not None:
                need(proof['worker_generation'] == args.expected_worker_generation, 'unexpected live worker generation')
            result['runtime_provenance'] = proof
            client.web_ui_sessions[sid]['provenance_done'] = True
            client._open_web_ui(sid)
            result['checks']['direct_live_runtime_pid_sha_worker_verified'] = True
            original.validate_io(observed, row['unit_id'])
            need(EXPECTED[row['unit_id']] <= set(result['checks']) and all(result['checks'][k] is True for k in EXPECTED[row['unit_id']]), 'complete original IO assertions absent')
            result['checks']['original_validate_io_completed_without_reduction'] = True
            result['host_observation'] = host_observation(observed, row)
            save(directory / 'host-observation.json', result['host_observation'])
            result['checks']['actual_host_font_canvas_layout_and_fresh_internal_bmi'] = True
            state = observed.state()
            state_valid(state, row)
            result['unit_state'] = state
            save(directory / 'final-units.json', state)
            current = client.json(f'sessions/{sid}', via_ui=False)
            save(directory / 'running-session.json', current)
            need(current['firmware_provenance'] == result['source'] and current['source_artifacts'][0] == row['source_cas_sha256'], 'running source pin differs')
            (directory / 'serial.txt').write_bytes(observed.serial.encode())
            data = client.raw(f'sessions/{sid}/frame.png')
            (directory / 'frame.png').write_bytes(data)
            result['frame'] = frame(data, row)
            result['checks']['nonblank_native_host_application_frame'] = True
            client.web_ui.call('capture', session_id=sid, phase='host-original-IO-complete', screenshot=True)
            fresh_sources(args.out_dir)
        except Exception as error:
            result['error'] = type(error).__name__ + ': ' + str(error)
        finally:
            if sid:
                try:
                    current = client.json(f'sessions/{sid}', via_ui=False)
                    pid = pid or current.get('pid')
                    save(directory / 'before-evidence-session.json', current)
                    serial = client.json(f'sessions/{sid}/serial?offset=0&limit=262144', via_ui=False)
                    save(directory / 'final-serial-response.json', serial)
                    (directory / 'serial-final.txt').write_bytes(serial['data'].encode())
                    data = client.raw(f'sessions/{sid}/evidence')
                    (directory / 'evidence.zip').write_bytes(data)
                    result['evidence_sha256'] = sha(data)
                    result['evidence_summary'] = evidence_check(data, result, request)
                    result['checks']['zip_before_stop_original_oracle_source_pid_and_contract'] = True
                except Exception as error:
                    result['evidence_error'] = str(error)
                    result['checks']['zip_before_stop_original_oracle_source_pid_and_contract'] = False
                try:
                    stopped = client.json(f'sessions/{sid}?purge=0', method='DELETE')
                    save(directory / 'stop-response.json', stopped)
                    history = client.json(f'sessions/{sid}', via_ui=False)
                    save(directory / 'retained-session.json', history)
                    need(stopped['state'] == history['state'] == 'stopped' and history['flash_retained'] is False and history['last_frame_available'] and not history['worker']['lease_active'], 'retained history/Flash/lease differs')
                    need(history['firmware_provenance'] == result.get('source'), 'retained source provenance differs')
                    need(type(pid) is int and pid > 0, 'owned runtime PID missing')
                    deadline = time.monotonic() + 15
                    while not common.pid_gone(pid) and time.monotonic() < deadline:
                        time.sleep(.1)
                    need(common.pid_gone(pid), 'owned QEMU remains after stop')
                    data = client.raw(f'sessions/{sid}/frame.png', via_ui=False)
                    (directory / 'history-frame.png').write_bytes(data)
                    frame(data, row)
                    health = client.json('health', via_ui=False)
                    save(directory / 'cleanup-health.json', health)
                    need(health['ok'] is True and health['capacity']['active_sessions'] == 0, 'service is not idle after case')
                    result['cleanup'] = {'owned_pid': pid, 'pid_gone': True, 'flash_retained': False, 'health_active_sessions': 0}
                    result['checks']['purge_zero_history_frame_flash_release_pid_exit_idle'] = True
                except Exception as error:
                    result['cleanup_error'] = str(error)
                    result['checks']['purge_zero_history_frame_flash_release_pid_exit_idle'] = False
                try:
                    report = load(args.out_dir / 'browser' / sid / 'web-report.json')
                    result['browser'] = browser_check(report, result)
                    result['checks']['actual_product_dom_http_match'] = True
                except Exception as error:
                    result['browser_error'] = str(error)
                    result['checks']['actual_product_dom_http_match'] = False
            result['status'] = 'PASS' if sid and not any(result.get(k) for k in ('error', 'evidence_error', 'cleanup_error', 'browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL'
            result['finished_at'] = now()
            save(directory / 'result.json', result)
    if result['status'] == 'PASS':
        try:
            result['saved_case_replay'] = check_case(args.out_dir, row)
        except Exception as error:
            result.update(status='FAIL', replay_error=type(error).__name__ + ': ' + str(error))
        save(directory / 'result.json', result)
    print(row['device_id'] + '/' + row['unit_id'] + ': ' + result['status'] + ' ' + result.get('error', result.get('replay_error', '')), flush=True)
    return result


def bounded_windows(directory, events, serial):
    accepted = [e for e in events if e['kind'] == 'input' and e['accepted']]
    windows = []
    for index, event in enumerate(accepted):
        before = event['before_cursor']['data']
        need(serial.startswith(before), 'pre-input UART is not a prefix of final actual UART')
        waits = [e for e in events if e['kind'] == 'wait-success' and e.get('input_event') == event['event_id']]
        need(waits, 'accepted input has no completed original guest predicate')
        text = (directory / waits[-1]['serial_file']).read_bytes().decode()
        need(text.startswith(before) and len(text) > len(before) and serial.startswith(text), 'input has no genuine fresh UART suffix')
        upper = len(accepted[index + 1]['before_cursor']['data']) if index + 1 < len(accepted) else len(serial)
        need(len(text) <= upper, 'guest observation crossed next input upper boundary')
        windows.append({'event': event, 'text': text[len(before):], 'lower': len(before), 'observed_end': len(text), 'upper': upper})
    return windows


def semantic_check(directory, row, result):
    events = load(directory / 'observation-index.json')
    serial = (directory / 'serial-final.txt').read_bytes().decode()
    need(not any(x in serial for x in original.GUEST_FAILURES), 'IO guest failure in actual UART')
    has = lambda text, marker: re.search(r'(?m)^' + re.escape(marker) + r'\r?$', text) is not None
    need(has(serial, row['ready_marker']), 'original guest ready marker absent')
    windows = bounded_windows(directory, events, serial)
    expected = host_contract.INPUTS[row['unit_id']]
    need(len(windows) == len(expected), 'original accepted input count differs')
    for item, (instance, values) in zip(windows, expected):
        event = item['event']
        need(event['id'] == instance and event['values'] == values and event['via_ui'] is True, 'original positive input order/vector/UI path differs')
    final = load(directory / 'final-units.json')
    state_valid(final, row)
    case = row['unit_id']
    if case == 'pir':
        markers = ('IO_PIR_CALLBACK 1 1', 'IO_PIR_CALLBACK 0 1', 'IO_PIR 1 1 1 1', 'IO_PIR_DISABLED_DONE 1 1', 'IO_PIR_CALLBACK 1 2', 'IO_PIR_CALLBACK 0 2')
        for item, marker in zip(windows, markers):
            need(has(item['text'], marker), 'fresh bounded PIR callback/state absent')
        need('IO_PIR_CALLBACK' not in windows[2]['text'] + windows[3]['text'] and has(windows[3]['text'], 'IO_PIR_REENABLED'), 'PIR disabled IRQ/rearm evidence differs')
    elif case == 'dual-button':
        for item, (raw, clicks) in zip(windows, (((0, 1), None), ((1, 1), (1, 0)), ((1, 0), None), ((1, 1), (1, 1)))):
            need(re.search(r'(?m)^IO_DUAL %d %d ' % raw, item['text']), 'fresh DualButton raw GPIO absent')
            if clicks:
                need(has(item['text'], 'IO_DUAL_CLICK %d %d' % clicks), 'fresh DualButton click state absent')
    elif case == 'limit':
        need(has(serial, 'IO_LIMIT_BUTTON_ALIAS 1'), 'original LIMIT alias absent')
        for item, (raw, count) in zip(windows, ((0, 0), (1, 1), (0, 2), (1, 3))):
            need(has(item['text'], f'IO_LIMIT {raw} {count}'), 'fresh LIMIT edge counter absent')
        need(has(windows[-1]['text'], 'IO_LIMIT_COUNT_RESET 0'), 'fresh LIMIT reset absent')
    elif case == 'key':
        for item, (raw, color) in zip(windows, ((0, 0x123456), (1, 0x2468AC))):
            need(has(item['text'], f'IO_KEY_RAW {raw}'), 'fresh Key raw GPIO absent')
            states = [load(directory / e['file']) for e in events if e['kind'] == 'state' and e.get('input_event') == item['event']['event_id']]
            need(any(properties(state)['led-rgb'] == color for state in states), 'Key RGB lacks actual guest QOM frame')
        need(properties(final)['led-frames'] >= 3, 'Key native RMT frame count absent')
    elif case == 'rgb':
        markers = ('IO_RGB_FULL 1', 'IO_RGB_SHORT 1', 'IO_RGB_FULL 2')
        positions = [serial.index(marker) for marker in markers]
        need(positions == sorted(positions) and len(set(positions)) == 3, 'RGB full/short/full guest order differs')
        states = {marker: [properties(load(directory / e['file'])) for e in events if e['kind'] == 'state' and e['phase'] == marker] for marker in markers}
        first = [p for p in states[markers[0]] if p['led-rgb'] == [0x112233, 0x445566, 0x778899]]
        need(first and states[markers[1]], 'RGB first full/short actual QOM observations missing')
        need(any(short['led-rgb'] == before['led-rgb'] and short['led-frames'] == before['led-frames'] and short['incomplete-frames'] > before['incomplete-frames'] for before in first for short in states[markers[1]]), 'RGB short frame fabricated a completed frame or lacks negative counter')
        need(any(p['led-rgb'] == [0xA1B2C3, 0x010203, 0x040506] for p in states[markers[2]]), 'RGB second full chain absent')
        counters = {e['property']: e['value'] for e in events if e['kind'] == 'qom' and e['path'] == '/machine/rmt0'}
        need(counters == result['rmt_controller'] and counters['tx-symbols'] >= 168 and counters['tx-threshold-events'] > 0 and counters['tx-completions'] >= 3 and counters['tx-errors'] == 0, 'RGB actual RMT threshold/refill/completion counters differ')
    elif case == 'fan':
        for stage, freq, setting in ((0, 1000, 0), (1, 1000, 25), (2, 1500, 100)):
            marker = f'IO_FAN {stage} {freq} {setting}'
            need(has(serial, marker), 'Fan original guest stage missing')
            duty = round((setting - 1) * 953 / 99 + 70) / 1023 * 100 if setting else 0
            states = [properties(load(directory / e['file'])) for e in events if e['kind'] == 'state' and e['phase'] == marker]
            need(any(abs(p['frequency-hz'] - freq) <= max(2, freq * .02) and abs(p['duty-pct'] - duty) <= .5 for p in states), 'Fan original PWM stage lacks actual LEDC QOM')
        need(properties(final)['output-transitions'] >= 3, 'Fan real LEDC transitions absent')
    elif case == 'rs485':
        incoming, initial = b'peer-to-guest\0\x7f\xff', b'guest-to-peer\0\x7f\xff'
        reply = b'echo:' + incoming
        need(has(windows[0]['text'], 'IO_RS485_RX ' + incoming.hex()) and has(windows[0]['text'], f'IO_RS485_ECHO {len(reply)} {reply.hex()}'), 'fresh binary UART RX/echo absent')
        props = properties(final)
        need(props['tx-hex'] == (initial + reply).hex() and props['read-bytes'] == len(incoming) and props['written-bytes'] == len(initial + reply), 'UART1 FIFO bytes/counters differ')
        rejected = [e for e in events if e['kind'] == 'input' and e['accepted'] is False]
        need(len(rejected) == 1 and rejected[0]['via_ui'] is False and rejected[0]['values'] == {'rx-hex': (b'x' * 256).hex()} and 'FIFO' in rejected[0]['error'] and re.search(r'HTTP (400|409|422)', rejected[0]['error']), 'original RS485 FIFO negative missing')
    elif case == 'hub':
        need(has(serial, 'IO_HUB_SCAN 68 88 90 112'), 'HUB same-bus leaf address scan absent')
        current = copy.deepcopy(original.HUB_INITIAL)
        for item in windows:
            event = item['event']
            current[event['id']].update(event['values'])
            values = [*current['env'].values(), *current['ncir'].values(), *current['tvoc'].values()]
            vectors = [[float(x) for x in line.split()] for line in re.findall(r'(?m)^IO_HUB ([^\r\n]+)', item['text'])]
            need(any(len(v) == 7 and all(abs(a - b) <= tolerance for a, b, tolerance in zip(v, values, (.2, .2, 1.5, .021, .021, 0, 0))) for v in vectors), 'fresh HUB cumulative leaf driver vector absent')
        for instance in current:
            need(all(properties(final, instance)[key] > 0 for key in ('transactions', 'read-bytes', 'written-bytes', 'input-events')), 'HUB leaf controller counters missing')
    identities = [(phase, int(chip), int(count)) for phase, chip, count in re.findall(r'(?m)^HOST_IO_INTERNAL (before|after_init|loop) (\d+) (\d+)\r?$', serial)]
    need(identities[:2] == [('before', 36, 1), ('after_init', 36, 2)] and all(chip == 36 for _, chip, _ in identities), 'onboard BMI270 identity evidence differs')
    need(all(a[2] < b[2] for a, b in zip(identities, identities[1:])), 'onboard read counter is not strictly increasing')
    host = load(directory / 'host-observation.json')
    text = (directory / host['serial_file']).read_bytes().decode()
    need(sha(text.encode()) == host['serial_sha256'] and text.startswith(host['before_cursor']['data']) and len(host['before_cursor']['data']) == host['fresh_loop_offset'], 'host final UART lower cursor differs')
    need(re.search(r'(?m)^HOST_IO_INTERNAL loop 36 ([3-9]|[1-9][0-9]+)\r?$', text[host['fresh_loop_offset']:]), 'no fresh onboard BMI after original IO assertions')
    visual = preparation.layout_module().PROFILES[row['device_id']]
    fonts = re.findall(r'(?m)^HOST_IO_FONT (\S+) (\S+) (\d+)\r?$', serial)
    need(len(fonts) == 1 and fonts[0][0] == 'Montserrat12' and float(fonts[0][1]) == visual['scale'] and int(fonts[0][2]) == visual['font_height'], 'actual font metrics differ')
    need(has(serial, host['geometry_marker']) and has(serial, host['layout_marker']) and re.search(r'(?m)^HOST_IO_DEFAULT_FONT_HEIGHT [1-9][0-9]*\r?$', serial), 'actual host canvas/layout markers missing')
    return {'status': 'PASS', 'accepted_inputs': len(windows), 'bounded_windows': [{k: item[k] for k in ('lower', 'observed_end', 'upper')} for item in windows],
            'internal_log_records': len(identities), 'last_internal_counter': identities[-1][2], 'native_readability': 'NOT REVIEWED'}


def validate_caller(directory, row):
    request = load(directory / 'source-request.json')
    need(set(request) == {'device_id', 'files', 'expected_base_sha256'} and request['device_id'] == row['device_id'] and request['expected_base_sha256'] == row['base_firmware_sha256'], 'source request identity changed')
    _, profile, port, base, layout = host_data(row['device_id'])
    files, origins, drivers = caller_files(row['device_id'], row['unit_id'], profile, port)
    need(request['files'] == files and row['probe_sha256'] == {name: sha(text.encode()) for name, text in files.items()}, 'caller original host IO/driver/config bytes changed')
    need(origins == load(directory / 'guest-source-freeze.json') and drivers == load(directory / 'official-driver-proof.json') == row['official_drivers'], 'original source origin/driver manifest changed')
    need(row['host_profile'] == profile and row['reference_layout'] == layout and sha(base.read_bytes()) == row['base_firmware_sha256'], 'host profile/base/actual VFS changed')
    need(row['layout_plan'] == json.loads(json.dumps(preparation.layout_module().planned_layout(row['device_id'], row['unit_id']))), 'formal host layout plan changed')
    need(row['resource_preflight'] == preparation.resource_preflight(row['device_id'], row['unit_id'], port, profile, base.read_bytes(), UnitRegistry()), 'host admission/resource preflight changed')
    need(row['attachments'] == original.attachments(row['unit_id'], port['id']) and row['custom_flags'] == FLAGS and row['custom_driver_modification'] is False, 'host topology/flavor changed')
    need(row['source_cas_sha256'] == sha(canonical(files)), 'caller CAS changed')
    need({p.relative_to(directory / 'files').as_posix() for p in (directory / 'files').rglob('*') if p.is_file()} == set(files), 'saved source inventory changed')
    for name, text in files.items():
        need((directory / 'files' / name).read_bytes() == text.encode(), 'saved source bytes changed: ' + name)
    return request


def check_case(output, row):
    directory = output / row['device_id'] / row['unit_id']
    result = load(directory / 'result.json')
    need(result['status'] == 'PASS' and EXPECTED[row['unit_id']] <= set(result['checks']) and all(result['checks'].values()), 'case lacks all original assertions')
    need(all(result[k] == row[k] for k in row if k != 'status'), 'result silently changed prepared identity')
    request = validate_caller(directory, row)
    firmware = load(directory / 'firmware-response.json')
    need(source_provenance(firmware, request, row) == result['source'], 'stored source provenance differs')
    proof = load(output / 'browser' / result['session_id'] / 'runtime-provenance.json')
    need(proof == result['runtime_provenance'] and proof['status'] == 'VERIFIED' and proof['kind'] == 'direct-pid' and proof['runtime_binary_sha256'] == row['expected_runtime_sha256'], 'direct PID runtime evidence differs')
    need(type(proof['observed_pid']) is int and proof['observed_pid'] > 0 and type(proof['worker_generation']) is int and proof['worker_id'] and proof['firmware_sha256'] == result['firmware_sha256'], 'runtime PID/firmware/worker identity absent')
    if result['expected_worker_generation'] is not None:
        need(proof['worker_generation'] == result['expected_worker_generation'], 'worker generation differs')
    actual = []
    for event in load(directory / 'http/index.json'):
        raw = (directory / 'http' / event['response_file']).read_bytes()
        need(sha(raw) == event['response_sha256'] and len(raw) == event['response_size'], 'actual HTTP response bytes changed')
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            payload = None
        mutation_allowed(event['path'].removeprefix('/api/v1/') + ('?' + event['query'] if event['query'] else ''), event['method'])
        actual.append((event, payload, raw))
    def backed(value, suffix, method=None):
        return any(payload == value and e['path'].endswith(suffix) and (method is None or e['method'] == method) for e, payload, _ in actual)
    def request_backed(path, expected, response=None):
        return any(e['method'] == 'POST' and e['path'] == path and json.loads((directory / 'http' / e['request_file']).read_bytes()) == expected and (response is None or p == response) for e, p, _ in actual)
    need(request_backed('/api/v1/firmware/uiflow', request, firmware), 'source composition lacks actual original HTTP request/response')
    inventory = load(directory / 'live-unit-inventory.json')
    need(backed(inventory, '/units', 'GET'), 'live admission inventory lacks actual HTTP backing')
    by_id = {u['id']: u for u in inventory['units']}
    need(all(by_id[a['unit_id']]['runtime']['status'] in ('implemented', 'validated') and row['device_id'] in by_id[a['unit_id']]['runtime'].get('hosts', []) for a in row['attachments']), 'recorded live host/Unit admission differs')
    artifact = load(directory / 'source-artifact-metadata.json')
    need(backed(artifact, '/artifacts/' + row['source_cas_sha256'], 'GET') and artifact['artifact_id'] == row['source_cas_sha256'] and artifact['size'] == len(canonical(request['files'])), 'source artifact lacks actual HTTP metadata')
    startup = load(directory / 'session-request.json')
    need(startup['uiflow_source_sha256'] == row['source_cas_sha256'] and startup['firmware_id'] == firmware['firmware_id'] and startup['device_id'] == row['device_id'] and startup['runtime'] == 'qemu' and startup['units'] == row['attachments'], 'session source pin/firmware/topology differs')
    created = load(directory / 'created-session.json')
    need(request_backed('/api/v1/sessions', startup, created) and created['session_id'] == result['session_id'], 'visible source lease lacks actual HTTP backing')
    for name in ('ready-session.json', 'running-session.json', 'before-evidence-session.json'):
        current = load(directory / name)
        need(backed(current, '/' + result['session_id'], 'GET') and current['pid'] == proof['observed_pid'] and current['firmware_provenance'] == result['source'] and current['source_artifacts'][0] == row['source_cas_sha256'], 'session PID/source continuity differs: ' + name)
    events = load(directory / 'observation-index.json')
    for event in events:
        if event['kind'] in ('wait-success', 'marker'):
            text = (directory / event['serial_file']).read_bytes().decode()
            need(sha(text.encode()) == event['serial_sha256'] and any(e['path'].endswith('/serial') and isinstance(p, dict) and p.get('data') == text for e, p, _ in actual), 'serial observation lacks original actual HTTP backing')
            need(0 <= event['offset'] <= len(text), 'original observation UART offset invalid')
            if event['kind'] == 'marker':
                need(re.search(r'(?m)^' + re.escape(event['marker']) + r'\r?$', text[event['offset']:]), 'original marker absent from original UART window')
        elif event['kind'] == 'state':
            need(backed(load(directory / event['file']), '/units'), 'QOM Unit observation lacks actual HTTP backing')
        elif event['kind'] == 'input':
            need(backed(event['before_cursor'], '/serial') and backed(event['before_live_state'], '/units'), 'input UART/QOM baseline lacks actual HTTP backing')
            if event['accepted'] is False:
                need(not event['via_ui'] and row['unit_id'] == 'rs485' and any(e['method'] == 'POST' and e['status'] in (400, 409, 422) and e['path'].endswith('/unit-input') and json.loads((directory / 'http' / e['request_file']).read_bytes()) == event['requested'] for e, _, _ in actual), 'negative input lacks actual API rejection')
        elif event['kind'] == 'qom':
            need(any(e['path'].endswith('/qom') and urllib.parse.parse_qs(e['query']) == {'path': [event['path']], 'property': [event['property']]} and isinstance(p, dict) and p.get('value') == event['value'] for e, p, _ in actual), 'scalar QOM lacks actual HTTP backing')
    host = load(directory / 'host-observation.json')
    host_text = (directory / host['serial_file']).read_bytes().decode()
    need(backed(host['before_cursor'], '/serial') and any(e['path'].endswith('/serial') and isinstance(p, dict) and p.get('data') == host_text for e, p, _ in actual), 'final host BMI lower/upper cursor lacks actual HTTP backing')
    serial_response = load(directory / 'final-serial-response.json')
    serial = (directory / 'serial-final.txt').read_bytes().decode()
    need(backed(serial_response, '/serial') and serial_response['data'] == serial, 'final UART lacks actual HTTP backing')
    browser = load(output / 'browser' / result['session_id'] / 'web-report.json')
    browser_summary = browser_check(browser, result)
    expected_browser = load(output / 'toolchain-before.json').get('browser_application')
    if expected_browser:
        need(browser['browser_version'] == expected_browser['version'], 'actual browser version differs from fresh toolchain')
    frozen = load(output / 'tooling-source-freeze.json')
    need(all(frozen.get(name) == digest for name, digest in browser['source_sha256'].items()), 'browser product source differs from frozen source')
    positive = [e for e in events if e['kind'] == 'input' and e['accepted'] is True]
    binding = host_contract.positive_input_binding({**row, 'firmware_sha256': result['firmware_sha256']}, positive, browser, serial, result)
    semantics = semantic_check(directory, row, result)
    data = (directory / 'evidence.zip').read_bytes()
    need(sha(data) == result['evidence_sha256'], 'evidence ZIP bytes changed')
    evidence_check(data, result, request)
    zip_indices = [i for i, (e, _, raw) in enumerate(actual) if e['method'] == 'GET' and e['path'].endswith('/evidence') and raw == data]
    stop_indices = [i for i, (e, _, _) in enumerate(actual) if e['method'] == 'DELETE' and e['path'].endswith('/' + result['session_id']) and urllib.parse.parse_qs(e['query']) == {'purge': ['0']}]
    need(len(zip_indices) == len(stop_indices) == 1 and zip_indices[0] < stop_indices[0], 'evidence ZIP was not fetched before purge=0 stop')
    history, stopped, health = (load(directory / name) for name in ('retained-session.json', 'stop-response.json', 'cleanup-health.json'))
    need(backed(history, '/' + result['session_id'], 'GET') and backed(stopped, '/' + result['session_id'], 'DELETE') and backed(health, '/health', 'GET'), 'cleanup has no actual HTTP backing')
    need(stopped['state'] == history['state'] == 'stopped' and history['flash_retained'] is False and history['last_frame_available'] is True and not history['worker']['lease_active'] and history['firmware_provenance'] == result['source'], 'history source/Flash/lease differs')
    need(health['ok'] is True and health['capacity']['active_sessions'] == 0 and result['cleanup']['owned_pid'] == proof['observed_pid'] and result['cleanup']['pid_gone'], 'recorded owned PID/idle cleanup missing')
    running_png = (directory / 'frame.png').read_bytes()
    need(frame(running_png, row) == result['frame'] and any(i < stop_indices[0] and e['path'].endswith('/frame.png') and raw == running_png for i, (e, _, raw) in enumerate(actual)), 'native running frame lacks actual pre-stop HTTP backing')
    history_png = (directory / 'history-frame.png').read_bytes()
    frame(history_png, row)
    need(any(i > stop_indices[0] and e['path'].endswith('/frame.png') and raw == history_png for i, (e, _, raw) in enumerate(actual)), 'retained native frame was not actually fetched after stop')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        contract = json.loads(archive.read('units/contract.json'))
        for name, digest in contract['source_hashes'].items():
            need(frozen.get('platform/units/' + name) == digest, 'ZIP Unit source not bound to preparation freeze')
    return {'device_id': row['device_id'], 'unit_id': row['unit_id'], 'session_id': result['session_id'], 'status': 'PASS',
            'semantic': semantics, 'positive_input_binding': binding, 'browser': browser_summary, 'worker_generation': proof['worker_generation']}


def checksums(output):
    files = sorted(p for p in output.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (output / 'SHA256SUMS').write_text(''.join(sha(p.read_bytes()) + '  ' + p.relative_to(output).as_posix() + '\n' for p in files))


def check_saved(output):
    need(output.is_relative_to(HERE) and output != HERE, 'only replay a harness child')
    seen = set()
    for line in (output / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (output / name).resolve()
        need(name not in seen and path.is_relative_to(output.resolve()) and sha(path.read_bytes()) == expected, 'saved evidence checksum changed: ' + name)
        seen.add(name)
    need(seen == {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file() and p.name != 'SHA256SUMS'}, 'saved artifact inventory changed')
    fresh_sources(output)
    prepared = load(output / 'prepared.json')
    rows = prepared['cases']
    need(rows and len({(r['device_id'], r['unit_id']) for r in rows}) == len(rows), 'empty/duplicate saved selection')
    need(len(rows) == prepared['case_count'] and prepared['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC', 'live result was not freshly prepared under root post-sync context')
    batch = load(output / 'batch-result.json')
    need(batch['status'] == 'PASS' and not batch['bridge_close_error'] and len(batch['cases']) == len(rows), 'batch result/browser cleanup incomplete')
    health = load(output / 'initial-health.json')
    need(health['ok'] is True and health['capacity']['active_sessions'] == 0, 'batch did not begin with idle service')
    initial_events = load(output / 'batch-http/index.json')
    need(len(initial_events) == 1, 'unexpected batch startup HTTP')
    event = initial_events[0]
    raw = (output / 'batch-http' / event['response_file']).read_bytes()
    need(event['method'] == 'GET' and event['path'] == '/api/v1/health' and event['status'] == 200 and event['response_sha256'] == sha(raw) and event['response_size'] == len(raw) and json.loads(raw) == health, 'initial idle health lacks actual HTTP backing')
    results = [check_case(output, row) for row in rows]
    return {'status': 'PASS', 'cases': results,
            'scope': 'Exact original host IO/config/official driver bytes; complete unchanged validate_io/validate_evidence; actual source API/PID/DOM/HTTP/bounded UART/QOM/ZIP/cleanup. Hardware NOT RUN.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--device', choices=DEVICES, action='append')
    parser.add_argument('--case', choices=CASES, action='append')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepare-only', action='store_true')
    modes.add_argument('--execute', action='store_true')
    modes.add_argument('--check', action='store_true')
    parser.add_argument('--api-url', default='http://127.0.0.1:8787')
    parser.add_argument('--expected-runtime-sha256', default=DEFAULT_RUNTIME)
    parser.add_argument('--expected-worker-generation', type=int)
    parser.add_argument('--source-context-commit', help='Root supplies current exact post-sync commit; execute always freshly prepares')
    args = parser.parse_args(argv)
    args.out_dir = args.out_dir.resolve()
    need(args.out_dir.is_relative_to(HERE) and args.out_dir != HERE, 'output must be a fresh harness child')
    if args.check:
        with offline_guard():
            summary = check_saved(args.out_dir)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.execute:
        need(os.environ.get('M5_UNIT_WEB_BRIDGE') == '1', 'root execution requires actual product Web bridge')
        need(args.source_context_commit is not None and args.source_context_commit == git_head(), 'root must supply current commit for a fresh post-sync source context')
        need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1', 'localhost', '::1'}, 'direct runtime PID verification requires local service')
        need(args.expected_worker_generation is None or args.expected_worker_generation >= 0, 'invalid expected worker generation')
    with offline_guard():
        rows = prepare(args.out_dir, list(dict.fromkeys(args.device or DEVICES)), list(dict.fromkeys(args.case or CASES)), args.expected_runtime_sha256, args.source_context_commit)
    if not args.execute:
        checksums(args.out_dir)
        print(json.dumps({'status': 'PREPARED_NO_API_OR_RUNTIME', 'combinations': len(rows), 'caller_python_files_per_case': 19,
                          'expected_runtime_sha256': args.expected_runtime_sha256, 'final_runtime_source_context_freeze': False,
                          'fresh_prepare_required_after_root_sync': True, 'network_browser_guest_process_calls': 0}, ensure_ascii=False))
        return
    os.environ['M5_UNIT_WEB_BRIDGE_OUT'] = str(args.out_dir / 'browser')
    os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256'] = args.expected_runtime_sha256
    from run_service_cases import Client
    class SourceOnlyClient(Client):
        def raw(self, path, method='GET', **kwargs):
            mutation_allowed(path, method)
            return super().raw(path, method=method, **kwargs)
    client = SourceOnlyClient(args.api_url)
    results = []
    bridge_close_error = None
    try:
        with common.HTTPRecorder(args.out_dir / 'batch-http'):
            health = client.json('health', via_ui=False)
            save(args.out_dir / 'initial-health.json', health)
            need(health['ok'] is True and health['capacity']['active_sessions'] == 0, 'root must begin with an idle service')
        for row in rows:
            result = run_case(client, args, row)
            results.append(result)
            if result.get('cleanup_error'):
                break
    finally:
        try:
            client.web_ui.close()
        except Exception as error:
            bridge_close_error = str(error)
        save(args.out_dir / 'batch-result.json', {'status': 'PASS' if not bridge_close_error and len(results) == len(rows) and all(r['status'] == 'PASS' for r in results) else 'FAIL',
                                                'bridge_close_error': bridge_close_error,
                                                'finished_at': now(), 'cases': [{k: r.get(k) for k in ('device_id', 'unit_id', 'session_id', 'status', 'error', 'replay_error', 'cleanup_error')} for r in results]})
        checksums(args.out_dir)
    need(not bridge_close_error and len(results) == len(rows) and all(r['status'] == 'PASS' for r in results), 'source host IO case/bridge cleanup failed')
    with offline_guard():
        summary = check_saved(args.out_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
