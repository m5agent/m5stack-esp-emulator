#!/usr/bin/env python3
"""Observe an unchanged Core2 image through a dedicated Device Service."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--service', required=True)
    p.add_argument('--token-file', type=Path, required=True)
    p.add_argument('--firmware', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--seconds', type=int, default=120)
    a = p.parse_args()
    binary = a.firmware.read_bytes()
    if hashlib.sha256(binary).hexdigest() != a.sha256 or a.seconds < 90:
        p.error('firmware SHA must match and observation must be at least 90 seconds')
    a.out_dir.mkdir(parents=True, exist_ok=False)
    token = a.token_file.read_text().strip()

    def api(route, body=None, raw=None, method=None):
        headers = {'Authorization': 'Bearer ' + token}
        if body is not None:
            raw = json.dumps(body).encode()
            headers['Content-Type'] = 'application/json'
        elif raw is not None:
            headers['Content-Type'] = 'application/octet-stream'
        req = urllib.request.Request(a.service.rstrip('/') + '/api/v1/' + route,
                                     data=raw, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=120) as response:
            b = response.read()
            return json.loads(b) if 'json' in response.headers.get('Content-Type', '') else b

    artifact = api('artifacts', raw=binary)
    firmware = api('firmware', {'device_id': 'core2', 'kind': 'merged',
                                'artifact_id': artifact['artifact_id']})
    session = api('sessions', {'device_id': 'core2', 'firmware_id': firmware['firmware_id'],
                              'runtime': 'qemu', 'ttl_seconds': a.seconds + 300})
    route = 'sessions/' + session['session_id']
    report = {'input_sha256': a.sha256, 'samples': []}
    try:
        deadline = time.monotonic() + 60
        while session['state'] != 'running':
            if session['state'] in ('failed', 'stopped') or time.monotonic() > deadline:
                raise RuntimeError('guest did not start')
            time.sleep(.2)
            session = api(route)
        start = time.monotonic()
        for seconds in range(0, a.seconds + 1, 30):
            time.sleep(max(0, start + seconds - time.monotonic()))
            frame = api(route + '/frame.png')
            (a.out_dir / f'frame-{seconds:03}.png').write_bytes(frame)
            serial = api(route + '/serial?offset=0&limit=262144')
            report['samples'].append({'elapsed_seconds': time.monotonic() - start,
                                      'frame_sha256': hashlib.sha256(frame).hexdigest(),
                                      'serial': serial})
        report['session'] = api(route)
        report['status'] = 'OBSERVED; application readiness requires frame/serial review'
    finally:
        try:
            evidence = api(route + '/evidence')
            (a.out_dir / 'evidence.zip').write_bytes(evidence)
            report['evidence_sha256'] = hashlib.sha256(evidence).hexdigest()
        finally:
            report['stop'] = api(route + '?purge=0', method='DELETE')
            (a.out_dir / 'observation.json').write_text(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
