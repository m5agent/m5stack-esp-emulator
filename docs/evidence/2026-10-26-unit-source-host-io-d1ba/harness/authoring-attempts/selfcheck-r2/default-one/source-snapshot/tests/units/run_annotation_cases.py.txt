#!/usr/bin/env python3
"""Same-guest scalar-rail checks. Default ENV/Relay; --case all selects twelve.

No session without --execute. Guest drivers and original assertions are reused.
"""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'platform/tools'))
sys.path.insert(0, str(ROOT / 'tests/units'))
from check_batch_evidence import Checker  # noqa: E402
from run_service_cases import Client, run_case, wait_for  # noqa: E402
from web_ui_bridge import WebUIBridge  # noqa: E402
import run_sensor_cases as sensors  # noqa: E402
import run_io_cases as io_cases  # noqa: E402
from annotation_contract import (  # noqa: E402
    CASES, SENSOR_CASES, FIRST, SECOND, env_rows, guest_marker_matches,
    required_phases, expected_posts, annotation_checks, buzzer_observation,
)
from prepare_host_controls import local_import_closure, freeze_toolchain  # noqa: E402
from run_host_control_cases import DeadlineBridge  # noqa: E402

SOURCES = (
    'platform/web/sessions.js', 'platform/web/sessions.html', 'platform/web/sessions.css',
    'platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/web/unit-annotations.js',
    'platform/web/model-shell.js', 'platform/web/device-shell-factory.js',
    'platform/web/unit-assembly-layout.js', 'tests/uiflow2/lib/rtc_probe.py',
    'platform/web/unit-visual-mappings.js', 'platform/tests/unit_web_bridge.mjs',
    'tests/units/run_service_cases.py', 'tests/units/web_ui_bridge.py',
    'tests/units/check_batch_evidence.py', 'tests/uiflow2/run_profile_ui_test.py',
    'tests/units/run_annotation_cases.py', 'platform/tests/unit_annotation_bridge.mjs',
    'platform/tools/firmware_analysis.py', 'platform/tools/user_firmware_matrix.py',
    'tests/units/probe/main.py', 'tests/units/probe/boot.py',
    'platform/tools/device_service.py', 'platform/tools/serve.py', 'platform/tools/unit_runtime.py',
    'platform/units/catalog.json', 'platform/units/host-ports.json', 'platform/units/runtime-profiles.json',
    'patches/uiflow2-unit-buzzer/0001-accept-soft-timer-callback.patch',
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def source_paths():
    seeds = [ROOT / name for name in SOURCES]
    for name in ('platform/web', 'platform/units', 'tests/units/probe',
                 'tests/units/sensors_probe', 'tests/units/io_probe', 'tests/uiflow2/lib'):
        seeds += [path for path in (ROOT / name).rglob('*') if path.is_file()
                  and '__pycache__' not in path.parts and path.suffix != '.pyc' and path.name != '.DS_Store']
    seeds += [ROOT / 'tests/uiflow2/device_matrix.json']
    closure, _ = local_import_closure(seeds)
    return sorted(set(seeds) | closure)


class AnnotationTransport(DeadlineBridge):
    """Keep common runtime provenance and protocol; select the annotation subclass."""
    def __init__(self, url, output):
        self.dead, self._response_buffer = False, bytearray()
        self.output, self.url = output.resolve(), url
        self.output.mkdir(parents=True, exist_ok=True)
        self.stderr = (self.output / 'bridge.stderr.txt').open('w', encoding='utf-8')
        node = os.environ.get('M5_UNIT_WEB_BRIDGE_NODE') or shutil.which('node')
        if not node:
            raise RuntimeError('Node.js required')
        self.process = subprocess.Popen([node, str(ROOT / 'platform/tests/unit_annotation_bridge.mjs'), url, str(self.output)],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        text=True, encoding='utf-8', bufsize=1, cwd=ROOT)
        atexit.register(self.close)


class AnnotationClient(Client):
    def __init__(self, url, case, output):
        super().__init__(url)
        self.case, self.env_checked, self.relay_values = case, False, set()
        self.guest_vectors = []
        self.observed_phases, self.owned_session_ids, self.annotation_errors = set(), [], []
        self.buzzer_offset, self.buzzer_observations = 0, []
        self.web_ui = AnnotationTransport(url, output)

    def serial_now(self, sid):
        return self.json(f'sessions/{sid}/serial?limit=262144', via_ui=False)['data']

    def record_guest(self, phase, values, serial, offset):
        fresh = serial[offset:]
        assert fresh, 'fresh guest evidence is empty'
        self.guest_vectors.append({'phase': phase, 'vector': values, 'serial_offset': offset,
            'guest_observed': True, 'fresh_serial_sha256': digest(fresh.encode()),
            'guest_marker_lines': [line for line in fresh.splitlines() if line.startswith(('SENSOR_', 'IO_', 'UNIT_ENV'))]})

    def annotation(self, sid, phase, expected):
        assert phase not in self.observed_phases, 'duplicate annotation phase'
        mode = 'state' if self.case == 'buzzer' and phase != 'buzzer-off' else 'full'
        self.web_ui.call('annotation', session_id=sid, phase=phase, expected=expected, evidence_mode=mode)
        self.observed_phases.add(phase)

    def thermal_observation(self, sid, phase, fixture, offset):
        serial = sensors.wait_for(self, sid, lambda text: sensors.thermal_reading(text, fixture['expected']) is not None, offset=offset)
        reading = sensors.thermal_reading(serial[offset:], fixture['expected'])
        assert reading is not None
        self.record_guest(phase, {'fixture': phase, 'expected': fixture['expected']}, serial, offset)
        self.guest_vectors[-1]['thermal_reading'] = reading
        properties = self.json(f'sessions/{sid}/units', via_ui=False)['units'][0]['properties']
        assert properties['raw-fixture-ready'] is True and type(properties['control-word']) is int
        self.annotation(sid, phase, {key: properties[key] for key in ('control-word', 'raw-fixture-ready')})

    def observe_buzzer(self, sid, data):
        properties = json.loads(data)['units'][0]['properties']
        serial = self.serial_now(sid)
        wanted = required_phases('buzzer')
        if len(self.buzzer_observations) >= len(wanted):
            return
        phase = wanted[len(self.buzzer_observations)]
        observation = buzzer_observation(phase, properties, serial, self.buzzer_offset)
        if observation is not None:
            expected = {key: properties[key] for key in ('frequency-hz', 'duty-pct')}
            self.annotation(sid, phase, expected)
            self.buzzer_offset = observation['marker_end']
            self.buzzer_observations.append({**observation, 'phase': phase, 'actual_qom': expected,
                'serial_sha256': digest(serial.encode())})

    def raw(self, path, method='GET', **kwargs):
        parts = path.split('?')[0].split('/')
        unit_get = method == 'GET' and len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'units'
        unit_post = method == 'POST' and len(parts) == 3 and parts[0] == 'sessions' and parts[2] == 'unit-input'
        observe_input = unit_post and self.case in (*SENSOR_CASES, 'pir', 'light', 'thermal')
        if observe_input:
            sid = parts[1]
            if self.case == 'thermal' and 'thermal-reference' not in self.observed_phases:
                self.thermal_observation(sid, 'thermal-reference', json.loads((sensors.THERMAL / 'fixture.json').read_text()), 0)
            offset = len(self.serial_now(sid))
        if unit_get and kwargs.get('via_ui', True) and self.case == 'env-iii' and not self.env_checked:
            self.env_checked = True
            sid = parts[1]
            self._open_web_ui(sid)
            serial = self.json(f'sessions/{sid}/serial?limit=262144', via_ui=False)['data']
            assert env_rows(serial, FIRST), 'original runner must observe first guest vector before the second input'
            self.record_guest('env-vector-1', FIRST, serial, 0)
            self.annotation(sid, 'env-vector-1', FIRST)
            offset = len(self.serial_now(sid))
            self.json(f'sessions/{sid}/unit-input', method='POST', payload={'id': 'external1', 'values': SECOND})
            serial = wait_for(self, sid, lambda text: bool(env_rows(text[offset:], SECOND)))
            self.record_guest('env-vector-2', SECOND, serial, offset)
            self.annotation(sid, 'env-vector-2', SECOND)
        if method == 'DELETE' and len(parts) == 2 and parts[0] == 'sessions':
            # Let the real API stop first, retain the same page for terminal UI.
            transport, self.web_ui = self.web_ui, None
            try:
                data = super().raw(path, method=method, **kwargs)
            finally:
                self.web_ui = transport
            try:
                transport.call('terminal', session_id=parts[1])
            except Exception as error:
                self.annotation_errors.append('terminal: ' + str(error))
            finally:
                try:
                    transport.call('close', session_id=parts[1])
                except Exception as error:
                    self.annotation_errors.append('browser close: ' + str(error))
            return data
        if method == 'GET' and len(parts) == 3 and parts[2] == 'evidence' and self.web_ui.dead:
            transport, self.web_ui = self.web_ui, None
            try:
                return super().raw(path, method=method, **kwargs)
            finally:
                self.web_ui = transport
        request_options = dict(kwargs)
        if unit_get and self.case == 'buzzer' and kwargs.get('via_ui', True):
            # The phase observer below validates the real product's next GET.
            # Avoid an additional general-purpose capture in a two-second tone.
            self._open_web_ui(parts[1])
            request_options['via_ui'] = False
        data = super().raw(path, method=method, **request_options)
        if method == 'POST' and path == 'sessions':
            self.owned_session_ids.append(json.loads(data)['session_id'])
        if observe_input:
            if self.case == 'thermal':
                self.thermal_observation(sid, 'thermal-variant', json.loads((sensors.THERMAL / 'synthetic-plus16.json').read_text()), offset)
            else:
                values = kwargs['payload']['values']
                serial = sensors.wait_for(self, sid, lambda text: guest_marker_matches(self.case, values, text), offset=offset)
                phase = f'input-{len(self.guest_vectors) + 1}'
                self.record_guest(phase, values, serial, offset)
                self.annotation(sid, phase, values)
        if unit_get and kwargs.get('via_ui', True) and self.case == 'relay':
            value = json.loads(data)['units'][0]['properties']['output-level']
            assert type(value) is bool
            if value not in self.relay_values:
                self.annotation(parts[1], f'relay-{int(value)}', {'output-level': value})
                self.relay_values.add(value)
        if unit_get and kwargs.get('via_ui', True) and self.case == 'buzzer':
            self.observe_buzzer(parts[1], data)
        if (method == 'GET' and len(parts) == 3 and parts[2] == 'serial' and kwargs.get('via_ui', True)
                and self.case == 'buzzer' and len(self.buzzer_observations) == 4):
            # Observe the timer's zero during the original serial wait. Waiting
            # until TIMER_DONE would already race the following manual write.
            snapshot = self.raw(f'sessions/{parts[1]}/units', via_ui=False)
            self.observe_buzzer(parts[1], snapshot)
        return data


def run_controller(client, directory, device, case, *, buzzer_callback_arity_patch=False):
    args = argparse.Namespace(out_dir=directory / 'controller', device=device, base=None,
        control_no_unit=False, prepare_only=False, ir_callback_root_patch=False,
        build_only=False, thermal_no_fixture=False,
        buzzer_callback_arity_patch=buzzer_callback_arity_patch)
    if case in SENSOR_CASES or case == 'thermal':
        return sensors.run_case(client, args, case)
    if case in {'pir', 'light', 'buzzer'}:
        return io_cases.run_case(client, args, case)
    return run_case(client, args, case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-url', default='http://127.0.0.1:8787')
    parser.add_argument('--device', choices=['cores3'], default='cores3')
    parser.add_argument('--case', choices=(*CASES, 'all'), action='append')
    parser.add_argument('--out-dir', type=Path)
    parser.add_argument('--expected-runtime-sha256')
    parser.add_argument('--execute', action='store_true', help='Create sequential visible sessions for the explicit selection')
    parser.add_argument('--buzzer-callback-arity-patch', action='store_true',
                        help='Explicit custom Buzzer guest; requires --case buzzer only and never upgrades the original firmware')
    args = parser.parse_args()
    selected = CASES if args.case and 'all' in args.case else tuple(dict.fromkeys(args.case or ('env-iii', 'relay')))
    if args.buzzer_callback_arity_patch and selected != ('buzzer',):
        parser.error('--buzzer-callback-arity-patch requires --case buzzer only')
    if not args.execute:
        print(json.dumps({'status': 'PREPARED_NOT_EXECUTED', 'sessions_started': 0, 'api_contacted': False,
                          'cases': list(selected), 'required_phases': {case: required_phases(case) for case in selected},
                          'buzzer_callback_arity_patch': args.buzzer_callback_arity_patch,
                          'scope': 'Existing scalar rails; thermal is control/model status and heart is raw samples.',
                          'pending_product_file': not (ROOT / 'platform/web/unit-annotations.js').exists()}, ensure_ascii=False))
        return 0
    if not args.out_dir or not re.fullmatch('[a-f0-9]{64}', args.expected_runtime_sha256 or ''):
        parser.error('--execute requires a new --out-dir and exact --expected-runtime-sha256')
    if urlparse(args.api_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
        parser.error('direct PID proof requires a local Device Service')
    if os.environ.get('M5_UNIT_WEB_BRIDGE') == '1':
        parser.error('unset M5_UNIT_WEB_BRIDGE; this adapter owns the bridge')
    os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256'] = args.expected_runtime_sha256
    output = args.out_dir.resolve()
    assert output.is_relative_to(ROOT / '.work'), 'raw evidence belongs in a fresh private .work directory'
    output.mkdir(parents=True, exist_ok=False)
    import littlefs
    _, toolchain = freeze_toolchain(littlefs)
    write_json(output / 'toolchain-before.json', toolchain)
    frozen = {}
    for path in source_paths():
        name, data = path.relative_to(ROOT).as_posix(), path.read_bytes()
        frozen[name] = digest(data)
        target = output / 'tool-sources' / (name + '.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_json(output / 'source-freeze.json', frozen)
    plain = Client(args.api_url)
    assert plain.json('health')['capacity']['active_sessions'] == 0, 'coordinate an idle 8787 before executing'
    reports = []
    for case in selected:
        directory = output / case
        directory.mkdir()
        client = AnnotationClient(args.api_url, case, directory / 'browser')
        result = {'status': 'FAIL', 'checks': {}}
        try:
            result = run_controller(client, directory, args.device, case,
                buzzer_callback_arity_patch=args.buzzer_callback_arity_patch)
        except Exception as error:
            result['error'] = str(error)
        finally:
            for owned in client.owned_session_ids:
                try:
                    if plain.json(f'sessions/{owned}')['state'] not in {'stopped', 'failed'}:
                        try:
                            (directory / 'emergency-evidence.zip').write_bytes(plain.raw(f'sessions/{owned}/evidence'))
                        finally:
                            plain.json(f'sessions/{owned}?purge=0', method='DELETE')
                        client.annotation_errors.append('owned session required emergency stop')
                except Exception as error:
                    client.annotation_errors.append('owned session cleanup: ' + str(error))
            try:
                client.web_ui.close()
            except Exception as error:
                client.annotation_errors.append('transport close: ' + str(error))
        sid = result.get('session_id')
        web_path = directory / 'browser' / str(sid) / 'web-report.json'
        web = json.loads(web_path.read_text()) if web_path.exists() else {}
        proof_path = web_path.with_name('runtime-provenance.json')
        proof = json.loads(proof_path.read_text()) if proof_path.exists() else {}
        checks = {'original_guest_runner': result['status'] == 'PASS',
                  'same_session_firmware': web.get('session_id') == sid and web.get('firmware_sha256') == result.get('firmware_sha256'),
                  'direct_runtime': proof.get('status') == 'VERIFIED' and proof.get('runtime_binary_sha256') == args.expected_runtime_sha256,
                  'no_browser_errors': not web.get('errors') and not web.get('annotation_asset_errors')
                    and not web_path.with_name('bridge-errors.json').exists() and not client.annotation_errors}
        checks.update(annotation_checks(case, web, client.guest_vectors))
        try:
            assert {path.relative_to(ROOT).as_posix() for path in source_paths()} == set(frozen)
            assert all(digest((ROOT / name).read_bytes()) == pin for name, pin in frozen.items())
            assert freeze_toolchain(littlefs)[1] == toolchain
            checks['frozen_sources_inventory_and_toolchain_unchanged'] = True
        except Exception as error:
            checks['frozen_sources_inventory_and_toolchain_unchanged'] = False
            client.annotation_errors.append('source/toolchain drift: ' + str(error))
        served = {row['file']: row['sha256'] for row in web.get('annotation_served_assets', [])}
        checks['annotation_assets_match_frozen_sources'] = all(served.get(name) == frozen[name] for name in
            ('platform/web/unit-annotations.js', 'platform/web/unit-panel.js', 'platform/web/unit-panel.css', 'platform/web/model-shell.js', 'platform/web/unit-assembly-layout.js'))
        if case == 'env-iii':
            wanted = [(field, value) for vector in (FIRST, SECOND) for field, value in vector.items()]
            actual = [(field, value) for post in web.get('posts', []) for field, value in post.get('request', {}).get('values', {}).items()]
            checks['two_guest_vectors'] = len(client.guest_vectors) == 2 and all(row['guest_observed'] for row in client.guest_vectors)
            checks['exact_six_product_input_posts'] = len(web.get('posts', [])) == 6 and actual == wanted
        elif case == 'relay':
            checks['both_guest_output_annotations'] = client.relay_values == {True, False}
            checks['no_relay_input_posts'] = web.get('posts') == []
            serial_path = directory / 'controller' / case / 'serial.txt'
            serial = serial_path.read_text(encoding='utf-8') if serial_path.exists() else ''
            checks['both_guest_output_markers'] = all(f'UNIT_RELAY {value}' in serial for value in (0, 1))
        mutations = web.get('annotation_mutation_requests', [])
        checks['no_unaccounted_browser_mutations'] = len(mutations) == len(expected_posts(case)) and all(
            row.get('method') == 'POST' and row.get('path') == f'/api/v1/sessions/{sid}/unit-input' for row in mutations)
        report = {'schema_version': 1, 'category': 'virtual-device-browser-unit-annotations', 'status': 'FAIL',
                  'device_id': args.device, 'unit_id': case, 'runtime': 'qemu', 'session_id': sid,
                  'firmware_sha256': result.get('firmware_sha256'), 'evidence_sha256': result.get('evidence_sha256'),
                  'firmware_flavor': result.get('firmware_flavor'),
                  'hardware_execution': 'NOT RUN', 'checks': checks, 'runtime_provenance': proof,
                  'guest_vectors': client.guest_vectors, 'source_sha256': frozen,
                  'annotation_errors': client.annotation_errors, 'controller_error': result.get('error'),
                  'buzzer_observations': client.buzzer_observations,
                  'scope': 'Scalar rail matches actual HTTP/QOM/DOM; transformed guest readings are checked separately. No atomic LCD/DOM or hardware claim.',
                  'controller_result': f'controller/{case}/result.json', 'browser_report': str(web_path.relative_to(directory)),
                  'evidence': f'controller/{case}/evidence.zip'}
        checker = Checker(directory)
        manifest = None
        try:
            manifest, count = checker.zip_manifest(directory / 'controller' / case / 'evidence.zip', report, case)
            report['zip_member_count'] = count
            report['zip_running_session'] = manifest['session']
            checks['strict_zip_before_stop'] = True
        except Exception as error:
            report['zip_check_error'] = str(error)
            checks['strict_zip_before_stop'] = False
        try:
            assert manifest is not None, 'no valid running-session ZIP for direct runtime proof'
            report['strict_runtime_proof'] = checker.direct_record(proof, manifest['session'], case, args.expected_runtime_sha256)
            checks['direct_runtime_matches_zip'] = True
        except Exception as error:
            report['runtime_check_error'] = str(error)
            checks['direct_runtime_matches_zip'] = False
        checks['history_retained'] = result.get('checks', {}).get('stopped_with_history') is True
        try:
            raw = plain.raw(f'sessions/{sid}')
            (directory / 'history.json').write_bytes(raw)
            history = json.loads(raw)
            assert history['state'] == 'stopped' and history['firmware_sha256'] == result['firmware_sha256']
            assert history['flash_retained'] is False
            (directory / 'history-frame.png').write_bytes(plain.raw(f'sessions/{sid}/frame.png'))
            raw = plain.raw('health')
            (directory / 'history-health.json').write_bytes(raw)
            checks['service_idle_after_case'] = json.loads(raw)['capacity']['active_sessions'] == 0
            checks['actual_stopped_history_and_flash_release'] = True
        except Exception as error:
            checks['service_idle_after_case'] = False
            checks['actual_stopped_history_and_flash_release'] = False
            report['health_error'] = str(error)
        report['artifact_sha256'] = {str(path.relative_to(directory)): digest(path.read_bytes())
                                    for path in sorted(directory.rglob('*')) if path.is_file()
                                    and path.suffix not in {'.bin'} and 'files' not in path.parts}
        try:
            report_path = directory / 'report.json'
            verified = checker.artifacts(report, {}, report_path)
            report['strict_controller_detail'] = checker.controller_detail(report, report_path, verified)
            assert manifest is not None, 'no valid running-session ZIP for browser detail'
            report['strict_browser_detail'] = checker.browser_detail(report, report_path, verified, manifest)
            checks['strict_guest_browser_artifacts'] = True
        except Exception as error:
            checks['strict_guest_browser_artifacts'] = False
            report['artifact_check_error'] = str(error)
        report['status'] = 'PASS' if all(checks.values()) else 'FAIL'
        write_json(directory / 'report.json', report)
        reports.append(report)
        write_json(output / 'summary.json', reports)
        print(f"ANNOTATION {case}: {report['status']}", flush=True)
        if report['status'] != 'PASS':
            break
    return 0 if len(reports) == len(selected) and all(row['status'] == 'PASS' for row in reports) else 1


if __name__ == '__main__':
    raise SystemExit(main())
