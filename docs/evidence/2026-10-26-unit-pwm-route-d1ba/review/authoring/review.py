#!/usr/bin/env python3
"""Independent offline-only harness review; synthetic checks are not guest PASS."""
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
AUTHOR = ROOT / '.work/unit-pwm-route-acceptance-20261026'
SHA = lambda b: hashlib.sha256(b).hexdigest()
checks = []
unexpected = []

def check(name, condition):
    assert condition, name
    checks.append(name)

def deny(name):
    def rejected(*a, **k):
        unexpected.append(name)
        raise AssertionError('forbidden offline operation: ' + name)
    return rejected

def reject(name, fn):
    try:
        fn()
    except RuntimeError:
        checks.append(name)
    else:
        raise AssertionError('negative accepted: ' + name)

def main():
    frozen = json.loads((AUTHOR / 'delivery-freeze.json').read_bytes())
    before = {n: SHA((AUTHOR / n).read_bytes()) for n in frozen['files']}
    check('all 12 delivery hashes and sizes match', all(before[n] == row['sha256'] and (AUTHOR / n).stat().st_size == row['size'] for n, row in frozen['files'].items()))
    check('requested runner identity', before['run_acceptance.py'] == '3d8c6257359920837aa4a49616d062f19aca5310dca6744f60d96645261d8635')
    with tempfile.TemporaryDirectory(prefix='sandbox-', dir=OUT) as temporary:
        harness = Path(temporary)
        for n in ['run_acceptance.py', 'source_api_common.py', *['guest/' + p.name for p in (AUTHOR / 'guest').glob('*.py')]]:
            dest = harness / n
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(AUTHOR / n, dest)
        sys.path[:0] = [str(harness), str(ROOT / 'tests/units'), str(ROOT / 'platform/tools')]
        with patch.object(socket, 'socket', deny('socket')), patch.object(urllib.request, 'urlopen', deny('HTTP')), patch.object(subprocess, 'Popen', deny('Popen')), patch.object(subprocess, 'run', deny('run')), patch.object(subprocess, 'check_output', deny('check_output')):
            spec = importlib.util.spec_from_file_location('independent_pwm_route_harness', harness / 'run_acceptance.py')
            h = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(h)
            h.ROOT = ROOT
            import run_service_cases
            with patch.object(run_service_cases, 'Client', deny('Client')):
                with contextlib.redirect_stdout(io.StringIO()):
                    h.main(['--out-dir', str(harness / 'default')])
                row = h.load(harness / 'default/prepared.json')
                request = h.load(harness / 'default/source-request.json')
                check('default is offline preparation', row['status'] == 'PREPARED_NO_API_OR_RUNTIME')
                check('exact source CAS', row['source_cas_sha256'] == frozen['source_cas_sha256'] == SHA(h.canonical(request['files'])))
                for name, text in request['files'].items():
                    check('exact guest byte copy ' + name, text.encode() == (AUTHOR / 'guest' / name).read_bytes() == (harness / 'default/files' / name).read_bytes())
                row2, request2 = h.prepare(harness / 'second')
                check('runtime-independent request determinism', request == request2 and row['caller_request_sha256'] == row2['caller_request_sha256'])
                check('single constructor and getter-only calls', row['guest_audit']['pwm_constructors'] == 1 and row['guest_audit']['post_constructor_setters'] == 0 and set(row['guest_audit']['getter_calls']) == {'freq', 'duty_u16'})
                check('60s hold; no callback imports', row['guest_audit']['hold_ms'] == 60000 and row['guest_audit']['callback_or_softtimer_driver'] == 'NOT IMPORTED')
                f = request['files']
                reject('post-init zero setter rejected', lambda: h.guest_audit({**f, 'pwm_route_program.py': f['pwm_route_program.py'].replace('duty = pwm.duty_u16()', 'duty = pwm.duty_u16(0)')}))
                reject('post-init freq setter rejected', lambda: h.guest_audit({**f, 'pwm_route_program.py': f['pwm_route_program.py'].replace('frequency = pwm.freq()', 'frequency = pwm.freq(2000)')}))
                reject('callback import rejected', lambda: h.guest_audit({**f, 'pwm_route_program.py': f['pwm_route_program.py'] + '\nfrom driver.haptic import Haptic\n'}))
                reject('runtime-conditioned config rejected', lambda: h.guest_audit({**f, 'probe_config.py': f['probe_config.py'] + 'RUNTIME = 1\n'}))
                b = {'data': 'PWMR_READY\r\nPWMR_HOLD 0 10 2000 0\r\n', 'next_offset': 50}
                a = {'data': b['data'] + 'PWMR_HOLD 1 260 2000 0\r\n', 'next_offset': 80}
                state = {'source': 'live', 'contract_status': 'frozen', 'units': [{'id': 'external1', 'unit_id': 'buzzer', 'source': 'guest-qom', 'available': True, 'errors': [], 'properties': {'frequency-hz': 2000, 'duty-pct': 0}}]}
                check('candidate actual predicate', h.evaluate_sample(b, state, a, 2000)['frequency-hz'] == 2000)
                for freq in (1999, 2000.5, 2001):
                    x = deepcopy(state); x['units'][0]['properties']['frequency-hz'] = freq
                    check('candidate tolerance ' + str(freq), h.evaluate_sample(b, x, a, 2000)['frequency-hz'] == freq)
                baseline = deepcopy(state); baseline['units'][0]['properties']['frequency-hz'] = 0
                check('baseline failure observation accepted separately', h.evaluate_sample(b, baseline, a, 0)['frequency-hz'] == 0)
                reject('zero cannot pass candidate', lambda: h.evaluate_sample(b, baseline, a, 2000))
                reject('2000 cannot reproduce baseline', lambda: h.evaluate_sample(b, state, a, 0))
                for field, value in [('frequency-hz', float('nan')), ('frequency-hz', float('inf')), ('frequency-hz', 1998.99), ('frequency-hz', 2001.01), ('duty-pct', 0.01), ('duty-pct', True)]:
                    x = deepcopy(state); x['units'][0]['properties'][field] = value
                    reject('invalid numeric ' + field + '/' + str(value), lambda x=x: h.evaluate_sample(b, x, a, 2000))
                reject('stale serial rejected', lambda: h.evaluate_sample(b, state, b, 2000))
                reject('unrelated appended bytes rejected', lambda: h.evaluate_sample(b, state, {'data': b['data'] + 'unrelated\r\n', 'next_offset': 90}, 2000))
                reject('changed prefix rejected', lambda: h.evaluate_sample(b, state, {'data': a['data'].replace('0 10', '0 11'), 'next_offset': 90}, 2000))
                reject('completed hold rejected', lambda: h.evaluate_sample(b, state, {'data': a['data'] + 'PWMR_HOLD_DONE\r\n', 'next_offset': 90}, 2000))
                reject('elapsed outside hold rejected', lambda: h.evaluate_sample(b, state, {'data': a['data'].replace('1 260', '1 60000'), 'next_offset': 90}, 2000))
                reject('guest getter mismatch rejected', lambda: h.evaluate_sample(b, state, {'data': a['data'].replace('1 260 2000', '1 260 0'), 'next_offset': 90}, 2000))
                for key, value in [('source', 'history'), ('contract_status', 'mutable')]:
                    x = deepcopy(state); x[key] = value
                    reject('state rejects ' + key, lambda x=x: h.evaluate_sample(b, x, a, 2000))
                for key, value in [('source', 'fake'), ('available', False), ('errors', ['broken']), ('unit_id', 'fan')]:
                    x = deepcopy(state); x['units'][0][key] = value
                    reject('endpoint rejects ' + key, lambda x=x: h.evaluate_sample(b, x, a, 2000))
                peer = {'status': 'FAIL_REPRODUCED', 'initialization_status': 'FAIL_REPRODUCED', 'expect_init_frequency_hz': 0, 'firmware_sha256': 'a' * 64, 'source_cas_sha256': row['source_cas_sha256'], 'source': {'metadata': {'effective_source_sha256': row['source_cas_sha256']}}, 'caller_request_sha256': row['caller_request_sha256'], 'runtime_provenance': {'runtime_binary_sha256': 'b' * 64}}
                candidate = {**deepcopy(peer), 'expected_runtime_sha256': 'c' * 64}
                check('same-identity A/B admitted', h.compare_peer(peer, candidate, request)['same_source_request_sha256'] == row['caller_request_sha256'])
                for key, value in [('status', 'PASS'), ('initialization_status', 'PASS'), ('expect_init_frequency_hz', 2000), ('firmware_sha256', 'd' * 64), ('source_cas_sha256', 'e' * 64), ('caller_request_sha256', 'f' * 64)]:
                    x = deepcopy(peer); x[key] = value
                    reject('A/B rejects peer ' + key, lambda x=x: h.compare_peer(x, candidate, request))
                x = deepcopy(peer); x['source']['metadata']['effective_source_sha256'] = 'd' * 64
                reject('A/B rejects different effective source', lambda: h.compare_peer(x, candidate, request))
                x = deepcopy(candidate); x['expected_runtime_sha256'] = 'b' * 64
                reject('A/B rejects same runtime', lambda: h.compare_peer(peer, x, request))
                reject('CLI rejects execute without exact runtime', lambda: h.main(['--execute', '--out-dir', str(harness / 'forbidden')]))
                with patch.dict(os.environ, {'M5_UNIT_WEB_BRIDGE': '1'}):
                    reject('CLI candidate requires peer', lambda: h.main(['--execute', '--out-dir', str(harness / 'forbidden'), '--expected-runtime-sha256', 'f' * 64, '--expect-init-frequency', '2000']))
                check('rejected execution produced no output', not (harness / 'forbidden').exists())
                check('no firmware binary from prepare', not list(harness.rglob('*.bin')))
                check('zero forbidden external/process calls', unexpected == [])
    check('author files unchanged', before == {n: SHA((AUTHOR / n).read_bytes()) for n in frozen['files']})
    report = {'status': 'PASS', 'scope': 'Independent read-only and synthetic offline sandbox of authoring/predicates/identity/CLI; no runtime, browser, service or subprocess calls. Not functional or hardware PASS.', 'runner_sha256': before['run_acceptance.py'], 'source_cas_sha256': frozen['source_cas_sha256'], 'checks': checks, 'check_count': len(checks), 'unexpected_calls': unexpected, 'open_findings': [], 'static_review': ['Five actual caller files contain one zero-duty constructor and only read-only getter calls after construction; no callback driver', 'Eight raw HTTP-backed UART-before/QOM/fresh-UART-after windows are evaluated inside the guest hold', 'Baseline is FAIL_REPRODUCED; candidate requires same firmware, caller/effective source and complete source request, plus distinct runtime', 'Actual source POST/session pin, PID/worker, DOM/HTTP, evidence ZIP before purge=0 stop, retained source/last frame, Flash release/PID exit/idle and offline replay are present'], 'limits': ['Sample windows lie within the 60-second guest hold; this is not evidence of complete 60-second continuous coverage', 'Getter source chain is fixed-source static evidence, not a dynamic native MMIO trace or universal firmware claim', 'Actual API runs and shared runtime regression belong to root'], 'hardware': 'NOT RUN'}
    (OUT / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'review.md').write_text('# PWM 初始化 A/B harness 独审\n\nPASS，无未关闭问题。12份作者交付hash匹配，五文件caller无构造后setter或回调驱动；baseline与candidate共用请求/CAS，不嵌入运行时预期。独立离线sandbox通过' + str(len(checks)) + '项检查，禁止socket/HTTP/Client/子进程调用，实际外部调用为0。\n\n八个UART前界→实际QOM→新UART后界窗口、同固件/caller/effective/request A/B、PID/worker、DOM/HTTP、ZIP-before-stop与history/Flash/PID清理均已静态核对；纯函数负控覆盖错误数值、非live状态、陈旧UART、hold完成、setter和A/B身份变化。\n\n此审查仅为离线作者/判断器证据，不是功能或硬件PASS。采样位于60秒guest hold内，不代表完整60秒连续覆盖；getter链证为静态源路径，未声称动态MMIO trace。作者文件未改。\n', encoding='utf-8')
    names = ['review.py', 'review.json', 'review.md']
    (OUT / 'SHA256SUMS').write_text(''.join(SHA((OUT / n).read_bytes()) + '  ' + n + '\n' for n in names))
    print(json.dumps({'status': 'PASS', 'checks': len(checks), 'review_sha256': SHA((OUT / 'review.json').read_bytes()), 'unexpected_calls': unexpected}))


if __name__ == '__main__':
    main()
