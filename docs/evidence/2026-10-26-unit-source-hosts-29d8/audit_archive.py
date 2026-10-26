#!/usr/bin/env python3
"""Offline source-host archive. Default audits; --assemble/--add-source copy exact bytes."""
import argparse
import ast
from datetime import datetime
import hashlib
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import zipfile
from urllib.parse import urlsplit
from PIL import Image

NAME = '2026-10-26-unit-source-hosts-29d8'
LIVE = '.work/unit-source-hosts-expanded-20261026/live-post-sync-r1'
HOSTS = ('atoms3r', 'sticks3', 'stopwatch')
CASES = ('button', 'relay', 'env-iii')
RUNTIME = '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
AUTHORED = {'README.md', 'audit_archive.py', 'copy-provenance.json', 'transport-paths.json', 'machine-summary.json', 'audit-report.json', 'SHA256SUMS'}
BAD = {'.pyc', '.bin', '.rom', '.elf', '.exe', '.dylib', '.so', '.o', '.a'}
MAGIC = {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe'}
sha = lambda data: hashlib.sha256(data).hexdigest()
load = lambda path: json.loads(path.read_bytes())
_PROVENANCE = None
_TRANSPORT = None

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def safe(base, relative):
    raw = PurePosixPath(relative)
    assert not raw.is_absolute() and '..' not in raw.parts and '\\' not in relative
    lexical = base / relative
    for ancestor in (lexical, *lexical.parents):
        if ancestor == base:
            break
        assert not ancestor.is_symlink(), 'symlink source/destination component'
    path = lexical.resolve()
    assert path.is_relative_to(base) and path != base
    return path

def register(root, arc, source_name, dest_name):
    global _PROVENANCE, _TRANSPORT
    if _PROVENANCE is None:
        _PROVENANCE = load(arc / 'copy-provenance.json')
        _TRANSPORT = load(arc / 'transport-paths.json')
    source = safe(root, source_name)
    assert source.is_file() and not source.is_symlink()
    raw = source.read_bytes()
    assert source.suffix.lower() not in BAD and raw[:4] not in MAGIC
    dest = safe(arc, dest_name)
    if dest.suffix == '.md':
        original = dest.relative_to(arc).as_posix()
        dest = dest.with_name(dest.name + '.txt')
        transport = _TRANSPORT
        row = {'original': original, 'transport': dest.relative_to(arc).as_posix(), 'sha256': sha(raw), 'size': len(raw), 'byte_changes': False}
        prior = {r['original']: r for r in transport['files']}
        if original in prior:
            assert prior[original] == row
        prior[original] = row
        transport['files'] = sorted(prior.values(), key=lambda x: x['original'])
    dest.parent.mkdir(parents=True, exist_ok=True)
    assert not dest.exists() or dest.read_bytes() == raw
    dest.write_bytes(raw)
    provenance = _PROVENANCE
    provenance['files'][dest.relative_to(arc).as_posix()] = {'source': source_name, 'sha256': sha(raw), 'size': len(raw), 'byte_changes': False}

def flush(arc):
    if _PROVENANCE is not None:
        save(arc / 'copy-provenance.json', _PROVENANCE)
        save(arc / 'transport-paths.json', _TRANSPORT)

def copy_tree(root, arc, source, dest):
    for path in sorted((root / source).rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store' and path.suffix != '.pyc':
            register(root, arc, path.relative_to(root).as_posix(), dest + '/' + path.relative_to(root / source).as_posix())

def assemble(root, arc):
    assert not arc.exists(), 'use a fresh archive, never overwrite evidence'
    terminal = load(root / LIVE / 'batch-result.json')
    assert terminal['status'] == 'PASS' and terminal['finished_at'] and len(terminal['cases']) == 9
    assert {(r['device_id'], r['unit_id']) for r in terminal['cases']} == {(h, c) for h in HOSTS for c in CASES}
    arc.mkdir(parents=True)
    save(arc / 'copy-provenance.json', {'schema_version': 1, 'files': {}})
    save(arc / 'transport-paths.json', {'schema_version': 1, 'byte_changes': False, 'files': []})
    copy_tree(root, arc, LIVE, 'batches/post-sync-r1')
    harness = '.work/unit-source-hosts-expanded-20261026'
    for name in ('run_source_hosts.py', 'source_api_common.py', 'self_check.py', 'README.md', 'common-origin.json', 'delivery-freeze.json', 'self-check-r1/result.json'):
        register(root, arc, harness + '/' + name, 'harness/' + name)
    copy_tree(root, arc, '.work/unit-source-hosts-independent-review-20261026', 'review/authoring')
    for source, dest in [('.work/unit-post-block-sync-20261026.json', 'sync/receipt.json'), ('.work/unit-post-block-fetch-20261026.log', 'sync/fetch.log'), ('.work/unit-post-block-merge-20261026.log', 'sync/merge.log'), (harness + '/live-post-sync-r1-process.log', 'verification/actual-process.log')]:
        register(root, arc, source, dest)
    rows = []
    for host in HOSTS:
        for case in CASES:
            rel = f'batches/post-sync-r1/{host}/{case}/result.json'
            result = load(arc / rel)
            rows.append({k: result[k] for k in ('device_id', 'unit_id', 'session_id', 'status', 'firmware_sha256', 'base_firmware_sha256', 'source_cas_sha256', 'source_context_commit') } | {'result': rel, 'result_sha256': sha((arc / rel).read_bytes())})
    save(arc / 'machine-summary.json', {'schema_version': 1, 'category': 'three-host UIFlow source API virtual-device validation', 'hardware': 'NOT RUN', 'external_work_log': 'SKIPPED_BY_USER', 'runtime_sha256': RUNTIME, 'functional_pass_sessions': 9, 'sessions': rows, 'scope': 'Only Button/Relay/ENV III per host; reference-bundled drivers unchanged; no inference for other 24 types, hotplug, physical behavior or shared full matrix'})
    flush(arc)
    (arc / 'audit_archive.py').write_bytes(Path(__file__).read_bytes())

def audit(root, arc, validate_manifest):
    assert not any(p.is_symlink() for p in arc.rglob('*')), 'symlink in archive tree'
    paths = sorted(p for p in arc.rglob('*') if p.is_file())
    files = {p.relative_to(arc).as_posix(): p for p in paths}
    provenance = load(arc / 'copy-provenance.json')['files']
    transport = {r['original']: r for r in load(arc / 'transport-paths.json')['files']}
    assert set(files) - set(provenance) <= AUTHORED
    assert {n for n in files if n.endswith('.md')} == {'README.md'}
    for name, row in provenance.items():
        raw = files[name].read_bytes()
        assert sha(raw) == row['sha256'] and len(raw) == row['size'] and row['byte_changes'] is False
        original = safe(root, row['source'])
        if original.is_file():
            assert raw == original.read_bytes()
    for name, row in transport.items():
        assert name not in files and sha(files[row['transport']].read_bytes()) == row['sha256'] and row['byte_changes'] is False
    images = 0
    zip_copies = 0
    zip_unique = set()
    members = 0
    utf8 = 0
    nested = 0
    def inspect(raw, locator, inside=False):
        nonlocal images, zip_copies, members, utf8
        assert raw[:4] not in MAGIC, locator
        if raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')) or raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
            with Image.open(io.BytesIO(raw)) as im:
                im.load()
                assert im.width > 0 and im.height > 0
            images += 1
        elif raw.startswith((b'PK\x03\x04', b'PK\x05\x06')):
            assert not inside, locator
            zip_copies += 1
            zip_unique.add(sha(raw))
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist()))
                assert not z.comment
                for member in z.infolist():
                    name = member.filename
                    safe(arc, name)
                    assert PurePosixPath(name).suffix.lower() not in BAD and (member.external_attr >> 16) & 0o170000 != 0o120000
                    members += 1
                    if not member.is_dir():
                        inspect(z.read(member), locator + '!' + name, True)
                manifest = json.loads(z.read('manifest.json'))
                assert set(manifest['files']) == set(z.namelist()) - {'manifest.json'}
                for name, row in manifest['files'].items():
                    payload = z.read(name)
                    assert sha(payload) == row['sha256'] and len(payload) == row['size']
        else:
            text = raw.decode('utf-8')
            utf8 += 1
            patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', r'\bsk-[A-Za-z0-9_-]{24,}', r'(?i)\bBearer\s+[A-Za-z0-9_.~+/-]{24,}', r'(?i)(?<![\w-])(?P<keyquote>[\x22\x27]?)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)(?P=keyquote)\s*[=:]\s*[\x22\x27][^\x22\x27\r\n]{16,}[\x22\x27]', r'(?<![\da-fA-F])(?:[\da-fA-F]{2}:){5}[\da-fA-F]{2}(?![\da-fA-F])']
            assert all(not re.search(pattern, text) for pattern in patterns), 'credential/MAC candidate: ' + locator
            for match in re.finditer(r'https?://[^\s\x22\x27<>\\)]+', text):
                value = match.group()
                if any(c in value for c in '{}$'):
                    continue
                host = urlsplit(value).hostname
                if not host:
                    continue
                assert not host.endswith(('.local', '.lan')), 'private hostname URL: ' + locator
                try:
                    address = ipaddress.ip_address(host)
                except ValueError:
                    continue
                documented_fixture = str(address) in ('10.0.2.2', '10.0.2.15') or any(address.version == n.version and address in n for n in map(ipaddress.ip_network, ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32')))
                assert address.is_global or address.is_loopback or documented_fixture, 'private URL: ' + locator
    for name, path in files.items():
        assert not path.is_symlink() and path.suffix.lower() not in BAD and '__pycache__' not in path.parts
        if name not in ('audit-report.json', 'SHA256SUMS'):
            inspect(path.read_bytes(), name)
        if path.suffix == '.py':
            ast.parse(path.read_text(encoding='utf-8'), filename=name)
        if path.name in ('SHA256SUMS', 'HARNESS_SHA256SUMS') and path != arc / 'SHA256SUMS':
            for line in path.read_text().splitlines():
                if not line:
                    continue
                digest, member = line.split('  ', 1)
                original = (path.parent / member).relative_to(arc).as_posix()
                target = transport.get(original, {}).get('transport', original)
                assert sha(safe(arc, target).read_bytes()) == digest, original
                nested += 1
    summary = load(arc / 'machine-summary.json')
    sync = load(arc / 'sync/receipt.json')
    prepared = load(arc / 'batches/post-sync-r1/prepared.json')
    frozen = load(arc / 'batches/post-sync-r1/tooling-source-freeze.json')
    assert sync['fresh_fetch'] is True and sync['working_tree_clean'] is True and sync['merge_output'] == 'Already up to date.'
    assert sync['head'] == prepared['source_context_commit'] and sync['next_source_runtime_sha256'] == RUNTIME
    assert prepared['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC' and prepared['fresh_prepare_required_after_root_commit_and_fetch'] is False
    sync_time = datetime.fromisoformat(sync['at'].replace('Z', '+00:00'))
    prepare_time = datetime.fromisoformat(prepared['created_at'].replace('Z', '+00:00'))
    assert sync_time.utcoffset() is not None and prepare_time.utcoffset() is not None and prepare_time > sync_time
    runner_sha = sync['next_source_harness_sha256']
    assert sha((arc / 'harness/run_source_hosts.py').read_bytes()) == runner_sha == frozen['HARNESS/run_source_hosts.py'] == sha((arc / 'batches/post-sync-r1/source-snapshot/HARNESS/run_source_hosts.py.txt').read_bytes())
    prepared_rows = {(r['device_id'], r['unit_id']): r for r in prepared['cases']}
    assert set(prepared_rows) == {(h, c) for h in HOSTS for c in CASES}
    assert len(summary['sessions']) == 9 and len({r['session_id'] for r in summary['sessions']}) == 9
    assert {(r['device_id'], r['unit_id']) for r in summary['sessions']} == {(h, c) for h in HOSTS for c in CASES}
    for row in summary['sessions']:
        path = safe(arc, row['result'])
        result = load(path)
        assert sha(path.read_bytes()) == row['result_sha256'] and result['status'] == row['status'] == 'PASS'
        assert all(result[k] == row[k] for k in ('device_id', 'unit_id', 'session_id', 'firmware_sha256', 'base_firmware_sha256', 'source_cas_sha256', 'source_context_commit'))
        prepared_row = prepared_rows[(row['device_id'], row['unit_id'])]
        assert row['source_context_commit'] == sync['head'] and result['source_context_stage'] == prepared_row['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC'
        assert all(result[k] == prepared_row[k] for k in ('source_context_commit', 'source_cas_sha256', 'base_firmware_sha256', 'probe_sha256', 'host_profile', 'attachments'))
        assert result['runtime_provenance']['runtime_binary_sha256'] == RUNTIME and all(result['checks'].values())
        assert result['cleanup']['pid_gone'] and result['cleanup']['flash_retained'] is False and result['cleanup']['health_active_sessions'] == 0
    if validate_manifest:
        listed = {}
        for line in (arc / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            assert name not in listed and sha(safe(arc, name).read_bytes()) == digest
            listed[name] = digest
        assert set(listed) == set(files) - {'SHA256SUMS'}
    return {'schema_version': 1, 'status': 'PASS', 'scope': 'Offline public archive byte provenance/transport/ZIP/CRC/images/UTF8/privacy/counts/sync binding; no API, guest, subprocess or compiler', 'provenance_files': len(provenance), 'transported_markdown': len(transport), 'nested_checksum_entries': nested, 'zip_payload_copies': zip_copies, 'unique_zip_payloads': len(zip_unique), 'zip_members': members, 'images_decoded': images, 'utf8_payloads': utf8, 'functional_pass_sessions': 9, 'source_context_commit': sync['head'], 'fresh_prepare_after_sync_verified': True, 'hardware': 'NOT RUN', 'source_work_directories_required_for_audit': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--assemble', action='store_true')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--add-source', action='append', default=[])
    args = parser.parse_args()
    root = args.repo_root.resolve()
    arc = root / 'docs/evidence' / NAME
    if args.assemble:
        assemble(root, arc)
        print(json.dumps({'status': 'ASSEMBLED_BYTES_ONLY', 'readme_required_before_audit': True}))
        return
    assert not args.add_source or args.write
    for item in args.add_source:
        register(root, arc, *item.split('=', 1))
    flush(arc)
    report = audit(root, arc, not args.write)
    if args.write:
        save(arc / 'audit-report.json', report)
        paths = sorted(p for p in arc.rglob('*') if p.is_file() and p != arc / 'SHA256SUMS')
        (arc / 'SHA256SUMS').write_text(''.join(sha(p.read_bytes()) + '  ' + p.relative_to(arc).as_posix() + '\n' for p in paths))
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
