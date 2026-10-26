#!/usr/bin/env python3
"""Read-only independent review of the frozen pre-final-checks source archive."""
import ast
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from urllib.parse import urlsplit
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ARC = ROOT / 'docs/evidence/2026-10-26-unit-source-hosts-29d8'
N = ARC.name
SHA = lambda b: hashlib.sha256(b).hexdigest()
J = lambda p: json.loads(p.read_bytes())

def fingerprint(a):
    files = {p.relative_to(a).as_posix(): p.read_bytes() for p in a.rglob('*') if p.is_file()}
    index = ''.join(f'{SHA(b)}  {n}\n' for n, b in sorted(files.items()))
    return {'files': len(files), 'bytes': sum(map(len, files.values())), 'all_files_index_sha256': SHA(index.encode()), 'top_manifest_sha256': SHA(files['SHA256SUMS']), 'auditor_sha256': SHA(files['audit_archive.py'])}

def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def main():
    before = fingerprint(ARC)
    assert (ROOT / '.work/archive_source_hosts_20261026.py').read_bytes() == (ARC / 'audit_archive.py').read_bytes()
    files = {p.relative_to(ARC).as_posix(): p for p in ARC.rglob('*') if p.is_file()}
    assert not any(p.is_symlink() for p in ARC.rglob('*'))
    listed = {}
    for line in (ARC / 'SHA256SUMS').read_text().splitlines():
        digest, n = line.split('  ', 1)
        assert re.fullmatch('[a-f0-9]{64}', digest) and n not in listed
        assert SHA(files[n].read_bytes()) == digest
        listed[n] = digest
    assert set(listed) == set(files) - {'SHA256SUMS'}
    prov = J(ARC / 'copy-provenance.json')['files']
    source_compared = 0
    for n, row in prov.items():
        data = files[n].read_bytes()
        assert SHA(data) == row['sha256'] and len(data) == row['size'] and row['byte_changes'] is False
        src = ROOT / row['source']
        assert src.is_relative_to(ROOT) and '..' not in PurePosixPath(row['source']).parts
        assert src.is_file() and not src.is_symlink()
        assert src.read_bytes() == data
        source_compared += 1
    mapping = J(ARC / 'transport-paths.json')['files']
    assert len({r['original'] for r in mapping}) == len(mapping) == len({r['transport'] for r in mapping})
    transport = {}
    for row in mapping:
        assert row['original'].endswith('.md') and row['transport'] == row['original'] + '.txt'
        assert row['original'] not in files and row['byte_changes'] is False
        b = files[row['transport']].read_bytes()
        assert SHA(b) == row['sha256'] and len(b) == row['size']
        transport[row['original']] = row['transport']
    assert [n for n in files if n.endswith('.md')] == ['README.md']
    nested = 0
    for n, p in files.items():
        if p.name in ('SHA256SUMS', 'HARNESS_SHA256SUMS') and n != 'SHA256SUMS':
            for line in p.read_text().splitlines():
                if not line:
                    continue
                digest, rel = line.split('  ', 1)
                orig = (p.parent / rel).relative_to(ARC).as_posix()
                assert SHA(files[transport.get(orig, orig)].read_bytes()) == digest
                nested += 1
    counts = dict(zip_copies=0, zip_unique=0, zip_members=0, images=0, utf8=0, python_parsed=0)
    zip_digests = set()
    credential_candidates = []
    bad = {'.pyc', '.bin', '.rom', '.elf', '.exe', '.dylib', '.so', '.o', '.a'}
    # Independent expression covers quoted JSON keys and assignment forms.
    literals = re.compile(r'''(?ix)(?<![\w-])(?:["']?)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)(?:["']?)\s*[:=]\s*["'][^"'\r\n]{16,}["']''')
    key_or_mac = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{24,}|(?i:\bBearer\s+[A-Za-z0-9_.~+/-]{24,})|(?<![\da-fA-F])(?:[\da-fA-F]{2}:){5}[\da-fA-F]{2}(?![\da-fA-F])')
    def inspect(data, locator, in_zip=False):
        assert PurePosixPath(locator.split('!')[-1]).suffix.lower() not in bad
        assert data[:4] not in {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe'}
        if data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')) or data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                assert im.width > 0 and im.height > 0
            counts['images'] += 1
        elif data.startswith((b'PK\x03\x04', b'PK\x05\x06')):
            assert not in_zip
            counts['zip_copies'] += 1
            zip_digests.add(SHA(data))
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                assert z.testzip() is None and not z.comment
                names = z.namelist()
                assert len(names) == len(set(names))
                for info in z.infolist():
                    p = PurePosixPath(info.filename)
                    assert not p.is_absolute() and '..' not in p.parts and '\\' not in info.filename
                    assert (info.external_attr >> 16) & 0o170000 != 0o120000
                    counts['zip_members'] += 1
                    if not info.is_dir():
                        inspect(z.read(info), locator + '!' + info.filename, True)
                manifest = json.loads(z.read('manifest.json'))['files']
                assert set(manifest) == set(names) - {'manifest.json'}
                for name, row in manifest.items():
                    b = z.read(name)
                    assert len(b) == row['size'] and SHA(b) == row['sha256']
        else:
            text = data.decode('utf-8')
            counts['utf8'] += 1
            if literals.search(text) or key_or_mac.search(text):
                credential_candidates.append(locator)
            for match in re.finditer(r'https?://[^\s"\x27<>\\)]+', text):
                url = match.group()
                if any(c in url for c in '{}$'):
                    continue
                host = urlsplit(url).hostname
                if not host:
                    continue
                assert not host.endswith(('.local', '.lan'))
                try:
                    address = ipaddress.ip_address(host)
                except ValueError:
                    continue
                nets = [ipaddress.ip_network(x) for x in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32')]
                fixture = str(address) in ('10.0.2.2', '10.0.2.15') or any(address.version == n.version and address in n for n in nets)
                assert address.is_global or address.is_loopback or fixture
            if locator.endswith('.py'):
                ast.parse(text)
                counts['python_parsed'] += 1
    for n, p in files.items():
        if n not in ('audit-report.json', 'SHA256SUMS'):
            inspect(p.read_bytes(), n)
    assert not credential_candidates, 'privacy candidates; values deliberately withheld'
    counts['zip_unique'] = len(zip_digests)
    expected = {(h, c) for h in ('atoms3r', 'sticks3', 'stopwatch') for c in ('button', 'relay', 'env-iii')}
    sync = J(ARC / 'sync/receipt.json')
    prepared = J(ARC / 'batches/post-sync-r1/prepared.json')
    batch = J(ARC / 'batches/post-sync-r1/batch-result.json')
    summary = J(ARC / 'machine-summary.json')
    assert batch['status'] == 'PASS' and len(batch['cases']) == 9
    assert {(r['device_id'], r['unit_id']) for r in batch['cases']} == expected
    assert {(r['device_id'], r['unit_id']) for r in summary['sessions']} == expected
    assert len({r['session_id'] for r in summary['sessions']}) == 9
    assert datetime.fromisoformat(prepared['created_at']) > datetime.fromisoformat(sync['at'])
    assert sync['head'] == prepared['source_context_commit']
    assert SHA((ARC / 'harness/run_source_hosts.py').read_bytes()) == sync['next_source_harness_sha256']
    result_rows = []
    for row in summary['sessions']:
        result = J(ARC / row['result'])
        assert SHA((ARC / row['result']).read_bytes()) == row['result_sha256']
        assert result['source_context_commit'] == sync['head']
        assert result['runtime_provenance']['runtime_binary_sha256'] == sync['next_source_runtime_sha256']
        assert result['status'] == 'PASS' and all(result['checks'].values())
        assert result['source']['metadata']['caller_file_count'] == 5 and result['uploaded_driver_files'] == []
        assert result['cleanup']['pid_gone'] and not result['cleanup']['flash_retained'] and result['cleanup']['health_active_sessions'] == 0
        result_rows.append({k: result[k] for k in ('device_id', 'unit_id', 'session_id', 'source_context_commit', 'source_cas_sha256', 'firmware_sha256', 'base_firmware_sha256')})
    owner = module_from(ARC / 'audit_archive.py', 'owner_frozen_auditor')
    owner_report = owner.audit(ROOT, ARC, True)
    write('owner-audit-original.json', owner_report)
    negatives = []
    def must_reject(name, fn, error_contains=None):
        try:
            fn()
        except AssertionError as e:
            if error_contains:
                assert error_contains in str(e), (name, type(e).__name__, str(e))
            negatives.append({'name': name, 'status': 'REJECTED_AS_EXPECTED', 'type': type(e).__name__, 'expected_stage': error_contains or 'semantic assertion after byte checks'})
        else:
            raise AssertionError('accepted negative: ' + name)
    with tempfile.TemporaryDirectory(prefix='scratch-', dir=OUT) as scratch:
        s = Path(scratch)
        fresh = s / 'fresh-checkout'
        copied = fresh / 'docs/evidence' / N
        shutil.copytree(ARC, copied)
        assert not (fresh / '.work').exists()
        assert fingerprint(copied) == before
        fresh_owner = module_from(copied / 'audit_archive.py', 'fresh_archived_auditor')
        write('owner-audit-without-work.json', fresh_owner.audit(fresh, copied, True))
        # Patch only parsed JSON, with original bytes and top SHA still valid.
        mutations = [
            ('wrong-sync-head', 'sync/receipt.json', 'head', '0' * 40),
            ('wrong-sync-runtime', 'sync/receipt.json', 'next_source_runtime_sha256', '0' * 64),
            ('wrong-sync-harness', 'sync/receipt.json', 'next_source_harness_sha256', '0' * 64),
            ('sync-fetch-not-fresh', 'sync/receipt.json', 'fresh_fetch', False),
            ('sync-tree-not-clean', 'sync/receipt.json', 'working_tree_clean', False),
            ('prepare-not-post-sync', 'batches/post-sync-r1/prepared.json', 'source_context_stage', 'PRE_SYNC'),
            ('prepare-still-required', 'batches/post-sync-r1/prepared.json', 'fresh_prepare_required_after_root_commit_and_fetch', True),
            ('prepare-before-sync', 'batches/post-sync-r1/prepared.json', 'created_at', '2026-10-26T00:00:00+00:00'),
            ('prepare-naive-time', 'batches/post-sync-r1/prepared.json', 'created_at', '2026-10-26T04:50:02'),
            ('sync-naive-time', 'sync/receipt.json', 'at', '2026-10-26T04:49:44'),
        ]
        for name, rel, key, value in mutations:
            baseline_load = fresh_owner.load
            def injected(path, rel=rel, key=key, value=value, base=baseline_load):
                doc = base(path)
                if path == copied / rel:
                    doc = copy.deepcopy(doc)
                    doc[key] = value
                return doc
            fresh_owner.load = injected
            try:
                must_reject(name, lambda: fresh_owner.audit(fresh, copied, True))
            finally:
                fresh_owner.load = baseline_load
        readme = (copied / 'README.md').read_bytes()
        key = 'api' + '_key'
        val = 'SYNTHETIC_' + 'CANARY_' + 'NO_REAL_KEY'
        for name, line in [
            ('quoted-json-credential', json.dumps({key: val})),
            ('single-quoted-credential', repr({key: val})),
            ('quoted-assignment-credential', key + ' = ' + repr(val)),
        ]:
            (copied / 'README.md').write_bytes(readme + b'\n' + line.encode())
            must_reject(name, lambda: fresh_owner.audit(fresh, copied, False), 'credential/MAC candidate')
        (copied / 'README.md').write_bytes(readme)
        assert fingerprint(copied) == before
        syroot = s / 'symlink-source'
        syarc = s / 'symlink-archive'
        syroot.mkdir(); syarc.mkdir()
        (syroot / 'actual.txt').write_text('harmless synthetic text\n')
        (syroot / 'alias.txt').symlink_to('actual.txt')
        realdir = syroot / 'real'
        realdir.mkdir(); (realdir / 'file.txt').write_text('harmless synthetic ancestor fixture\n')
        (syroot / 'aliasdir').symlink_to('real', target_is_directory=True)
        (syarc / 'copy-provenance.json').write_text('{"schema_version":1,"files":{}}')
        (syarc / 'transport-paths.json').write_text('{"schema_version":1,"files":[]}')
        fresh_owner._PROVENANCE = fresh_owner._TRANSPORT = None
        must_reject('source-file-symlink', lambda: fresh_owner.register(syroot, syarc, 'alias.txt', 'copy.txt'), 'symlink source/destination component')
        must_reject('source-ancestor-symlink', lambda: fresh_owner.register(syroot, syarc, 'aliasdir/file.txt', 'copy.txt'), 'symlink source/destination component')
        assert not (syarc / 'copy.txt').exists()
    after = fingerprint(ARC)
    assert before == after
    write('negative-controls.json', {'status': 'PASS', 'tests': len(negatives), 'results': negatives, 'on_original_archive_mutation': False, 'network_browser_guest_calls': 0})
    report = {'schema_version': 1, 'status': 'PASS', 'at': datetime.now(timezone.utc).isoformat(), 'scope': 'Frozen archive before root appends final verification and this review; archive integrity and declared identity binding only; live UART/QOM semantics reviewed separately in review/live', 'archive': N, 'before_final_verification_fingerprint': before, 'archive_unchanged_after_review': before == after, 'source_original_bytes_compared': source_compared, 'markdown_transport_entries': len(mapping), 'nested_checksum_entries': nested, 'counts': counts, 'privacy_candidates': len(credential_candidates), 'exact_host_case_pairs': len(expected), 'unique_sessions': len(result_rows), 'sessions': result_rows, 'archived_auditor_without_original_work': 'PASS; real archive copy in fresh checkout with no .work directory', 'negative_controls': len(negatives), 'preflight_findings': [{'finding': 'source/ancestor symlink identity before resolve', 'status': 'FIXED_AND_NEGATIVE_CONTROL_VERIFIED'}, {'finding': 'sync receipt semantic binding', 'status': 'FIXED_AND_NEGATIVE_CONTROL_VERIFIED'}, {'finding': 'quoted JSON credential key scanning', 'status': 'FIXED_AND_NEGATIVE_CONTROL_VERIFIED'}], 'open_findings': [], 'functional_rerun': 'NOT RUN; existing nine virtual-device sessions are preserved evidence', 'hardware': 'NOT RUN', 'api_browser_network_guest_calls': 0}
    write('review.json', report)
    md = f'''# 三主机源码归档独立审查\n\n结论：PASS；当前审查范围无未关闭问题。仅审查 root 追加最终 verification/本报告前的固定归档。\n\n- 原归档 {before['files']} 文件、{before['bytes']} 字节；逐项核对顶层 SHA 全集，{source_compared} 份复制原文与现存 `.work` 原字节一致。\n- {len(mapping)} 份 Markdown 仅改存储后缀；{nested} 条嵌套 SHA 经映射逐条解析成功。\n- {counts['zip_copies']} 份 ZIP（{counts['zip_unique']} 个唯一载荷）、{counts['zip_members']} 成员路径/模式/CRC/清单 hash 正常；{counts['images']} 次图像完整解码成功；独立隐私候选为 0。\n- 精确三主机×三类型、九个唯一会话；sync HEAD/runtime/harness 与准备、源快照、结果身份一致。仅核对记录内容与完整性，UART/QOM 的实际功能语义已有独立 live 审查。\n- 把归档真实复制至无 `.work` 的临时新 checkout，直接导入所附 auditor，完整 audit PASS。\n- {len(negatives)} 个负控均按预期拒绝：源文件/祖先 symlink、错误 sync HEAD/runtime/harness、未 fresh fetch/脏树、非 post-sync/仍需 prepare、早于同步/无时区时间，以及 JSON/单引号/赋值形式的合成 credential。负控不改原归档，不依赖 checksum 失败。\n- 原归档审前审后逐文件指纹完全相同。未调用 API、浏览器、网络或 guest；没有重跑功能测试；hardware NOT RUN。\n\n审查时固定指纹：\n\n```text\nauditor_sha256 {before['auditor_sha256']}\nSHA256SUMS_sha256 {before['top_manifest_sha256']}\nall_files_index_sha256 {before['all_files_index_sha256']}\n```\n\n前期发现的 symlink 检查顺序、sync 语义绑定、quoted JSON 键扫描已由 owner 修复，并由本次负控独立验证。root 之后附加文件需重新生成顶层 SHA 并 rerun audit；本报告不预先覆盖这些新增文件。\n'''
    (OUT / 'review.md').write_text(md, encoding='utf-8')
    curated = ['review_archive.py', 'review.json', 'review.md', 'negative-controls.json', 'owner-audit-original.json', 'owner-audit-without-work.json']
    (OUT / 'SHA256SUMS').write_text(''.join(SHA((OUT / n).read_bytes()) + '  ' + n + '\n' for n in curated), encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'review_sha256': SHA((OUT / 'review.json').read_bytes()), 'negative_controls': len(negatives), 'fingerprint': before}, indent=2))

if __name__ == '__main__':
    main()
