"""Offline checker mutation tests. Fake API only; never guest evidence."""
from pathlib import Path
import base64
import hashlib
import io
import json
import socket
import tempfile
import types
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / '.work/flashlight-live-probe-20261027/probe.py'
SOURCE = Path(__file__).with_name('probe-reviewed.py.txt').read_bytes()


def deny(*args, **kwargs):
    raise AssertionError('network prohibited in offline review')


socket.create_connection = deny
socket.socket.connect = deny
m = types.ModuleType('offline_flashlight_probe')
m.__file__ = str(PROBE)
exec(compile(SOURCE, str(PROBE), 'exec'), m.__dict__)
RESULTS = []


def record(name, action, expected_accept, expected_message=None):
    try:
        action()
        accepted, message = True, None
    except (ValueError, AssertionError, KeyError) as error:
        accepted, message = False, str(error)
    row = {'name': name, 'accepted': accepted, 'expected_accept': expected_accept,
           'status': 'PASS' if accepted is expected_accept else 'UNRESOLVED', 'error': message}
    if expected_message and not accepted:
        row['expected_message_found'] = expected_message in message
        if expected_message not in message:
            row['status'] = 'UNRESOLVED'
    RESULTS.append(row)


class FakePhaseClient:
    def __init__(self, mutation):
        self.mutation = mutation
        self.after = False
        self.lane = None

    def json(self, path, method='GET', body=None, **kwargs):
        if '/serial?' in path:
            if not self.after:
                return {'next_offset': 0, 'data': ''}
            en = 0 if self.mutation in ('wrong-en', 'restore-unknown') else 1
            row = {'phase': ('restore' if self.mutation == 'restore-unknown' else 'raw9'), 'nonce': self.lane.nonce, 'en': en,
                   'driver_sha256': m.DRIVER_SHA, 'driver_file': '/fixture/official_flash.py'}
            if self.mutation == 'wrong-nonce':
                row['nonce'] = '9' * 32
            line = m.PREFIX + json.dumps(row) + '\n'
            start = '__M5_EXEC_' + 'b' * 32 + '__:START'
            if self.mutation == 'missing-start':
                text = line
            elif self.mutation == 'before-true-start':
                text = start + ' is only echoed text\n' + line + start + '\n'
            elif self.mutation == 'incomplete-line':
                text = start + '\n' + line.rstrip('\n')
            else:
                text = start + '\n' + line * (2 if self.mutation == 'duplicate-line' else 1)
            return {'next_offset': len(text), 'data': text}
        if path == 'program-revisions':
            return {'revision': {'revision_id': 'a' * 64}}
        if path.endswith('/program'):
            if method == 'POST':
                self.after = True
                revision = 'e' * 64 if self.mutation == 'receipt-revision' else 'a' * 64
                return {'program': {'execution_id': 'b' * 32, 'revision_id': revision,
                                    'pid': 1234, 'firmware_sha256': 'f' * 64, 'state': 'running'}}
            return {'program': {'execution_id': ('c' if self.mutation == 'cross-execution' else 'b') * 32,
                                'revision_id': ('d' if self.mutation == 'cross-execution' else 'a') * 64,
                                'pid': 1234, 'firmware_sha256': 'f' * 64, 'state': 'completed'}}
        if path.endswith('/units'):
            high = self.after and self.mutation not in ('wrong-en', 'restore-unknown')
            return {'units': [{'available': True, 'errors': {}, 'properties': {
                'flash-mode': True, 'mode-frozen': True, 'en-level': high,
                'output-known': False, 'active': False, 'edge-count': 0,
                'decoded-programs': 0, 'unqualified-programs': 0}}]}
        raise AssertionError(('unexpected fake route', path))

    def request(self, path, **kwargs):
        high = self.mutation not in ('wrong-en', 'restore-unknown')
        image = m.Image.new('RGB', (64, 64), (255, 255, 255) if high else (0, 0, 0))
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        raw = buffer.getvalue()
        return raw, {'x-frame-sha256': '0' * 64 if self.mutation == 'frame-hash' else m.common.sha(raw),
                     'x-frame-execution-id': 'b' * 32, 'x-frame-revision-id': 'a' * 64}


def phase_case(mutation):
    with tempfile.TemporaryDirectory() as temp:
        client = FakePhaseClient(mutation)
        lane = m.Lane(client, SimpleNamespace(), 'cores3', True, Path(temp))
        client.lane = lane
        lane.owned['session_id'] = '1' * 32
        lane.session = {'pid': 1234, 'firmware_sha256': 'f' * 64}
        lane.pins = {'white': 2, 'yellow': 1}
        lane.same_vm = lambda: None
        return lane.phase('restore' if mutation == 'restore-unknown' else 'raw9')


def execute_case(mutation):
    with tempfile.TemporaryDirectory() as temp:
        lane = m.Lane(None, SimpleNamespace(hold_file=None), 'cores3', True, Path(temp))
        lane.create = lambda: None
        lane.same_vm = lambda: None
        lane.reject_mode = lambda: None
        lane.capture_zip = lambda: None
        lane.cleanup = lambda: {'status': 'PASS'}
        state = {'output-known': True, 'active': False, 'en-level': False,
                 'rising-edges': 0, 'edge-count': 0, 'decoded-programs': 0,
                 'unqualified-programs': 0, 'timeout-events': 0,
                 'last-program-count': 0, 'flash-level-pct': 0, 'timeout-ms': 0}

        def phase(name):
            before = dict(state)
            pulses = {'original-short': 1, 'original-long100': 2, 'original-long60': 10,
                      'original-long30': 16, 'raw9': 9, 'raw16': 16,
                      'invalid17': 17, 'slow2': 2}.get(name)
            if pulses:
                state['rising-edges'] += pulses
                state['edge-count'] += pulses * 2
                state['en-level'] = True
                known = name not in ('invalid17', 'slow2')
                if mutation == 'unknown-short' and name == 'original-short':
                    known = False
                if mutation == 'known-invalid' and name == 'invalid17':
                    known = True
                if mutation == 'known-slow' and name == 'slow2':
                    known = True
                state['output-known'] = known
                if known:
                    state['decoded-programs'] += 1
                    state['last-program-count'] = pulses
                    state['flash-level-pct'] = 100 - ((pulses - 1) % 8) * 10
                    state['timeout-ms'] = 220 if pulses <= 8 else 1300
                    state['active'] = True
                else:
                    state['unqualified-programs'] += 1
                    state['active'] = False
                if mutation == 'missing-edges' and name == 'original-short':
                    state['rising-edges'] = before['rising-edges']
                    state['edge-count'] = before['edge-count']
                if mutation == 'wrong-table' and name == 'raw9':
                    state['flash-level-pct'] = 30
            else:
                state.update({'output-known': True, 'active': False, 'en-level': False})
            if mutation == 'all-off':
                state.update({'output-known': False, 'active': False, 'edge-count': 0,
                              'decoded-programs': 0, 'unqualified-programs': 0})
            if mutation == 'restore-unknown' and name == 'restore':
                state.update({'output-known': False, 'active': False})
            item = {'index': len(lane.report['observations']), 'phase': name,
                    'before_properties': before, 'unit': {'properties': dict(state)}}
            lane.report['observations'].append(item)
            return item

        lane.phase = phase
        lane.units = lambda: {'units': [{'properties': {
            **state, 'output-known': True, 'active': False,
            'timeout-events': state['timeout-events'] + 1}}]}
        result = lane.execute()
        if result['status'] != 'PASS':
            raise ValueError(result['error']['message'])
        assert result['model_completeness'] == 'partial'
        return result


compiled = []
for phase in m.PHASES:
    payload = m.package('a' * 32, phase, {'white': 2, 'yellow': 1})
    compile(payload['files']['main.py']['data'], 'main.py', 'exec')
    assert base64.b64decode(payload['files']['official_flash.py']['data']) == m.DRIVER.read_bytes()
    compiled.append(phase)

record('phase-valid-fake-fixture', lambda: phase_case('none'), True)
record('reject-cross-execution-and-revision', lambda: phase_case('cross-execution'), False,
       'GET program identity differs')
record('reject-receipt-checkpoint-mismatch', lambda: phase_case('receipt-revision'), False,
       'POST receipt revision differs')
record('reject-no-current-execution-START', lambda: phase_case('missing-start'), False,
       'fresh execution START missing')
record('reject-incomplete-record', lambda: phase_case('incomplete-line'), False,
       'fresh guest record missing')
record('reject-wrong-nonce', lambda: phase_case('wrong-nonce'), False,
       'fresh guest record missing')
record('reject-duplicate-record', lambda: phase_case('duplicate-line'), False,
       'fresh guest record missing')
record('reject-wrong-phase-pad', lambda: phase_case('wrong-en'), False,
       'guest/QOM EN pad differs')
record('reject-frame-hash-mismatch', lambda: phase_case('frame-hash'), False,
       'frame Run identity differs')
record('reject-record-before-true-START', lambda: phase_case('before-true-start'), False)
record('execute-valid-fake-partial-fixture', lambda: execute_case('none'), True)
record('reject-all-off-no-waveform', lambda: execute_case('all-off'), False,
       'long-low reset did not reach known off')
record('reject-unknown-mandatory-single-pulse', lambda: execute_case('unknown-short'), False,
       'one-pulse original driver minimum not qualified')
record('reject-no-real-edges', lambda: execute_case('missing-edges'), False,
       'actual GPIO pulse edges missing')
record('reject-wrong-qualified-table', lambda: execute_case('wrong-table'), False,
       'qualified command differs')
record('reject-admitted-17-pulse-negative', lambda: execute_case('known-invalid'), False,
       'qualified command differs')
record('reject-admitted-slow-wave-negative', lambda: execute_case('known-slow'), False,
       'negative waveform was incorrectly admitted')
record('reject-unknown-final-restore', lambda: phase_case('restore-unknown'), False,
       'long-low reset/recovery not known off')

report = {'category': 'OFFLINE_CHECKER_AUDIT_NO_GUEST_NO_API',
          'probe_sha256': hashlib.sha256(SOURCE).hexdigest(),
          'driver_sha256': hashlib.sha256(m.DRIVER.read_bytes()).hexdigest(),
          'driver_bytes': len(m.DRIVER.read_bytes()), 'phases_compiled': compiled,
          'network': 'DENIED', 'tests': RESULTS,
          'pass': sum(row['status'] == 'PASS' for row in RESULTS),
          'unresolved': sum(row['status'] == 'UNRESOLVED' for row in RESULTS)}
Path(__file__).with_name('report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
