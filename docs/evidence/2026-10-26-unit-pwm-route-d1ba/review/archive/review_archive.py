#!/usr/bin/env python3
"""Independent read-only PWM archive audit, with temporary-copy negative controls."""
from collections import Counter
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request
from unittest.mock import patch
import zipfile
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
ARC = ROOT / 'docs/evidence/2026-10-26-unit-pwm-route-d1ba'
SHA = lambda b: hashlib.sha256(b).hexdigest()
J = lambda p: json.loads(p.read_bytes())

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def fingerprint(a):
    rows = [(p.relative_to(a).as_posix(), p.stat().st_size, digest(p)) for p in a.rglob('*') if p.is_file()]
    return {'files': len(rows), 'bytes': sum(n for _, n, _ in rows), 'all_files_index_sha256': SHA(''.join(h + '  ' + n + '\n' for n, _, h in sorted(rows)).encode()), 'top_manifest_sha256': digest(a / 'SHA256SUMS'), 'auditor_sha256': digest(a / 'audit_archive.py')}

def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def main():
    before = fingerprint(ARC)
    assert before['auditor_sha256'] == '7754602baba7e7f4d089eb9a0d4967db87ec502716960cebafcd8975fd77ce7a'
    assert (ARC / 'audit_archive.py').read_bytes() == (ROOT / '.work/archive_unit_pwm_route_20261026.py').read_bytes()
    files = {p.relative_to(ARC).as_posix(): p for p in ARC.rglob('*') if p.is_file()}
    assert not any(p.is_symlink() for p in ARC.rglob('*'))
    listed = {}
    for line in (ARC / 'SHA256SUMS').read_text().splitlines():
        h, n = line.split('  ', 1)
        assert n not in listed and digest(files[n]) == h
        listed[n] = h
    assert set(listed) == set(files) - {'SHA256SUMS'}
    provenance = J(ARC / 'copy-provenance.json')['files']
    for n, row in provenance.items():
        assert digest(files[n]) == row['sha256'] and files[n].stat().st_size == row['size'] and row['byte_changes'] is False
        src = ROOT / row['source']
        assert src.is_file() and not src.is_symlink() and src.read_bytes() == files[n].read_bytes()
    transport = J(ARC / 'transport-paths.json')['files']
    assert len({r['original'] for r in transport}) == len(transport) == len({r['transport'] for r in transport})
    translated = {}
    for row in transport:
        assert row['transport'] == row['original'] + '.txt' and row['byte_changes'] is False
        assert digest(files[row['transport']]) == row['sha256'] and files[row['transport']].stat().st_size == row['size']
        translated[row['original']] = row['transport']
    assert {n for n in files if n.endswith('.md')} == {'README.md'}
    omitted = J(ARC / 'omissions.json')['files']
    omission_reasons = Counter()
    for n, row in omitted.items():
        assert n == row['archive_original'] and n not in files and row['byte_changes'] is False
        source = ROOT / row['source']
        assert source.is_file() and not source.is_symlink() and digest(source) == row['sha256'] and source.stat().st_size == row['size']
        omission_reasons[row['reason']] += 1
        if 'png' in row:
            with Image.open(source) as im:
                im.load(); a = (im.size, im.convert('RGB').tobytes())
            with Image.open(files[row['png']]) as im:
                im.load(); b = (im.size, im.convert('RGB').tobytes())
            assert a == b and digest(files[row['png']]) == row['png_sha256']
    nested = 0
    for n, p in files.items():
        if p.name not in ('SHA256SUMS', 'HARNESS_SHA256SUMS') or n == 'SHA256SUMS':
            continue
        for line in p.read_text().splitlines():
            if not line:
                continue
            h, member = line.split('  ', 1)
            name = (PurePosixPath(n).parent / member).as_posix()
            target = translated.get(name, name)
            assert digest(files[target]) == h if target in files else omitted[name]['sha256'] == h
            nested += 1
    zip_members, zips = 0, 0
    for n, p in files.items():
        if p.suffix != '.zip':
            continue
        zips += 1
        with zipfile.ZipFile(p) as z:
            assert z.testzip() is None and len(z.namelist()) == len(set(z.namelist())) and not z.comment
            manifest = json.loads(z.read('manifest.json'))['files']
            assert set(manifest) == set(z.namelist()) - {'manifest.json'}
            for name, row in manifest.items():
                raw = z.read(name); assert SHA(raw) == row['sha256'] and len(raw) == row['size']
            zip_members += len(z.namelist())
    pcm = {n: p for n, p in files.items() if p.suffix == '.pcm'}
    rmt = {n: p for n, p in files.items() if p.suffix == '.rmt'}
    assert len(pcm) == 20 and all(p.stat().st_size > 0 and p.stat().st_size % 2 == 0 for p in pcm.values())
    assert len(rmt) == 9 and all(p.stat().st_size > 0 and p.stat().st_size % 4 == 0 for p in rmt.values())
    binary_uart = files['regression/full-r1/stackchan-servo/serial1.log'].read_bytes()
    assert binary_uart.startswith(b'\xff\xff')
    try:
        binary_uart.decode('utf-8')
    except UnicodeDecodeError:
        pass
    else:
        raise AssertionError('expected actual binary UART bytes, never sanitized UTF-8')
    full = J(ARC / 'regression/full-r1/summary.json')
    regression = J(ARC / 'review/regression/review.json')
    assert digest(ARC / 'regression/full-r1/summary.json') == regression['summary_sha256'] == '0d518bee9a554c91f185fe55d78728639aa604b5072fe3f94eb6f97a08ed5d91'
    assert Counter(r['status'] for r in full['results'].values()) == {'PASS': 67}
    assert Counter(c['status'] for r in full['results'].values() for c in r['checks']) == {'PASS': 274}
    assert regression['status'] == 'PASS_WITH_PROVENANCE_LIMITATIONS' and regression['strict_all_binary_ROM_full_start_end_freeze'] == 'NOT_ESTABLISHED'
    assert all(r['attempts'] == 1 and r['retry_used'] is False for r in full['results'].values())
    assert omitted['regression/full-r1/core2-imu/after.ppm']['sha256'] == regression['core2_imu_actual_marker']['ppm_sha256']
    with Image.open(ARC / 'regression/full-r1/core2-imu/after.png') as im:
        assert im.convert('RGB').getpixel((4, 4)) == (0, 255, 0)
    platform = J(ARC / 'candidate/root-platform-tests.json')
    platform_log = (ARC / 'candidate/root-platform-tests.log').read_text()
    assert platform['status'] == 'PASS' and platform['tests_run'] == 652 and not any(platform[k] for k in ('failures', 'errors', 'skipped'))
    assert 'Ran 652 tests' in platform_log and '\nOK\n' in platform_log and 'skipped=' not in platform_log
    external_calls, negatives = [], []
    def deny(*a, **k):
        external_calls.append('denied external/write operation'); raise AssertionError('forbidden operation')
    def reject(label, fn):
        try:
            fn()
        except (AssertionError, UnicodeDecodeError, FileNotFoundError):
            negatives.append(label)
        else:
            raise AssertionError('negative accepted: ' + label)
    with ExitStack() as stack:
        for obj, name in [(socket, 'socket'), (urllib.request, 'urlopen'), (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_output')]:
            stack.enter_context(patch.object(obj, name, deny))
        owner = module(ARC / 'audit_archive.py', 'owner_archive_audit')
        original_report = owner.audit(ARC, ROOT)
        (OUT / 'owner-original.json').write_text(json.dumps(original_report, indent=2) + '\n')
        with tempfile.TemporaryDirectory(prefix='fresh-', dir=OUT) as temporary:
            fresh = Path(temporary)
            copy = fresh / 'docs/evidence' / ARC.name
            shutil.copytree(ARC, copy)
            assert not (fresh / '.work').exists() and fingerprint(copy) == before
            clean_owner = module(copy / 'audit_archive.py', 'fresh_archive_audit')
            with patch.object(sys, 'argv', ['audit_archive.py', '--archive-dir', str(copy)]), patch.object(Path, 'write_bytes', deny), patch.object(Path, 'write_text', deny), redirect_stdout(io.StringIO()) as output:
                clean_owner.main()
            standalone = json.loads(output.getvalue()); assert standalone['status'] == 'PASS'
            assert fingerprint(copy) == before
            (OUT / 'owner-without-work.json').write_text(json.dumps(standalone, indent=2) + '\n')
            # All negative controls use only local temporary synthetic files or memory.
            fixtures = fresh / 'fixtures'; fixtures.mkdir()
            (fixtures / 'actual.txt').write_text('harmless\n'); (fixtures / 'alias.txt').symlink_to('actual.txt')
            (fixtures / 'actual-dir').mkdir(); (fixtures / 'alias-dir').symlink_to('actual-dir', target_is_directory=True)
            reject('source-file-symlink', lambda: clean_owner.safe(fixtures, 'alias.txt'))
            reject('source-ancestor-symlink', lambda: clean_owner.safe(fixtures, 'alias-dir/missing.txt'))
            for name in ('../escape', '/absolute', 'bad\\name'):
                reject('unsafe-relative:' + name, lambda name=name: clean_owner.relative(name))
            canary = json.dumps({'api' + '_key': 'SYNTHETIC_' + 'CANARY_NO_REAL_KEY'}).encode()
            reject('quoted-json-credential', lambda: clean_owner.scan_text(canary, 'synthetic'))
            reject('unknown-binary-UART-is-not-silently-decoded', lambda: clean_owner.inspect(b'\xff\xff', 'other/serial1.log', Counter()))
            reject('unaligned-PCM', lambda: clean_owner.inspect(b'\x01', 'test.pcm', Counter()))
            reject('unaligned-RMT', lambda: clean_owner.inspect(b'\x01\x02', 'test.rmt', Counter()))
            target = fresh / 'must-not-assemble'
            with patch.object(clean_owner, 'load', lambda p: {}):
                try:
                    clean_owner.assemble(fresh, target)
                except (KeyError, FileNotFoundError, AssertionError):
                    negatives.append('assemble-missing-terminal-gate-before-mkdir')
                else:
                    raise AssertionError('assembly ignored missing terminal gate')
            assert not target.exists()
    assert not external_calls and fingerprint(ARC) == before
    docs = ['docs/unit-integration-host-issues.md', 'docs/project-status.md', 'docs/project-backlog.md', 'docs/unit-agent-api.md', 'docs/plans/2026-10-25-unit-runtime-integration.md', 'docs/validation-ledger.md']
    report = {'status': 'PASS', 'scope': 'Fixed archive before root appends this archive review; copied/omitted original bytes, metadata/transport/nested SHA, binary UART/PCM/RMT, original ZIP and standalone default read-only audit. No new functional/hardware execution.',
        'reviewed_archive_fingerprint': before, 'archive_unchanged_after_review': True,
        'provenance_original_files_compared': len(provenance), 'exact_omission_original_files_compared': len(omitted), 'omission_reasons': dict(omission_reasons),
        'transported_markdown': len(transport), 'nested_checksum_entries': nested, 'zip_copies': zips, 'zip_members': zip_members,
        'pcm_files': len(pcm), 'pcm_bytes': sum(p.stat().st_size for p in pcm.values()), 'rmt_files': len(rmt), 'binary_servo_uart': {'bytes': len(binary_uart), 'sha256': SHA(binary_uart), 'raw_non_UTF8_preserved': True},
        'standalone_without_work': 'PASS; true archive copy in fresh checkout, default main, all filesystem write functions denied',
        'negative_controls': negatives, 'external_calls': external_calls, 'open_findings': [],
        'authority_docs_review': {'status': 'PASS_NO_SCOPE_OVERCLAIM_FOUND', 'files_sha256': {n: digest(ROOT / n) for n in docs},
            'boundaries': ['HOST20 closes only initialization route', 'HOST21 old66/67 and intermittent cause remain open', 'HOST22 records command overwrite without claiming actual launch trace', '67/274 is one independent full run; no targeted splice', 'A/B sampling about4s inside60s hold; no full-soak or hardware claim', 'ROM/C6 full-start and IR mutable Flash limitations retained; actual 652 zero-skip root log checked']},
        'hardware': 'NOT RUN'}
    (OUT / 'review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    (OUT / 'review.md').write_text('# PWM 归档与authority文档独审\n\nPASS，无未关闭问题。'+str(len(provenance))+'份保留文件及'+str(len(omitted))+'份omission逐项与原件hash/字节核对；'+str(len(transport))+'份Markdown仅改存储后缀，'+str(nested)+'条nested SHA解析成功。20份PCM、9份RMT与原非UTF8 servo UART完整保留；ZIP CRC/成员manifest正常。\n\n归档真实复制到无.work的新checkout，默认main在禁止任何write/API/进程的条件下audit PASS；负控均预期拒绝。原归档审前后指纹未变，本报告仅覆盖root加入此报告前的成品。\n\n六份authority文档未见越界：初始化route有界关闭；旧失败、偶发根因、原Buzzer/完整周期/硬件和provenance限制均保留；652零skip与原log相符。新完整67/274与Core2绿色marker来自原full轮，不拼接targeted。\n', encoding='utf-8')
    names = ['review_archive.py', 'review.json', 'review.md', 'owner-original.json', 'owner-without-work.json']
    (OUT / 'SHA256SUMS').write_text(''.join(digest(OUT / n) + '  ' + n + '\n' for n in names))
    print(json.dumps({'status': 'PASS', 'review_sha256': digest(OUT / 'review.json'), 'fingerprint': before, 'negative_controls': len(negatives)}, indent=2))

if __name__ == '__main__':
    main()
