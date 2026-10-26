#!/usr/bin/env python3
"""Independent local source replay. Only writes inside this fresh audit folder."""
from pathlib import Path
from datetime import datetime, timezone
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import traceback

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
SOURCE = ROOT / '.work/unit-runtime-source-ledc-readback/qemu'
REPLAY = OUT / 'qemu'
BUILD_MANIFEST = ROOT / '.work/unit-runtime-build-ledc-readback/build-manifest.json'
BOOTSTRAP = ROOT / 'scripts/bootstrap-unit-runtime.py'
BASE_COMMIT = '40edccac415693c5130f91c01d84176ae6008566'
GIT = Path(shutil.which('git')).resolve()
PYTHON = Path(sys.executable).resolve()
env = {**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_LFS_SKIP_SMUDGE': '1'}
commands = []
receipt = {'schema_version': 1, 'status': 'RUNNING', 'started_at': datetime.now(timezone.utc).isoformat(),
           'scope': 'Source replay only; no build, API, runtime, guest or hardware execution.',
           'writes': 'Own new .work/unit-ledc-readback-replay-20261026 directory only',
           'base_commit': BASE_COMMIT}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n')


def command(label, args, cwd=OUT):
    path = OUT / 'logs' / f'{len(commands)+1:02d}-{label}.txt'
    record = {'sequence': len(commands)+1, 'label': label, 'argv': [str(a) for a in args],
              'cwd': str(cwd.relative_to(ROOT)), 'started_at': datetime.now(timezone.utc).isoformat()}
    run = subprocess.run([str(a) for a in args], cwd=cwd, env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, check=False)
    path.write_bytes(run.stdout)
    record.update(returncode=run.returncode, output=str(path.relative_to(OUT)), output_sha256=sha(run.stdout),
                  finished_at=datetime.now(timezone.utc).isoformat())
    commands.append(record)
    write('commands.json', commands)
    if run.returncode:
        raise RuntimeError(f'{label}: exit {run.returncode}; see {path.name}')
    return run.stdout.decode()


def git(label, args, cwd=REPLAY):
    return command(label, [GIT, '-c', 'core.hooksPath=/dev/null', *args], cwd)


def source_fingerprints(directory, names):
    result = {}
    for name in names:
        path = directory / name
        result[name] = {'present': path.is_file(), 'symlink': path.is_symlink(),
                        **({'sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size} if path.is_file() else {})}
    return result


try:
    assert not REPLAY.exists()
    manifest_raw, bootstrap_raw = BUILD_MANIFEST.read_bytes(), BOOTSTRAP.read_bytes()
    (OUT / 'inputs/build-manifest.json').write_bytes(manifest_raw)
    (OUT / 'inputs/bootstrap-unit-runtime.py').write_bytes(bootstrap_raw)
    manifest = json.loads(manifest_raw)
    tree = ast.parse(bootstrap_raw.decode())
    definitions = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                   and n.targets[0].id in {'QEMU_COMMIT', 'PATCHES'}}
    assert definitions['QEMU_COMMIT'] == manifest['qemu']['commit'] == BASE_COMMIT
    order = definitions['PATCHES']
    assert len(order) == 7 and list(manifest['patches']) == list(order)
    assert len(manifest['files']) == 106
    patches, patch_rows, names = [], [], set()
    for index, name in enumerate(order, 1):
        raw = (ROOT / name).read_bytes()
        assert sha(raw) == manifest['patches'][name], name
        target = OUT / 'inputs' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        patches.append(target)
        names.update(line[6:] for line in raw.decode().splitlines() if line.startswith('+++ b/'))
        patch_rows.append({'sequence': index, 'source': name, 'snapshot': str(target.relative_to(OUT)),
                           'bytes': len(raw), 'sha256': sha(raw)})
    assert names == set(manifest['files']), 'manifest patch-file inventory differs'
    write('patches.json', patch_rows)
    tools = {'python': {'name': PYTHON.name, 'sha256': sha(PYTHON.read_bytes()), 'version': sys.version},
             'git': {'path': str(GIT), 'sha256': sha(GIT.read_bytes()), 'version': command('git-version', [GIT, '--version']).strip()},
             'bootstrap': {'path': str(BOOTSTRAP.relative_to(ROOT)), 'sha256': sha(bootstrap_raw)},
             'replay_script': {'sha256': sha(Path(__file__).read_bytes())}}
    write('tools.json', tools)
    source_head = git('readonly-source-head', ['rev-parse', 'HEAD'], SOURCE).strip()
    assert source_head == BASE_COMMIT
    cold_before = source_fingerprints(SOURCE, names)
    assert all(cold_before[n]['present'] and not cold_before[n]['symlink'] and cold_before[n]['sha256'] == v for n, v in manifest['files'].items())
    write('cold-build-source-before.json', cold_before)
    binary = Path(manifest['binary'])
    assert binary.resolve().is_relative_to(ROOT) and binary.is_file()
    binary_before = sha(binary.read_bytes())
    assert binary_before == manifest['binary_sha256']
    receipt.update(input_build_manifest_sha256=sha(manifest_raw), bootstrap_sha256=sha(bootstrap_raw),
                   cold_build_binary_sha256=binary_before, patch_count=7, expected_source_files=106,
                   clone_source='Existing local repository object store; no network fetch')
    write('receipt.json', receipt)
    print('Frozen 7 patch hashes, 106 cold-build source hashes and binary SHA verified.', flush=True)
    git('clone-local-shared-no-checkout', ['clone', '--shared', '--no-checkout', str(SOURCE), str(REPLAY)], OUT)
    git('checkout-fixed-base', ['checkout', '--detach', BASE_COMMIT])
    assert git('base-head', ['rev-parse', 'HEAD']).strip() == BASE_COMMIT
    base_tree = git('base-tree-object', ['rev-parse', 'HEAD^{tree}']).strip()
    assert git('base-clean-status', ['status', '--porcelain=v1', '--untracked-files=all']) == ''
    baseline = source_fingerprints(REPLAY, names)
    write('base-source-files.json', baseline)
    forward = []
    for row, patch in zip(patch_rows, patches):
        index = row['sequence']
        git(f'forward-{index:02d}-check', ['apply', '--check', str(patch)])
        git(f'forward-{index:02d}-apply', ['apply', str(patch)])
        forward.append({'sequence': index, 'patch': row['source'], 'sha256': row['sha256'], 'check': 'PASS', 'apply': 'PASS'})
        print(f'Forward {index}/7 checked and applied: {Path(row["source"]).name}', flush=True)
    write('forward.json', forward)
    actual = source_fingerprints(REPLAY, names)
    comparison = []
    for name, expected in sorted(manifest['files'].items()):
        observed = actual[name]
        assert observed['present'] and not observed['symlink'] and observed['sha256'] == expected, name
        comparison.append({'path': name, 'manifest_sha256': expected, 'replayed_sha256': observed['sha256'],
                           'cold_build_source_sha256': cold_before[name]['sha256'], 'bytes': observed['bytes'], 'match': True})
        destination = OUT / 'forward-source' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((REPLAY / name).read_bytes())
    write('forward-source-comparison.json', comparison)
    forward_status = git('forward-status', ['status', '--porcelain=v1', '--untracked-files=all'])
    write('forward-summary.json', {'status': 'PASS', 'matched_source_files': len(comparison),
          'expected_file_set_matches_patch_plus_paths': True, 'cold_build_binary_sha256': binary_before,
          'tree_object': base_tree, 'worktree_status_sha256': sha(forward_status.encode())})
    print('Forward replay matches cold-build manifest and current cold-build source: 106/106.', flush=True)
    reverse = []
    for row, patch in reversed(list(zip(patch_rows, patches))):
        index = row['sequence']
        git(f'reverse-{index:02d}-check', ['apply', '--reverse', '--check', str(patch)])
        git(f'reverse-{index:02d}-apply', ['apply', '--reverse', str(patch)])
        reverse.append({'forward_sequence': index, 'patch': row['source'], 'sha256': row['sha256'], 'check': 'PASS', 'apply': 'PASS'})
        print(f'Reverse patch {index} checked and applied.', flush=True)
    write('reverse.json', reverse)
    assert source_fingerprints(REPLAY, names) == baseline, 'affected-file bytes/presence did not return to base'
    assert git('final-head', ['rev-parse', 'HEAD']).strip() == BASE_COMMIT
    assert git('final-tree-object', ['rev-parse', 'HEAD^{tree}']).strip() == base_tree
    assert git('final-clean-status', ['status', '--porcelain=v1', '--untracked-files=all']) == ''
    git('final-worktree-diff-empty', ['diff', '--no-ext-diff', '--exit-code', 'HEAD'])
    git('final-index-diff-empty', ['diff', '--no-ext-diff', '--cached', '--exit-code', 'HEAD'])
    cold_after = source_fingerprints(SOURCE, names)
    assert cold_after == cold_before
    assert BUILD_MANIFEST.read_bytes() == manifest_raw and BOOTSTRAP.read_bytes() == bootstrap_raw
    assert sha(binary.read_bytes()) == binary_before
    assert all(sha((ROOT / row['source']).read_bytes()) == row['sha256'] for row in patch_rows)
    write('cold-build-source-after.json', cold_after)
    receipt.update(status='PASS', finished_at=datetime.now(timezone.utc).isoformat(), base_tree=base_tree,
                   source_files_matched=106, forward_checks=7, forward_applies=7, reverse_checks=7, reverse_applies=7,
                   reverse_order=[row['forward_sequence'] for row in reverse],
                   final_base_clean=True, affected_files_restored_exactly=True,
                   cold_build_source_unchanged=True, cold_build_binary_unchanged=True,
                   frozen_manifest_bootstrap_and_patches_unchanged=True,
                   new_build_performed=False, api_calls=0, sessions_started=0,
                   patched_source_sha256_inventory=sha((OUT / 'forward-source-comparison.json').read_bytes()),
                   commands=len(commands))
except BaseException as error:
    receipt.update(status='FAIL', finished_at=datetime.now(timezone.utc).isoformat(),
                   error=type(error).__name__ + ': ' + str(error))
    (OUT / 'failure.txt').write_text(traceback.format_exc())
    write('receipt.json', receipt)
    raise
else:
    write('receipt.json', receipt)
    print(json.dumps(receipt, indent=2), flush=True)
