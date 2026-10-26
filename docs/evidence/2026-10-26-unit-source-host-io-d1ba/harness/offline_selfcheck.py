#!/usr/bin/env python3
"""Offline harness checks only: no fake Client, guest, API, browser or BIN.

Synthetic UART strings below exercise only cursor/predicate rejection helpers;
they are not runtime observations and never produce a virtual-device PASS.
"""
from __future__ import annotations
import argparse
import ast
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import run_source_host_io as harness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    harness.need(output.is_relative_to(harness.HERE) and output != harness.HERE and not output.exists(), 'choose a fresh selfcheck child')
    output.mkdir(parents=True)
    checks = []

    def check(name, callback):
        callback()
        checks.append({'name': name, 'status': 'PASS_OFFLINE_ONLY'})

    def rejected(callback, pattern):
        try:
            callback()
        except Exception as error:
            harness.need(pattern in str(error), 'rejection failed for an unrelated reason: ' + str(error))
        else:
            raise RuntimeError('expected fail-closed rejection did not happen')

    def assert_true(value, message='offline assertion failed'):
        harness.need(value, message)

    with harness.offline_guard():
        prepared = output / 'prepared24'
        rows = harness.prepare(prepared, list(harness.DEVICES), list(harness.CASES))
        check('all24-selected-source-requests', lambda: assert_true(len(rows) == 24 and {r['status'] for r in rows} == {'PREPARED_NO_API_OR_RUNTIME'}))
        check('actual-readonly-admission-and-ADC-boundaries', lambda: assert_true(harness.load(prepared / 'admission-inventory.json')['selected_combinations'] == 24))
        for row in rows:
            directory = prepared / row['device_id'] / row['unit_id']
            request = harness.validate_caller(directory, row)
            check(row['device_id'] + '/' + row['unit_id'] + ':exact19-original-host-and-driver-files', lambda request=request: assert_true(len(request['files']) == 19))
            for name, text in request['files'].items():
                ast.parse(text, filename=name)
            assert_true(row['custom_flags'] == harness.FLAGS and row['adc_fixture'] == 'NOT USED')
            assert_true(row['expected_runtime_sha256'] == harness.DEFAULT_RUNTIME)
        check('original-protocol-and-full-oracle-function-hashes', lambda: assert_true(harness.preparation.protocol_audit()[0] == harness.load(prepared / 'protocol-audit.json') and harness.function_hashes() == harness.load(prepared / 'original-functions.json')))
        check('strict-source-and-toolchain-current-continuity', lambda: harness.fresh_sources(prepared))
        check('no-network', lambda: rejected(lambda: harness.urllib.request.urlopen('http://127.0.0.1:8787'), 'offline mode forbids'))
        check('no-socket', lambda: rejected(lambda: harness.socket.socket(), 'offline mode forbids'))
        check('no-subprocess', lambda: rejected(lambda: harness.subprocess.Popen(['false']), 'offline mode forbids'))
        check('no-legacy-builder', lambda: rejected(lambda: harness.preparation.prepare_one(), 'offline mode forbids'))
        check('no-original-binary-runner', lambda: rejected(lambda: harness.original.run_case(), 'offline mode forbids'))
        check('no-Client-construction', lambda: rejected(lambda: harness.sys.modules['run_service_cases'].Client('http://127.0.0.1:8787'), 'offline mode forbids'))
        check('default-main-does-not-construct-Client', lambda: harness.main(['--out-dir', str(output / 'default-one'), '--device', 'atoms3r', '--case', 'pir']))
        check('existing-output-is-immutable', lambda: rejected(lambda: harness.prepare(prepared, ['atoms3r'], ['pir']), 'fresh harness child'))

        source_file = prepared / 'tooling-source-freeze.json'
        original_freeze = source_file.read_bytes()
        frozen = harness.load(source_file)
        key = next(iter(frozen))
        frozen[key] = '0' * 64
        harness.save(source_file, frozen)
        check('source-byte-drift-requires-fresh-prepare', lambda: rejected(lambda: harness.fresh_sources(prepared), 'source inventory/bytes drift'))
        source_file.write_bytes(original_freeze)
        frozen = harness.load(source_file)
        frozen['OFFLINE_EXTRA_INVENTORY_NEGATIVE_CONTROL'] = '0' * 64
        harness.save(source_file, frozen)
        check('source-inventory-drift-requires-fresh-prepare', lambda: rejected(lambda: harness.fresh_sources(prepared), 'source inventory/bytes drift'))
        source_file.write_bytes(original_freeze)
        chain_file = prepared / 'toolchain-before.json'
        original_chain = chain_file.read_bytes()
        chain = harness.load(chain_file)
        chain['python_executable_sha256'] = '0' * 64
        harness.save(chain_file, chain)
        check('toolchain-ABI-drift-requires-fresh-prepare', lambda: rejected(lambda: harness.fresh_sources(prepared), 'toolchain/ABI drift'))
        chain_file.write_bytes(original_chain)
        prepared_file = prepared / 'prepared.json'
        original_prepared = prepared_file.read_bytes()
        descriptor = harness.load(prepared_file)
        descriptor['source_context_commit'] = '0' * 40
        harness.save(prepared_file, descriptor)
        check('checkout-commit-drift-requires-fresh-prepare', lambda: rejected(lambda: harness.fresh_sources(prepared), 'checkout commit drift'))
        prepared_file.write_bytes(original_prepared)
        row = rows[0]
        case_dir = prepared / row['device_id'] / row['unit_id']
        source_file = case_dir / 'files/io_drivers/pir.py'
        raw = source_file.read_bytes()
        source_file.write_bytes(raw + b'\n# OFFLINE_DRIFT_NEGATIVE_CONTROL\n')
        check('saved-caller-driver-byte-drift-rejected', lambda: rejected(lambda: harness.validate_caller(case_dir, row), 'saved source bytes changed'))
        source_file.write_bytes(raw)
        alternate = harness.prepare(output / 'alternate-runtime-one', ['sticks3'], ['rgb'], '1' * 64)
        check('expected-runtime-is-parameterized', lambda: assert_true(alternate[0]['expected_runtime_sha256'] == '1' * 64))
        check('bad-runtime-SHA-rejected-before-write', lambda: rejected(lambda: harness.prepare(output / 'bad-runtime', ['atoms3r'], ['pir'], 'short'), 'full SHA256'))
        check('excluded-cases-cannot-be-selected', lambda: rejected(lambda: harness.prepare(output / 'excluded-ir', ['atoms3r'], ['ir']), 'unsupported/duplicate IO selection'))
        for path in ('artifacts', 'firmware', 'firmware/compose', 'sessions/x/network-fault', '../firmware/uiflow', '/firmware/uiflow', 'firmware%2fuiflow'):
            check('source-only-mutation-reject:' + path, lambda path=path: rejected(lambda: harness.mutation_allowed(path, 'POST'), 'prohibited' if path in ('artifacts', 'firmware', 'firmware/compose', 'sessions/x/network-fault') else 'unsafe API path'))
        for path, method in (('firmware/uiflow', 'POST'), ('sessions', 'POST'), ('sessions/abc/unit-input', 'POST'), ('sessions/abc?purge=0', 'DELETE')):
            check('allowed-original-source-mutation:' + path, lambda path=path, method=method: harness.mutation_allowed(path, method))

        prior = 'OFFLINE_OLD_MARKER\n'
        predicate = lambda text: 'OFFLINE_OLD_MARKER\n' in text
        check('stale-predicate-plus-unrelated-new-bytes-rejected', lambda: assert_true(not harness.original_and_fresh(predicate, prior + 'unrelated\n', prior + 'unrelated\n', prior, 0)))
        check('predicate-must-be-in-fresh-suffix', lambda: assert_true(harness.original_and_fresh(predicate, prior + prior, prior + prior, prior, 0)))
        check('original-offset-preserved-and-fresh-predicate-required', lambda: assert_true(harness.original_and_fresh(predicate, prior, prior + prior, prior, len(prior))))
        trace_dir = output / 'offline-window-helper-controls'
        trace_dir.mkdir()
        (trace_dir / 'first.txt').write_text('aOFFLINE_FRESH_1\n')
        (trace_dir / 'second.txt').write_text('aOFFLINE_FRESH_1\nbOFFLINE_FRESH_2\n')
        events = [
            {'event_id': 0, 'kind': 'input', 'accepted': True, 'before_cursor': {'data': 'a'}},
            {'event_id': 1, 'kind': 'wait-success', 'input_event': 0, 'serial_file': 'first.txt'},
            {'event_id': 2, 'kind': 'input', 'accepted': True, 'before_cursor': {'data': 'aOFFLINE_FRESH_1\nb'}},
            {'event_id': 3, 'kind': 'wait-success', 'input_event': 2, 'serial_file': 'second.txt'},
        ]
        serial = 'aOFFLINE_FRESH_1\nbOFFLINE_FRESH_2\n'
        check('bounded-UART-positive-helper-only', lambda: assert_true(len(harness.bounded_windows(trace_dir, events, serial)) == 2))
        (trace_dir / 'first.txt').write_text(serial)
        check('cross-next-input-upper-bound-rejected', lambda: rejected(lambda: harness.bounded_windows(trace_dir, events, serial), 'crossed next input upper'))
        check('no-BIN-files-created', lambda: assert_true(not list(output.rglob('*.bin'))))
        harness.fresh_sources(prepared)
        harness.checksums(prepared)
        harness.checksums(output / 'alternate-runtime-one')
    report = {'status': 'PASS_OFFLINE_ONLY', 'checks': checks, 'check_count': len(checks), 'prepared_combinations': 24,
              'API_network_browser_subprocess_guest_calls': 0, 'BIN_build_or_upload': False,
              'runtime_result': 'NOT RUN', 'hardware_validation': 'NOT RUN', 'final_runtime_source_context_freeze': False,
              'scope': 'Authoring/selfcheck only. Synthetic helper strings cannot establish guest/controller/runtime PASS.'}
    harness.save(output / 'offline-selfcheck.json', report)
    harness.checksums(output)
    print(json.dumps({k: report[k] for k in report if k != 'checks'}, indent=2))


if __name__ == '__main__':
    main()
