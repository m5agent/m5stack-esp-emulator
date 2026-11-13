#!/usr/bin/env python3
"""Retain unchanged Atom Matrix factory behavior through a dedicated service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request

EXPECTED_SHA = '24892fcf5d5f8c97ee30a5ffb4fec166dca1c254cc6f54861af28abc8732ba2f'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=130)
    parser.add_argument('--wifi-ssid', required=True)
    parser.add_argument('--password-env', default='M5_TEST_WIFI_PASSWORD')
    args = parser.parse_args()
    if args.seconds < 120:
        parser.error('at least 120 seconds are required')
    password = os.environ.get(args.password_env)
    if not password:
        parser.error('the specified password environment variable must be set')
    firmware = args.firmware.read_bytes()
    if hashlib.sha256(firmware).hexdigest() != EXPECTED_SHA:
        parser.error('this regression requires the original Atom Matrix v1.0 BIN')
    args.out_dir.mkdir(parents=True, exist_ok=True)
    token = args.token_file.read_text().strip()
    def call(method, path, body=None, raw=None):
        headers = {'Authorization': 'Bearer ' + token,
                   'Content-Type': 'application/json' if raw is None else 'application/octet-stream'}
        data = json.dumps(body).encode() if body is not None else raw
        request = urllib.request.Request(args.service.rstrip('/') + '/api/v1/' + path,
                                         data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=45) as response:
            content = response.read()
            return json.loads(content) if 'json' in response.headers.get('Content-Type', '') else content
    artifact = call('POST', 'artifacts', raw=firmware)
    image = call('POST', 'firmware', {'device_id': 'atom-matrix', 'kind': 'merged',
                                    'artifact_id': artifact['artifact_id']})
    session = call('POST', 'sessions', {
        'device_id': 'atom-matrix', 'firmware_id': image['firmware_id'],
        'runtime': 'qemu-wifi', 'ttl_seconds': int(args.seconds + 180),
        'network': {'profile': 'generic-observe', 'wifi_ssid': args.wifi_ssid,
                    'wifi_auth': 'wpa2-psk', 'wifi_password': password,
                    'capture_pcap': True, 'http_fixture': False},
    })
    prefix = 'sessions/' + session['session_id']
    started = time.monotonic()
    try:
        time.sleep(2)
        while time.monotonic() - started < args.seconds:
            time.sleep(max(0, min(2, args.seconds - (time.monotonic() - started))))
        states = [call('GET', prefix + '/device-state')]
        for action in ('down', 'up'):
            call('POST', prefix + '/input', {'kind': 'key', 'key': 'a', 'action': action,
                                           'settle_seconds': 0.2})
            states.append(call('GET', prefix + '/device-state'))
        serial = ''
        offset = 0
        while True:
            chunk = call('GET', prefix + f'/serial?offset={offset}&limit=262144')
            serial += chunk['data']
            if chunk['next_offset'] == offset or chunk['bytes'] < 262144:
                break
            offset = chunk['next_offset']
        (args.out_dir / 'serial.log').write_text(serial)
        (args.out_dir / 'device-state.json').write_text(json.dumps(states, indent=2))
        (args.out_dir / 'session.json').write_text(json.dumps(call('GET', prefix), indent=2))
        (args.out_dir / 'evidence.zip').write_bytes(call('GET', prefix + '/evidence'))
        result = {'source_sha256': EXPECTED_SHA, 'wall_seconds': time.monotonic() - started,
                  'scan_observed': 'Best RSSI:' in serial,
                  'http_response_observed': '[HTTP] GET... code:' in serial,
                  'factory_http_pass': '[HTTP] HTTP test pass' in serial,
                  'runtime_errors': [marker for marker in ('Guru Meditation', 'watchdog', 'abort()') if marker in serial],
                  'button_edges': [state['components']['onboard-io']['properties']['pressed'] for state in states],
                  'led_frames': states[-1]['components']['onboard-io']['properties']['led-frames']}
        (args.out_dir / 'summary.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        return 0 if result['scan_observed'] and result['http_response_observed'] and not result['runtime_errors'] and result['button_edges'] == [False, True, False] else 1
    finally:
        call('DELETE', prefix + '?purge=0&retain_flash=0')

if __name__ == '__main__':
    raise SystemExit(main())
