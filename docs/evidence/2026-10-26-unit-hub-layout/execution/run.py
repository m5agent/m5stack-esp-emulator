#!/usr/bin/env python3
"""Freeze and run five browser-only suites against current product sources."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import time

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
digest = lambda data: hashlib.sha256(data).hexdigest()
stamp = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


cohort = json.loads((ROOT / '.work/unit-hub-layout-web-cohort-20261026.json').read_text())
for name, sha in cohort.items():
    assert digest((ROOT / name).read_bytes()) == sha, f'cohort drift: {name}'

prior = json.loads((ROOT / '.work/unit-readouts-regression-20261026/source-freeze.json').read_text())
names = set(prior['files']) | set(cohort) | {
    'tests/units/web_ui_bridge.py', 'tests/units/run_service_cases.py',
    'platform/tests/test_frontend_recovery.mjs',
}
frozen = {'schema_version': 1, 'category': 'post-promotion-browser-regression-source-freeze',
          'frozen_at': stamp(), 'scope': 'Current product sources; browser fixtures only, no Device Service/firmware/hardware.',
          'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
          'files': {}, 'vendor_asset_trees': {}, 'harness_sources': {}}
for name in sorted(names):
    data = (ROOT / name).read_bytes()
    target = WORK / 'tool-sources' / (name + '.txt')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    frozen['files'][name] = {'sha256': digest(data), 'snapshot': str(target.relative_to(WORK))}
for prefix in ['platform/web/vendor/m5stack-models', 'platform/web/vendor/three']:
    frozen['vendor_asset_trees'][prefix] = {str(path.relative_to(ROOT)): digest(path.read_bytes())
                                          for path in sorted((ROOT / prefix).rglob('*')) if path.is_file()}
for name in ['run.py', 'browser-layout-product.mjs']:
    frozen['harness_sources'][name] = digest((WORK / name).read_bytes())
write(WORK / 'source-freeze.json', frozen)
shutil.copy2(ROOT / '.work/unit-hub-layout-promoted-20261026.json', WORK / 'promotion-receipt.json')
shutil.copy2(ROOT / '.work/unit-hub-layout-web-cohort-20261026.json', WORK / 'promotion-cohort.json')

jobs = [
    ('model', ['node', 'platform/tests/test_model_shell.mjs'], {'M5_MODEL_TEST_OUT': str(WORK / 'model')}),
    ('panel', ['node', 'platform/tests/test_unit_panel.mjs'], {'M5_UNIT_PANEL_OUT': str(WORK / 'panel')}),
    ('bridge', ['node', 'platform/tests/test_unit_web_bridge.mjs'], {'M5_UNIT_WEB_BRIDGE_TEST_OUT': str(WORK / 'bridge')}),
    ('mount', ['node', 'platform/tests/test_session_mount.mjs', str(ROOT), str(WORK / 'mount')], {}),
    ('hub-product', ['node', str(WORK / 'browser-layout-product.mjs')], {}),
]


def run(job):
    name, command, extra = job
    started = stamp()
    before = time.monotonic()
    with (WORK / (name + '.stdout.txt')).open('w') as stdout, (WORK / (name + '.stderr.txt')).open('w') as stderr:
        result = subprocess.run(command, cwd=ROOT, env={**os.environ, **extra}, stdout=stdout, stderr=stderr)
    return {'name': name, 'command': command, 'started_at': started, 'finished_at': stamp(),
            'elapsed_seconds': round(time.monotonic() - before, 3), 'exit_code': result.returncode,
            'stdout': name + '.stdout.txt', 'stderr': name + '.stderr.txt'}


results = []
with ThreadPoolExecutor(max_workers=2) as pool:
    for future in as_completed([pool.submit(run, job) for job in jobs]):
        result = future.result()
        results.append(result)
        write(WORK / 'run-progress.json', results)
        print(json.dumps(result, ensure_ascii=False), flush=True)

drift = []
for name, entry in frozen['files'].items():
    if digest((ROOT / name).read_bytes()) != entry['sha256']:
        drift.append(name)
for tree in frozen['vendor_asset_trees'].values():
    for name, sha in tree.items():
        if digest((ROOT / name).read_bytes()) != sha:
            drift.append(name)
for name, sha in frozen['harness_sources'].items():
    if digest((WORK / name).read_bytes()) != sha:
        drift.append(name)
report = {'schema_version': 1, 'category': 'post-promotion-browser-regression',
          'status': 'PASS' if all(row['exit_code'] == 0 for row in results) and not drift else 'FAIL',
          'finished_at': stamp(), 'maximum_concurrent_browsers': 2,
          'firmware_execution': 'NOT RUN', 'device_service_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN',
          'source_drift': drift, 'runs': results}
write(WORK / 'run-summary.json', report)
print(json.dumps({'status': report['status'], 'source_drift': drift}, ensure_ascii=False), flush=True)
raise SystemExit(0 if report['status'] == 'PASS' else 1)
