#!/usr/bin/env python3
"""Observe original Core2 UIFlow 1.15.5 through a dedicated Device Service."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


FIRMWARE_SHA256 = '3b389eea45b2c1a45b65c29e6de969635e19c486cd5876a048724d6c551f7d1b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--runtime-binary', type=Path, required=True,
                        help='Actual compiled executable used by this local service, before any wrapper')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--seconds', type=int, default=330)
    args = parser.parse_args()
    binary = args.firmware.read_bytes()
    if hashlib.sha256(binary).hexdigest() != FIRMWARE_SHA256:
        parser.error('expected unchanged Core2 UIFlow 1.15.5 firmware')
    if args.seconds < 180 or args.seconds % 5:
        parser.error('observation must be at least 180 seconds and a multiple of five')
    args.out_dir.mkdir(parents=True, exist_ok=False)
    token = args.token_file.read_text().strip()

    def api(route, body=None, raw=None, method=None):
        headers = {'Authorization': 'Bearer ' + token}
        if body is not None:
            raw = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        elif raw is not None:
            headers['Content-Type'] = 'application/octet-stream'
        request = urllib.request.Request(args.service.rstrip('/') + '/api/v1/' + route,
                                         data=raw, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
            return json.loads(data) if 'json' in response.headers.get('Content-Type', '') else data

    report = {'input_sha256': FIRMWARE_SHA256,
              'runtime_sha256': hashlib.sha256(args.runtime_binary.read_bytes()).hexdigest(),
              'samples': []}
    artifact = api('artifacts', raw=binary)
    firmware = api('firmware', {'device_id': 'core2', 'kind': 'merged',
                                'artifact_id': artifact['artifact_id']})
    session = api('sessions', {'device_id': 'core2', 'firmware_id': firmware['firmware_id'],
                              'runtime': 'qemu-wifi', 'ttl_seconds': args.seconds + 300,
                              'network': {'http_fixture': False, 'capture_pcap': True}})
    route = 'sessions/' + session['session_id']
    try:
        deadline = time.monotonic() + 60
        while session['state'] != 'running':
            if session['state'] in ('failed', 'stopped') or time.monotonic() > deadline:
                raise RuntimeError('guest did not start')
            time.sleep(.2)
            session = api(route)
        report['running'] = session
        start = time.monotonic()
        for seconds in range(0, args.seconds + 1, 5):
            time.sleep(max(0, start + seconds - time.monotonic()))
            sample = {'elapsed_seconds': time.monotonic() - start,
                      'serial': api(route + '/serial?offset=0&limit=262144')}
            if seconds % 30 == 0 or seconds == args.seconds:
                frame = api(route + '/frame.png')
                (args.out_dir / f'frame-{seconds:03}.png').write_bytes(frame)
                sample['frame_sha256'] = hashlib.sha256(frame).hexdigest()
            report['samples'].append(sample)
            (args.out_dir / 'observation.json').write_text(json.dumps(report, indent=2))
        report['status'] = 'OBSERVED; review serial and frames for application readiness'
    finally:
        try:
            evidence = api(route + '/evidence')
            (args.out_dir / 'evidence.zip').write_bytes(evidence)
            report['evidence_sha256'] = hashlib.sha256(evidence).hexdigest()
        finally:
            report['stop'] = api(route + '?purge=0&retain_flash=0', method='DELETE')
            (args.out_dir / 'observation.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
