#!/usr/bin/env python3
"""Explicit Device Service Scroll validation; plan mode never starts a guest."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import uuid
import zipfile
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/units'))
from run_live_program import ProbeClient, poll, require, save
from run_live_package import decode_rejection, canonical
from run_host_cases import runtime_provenance
from scroll_protocol_probe import build_probe_source

DEVICES = ('cores3', 'atoms3r', 'sticks3', 'stopwatch')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def events(data, marker):
    result = []
    for line in data.splitlines(keepends=True):
        if line.startswith(marker + ' ') and line.endswith('\n'):
            try:
                row = json.loads(line[len(marker) + 1:])
            except ValueError:
                continue
            if isinstance(row, dict):
                result.append(row)
    return result


def unit_state(payload, session_id):
    require(payload.get('session_id') == session_id and payload.get('source') == 'live', 'Unit snapshot identity/source differs')
    rows = [row for row in payload.get('units', []) if row.get('id') == 'external1']
    require(len(rows) == 1 and rows[0].get('unit_id') == 'scroll' and rows[0].get('available') is True
            and rows[0].get('source') == 'guest-qom' and not rows[0].get('errors'), 'Scroll QOM unavailable')
    return rows[0]['properties']


def validate_bundle(data, report, submitted):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        require(archive.testzip() is None and len(names) == len(set(names)), 'invalid evidence ZIP')
        for name in names:
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name
                    and path.as_posix() == name, 'unsafe ZIP member path')
            require((archive.getinfo(name).external_attr >> 16) & 0xf000 != 0xa000, 'ZIP symlink member')
        manifest = json.loads(archive.read('manifest.json'))
        require(set(manifest['files']) == set(names) - {'manifest.json'}, 'ZIP manifest index differs')
        for name, row in manifest['files'].items():
            content = archive.read(name)
            require(type(row.get('size')) is int and row['size'] == len(content) and row.get('sha256') == sha(content), 'ZIP member size/hash differs')
        session = manifest['session']
        require(session['state'] == 'running' and all(session.get(key) == report[key] for key in
                ('session_id', 'device_id', 'runtime', 'pid', 'firmware_sha256', 'worker')), 'ZIP session identity differs')
        require(manifest['device']['device_id'] == report['device_id'], 'ZIP device identity differs')
        require({'serial.log', 'frames/current.png', 'qom/snapshot.json', 'units/contract.json',
                 'units/state.json', 'units/runtime.json'} <= set(names), 'data-plane evidence missing')
        require(json.loads(archive.read('units/runtime.json'))['attachments'] == report['attachments']
                and session['units'] == report['attachments'], 'ZIP frozen attachment differs')
        contract = json.loads(archive.read('units/contract.json'))
        require(contract['source_hashes'] == report['contract_hashes'], 'ZIP contract hashes differ')
        observed_units = json.loads(archive.read('units/state.json'))
        require(observed_units == manifest['units'] and observed_units['contract_hashes'] == report['contract_hashes'], 'ZIP Unit state/contract differs')
        unit_state(observed_units, report['session_id'])
        raw = archive.read('serial.log')
        text = raw.decode('utf-8', errors='replace')
        require(text.count('ESP-ROM:') == report['rom_banners'] and text.count('M5EMU_UART_REPL_READY') == 1, 'guest reboot/bootstrap repeated')
        for name, execution in report['executions'].items():
            program = execution['program']
            saved = json.loads(archive.read('programs/' + program['execution_id'] + '.json'))
            require(all(saved.get(key) == program[key] for key in ('execution_id', 'revision_id', 'source_sha256'))
                    and saved['pid'] == report['pid'] and saved['firmware_sha256'] == report['firmware_sha256']
                    and saved['state'] == 'completed', 'ZIP execution state or runtime differs')
            original = json.loads(archive.read('programs/' + program['revision_id'] + '/source.json'))
            files = {'main.py': submitted[name]}
            require(original == {'entrypoint': 'main.py', 'files': files}
                    and sha(canonical({'source_kind': 'uiflow2-python', **original})) == program['revision_id']
                    and sha(canonical(files)) == program['source_sha256'], 'ZIP original source/revision hash differs')
            metadata = json.loads(archive.read('programs/' + program['revision_id'] + '/revision.json'))
            require(all(metadata.get(key) == program[key] for key in ('revision_id', 'source_sha256'))
                    and metadata['source_kind'] == 'uiflow2-python' and metadata['entrypoint'] == 'main.py'
                    and metadata['total_source_bytes'] == len(submitted[name].encode())
                    and metadata['files'] == [{'path': 'main.py', 'size': len(submitted[name].encode()), 'sha256': sha(submitted[name].encode())}], 'ZIP revision metadata differs')
            observation = report['observations'][name]
            window = observation['serial']
            start, end = window['offset'], window['next_offset']
            require(type(start) is int and type(end) is int and type(observation['offset']) is int
                    and 0 <= start <= end <= len(raw) and start == observation['offset'], 'serial byte offsets invalid')
            require(sha(raw[:start].decode('utf-8', errors='replace').encode()) == observation['prefix_sha256'], 'serial prefix differs')
            require(raw[start:end].decode('utf-8', errors='replace') == window['data'], 'serial raw-byte offsets differ')
            require(f"__M5_EXEC_{program['execution_id']}__:START" in window['data'], 'execution START absent from fresh UART')
            require(f"__M5_EXEC_{program['execution_id']}__:DONE" in raw[start:].decode('utf-8', errors='replace'), 'execution DONE absent from UART')
            require(any(row.get('kind') == 'done' for row in events(window['data'], observation['marker'])), 'ZIP lacks fresh phase completion')
        frame = archive.read('frames/current.png')
        require(sha(frame) == report['final_frame']['sha256'], 'ZIP final frame differs')
        require(contract['units']['scroll']['id'] == 'scroll', 'frozen Scroll contract absent')
        require(session['program']['execution_id'] == next(reversed(report['executions'].values()))['program']['execution_id'], 'ZIP latest execution differs')
        return {'members': len(names), 'sha256': sha(data), 'original_source_and_serial_byte_windows': True}


def run(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = ProbeClient(args.api, args.out_dir)
    session_id, expected = None, None
    submitted = {}
    report = {'status': 'FAIL', 'schema_version': 1, 'captured_at': datetime.now(timezone.utc).isoformat(),
              'device_id': args.device, 'unit_id': 'scroll', 'runtime': 'qemu',
              'validation': 'virtual-device validation', 'hardware_validation': 'NOT RUN',
              'executions': {}, 'observations': {}, 'inputs': [], 'negative_controls': {},
              'source_sha256': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (Path(__file__).resolve(), ROOT / 'tests/units/scroll_protocol_probe.py')}}
    try:
        inventory = client.json('units?device_id=' + args.device)
        host = next(row for row in inventory['hosts'] if row['device_id'] == args.device)
        ports = [port for port in host['ports'] if port.get('visual_port') == 'grove' and port.get('wiring_status') == 'confirmed' and port.get('physical_presence') == 'main-device']
        require(len(ports) == 1, 'confirmed physical Grove port missing')
        port = ports[0]
        attachments = [{'id': 'external1', 'unit_id': 'scroll', 'port_id': port['id'], 'initial': {'source-count': 0, 'pressed': False}}]
        created = client.json('sessions', 'POST', {'device_id': args.device, 'runtime': 'qemu', 'program_mode': 'uiflow-live', 'ttl_seconds': 1200,
                              'ready_timeout_seconds': 40, 'units': attachments})
        session_id = created['session_id']; prefix = 'sessions/' + session_id
        save(args.out_dir / 'created.json', created)
        ready = poll(lambda: client.json(prefix), lambda row: row['state'] in {'running', 'failed', 'stopped'}, 100)
        require(ready['state'] == 'running', 'guest boot failed: ' + str(ready.get('error')))
        pins = created['units'][0]['pins']; require(pins == {key: port['pins'][key] for key in ('white', 'yellow')}, 'frozen pins differ')
        report.update(session_id=session_id, pid=ready['pid'], firmware_sha256=ready['firmware_sha256'], worker=ready['worker'], pins=pins,
                      attachments=created['units'], contract_hashes=client.json(prefix + '/units')['contract_hashes'])
        report['runtime_provenance'] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        serial = client.json(prefix + '/serial?offset=0&limit=1048576')
        report['rom_banners'] = serial['data'].count('ESP-ROM:')
        require(serial['data'].count('M5EMU_UART_REPL_READY') == 1, 'bootstrap marker missing')
        nonce = '/m5-scroll-' + uuid.uuid4().hex

        def state():
            payload = client.json(prefix + '/units')
            return unit_state(payload, session_id)

        def inject(values):
            before = state()
            posted = client.json(prefix + '/unit-input', 'POST', {'id': 'external1', 'values': values})
            after = unit_state(posted, session_id)
            require(all(type(after[k]) is type(v) and after[k] == v for k, v in values.items()), 'physical injection was not reflected by QOM')
            report['inputs'].append({'values': values, 'before': before, 'after': after})
            return after

        def reject(name, values, *, status=409, code='unit_input_rejected'):
            before = state()
            try:
                client.json(prefix + '/unit-input', 'POST', {'id': 'external1', 'values': values})
            except RuntimeError as error:
                rejection = decode_rejection(error)
            else:
                raise RuntimeError('unsupported physical source accepted: ' + name)
            after = state()
            keys = ('source-count', 'pressed', 'counter', 'increments', 'direction', 'input-events')
            require(all(after[key] == before[key] for key in keys), 'rejected physical source changed logical/physical state')
            require(rejection['status'] == status and rejection['response']['error']['code'] == code, 'unexpected input rejection')
            report['negative_controls'][name] = {'response': rejection, 'before': before, 'after': after}

        def phase(name, which, *, on_ready=None, extra='', **options):
            nonlocal expected
            before = client.json(prefix + '/serial?offset=0&limit=1048576')
            marker = 'SCROLL_' + str(len(submitted)).zfill(2) + '_' + uuid.uuid4().hex[:8].upper()
            source = build_probe_source(pins, which, marker=marker, **options)
            guard = f'import sys\nassert {nonce!r} in sys.path, "MicroPython VM reset"\n'
            if not submitted:
                guard = f'import sys\nsys.path.append({nonce!r})\n'
            source = guard + source + extra
            submitted[name] = source
            result = client.json(prefix + '/program', 'POST', {'source': source, 'expected_execution_id': expected, 'timeout_seconds': 20})
            expected = result['program']['execution_id']; report['executions'][name] = result
            require(result['program']['pid'] == report['pid'] and result['program']['firmware_sha256'] == report['firmware_sha256'], 'program replaced the device')
            def observe():
                current = client.json(prefix + '/program')['program']
                require(current['execution_id'] == expected and current['pid'] == report['pid']
                        and current['firmware_sha256'] == report['firmware_sha256']
                        and current['state'] not in {'failed', 'unknown', 'cancelled'}, 'phase failed or was replaced: ' + str(current))
                return client.json(prefix + f"/serial?offset={before['next_offset']}&limit=1048576")
            if on_ready:
                poll(observe, lambda row: any(event.get('kind') == 'ready' for event in events(row['data'], marker)), 30)
                on_ready()
            observed = poll(observe, lambda row: any(event.get('kind') == 'done' for event in events(row['data'], marker)), 40)
            def current_program():
                current = client.json(prefix + '/program')['program']
                require(current['execution_id'] == expected and current['pid'] == report['pid']
                        and current['firmware_sha256'] == report['firmware_sha256'], 'phase completion identity changed')
                return current
            current = poll(current_program, lambda row: row['state'] in {'completed', 'failed', 'unknown'}, 20)
            require(current['state'] == 'completed', 'phase did not finish')
            result['program'] = current
            report['observations'][name] = {'offset': before['next_offset'], 'prefix_sha256': sha(before['data'].encode()), 'marker': marker,
                                           'serial': observed, 'events': events(observed['data'], marker), 'state': state()}
            save(args.out_dir / (name + '.json'), report['observations'][name])
            return report['observations'][name]['state']

        phase('registers', 'registers')
        phase('versions', 'versions')
        def wake_source(target, pressed):
            # QOM properties are set individually. Publish the button first;
            # source-count is the guest's final wake-up condition.
            inject({'pressed': pressed})
            return inject({'source-count': target})
        for name, target, count, direction, ab, pressed, color in (
            ('forward', 123, 123, 1, 0, True, 0xff0000),
            ('backward', 100, -23, 0, 0, False, 0x00ff00),
            ('reversed-ab', 110, -10, 1, 1, True, 0x0000ff),
        ):
            after = phase(name, 'driver-live', expected_counter=count, expected_increment=count, expected_direction=direction,
                          ab_direction=ab, source_count=target, pressed=pressed, led_rgb=color,
                          on_ready=lambda target=target, pressed=pressed: wake_source(target, pressed))
            require(after['counter'] == count and after['increments'] == 0 and after['direction'] == direction and after['ab-direction'] == ab and after['led-rgb'] == color, 'original API/QOM result differs')
        phase('reset-baseline', 'registers', pressed=True)
        after = inject({'source-count': 115})
        require(after['counter'] == 5 and after['increments'] == 5, 'source baseline was reset by register operations')
        after = phase('increment-prime', 'snapshot-prime', reg=0x50, reads=(1,), expected_hex=('05',))
        require(after['increments'] == 0, 'selection must consume increment before complete read')
        inject({'source-count': 117})
        after = phase('increment-old-tx', 'snapshot-read', reads=(4,), expected_hex=('00000005',))
        require(after['counter'] == 7 and after['increments'] == 2, 'snapshot read consumed a later physical update')
        phase('increment-suffix-prime', 'snapshot-prime', reg=0x51, reads=(2,), expected_hex=('0000',))
        inject({'source-count': 116})
        after = phase('increment-suffix-old-tx', 'snapshot-read', reads=(4,), expected_hex=('00000000',))
        require(after['increments'] == -1, 'old suffix snapshot consumed new negative increment')
        after = phase('increment-next', 'snapshot-prime', reg=0x50, reads=(4,), expected_hex=('ffffffff',))
        require(after['increments'] == 0, 'new increment selection failed to clear')
        phase('raw-counter', 'set-counter', raw_counter=0x12345678)
        phase('counter-prime', 'snapshot-prime', reg=0x11, reads=(2,), expected_hex=('5634',))
        inject({'source-count': 117})
        phase('counter-old-tx', 'snapshot-read', reads=(4,), expected_hex=('12563412',))
        phase('counter-fresh', 'snapshot-prime', reg=0x10, reads=(4,), expected_hex=('79563412',))
        reject('unproven-large-timer-step', {'source-count': -32768})
        reject('timer-rollover-domain', {'source-count': 32768}, status=400, code='invalid_unit_input')
        phase('overflow-counter', 'set-counter', raw_counter=2**31 - 1)
        reject('non-atomic-mixed-input', {'pressed': False, 'source-count': 118}, status=400, code='invalid_unit_input')
        reject('int32-overflow', {'source-count': 118})
        phase('restore-after-overflow', 'registers', pressed=True)
        after = phase('address-change', 'address-change')
        require(after['i2c-address'] == 0x41, 'new live address not reflected by controller')
        after = phase('address-restore', 'address-restore', address=0x41, target_address=0x40)
        require(after['i2c-address'] == 0x40, 'live address restore failed')
        before = state()
        phase('address-zero-gap', 'versions', extra="\n_write(b'\\xff\\x00')\n_check(_hex(_register(0xFE, 1)), '01', 'zero-address-gap-keeps-old-data-plane')\n")
        after = state()
        require(after['i2c-address'] == 0x40 and after['command-errors'] > before['command-errors'], 'address-zero gap was hidden')
        after = phase('bootloader-gap', 'bootloader')
        require(after['bootloader-supported'] is False and after['bootloader-requests'] >= 1 and after['timer-rollover-supported'] is False
                and after['zero-address-unicast-supported'] is False, 'unsupported paths were advertised as implemented')
        phase('final-recovery', 'registers', pressed=True, led_rgb=0x123456,
              extra="\nscreen=M5.Display\nscreen.setBrightness(255)\nscreen.fillScreen(0x123456)\nscreen.setTextColor(0xffffff, 0x123456)\nscreen.setTextSize(1)\nscreen.setCursor(screen.width()//2-30, screen.height()//2)\nscreen.print('SCROLL OK')\n")
        report['final_state'] = state()
        require(report['final_state']['source-count'] == 117 and report['final_state']['led-rgb'] == 0x123456, 'final recovery state differs')
        frame = client.raw(prefix + '/frame.png'); (args.out_dir / 'frame.png').write_bytes(frame)
        with Image.open(io.BytesIO(frame)) as image:
            image.load(); require(image.format == 'PNG', 'invalid frame')
            colored = sum(all(abs(a-b) <= 8 for a,b in zip(pixel,(0x12,0x34,0x56))) for pixel in image.convert('RGB').getdata())
            require(colored > image.width * image.height * .6, 'recovery application frame absent')
            report['final_frame'] = {'sha256': sha(frame), 'size': list(image.size), 'application_color_pixels': colored}
        report['final_runtime_provenance'] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        current = client.json(prefix)
        require(current['pid'] == report['pid'] and current['firmware_sha256'] == report['firmware_sha256'] and current['worker'] == report['worker'], 'runtime owner changed')
        data = client.raw(prefix + '/evidence'); (args.out_dir / 'evidence.zip').write_bytes(data)
        report['evidence'] = validate_bundle(data, report, submitted)
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    finally:
        if session_id:
            try:
                if not (args.out_dir / 'evidence.zip').exists():
                    (args.out_dir / 'failure-evidence.zip').write_bytes(client.raw('sessions/' + session_id + '/evidence'))
            except Exception as error:
                report.update(status='FAIL', evidence_error=str(error))
            try:
                stopped = client.json('sessions/' + session_id + '?purge=0', 'DELETE')
                stopped = poll(lambda: client.json('sessions/' + session_id), lambda row: row['state'] in {'stopped', 'failed'}, 40)
                require(stopped['state'] == 'stopped' and stopped['flash_retained'] is False and stopped['last_frame_available'] is True, 'cleanup/history failed')
                save(args.out_dir / 'stopped.json', stopped)
                report['cleanup'] = {'history_retained': True, 'flash_retained': False, 'last_frame_available': True}
            except Exception as error:
                report.update(status='FAIL', cleanup_error=str(error))
        save(args.out_dir / 'report.json', report)
    require(report['status'] == 'PASS', report.get('error') or report.get('cleanup_error') or report.get('evidence_error') or 'Scroll validation failed')
    print(json.dumps({'status': 'PASS', 'session_id': session_id, 'device': args.device, 'executions': len(report['executions'])}))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api', default='http://127.0.0.1:8787')
    parser.add_argument('--device', choices=DEVICES, default='cores3')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--expected-runtime-sha256')
    parser.add_argument('--out-dir', type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({'status': 'PLANNED_NOT_EXECUTED', 'device': args.device, 'unit': 'scroll', 'controller_execution': 'NOT RUN',
                          'scope': 'bounded source TIM16 subset; original API, raw register snapshots and explicit unsupported paths',
                          'hardware_validation': 'NOT RUN'}))
        return
    if args.out_dir is None or args.out_dir.exists() or not re.fullmatch('[0-9a-f]{64}', args.expected_runtime_sha256 or ''):
        parser.error('--execute needs new --out-dir and exact --expected-runtime-sha256')
    run(args)


if __name__ == '__main__':
    main()
