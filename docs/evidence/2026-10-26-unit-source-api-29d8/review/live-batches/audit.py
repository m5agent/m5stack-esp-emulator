"""Independent offline audit: local evidence bytes only, no network/process APIs."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNTIME = '29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
BASE = '1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264'
FAILURES = ('IO_PROBE_FAIL', 'CONTROL_PROBE_ERROR', 'Traceback (most recent call last)', 'Guru Meditation', 'A fatal error occurred', 'Rebooting...')

def load(path): return json.loads(path.read_bytes())
def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
def require(ok, message):
    if not ok: raise AssertionError(message)
def props(state): return state['units'][0]['properties']
def entries(directory):
    rows = load(directory / 'http/index.json')
    for row in rows:
        raw = (directory / 'http' / row['response_file']).read_bytes()
        require(len(raw) == row['response_size'] and sha(raw) == row['response_sha256'], 'HTTP transcript response digest/length differs')
        row['_raw'] = raw
        try: row['_json'] = json.loads(raw)
        except (ValueError, UnicodeDecodeError): row['_json'] = None
        request = (directory / 'http' / row['request_file']).read_bytes()
        try: row['_request'] = json.loads(request)
        except (ValueError, UnicodeDecodeError): row['_request'] = None
    return rows

def audit_case(batch, case):
    directory = batch / case
    result = load(directory / 'result.json')
    source_request = load(directory / 'source-request.json')
    firmware = load(directory / 'firmware-response.json')
    source = firmware['source']; metadata = source['metadata']
    http = entries(directory)
    sid = result['session_id']; path = '/api/v1/sessions/' + sid
    require(result['status'] == 'PASS' and result['hardware_validation'] == 'NOT RUN', 'case status/category differs')
    require(firmware['kind'] == source['kind'] == 'uiflow', 'source composition kind differs')
    for filename, value in source_request['files'].items():
        require((directory / 'files' / filename).read_bytes() == value.encode('utf-8'), 'caller source text differs: ' + filename)
        row = next(row for row in metadata['files'] if row['path'] == filename)
        require(row['origin'] == 'caller' and row['sha256'] == sha(value.encode()) and row['size'] == len(value.encode()), 'file metadata differs')
    source_sha = sha(canonical(source_request['files']))
    require(source_sha == source['artifact_id'] == metadata['source_sha256'] == result['source_cas_sha256'], 'canonical caller CAS binding differs')
    require(metadata['base_sha256'] == source_request['expected_base_sha256'] == BASE, 'reference base differs')
    require(metadata['firmware_sha256'] == firmware['sha256'] == firmware['firmware_id'] == result['firmware_sha256'], 'derived image binding differs')
    require(metadata['status'] == 'COMPOSED_NOT_EXECUTED', 'packaging status was promoted to runtime PASS')
    require(all(metadata['preservation'][name] is True for name in ('outside_vfs_unchanged', 'existing_files_readback_verified', 'source_readback_verified')), 'VFS composition/readback metadata incomplete')
    require(any(row['method'] == 'POST' and row['path'] == '/api/v1/firmware/uiflow' and row['status'] == 201 and row['_request'] == source_request and row['_json'] == firmware for row in http), 'source request/response lacks matching real HTTP capture')
    session_request = load(directory / 'session-request.json')
    require(session_request['uiflow_source_sha256'] == source_sha and session_request['firmware_id'] == firmware['firmware_id'], 'session source pin/image differs')
    require(any(row['method'] == 'POST' and row['path'] == '/api/v1/sessions' and row['status'] == 202 and row['_request'] == session_request and row['_json']['session_id'] == sid for row in http), 'session request not captured')
    negative_codes = set()
    for row in http:
        if row['method'] == 'POST' and row['path'] == '/api/v1/sessions' and row['status'] in (400, 409):
            negative_codes.add((row['status'], row['_json']['error']['code']))
    require({(400, 'uiflow_source_binding_required'), (409, 'uiflow_source_binding_mismatch')} <= negative_codes, 'source pin HTTP negatives absent')
    require(load(directory / 'after-pin-negative-health.json')['capacity']['active_sessions'] == 0, 'negative pin reserved runtime')
    proof = load(batch / 'browser' / sid / 'runtime-provenance.json')
    running = load(directory / 'running-session.json')
    require(proof == result['runtime_provenance'] and proof['status'] == 'VERIFIED' and proof['kind'] == 'direct-pid', 'runtime proof differs')
    require(proof['runtime_binary_sha256'] == RUNTIME and proof['observed_pid'] == running['pid'], 'runtime hash/PID differs')
    require(proof['worker_generation'] == 11 and proof['firmware_sha256'] == firmware['firmware_id'], 'generation/image proof differs')
    require(running['firmware_provenance'] == source, 'running provenance differs')
    require(any(row['path'] == path and row['_json'] == running for row in http), 'running PID/provenance snapshot lacks actual HTTP capture')
    serial = (directory / 'serial.txt').read_bytes().decode('utf-8')
    require(not any(value in serial for value in FAILURES), 'guest failure in saved serial')
    for marker in result['required_markers']:
        require(re.search(r'(?m)^' + re.escape(marker) + r'\r?$', serial), 'required guest marker missing')
    fresh = []
    for index, step in enumerate(result['steps']):
        if 'serial_offset' not in step: continue
        before = (directory / f'steps/{index:02d}-before.txt').read_bytes().decode()
        after = (directory / f'steps/{index:02d}-after.txt').read_bytes().decode()
        require(after.startswith(before) and len(before) == step['serial_offset'], 'fresh serial prefix/offset differs')
        require(sha(before.encode()) == step['before_sha256'] and sha(after.encode()) == step['after_sha256'], 'fresh serial hashes differ')
        delta = after[len(before):]
        require(delta == step['fresh_serial'], 'reported fresh delta differs')
        qom = props(load(directory / step['state_file']))
        values = step['values']
        if case == 'button':
            require(re.search(r'(?m)^UNIT_BUTTON %d\r?$' % (0 if values['pressed'] else 1), delta) and qom['pressed'] is values['pressed'], 'fresh GPIO press/readback differs')
        elif case == 'encoder':
            require(re.search(r'(?m)^CONTROL_ENCODER %d %d\r?$' % (values['counter'], int(values['pressed'])), delta), 'fresh signed encoder marker absent')
            require(qom['counter'] == values['counter'] and qom['pressed'] is values['pressed'], 'encoder QOM differs')
        elif case == 'env-iii':
            vectors = re.findall(r'(?m)^UNIT_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$', delta)
            require(any(all(abs(float(a)-b) < tolerance for a,b,tolerance in zip(vector, step['expected_vector'], (.2,.2,1))) for vector in vectors), 'fresh compensated ENV vector absent')
            require(all(abs(qom[k]-v)<1e-6 for k,v in values.items()), 'ENV QOM inputs differ')
        fresh.append({'serial_offset':step['serial_offset'], 'values':values, 'fresh_serial':delta})
    state = load(directory / 'final-units.json')
    require(state == result['unit_state'] and state['source'] == 'live' and state['contract_status'] == 'frozen', 'final live frozen QOM differs')
    require(any(row['_json'] == state and row['path'] == path + '/units' for row in http), 'QOM state absent in captured HTTP')
    final_props = props(state)
    if case in ('env-iii', 'encoder'):
        require(all(final_props[k] > 0 for k in ('transactions','read-bytes','written-bytes','input-events')), 'I2C data plane counters absent')
    if case == 'button': require(final_props['input-events'] == 4, 'Button input event count differs')
    if case == 'relay':
        delta = serial[result['relay_fresh_offset']:]
        require('UNIT_RELAY 0' in delta and 'UNIT_RELAY 1' in delta, 'fresh guest relay cycle absent')
        require([step['properties']['output-level'] for step in result['steps']] == [False,True], 'relay output snapshots differ')
        require(final_props['output-transitions'] > props(load(directory/'initial-units.json'))['output-transitions'], 'new relay GPIO transitions absent')
    zip_data = (directory / 'evidence.zip').read_bytes()
    require(sha(zip_data) == result['evidence_sha256'], 'ZIP digest differs')
    with zipfile.ZipFile(directory / 'evidence.zip') as archive:
        require(archive.testzip() is None and len(archive.namelist()) == len(set(archive.namelist())), 'ZIP corrupt or duplicate names')
        manifest = json.loads(archive.read('manifest.json'))
        require(set(manifest['files']) == set(archive.namelist())-{'manifest.json'}, 'ZIP index differs')
        for name, info in manifest['files'].items():
            raw = archive.read(name)
            require(len(raw) == info['size'] and sha(raw) == info['sha256'], 'ZIP member differs: '+name)
        session = manifest['session']
        require(session['state'] == 'running' and session['session_id'] == sid and session['pid'] == proof['observed_pid'], 'ZIP runtime session/PID differs')
        require(session['worker']['worker_id'] == proof['worker_id'] and session['worker']['generation'] == 11 and session['worker']['lease_active'] is True, 'ZIP worker proof differs')
        require(session['firmware_sha256'] == firmware['sha256'] and session['firmware_provenance'] == source == json.loads(archive.read('firmware/uiflow-source.json')), 'ZIP source provenance differs')
        require(session['source_artifacts'][0] == source_sha, 'ZIP caller source CAS differs')
        zip_serial = archive.read('serial.log')
        require(zip_serial.decode().startswith(serial), 'ZIP serial prefix differs')
        require(json.loads(archive.read('units/state.json'))['contract_hashes'] == state['contract_hashes'], 'ZIP Unit contract differs')
    evidence_events = [index for index,row in enumerate(http) if row['path'] == path+'/evidence' and row['_raw'] == zip_data and row['status'] == 200]
    stop_events = [index for index,row in enumerate(http) if row['path'] == path and row['method'] == 'DELETE' and row['query'] == 'purge=0' and row['status'] == 200]
    require(evidence_events and stop_events and max(evidence_events) < min(stop_events), 'ZIP was not captured before retained stop')
    serial_chunks = 0
    for index, row in enumerate(http):
        if row['path'] == path+'/serial' and row['status'] == 200 and index < max(evidence_events):
            chunk = row['_json']; begin,end = chunk['offset'],chunk['next_offset']
            require(chunk['session_id'] == sid and end-begin == chunk['bytes'], 'HTTP serial range differs')
            require(zip_serial[begin:end].decode() == chunk['data'], 'ZIP guest serial differs from actual HTTP serial chunk')
            serial_chunks += 1
    require(serial_chunks > 0, 'raw serial HTTP chunks absent')
    retained = load(directory/'retained-session.json')
    require(retained['state'] == 'stopped' and retained['flash_retained'] is False and retained['firmware_provenance'] == source, 'retained history/flash/provenance differs')
    health = load(directory/'cleanup-health.json')
    require(health['capacity']['active_sessions'] == 0 and health['capacity']['worker']['active_lease_count'] == 0, 'cleanup lease/capacity not idle')
    require(any(row['_json'] == retained and row['path'] == path for row in http), 'retained session lacks raw HTTP match')
    require(any(row['_json'] == health and row['path'] == '/api/v1/health' for row in http), 'cleanup health lacks raw HTTP match')
    require(result['cleanup']['pid_gone'] is True and result['cleanup']['owned_pid'] == proof['observed_pid'], 'recorded process cleanup differs')
    web = load(batch / 'browser' / sid / 'web-report.json')
    require(web['session_id'] == sid and web['firmware_sha256'] == firmware['sha256'] and web['hardware_execution'] == 'NOT RUN' and not web['errors'], 'browser session/error/category differs')
    running_snapshots = [snap for snap in web['snapshots'] if snap['session_state'] == 'running']
    require(running_snapshots, 'no running DOM snapshots')
    for snap in running_snapshots:
        require(len(snap['units']) == 1, 'DOM attachment tree differs')
        unit = snap['units'][0]; properties = unit['readback']['properties']
        require(unit['instance'] == 'external1' and unit['mounted_port'] == 'grove', 'DOM port/instance differs')
        require(any(any(item['id'] == unit['instance'] and item.get('properties') == properties for item in row.get('response',{}).get('units',[])) for row in web['readbacks']+web['posts']), 'DOM has no matching captured real browser HTTP response')
        for name,value in properties.items():
            dom = next(row for row in unit['values'] if row['field'] == name)
            if name == 'led-rgb' and dom.get('rgb'):
                require(dom['rgb'] == [f'LED[{i}] #{color:06x}' for i,color in enumerate(value)], 'RGB DOM labels differ from HTTP colors')
            else:
                expected = json.dumps(value,separators=(',',':')) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                require(dom['text'] == expected, 'DOM text differs from actual HTTP: '+name)
        if snap.get('screenshot'): require((batch/'browser'/sid/snap['screenshot']).is_file(), 'DOM screenshot missing')
    for filename, digest in web['source_sha256'].items():
        require(sha((REPO/filename).read_bytes()) == digest, 'browser source hash differs from repository: '+filename)
    out = {'case':case,'status':'PASS','session_id':sid,'source_cas_sha256':source_sha,'firmware_sha256':firmware['sha256'],'runtime':{'sha256':RUNTIME,'pid':proof['observed_pid'],'generation':proof['worker_generation']},'http_events_verified':len(http),'serial_http_chunks_verified':serial_chunks,'fresh_serial_steps':fresh,'final_properties':final_props,'evidence_sha256':sha(zip_data),'web':{'running_snapshots':len(running_snapshots),'posts':len(web['posts']),'actions':len(web['actions'])},'cleanup':{'retained_state':retained['state'],'flash_retained':retained['flash_retained'],'active_sessions':health['capacity']['active_sessions'],'pid_gone_recorded':result['cleanup']['pid_gone']}}
    if case == 'rgb':
        events = load(directory/'observation-index.json')
        phases = []
        for marker in ('IO_RGB_FULL 1','IO_RGB_SHORT 1','IO_RGB_FULL 2'):
            position = next(i for i,e in enumerate(events) if e.get('marker') == marker)
            event = events[position]; raw=(directory/event['file']).read_bytes().decode()
            require(re.search(r'(?m)^'+re.escape(marker)+r'\r?$',raw[event['offset']:]), 'RGB marker not in fresh observation window')
            follow = next(e for e in events[position+1:] if e['kind']=='state')
            observed=load(directory/follow['file'])
            require(any(row['_json']==observed and row['path']==path+'/units' for row in http), 'RGB phase state lacks real HTTP capture')
            phases.append({'marker':marker,'serial_offset':event['offset'],'state_file':follow['file'],'captured_at':observed['captured_at'],'properties':props(observed)})
        first,short,last=[phase['properties'] for phase in phases]
        require(first['led-rgb']==[0x112233,0x445566,0x778899], 'first full three-LED chain differs')
        require(short['led-rgb']==first['led-rgb'] and short['led-frames']==first['led-frames'] and short['output-transitions']==first['output-transitions'] and short['incomplete-frames']>first['incomplete-frames'], 'short frame mutated complete chain or lacked reject counter')
        require(last['led-rgb']==[0xA1B2C3,0x010203,0x040506] and last['led-frames']>short['led-frames'], 'second full three-LED chain did not advance')
        require(phases[0]['captured_at'] < phases[1]['captured_at'] < phases[2]['captured_at'], 'RGB captured phase ordering differs')
        controller={e['property']:e['value'] for e in events if e['kind']=='qom' and e['path']=='/machine/rmt0'}
        require(controller==result['rmt_controller'] and controller['tx-symbols']>=168 and controller['tx-threshold-events']>0 and controller['tx-completions']>=3 and controller['tx-errors']==0,'native RMT counters differ')
        out['rgb_sequence']=phases;out['rmt']=controller
    return out

def main():
    report={'category':'independent-offline-recorded-virtual-device-review','api_calls':'NOT RUN','new_guest_or_hardware_execution':'NOT RUN','current_runtime_or_hardware_claim':'none','batches':{}}
    for batch_name in ['live-five-r1','live-button-r1']:
        batch=REPO/'.work/unit-agent-api-live-20261026'/batch_name
        digest_count=0
        for line in (batch/'SHA256SUMS').read_text().splitlines():
            digest,filename=line.split('  ',1);target=(batch/filename).resolve()
            require(target.is_relative_to(batch.resolve()) and sha(target.read_bytes())==digest,'frozen file changed: '+filename)
            digest_count+=1
        rows=load(batch/'prepared.json')['cases'];cases=[]
        for row in rows:
            cases.append(audit_case(batch,row['unit_id']))
        negative_http = load(batch/'batch-http/index.json')
        codes=[]
        for row in negative_http:
            raw=(batch/'batch-http'/row['response_file']).read_bytes()
            require(len(raw)==row['response_size'] and sha(raw)==row['response_sha256'], 'batch HTTP transcript differs')
            if row['method']=='POST':
                error=json.loads(raw)['error']['code']; codes.append((row['status'],error))
        require(set(codes)=={(409,'uiflow_base_hash_mismatch'),(400,'invalid_uiflow_source_path')}, 'source API raw negative statuses differ')
        report['batches'][batch_name]={'status':'PASS','frozen_files_verified':digest_count,'source_negative_http':codes,'cases':cases}
    report['status']='PASS'
    (OUT/'independent-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'batches':{name:{'cases':len(value['cases']),'frozen_files':value['frozen_files_verified']} for name,value in report['batches'].items()}},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
