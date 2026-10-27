#!/usr/bin/env python3
"""Verify this text-only build archive; optional original/source checks are read-only."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def load(name: str):
    return json.loads((ROOT / name).read_text())

def safe_file(name: str) -> Path:
    path = ROOT / name
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    assert path.is_file() and not path.is_symlink(), name
    return path

def check_privacy(raw: bytes, name: str):
    text = raw.decode('utf-8')
    patterns = {
        'mac-literal': r'(?i)(?<![a-f0-9])(?:[a-f0-9]{2}:){5}[a-f0-9]{2}(?![a-f0-9])',
        'private-key': r'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----',
        'bearer-token': r'(?i)Bearer [a-z0-9._~+/-]{24,}',
        'url-userinfo': r'https?://[^\s/"\x27]+:[^\s/"\x27]+@',
    }
    for kind, pattern in patterns.items():
        assert not re.search(pattern, text), (name, kind)
    assert b'\x00' not in raw, name

def verify_originals(index: dict, repo: Path):
    count = 0
    for item in index['records'] + index['fingerprints']:
        if 'source_path' not in item:
            continue
        path = Path(item['source_path'])
        path = path if path.is_absolute() else repo / path
        raw = path.read_bytes()
        assert len(raw) == item['source_bytes'] and sha(raw) == item['source_sha256'], str(path)
        count += 1
    return count

def replay_source(source: Path, repo: Path, receipt: dict, expected: dict):
    """Mutate only an isolated temporary index; verify worktree/actual index stay fixed."""
    paths = sorted(receipt['files'])
    patches = list(receipt['patches'])
    for name in paths:
        assert sha((source / name).read_bytes()) == receipt['files'][name], name
    for name in patches:
        assert sha((repo / name).read_bytes()) == receipt['patches'][name], name
    git_dir = Path(subprocess.check_output(['git', 'rev-parse', '--absolute-git-dir'], cwd=source, text=True).strip())
    actual_index = git_dir / 'index'
    index_before = sha(actual_index.read_bytes())
    with tempfile.TemporaryDirectory(prefix='m5-route-history-index-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'), GIT_OPTIONAL_LOCKS='0')
        def git(*args):
            result = subprocess.run(['git', *args], cwd=source, env=env, capture_output=True, text=True)
            assert result.returncode == 0, (args, result.returncode)
            return result.stdout.strip()
        assert git('rev-parse', 'HEAD') == receipt['qemu']['commit']
        base = git('rev-parse', 'HEAD^{tree}')
        git('read-tree', 'HEAD')
        git('add', '--', *paths)
        postimage = git('write-tree')
        for name in reversed(patches):
            git('apply', '--cached', '--reverse', '--check', str(repo / name))
            git('apply', '--cached', '--reverse', str(repo / name))
        reverse = git('write-tree')
        assert reverse == base == expected['base_tree']
        for name in patches:
            git('apply', '--cached', '--check', str(repo / name))
            git('apply', '--cached', str(repo / name))
        forward = git('write-tree')
        assert forward == postimage == expected['postimage_tree']
    assert sha(actual_index.read_bytes()) == index_before
    for name in paths:
        assert sha((source / name).read_bytes()) == receipt['files'][name], name
    return {'base_tree': base, 'postimage_tree': postimage, 'actual_index_unchanged': True, 'all_106_source_files_unchanged': True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, help='original repository root, needed only by optional checks')
    parser.add_argument('--check-originals', action='store_true', help='also compare every retained local original/fingerprint')
    parser.add_argument('--qemu-source', type=Path, help='optionally rerun the isolated-index reverse/forward replay on this matching source')
    args = parser.parse_args()
    if (args.check_originals or args.qemu_source) and not args.repo_root:
        parser.error('--repo-root is required for optional original/source checks')
    index = load('index.json')
    names = [r['archive_path'] for r in index['records']]
    assert len(names) == len(set(names))
    actual = {str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
    assert actual == set(names) | {'index.json'}, sorted(actual ^ (set(names) | {'index.json'}))
    for item in index['records']:
        path = safe_file(item['archive_path']); raw = path.read_bytes()
        assert len(raw) == item['archive_bytes'] and sha(raw) == item['archive_sha256'], item['archive_path']
        if item['classification'] == 'original-bytes':
            assert item['source_bytes'] == len(raw) and item['source_sha256'] == sha(raw)
        else:
            assert item['classification'] == 'generated'
        assert path.suffix.lower() not in {'.bin', '.rom', '.mpy', '.zip', '.a', '.o', '.dylib'}
        check_privacy(raw, item['archive_path'])
    check_privacy((ROOT / 'index.json').read_bytes(), 'index.json')
    for item in index['fingerprints']:
        assert item['classification'] == 'fingerprint-only' and item['source_bytes'] >= 0
        assert re.fullmatch(r'[0-9a-f]{64}', item['source_sha256'])
    source = load('originals/source-receipt.json')
    manifest = load('originals/build-manifest.json')
    root = load('originals/root-build-verification.json')
    check = load('originals/root-source-check.json')
    implementation = load('originals/implementation.json')
    replay = load('originals/source-replay/receipt.json')
    summary = load('summary.json')
    reuse = load('originals/dependency-reuse.json')
    cache = load('dependency-cache-verification.json')
    invocation = load('build-invocation.json')
    assert len(source['files']) == 106 and len(source['patches']) == 12
    assert source['files'] == manifest['files'] == root['source_files'] == replay['source_files_before'] == replay['source_files_after']
    assert source['patches'] == manifest['patches'] == root['patches'] == check['patches'] == replay['patches']
    assert check['source_status'] == 'verified' and check['source_files'] == 106
    assert source['qemu']['commit'] == root['source_commit'] == replay['qemu_commit'] == '40edccac415693c5130f91c01d84176ae6008566'
    assert manifest['binary_sha256'] == summary['runtime_sha256'] == root['new_runtime_sha256'] == replay['runtime_sha256_before'] == replay['runtime_sha256_after'] == '3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1'
    assert summary['prior_runtime_sha256'] == implementation['reference_runtime_sha256'] == '7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e'
    for flag in ('reverse_equals_head_tree', 'forward_equals_postimage_tree', 'actual_index_unchanged', 'all_106_source_files_unchanged', 'runtime_unchanged'):
        assert replay[flag] is True and summary['source_replay'][flag] is True
    assert replay['base_tree'] == replay['reversed_tree'] == 'ddde372fbcc1b22e99f24372e14dee425be3193b'
    assert replay['postimage_tree'] == replay['restored_tree'] == 'ce1b71562a4f87bcdd0344cc8dd8304b661fff6f'
    assert replay['actual_index_sha256_before'] == replay['actual_index_sha256_after']
    assert [r['patch'] for r in replay['reverse']] == list(reversed(source['patches']))
    assert [r['patch'] for r in replay['forward']] == list(source['patches'])
    assert len(replay['steps']) == 77 and all(r['exit_code'] == 0 for r in replay['steps'])
    assert len(implementation['files']) == 3
    assert all(r['candidate_sha256'] == source['files'][r['path']] for r in implementation['files'])
    source_fingerprints = {r['qemu_relative_path']: r['source_sha256'] for r in index['fingerprints'] if r['category'] == 'qemu-source-postimage'}
    assert source_fingerprints == source['files']
    patch_fingerprints = {r['source_path']: r['source_sha256'] for r in index['fingerprints'] if r['category'] == 'source-patch'}
    assert patch_fingerprints == source['patches']
    deps = reuse['copied_regular_dependency_files']
    assert len(deps) == 43 and len(cache['checks']) == 43 and all(c['match'] and deps[c['path']] == c['expected_sha256'] == c['actual_sha256'] for c in cache['checks'])
    dep_fingerprints = {r['dependency_relative_path']: r['source_sha256'] for r in index['fingerprints'] if r['category'] == 'reused-dependency-file'}
    assert dep_fingerprints == deps
    assert reuse['qemu_source_and_build_objects_copied'] is False
    assert invocation['bootstrap_captured_after_execution'] is True and invocation['argv'][-2:] == ['--jobs', '8']
    assert invocation['bootstrap_sha256'] == sha((ROOT / 'originals/bootstrap-unit-runtime.py.txt').read_bytes())
    log = (ROOT / 'originals/build.log').read_text()
    assert '[1508/1508]' in log and 'SHA256: ' + summary['runtime_sha256'] in log
    report = {'status': 'PASS', 'archive_records': len(index['records']), 'fingerprint_only_inputs': len(index['fingerprints']), 'patches': 12, 'source_files': 106, 'reused_dependency_files': 43, 'replay_tree_receipt': 'PASS', 'guest_execution': 'NOT RUN', 'hardware_execution': 'NOT RUN'}
    if args.check_originals:
        report['original_inputs_matched'] = verify_originals(index, args.repo_root.resolve())
    if args.qemu_source:
        report['optional_source_replay'] = replay_source(args.qemu_source.resolve(), args.repo_root.resolve(), source, replay)
    print(json.dumps(report, sort_keys=True))

if __name__ == '__main__':
    main()
