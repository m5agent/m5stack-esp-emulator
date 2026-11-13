#!/usr/bin/env python3
"""Enumerate the original PaperColor factory MSC interface before later app work."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'atoms3_display'))
from run_test import Client
# Distinct module name avoids importing the helper above twice.
import importlib.util
spec = importlib.util.spec_from_file_location('usb_probe', Path(__file__).resolve().parents[1] / 'sticks3_usb_otg' / 'run_test.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
Probe = module.Probe
SHA = 'a3f5ca4ae89dd724dd8f9b2d800fd9749af84bf0cf2fffbf99cdf822b285f419'

def run(args):
    data = args.bin.read_bytes(); assert hashlib.sha256(data).hexdigest() == SHA
    args.out.mkdir(parents=True, exist_ok=True)
    token = args.token_file.read_text().strip(); client = Client(args.api, token)
    artifact = client.call('/artifacts', raw=data)
    fw = client.call('/firmware', {'device_id': 'papercolor', 'kind': 'merged', 'artifact_id': artifact['artifact_id']})
    assert client.call('/firmware/analyze', {'firmware_id': fw['firmware_id']})['valid']
    session = client.call('/sessions', {'device_id': 'papercolor', 'firmware_id': fw['firmware_id'], 'runtime': 'qemu', 'ttl_seconds': 900})
    sid = session['session_id']; route = '/sessions/' + sid
    probe = Probe(args.api.rstrip('/') + route, token)
    result = {'status': 'FAIL', 'source_sha256': SHA, 'session_id': sid}
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                if probe.state('host-state').startswith('attached'): break
            except Exception:
                pass
            time.sleep(.01)
        before = client.call(route + '/serial?offset=0&limit=1000000')['data']
        assert before.count('Rebooting...') == 0, 'must enumerate the first cold-boot epoch'
        result['mode'] = probe.state('host-state')
        probe.packet('reset', 'ACK', 2)
        device = probe.read(0x80, 6, 0x0100, 0, 18)
        assert device.hex() == '12010002ef0201403a300240000101020301'
        probe.write(0, 5, 7, 0)
        assert probe.state('host-state').startswith('attached address=7 ')
        header = probe.read(0x80, 6, 0x0200, 0, 9)
        config = probe.read(0x80, 6, 0x0200, 0, int.from_bytes(header[2:4], 'little'))
        assert config.hex() == '09022000010100a0320904000002080650000705010240000007058102400000'
        probe.write(0, 9, 1, 0)
        assert probe.read(0x80, 8, 0, 0, 1) == b'\x01'
        assert probe.read(0xa1, 0xfe, 0, 0, 1) == b'\x00'  # MSC GET_MAX_LUN
        after = client.call(route + '/serial?offset=0&limit=1000000')['data']
        assert after.count('Rebooting...') == 0 and 'assert failed:' not in after
        result.update(status='PASS', device=device.hex(), configuration=config.hex(),
                      get_configuration='01', get_max_lun='00', reset_epochs=1)
        (args.out / 'serial.log').write_text(after)
    finally:
        result['transactions'] = probe.transcript
        try: (args.out / 'evidence.zip').write_bytes(client.call(route + '/evidence'))
        finally:
            result['stop'] = client.call(route + '?purge=0&retain_flash=0', method='DELETE')
            (args.out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'mode': result['mode'], 'get_max_lun': '00'}))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api', required=True); p.add_argument('--token-file', required=True, type=Path)
    p.add_argument('--bin', required=True, type=Path); p.add_argument('--out', required=True, type=Path)
    run(p.parse_args())
