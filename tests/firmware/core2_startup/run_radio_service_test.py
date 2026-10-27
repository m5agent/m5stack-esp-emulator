#!/usr/bin/env python3
"""Two sequential visible Core2 OpenMAC sessions; no direct QEMU/service launch."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'platform/tools'), str(ROOT / '.work/py312')]
from uiflow_source import build_uiflow_source_image  # noqa: E402
from pcap_summary import summarize_pcap  # noqa: E402

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

startup = module('startup_gate', ROOT / 'tests/firmware/core2_startup/run_service_test.py')
legacy = module('stock_radio_parser', ROOT / 'tests/network/core2_openmac_wifi/run_test.py')
require, sha, save = startup.require, startup.sha, startup.save

class Fixture(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b'CORE2_HOST_HTTP_OK\n'
        self.server.observations.append({'path': self.path, 'host': self.headers.get('Host'), 'status': 200, 'body_sha256': sha(body)})
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass

FAILURE = re.compile(r'Traceback \(most recent call last\)|Guru Meditation|Interrupt wdt timeout|TG[01]WDT_SYS_RESET|CORE2_WIFI_RESULT: FAILED|CORE2_WIFI_\w+_ERROR|CORE2_HTTP_ERROR')

def guest_checks(serial):
    parsed = legacy.parse_probe(serial)
    return {
        'stock_version': bool(re.search(r'\bV2\.5\.3\b', serial)),
        'single_boot': serial.count('CORE2_WIFI_BOOT_FLAG') == 1 and len(re.findall(r'(?m)^rst:0x', serial)) == 1,
        'no_guest_error_or_reset': not bool(FAILURE.search(serial)),
        'active': parsed['active'], 'scan_nonempty': parsed['scan_count'] >= 1,
        'known_ap': parsed['known_ssid'], 'connect_returned': parsed['connect_returned'],
        'connected': parsed['connected'], 'dhcp_address': parsed['ip'] == '10.0.2.15',
        'http_200': parsed['http_200'], 'terminal_pass': parsed['terminal_result'] == 'PASSED',
    }, parsed

def packet_checks(raw, out, port):
    capture = out / 'capture.pcap'; capture.write_bytes(raw)
    parsed = summarize_pcap(capture)
    save(out / 'pcap-summary.json', parsed)
    message_types = parsed['dhcp']['message_types']
    endpoint = '10.0.2.2:' + str(port)
    flows = parsed['flows']
    checks = {
        'pcap_packets': parsed['packets'] > 0,
        'pcap_well_formed': parsed['malformed_records'] == 0 and parsed['truncated_records'] == 0,
        'pcap_dhcp_dora': all(message_types.get(k, 0) >= 1 for k in ('discover', 'offer', 'request', 'ack')),
        'pcap_http_guest_payload': any(f['protocol'] == 'TCP' and f['destination'] == endpoint and f['payload_bytes'] > 0 for f in flows),
        'pcap_http_host_payload': any(f['protocol'] == 'TCP' and f['source'] == endpoint and f['payload_bytes'] > 0 for f in flows),
    }
    compact = {'sha256': sha(raw), 'bytes': len(raw), 'packets': parsed['packets'], 'dhcp_message_types': message_types,
               'tcp_flow_count': sum(f['protocol'] == 'TCP' for f in flows)}
    return checks, compact

def one_session(api, args, index, firmware, fixture):
    output = args.out_dir / ('session-' + str(index)); output.mkdir()
    result = {'attempt': index, 'status': 'FAIL', 'checks': {}, 'started_at': datetime.now(timezone.utc).isoformat()}
    sid, latest, retained_serial, retained_frame = None, None, None, None
    request_offset = len(fixture.observations)
    try:
        latest = api.json('sessions', 'POST', payload={'device_id': 'core2', 'firmware_id': firmware['firmware_id'],
            'runtime': 'qemu-wifi', 'ttl_seconds': 300, 'ready_timeout_seconds': args.timeout,
            'ready_marker': 'CORE2_WIFI_RESULT: PASSED',
            'network': {'profile': 'core2-openmac', 'attempts': 1, 'capture_pcap': True,
                        'expected_markers': ['CORE2_WIFI_CONNECTED True', 'CORE2_HTTP_OK', 'CORE2_WIFI_RESULT: PASSED']}})
        sid = latest['session_id']; prefix = 'sessions/' + sid
        result['session_id'] = sid; result['firmware_sha256'] = firmware['sha256']
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            latest = api.json(prefix); save(output / 'session.json', latest)
            serial = api.json(prefix + '/serial?offset=0&limit=1048576')['data']
            (output / 'serial.log').write_text(serial, encoding='utf-8')
            checks, parsed = guest_checks(serial); result['checks'].update(checks)
            if FAILURE.search(serial) or latest['state'] in ('stopped', 'failed'):
                raise RuntimeError('guest WiFi probe failed or reset')
            if latest['state'] == 'running' and all(checks.values()): break
            time.sleep(.2)
        require(latest['state'] == 'running' and all(checks.values()), 'WiFi scan/association/DHCP/HTTP acceptance timed out')
        result['runtime_provenance'] = startup.runtime_provenance(api, latest, args.expected_runtime_sha256, args.runtime_source_receipt)
        result['pid'] = latest['pid']
        qom, radio = startup.collect_qom(api, prefix, offline=False)
        save(output / 'qom.json', qom); save(output / 'radio.json', radio)
        result['checks']['explicit_radio_enabled'] = radio.get('value') is True
        network = api.json(prefix + '/network'); save(output / 'network.json', network)
        result['checks']['network_marker_proof'] = network['status'] == 'PASS'
        observed = fixture.observations[request_offset:]
        save(output / 'http-requests.json', observed)
        result['controlled_http_requests'] = observed
        result['checks']['controlled_http_observed'] = len(observed) == 1 and observed[0]['path'] == '/' and observed[0]['host'] == 'core2-test' and observed[0]['status'] == 200
        frame = api.raw(prefix + '/frame.png'); (output / 'frame.png').write_bytes(frame)
        metrics = startup.png_metrics(frame); result['frame'] = {'width': metrics['width'], 'height': metrics['height'], 'bytes': len(frame), 'sha256': sha(frame)}
        result['checks']['frame_captured'] = metrics['width'] == 320 and metrics['height'] == 240
        result['checks']['runtime_unchanged'] = startup.runtime_provenance(api, latest, args.expected_runtime_sha256, args.runtime_source_receipt) == result['runtime_provenance']
    except Exception as error:
        result['error'] = str(error)
    finally:
        if sid:
            prefix = 'sessions/' + sid
            try:
                raw = api.raw(prefix + '/evidence'); (output / 'evidence.zip').write_bytes(raw)
                result['evidence'], retained_serial, retained_frame = startup.validate_bundle(raw, latest)
                checks, parsed = guest_checks(retained_serial)
                result['checks'].update({'zip_' + k: v for k, v in checks.items()})
                result['checks']['evidence_requested_running'] = result['evidence']['session_state'] == 'running'
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    capture = archive.read('network/capture.pcap')
                checks, result['pcap'] = packet_checks(capture, output, fixture.server_port)
                result['checks'].update(checks)
            except Exception as error: result['evidence_error'] = str(error)
            try:
                api.json(prefix + '?purge=0', 'DELETE')
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    history = api.json(prefix)
                    if history['state'] not in ('stopping', 'booting', 'running', 'provisioning', 'flashing'): break
                    time.sleep(.1)
                save(output / 'history.json', history)
                frame = api.raw(prefix + '/frame.png'); (output / 'history-frame.png').write_bytes(frame)
                serial = api.json(prefix + '/serial?offset=0&limit=1048576')['data']; (output / 'history-serial.log').write_text(serial)
                old_pid = latest.get('pid')
                checks = {'stopped_with_history': history['state'] == 'stopped',
                    'flash_released': history.get('flash_retained') is False,
                    'runtime_pid_gone': type(old_pid) is int and history.get('pid') in (None, old_pid) and not startup.process_identity(old_pid)['exists'],
                    'history_frame_exact': retained_frame is not None and frame == retained_frame,
                    'history_serial_retained': retained_serial is not None and serial.startswith(retained_serial)}
                guest, _ = guest_checks(serial); checks.update({'history_' + k: v for k, v in guest.items()})
                result['history'] = {'frame_sha256': sha(frame), 'serial_sha256': sha(serial.encode()), 'serial_bytes': len(serial.encode())}
                result['checks'].update(checks)
            except Exception as error: result['stop_error'] = str(error)
        result['status'] = 'PASS' if sid and result['checks'] and not any(k in result for k in ('error', 'evidence_error', 'stop_error')) and all(result['checks'].values()) else 'FAIL'
        save(output / 'result.json', result)
        print(json.dumps({'attempt': index, 'session_id': sid, 'status': result['status']}), flush=True)
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', required=True)
    parser.add_argument('--api', default='http://127.0.0.1:8787')
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--base', type=Path, default=ROOT / 'platform/.cache/firmware/core2/uiflow2.bin')
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--expected-runtime-sha256', '--expected-runtime-sha', dest='expected_runtime_sha256', required=True)
    parser.add_argument('--runtime-source-receipt', '--receipt', dest='runtime_source_receipt', type=Path,
                        default=ROOT / '.work/core2-runtime-final/source-receipt.json')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args(); require(10 <= args.timeout <= 300, 'timeout must be between 10 and 300 seconds')
    require(bool(re.fullmatch('[0-9a-f]{64}', args.expected_runtime_sha256)), 'runtime SHA256 is invalid')
    args.out_dir.mkdir(parents=True, exist_ok=False)
    api = startup.Api(args.api, args.token_file)
    fixture = ThreadingHTTPServer(('127.0.0.1', 0), Fixture); fixture.observations = []
    thread = threading.Thread(target=fixture.serve_forever, daemon=True); thread.start()
    report = {'schema_version': 1, 'kind': 'core2-explicit-wifi-two-session-regression', 'status': 'FAIL',
        'validation': 'virtual-device validation', 'hardware_validation': 'NOT RUN', 'runtime': 'qemu-wifi', 'profile': 'core2-openmac',
        'scope': 'Stock UIFlow2 WiFi scan/association/DHCP and a controlled local HTTP fixture; public networking and BLE are NOT RUN.',
        'runner_sha256': sha(Path(__file__).read_bytes())}
    try:
        base = args.base.read_bytes(); identity = startup.firmware_identity(base, startup.BASE_SHA256, startup.APP_SHA256)
        files_root = ROOT / 'tests/network/core2_openmac_wifi/files'
        original = (files_root / 'main.py').read_text(); require(original.count('__HTTP_PORT__') == 1, 'official probe HTTP port placeholder differs')
        source = original.replace('__HTTP_PORT__', str(fixture.server_port)); boot = (files_root / 'boot.py').read_text()
        image, metadata = build_uiflow_source_image(base, 16 << 20, {'main.py': source, 'boot.py': boot}, expected_base_sha256=startup.BASE_SHA256)
        require(metadata['preservation']['outside_vfs_unchanged'], 'composition changed stock executable/boot bytes')
        (args.out_dir / 'main.py').write_text(source); (args.out_dir / 'boot.py').write_text(boot)
        save(args.out_dir / 'composition.json', metadata)
        report['firmware'] = {'base_sha256': startup.BASE_SHA256, 'application_sha256': identity['application']['sha256'], 'derived_sha256': sha(image),
            'original_probe_sha256': sha(original.encode()), 'effective_probe_sha256': sha(source.encode()), 'boot_sha256': sha(boot.encode()),
            'only_original_source_substitution': '__HTTP_PORT__', 'm5_display_wrapper_added': False}
        artifact = api.json('artifacts', 'POST', body=image, headers={'Content-Type': 'application/octet-stream', 'X-Artifact-Name': 'core2-radio-regression.bin'})
        firmware = api.json('firmware', 'POST', payload={'device_id': 'core2', 'kind': 'merged', 'artifact_id': artifact['artifact_id']})
        require(firmware['sha256'] == sha(image), 'service image SHA256 differs'); save(args.out_dir / 'firmware.json', firmware)
        runs = [one_session(api, args, index, firmware, fixture) for index in (1, 2)]
        report['runs'] = runs
        report['checks'] = {'both_pass': all(r['status'] == 'PASS' for r in runs),
            'different_session_ids': len({r.get('session_id') for r in runs}) == 2,
            'different_process_ids': all(type(r.get('pid')) is int for r in runs) and len({r['pid'] for r in runs}) == 2,
            'same_firmware': all(r.get('firmware_sha256') == firmware['sha256'] for r in runs),
            'sequential_cleanup': all(r.get('checks', {}).get('runtime_pid_gone') is True for r in runs)}
        report['status'] = 'PASS' if all(report['checks'].values()) else 'FAIL'
    except Exception as error: report['error'] = str(error)
    finally:
        fixture.shutdown(); fixture.server_close(); thread.join(timeout=3)
        save(args.out_dir / 'summary.json', report)
    print(json.dumps({'status': report['status'], 'summary': str(args.out_dir / 'summary.json')}), flush=True)
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__': raise SystemExit(main())
