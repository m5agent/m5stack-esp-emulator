#!/usr/bin/env python3
"""Offline PWM archive: default read-only audit; root alone calls --assemble after terminal full matrix."""
import argparse
import ast
from collections import Counter
import hashlib
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import stat
from urllib.parse import urlsplit
import zipfile
from PIL import Image

NAME = '2026-10-26-unit-pwm-route-d1ba'
BASELINE = '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
CANDIDATE = 'd1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff'
TREES = {
    '.work/unit-pwm-route-acceptance-20261026': 'acceptance',
    '.work/unit-pwm-route-candidate-20261026': 'candidate',
    '.work/unit-pwm-route-acceptance-independent-review-20261026': 'review/authoring',
    '.work/unit-pwm-route-live-independent-review-20261026': 'review/live',
    '.work/unit-pwm-route-regression-independent-review-20261026': 'review/regression',
    '.work/unit-pwm-route-regression-20261026': 'regression',
}
AUTHORED = {'README.md', 'audit_archive.py', 'copy-provenance.json', 'transport-paths.json',
            'omissions.json', 'machine-summary.json', 'audit-report.json', 'SHA256SUMS'}
FORBIDDEN = {'.bin', '.rom', '.elf', '.exe', '.dylib', '.so', '.o', '.a', '.pyc', '.img'}
NATIVE = {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
          b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
LIMITS = [
    'Virtual-device evidence only; hardware NOT RUN.',
    'Each A/B batch has eight fresh UART-before / real units-QOM / UART-after windows covering about four guest seconds, not a continuous 60-second soak or the first instant of initialization.',
    'Candidate output-transitions=1 counts observer property changes, not physical PWM pulses.',
    'The generic evidence ZIP QOM snapshot has a node limit; actual frozen UnitRegistry /units queries provide the per-window frequency and duty fields.',
    'Original Buzzer.once timer bug, full-cycle/latch/fade behavior, and physical acoustic/electrical equivalence remain OPEN.',
    'Full-matrix prepare records 388 source hashes and the expected Xtensa pin; no complete all-ROM/C6 full-start freeze exists. Cold-build, mid-run, C6-before and end observations retain their actual observation times and never recreate a full-start freeze.',
    'papercolor-rgb original summary.command is overwritten by the WS2812 checker command. Its launch is STATIC_RECONSTRUCTION from frozen source; functional assertions are separate. No actual per-case argv trace is claimed.',
    'Six IR cases have final mutable Flash image hashes different from their stdout initial-image hashes. The prepared source files remain byte-identical; no rewrite cause or immutable final-BIN claim is inferred.',
    'Older candidate platform logs retain 628 passed, 22 skipped and 2 stale-snapshot failures; the later root environment result is a separate 652 passed, zero skipped run.',
]
def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def load(path):
    return json.loads(path.read_bytes())

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def relative(name):
    assert isinstance(name, str) and name and '\\' not in name and '\x00' not in name
    p = PurePosixPath(name)
    assert not p.is_absolute() and '..' not in p.parts and p.as_posix() == name and name != '.'
    return name

def safe(base, name):
    relative(name)
    path = base / name
    for part in (path, *path.parents):
        if part == base:
            break
        assert not part.is_symlink(), 'symlink component: ' + name
    assert path.resolve().is_relative_to(base.resolve()) and path.resolve() != base.resolve()
    return path

def pixels(raw):
    with Image.open(io.BytesIO(raw)) as im:
        im.load()
        assert im.width > 0 and im.height > 0
        rgb = im.convert('RGB')
        return {'size': list(rgb.size), 'rgb_sha256': digest(rgb.tobytes())}

def scan_text(raw, locator):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise AssertionError('unclassified non-UTF8 payload: ' + locator) from exc
    patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                r'\bsk-[A-Za-z0-9_-]{24,}', r'(?i)\bBearer\s+[A-Za-z0-9_.~+/-]{24,}',
                r'(?i)(?<![\w-])(?P<q>[\x22\x27]?)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)(?P=q)\s*[=:]\s*[\x22\x27][^\x22\x27\r\n]{16,}[\x22\x27]',
                r'(?<![\da-fA-F])(?:[\da-fA-F]{2}:){5}[\da-fA-F]{2}(?![\da-fA-F])']
    for pattern in patterns:
        assert not re.search(pattern, text), 'credential/MAC candidate: ' + locator
    for match in re.finditer(r'https?://[^\s\x22\x27<>\\)]+', text):
        value = match.group()
        if any(c in value for c in '{}$'):
            continue
        host = urlsplit(value).hostname
        if not host:
            continue
        assert not host.endswith(('.local', '.lan')), 'private hostname: ' + locator
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            continue
        fixture = str(address) in ('10.0.2.2', '10.0.2.15') or any(address.version == n.version and address in n for n in map(ipaddress.ip_network, ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32')))
        assert address.is_global or address.is_loopback or fixture, 'private URL: ' + locator
    return text

def inspect(raw, locator, counts, inside=False):
    name = locator.rsplit('!', 1)[-1]
    assert PurePosixPath(name).suffix.lower() not in FORBIDDEN and raw[:4] not in NATIVE
    assert not raw.startswith((b'!<arch>\n', b'MZ')), 'native/archive executable: ' + locator
    if raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a', b'P6\n')) or raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        pixels(raw)
        counts['images_decoded'] += 1
    elif raw.startswith((b'PK\x03\x04', b'PK\x05\x06')):
        assert not inside, 'nested ZIP: ' + locator
        counts['zip_copies'] += 1
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            assert z.testzip() is None and not z.comment
            names = z.namelist()
            assert len(names) == len(set(names)) and 'manifest.json' in names
            for member in z.infolist():
                relative(member.filename.rstrip('/'))
                assert stat.S_IFMT(member.external_attr >> 16) != stat.S_IFLNK
                assert not member.flag_bits & 1, 'encrypted ZIP member'
                assert not member.is_dir(), 'unexpected directory member'
                inspect(z.read(member), locator + '!' + member.filename, counts, True)
                counts['zip_members'] += 1
            manifest = json.loads(z.read('manifest.json'))
            assert set(manifest['files']) == set(names) - {'manifest.json'}
            for member, row in manifest['files'].items():
                payload = z.read(member)
                assert digest(payload) == row['sha256'] and len(payload) == row['size']
    elif PurePosixPath(name).suffix == '.pcm':
        assert len(raw) > 0 and len(raw) % 2 == 0, 'invalid raw signed-16 PCM length'
        counts['pcm_files'] += 1
        counts['pcm_bytes'] += len(raw)
    elif PurePosixPath(name).suffix == '.rmt':
        assert len(raw) > 0 and len(raw) % 4 == 0, 'invalid raw RMT word length'
        counts['rmt_files'] += 1
    elif name.endswith('/stackchan-servo/serial1.log'):
        assert raw.startswith(b'\xff\xff') and len(raw) > 0, 'invalid captured servo UART prefix'
        scan_text(raw.decode('latin-1').encode('utf-8'), locator)
        counts['binary_servo_uart_files'] += 1
    else:
        text = scan_text(raw, locator)
        counts['utf8_payloads'] += 1
        if name.endswith('.py'):
            ast.parse(text, filename=locator)

def terminal(root):
    base = load(root / '.work/unit-pwm-route-acceptance-20261026/baseline-r1/result.json')
    candidate = load(root / '.work/unit-pwm-route-acceptance-20261026/candidate-r1/result.json')
    assert base['status'] == base['initialization_status'] == 'FAIL_REPRODUCED'
    assert candidate['status'] == candidate['initialization_status'] == 'PASS'
    assert base['finished_at'] and candidate['finished_at']
    full = root / '.work/unit-pwm-route-regression-20261026/full-r1/summary.json'
    assert full.is_file(), 'full matrix has no terminal summary; do not assemble or stop/restart it'
    matrix = load(full)
    assert matrix['generated_at'] and len(matrix['results']) == 67
    assert all(r['status'] not in ('PENDING', 'RUNNING', 'STARTED') for r in matrix['results'].values())
    review = load(root / '.work/unit-pwm-route-regression-independent-review-20261026/review.json')
    assert review['status'] not in ('PENDING', 'RUNNING'), 'wait for terminal regression independent review'
    return base, candidate, matrix

class Writer:
    def __init__(self, root, arc):
        self.root, self.arc = root, arc
        self.provenance = {'schema_version': 1, 'files': {}}
        self.transport = {'schema_version': 1, 'byte_changes': False, 'files': []}
        self.omissions = {'schema_version': 1, 'files': {}}
        if arc.exists():
            self.provenance = load(arc / 'copy-provenance.json')
            self.transport = load(arc / 'transport-paths.json')
            self.omissions = load(arc / 'omissions.json')

    def register(self, source_name, original, copy=True):
        source, original = safe(self.root, source_name), relative(original)
        assert source.is_file() and not source.is_symlink()
        raw = source.read_bytes()
        row = {'source': source_name, 'sha256': digest(raw), 'size': len(raw), 'byte_changes': False}
        forbidden = source.suffix.lower() in FORBIDDEN or raw[:4] in NATIVE or raw.startswith((b'!<arch>\n', b'MZ')) or source.name == '.DS_Store'
        if forbidden or '__pycache__' in source.parts:
            omission = row | {'reason': 'excluded firmware/ROM/flash/native/build/cache artifact', 'archive_original': original}
            assert original not in self.provenance['files']
            prior = self.omissions['files'].get(original)
            assert prior is None or prior == omission
            self.omissions['files'][original] = omission
            return
        if source.suffix.lower() == '.ppm':
            # A packed PPM can differ from the ordinary PNG; only omit when decoded RGB pixels match.
            png = source.with_name(source.name.replace('.packed.ppm', '.png')).with_suffix('.png')
            if png.is_file() and pixels(raw) == pixels(png.read_bytes()):
                png_dest = str(PurePosixPath(original).with_name(png.name))
                omission = row | {'archive_original': original, 'reason': 'redundant PPM; RGB pixels verified equal to retained PNG at assembly',
                                  'png': png_dest, 'png_sha256': digest(png.read_bytes()), 'decoded_rgb': pixels(raw)}
                prior = self.omissions['files'].get(original)
                assert prior is None or prior == omission
                self.omissions['files'][original] = omission
                return
        dest_name = original + '.txt' if original.endswith('.md') else original
        assert original not in self.omissions['files']
        prior = self.provenance['files'].get(dest_name)
        assert prior is None or prior == row, 'conflicting provenance: ' + dest_name
        self.provenance['files'][dest_name] = row
        if dest_name != original:
            transport = {'original': original, 'transport': dest_name, 'sha256': row['sha256'], 'size': row['size'], 'byte_changes': False}
            old = {r['original']: r for r in self.transport['files']}
            assert original not in old or old[original] == transport
            old[original] = transport
            self.transport['files'] = sorted(old.values(), key=lambda r: r['original'])
        inspect(raw, dest_name, Counter())
        if copy:
            dest = safe(self.arc, dest_name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            assert not dest.exists() or dest.read_bytes() == raw, 'never overwrite different evidence'
            dest.write_bytes(raw)

    def tree(self, source, dest, copy=True):
        folder = safe(self.root, source)
        assert folder.is_dir()
        for path in sorted(folder.rglob('*')):
            assert not path.is_symlink(), 'symlink source: ' + str(path)
            if path.is_file():
                self.register(path.relative_to(self.root).as_posix(), dest + '/' + path.relative_to(folder).as_posix(), copy)

    def flush(self):
        save(self.arc / 'copy-provenance.json', self.provenance)
        save(self.arc / 'transport-paths.json', self.transport)
        save(self.arc / 'omissions.json', self.omissions)

def populate(writer, copy):
    for source, dest in TREES.items():
        writer.tree(source, dest, copy)
    writer.register('.work/unit-runtime-build-pwm-route/build-manifest.json', 'build/build-manifest.json', copy)
    # Bounded regression source snapshot, checked against the actual pre-run source digest receipt.
    prepare = load(writer.root / '.work/unit-pwm-route-regression-20261026/prepare.json')
    for source, expected in prepare['source_sha256'].items():
        path = safe(writer.root, source)
        assert digest(path.read_bytes()) == expected, 'prepared regression source drift: ' + source
        writer.register(source, 'regression/frozen-source/' + source, copy)

def nested_checks(files, transport, omitted, read):
    count = 0
    for name in files:
        if PurePosixPath(name).name not in ('SHA256SUMS', 'HARNESS_SHA256SUMS') or name == 'SHA256SUMS':
            continue
        seen = set()
        for line in read(name).decode('utf-8').splitlines():
            if not line:
                continue
            expected, member = line.split('  ', 1)
            assert re.fullmatch('[0-9a-f]{64}', expected)
            relative(member)
            original = (PurePosixPath(name).parent / member).as_posix()
            assert original not in seen
            seen.add(original)
            target = transport.get(original, {}).get('transport', original)
            if target in files:
                assert digest(read(target)) == expected, 'nested SHA mismatch: ' + original
            else:
                assert original in omitted and omitted[original]['sha256'] == expected, 'unknown missing nested entry: ' + original
            count += 1
    return count

def make_summary(arc):
    base = load(arc / 'acceptance/baseline-r1/result.json')
    candidate = load(arc / 'acceptance/candidate-r1/result.json')
    full = load(arc / 'regression/full-r1/summary.json')['results']
    targeted = load(arc / 'regression/targeted-cores3-r1/summary.json')['results']
    return {'schema_version': 1, 'category': 'custom raw-PWM route initialization A/B and shared-controller repository regression',
            'baseline': {k: base[k] for k in ('status', 'session_id', 'firmware_sha256', 'source_cas_sha256', 'caller_request_sha256', 'runtime_provenance')},
            'candidate': {k: candidate[k] for k in ('status', 'session_id', 'firmware_sha256', 'source_cas_sha256', 'caller_request_sha256', 'runtime_provenance')},
            'sample_guest_bounds_ms': {n: [r['samples'][0]['before']['elapsed_ms'], r['samples'][-1]['after']['elapsed_ms']] for n, r in [('baseline', base), ('candidate', candidate)]},
            'full_matrix': {'cases': len(full), 'counts': dict(Counter(r['status'] for r in full.values())),
                            'assertions': dict(Counter(c['status'] for r in full.values() for c in r.get('checks', []))),
                            'all_single_attempt_no_retry': all(r.get('attempts') == 1 and r.get('retry_used') is False for r in full.values()),
                            'no_targeted_splice': True, 'all_ROM_C6_full_start_freeze': 'NOT AVAILABLE',
                            'papercolor_rgb_launch_evidence': 'STATIC_RECONSTRUCTION', 'actual_per_case_argv_trace': 'NOT AVAILABLE'},
            'targeted_cores3': {'cases': len(targeted), 'counts': dict(Counter(r['status'] for r in targeted.values()))},
            'hardware': 'NOT RUN', 'external_work_log': 'SKIPPED_BY_USER', 'limitations': LIMITS}

def assemble(root, arc):
    terminal(root)  # First, before creating any archive directory.
    assert not arc.exists(), 'fresh destination required'
    writer = Writer(root, arc)
    populate(writer, False)  # Complete privacy/type/hash preflight before any copy.
    tr = {r['original']: r for r in writer.transport['files']}
    nested_checks(writer.provenance['files'], tr, writer.omissions['files'], lambda n: safe(root, writer.provenance['files'][n]['source']).read_bytes())
    arc.mkdir(parents=True)
    for name, row in writer.provenance['files'].items():
        raw = safe(root, row['source']).read_bytes()
        assert digest(raw) == row['sha256'] and len(raw) == row['size'], 'source changed during assembly'
        path = safe(arc, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    writer.flush()
    save(arc / 'machine-summary.json', make_summary(arc))
    (arc / 'audit_archive.py').write_bytes(Path(__file__).read_bytes())
    (arc / 'README.md').write_text('# PWM route initialization evidence\n\nOriginal captured files are byte-preserved. Captured Markdown uses `.md.txt`; original nested checksum lists are resolved by `transport-paths.json` and exact-hash `omissions.json`. PCM and RMT data-plane inputs and outputs are retained. PPM is omitted only with a matching decoded RGB PNG witness. Firmware, ROM, Flash images and native/build artifacts are omitted by exact hash.\n\n' + '\n'.join('- ' + x for x in LIMITS) + '\n\nRun `python3 audit_archive.py --archive-dir .` from this archive for a read-only audit. It needs Pillow and no `.work`, device API, QEMU, compiler or guest execution. Optional `--repo-root` additionally compares any available original files.\n', encoding='utf-8')

def audit(arc, root=None, validate_manifest=True):
    assert arc.is_dir() and not arc.is_symlink()
    assert not any(p.is_symlink() for p in arc.rglob('*'))
    files = {p.relative_to(arc).as_posix(): p for p in arc.rglob('*') if p.is_file()}
    provenance = load(arc / 'copy-provenance.json')['files']
    transport = {r['original']: r for r in load(arc / 'transport-paths.json')['files']}
    omitted = load(arc / 'omissions.json')['files']
    assert set(files) - set(provenance) <= AUTHORED and set(provenance) <= set(files)
    assert {n for n in files if n.endswith('.md')} == {'README.md'}
    counts = Counter()
    for name, path in sorted(files.items()):
        relative(name)
        assert '__pycache__' not in path.parts
        if name not in ('audit-report.json', 'SHA256SUMS'):
            inspect(path.read_bytes(), name, counts)
    for name, row in provenance.items():
        relative(row['source'])
        raw = files[name].read_bytes()
        assert digest(raw) == row['sha256'] and len(raw) == row['size'] and row['byte_changes'] is False
        if root is not None:
            source = safe(root, row['source'])
            if source.is_file():
                assert source.read_bytes() == raw, 'available original drift: ' + name
    for original, row in transport.items():
        assert original.endswith('.md') and row['transport'] == original + '.txt' and original not in files
        raw = files[row['transport']].read_bytes()
        assert digest(raw) == row['sha256'] and len(raw) == row['size'] and row['byte_changes'] is False
    assert {n for n, r in provenance.items() if r['source'].endswith('.md')} == {r['transport'] for r in transport.values()}
    for original, row in omitted.items():
        relative(original)
        relative(row['source'])
        assert original == row['archive_original'] and original not in files
        assert re.fullmatch('[0-9a-f]{64}', row['sha256']) and row['size'] >= 0 and row['byte_changes'] is False
        if 'png' in row:
            png = files[row['png']].read_bytes()
            assert digest(png) == row['png_sha256'] and pixels(png) == row['decoded_rgb']
        if root is not None:
            source = safe(root, row['source'])
            if source.is_file():
                raw = source.read_bytes()
                assert digest(raw) == row['sha256'] and len(raw) == row['size']
                if 'png' in row:
                    assert pixels(raw) == row['decoded_rgb']
    counts['nested_checksum_entries'] = nested_checks(files, transport, omitted, lambda n: files[n].read_bytes())
    base = load(arc / 'acceptance/baseline-r1/result.json')
    candidate = load(arc / 'acceptance/candidate-r1/result.json')
    assert base['status'] == base['initialization_status'] == 'FAIL_REPRODUCED'
    assert candidate['status'] == candidate['initialization_status'] == 'PASS'
    for key in ('firmware_sha256', 'source_cas_sha256', 'caller_request_sha256'):
        assert base[key] == candidate[key]
    assert (arc / 'acceptance/baseline-r1/source-request.json').read_bytes() == (arc / 'acceptance/candidate-r1/source-request.json').read_bytes()
    for name, result, runtime, freq in [('baseline-r1', base, BASELINE, 0), ('candidate-r1', candidate, CANDIDATE, 2000)]:
        assert result['runtime_provenance']['runtime_binary_sha256'] == runtime
        assert result['source']['metadata']['effective_source_sha256'] == result['source_cas_sha256']
        assert len(result['samples']) == 8 and all(result['checks'].values())
        assert result['guest_audit']['pwm_constructors'] == 1 and result['guest_audit']['post_constructor_setters'] == 0
        assert all(s['frequency-hz'] == freq and s['duty-pct'] == 0 and 0 <= s['before']['elapsed_ms'] < s['after']['elapsed_ms'] < 60000 for s in result['samples'])
        assert result['cleanup']['pid_gone'] and result['cleanup']['flash_retained'] is False and result['cleanup']['active_sessions'] == 0
        assert digest((arc / 'acceptance' / name / 'evidence.zip').read_bytes()) == result['evidence_sha256']
    prepare = load(arc / 'regression/prepare.json')
    assert len(prepare['source_sha256']) == 388 and prepare['runtime_sha256'] == CANDIDATE and prepare['allow_retries'] is False
    for source, expected in prepare['source_sha256'].items():
        original = 'regression/frozen-source/' + source
        target = transport.get(original, {}).get('transport', original)
        assert digest(files[target].read_bytes()) == expected
    assert load(arc / 'machine-summary.json') == make_summary(arc)
    summary = load(arc / 'machine-summary.json')
    assert summary['full_matrix']['cases'] == 67
    build = (arc / 'build/build-manifest.json').read_bytes()
    assert digest(build) == load(arc / 'candidate/receipt.json')['build_manifest_sha256']
    tests = load(arc / 'candidate/root-platform-tests.json')
    assert tests['status'] == 'PASS' and tests['tests_run'] == 652 and not any(tests[k] for k in ('failures', 'errors', 'skipped'))
    if validate_manifest:
        listed = {}
        for line in files['SHA256SUMS'].read_text(encoding='utf-8').splitlines():
            expected, name = line.split('  ', 1)
            assert name not in listed and name in files and digest(files[name].read_bytes()) == expected
            listed[name] = expected
        assert set(listed) == set(files) - {'SHA256SUMS'}
    return {'schema_version': 1, 'status': 'PASS', 'scope': 'offline byte-provenance, MD transport, exact omissions, nested hashes, ZIP CRC/member manifests, images, UTF8/privacy and bounded result binding',
            'provenance_files': len(provenance), 'transported_markdown': len(transport), 'omitted_files': len(omitted),
            'checks': dict(counts), 'source_work_directories_required_for_audit': False,
            'full_matrix_functional_counts': summary['full_matrix']['counts'], 'hardware': 'NOT RUN', 'limitations': LIMITS}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path)
    parser.add_argument('--archive-dir', type=Path)
    parser.add_argument('--assemble', action='store_true')
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--add-source', action='append', default=[], metavar='REPO_RELATIVE=ARCHIVE_RELATIVE')
    parser.add_argument('--preflight', action='store_true', help='read sources only, including while matrix runs; never assembles')
    args = parser.parse_args()
    root = args.repo_root.resolve() if args.repo_root else None
    arc = args.archive_dir.resolve() if args.archive_dir else (root / 'docs/evidence' / NAME if root else Path(__file__).resolve().parent)
    assert not (args.assemble and (args.write or args.add_source or args.preflight))
    if args.preflight:
        assert root is not None and not args.write and not args.add_source
        writer = Writer(root, arc)
        assert not arc.exists(), 'source preflight is only for an unassembled archive'
        populate(writer, False)
        count = nested_checks(writer.provenance['files'], {r['original']: r for r in writer.transport['files']}, writer.omissions['files'], lambda n: safe(root, writer.provenance['files'][n]['source']).read_bytes())
        print(json.dumps({'status': 'SOURCE_PREFLIGHT_PASS', 'terminal_gate': 'NOT EVALUATED; preflight is not assembly authorization', 'files': len(writer.provenance['files']), 'omissions': len(writer.omissions['files']), 'nested_checksum_entries': count}))
        return
    if args.assemble:
        assert root is not None
        assemble(root, arc)
        print(json.dumps({'status': 'ASSEMBLED_BYTES_ONLY', 'next': 'root review README, then --write and read-only audit'}))
        return
    assert not args.add_source or args.write and root is not None
    if args.add_source:
        writer = Writer(root, arc)
        for item in args.add_source:
            writer.register(*item.split('=', 1))
        writer.flush()
    report = audit(arc, root, not args.write)
    if args.write:
        save(arc / 'audit-report.json', report)
        paths = sorted(p for p in arc.rglob('*') if p.is_file() and p != arc / 'SHA256SUMS')
        (arc / 'SHA256SUMS').write_text(''.join(digest(p.read_bytes()) + '  ' + p.relative_to(arc).as_posix() + '\n' for p in paths), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
