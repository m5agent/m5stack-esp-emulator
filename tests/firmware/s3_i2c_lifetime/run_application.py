#!/usr/bin/env python3
"""Collect a pinned application control through an owned Device Service lease.

Raw output contains private session metadata; keep --out in ignored/artifact
storage. Human frame review and a redacted summary are separate acceptance steps.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from PIL import Image


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Client:
    def __init__(self, api, token):
        parsed = urllib.parse.urlsplit(api)
        if parsed.hostname != '127.0.0.1' or parsed.port in (None, 8787, 8830):
            raise ValueError('use an owned loopback Device Service port')
        self.base = api.rstrip('/')
        self.token = token

    def call(self, route, payload=None, raw=None, method=None):
        headers = {'Authorization': 'Bearer ' + self.token}
        if payload is not None:
            raw = json.dumps(payload).encode()
            headers['Content-Type'] = 'application/json'
        elif raw is not None:
            headers['Content-Type'] = 'application/octet-stream'
        request = urllib.request.Request(self.base + route, raw, headers, method=method)
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
            return json.loads(data) if 'json' in response.headers.get('Content-Type', '') else data


def frame(client, route, out, name):
    data = client.call(route + '/frame.png')
    (out / (name + '.png')).write_bytes(data)
    im = Image.open(io.BytesIO(data)).convert('RGB')
    pixels = list(im.getdata())
    return {'sha256': sha(data), 'pixel_sha256': sha(im.tobytes()), 'size': list(im.size),
            'colors': len(set(pixels)), 'nonblack': sum(p != (0, 0, 0) for p in pixels)}


def touch_spec(value):
    fields = value.split(':')
    if len(fields) != 3:
        raise argparse.ArgumentTypeError('expected SECONDS:X:Y')
    at, x, y = map(int, fields)
    if at < 0 or not 0 <= x < 320 or not 0 <= y < 240:
        raise argparse.ArgumentTypeError('touch must be within the 320x240 frame')
    return at, x, y


def run(args):
    data = args.bin.read_bytes()
    if sha(data) != args.sha256:
        raise ValueError('firmware SHA256 mismatch')
    if args.seconds < 330:
        raise ValueError('application stability control requires at least 330 seconds')
    args.out.mkdir(parents=True, exist_ok=False)
    client = Client(args.api, args.token_file.read_text().strip())
    artifact = client.call('/artifacts', raw=data)
    firmware = client.call('/firmware', {'kind': 'merged', 'device_id': 'stackchan',
                                       'artifact_id': artifact['artifact_id']})
    analysis = client.call('/firmware/analyze', {'firmware_id': firmware['firmware_id']})
    assert analysis['valid'], 'firmware composition rejected'
    session = client.call('/sessions', {'device_id': 'stackchan', 'firmware_id': firmware['firmware_id'],
        'runtime': 'qemu', 'ttl_seconds': args.seconds + 300, 'ready_timeout_seconds': 30,
        'runtime_env': {'M5SW_FT_TRACE': '1'}})
    route = '/sessions/' + session['session_id']
    report = {'status': 'REVIEW', 'firmware_sha256': sha(data), 'firmware': firmware,
              'runtime_sha256': sha(args.runtime_bin.read_bytes()), 'session_id': session['session_id'],
              'samples': [], 'inputs': []}
    (args.out / 'current.json').write_text(json.dumps({'route': route}))
    try:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            state = client.call(route)['state']
            if state in ('running', 'failed', 'stopped'):
                break
            time.sleep(.2)
        assert state == 'running', 'guest did not reach backend readiness'
        started = time.monotonic()
        actions = iter(sorted(args.touch_at))
        pending = next(actions, None)
        sample_index = 0
        next_sample = 0
        while True:
            elapsed = time.monotonic() - started
            if pending is not None and elapsed >= pending[0]:
                at, x, y = pending
                name = 'input-' + str(len(report['inputs']))
                before = frame(client, route, args.out, name + '-before')
                request = {'kind': 'touch', 'x': x, 'y': y, 'settle_seconds': 1}
                receipt = client.call(route + '/input', request)
                after = frame(client, route, args.out, name + '-after')
                report['inputs'].append({'elapsed_seconds': elapsed, 'request': request,
                    'receipt': receipt, 'before': before, 'after': after})
                pending = next(actions, None)
            if elapsed >= next_sample:
                logs = client.call(route + '/logs?offset=0&limit=1048576')
                (args.out / 'logs-latest.json').write_text(json.dumps(logs))
                serial = logs.get('data', '') + '\n' + logs.get('stderr', '')
                sample = {'elapsed_seconds': elapsed, 'state': client.call(route)['state'],
                    'frame': frame(client, route, args.out, f'frame-{sample_index:03}'),
                    'servo': client.call(route + '/qom?path=/machine/scs_servo&property=state'),
                    'boot_count': len(re.findall(r'rst:0x', serial)),
                    'panic_markers': [m for m in ('Guru Meditation', 'assert failed', 'Rebooting...',
                        'Task watchdog', 'Double exception', 'atomic_mmu_lookup') if m in serial]}
                report['samples'].append(sample)
                report['elapsed_seconds'] = time.monotonic() - started
                (args.out / 'raw-result.json').write_text(json.dumps(report, indent=2))
                print(json.dumps({'sample': sample_index, 'elapsed': round(elapsed),
                    'state': sample['state'], 'panic': sample['panic_markers'],
                    'boot_count': sample['boot_count']}), flush=True)
                if sample['state'] != 'running' or sample['panic_markers'] or sample['boot_count'] > 1:
                    report['status'] = 'FAIL'
                    break
                if elapsed >= args.seconds:
                    break
                sample_index += 1
                next_sample = min(args.seconds, sample_index * 10)
            time.sleep(.1)
        report['final_snapshot'] = client.call(route)
        report['qom_snapshot'] = client.call(route + '/qom-snapshot',
            {'path': '/machine', 'depth': 2, 'max_nodes': 500})
    finally:
        try:
            evidence = client.call(route + '/evidence')
            (args.out / 'evidence.zip').write_bytes(evidence)
            report['evidence_sha256'] = sha(evidence)
        finally:
            report['stop'] = client.call(route + '?purge=0&retain_flash=0', method='DELETE')
            report['stopped_snapshot'] = client.call(route)
            (args.out / 'raw-result.json').write_text(json.dumps(report, indent=2))
    if report['status'] == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--bin', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--runtime-bin', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=360)
    parser.add_argument('--touch-at', type=touch_spec, action='append', default=[])
    run(parser.parse_args())
