#!/usr/bin/env python3
"""Audit only completed rest21 case artifacts; every incremental receipt is PENDING.

No active/truncated frame is opened. Final24 still requires terminal batch SHA,
all disjoint case sets, and separate actual native-frame visual review.
"""
from __future__ import annotations
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import socket
import subprocess
import sys
import urllib.request
from unittest.mock import patch

sys.dont_write_bytecode = True
import audit as a


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt-name', required=True)
    args = parser.parse_args()
    a.need(Path(args.receipt_name).name == args.receipt_name and args.receipt_name.endswith('.json'), 'local JSON receipt only')
    out = a.HERE / args.receipt_name
    a.need(not out.exists(), 'never overwrite incremental audit receipt')
    fan, batch = a.AUTHOR / 'live-fan-r1', a.AUTHOR / 'live-rest-r1'
    prepared = a.LOAD(batch / 'prepared.json')
    frozen, fan_frozen = a.LOAD(batch / 'tooling-source-freeze.json'), a.LOAD(fan / 'tooling-source-freeze.json')
    a.need(frozen == fan_frozen and len(frozen) == 481, 'actual batch source dependency bytes/inventory differ')
    for filename, digest in frozen.items():
        a.need(a.SHA((batch / 'source-snapshot' / (filename + '.txt')).read_bytes()) == digest, 'prepared rest21 source snapshot changed')
    a.need({(r['device_id'], r['unit_id']) for r in prepared['cases']} == {(h, u) for h in a.HOSTS for u in a.UNITS if u != 'fan'}, 'rest21 exact selection differs')
    calls = []
    def denied(*args, **kwargs):
        calls.append('forbidden operation attempted')
        raise RuntimeError('incremental review forbids API/network/process/guest')
    sys.path[:0] = [str(a.ROOT / 'tests/units'), str(a.ROOT / 'platform/tools')]
    reviewed, pending = [], []
    with ExitStack() as stack:
        for obj, name in ((urllib.request, 'urlopen'), (socket, 'socket'), (socket, 'create_connection'), (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_output')):
            stack.enter_context(patch.object(obj, name, denied))
        import run_io_cases as original
        import run_host_io_cases as host
        stack.enter_context(patch.object(sys.modules['run_service_cases'].Client, '__init__', denied))
        for row in prepared['cases']:
            result_file = batch / row['device_id'] / row['unit_id'] / 'result.json'
            try:
                result = a.LOAD(result_file)
            except (FileNotFoundError, json.JSONDecodeError):
                result = None
            if not result or result.get('status') != 'PASS' or result.get('saved_case_replay', {}).get('status') != 'PASS':
                pending.append([row['device_id'], row['unit_id']])
                continue
            reviewed.append(a.audit_case(batch, row, frozen, original, host))
    a.need(not calls, 'review attempted forbidden operation')
    report = {'status': 'PENDING', 'scope': 'Completed-case incremental raw evidence only. Rest21 batch SHA/terminal gate and final24 are not yet established by this receipt.',
              'auditor_sha256': a.SHA((a.HERE / 'audit.py').read_bytes()), 'incremental_auditor_sha256': a.SHA(Path(__file__).read_bytes()),
              'source_context_by_batch': {'fan-r1': a.LOAD(fan / 'prepared.json')['source_context_commit'], 'rest-r1': prepared['source_context_commit']},
              'same_481_source_dependency_inventory_and_hashes': True, 'completed_rest_cases_reviewed': len(reviewed),
              'expected_rest_cases': 21, 'total_with_previously_reviewed_fan3': len(reviewed) + 3,
              'pending_rest_cases': pending, 'cases': reviewed, 'native_visual_review': 'SEPARATE_ACTUAL_INSPECTION_REQUIRED',
              'API_browser_guest_subprocess_calls_during_review': 0, 'batch_terminal_checksum_gate': 'PENDING_FINAL24_REVIEW',
              'original_files_modified': False, 'hardware': 'NOT RUN'}
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'completed_rest_cases_reviewed', 'total_with_previously_reviewed_fan3', 'pending_rest_cases', 'same_481_source_dependency_inventory_and_hashes', 'API_browser_guest_subprocess_calls_during_review')}, indent=2))


if __name__ == '__main__':
    main()
