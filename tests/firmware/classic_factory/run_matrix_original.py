#!/usr/bin/env python3
"""Retain unchanged Atom Matrix factory behavior through a dedicated service."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

EXPECTED_SHA = '24892fcf5d5f8c97ee30a5ffb4fec166dca1c254cc6f54861af28abc8732ba2f'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--firmware', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=130)
    parser.add_argument('--wifi-ssid')
    parser.add_argument('--offline', action='store_true', help='use the default radio-disabled qemu runtime')
    parser.add_argument('--password-env', default='M5_TEST_WIFI_PASSWORD')
    args = parser.parse_args()
    if args.seconds < 120:
        parser.error('at least 120 seconds are required')
    password = os.environ.get(args.password_env)
    if not args.offline and (not password or not args.wifi_ssid):
        parser.error('--wifi-ssid and the specified password environment variable must be set')
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
    request = {
        'device_id': 'atom-matrix', 'firmware_id': image['firmware_id'],
        'runtime': 'qemu' if args.offline else 'qemu-wifi',
        'ttl_seconds': int(args.seconds + 180),
    }
    if not args.offline:
        request['network'] = {'profile': 'generic-observe', 'wifi_ssid': args.wifi_ssid,
                    'wifi_auth': 'wpa2-psk', 'wifi_password': password,
                    'capture_pcap': True, 'http_fixture': False}
    session = call('POST', 'sessions', request)
    prefix = 'sessions/' + session['session_id']
    started = time.monotonic()
    try:
        samples = []
        while time.monotonic() - started < args.seconds:
            time.sleep(max(0, min(2, args.seconds - (time.monotonic() - started))))
            samples.append({'wall_seconds': time.monotonic() - started,
                            'state': call('GET', prefix + '/device-state')})
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
        (args.out_dir / 'samples.json').write_text(json.dumps(samples, indent=2))
        (args.out_dir / 'device-state.json').write_text(json.dumps(states, indent=2))
        controller = {}
        for path, properties in (
            ('/machine/rmt-classic', ('tx-symbols', 'tx-threshold-events',
                                    'tx-completions', 'tx-errors', 'tx-last-tick-hz')),
            ('/machine/onboard_io', ('led-frames', 'incomplete-frames', 'led-rgb')),
        ):
            for prop in properties:
                query = urllib.parse.urlencode({'path': path, 'property': prop})
                controller[path + '/' + prop] = call('GET', prefix + '/qom?' + query)['value']
        (args.out_dir / 'controller.json').write_text(json.dumps(controller, indent=2))
        (args.out_dir / 'session.json').write_text(json.dumps(call('GET', prefix), indent=2))
        (args.out_dir / 'evidence.zip').write_bytes(call('GET', prefix + '/evidence'))
        result = {'source_sha256': EXPECTED_SHA, 'wall_seconds': time.monotonic() - started,
                  'scan_observed': 'Best RSSI:' in serial,
                  'http_response_observed': '[HTTP] GET... code:' in serial,
                  'factory_http_pass': '[HTTP] HTTP test pass' in serial,
                  'poweron_resets': serial.count('POWERON_RESET'),
                  'runtime_errors': [marker for marker in ('Guru Meditation', 'watchdog', 'abort()') if marker in serial],
                  'button_edges': [state['components']['onboard-io']['properties']['pressed'] for state in states],
                  'led_frames': states[-1]['components']['onboard-io']['properties']['led-frames'],
                  'nonblack_samples': sum(any(sample['state']['components']['onboard-io']['properties']['led-rgb']) for sample in samples),
                  'controller': controller}
        (args.out_dir / 'summary.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        network_ok = args.offline or (result['scan_observed'] and result['http_response_observed'])
        return 0 if network_ok and not result['runtime_errors'] and result['poweron_resets'] == 1 and result['button_edges'] == [False, True, False] and result['nonblack_samples'] > 0 else 1
    finally:
        try:
            if not (args.out_dir / 'evidence.zip').exists():
                (args.out_dir / 'evidence.zip').write_bytes(call('GET', prefix + '/evidence'))
        finally:
            call('DELETE', prefix + '?purge=0&retain_flash=0')

if __name__ == '__main__':
    raise SystemExit(main())
