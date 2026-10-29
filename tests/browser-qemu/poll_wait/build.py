#!/usr/bin/env python3
"""Compile and run the shipped poll branch against Emscripten 3.1.50."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emcc', required=True)
    parser.add_argument('--node', default='node')
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.out_dir.resolve()
    if output.exists():
        parser.error('--out-dir must be new; preserve prior evidence')
    version = subprocess.check_output([args.emcc, '--version'], text=True)
    if not re.search(r'\b3\.1\.50\b', version):
        parser.error('this negative control pins Emscripten 3.1.50')
    spec = importlib.util.spec_from_file_location('poll_patch', ROOT / 'platform/tests/test_wasm_poll_wait_patch.py')
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    output.mkdir(parents=True)
    (output / 'actual-poll.inc').write_text(patch.actual_wasm_poll())
    source = Path(__file__).with_name('probe.c')
    target = output / 'poll.cjs'
    command = [args.emcc, str(source), '-I' + str(output), '-O2', '-pthread',
               '-sPROXY_TO_PTHREAD=1', '-sPTHREAD_POOL_SIZE=1', '-sEXIT_RUNTIME=1',
               '-sSINGLE_FILE=1', '-sASSERTIONS=2', '-sENVIRONMENT=node,worker',
               '-o', str(target)]
    report = {'kind':'wasm-host-poll-control', 'sdk':'3.1.50', 'guest_execution':'NOT RUN',
              'source_sha256':sha(source), 'patch_sha256':sha(patch.PATCH),
              'actual_branch_sha256':sha(output / 'actual-poll.inc'), 'status':'FAIL'}
    try:
        with (output / 'build.log').open('wb') as stream:
            subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=True)
        result = subprocess.run([args.node, str(target)], capture_output=True, text=True, timeout=30)
        (output / 'run.log').write_text(result.stdout + result.stderr)
        result.check_returncode()
        marker = next(line[len('M5_POLL_WAIT '):] for line in result.stdout.splitlines() if line.startswith('M5_POLL_WAIT '))
        report.update(status='PASS', result=json.loads(marker), exit_code=result.returncode,
                      artifact_sha256=sha(target))
    finally:
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
