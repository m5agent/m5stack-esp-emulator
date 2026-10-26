#!/usr/bin/env python3
"""Offline evidence re-audit only. No API, process launch, guest or matrix execution.

Without --terminal-exit-code this always records PENDING, even if a summary
already exists. Root supplies that value only after observing runner termination.
"""
import argparse
from array import array
import ast
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import urllib.request
from unittest.mock import patch
from PIL import Image

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RUN = ROOT / '.work/unit-pwm-route-regression-20261026'
FULL = RUN / 'full-r1'
EXPECTED_RUNTIME = 'd1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff'
SHA = lambda b: hashlib.sha256(b).hexdigest()
J = lambda p: json.loads(p.read_bytes())

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def need(value, message):
    if not value:
        raise AssertionError(message)

def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def seal():
    names = ['audit_matrix.py', 'review.json', 'review.md', 'mid-run-observation.json', 'helper-checks.json']
    (OUT / 'SHA256SUMS').write_text(''.join(digest(OUT / n) + '  ' + n + '\n' for n in names if (OUT / n).is_file()))

def module(name, relative):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def assets_now(mid):
    assets = {k: {'path': v['path'], 'size': (ROOT / v['path']).stat().st_size,
                  'sha256': digest(ROOT / v['path'])} for k, v in mid['assets'].items()}
    dirs = {'xtensa': ROOT / '.work/unit-runtime-source-pwm-route/qemu/pc-bios',
            'c6': ROOT / '.work/M5StopWatch-QEMU/build/qemu-c6/pc-bios'}
    roms = {k: {p.relative_to(d).as_posix(): {'size': p.stat().st_size, 'sha256': digest(p)}
                for p in sorted(d.rglob('*.bin')) if p.is_file()} for k, d in dirs.items()}
    return {'at': datetime.now(timezone.utc).isoformat(), 'assets': assets, 'roms': roms}

def path_for(value):
    p = Path(value)
    return p if p.is_absolute() else ROOT / p

def command_record(matrix, case, result, reference):
    output = Path(result['output'])
    need(path_for(output).resolve() == FULL / case['id'], 'case output outside this single full run')
    sd = output / 'sd.img' if case.get('sd_image') else None
    expected = matrix.command_for(case, output, sd, reference=reference)
    if case.get('rmt_ws2812'):
        # Existing runner reuses `command` for its WS2812 checker before summary.
        checker = [sys.executable, str(ROOT / 'tests/uiflow2/check_rmt_ws2812.py'),
                   str(case['rmt_ws2812']['capture']).format(out_dir=output)]
        for led in case['rmt_ws2812']['leds']:
            checker += ['--led', led]
        need(result['command'] == checker, 'known WS2812 command overwrite differs')
        origin = 'STATIC_RECONSTRUCTION_FROM_FROZEN_COMMAND_FOR; summary stores WS2812 validation command'
    else:
        need(result['command'] == expected, 'recorded profile command differs from original case definition')
        origin = 'RECORDED_PROFILE_COMMAND_MATCHES_FROZEN_COMMAND_FOR'
    need('--allow-retries' not in expected and '--prebuilt-image' not in expected, 'unexpected retry/prebuilt bypass')
    return {'profile_command': expected, 'provenance': origin}

def frame_evidence(profile, case, directory):
    expected = tuple(map(int, case['expected_size'].split('x')))
    frames = {}
    for label in ('before', 'after'):
        p = directory / (label + '.ppm')
        w, h, pixels = profile.read_ppm(p)  # Read-only, never canonicalize/write.
        need((w, h) == expected, label + ' native frame geometry mismatch')
        nonblack, colors = profile.frame_stats(pixels)
        need(nonblack >= 16 and colors >= int(case.get('min_unique_colors', 2)), label + ' native frame blank/insufficient colors')
        png = directory / (label + '.png')
        with Image.open(png) as im:
            im.load()
            need(im.size == expected and im.convert('RGB').tobytes() == pixels, label + ' PNG differs from canonical raw PPM')
        frames[label] = {'ppm_sha256': digest(p), 'png_sha256': digest(png), 'width': w, 'height': h,
                         'pixels_sha256': SHA(pixels), 'nonblack': nonblack, 'unique_colors_capped_256': colors}
        if label == 'after' and case.get('frame_color'):
            marker = case['frame_color']
            x, y = marker['x'], marker['y']
            need(0 <= x < w and 0 <= y < h, 'frame marker outside image')
            rgb = tuple(pixels[(y * w + x) * 3:(y * w + x) * 3 + 3])
            good = max(rgb) < 64 if marker.get('dark') else rgb[1] > rgb[0] * 2 and rgb[1] > rgb[2] * 2
            frames['marker'] = {'x': x, 'y': y, 'rgb': rgb, 'dark': bool(marker.get('dark')), 'pass': good}
            need(good, 'actual frame success marker absent: ' + str(rgb))
    need(case.get('allow_static_frame') or frames['before']['pixels_sha256'] != frames['after']['pixels_sha256'], 'required UI change absent')
    return frames

def packaged_sources(profile, case, directory, reference):
    import littlefs
    image = directory / 'uiflow2-ui-test.bin'
    raw = image.read_bytes()
    need(len(raw) == int(case['flash_size'], 0), 'composed flash size mismatch')
    p = reference['effective']
    fs = littlefs.LittleFS(context=littlefs.UserContext(buffer=bytearray(raw[p['offset']:p['offset'] + p['size']])),
        block_size=4096, block_count=p['size'] // 4096, read_size=128, prog_size=32,
        lookahead_size=128, block_cycles=100, mount=False)
    fs.mount()
    probes = {}
    try:
        for rel, source in profile.runtime_files(ROOT / case['files_dir']).items():
            with fs.open('/' + rel.as_posix(), 'rb') as f:
                content = f.read()
            need(content == source.read_text().encode(), 'packaged Python differs from frozen probe: ' + rel.as_posix())
            probes[rel.as_posix()] = SHA(content)
    finally:
        fs.unmount()
    return {'current_mutable_flash_sha256': SHA(raw), 'packaged_python': probes,
            'scope': 'Actual final LittleFS readback. Initial image hash is independently read from raw runner stdout.'}

def data_planes(case, directory, stdout, nec, ws):
    results = {}
    for path, prop, raw in case.get('qom_expect', []):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        line = f'qom-expect {path} {prop}={value}'
        need(line in stdout.splitlines(), 'actual final QOM getter missing: ' + line)
    if case.get('qom_expect'):
        results['qom_expect'] = case['qom_expect']
    if case.get('qom_steps') or case.get('qom') or case.get('qom_set_boot'):
        results['qom_injections'] = {'scope': 'Frozen profile command + frozen runner ordering and guest/frame effects; qom-set is not itself a controller readback',
            'optional_debug_readbacks': [s for s in stdout.splitlines() if s.startswith(('qom ', 'qom-step ', 'qom-boot '))]}
    if case.get('pcm'):
        spec = case['pcm']; p = Path(str(spec['capture']).format(out_dir=directory)); raw = p.read_bytes()
        need(raw and len(raw) % 2 == 0, 'empty/unaligned captured PCM')
        samples = array('h'); samples.frombytes(raw)
        if sys.byteorder != 'little':
            samples.byteswap()
        nonzero = sum(x != 0 for x in samples); peak = max(samples) - min(samples)
        need(nonzero >= int(spec.get('min_nonzero', 1000)) and peak >= int(spec.get('min_peak_to_peak', 1000)), 'captured PCM failed original thresholds')
        results['captured_pcm'] = {'sha256': SHA(raw), 'bytes': len(raw), 'samples': len(samples), 'nonzero': nonzero, 'peak_to_peak': peak}
    if case.get('pcm_tone_source'):
        spec = case['pcm_tone_source']; p = Path(str(spec['output']).format(out_dir=directory))
        frequency, rate, seconds, amplitude = float(spec['frequency']), int(spec['sample_rate']), float(spec['seconds']), int(spec['amplitude'])
        expected = b''.join(struct.pack('<h', int(amplitude * math.sin(2 * math.pi * frequency * i / rate))) for i in range(int(rate * seconds)))
        need(p.read_bytes() == expected, 'microphone PCM injection fixture bytes differ')
        results['microphone_input_fixture'] = {'sha256': SHA(expected), 'bytes': len(expected), 'scope': 'Host PCM source; guest capture path still requires serial/frame assertions'}
    if case.get('rmt_nec'):
        spec = case['rmt_nec']; p = Path(str(spec['capture']).format(out_dir=directory))
        address, command, offset = nec.decode_nec(p)
        need(address == spec['address'] & 255 and command == spec['command'] & 255, 'captured NEC decode mismatch')
        results['rmt_nec'] = {'sha256': digest(p), 'address': address, 'command': command, 'offset': offset}
    if case.get('rmt_nec_source'):
        spec = case['rmt_nec_source']; p = Path(str(spec['output']).format(out_dir=directory))
        symbol = lambda d0, d1: d0 | (1 << 15) | (d1 << 16)
        payload = ((spec['command'] & 255) << 16) | (spec['address'] & 255)
        words = [symbol(9000, 4500)] + [symbol(560, 1690 if payload & (1 << i) else 560) for i in range(32)] + [symbol(560, 0)]
        expected = b''.join(x.to_bytes(4, 'little') for x in words)
        need(p.read_bytes() == expected, 'RMT NEC input fixture bytes differ')
        results['rmt_nec_input_fixture'] = {'sha256': SHA(expected), 'bytes': len(expected)}
    if case.get('rmt_ws2812'):
        spec = case['rmt_ws2812']; p = Path(str(spec['capture']).format(out_dir=directory)); raw = p.read_bytes()
        need(raw and len(raw) % 4 == 0, 'WS2812 word alignment')
        symbols = list(struct.unpack('<' + 'I' * (len(raw) // 4), raw))
        leds = [ws.parse_rgb(v) for v in spec['leds']]; expected = bytes(c for led in leds for c in led)
        size = len(leds) * ws.SYMBOLS_PER_LED
        found = next((i for i in range(len(symbols) - size + 1) if ws.decode_chunk(symbols[i:i + size]) == expected), None)
        need(found is not None, 'WS2812 captured GRB mismatch')
        results['rmt_ws2812'] = {'sha256': SHA(raw), 'expected': expected.hex(), 'offset': found}
    if case.get('disk'):
        spec = case['disk']; p = Path(str(spec['image']).format(out_dir=directory)); raw = p.read_bytes(); offset = int(spec['sector']) * 512
        need(raw[offset:offset + 512] == bytes((i * 7 + 0x31) & 255 for i in range(512)), 'SD sector data plane mismatch')
        results['disk'] = {'sha256': SHA(raw), 'sector': spec['sector'], 'length': 512}
    return results

def one_case(matrix, profile, case, result, nec, ws):
    name = case['id']; directory = FULL / name
    need(result['attempts'] == 1 and result['retry_used'] is False and not case.get('retries'), 'case is not a single clean attempt')
    need(not list(directory.glob('serial.attempt-*.log')), 'retry/forbidden-serial attempt artifact exists')
    stdout = (FULL / (name + '.stdout')).read_text(); stderr = (FULL / (name + '.stderr')).read_text()
    need('--- retry ' not in stdout + stderr, 'retry append marker exists')
    serial = (directory / 'serial.log').read_text(errors='replace')
    serial1 = (directory / 'serial1.log').read_text(errors='replace')
    forbidden = [x for x in matrix.DEFAULT_SERIAL_FAILURES + tuple(case.get('serial_forbid', ())) if x in stdout + '\n' + serial]
    need(not forbidden, 'forbidden guest failure marker: ' + repr(forbidden))
    missing = [x for x in case.get('serial_expect', []) if x not in serial]
    missing1 = [x for x in case.get('serial1_expect', []) if x not in serial1]
    need(not missing and not missing1, 'raw guest UART assertions missing: ' + repr(missing + missing1))
    reference = matrix.reference_layout(case)
    need(reference == result['reference_layout'], 'per-case actual base/partition hash differs')
    command = command_record(matrix, case, result, reference)
    names = [x['name'] for x in case['checks']]
    need([x['name'] for x in result['checks']] == names and all(x['status'] == result['status'] for x in result['checks']), 'original assertion inventory/status changed')
    evidence = [key for configured, key in [('serial_expect', 'serial.log'), ('serial1_expect', 'serial1.log')] if case.get(configured)]
    evidence += [key for configured, key in [('qom_expect', 'qom'), ('pcm', 'pcm'), ('rmt_nec', 'rmt-nec'), ('rmt_ws2812', 'rmt-ws2812'), ('disk', 'disk'), ('frame_color', 'frame-marker')] if case.get(configured) or configured == 'qom_expect' and case.get('qom_steps')]
    need(result['evidence_sources'] == evidence and all(x['evidence'] == evidence for x in result['checks']), 'case assertion evidence inventory changed')
    need(f"PASS machine={case['machine']} size={case['expected_size']} inputs={','.join(case['inputs'])}" in stdout, 'raw profile completion sentinel absent')
    sources = packaged_sources(profile, case, directory, reference)
    printed = re.findall(r'(?m)^sha256: ([a-f0-9]{64})$', stdout)
    need(len(printed) == 1, 'initial composed image hash absent/duplicated')
    sources['initial_printed_image_sha256'] = printed[0]
    sources['mutable_image_unchanged_after_guest'] = sources['current_mutable_flash_sha256'] == printed[0]
    frames = frame_evidence(profile, case, directory)
    planes = data_planes(case, directory, stdout, nec, ws)
    need(result['status'] == case['expected_status'] == 'PASS' and result['exit_code'] == 0, 'original matrix case failed; no targeted rerun may replace it')
    return {'status': 'PASS_RECOMPUTED', 'assertion_names': names, 'reference': reference, 'command': command,
            'stdout_sha256': digest(FULL / (name + '.stdout')), 'stderr_sha256': digest(FULL / (name + '.stderr')),
            'serial_sha256': digest(directory / 'serial.log'), 'serial1_sha256': digest(directory / 'serial1.log'),
            'frames': frames, 'data_planes': planes, 'sources': sources}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--terminal-exit-code', type=int)
    args = p.parse_args()
    prepare = J(RUN / 'prepare.json'); mid = J(OUT / 'mid-run-observation.json')
    now = assets_now(mid)
    source_current = {n: digest(ROOT / n) for n in prepare['source_sha256']}
    source_ok = source_current == prepare['source_sha256']
    need(prepare['allow_retries'] is False and prepare['runtime_sha256'] == EXPECTED_RUNTIME, 'prepared shared-controller runtime/retry scope mismatch')
    sys.path.insert(0, str(ROOT / 'platform/tools'))
    def deny(*a, **k):
        raise AssertionError('audit forbids API/socket/process/guest operations')
    with ExitStack() as stack:
        for obj, name in [(socket, 'socket'), (socket, 'create_connection'), (urllib.request, 'urlopen'), (subprocess, 'Popen'), (subprocess, 'run'), (subprocess, 'check_output'), (os, 'system')]:
            stack.enter_context(patch.object(obj, name, deny))
        matrix = module('audit_matrix_definition', 'tests/uiflow2/run_peripheral_matrix.py')
        profile = module('audit_profile_readers', 'tests/uiflow2/run_profile_ui_test.py')
        nec = module('audit_nec_reader', 'tests/uiflow2/check_rmt_nec.py')
        ws = module('audit_ws_reader', 'tests/uiflow2/check_rmt_ws2812.py')
        matrix.QEMU = ROOT / prepare['runtime_binary']; matrix.ROM_DIR = ROOT / prepare['rom_dir']
        matrix.QEMU_C6 = ROOT / mid['assets']['c6_binary']['path']
        cases = matrix.CASES
        need(len(cases) == 67 and sum(len(c['checks']) for c in cases) == 274, 'original 67/274 case/assertion scope drift')
        pending = {'status': 'PENDING', 'prepared_sha256': digest(RUN / 'prepare.json'), 'terminal_exit_code': args.terminal_exit_code,
            'expected_cases': 67, 'expected_assertions': 274, 'source_freeze_entries': len(source_current), 'source_freeze_current_match': source_ok,
            'mid_end_observed_assets_equal': now['assets'] == mid['assets'], 'mid_end_observed_roms_equal': now['roms'] == mid['roms'],
            'summary_present': (FULL / 'summary.json').is_file(), 'hardware': 'NOT RUN',
            'provenance_limitations': ['No complete all-ROM/C6 full-start freeze; mid-run observation is not relabeled as start', 'Xtensa has cold-build/prepared expected SHA and an actual mid-run process observation; per-case launch commands are configuration evidence', 'papercolor-rgb summary overwrites profile command with WS2812 checker; original command requires frozen-source static reconstruction'],
            'no_targeted_splice': True, 'API_guest_case_execution': 0}
        if args.terminal_exit_code is None or not pending['summary_present']:
            save('review.json', pending)
            (OUT / 'review.md').write_text('# d1ba 完整矩阵独审\n\nPENDING。尚未收到 root 的原始 runner 终态 exit，或本次67例 summary 尚未写出。脚本就绪及部分已完成产物的只读 helper 核对，不是完整矩阵 PASS。\n\n无API/guest/case执行。全量终态到达后由 root 确认实际 exit，再以 `--terminal-exit-code N` 运行离线审计。禁止将 targeted/补跑结果拼接进 full-r1。ROM/C6仅mid/end观测，不冒充完整full-start freeze；papercolor-rgb profile命令仅静态重构。\n', encoding='utf-8')
            seal()
            print(json.dumps(pending, indent=2))
            return
        need(source_ok, 'runner/probe/source hash drift since root prepare')
        need(now['assets'] == mid['assets'] and now['roms'] == mid['roms'], 'runtime/ROM bytes changed since mid-run observation')
        summary_path = FULL / 'summary.json'; summary_sha = digest(summary_path); summary = J(summary_path)
        need(set(summary['results']) == {c['id'] for c in cases}, 'full run lacks exact original 67 cases')
        results, errors = {}, {}
        for index, case in enumerate(cases):
            try:
                results[case['id']] = one_case(matrix, profile, case, summary['results'][case['id']], nec, ws)
            except Exception as error:
                errors[case['id']] = type(error).__name__ + ': ' + str(error)
                results[case['id']] = {'status': 'FAIL_RECOMPUTATION_OR_ORIGINAL', 'reported_status': summary['results'][case['id']]['status'], 'error': errors[case['id']]}
            if (index + 1) % 10 == 0:
                print('offline audited', index + 1, '/', len(cases), flush=True)
        need(summary_sha == digest(summary_path), 'summary changed during offline final audit')
        # Never replace a failed full-r1 case with targeted-cores3-r1 or another run.
        counts = dict(Counter(x['status'] for x in summary['results'].values()))
        checks = dict(Counter(x['status'] for c in summary['results'].values() for x in c['checks']))
        core2_case = next(c for c in cases if c['id'] == 'core2-imu')
        try:
            marker = core2_case['frame_color']
            width, height, pixels = profile.read_ppm(FULL / 'core2-imu/after.ppm')
            x, y = marker['x'], marker['y']
            rgb = tuple(pixels[(y * width + x) * 3:(y * width + x) * 3 + 3])
            core2_marker = {'x': x, 'y': y, 'rgb': rgb, 'green_marker': rgb[1] > rgb[0] * 2 and rgb[1] > rgb[2] * 2,
                             'ppm_sha256': digest(FULL / 'core2-imu/after.ppm'),
                             'reported_full_run_status': summary['results']['core2-imu']['status']}
        except Exception as error:
            core2_marker = {'status': 'UNAVAILABLE', 'error': str(error)}
        ok = args.terminal_exit_code == 0 and not errors and counts == {'PASS': 67} and checks == {'PASS': 274}
        report = {**pending, 'status': 'PASS_WITH_PROVENANCE_LIMITATIONS' if ok else 'FAIL',
            'full_matrix_status': 'PASS' if ok else 'FAIL', 'actual_case_counts': counts, 'actual_assertion_counts': checks,
            'summary_sha256': summary_sha, 'cases': results, 'errors': errors, 'terminal_exit_code_source': 'root observed runner tool termination, supplied explicitly',
            'strict_all_binary_ROM_full_start_end_freeze': 'NOT_ESTABLISHED', 'end_observation': now,
            'core2_imu': results.get('core2-imu'), 'core2_imu_actual_marker': core2_marker,
            'scope': 'Independent offline raw UART/QOM/frame/PCM/RMT/disk, packaged Python, exact command/source/runtime/ROM re-audit of one full run. No API, guest/case execution or hardware.'}
        save('review.json', report)
        (OUT / 'review.md').write_text('# d1ba 完整矩阵独审\n\n' + report['status'] + '\n\n一次 full-r1 的原67case/274assertion逐例离线重算；不拼接任何targeted结果。runtime/ROM仅按真实prepared、cold-build、mid/end及每case reference hash分层，不宣称完整all-ROM/C6启动前后冻结。papercolor-rgb原profile命令为冻结源码静态反推，summary实际保存WS2812 checker命令。\n\n实际统计：' + json.dumps(counts) + '；assertions：' + json.dumps(checks) + '。错误：' + json.dumps(errors, ensure_ascii=False) + '。hardware NOT RUN。详见review.json逐例原始文件hash及Core2 marker像素。\n', encoding='utf-8')
        seal()
        print(json.dumps({'status': report['status'], 'cases': counts, 'assertions': checks, 'errors': errors, 'review_sha256': digest(OUT / 'review.json')}, indent=2))

if __name__ == '__main__':
    main()
