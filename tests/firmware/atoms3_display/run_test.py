#!/usr/bin/env python3
"""Run the pinned original AtomS3 images through an owned Device Service."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
from PIL import Image

IMAGES = {
    'snake': '3e4fcd924596035d0240d5b15e53cffa7538151a0ac1ff04d32bd113f3c6b7af',
    'userdemo': '2d78c3d8874eee0f6d91eb9c8fe6ad482488dad05e5a42adc1dde09977800b06',
}
class Client:
    def __init__(self, api, token):
        parsed = urllib.parse.urlsplit(api)
        if parsed.hostname != '127.0.0.1' or parsed.port in (None, 8787, 8830):
            raise ValueError('use an owned loopback Device Service port')
        self.api = api.rstrip('/')
        self.token = token
    def call(self, route, body=None, raw=None, method=None):
        headers = {'Authorization': 'Bearer ' + self.token}
        if body is not None:
            raw = json.dumps(body).encode(); headers['Content-Type'] = 'application/json'
        elif raw is not None:
            headers['Content-Type'] = 'application/octet-stream'
        request = urllib.request.Request(self.api + route, raw, headers, method=method)
        with urllib.request.urlopen(request, timeout=180) as response:
            data = response.read()
            return json.loads(data) if 'json' in response.headers.get('content-type', '') else data

def frame(client, session, out, name):
    data = client.call('/sessions/' + session + '/frame.png')
    (out / (name + '.png')).write_bytes(data)
    im = Image.open(io.BytesIO(data)).convert('RGB')
    colors = set(im.getdata())
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': list(im.size),
            'colors': len(colors), 'nonblack': sum(p != (0, 0, 0) for p in im.getdata())}

def run(args):
    data = args.bin.read_bytes()
    assert hashlib.sha256(data).hexdigest() == IMAGES[args.case], 'wrong original firmware'
    out = args.out; out.mkdir(parents=True, exist_ok=True)
    client = Client(args.api, args.token_file.read_text().strip())
    artifact = client.call('/artifacts', raw=data)
    fw = client.call('/firmware', {'device_id': 'atoms3', 'kind': 'merged', 'artifact_id': artifact['artifact_id']})
    analysis = client.call('/firmware/analyze', {'firmware_id': fw['firmware_id']})
    assert analysis['valid']
    session = client.call('/sessions', {'device_id': 'atoms3', 'firmware_id': fw['firmware_id'],
        'runtime': 'qemu', 'ttl_seconds': 900, 'runtime_env': {'M5SW_ATOMS3_GC9107': '1'}})
    sid = session['session_id']; route = '/sessions/' + sid
    report = {'source_sha256': artifact['sha256'], 'source_bytes': len(data), 'session_id': sid,
              'case': args.case, 'frames': [], 'inputs': [], 'status': 'FAIL'}
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            snapshot = client.call(route)
            if snapshot['state'] == 'running': break
            assert snapshot['state'] not in ('failed', 'stopped'), snapshot
            time.sleep(.2)
        assert snapshot['state'] == 'running'
        # Backend readiness precedes display initialization. Bound application
        # readiness by observed pixels, then begin the 120-second stability window.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            sample = frame(client, sid, out, 'ready')
            if sample['size'] == [128, 128] and sample['colors'] > 2 and sample['nonblack'] > 100:
                break
            time.sleep(.2)
        assert sample['size'] == [128, 128] and sample['colors'] > 2 and sample['nonblack'] > 100
        started = time.monotonic()
        for index in range(5):
            if index:
                time.sleep(max(0, started + 30 * index - time.monotonic()))
            sample = frame(client, sid, out, 'stable-' + str(index))
            assert sample['size'] == [128, 128] and sample['colors'] > 2 and sample['nonblack'] > 100
            report['frames'].append(sample)
        report['stable_seconds'] = time.monotonic() - started
        if args.case == 'snake':
            previous = report['frames'][-1]['sha256']
            for axis, value in [('accel-y', .8), ('accel-x', -.8), ('accel-y', -.8), ('accel-x', .8)]:
                for prop in ('accel-x', 'accel-y'):
                    client.call(route + '/qom', {'path': '/machine/mpu6886', 'property': prop,
                                               'value': value if prop == axis else 0})
                time.sleep(.2)
                sample = frame(client, sid, out, 'tilt-' + str(len(report['inputs'])))
                report['inputs'].append({'axis': axis, 'value': value, 'frame': sample})
                assert sample['sha256'] != previous, 'no visible input response'
                previous = sample['sha256']
            for prop in ('accel-x', 'accel-y'):
                client.call(route + '/qom', {'path': '/machine/mpu6886', 'property': prop, 'value': 0})
        report['final_session'] = client.call(route)
        serial = client.call(route + '/serial?offset=0&limit=1000000')['data']
        (out / 'serial.log').write_text(serial)
        assert not any(marker in serial for marker in ('Guru Meditation', 'assert failed', 'Rebooting...', 'Task watchdog'))
        assert report['final_session']['state'] == 'running'
        report['status'] = 'PASS'
    finally:
        try: (out / 'evidence.zip').write_bytes(client.call(route + '/evidence'))
        finally:
            report['stop'] = client.call(route + '?purge=0&retain_flash=0', method='DELETE')
            (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'case': args.case, 'status': report['status'], 'stable_seconds': report['stable_seconds']}))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api', required=True); p.add_argument('--token-file', required=True, type=Path)
    p.add_argument('--case', required=True, choices=IMAGES); p.add_argument('--bin', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    run(p.parse_args())
