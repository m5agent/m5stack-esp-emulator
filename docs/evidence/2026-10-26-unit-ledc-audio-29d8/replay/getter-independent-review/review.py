#!/usr/bin/env python3
"""Independent review of existing getter A/B artifacts; no API or guest calls."""
from pathlib import Path, PurePosixPath
from collections import Counter
from datetime import datetime, timezone
import difflib
import hashlib
import io
import json
import re
import zipfile
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
INPUT = ROOT / '.work/unit-ledc-mmio-diagnostic-20261026-r1'
FW = '3ce76c8033131c6e0773406475c4b7342ae5f46d1e22240d690e6e61f9bba251'
RUNTIMES = ['a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047',
            '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d']
RUNS = ['baseline-r1', 'readback-mmio-r1']
ANALYSES = ['baseline-analysis-r2.json', 'readback-mmio-analysis-r1.json']
REQUESTED = [0, 16384, 32768, 49152, 65535, 0]
COUNTS = [0, 2048, 4096, 6144, 8192, 0]
PCTS = [0, 25, 50, 75, 100, 0]
PATTERNS = {
 'sample': r'(?m)^LEDC_DIAG_SAMPLE (\d+) (\d+) (\d+) (\d+) (\d+) (.+)\r?$',
 'global': r'(?m)^LEDC_DIAG_GLOBAL (\d+) (\d+) (\d+)\r?$',
 'timer': r'(?m)^LEDC_DIAG_TIMER (\d+) (\d+) (\d+) (\d+)\r?$',
 'raw': r'(?m)^LEDC_DIAG_RAW (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)\r?$',
 'phase': r'(?m)^LEDC_DIAG_PHASE (\d+) (\w+) (\d+)\r?$',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


inputs = []


def frozen(path, label):
    raw = path.read_bytes()
    dst = OUT / 'inputs' / label
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(raw)
    inputs.append({'path': str(path.relative_to(ROOT)), 'snapshot': str(dst.relative_to(OUT)),
                   'bytes': len(raw), 'sha256': sha(raw)})
    return raw


freeze = {name: (OUT.parent / name).read_bytes() for name in ['receipt.json', 'SHA256SUMS', 'final-verification.json']}
result = {'schema_version': 1, 'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(),
          'scope': 'Read-only review of collected virtual-device evidence; no API/session/guest/QEMU execution.',
          'firmware_sha256': FW, 'runs': []}
reports, unit_runtime_bytes, source_records = [], [], []
try:
 for lane, (run, analysis_name, runtime) in enumerate(zip(RUNS, ANALYSES, RUNTIMES)):
    p = INPUT / run
    report_raw = frozen(p / 'report.json', run + '/report.json')
    report = json.loads(report_raw)
    analysis = json.loads(frozen(INPUT / analysis_name, analysis_name))
    assert report['status'] == 'OBSERVATIONS_COLLECTED' and report['firmware_sha256'] == FW
    assert report['device_id'] == 'cores3' and report['unit_id'] == 'buzzer' and report['runtime'] == 'qemu'
    assert report['firmware_flavor'] == 'custom-guest-ledc-mmio-diagnostic-v1'
    assert report['expected_runtime_sha256'] == runtime
    assert analysis['input_report_sha256'] == sha(report_raw) and analysis['firmware_sha256'] == FW
    assert analysis['runtime_provenance'] == report['runtime_provenance']
    assert sha((p / 'uiflow2-ui-test.bin').read_bytes()) == FW
    for name, expected in report['artifact_sha256'].items():
        relative = PurePosixPath(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        path = p / name
        assert path.resolve().is_relative_to(p.resolve()) and not path.is_symlink()
        assert sha(path.read_bytes()) == expected, (run, name)
    source_record = json.loads((p / 'source-before.json').read_bytes())
    assert source_record == report['source_sha256']
    for name, expected in source_record.items():
        assert sha((p / 'source-snapshot' / (name + '.txt')).read_bytes()) == expected
    proof_path = next(name for name in report['artifact_sha256'] if name.endswith('/runtime-provenance.json'))
    proof = json.loads(frozen(p / proof_path, run + '/runtime-provenance.json'))
    assert proof == report['runtime_provenance']
    assert proof['kind'] == 'direct-pid' and proof['status'] == 'VERIFIED'
    assert proof['session_id'] == report['session_id'] and proof['firmware_sha256'] == FW
    assert proof['runtime_binary_sha256'] == runtime and type(proof['observed_pid']) is int and proof['observed_pid'] > 0
    with zipfile.ZipFile(p / 'evidence.zip') as z:
        entries = z.infolist(); names = [entry.filename for entry in entries]
        assert len(names) == len(set(names)) and z.testzip() is None
        manifest = json.loads(z.read('manifest.json'))
        assert set(manifest['files']) == set(names) - {'manifest.json'}
        for name, expected in manifest['files'].items():
            content = z.read(name)
            assert len(content) == expected['size'] and sha(content) == expected['sha256']
        session, worker = manifest['session'], manifest['session']['worker']
        assert session['state'] == 'running' and session['pid'] == proof['observed_pid']
        assert all(session[k] == report[k] for k in ['session_id', 'device_id', 'runtime', 'firmware_sha256'])
        assert worker['worker_id'] == proof['worker_id'] and type(worker['generation']) is int
        assert worker['generation'] == proof['worker_generation'] == 9 + lane and worker['lease_active'] is True
        assert z.read('serial.log') == (p / 'serial.txt').read_bytes()
        unit_runtime = z.read('units/runtime.json')
        cfg = json.loads(unit_runtime)
        assert cfg == {'schema_version': 1, 'attachments': [{'id': 'external1', 'unit_id': 'buzzer',
            'port_id': 'port-a', 'pins': {'yellow': 2, 'white': 1}, 'visual_port': 'grove', 'initial': {}}]}
        frames = {'running_zip': z.read('frames/current.png'), 'external': (p / 'frame.png').read_bytes(),
                  'history': (p / 'history-frame.png').read_bytes()}
        for name, raw in frames.items():
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                assert image.format == 'PNG' and image.size == (320, 240)
                assert any(a != b for a, b in image.convert('RGB').getextrema())
        zip_summary = {'members': len(names), 'sha256': sha((p / 'evidence.zip').read_bytes()),
                       'runtime_config_sha256': sha(unit_runtime),
                       'frames': {k: sha(v) for k, v in frames.items()}}
    history = json.loads((p / 'history.json').read_bytes())
    assert history['state'] == 'stopped' and history['flash_retained'] is False
    assert all(history[k] == report[k] for k in ['session_id', 'device_id', 'runtime', 'firmware_sha256'])
    serial = (p / 'serial.txt').read_bytes().decode()
    assert 'LEDC_DIAG_DONE' in serial and not any(x in serial for x in ['LEDC_DIAG_FAIL', 'Traceback (most recent call last)', 'Guru Meditation'])
    tables = {k: [m.groups() for m in re.finditer(pattern, serial)] for k, pattern in PATTERNS.items()}
    grids = {'sample': {(a, b) for a in range(6) for b in range(10)},
             'global': {(a, b) for a in range(6) for b in range(10)},
             'timer': {(a, b, c) for a in range(6) for b in range(10) for c in range(4)},
             'raw': {(a, b, c) for a in range(6) for b in range(10) for c in range(8)}}
    for kind, grid in grids.items():
        width = 3 if kind in ['timer', 'raw'] else 2
        keys = [tuple(map(int, row[:width])) for row in tables[kind]]
        assert len(keys) == len(set(keys)) and set(keys) == grid
    assert len(tables['phase']) == 6 and [(int(x[0]), int(x[2])) for x in tables['phase']] == list(enumerate(REQUESTED))
    raw_table = {tuple(map(int, row[:3])): list(map(int, row[3:])) for row in tables['raw']}
    timer_table = {tuple(map(int, row[:3])): int(row[3]) for row in tables['timer']}
    global_table = {tuple(map(int, row[:2])): int(row[2]) for row in tables['global']}
    phase_rows = []
    for phase in range(6):
        phase_samples = [row for row in tables['sample'] if int(row[0]) == phase]
        for sample_row in phase_samples:
            _, sample, requested, getter, route, description = sample_row
            sample, requested, getter, route = map(int, [sample, requested, getter, route])
            assert requested == REQUESTED[phase] and route == 73 and global_table[phase, sample] == 1
            conf0, hpoint, duty, conf1, duty_r = raw_table[phase, sample, 0]
            assert conf0 & 3 == 0 and conf0 & 4 and timer_table[phase, sample, 0] & 15 == 13
            tc = timer_table[phase, sample, 0]
            assert not tc & ((1 << 22) | (1 << 23))
            assert 80000000 * 256 / ((tc >> 4) & 0x3ffff) / (1 << 13) == 2000
            assert all(raw_table[phase, sample, c][2] == raw_table[phase, sample, c][4] == 0 for c in range(1, 8))
            expected_count = COUNTS[phase] if lane else 0
            assert duty == duty_r == expected_count << 4
            assert getter == (min(65535, expected_count << 3) if lane else 0)
        phase_rows.append({'phase': phase, 'requested': REQUESTED[phase], 'samples': len(phase_samples),
                           'duty_raw': (COUNTS[phase] << 4) if lane else 0,
                           'duty_count': COUNTS[phase] if lane else 0,
                           'getter': REQUESTED[phase] if lane else 0, 'resolution': 13})
    observations = json.loads((p / 'observations.json').read_bytes())
    stable, excluded, phase_transitions = [], [], []
    for index, observation in enumerate(observations):
        prefixes, last = [], []
        for side in ['before', 'after']:
            length = observation['serial_' + side + '_length']
            assert type(length) is int and 0 <= length <= len(serial)
            prefix = serial[:length]
            assert sha(prefix.encode()) == observation['serial_' + side + '_sha256']
            prefixes.append(prefix)
            matches = list(re.finditer(PATTERNS['sample'], prefix))
            last.append(matches[-1].groups()[:2] if matches else None)
            phases = list(re.finditer(PATTERNS['phase'], prefix))
            assert (list(phases[-1].groups()) if phases else None) == observation['phase_' + side]
        assert prefixes[1].startswith(prefixes[0]) and observation['serial_prefix_preserved'] is True
        body_raw = (p / observation['body']).read_bytes()
        assert sha(body_raw) == observation['body_sha256']
        body = json.loads(body_raw)
        assert body['session_id'] == report['session_id'] and body['state'] == 'running' and body['source'] == 'live'
        assert len(body['units']) == 1
        unit = body['units'][0]
        assert unit['id'] == 'external1' and unit['unit_id'] == 'buzzer' and unit['source'] == 'guest-qom' and unit['available'] is True and not unit['errors']
        duty, frequency = unit['properties']['duty-pct'], unit['properties']['frequency-hz']
        reason = None
        if last[0] != last[1] or not last[0]: reason = 'sample-boundary-or-no-sample'
        elif not 1 <= int(last[0][1]) <= 8: reason = 'edge-sample-0-or-9'
        elif observation['phase_before'] != observation['phase_after'] or not observation['phase_before'] or int(observation['phase_before'][0]) != int(last[0][0]): reason = 'phase-boundary'
        if reason:
            excluded.append(index)
        else:
            phase, sample = map(int, last[0])
            assert abs(duty - PCTS[phase]) <= .1 and frequency == 2000
            stable.append({'index': index, 'phase': phase, 'sample': sample, 'duty_pct': duty,
                           'frequency_hz': frequency, 'body_sha256': observation['body_sha256']})
        if observation['phase_before'] == observation['phase_after'] and observation['phase_before']:
            phase = int(observation['phase_before'][0])
            if abs(duty - PCTS[phase]) > .1:
                assert index in excluded
                phase_transitions.append({'index': index, 'phase_marker': phase, 'actual_duty_pct': duty})
    assert len(observations) == 97 and len(stable) == [76, 75][lane] and len(phase_transitions) == 4
    assert {row['phase'] for row in stable} == set(range(6))
    assert stable == analysis['strict_stable_observations']
    assert excluded == [row['index'] for row in analysis['excluded_observations']]
    assert analysis['settled_readback_matches_resolution'] is bool(lane)
    result['runs'].append({'label': run, 'runtime_sha256': runtime, 'worker_generation': proof['worker_generation'],
        'direct_pid_proof_sha256': sha((p / proof_path).read_bytes()), 'report_sha256': sha(report_raw),
        'analysis_sha256': sha((INPUT / analysis_name).read_bytes()), 'artifact_hashes_verified': len(report['artifact_sha256']),
        'zip': zip_summary, 'samples': 60, 'raw_channel_records': 480, 'globals': 60, 'timer_records': 240,
        'unique_complete_grids': True, 'stable_qom': len(stable), 'excluded_qom': len(excluded),
        'phase_only_transition_rows_excluded': phase_transitions, 'phase_results': phase_rows,
        'resolution': 13, 'gpio2_route': 73, 'global_clock_selector': 1, 'history_stopped_flash_released': True})
    reports.append(report); unit_runtime_bytes.append(unit_runtime); source_records.append(source_record)
 assert reports[0]['packaged_python_sha256'] == reports[1]['packaged_python_sha256']
 assert (INPUT / RUNS[0] / 'uiflow2-ui-test.bin').read_bytes() == (INPUT / RUNS[1] / 'uiflow2-ui-test.bin').read_bytes()
 assert unit_runtime_bytes[0] == unit_runtime_bytes[1]
 a = INPUT / RUNS[0] / 'source-snapshot/.work/unit-ledc-mmio-diagnostic-20261026-r1/run.py.txt'
 b = INPUT / RUNS[1] / 'source-snapshot/.work/unit-ledc-mmio-diagnostic-20261026-r1/run_readback_mmio.py.txt'
 old_runner, new_runner = a.read_text(), b.read_text()
 assert old_runner.replace('unit-runtime-source-core2-compat/qemu/hw/misc/esp32_ledc.c', 'unit-runtime-source-ledc-readback/qemu/hw/misc/esp32_ledc.c') == new_runner
 (OUT / 'runner-source-path-only.diff').write_text(''.join(difflib.unified_diff(old_runner.splitlines(True), new_runner.splitlines(True))))
 frozen(a, 'baseline-runner.py'); frozen(b, 'readback-runner.py'); frozen(INPUT / 'analyze.py', 'analyze.py')
 old_receipt = json.loads(freeze['receipt.json'])
 assert old_receipt['status'] == 'PASS' and old_receipt['cold_build_binary_sha256'] == RUNTIMES[1]
 build_manifest = json.loads((OUT.parent / 'inputs/build-manifest.json').read_bytes())
 new_source = INPUT / RUNS[1] / 'source-snapshot/.work/unit-runtime-source-ledc-readback/qemu/hw/misc/esp32_ledc.c.txt'
 assert sha(new_source.read_bytes()) == build_manifest['files']['hw/misc/esp32_ledc.c']
 assert sha((OUT.parent / 'forward-source/hw/misc/esp32_ledc.c').read_bytes()) == sha(new_source.read_bytes())
 assert all((OUT.parent / name).read_bytes() == raw for name, raw in freeze.items())
 result.update(status='PASS', finished_at=datetime.now(timezone.utc).isoformat(), findings=[],
    identical_firmware_bytes=True, identical_packaged_guest_hashes=True, identical_controller_attachment_bytes=True,
    runner_change_only_compiled_source_snapshot_path=True, existing_freeze_receipts_unchanged=True,
    cold_build_source_replay_receipt_sha256=sha(freeze['receipt.json']),
    source_attribution='New runtime SHA matches the separately frozen cold build and 106-file replay receipt. Runtime execution proof is direct-PID/worker identity, not an assumption from a source path.',
    allowed_conclusion='Same custom diagnostic firmware on the new runtime reads the existing settled set+update duty correctly; old runtime readback is zero despite nonzero QOM output.',
    boundaries=['Not the original Buzzer.once functional path.', 'Pending/current-cycle distinctions, active-latch/fade/HPOINT timing remain untested model gaps.', 'No physical PWM, acoustic or electrical claim.', 'No exact private dirty-SDK source attribution.', 'Stable serial brackets do not make independent frame captures atomic.'])
except BaseException as error:
 result.update(status='FAIL', error=type(error).__name__ + ': ' + str(error))
 dump('review.json', result)
 dump('input-manifest.json', inputs)
 raise
else:
 dump('review.json', result)
 dump('input-manifest.json', inputs)
 print(json.dumps({'status': result['status'], 'identical_firmware_bytes': True,
       'runs': [{k: row[k] for k in ['label', 'artifact_hashes_verified', 'samples', 'raw_channel_records', 'stable_qom', 'excluded_qom']} for row in result['runs']]}, indent=2))
