"""Independent raw-byte evidence audit; reads only, never contacts an API."""
from pathlib import Path
import base64
import hashlib
import io
import json
import re
import socket
import types
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
RUNTIME = '7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e'
DRIVER_SHA = '10546386ee156034c268404e96f4d086b88c52254da1fcd2aa19130ce2f6629f'


def deny(*args, **kwargs):
    raise AssertionError('independent audit must not contact network')


socket.create_connection = deny
socket.socket.connect = deny


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


controller = json.loads((HERE / 'controller-report.json').read_text())
intended = [(host, mode) for host in ('atoms3r', 'sticks3', 'stopwatch') for mode in ('flash', 'torch')]
aggregate = {'category': 'INDEPENDENT_RAW_EVIDENCE_AUDIT', 'network': 'DENIED',
             'expected_runtime_sha256': RUNTIME, 'worker_generation': 42,
             'hardware': 'NOT RUN', 'live_browser': 'NOT RUN',
             'full_sixteen_code_admission': False, 'lanes': [], 'files': []}
nonces, session_ids = set(), set()
dependency_hash_sets = {}
for host, mode in intended:
    folder = HERE / (host + '-' + mode)
    if not (folder / 'report.json').exists():
        aggregate['lanes'].append({'device_id': host, 'mode': mode, 'status': 'NOT RUN',
                                   'reason': 'not completed in this fresh gen42 cohort; see controller report'})
        continue
    original_report = (folder / 'report.json').read_bytes()
    report = json.loads(original_report)
    source = (folder / 'runner-source.py.txt').read_bytes()
    receipt = json.loads((folder / 'runner-source-receipt.json').read_text())
    assert receipt['source_sha256'] == sha(source) == controller['runner_sha256']
    assert receipt['captured_before_api'] is True
    for name, fingerprint in receipt['dependency_sha256'].items():
        dependency_hash_sets.setdefault(name, set()).add(fingerprint)
    module = types.ModuleType('archived_flashlight_runner')
    module.__file__ = str(ROOT / '.work/flashlight-live-probe-20261027/probe.py')
    exec(compile(source, module.__file__, 'exec'), module.__dict__)
    assert report['runtime']['sha256'] == RUNTIME
    assert report['runtime']['pid'] == report['pid']
    assert report['worker']['generation'] == 42 and report['worker']['lease_active'] is True
    assert report['nonce'] not in nonces and report['session_id'] not in session_ids
    assert re.fullmatch('[0-9a-f]{32}', report['nonce'])
    nonces.add(report['nonce']); session_ids.add(report['session_id'])
    assert report['flash_mode'] is (mode == 'flash')
    assert report['hardware'] == report['live_browser'] == 'NOT RUN'
    cleanup = report['cleanup']; stopped = cleanup['session']
    assert cleanup['status'] == 'PASS' and cleanup['pid_gone'] is True and cleanup['zip_before_stop'] is True
    assert stopped['state'] == 'stopped' and stopped['flash_retained'] is False
    assert stopped['worker']['lease_active'] is False and stopped['worker']['generation'] == 42
    assert stopped['session_id'] == report['session_id'] and stopped['firmware_sha256'] == report['firmware_sha256']
    assert sha((folder / 'history-last.png').read_bytes()) == cleanup['history_frame_sha256'] == report['last_frame_sha256']
    http = json.loads((folder / 'http.json').read_text())
    errors = []
    for index, row in enumerate(http):
        if 'status' not in row:
            continue
        raw = (folder / f'http-{index:04d}.response').read_bytes()
        assert sha(raw) == row['sha256'] and len(raw) == row['bytes']
        if row['status'] >= 400:
            body = json.loads(raw)
            errors.append({'index': index, 'method': row['method'], 'path': row['path'],
                           'status': row['status'], 'body': body, 'raw_sha256': sha(raw)})
    rejects = [error for error in errors if error['status'] == 409]
    assert len(rejects) == 2 and all(row['body']['error']['code'] == 'unit_input_creation_only' for row in rejects)
    zip_bytes = (folder / 'evidence-before-stop.zip').read_bytes()
    assert sha(zip_bytes) == report['evidence_zip']['sha256']
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) and archive.testzip() is None
        assert all(not name.startswith('/') and '..' not in name.split('/') for name in names)
        manifest = json.loads(archive.read('manifest.json'))
        assert set(manifest['files']) == set(names) - {'manifest.json'}
        for name, record in manifest['files'].items():
            raw = archive.read(name)
            assert record == {'size': len(raw), 'sha256': sha(raw)}
        session = manifest['session']
        assert session['state'] == 'running' and session['runtime'] == 'qemu'
        for name in ('session_id', 'device_id', 'pid', 'firmware_sha256'):
            assert session[name] == report[name]
        assert session['worker']['generation'] == 42 and session['worker']['lease_active'] is True
        assert sha(archive.read('frames/current.png')) == report['last_frame_sha256']
        assert session['program']['execution_id'] == report['runs'][-1]['execution_id']
        assert session['program']['revision_id'] == report['runs'][-1]['revision_id']
        serial = archive.read('serial.log').decode('utf-8', errors='replace')
        observations = []
        for index, observation in enumerate(report['observations']):
            phase = observation['phase']; run = observation['execution']
            expected_payload = module.package(report['nonce'], phase, report['pins'])
            expected_files = {name: (entry['data'].encode() if entry['encoding'] == 'utf8'
                              else base64.b64decode(entry['data']))
                              for name, entry in expected_payload['files'].items()}
            hashes = {name: sha(data) for name, data in expected_files.items()}
            expected_rid = sha(canonical({'source_kind': 'uiflow2-package', 'entrypoint': 'main.py', 'files': hashes}))
            assert run['revision_id'] == expected_rid
            assert report['runs'][index]['execution_id'] == run['execution_id']
            assert report['runs'][index]['revision_id'] == expected_rid
            for key in ('pid', 'firmware_sha256'):
                assert run[key] == report[key] and report['runs'][index][key] == report[key]
            assert run['state'] == 'completed'
            stored = json.loads(archive.read('programs/' + run['execution_id'] + '.json'))
            assert stored['execution_id'] == run['execution_id'] and stored['revision_id'] == expected_rid
            for name, data in expected_files.items():
                assert archive.read('programs/' + expected_rid + '/files/' + name) == data
            assert hashes['official_flash.py'] == DRIVER_SHA
            marker = '__M5_EXEC_' + run['execution_id'] + '__:START'
            matched = re.search(re.escape(marker) + r'\r?\n', serial)
            assert matched
            end = serial.find('__M5_EXEC_', matched.end())
            window = serial[matched.end():] if end < 0 else serial[matched.end():end]
            rows = []
            for line in window.splitlines(keepends=True):
                if line.startswith(module.PREFIX) and line.endswith('\n'):
                    rows.append(json.loads(line[len(module.PREFIX):]))
            rows = [row for row in rows if row.get('nonce') == report['nonce'] and row.get('phase') == phase]
            assert len(rows) == 1 and rows[0] == observation['guest']
            assert rows[0]['driver_sha256'] == DRIVER_SHA
            unit = observation['unit']; props = unit['properties']; before = observation['before_properties']
            assert unit['id'] == 'lamp' and unit['unit_id'] == 'flashlight' and unit['available'] is True
            assert not unit['errors'] and unit['pins'] == report['pins']
            assert props['flash-mode'] is (mode == 'flash') and props['mode-frozen'] is True
            expected_en = phase not in ('reset', 'restore', 'steady-off')
            assert props['en-level'] is expected_en and rows[0]['en'] == int(expected_en)
            assert props['pad-synchronized'] is True and props['gpio-route-supported'] is True
            frame = (folder / f'{index:02d}-{phase}.png').read_bytes()
            assert sha(frame) == observation['frame_sha256'] == observation['frame_headers']['x-frame-sha256']
            assert observation['frame_headers']['x-frame-execution-id'] == run['execution_id']
            assert observation['frame_headers']['x-frame-revision-id'] == expected_rid
            with module.Image.open(io.BytesIO(frame)) as image:
                assert list(image.convert('RGB').getpixel((image.width // 2, image.height // 2))) == ([255] * 3 if expected_en else [0] * 3)
            with module.Image.open(io.BytesIO(frame)) as image:
                image.verify()
            delta = props['edge-count'] - before['edge-count']
            trace = props['edge-trace-ns']
            assert len(trace) == min(256, props['edge-count'])
            assert props['trace-overflows'] == max(0, props['edge-count'] - 256)
            assert 0 <= delta <= len(trace)
            assert all(type(pair[0]) is int and pair[1] in (0, 1) for pair in trace)
            assert all(trace[i][0] >= trace[i-1][0] and trace[i][1] != trace[i-1][1] for i in range(1, len(trace)))
            remaining = len(trace) - delta
            assert trace[:remaining] == (before['edge-trace-ns'][-remaining:] if remaining else [])
            new_edges = trace[-delta:] if delta else []
            n = {'original-short': 1, 'original-long100': 2, 'original-long60': 10,
                 'original-long30': 16, 'raw9': 9, 'raw16': 16, 'invalid17': 17, 'slow2': 2}.get(phase)
            first_rise = next((i for i, pair in enumerate(new_edges) if pair[1]), None)
            widths = [] if first_rise is None else [new_edges[i][0] - new_edges[i-1][0]
                      for i in range(first_rise + 1, len(new_edges))]
            classification = observation.get('waveform_result')
            if n:
                assert sum(pair[1] for pair in new_edges) == props['rising-edges'] - before['rising-edges'] == n
                assert len(widths) == 2 * n - 2
                if classification == 'QUALIFIED_NOMINAL_DIGITAL_CODE':
                    assert props['output-known'] is True and 1 <= n <= 16
                    assert props['last-program-count'] == n
                    assert props['flash-level-pct'] == 100 - ((n - 1) % 8) * 10
                    assert props['timeout-ms'] == (220 if n <= 8 else 1300)
                    assert props['decoded-programs'] == before['decoded-programs'] + 1
                    assert all(750 <= width <= 10000 for width in widths)
                else:
                    assert classification == 'UNKNOWN_NOT_ADMITTED' and props['output-known'] is False
                    assert props['unqualified-programs'] > before['unqualified-programs']
                    if n <= 16:
                        assert any(not 750 <= width <= 10000 for width in widths)
                if phase == 'original-short':
                    expired = observation['timeout_observation']['properties']
                    assert classification == 'QUALIFIED_NOMINAL_DIGITAL_CODE'
                    assert expired['output-known'] is True and expired['active'] is False and expired['en-level'] is True
                    assert expired['timeout-events'] > before['timeout-events']
                if phase in ('invalid17', 'slow2'):
                    assert props['output-known'] is False and observation['negative_scope'].startswith('unqualified actual waveform')
            if phase in ('reset', 'restore'):
                assert props['output-known'] is True and props['active'] is False
            if mode == 'torch':
                assert props['output-known'] is True and props['active'] is expected_en
                assert props['flash-level-pct'] == props['timeout-ms'] == 0
            observations.append({'phase': phase, 'execution_id': run['execution_id'], 'revision_id': expected_rid,
                                 'actual_rising_edges': sum(pair[1] for pair in new_edges), 'actual_edge_count': delta,
                                 'inter_pulse_widths_ns': widths, 'classification': classification,
                                 'output_known': props['output-known'], 'active_at_snapshot': props['active'],
                                 'decoded_count': props['last-program-count'], 'flash_level_pct': props['flash-level-pct'],
                                 'timeout_ms': props['timeout-ms'], 'unknown_reason': props['unknown-reason']})
    expected_count = 10 if mode == 'flash' else 4
    if report['status'] == 'PASS':
        assert len(observations) == len(report['runs']) == expected_count
        assert report['model_completeness'] == 'partial'
    else:
        assert report.get('error'), 'failed lane needs explicit error evidence'
    aggregate['lanes'].append({'device_id': host, 'mode': mode, 'status': report['status'],
                              'error': report.get('error'), 'cleanup': cleanup['status'],
                              'session_id': report['session_id'], 'nonce': report['nonce'], 'pid': report['pid'],
                              'firmware_sha256': report['firmware_sha256'], 'runtime_sha256': RUNTIME,
                              'runner_sha256': sha(source), 'report_sha256': sha(original_report),
                              'http_original_responses_verified': len(http), 'zip_sha256': sha(zip_bytes),
                              'zip_members_crc_and_hash_verified': len(names),
                              'source_revision_driver_nonce_identity_verified': True,
                              'history_flash_pid_owned_lease_verified': True,
                              'observations': observations, 'http_errors': errors})
    assert (folder / 'report.json').read_bytes() == original_report
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            assert not path.is_symlink()
            aggregate['files'].append({'path': str(path.relative_to(HERE)), 'bytes': path.stat().st_size,
                                       'sha256': sha(path.read_bytes())})
aggregate['status'] = 'SIX_LANES_PASS_SCOPED_PARTIAL_MODEL' if all(row['status'] == 'PASS' for row in aggregate['lanes']) else 'INCOMPLETE_COHORT'
aggregate['captured_dependency_sha256'] = {name: sorted(values) for name, values in dependency_hash_sets.items()}
aggregate['all_captured_dependency_hashes_identical_across_lanes'] = all(len(values) == 1 for values in dependency_hash_sets.values())
old_folder = ROOT / '.work/flashlight-other-hosts-20261027'
old_hashes = json.loads((HERE / 'gen41-preexisting-file-sha256.json').read_text())
assert old_hashes == {str(path.relative_to(old_folder)): sha(path.read_bytes()) for path in old_folder.rglob('*') if path.is_file()}
aggregate['gen41_original_files_unchanged'] = True
aggregate['gen41_original_files_checked'] = len(old_hashes)
aggregate['totals'] = {'pass_lanes': sum(row['status'] == 'PASS' for row in aggregate['lanes']),
                       'failed_lanes': sum(row['status'] == 'FAIL' for row in aggregate['lanes']),
                       'not_run_lanes': sum(row['status'] == 'NOT RUN' for row in aggregate['lanes']),
                       'original_evidence_files': len(aggregate['files'])}
(HERE / 'independent-aggregate.json').write_text(json.dumps(aggregate, indent=2) + '\n')
print(json.dumps({'status': aggregate['status'], 'totals': aggregate['totals'],
                  'all_six_zip_and_raw_http_verification': 'PASS',
                  'full_sixteen_code_admission': False}, indent=2))
