#!/usr/bin/env python3
"""Independent offline source-host IO review. Synthetic checks are not runtime PASS."""
import ast
import contextlib
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from unittest.mock import patch

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
AUTHOR = ROOT / '.work/unit-source-host-io-20261026'
SHA = lambda b: hashlib.sha256(b).hexdigest()
checks, unexpected = [], []

def check(name, value):
    assert value, name
    checks.append(name)

def reject(name, fn):
    try:
        fn()
    except (RuntimeError, AssertionError, ValueError, TypeError, KeyError, StopIteration):
        checks.append(name)
    else:
        raise AssertionError('negative accepted: ' + name)

def denied(label):
    def call(*a, **k):
        unexpected.append(label)
        raise AssertionError('forbidden offline call ' + label)
    return call

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def main():
    authoring = json.loads((AUTHOR / 'authoring-ready.json').read_bytes())
    before = {n: SHA((AUTHOR / n).read_bytes()) for n in authoring['files']}
    check('author runner exact expected identity', before['run_source_host_io.py'] == '211365bb5abafc2390fb7e0da72da3b8b1ff224beaba750785dcd88b786534b2')
    check('all frozen author file bytes and sizes', all(before[n] == row['sha256'] and (AUTHOR / n).stat().st_size == row['size_bytes'] for n, row in authoring['files'].items()))
    for line in (AUTHOR / 'AUTHORING.SHA256SUMS').read_text().splitlines():
        digest, n = line.split('  ', 1)
        check('author top hash ' + n, SHA((AUTHOR / n).read_bytes()) == digest)
    sys.path[:0] = [str(AUTHOR), str(ROOT / 'tests/units'), str(ROOT / 'platform/tools')]
    with patch.object(socket, 'socket', denied('socket')), patch.object(socket, 'create_connection', denied('connect')), patch.object(urllib.request, 'urlopen', denied('HTTP')), patch.object(subprocess, 'Popen', denied('Popen')), patch.object(subprocess, 'run', denied('run')), patch.object(subprocess, 'check_output', denied('check_output')), patch.object(os, 'system', denied('system')):
        h = module('independent_source_host_io', AUTHOR / 'run_source_host_io.py')
        from run_service_cases import Client
        with patch.object(Client, '__init__', denied('Client')):
            prepared = AUTHOR / 'selfcheck-r4/prepared24'
            descriptor = h.load(prepared / 'prepared.json')
            rows = descriptor['cases']
            expected = {(d, c) for d in ('atoms3r', 'sticks3', 'stopwatch') for c in ('pir', 'dual-button', 'limit', 'key', 'rgb', 'fan', 'rs485', 'hub')}
            check('exact 24 selected pairs and no duplicate', len(rows) == 24 and {(r['device_id'], r['unit_id']) for r in rows} == expected)
            check('original guest protocol byte/AST preservation', h.preparation.protocol_audit()[0] == h.load(prepared / 'protocol-audit.json'))
            check('original oracle function hashes', h.function_hashes() == h.load(prepared / 'original-functions.json'))
            with h.offline_guard():
                h.fresh_sources(prepared)
                for row in rows:
                    case_dir = prepared / row['device_id'] / row['unit_id']
                    request = h.validate_caller(case_dir, row)
                    check(row['device_id'] + '/' + row['unit_id'] + ' 19 byte-exact caller files and CAS', len(request['files']) == 19 and h.sha(h.canonical(request['files'])) == row['source_cas_sha256'])
                    check(row['device_id'] + '/' + row['unit_id'] + ' original flags/admission/no ADC', row['custom_flags'] == h.FLAGS and row['custom_driver_modification'] is False and row['adc_fixture'] == 'NOT USED' and row['resource_preflight']['status'] == 'ADMITTED_NOT_EXECUTED')
            row = rows[0]
            request = h.load(prepared / row['device_id'] / row['unit_id'] / 'source-request.json')
            cas = h.sha(h.canonical(request['files']))
            fw = 'a' * 64
            meta = {'base_sha256': row['base_firmware_sha256'], 'source_sha256': cas, 'effective_source_sha256': cas,
                'firmware_sha256': fw, 'files': [{'path': n, 'sha256': h.sha(s.encode()), 'size': len(s.encode()), 'origin': 'caller'} for n, s in request['files'].items()],
                'generated_files': [], 'caller_file_count': 19, 'caller_source_bytes': sum(len(s.encode()) for s in request['files'].values()),
                'status': 'COMPOSED_NOT_EXECUTED', 'kind': 'uiflow2-source-composition',
                'vfs': {'filesystem': 'LittleFS', 'source': 'actual-base-partition-table', 'offset': row['reference_layout']['offset'], 'size': row['reference_layout']['size']},
                'preservation': {k: True for k in ('outside_vfs_unchanged', 'existing_files_readback_verified', 'source_readback_verified')},
                'toolchain': row['expected_composer_toolchain']}
            firmware = {'source': {'kind': 'uiflow', 'artifact_id': cas, 'metadata': meta}, 'sha256': fw, 'firmware_id': fw}
            check('source provenance predicate accepts exact synthetic fixture', h.source_provenance(firmware, request, row) == firmware['source'])
            for label, mutate in [
                ('base mismatch', lambda x: x['source']['metadata'].update(base_sha256='b' * 64)),
                ('effective CAS mismatch', lambda x: x['source']['metadata'].update(effective_source_sha256='b' * 64)),
                ('generated source', lambda x: x['source']['metadata'].update(generated_files=['hidden.py'])),
                ('file origin mismatch', lambda x: x['source']['metadata']['files'][0].update(origin='generated')),
                ('file bytes mismatch', lambda x: x['source']['metadata']['files'][0].update(sha256='b' * 64)),
                ('VFS offset mismatch', lambda x: x['source']['metadata']['vfs'].update(offset=0)),
                ('preservation not verified', lambda x: x['source']['metadata']['preservation'].update(source_readback_verified=False)),
                ('composer ABI drift', lambda x: x['source']['metadata'].update(toolchain={'wrong': True})),
                ('composition relabeled executed', lambda x: x['source']['metadata'].update(status='EXECUTED')),
            ]:
                x = deepcopy(firmware); mutate(x)
                reject('source predicate rejects ' + label, lambda x=x: h.source_provenance(x, request, row))
            source = (AUTHOR / 'run_source_host_io.py').read_text()
            tree = ast.parse(source)
            run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_case')
            calls = [ast.unparse(n.func) for n in ast.walk(run) if isinstance(n, ast.Call)]
            check('complete original IO oracle directly invoked', 'original.validate_io' in calls)
            evidence = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'evidence_check')
            check('complete original evidence oracle directly invoked', any(isinstance(n, ast.Call) and ast.unparse(n.func) == 'original.validate_evidence' for n in ast.walk(evidence)))
            check('host font canvas BMI observation retained', 'host_observation' in calls and 'actual_host_font_canvas_layout_and_fresh_internal_bmi' in ast.get_source_segment(source, run))
            check('formal positive-input binder directly invoked', 'host_contract.positive_input_binding(' in source)
            check('no source fallback calls to original run or prepare', 'original.run_case(' not in source and 'preparation.prepare_one(' not in source and 'build_control_image(' not in source)
            check('runtime identity remains parameterized', "proof['runtime_binary_sha256'] == args.expected_runtime_sha256" in source and 'M5_UNIT_EXPECT_RUNTIME_SHA256' in source)
            fixture = module('independent_original_host_io_fixture', ROOT / 'tests/units/test_host_io_execution.py')
            for case in h.CASES:
                data = fixture.fixture(case)
                result = h.host_contract.positive_input_binding(*data)
                check('formal positive binding synthetic fixture ' + case, len(result['vectors']) == len(h.host_contract.INPUTS[case]))
            data = list(fixture.fixture('key'))
            data[2]['posts'][0]['request']['values']['pressed'] = False
            reject('positive binding rejects wrong action vector', lambda: h.host_contract.positive_input_binding(*data))
            data = list(fixture.fixture('hub'))
            data[2]['posts'][-1]['request']['id'] = 'ncir'
            reject('HUB child IDs cannot alias', lambda: h.host_contract.positive_input_binding(*data))
            data = list(fixture.fixture('rgb')); data[2]['posts'] = [fixture.fixture('key')[2]['posts'][0]]
            reject('output-only case cannot claim an input POST', lambda: h.host_contract.positive_input_binding(*data))
            prior = 'OLD_MARKER\r\n'
            predicate = lambda text: 'OLD_MARKER\r\n' in text
            check('old predicate plus unrelated bytes does not count fresh', not h.original_and_fresh(predicate, prior + 'new\r\n', prior + 'new\r\n', prior, 0))
            check('predicate in fresh suffix accepted', h.original_and_fresh(predicate, prior + prior, prior + prior, prior, 0))
            check('original offset and fresh suffix are both required', h.original_and_fresh(predicate, prior, prior + prior, prior, len(prior)))
            with tempfile.TemporaryDirectory(prefix='sandbox-', dir=OUT) as temporary:
                temp = Path(temporary)
                events = [{'event_id': 0, 'kind': 'input', 'accepted': True, 'before_cursor': {'data': 'a'}},
                          {'event_id': 1, 'kind': 'wait-success', 'input_event': 0, 'serial_file': 'one.txt'},
                          {'event_id': 2, 'kind': 'input', 'accepted': True, 'before_cursor': {'data': 'aFIRST\nb'}},
                          {'event_id': 3, 'kind': 'wait-success', 'input_event': 2, 'serial_file': 'two.txt'}]
                (temp / 'one.txt').write_text('aFIRST\n'); (temp / 'two.txt').write_text('aFIRST\nbSECOND\n')
                serial = 'aFIRST\nbSECOND\n'
                check('bounded fresh UART windows', len(h.bounded_windows(temp, events, serial)) == 2)
                (temp / 'one.txt').write_text(serial)
                reject('observation cannot cross next input upper bound', lambda: h.bounded_windows(temp, events, serial))
                (temp / 'one.txt').write_text('a')
                reject('zero fresh suffix rejected', lambda: h.bounded_windows(temp, events, serial))
                h.HERE = temp
                for n in ('run_source_host_io.py', 'source_api_common.py'):
                    shutil.copyfile(AUTHOR / n, temp / n)
                with contextlib.redirect_stdout(io.StringIO()), h.offline_guard():
                    h.main(['--out-dir', str(temp / 'default'), '--device', 'atoms3r', '--case', 'pir'])
                    alternate = h.prepare(temp / 'alternate', ['sticks3'], ['rgb'], '1' * 64)
                check('default prepares without Client or execution', h.load(temp / 'default/prepared.json')['status'] == 'PREPARED_NO_API_OR_RUNTIME')
                check('runtime SHA can differ from default', alternate[0]['expected_runtime_sha256'] == '1' * 64)
                reject('invalid runtime rejected before writing', lambda: h.prepare(temp / 'bad', ['atoms3r'], ['pir'], 'short'))
                check('invalid runtime produced no directory', not (temp / 'bad').exists())
                reject('excluded original IR cannot enter selection', lambda: h.prepare(temp / 'ir', ['atoms3r'], ['ir']))
                reject('excluded original Buzzer cannot enter selection', lambda: h.prepare(temp / 'buzzer', ['atoms3r'], ['buzzer']))
                reject('execute without root bridge rejected', lambda: h.main(['--out-dir', str(temp / 'execute'), '--execute']))
                check('no binary generated in sandbox', not list(temp.rglob('*.bin')))
            for path in ('artifacts', 'firmware', 'firmware/compose', 'sessions/x/network-fault', '../firmware/uiflow', '/firmware/uiflow', 'firmware%2fuiflow'):
                reject('mutation guard rejects ' + path, lambda path=path: h.mutation_allowed(path, 'POST'))
            for path, method in [('firmware/uiflow', 'POST'), ('sessions', 'POST'), ('sessions/x/unit-input', 'POST'), ('sessions/x?purge=0', 'DELETE')]:
                h.mutation_allowed(path, method)
                check('authorized source-path mutation ' + path, True)
            reject('stop purge=1 rejected', lambda: h.mutation_allowed('sessions/x?purge=1', 'DELETE'))
            check('no forbidden calls attempted', unexpected == [])
    check('author files remain unchanged', before == {n: SHA((AUTHOR / n).read_bytes()) for n in authoring['files']})
    report = {'status': 'PASS_OFFLINE_ONLY', 'runner_sha256': before['run_source_host_io.py'], 'authoring_receipt_sha256': SHA((AUTHOR / 'authoring-ready.json').read_bytes()),
        'scope': 'Independent offline source/CAS/oracle/CLI/predicate and synthetic counterexample review; no API, browser, guest, firmware build or subprocess execution',
        'check_count': len(checks), 'checks': checks, 'unexpected_calls': unexpected, 'selected_combinations': 24, 'caller_files_each': 19,
        'open_findings': [], 'runtime_functional_result': 'NOT RUN', 'hardware': 'NOT RUN',
        'boundaries': ['Original IR/Buzzer excluded; historical original/custom outcomes unchanged', 'Angle/Light ADC fixture/oracle boundaries retained', 'Fresh source/runtime/HEAD/toolchain preparation required for root execution', 'Real PID/worker, DOM/HTTP, UART/QOM, ZIP-before-stop and cleanup still require actual execution', 'Native frame readability is not established by offline decoding or synthetic checks']}
    (OUT / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'review.md').write_text('# 三主机 IO source harness 独审\n\nPASS_OFFLINE_ONLY，无未关闭问题。作者freeze匹配；原24组合×19 caller源文件/CAS/实际host base与VFS、官方驱动与config均核对。原IO validate_io/validate_evidence直接调用；formal positive_input_binding、host字体/canvas/layout与新鲜BMI读取均保留。\n\n独立' + str(len(checks)) + '项离线检查通过，包含source provenance字段负控、source-only mutation白名单、原正式input绑定、陈旧UART/零后缀/跨下一输入上界反例、runtime参数化、默认不构造Client与不生成BIN。禁止socket/HTTP/Client/进程调用，实际外部调用0。作者文件审前后不变。\n\n此结论仅说明harness可交root执行，不是虚拟设备或硬件PASS。原IR/Buzzer和ADC边界保持；实际功能、runtime/worker、DOM/HTTP、ZIP/cleanup及native frame人工可读性仍需root执行和审查。\n', encoding='utf-8')
    names = ['review.py', 'review.json', 'review.md']
    (OUT / 'SHA256SUMS').write_text(''.join(SHA((OUT / n).read_bytes()) + '  ' + n + '\n' for n in names))
    print(json.dumps({'status': report['status'], 'checks': len(checks), 'review_sha256': SHA((OUT / 'review.json').read_bytes()), 'unexpected_calls': unexpected}))

if __name__ == '__main__':
    main()
