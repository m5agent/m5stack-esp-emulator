#!/usr/bin/env python3
"""Offline archive helper. Default audits only; --assemble is a root-only action.

This authoring agent must not invoke --assemble. All copies preserve bytes;
captured .md files are transported as .md.txt. Archive audit is self-contained.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import io
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit
import zipfile
from PIL import Image

NAME = '2026-10-26-unit-source-host-io-d1ba'
AUTHOR = '.work/unit-source-host-io-20261026'
AUTHOR_REVIEW = '.work/unit-source-host-io-independent-review-20261026'
LIVE_REVIEW = '.work/unit-source-host-io-live-independent-review-20261026'
HOSTS = ('atoms3r', 'sticks3', 'stopwatch')
UNITS = ('pir', 'dual-button', 'limit', 'key', 'rgb', 'fan', 'rs485', 'hub')
EXPECTED = {(h, u) for h in HOSTS for u in UNITS}
RUNTIME = 'd1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff'
GENERATION = 12
BATCHES = {'fan-r1': 'live-fan-r1', 'rest-r1': 'live-rest-r1'}
BAD = {'.pyc', '.bin', '.rom', '.elf', '.exe', '.dylib', '.so', '.o', '.a', '.dmp', '.core'}
MAGIC = {b'\x7fELF', b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
OWN = {'README.md', 'audit_archive.py', 'copy-provenance.json', 'transport-paths.json', 'omitted-source-snapshots.json', 'machine-summary.json', 'audit-report.json', 'SHA256SUMS'}
FIXED_COMMIT = 'cba4e3cda263bc15ed98bf9aa997e48e19f404cc'
OMIT = {
    'platform/tools/network_fabric.py': {'sha256': '608f6df7d0dcffec56fe702e922b1412cb189acdd586b46e826c121746125aef', 'size': 45221,
                                       'git_blob_oid': 'adf10856a4e76a2d1aae8f776e7d681d4052e203',
                                       'classification_evidence': {'constant': 'GUEST_MACS', 'source_lines': [27, 28], 'role': 'Static virtual network fabric fixture, not measured execution identity'}},
    'platform/tools/ble_probe.py': {'sha256': '2548151a414dc4ccc18d858d2d384c1a1ce0cb9d7f1d976646fb93f9c76d0757', 'size': 16955,
                                  'git_blob_oid': '01f5af6b7aa298ba23ffe39d534be0de99d644b1',
                                  'classification_evidence': {'constructors': ['LocalLink', 'Controller(network-lane-emu)', 'Controller(network-lane-phone)'], 'source_lines': [174, 202, 210], 'role': 'Static local virtual BLE controllers, not physical hardware or execution capture'}},
}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
load = lambda path: json.loads(path.read_bytes())


def need(value, message):
    if not value:
        raise RuntimeError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def safe(base, relative):
    text = str(relative)
    raw = PurePosixPath(text)
    need(not raw.is_absolute() and '..' not in raw.parts and '\\' not in text and raw.parts, 'unsafe relative archive/source path')
    lexical = base / text
    for path in (lexical, *lexical.parents):
        if path == base:
            break
        need(not path.is_symlink(), 'symlink in source/destination path')
    result = lexical.resolve()
    need(result.is_relative_to(base.resolve()) and result != base.resolve(), 'path escaped archive/source root')
    return result


def transport(name):
    return name + '.txt' if name.lower().endswith('.md') else name


def refuse_native(raw, name):
    need(PurePosixPath(name).suffix.lower() not in BAD and raw[:4] not in MAGIC and not raw.startswith(b'MZ'), 'firmware/native/compiled payload forbidden: ' + name)


def privacy_candidates(text, locator):
    findings = []
    patterns = {'private-key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                'API-token': r'\bsk-[A-Za-z0-9_-]{24,}', 'Bearer-token': r'(?i)\bBearer\s+[A-Za-z0-9_.~+/-]{24,}',
                'credential-literal': r'(?i)(?<![\w-])(?P<q>[\x22\x27]?)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)(?P=q)\s*[=:]\s*[\x22\x27][^\x22\x27\r\n]{16,}[\x22\x27]',
                'MAC-literal': r'(?<![\da-fA-F])(?:[\da-fA-F]{2}:){5}[\da-fA-F]{2}(?![\da-fA-F])'}
    for kind, pattern in patterns.items():
        if re.search(pattern, text):
            findings.append({'kind': kind, 'locator': locator, 'raw_value_printed': False})
    for match in re.finditer(r'https?://[^\s\x22\x27<>\\)]+', text):
        value = match.group()
        if any(c in value for c in '{}$'):
            continue
        host = urlsplit(value).hostname
        if not host:
            continue
        private = host.endswith(('.local', '.lan'))
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None:
            fixture = str(address) in ('10.0.2.2', '10.0.2.15') or any(address.version == network.version and address in network for network in map(ipaddress.ip_network, ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24', '2001:db8::/32')))
            private = private or not (address.is_global or address.is_loopback or fixture)
        if private:
            findings.append({'kind': 'private-URL-candidate', 'locator': locator, 'raw_value_printed': False})
    return findings


def exact_omission(source, target, raw):
    """Only two approved indirect source-snapshot payloads; never real captures."""
    for dependency, specification in OMIT.items():
        suffix = '/source-snapshot/' + dependency + '.txt'
        if source.endswith(suffix) and target.endswith(suffix):
            blob = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
            need(sha(raw) == specification['sha256'] and len(raw) == specification['size'] and blob == specification['git_blob_oid'], 'approved indirect snapshot changed; cannot omit unknown bytes')
            return {'source': source, 'omitted_archive_path': target, 'dependency': dependency,
                    **specification, 'fixed_git_commit': FIXED_COMMIT, 'git_show_reference': FIXED_COMMIT + ':' + dependency,
                    'byte_changes': False, 'bytes_in_archive': False,
                    'reason': 'Exact omission requested by root to avoid newly copying static virtual MAC literals. Original files unchanged; all caller/driver/runtime HTTP/ZIP/serial remain byte-exact.'}
    return None


def omission_bindings(root, plan, omissions):
    """Keep original freeze and nested-checksum entries, without source bytes."""
    by_source = {row['source']: row for row in omissions.values()}
    for row in omissions.values():
        source_parent = row['source'].rsplit('/source-snapshot/', 1)[0]
        archive_parent = row['omitted_archive_path'].rsplit('/source-snapshot/', 1)[0]
        freeze_source = source_parent + '/tooling-source-freeze.json'
        freeze = load(safe(root, freeze_source))
        need(freeze[row['dependency']] == row['sha256'], 'omitted snapshot is not bound to original source freeze')
        row['original_freeze_entry'] = {'manifest_source': freeze_source, 'manifest_archive': archive_parent + '/tooling-source-freeze.json',
                                        'entry_name': row['dependency'], 'sha256': freeze[row['dependency']]}
        row['original_nested_checksum_entries'] = []
    for source, target in plan:
        if not Path(source).name.endswith('SHA256SUMS'):
            continue
        manifest = safe(root, source)
        for line in manifest.read_text().splitlines():
            if not line:
                continue
            digest, member = line.split('  ', 1)
            reference = (manifest.parent / member).resolve()
            if not reference.is_relative_to(root.resolve()):
                continue
            original = reference.relative_to(root).as_posix()
            if original in by_source:
                row = by_source[original]
                need(digest == row['sha256'], 'nested checksum differs from omitted source content hash')
                row['original_nested_checksum_entries'].append({'manifest_source': source, 'manifest_archive': transport(target),
                                                                 'entry_name': member, 'sha256': digest, 'original_entry_line': line})
    for row in omissions.values():
        row['nested_checksum_entry_status'] = 'ORIGINAL_ENTRIES_PRESERVED' if row['original_nested_checksum_entries'] else 'NO_NESTED_CHECKSUM_ENTRY_WAS_PRODUCED_IN_ORIGINAL_PARTIAL_ATTEMPT'
        if any('/' + batch + '/' in row['source'] for batch in BATCHES.values()):
            need(row['original_nested_checksum_entries'], 'selected terminal batch omission lacks original nested checksum entry')


def terminal_preflight(root, final=False):
    pending, cases, contexts, freezes = [], [], {}, {}
    for target, source in BATCHES.items():
        batch = root / AUTHOR / source
        if not (batch / 'batch-result.json').is_file():
            pending.append(source + ': no terminal batch result')
            continue
        result, prepared = load(batch / 'batch-result.json'), load(batch / 'prepared.json')
        desired = {(h, 'fan') for h in HOSTS} if target == 'fan-r1' else {(h, u) for h in HOSTS for u in UNITS if u != 'fan'}
        need(result['status'] == 'PASS' and not result['bridge_close_error'], 'selected batch is not terminal PASS: ' + source)
        need(prepared['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC' and len(prepared['cases']) == len(desired), 'batch root source-context/count differs')
        need({(r['device_id'], r['unit_id']) for r in prepared['cases']} == desired, 'selected Fan3/rest21 topology differs')
        contexts[target] = prepared['source_context_commit']
        freezes[target] = load(batch / 'tooling-source-freeze.json')
        for row in prepared['cases']:
            case = load(batch / row['device_id'] / row['unit_id'] / 'result.json')
            need(case['status'] == 'PASS' and all(case['checks'].values()) and case['source_context_commit'] == contexts[target], 'selected case incomplete')
            need(case['runtime_provenance']['runtime_binary_sha256'] == RUNTIME and case['runtime_provenance']['status'] == 'VERIFIED' and case['runtime_provenance']['worker_generation'] == case['expected_worker_generation'] == GENERATION, 'selected case runtime/worker generation identity differs')
            cases.append({'batch': target, 'prepared': row, 'result': case})
    pairs = {(c['result']['device_id'], c['result']['unit_id']) for c in cases}
    need(len(pairs) == len(cases), 'Fan/host case counted twice')
    author = load(root / AUTHOR_REVIEW / 'review.json')
    need(author['status'] == 'PASS_OFFLINE_ONLY' and author['check_count'] == 114 and not author['open_findings'] and not author['unexpected_calls'], '114-check authoring review incomplete')
    selfcheck = load(root / AUTHOR / 'selfcheck-r4/offline-selfcheck.json')
    need(selfcheck['status'] == 'PASS_OFFLINE_ONLY' and selfcheck['check_count'] == 61 and selfcheck['API_network_browser_subprocess_guest_calls'] == 0, '61-check authoring selfcheck incomplete')
    final_review = root / LIVE_REVIEW / 'final24-review.json'
    visual_review = root / LIVE_REVIEW / 'native-visual-final24.json'
    if not final_review.is_file():
        pending.append('final24 independent raw live review absent')
    if not visual_review.is_file():
        pending.append('actual 24 native visual reviews absent')
    if final_review.is_file():
        live = load(final_review)
        need(live['status'] == 'PASS' and live['reviewed_combinations'] == 24 and not live['pending_combinations'] and live['API_browser_guest_subprocess_calls_during_review'] == 0, 'final live review not complete')
        need({(r['device_id'], r['unit_id']) for r in live['cases']} == EXPECTED and len(live['cases']) == 24, 'final independent live selection differs')
    if visual_review.is_file():
        visual = load(visual_review)
        need(visual['reviewed_native_frames'] == 24 and len(visual['frames']) == 24 and {(r['device_id'], r['unit_id']) for r in visual['frames']} == EXPECTED, 'native visual review not exactly24')
        need(all(r['actual_view_image_inspection'] is True and r['readability'] == 'READABLE_CAPTURED_NATIVE_FRAME_ONLY' and r['clipping_observed'] is False for r in visual['frames']), 'native captured-frame visual acceptance incomplete')
    dependency_equal = None
    if len(freezes) == 2:
        dependency_equal = freezes['fan-r1'] == freezes['rest-r1']
        need(dependency_equal, 'batch source dependency inventory/bytes differ; do not waive caller/protocol/source binding')
    pending += [f'missing selected case: {h}/{u}' for h, u in sorted(EXPECTED - pairs)]
    if final:
        need(not pending and len(cases) == 24, '24 terminal source IO cases/reviews required before assemble: ' + '; '.join(pending))
    return {'status': 'READY_FOR_ROOT_ASSEMBLE' if not pending else 'PENDING', 'reviewed_selected_cases': len(cases),
            'expected_selected_cases': 24, 'source_context_by_batch': contexts, 'same_source_dependency_bytes': dependency_equal,
            'pending': pending, 'cases': cases}


def source_plan(root, require_all=True):
    """Preserve all authoring/failure attempts; selected success batches stay distinct."""
    plan = []
    def tree(source, target):
        base = safe(root, source)
        if not base.is_dir() and not require_all:
            return
        need(base.is_dir(), 'missing source evidence tree: ' + source)
        for path in sorted(base.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store' and path.suffix != '.pyc':
                plan.append((path.relative_to(root).as_posix(), target + '/' + path.relative_to(base).as_posix()))
    for target, source in BATCHES.items():
        tree(AUTHOR + '/' + source, 'batches/' + target)
    author = root / AUTHOR
    for path in sorted(author.iterdir()):
        if path.name in BATCHES.values() or path.name in ('__pycache__', '.DS_Store'):
            continue
        source = path.relative_to(root).as_posix()
        if path.is_dir():
            tree(source, ('batches/attempts/' if path.name.startswith('live-') else 'harness/authoring-attempts/') + path.name)
        elif path.suffix in ('.log', '.out', '.err'):
            plan.append((source, 'verification/logs/' + path.name))
        elif path.name == 'verification-commands.json':
            plan.append((source, 'verification/actual-commands.json'))
        else:
            plan.append((source, 'harness/' + path.name))
    tree(AUTHOR_REVIEW, 'review/authoring')
    tree(LIVE_REVIEW, 'review/live')
    helper_review = root / '.work/unit-source-host-io-archive-independent-review-20261026'
    if helper_review.is_dir():
        for path in sorted(helper_review.iterdir()):
            if path.is_file() and path.suffix != '.pyc' and path.name != '.DS_Store':
                plan.append((path.relative_to(root).as_posix(), 'verification/archive-helper-independent-review/' + path.name))
    return plan


def copy_sources(root, archive, plan, provenance, transports, omissions=None):
    omissions = omissions if omissions is not None else {}
    for source_name, target_name in plan:
        source = safe(root, source_name)
        need(source.is_file(), 'missing source evidence file: ' + source_name)
        raw = source.read_bytes()
        refuse_native(raw, source_name)
        omission = exact_omission(source_name, target_name, raw)
        if omission:
            need(target_name not in provenance and not (archive / target_name).exists(), 'omitted snapshot unexpectedly present')
            omissions[target_name] = omission
            continue
        name = transport(target_name)
        target = safe(archive, name)
        target.parent.mkdir(parents=True, exist_ok=True)
        need(not target.exists() or target.read_bytes() == raw, 'refuse to overwrite different archived evidence: ' + name)
        target.write_bytes(raw)
        record = {'source': source_name, 'sha256': sha(raw), 'size': len(raw), 'byte_changes': False}
        need(name not in provenance or provenance[name] == record, 'provenance destination collision')
        provenance[name] = record
        if name != target_name:
            transports[target_name] = {'original': target_name, 'transport': name, 'sha256': sha(raw), 'size': len(raw), 'byte_changes': False}


def command_receipt_valid(value, contexts, required_batches=('fan-r1', 'rest-r1')):
    """Root's explicit transcription of actual tool calls; not an OS exec trace."""
    need(value.get('recording_type') == 'root transcription of actual exec_command tool calls; not OS exec trace' and isinstance(value.get('calls'), list), 'actual root tool-call transcription required')
    for batch in required_batches:
        source = BATCHES[batch]
        for mode in ('--execute', '--check'):
            matches = []
            for item in value['calls']:
                text = ' '.join(item.get('argv', []))
                if source in text and mode in text and type(item.get('exec_session_id')) is int and item['exec_session_id'] > 0 and item.get('observed_exit_code') == 0:
                    matches.append(item)
                    need(item.get('stdout_log'), 'actual command transcription needs original stdout log')
                    if mode == '--execute':
                        need(contexts[batch] in text and RUNTIME in text, 'actual execution command not pinned to batch exact source HEAD/runtime')
            need(matches, 'successful actual command missing: ' + source + ' ' + mode)


def sync_receipt_valid(value, contexts):
    """Validate root's actual saved fetch/merge schema, without invented fields."""
    required = {'started_at', 'finished_at', 'block_commit', 'head_after', 'origin_main', 'fetch_exit_code',
                'merge_exit_code', 'fetch_log', 'merge_log', 'merge_output', 'worktree_clean_after'}
    need(required <= set(value), 'actual post-PWM sync receipt schema incomplete')
    need(value['block_commit'] == value['head_after'] == contexts['rest-r1'] and contexts['fan-r1'] == FIXED_COMMIT,
         'actual sync does not bind distinct exact Fan/rest contexts')
    need(value['fetch_exit_code'] == value['merge_exit_code'] == 0 and value['worktree_clean_after'] is True and
         value['merge_output'].strip() == 'Already up to date.' and re.fullmatch('[0-9a-f]{40}', value['origin_main']),
         'actual fetch/merge exit/cleanliness/output fields do not establish recorded sync')


def assemble(root, archive, command_receipt, sync_receipt, additions):
    need(not archive.exists(), 'root must choose fresh archive; existing evidence is immutable')
    state = terminal_preflight(root, final=True)
    need(command_receipt and sync_receipt, 'root supplies real command and fetch/merge receipts')
    commands = load(safe(root, command_receipt))
    command_receipt_valid(commands, state['source_context_by_batch'])
    sync = load(safe(root, sync_receipt))
    sync_receipt_valid(sync, state['source_context_by_batch'])
    archive.mkdir(parents=True)
    provenance, transports, omissions = {}, {}, {}
    plan = source_plan(root)
    plan += [(command_receipt, 'verification/actual-commands.json'), (sync_receipt, 'verification/post-fan-sync.json')]
    plan += [(sync[key], 'verification/sync/' + Path(sync[key]).name) for key in ('fetch_log', 'merge_log')]
    plan += additions
    copy_sources(root, archive, plan, provenance, transports, omissions)
    omission_bindings(root, plan, omissions)
    sessions = []
    for item in state['cases']:
        result = item['result']
        name = f"batches/{item['batch']}/{result['device_id']}/{result['unit_id']}/result.json"
        sessions.append({k: result[k] for k in ('device_id', 'unit_id', 'session_id', 'firmware_sha256', 'base_firmware_sha256', 'source_cas_sha256', 'source_context_commit')} |
                        {'status': result['status'], 'batch': item['batch'], 'result': name, 'result_sha256': sha((archive / name).read_bytes()),
                         'runtime_sha256': result['runtime_provenance']['runtime_binary_sha256'], 'worker_generation': result['runtime_provenance']['worker_generation']})
    save(archive / 'copy-provenance.json', {'schema_version': 1, 'files': provenance})
    save(archive / 'transport-paths.json', {'schema_version': 1, 'byte_changes': False, 'files': sorted(transports.values(), key=lambda x: x['original'])})
    save(archive / 'omitted-source-snapshots.json', {'schema_version': 1, 'bytes_omitted_not_redacted': True,
                                                   'unique_payloads': 2, 'fixed_git_commit': FIXED_COMMIT,
                                                   'files': omissions, 'scope': 'Only exact copies of two indirect static-fixture source snapshots; source closure bytes are not fully contained. Recheck fixed Git blobs when source review is required.'})
    save(archive / 'machine-summary.json', {'schema_version': 1, 'status': 'PASS', 'functional_pass_sessions': 24,
                                         'runtime_sha256': RUNTIME, 'source_context_by_batch': state['source_context_by_batch'],
                                         'worker_generation': GENERATION,
                                         'same_source_dependency_bytes': True, 'sessions': sessions, 'hardware': 'NOT RUN',
                                         'source_closure_bytes_in_archive': 'EXCEPT_TWO_PINNED_INDIRECT_STATIC_FIXTURE_SNAPSHOTS',
                                         'omitted_indirect_snapshot_copies': len(omissions), 'omitted_unique_payloads': 2,
                                         'authoring_selfcheck_count': 61, 'authoring_independent_check_count': 114,
                                         'scope': 'Exact three-host eight-Unit source API paths. Fan3/rest21 are disjoint and can have different exact HEADs with identical dependency bytes. Original IR/Buzzer/ADC/hardware/full-runtime claims remain separate.'})
    (archive / 'audit_archive.py').write_bytes(Path(__file__).read_bytes())
    (archive / 'README.md').write_text('# 三主机 Unit source API 验证证据\n\n'
        'AtomS3R / StickS3 / StopWatch × PIR、DualButton、Limit、Key、RGB、Fan、RS485、HUB，'
        '共 24 个明确的 virtual-device source API 路径。Fan3 与其余21例分批执行，'
        '每批准确 source HEAD 见 machine-summary.json；源码依赖字节保持相同，runtime 均绑定 d1ba。\n\n'
        'batches/fan-r1 和 batches/rest-r1 保留原 HTTP、caller、source pin、PID/worker、UART/QOM、'
        '产品 DOM/HTTP、ZIP-before-stop、native frame 和 history/Flash/idle 清理证据。'
        'harness 保留作者 freeze、61项自检及全部作者尝试；review/authoring 保留114项独审，'
        'review/live 保留独立实际证据和24张 native PNG 的逐张审阅。失败尝试保留，不计入24 PASS。\n\n'
        '源码作者阶段的旧 runtime 默认值、离线 PENDING 与历史失败均为原始过程证据，不继承为实际 PASS。'
        '每文件来源和 SHA 见 copy-provenance.json。除本 README 外，捕获的 Markdown 改名 .md.txt，'
        '内容字节不变，映射见 transport-paths.json。verification 保存 root 实际命令输出、工具调用的事后准确转录与同步 receipt；不把转录称为 OS exec trace。\n\n'
        '为避免新增拷贝 MAC literal，只精确省略 network_fabric.py 与 ble_probe.py 两个间接依赖的 '
        'source-snapshot 复制件；原件不动，也不清洗字节。全部 caller/driver/真实 HTTP/ZIP/serial 均保留。'
        '因此本包不声称 source closure 全量字节入包。omitted-source-snapshots.json 保留每份省略的来源、'
        'SHA/size、原 freeze/嵌套 SHA 条目、固定 cba Git blob oid 和 git-show reference。'
        '两处属于静态虚拟 fixture，不是执行采集；需要源码复查时，从固定仓内 commit 用 git show '
        '读取并核对 SHA256/size/Git blob oid。独立 audit 对这些条目验证 hash/reference，一律承认没有源码字节。\n\n'
        '可读性只适用于实际捕获 PNG；不代表连续全帧保真。原 IR/Buzzer 风险、ADC fixture/oracle、'
        '其它 Unit/拓扑、共享 runtime 完整回归以及硬件、电气、声学结果均不由本包关闭。\n\n'
        '独立离线复核：`python3 audit_archive.py --repo-root <repo>`。默认只读，不调用 API/guest/子进程。\n', encoding='utf-8')


def audit(root, archive, check_manifest=True):
    need(archive.is_dir() and not any(p.is_symlink() for p in archive.rglob('*')), 'archive absent or contains symlink')
    files = {p.relative_to(archive).as_posix(): p for p in archive.rglob('*') if p.is_file()}
    provenance = load(archive / 'copy-provenance.json')['files']
    transports = {r['original']: r for r in load(archive / 'transport-paths.json')['files']}
    omission_manifest = load(archive / 'omitted-source-snapshots.json')
    omissions = omission_manifest['files']
    need(set(files) - set(provenance) <= OWN and {name for name in files if name.lower().endswith('.md')} == {'README.md'}, 'unexpected generated file or untransported Markdown')
    for name, record in provenance.items():
        raw = safe(archive, name).read_bytes()
        need(sha(raw) == record['sha256'] and len(raw) == record['size'] and record['byte_changes'] is False, 'copy provenance hash/length differs')
        original = safe(root, record['source'])
        if original.is_file():
            need(original.read_bytes() == raw, 'archive differs from available source evidence')
    for original, record in transports.items():
        need(original not in files and record['transport'] in provenance and sha(safe(archive, record['transport']).read_bytes()) == record['sha256'] and record['byte_changes'] is False, 'Markdown transport changed bytes')
    need(omission_manifest['fixed_git_commit'] == FIXED_COMMIT and omission_manifest['unique_payloads'] == 2 and {r['dependency'] for r in omissions.values()} == set(OMIT), 'omitted source payload scope differs')
    for name, record in omissions.items():
        specification = OMIT[record['dependency']]
        need(name not in files and name not in provenance and record['bytes_in_archive'] is False and record['byte_changes'] is False and record['fixed_git_commit'] == FIXED_COMMIT and record['git_show_reference'] == FIXED_COMMIT + ':' + record['dependency'], 'omitted snapshot unexpectedly present or reference changed')
        need(all(record[key] == specification[key] for key in ('sha256', 'size', 'git_blob_oid', 'classification_evidence')), 'omitted exact content/source classification differs')
        suffix = '/source-snapshot/' + record['dependency'] + '.txt'
        need(name.endswith(suffix) and record['source'].endswith(suffix), 'omission escaped exact indirect source-snapshot copies')
        binding = record['original_freeze_entry']
        need(load(safe(archive, binding['manifest_archive']))[binding['entry_name']] == binding['sha256'] == record['sha256'], 'omitted original freeze binding differs')
        for entry in record['original_nested_checksum_entries']:
            need(entry['original_entry_line'] in safe(archive, entry['manifest_archive']).read_text().splitlines() and entry['original_entry_line'] == entry['sha256'] + '  ' + entry['entry_name'] and entry['sha256'] == record['sha256'], 'recorded omitted nested SHA entry differs from original archived manifest')
        original = safe(root, record['source'])
        if original.is_file():
            raw = original.read_bytes()
            need(sha(raw) == record['sha256'] and len(raw) == record['size'] and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == record['git_blob_oid'], 'available omitted original differs from fixed Git blob pin')
    counters = {'images_decoded': 0, 'ZIP_copies': 0, 'ZIP_members': 0, 'UTF8_payloads': 0, 'nested_checksum_entries': 0}
    privacy_findings = []
    unique_zip = set()
    def inspect(raw, locator, in_zip=False):
        refuse_native(raw, locator)
        if raw.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff', b'GIF87a', b'GIF89a')) or raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
                need(image.width > 0 and image.height > 0, 'invalid image')
            counters['images_decoded'] += 1
        elif raw.startswith((b'PK\x03\x04', b'PK\x05\x06')):
            need(not in_zip, 'nested ZIP payload not allowed')
            counters['ZIP_copies'] += 1
            unique_zip.add(sha(raw))
            with zipfile.ZipFile(io.BytesIO(raw)) as archive_zip:
                need(archive_zip.testzip() is None and len(archive_zip.namelist()) == len(set(archive_zip.namelist())) and not archive_zip.comment, 'ZIP CRC/membership/comment differs')
                for member in archive_zip.infolist():
                    safe(archive, member.filename)
                    need((member.external_attr >> 16) & 0o170000 != 0o120000, 'ZIP symlink forbidden')
                    counters['ZIP_members'] += 1
                    if not member.is_dir():
                        inspect(archive_zip.read(member), locator + '!' + member.filename, True)
                manifest = json.loads(archive_zip.read('manifest.json'))
                need(set(manifest['files']) == set(archive_zip.namelist()) - {'manifest.json'}, 'ZIP manifest inventory differs')
                for name, record in manifest['files'].items():
                    payload = archive_zip.read(name)
                    need(sha(payload) == record['sha256'] and len(payload) == record['size'], 'ZIP manifest SHA/size differs')
        else:
            text = raw.decode('utf-8')
            need('\x00' not in text, 'unrecognized binary/NUL payload')
            counters['UTF8_payloads'] += 1
            privacy_findings.extend(privacy_candidates(text, locator))
    for name, path in files.items():
        need('__pycache__' not in path.parts and path.suffix.lower() not in BAD, 'compiled/cache file in archive')
        if name not in ('audit-report.json', 'SHA256SUMS'):
            inspect(path.read_bytes(), name)
        if path.suffix == '.py':
            ast.parse(path.read_text(), filename=name)
        if path != archive / 'SHA256SUMS' and (path.name.endswith('SHA256SUMS') or path.name == 'SHA256SUMS'):
            for line in path.read_text().splitlines():
                if not line:
                    continue
                digest, member = line.split('  ', 1)
                original = (path.parent / member).relative_to(archive).as_posix()
                target = transports.get(original, {}).get('transport', original)
                if target in omissions:
                    record = omissions[target]
                    need(digest == record['sha256'] and any(entry['manifest_archive'] == name and entry['entry_name'] == member and entry['sha256'] == digest for entry in record['original_nested_checksum_entries']), 'omitted nested checksum original entry missing/different')
                else:
                    need(sha(safe(archive, target).read_bytes()) == digest, 'nested checksum/transport differs: ' + original)
                counters['nested_checksum_entries'] += 1
    need(not privacy_findings, 'privacy candidates require exact evidence review; no silent redact/allowlist: ' + json.dumps(privacy_findings[:8]))
    summary = load(archive / 'machine-summary.json')
    need(summary['status'] == 'PASS' and summary['functional_pass_sessions'] == 24 and summary['same_source_dependency_bytes'] is True and summary['runtime_sha256'] == RUNTIME, 'machine summary scope differs')
    need(len(summary['sessions']) == len({r['session_id'] for r in summary['sessions']}) == 24 and {(r['device_id'], r['unit_id']) for r in summary['sessions']} == EXPECTED, '24 unique session/case set differs')
    contexts = summary['source_context_by_batch']
    freezes = {}
    for target in BATCHES:
        prepared = load(archive / 'batches' / target / 'prepared.json')
        need(prepared['source_context_stage'] == 'ROOT_SUPPLIED_POST_SYNC' and prepared['source_context_commit'] == contexts[target], 'batch source HEAD differs')
        freezes[target] = load(archive / 'batches' / target / 'tooling-source-freeze.json')
    need(freezes['fan-r1'] == freezes['rest-r1'], 'batch source dependency bytes differ')
    for row in summary['sessions']:
        result_path = safe(archive, row['result'])
        result = load(result_path)
        need(sha(result_path.read_bytes()) == row['result_sha256'] and result['status'] == row['status'] == 'PASS' and all(result['checks'].values()), 'archived selected result differs')
        need(all(result[k] == row[k] for k in ('device_id', 'unit_id', 'session_id', 'firmware_sha256', 'base_firmware_sha256', 'source_cas_sha256', 'source_context_commit')), 'archived result/source pin differs')
        need(row['source_context_commit'] == contexts[row['batch']] and result['runtime_provenance']['runtime_binary_sha256'] == RUNTIME and result['runtime_provenance']['worker_generation'] == row['worker_generation'] == GENERATION, 'archived exact source/runtime/worker differs')
        need(result['cleanup']['pid_gone'] and result['cleanup']['flash_retained'] is False and result['cleanup']['health_active_sessions'] == 0, 'archived PID/Flash/idle cleanup incomplete')
    command_receipt_valid(load(archive / 'verification/actual-commands.json'), contexts)
    for call in load(archive / 'verification/actual-commands.json')['calls']:
        need(any(row['source'] == call['stdout_log'] for row in provenance.values()), 'root command stdout log not preserved by provenance')
    sync = load(archive / 'verification/post-fan-sync.json')
    sync_receipt_valid(sync, contexts)
    need(all(any(record['source'] == sync[key] for record in provenance.values()) for key in ('fetch_log', 'merge_log')), 'actual fetch/merge logs not preserved')
    live = load(archive / 'review/live/final24-review.json')
    visual = load(archive / 'review/live/native-visual-final24.json')
    need(live['status'] == 'PASS' and live['reviewed_combinations'] == visual['reviewed_native_frames'] == 24 and not live['pending_combinations'], 'final live/native review incomplete')
    need({(r['device_id'], r['unit_id']) for r in live['cases']} == {(r['device_id'], r['unit_id']) for r in visual['frames']} == EXPECTED, 'independent live/native selections differ')
    for frame in visual['frames']:
        batch = 'fan-r1' if frame['unit_id'] == 'fan' else 'rest-r1'
        need(frame['actual_view_image_inspection'] is True and frame['readability'] == 'READABLE_CAPTURED_NATIVE_FRAME_ONLY' and frame['clipping_observed'] is False and sha((archive / 'batches' / batch / frame['device_id'] / frame['unit_id'] / 'frame.png').read_bytes()) == frame['sha256'], 'native visual acceptance not bound to actual captured PNG')
    authoring = load(archive / 'review/authoring/review.json')
    selfcheck = load(archive / 'harness/authoring-attempts/selfcheck-r4/offline-selfcheck.json')
    need(authoring['status'] == 'PASS_OFFLINE_ONLY' and authoring['check_count'] == 114 and selfcheck['status'] == 'PASS_OFFLINE_ONLY' and selfcheck['check_count'] == 61, 'authoring review/selfcheck scope differs')
    if check_manifest:
        listed = {}
        for line in (archive / 'SHA256SUMS').read_text().splitlines():
            digest, name = line.split('  ', 1)
            need(name not in listed and sha(safe(archive, name).read_bytes()) == digest, 'top-level archive checksum differs')
            listed[name] = digest
        need(set(listed) == set(files) - {'SHA256SUMS'}, 'top-level archive inventory differs')
    return {'schema_version': 1, 'status': 'PASS', 'functional_pass_sessions': 24, 'hardware': 'NOT RUN',
            'scope': 'Offline exact-byte provenance/MD transport/ZIP CRC+manifest/nested SHA/images/privacy/source-context+runtime pin audit; no API/process/guest.',
            'provenance_files': len(provenance), 'transported_Markdown_files': len(transports), 'unique_ZIP_payloads': len(unique_zip),
            'source_context_by_batch': contexts, 'same_source_dependency_bytes': True, 'source_work_directories_required': False,
            'source_closure_bytes_in_archive': 'EXCEPT_TWO_PINNED_INDIRECT_STATIC_FIXTURE_SNAPSHOTS',
            'omitted_indirect_snapshot_copies': len(omissions), 'omitted_unique_payloads': 2,
            'omitted_source_recheck_requires_fixed_repository_git_commit': True,
            'privacy_candidates': 0, **counters}


def write_manifest(archive):
    paths = sorted(p for p in archive.rglob('*') if p.is_file() and p != archive / 'SHA256SUMS')
    (archive / 'SHA256SUMS').write_text(''.join(sha(p.read_bytes()) + '  ' + p.relative_to(archive).as_posix() + '\n' for p in paths))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', type=Path, required=True)
    parser.add_argument('--assemble', action='store_true', help='Root-only explicit mutation; requires final24 and actual receipts')
    parser.add_argument('--write', action='store_true', help='Root-only audit-report/manifest refresh after explicit additions')
    parser.add_argument('--command-receipt', help='Repo-relative actual root invocation JSON, not templates')
    parser.add_argument('--sync-receipt', help='Repo-relative actual post-PWM head_after/fetch_exit_code/merge_exit_code receipt')
    parser.add_argument('--add-source', action='append', default=[], help='Explicit repo-relative SOURCE=ARCHIVE_DEST, exact bytes')
    parser.add_argument('--preflight', action='store_true', help='Read source terminal status only; no archive write')
    args = parser.parse_args()
    root = args.repo_root.resolve()
    archive = root / 'docs/evidence' / NAME
    need(not (args.assemble and args.write), 'choose assemble or metadata refresh')
    additions = [tuple(item.split('=', 1)) for item in args.add_source]
    need(all(len(item) == 2 for item in additions), 'explicit addition must be SOURCE=DEST')
    if args.preflight or not archive.exists() and not args.assemble:
        need(not args.write and not additions, 'source preflight is read-only')
        state = terminal_preflight(root, final=False)
        print(json.dumps({k: v for k, v in state.items() if k != 'cases'}, ensure_ascii=False, indent=2))
        return
    if args.assemble:
        assemble(root, archive, args.command_receipt, args.sync_receipt, additions)
        report = audit(root, archive, check_manifest=False)
        save(archive / 'audit-report.json', report)
        write_manifest(archive)
    elif args.write:
        provenance = load(archive / 'copy-provenance.json')['files']
        transports = {row['original']: row for row in load(archive / 'transport-paths.json')['files']}
        omissions = load(archive / 'omitted-source-snapshots.json')['files']
        previous_omissions = set(omissions)
        copy_sources(root, archive, additions, provenance, transports, omissions)
        new_omissions = {name: row for name, row in omissions.items() if name not in previous_omissions}
        if new_omissions:
            omission_bindings(root, additions, new_omissions)
            omitted_manifest = load(archive / 'omitted-source-snapshots.json')
            omitted_manifest['files'] = omissions
            save(archive / 'omitted-source-snapshots.json', omitted_manifest)
        save(archive / 'copy-provenance.json', {'schema_version': 1, 'files': provenance})
        save(archive / 'transport-paths.json', {'schema_version': 1, 'byte_changes': False, 'files': sorted(transports.values(), key=lambda x: x['original'])})
        report = audit(root, archive, check_manifest=False)
        save(archive / 'audit-report.json', report)
        write_manifest(archive)
    else:
        need(not additions, 'adding source requires explicit root --write')
    print(json.dumps(audit(root, archive, check_manifest=True), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
