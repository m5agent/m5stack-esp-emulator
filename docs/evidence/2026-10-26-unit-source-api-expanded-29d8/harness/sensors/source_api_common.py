#!/usr/bin/env python3
"""Prepare source-only requests, or explicitly execute real API/browser Unit acceptance.

Default: offline request preparation only. No BIN builder, artifact upload,
HTTP request, browser or QEMU is used unless --execute is supplied by root.
--check validates saved evidence offline without contacting the service.
"""
from __future__ import annotations
import argparse, ast, collections, hashlib, io, json, os, pathlib, re, shutil, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from datetime import datetime, timezone

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
UNIT=ROOT/'tests/units'
BASE='1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264'
RUNTIME='29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
CASES=('button','relay','env-iii','rgb','encoder')
FAILURES=('IO_PROBE_FAIL','CONTROL_PROBE_ERROR','Traceback (most recent call last)','Guru Meditation','A fatal error occurred','Rebooting...')

def need(condition,message):
    if not condition: raise RuntimeError(message)
def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def load(path):return json.loads(path.read_bytes())
def now():return datetime.now(timezone.utc).isoformat()
def guarded_directory(path):
    path=path.resolve();need(path.is_relative_to(HERE) and path!=HERE,'outputs must be in a fresh child of this harness directory');return path

def source_files(case):
    mapping={};origins={}
    def add(target,source):
        data=source.read_bytes();text=data.decode('utf-8');need(text.encode('utf-8')==data,'source UTF-8 bytes changed')
        mapping[target]=text;origins[target]={'repository_path':source.relative_to(ROOT).as_posix(),'size':len(data),'sha256':sha(data),'copy':'byte-exact'}
    add('boot.py',UNIT/'probe/boot.py')
    if case in ('button','relay','env-iii'):
        add('main.py',UNIT/'probe/main.py')
    elif case=='rgb':
        for name in ('main.py','io_program.py','probe_logging.py'):add(name,UNIT/'io_probe'/name)
        for name in ('__init__.py','rgb.py'):add('io_drivers/'+name,UNIT/'io_probe/io_drivers'/name)
    else:
        add('main.py',UNIT/'controls_probe/main.py')
        for name in ('__init__.py','encoder.py','unit_helper.py'):add('control_drivers/'+name,UNIT/'controls_probe/control_drivers'/name)
    ports=load(ROOT/'platform/units/host-ports.json')['hosts']
    host=next(row for row in ports if row['device_id']=='cores3')
    choices=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device']
    need(len(choices)==1,'CoreS3 must have one confirmed main Grove connector');port=choices[0]
    config={'CASE':case,'WHITE':port['pins']['white'],'YELLOW':port['pins']['yellow'],'DEVICE_ID':'cores3'}
    if case=='rgb':config['IR_CALLBACK_ROOT_PATCH']=False
    text=''.join(f'{k} = {v!r}\n' for k,v in config.items());mapping['probe_config.py']=text
    origins['probe_config.py']={'copy':'generated-explicit-probe-config','size':len(text.encode()),'sha256':sha(text.encode()),'host_ports_sha256':sha((ROOT/'platform/units/host-ports.json').read_bytes())}
    for name,text in mapping.items():ast.parse(text,filename=name)
    # Prove selected vendored driver bytes before preparing any request.
    package='io_drivers' if case=='rgb' else 'control_drivers' if case=='encoder' else None
    driver_proof={}
    if package:
        parent=UNIT/('io_probe' if case=='rgb' else 'controls_probe')/package
        manifest=load(parent/'source-manifest.json')
        for name,text in mapping.items():
            if name.startswith(package+'/') and name.split('/',1)[1] in manifest:
                record=manifest[name.split('/',1)[1]]
                need(sha(text.encode())==record['sha256'],'vendored official driver hash mismatch: '+name)
                driver_proof[name]=record
    return dict(sorted(mapping.items())),origins,port,driver_proof

def prepare(output,cases):
    need(not output.exists(),'choose a fresh output directory; existing evidence is preserved');output.mkdir(parents=True)
    tooling=['tests/units/run_service_cases.py','tests/units/run_io_cases.py','tests/units/run_control_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js','platform/units/host-ports.json','platform/units/runtime-profiles.json','platform/units/catalog.json','platform/tools/unit_runtime.py','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py']
    freeze={}
    for name in tooling:
        data=(ROOT/name).read_bytes();freeze[name]=sha(data)
        target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    harness=pathlib.Path(__file__).read_bytes();freeze['HARNESS/run_api_acceptance.py']=sha(harness)
    target=output/'source-snapshot/HARNESS/run_api_acceptance.py.txt';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(harness)
    save(output/'tooling-source-freeze.json',freeze)
    prepared=[]
    for case in cases:
        directory=output/case;directory.mkdir()
        files,origins,port,drivers=source_files(case)
        request={'device_id':'cores3','files':files,'expected_base_sha256':BASE}
        save(directory/'source-request.json',request)
        for name,text in files.items():
            target=directory/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode())
        save(directory/'guest-source-freeze.json',origins)
        save(directory/'official-driver-proof.json',drivers)
        for package,source in [('io_drivers',UNIT/'io_probe/io_drivers/LICENSE.MIT'),('control_drivers',UNIT/'controls_probe/control_drivers/LICENSE.MIT')]:
            if any(name.startswith(package+'/') for name in files):
                target=directory/'license-evidence'/package/'LICENSE.MIT';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        row={'unit_id':case,'device_id':'cores3','runtime':'qemu','base_sha256':BASE,'expected_runtime_sha256':RUNTIME,'source_cas_sha256':sha(canonical(files)),'files':{name:{'sha256':sha(text.encode()),'size':len(text.encode())} for name,text in files.items()},'port':port,'attachments':[{'id':'external1','unit_id':case,'port_id':port['id']}],'ready_marker':('IO_PROBE_READY' if case=='rgb' else 'CONTROL_PROBE_READY' if case=='encoder' else 'UNIT_PROBE_READY')+' '+case,'status':'PREPARED_NO_API_OR_RUNTIME'}
        save(directory/'prepared.json',row);prepared.append(row)
    save(output/'prepared.json',{'created_at':now(),'status':'PREPARED_NO_API_OR_RUNTIME','cases':prepared,'source_intake':'POST /api/v1/firmware/uiflow','binary_build_or_upload':False})
    return prepared

class HTTPRecorder:
    """Record actual urllib traffic; all reads return the original response bytes."""
    def __init__(self,directory):self.directory=directory;self.events=[];self.original=None
    def __enter__(self):
        self.directory.mkdir(parents=True,exist_ok=True);self.original=urllib.request.urlopen;urllib.request.urlopen=self.open;return self
    def __exit__(self,*args):
        urllib.request.urlopen=self.original;save(self.directory/'index.json',self.events)
    def open(self,request,*args,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else str(request)
        method=request.get_method() if isinstance(request,urllib.request.Request) else 'GET'
        need(urllib.parse.urlparse(url).hostname in {'127.0.0.1','localhost','::1'},'runner records only the local Device Service')
        number=len(self.events);prefix=f'{number:05d}';body=getattr(request,'data',None)
        event={'at':now(),'method':method,'url':url,'path':urllib.parse.urlsplit(url).path,'query':urllib.parse.urlsplit(url).query,'request_file':prefix+'.request.raw','response_file':prefix+'.response.raw'}
        self.events.append(event);(self.directory/event['request_file']).write_bytes(body or b'')
        def record(data):
            target=self.directory/event['response_file']
            with target.open('ab') as stream:stream.write(data)
            event['response_sha256']=sha(target.read_bytes());event['response_size']=target.stat().st_size
            save(self.directory/'index.json',self.events)
            return data
        try:response=self.original(request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            event['status']=error.code;real_read=error.read
            def audited_error_read(*read_args,**read_kwargs):return record(real_read(*read_args,**read_kwargs))
            error.read=audited_error_read
            raise
        event['status']=response.status
        class Response:
            def __enter__(self):response.__enter__();return self
            def __exit__(self,*values):return response.__exit__(*values)
            def __getattr__(self,name):return getattr(response,name)
            def read(self,*values,**options):return record(response.read(*values,**options))
        return Response()

def source_provenance(firmware,request):
    files=request['files'];source=firmware['source'];meta=source['metadata'];caller_sha=sha(canonical(files))
    need(source['kind']=='uiflow' and source['artifact_id']==caller_sha,'firmware source kind/CAS does not match canonical caller files')
    need(meta['base_sha256']==BASE and meta['source_sha256']==caller_sha,'source API base/source SHA differs')
    need(meta['firmware_sha256']==firmware['sha256']==firmware['firmware_id'],'returned firmware identity differs')
    entries={entry['path']:entry for entry in meta['files']}
    need(len(entries)==len(meta['files']) and set(entries)==set(files),'effective source file set differs from caller file set')
    for name,text in files.items():
        need(entries[name]['sha256']==sha(text.encode()) and entries[name]['size']==len(text.encode()),'source API file size/hash differs: '+name)
        need(entries[name].get('origin')=='caller','source was not preserved as caller bytes: '+name)
    need(meta['generated_files']==[],'unexpected source generation despite explicit caller boot/main')
    need(meta['effective_source_sha256']==caller_sha,'effective source identity differs')
    for field in ('vfs','toolchain','preservation'):need(isinstance(meta[field],dict) and bool(meta[field]),'source metadata missing '+field)
    need(meta['status']=='COMPOSED_NOT_EXECUTED' and meta['kind']=='uiflow2-source-composition','source composition overclaims guest execution')
    need(meta['vfs']['filesystem']=='LittleFS' and meta['vfs']['source']=='actual-base-partition-table','source VFS metadata has no actual partition layout')
    need(all(meta['preservation'].get(k) is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified')),'source composition/readback preservation failed')
    need(meta['caller_file_count']==len(files) and meta['caller_source_bytes']==sum(len(s.encode()) for s in files.values()),'caller source totals differ')
    return source

def input_negative(client,session_id,values,stable_fields,directory):
    before=client.json(f'sessions/{session_id}/units',via_ui=False)
    try:
        client.json(f'sessions/{session_id}/unit-input',method='POST',payload={'id':'external1','values':values},via_ui=False)
    except RuntimeError as error:
        need(re.search(r'HTTP (400|409)\b',str(error)) is not None,'invalid input failed outside expected API rejection')
        failure=str(error)
    else:raise RuntimeError('invalid Unit input was accepted')
    after=client.json(f'sessions/{session_id}/units',via_ui=False)
    b=before['units'][0]['properties'];a=after['units'][0]['properties']
    need(all(a[key]==b[key] for key in (*stable_fields,'input-events')),'rejected Unit input changed physical input state')
    save(directory/'negative-input.json',{'request':{'id':'external1','values':values},'error':failure,'before':before,'after':after,'unchanged_fields':[*stable_fields,'input-events']})

def source_negatives(client,request,output):
    cases=[('wrong-base',{**request,'expected_base_sha256':'0'*64}),('path-traversal',{**request,'files':{'main.py':'print("no runtime should be created")\n','../escape.py':'pass\n'}})]
    results=[]
    for label,payload in cases:
        try:client.json('firmware/uiflow',method='POST',payload=payload,via_ui=False)
        except RuntimeError as error:
            need(re.search(r'HTTP (400|409)\b',str(error)) is not None,'source negative failed outside expected API rejection')
            results.append({'case':label,'status':'REJECTED','error':str(error)})
        else:raise RuntimeError('source negative was accepted: '+label)
    save(output/'source-api-negatives.json',results)

def pid_gone(pid):
    try:os.kill(pid,0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False

def frame_valid(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load();need(image.format=='PNG' and image.size==(320,240),'native framebuffer format or geometry differs')
        need(len(image.convert('RGB').getcolors(maxcolors=1) or [])==0,'native framebuffer has only one color')
    return {'sha256':sha(data),'size':len(data),'width':320,'height':240}

def check_browser(report,session_id,firmware_sha):
    need(report['session_id']==session_id and report['firmware_sha256']==firmware_sha,'browser session/firmware identity differs')
    need(not report.get('errors'),'browser captured product errors')
    snapshots=[s for s in report['snapshots'] if s.get('session_state')=='running']
    need(bool(snapshots),'no actual running DOM snapshots')
    for snap in snapshots:
        need(len(snap['units'])==1,'browser attachment set differs')
        unit=snap['units'][0]
        need(unit['dom_matches_product_readback'] is True and unit['readback_matches_real_http_response'] is True,'DOM is not bound to actual HTTP readback')
        props=unit['readback']['properties']
        need(any(event.get('response',{}).get('units') and any(u['id']==unit['instance'] and u.get('properties')==props for u in event['response']['units']) for event in report['readbacks']+report['posts']),'DOM properties lack an independent captured browser HTTP response')
        for field,value in props.items():
            row=next((r for r in unit['values'] if r['field']==field),None);need(row is not None,'actual DOM property missing')
            if field=='led-rgb' and row.get('rgb'):
                colors=value if isinstance(value,list) else [value]
                need(row['rgb']==[f'LED[{i}] #{color:06x}' for i,color in enumerate(colors)],'RGB DOM label differs')
            else:
                text=json.dumps(value,separators=(',',':'),ensure_ascii=False) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                need(row['text']==text,'actual DOM value differs: '+field)
    return {'snapshots':len(snapshots),'posts':len(report['posts']),'actions':len(report['actions'])}

def case_protocol(client,session_id,case,result,directory,Observations,validate_io):
    class RecordedObservations(Observations):
        def __init__(self,*values):
            super().__init__(*values);self.phase='startup';self.records=[]
        def state(self):
            state=super().state();n=len(self.records);name=f'observations/{n:04d}-state.json'
            save(directory/name,state);self.records.append({'kind':'state','phase':self.phase,'file':name})
            save(directory/'observation-index.json',self.records);return state
        def marker(self,marker,**options):
            if case=='rgb' and marker=='IO_RGB_FULL 2' and 'offset' not in options:options['offset']=len(self.serial)
            super().marker(marker,**options);self.phase=marker;n=len(self.records);name=f'observations/{n:04d}-serial.txt'
            target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(self.serial.encode())
            self.records.append({'kind':'marker','marker':marker,'offset':options.get('offset',0),'file':name,'sha256':sha(self.serial.encode())})
            save(directory/'observation-index.json',self.records)
        def qom(self,path,prop):
            value=super().qom(path,prop);self.records.append({'kind':'qom','path':path,'property':prop,'value':value})
            save(directory/'observation-index.json',self.records);return value
    observed=RecordedObservations(client,session_id,result)
    observed.marker(result['ready_marker'],timeout=180)
    initial=observed.state();save(directory/'initial-units.json',initial)
    session=client.json(f'sessions/{session_id}',via_ui=False)
    proof=client.web_ui.runtime_provenance(session,lambda:client.json(f'sessions/{session_id}',via_ui=False))
    need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'live process proof did not match frozen runtime')
    need(isinstance(proof['worker_id'],str) and proof['worker_id'] and type(proof['worker_generation']) is int,'live process proof lacks worker generation')
    result['runtime_provenance']=proof;client.web_ui_sessions[session_id]['provenance_done']=True;client._open_web_ui(session_id)
    result['steps']=[]
    def fresh(values,predicate):
        observed.wait(lambda text:True);before=observed.serial;offset=len(before)
        observed.input(values);observed.wait(predicate,offset=offset)
        delta=observed.serial[offset:];need(bool(delta),'no fresh guest serial after input')
        state=observed.state();n=len(result['steps']);save(directory/f'steps/{n:02d}-state.json',state)
        (directory/f'steps/{n:02d}-before.txt').write_text(before,encoding='utf-8');(directory/f'steps/{n:02d}-after.txt').write_text(observed.serial,encoding='utf-8')
        result['steps'].append({'values':values,'serial_offset':offset,'before_sha256':sha(before.encode()),'after_sha256':sha(observed.serial.encode()),'state_file':f'steps/{n:02d}-state.json','fresh_serial':delta})
        return state,delta
    if case=='button':
        input_negative(client,session_id,{'pressed':'true'},('pressed','input-level'),directory)
        for pressed,raw in ((True,0),(False,1),(True,0),(False,1)):
            marker=f'UNIT_BUTTON {raw}'
            state,delta=fresh({'pressed':pressed},lambda text,m=marker:re.search(r'(?m)^'+re.escape(m)+r'\r?$',text) is not None)
            need(state['units'][0]['properties']['pressed'] is pressed,'live GPIO input does not match injected state')
            result['required_markers'].append(marker)
        result['checks']['fresh_guest_button_both_gpio_levels']=True
    elif case=='env-iii':
        input_negative(client,session_id,{'temperature-c':22.0,'pressure-pa':-1},('temperature-c','humidity-pct','pressure-pa'),directory)
        for vector in ((31.5,67.0,98765.0),(18.25,33.0,103250.0)):
            def match(text,v=vector):
                return any(all(abs(float(actual)-expected)<tolerance for actual,expected,tolerance in zip(row,v,(0.2,0.2,1.0))) for row in re.findall(r'(?m)^UNIT_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$',text))
            values=dict(zip(('temperature-c','humidity-pct','pressure-pa'),vector));state,delta=fresh(values,match)
            need(match(delta),'fresh compensated ENV vector not observed')
            result['steps'][-1]['expected_vector']=list(vector)
            for key,value in values.items():need(abs(state['units'][0]['properties'][key]-value)<0.000001,'ENV QOM input differs')
        result['checks']['fresh_guest_two_compensated_environment_vectors']=True
    elif case=='encoder':
        input_negative(client,session_id,{'counter':32768,'pressed':True},('counter','pressed'),directory)
        for counter,pressed in ((-12345,True),(32767,False)):
            marker=f'CONTROL_ENCODER {counter} {int(pressed)}'
            state,_=fresh({'counter':counter,'pressed':pressed},lambda text,m=marker:re.search(r'(?m)^'+re.escape(m)+r'\r?$',text) is not None)
            p=state['units'][0]['properties'];need(p['counter']==counter and p['pressed'] is pressed,'signed counter/active-low QOM differs')
            result['required_markers'].append(marker)
        need(observed.properties()['led-rgb']==[0x112233,0x445566],'official driver LED register triplets differ')
        result['checks']['fresh_guest_signed_counter_active_low_and_led_outputs']=True
    elif case=='relay':
        input_negative(client,session_id,{'output-level':True},(),directory)
        observed.wait(lambda text:True);offset=len(observed.serial)
        observed.wait(lambda text:'UNIT_RELAY 0' in text and 'UNIT_RELAY 1' in text,offset=offset)
        for level in (False,True):
            state=observed.properties_match(lambda p,l=level:p['output-level'] is l,timeout=20)
            result['steps'].append({'expected_output':level,'properties':state})
            client.web_ui.call('capture',session_id=session_id,phase='relay-output-'+str(int(level)),screenshot=True)
        need(observed.properties()['output-transitions']>initial['units'][0]['properties']['output-transitions'],'guest did not generate new relay transitions')
        result['relay_fresh_offset']=offset;result['required_markers']+=['UNIT_RELAY 0','UNIT_RELAY 1']
        result['checks']['fresh_guest_gpio_relay_output_switches']=True
    else:
        input_negative(client,session_id,{'led-rgb':[1,2,3]},(),directory)
        validate_io(observed,'rgb')  # Original native RMT/GRB/short-frame assertions only.
    state=observed.state();save(directory/'final-units.json',state);props=state['units'][0]['properties']
    need(state['source']=='live' and state['contract_status']=='frozen' and state['units'][0]['source']=='guest-qom' and state['units'][0]['available'],'Unit QOM/frozen state unavailable')
    if case in ('env-iii','encoder'):
        need(all(type(props.get(k)) is int and props[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events')),'I2C controller transactions/bytes/input counters missing')
    elif case=='button':need(props['input-events']>=4,'GPIO input event counters absent')
    elif case=='relay':need(props['output-transitions']>=2,'GPIO output transition counters absent')
    result['unit_state']=state;result['checks']['live_guest_qom_and_counters']=True
    observed.wait(lambda text:True);(directory/'serial.txt').write_text(observed.serial,encoding='utf-8')
    need(not any(marker in observed.serial for marker in FAILURES),'guest exception in final serial')
    return observed.serial

def validate_zip(data,result,request):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();need(len(names)==len(set(names)) and archive.testzip() is None,'duplicate/corrupt evidence ZIP')
        required={'manifest.json','serial.log','frames/current.png','qom/snapshot.json','units/contract.json','units/runtime.json','units/state.json','firmware/uiflow-source.json'}
        need(required<=set(names),'evidence ZIP missing required source/guest/controller files')
        manifest=json.loads(archive.read('manifest.json'));need(set(manifest['files'])==set(names)-{'manifest.json'},'ZIP member index differs')
        for name,info in manifest['files'].items():
            raw=archive.read(name);need(info['size']==len(raw) and info['sha256']==sha(raw),'ZIP member hash differs: '+name)
        session=manifest['session'];need(session['state']=='running','ZIP was not captured before stop')
        for key in ('session_id','device_id','runtime','firmware_sha256'):need(session[key]==result[key],'ZIP session identity differs: '+key)
        proof=result['runtime_provenance'];need(session['pid']==proof['observed_pid'],'ZIP PID differs from direct process proof')
        worker=session['worker'];need(worker['lease_active'] is True and worker['worker_id']==proof['worker_id'] and worker['generation']==proof['worker_generation'],'ZIP worker lease/generation differs')
        need(session['firmware_provenance']==result['source']==json.loads(archive.read('firmware/uiflow-source.json')),'ZIP/session firmware source provenance differs')
        need(session['source_artifacts'][0]==sha(canonical(request['files'])),'ZIP source artifact is not canonical source JSON CAS')
        state=json.loads(archive.read('units/state.json'));runtime=json.loads(archive.read('units/runtime.json'));contract=json.loads(archive.read('units/contract.json'))
        need(state['session_id']==session['session_id'] and state['source']=='live' and state['contract_status']=='frozen','ZIP Unit state unavailable')
        need(len(state['units'])==1 and state['units'][0]['unit_id']==result['unit_id'] and state['units'][0]['available'],'ZIP Unit tree differs')
        need(runtime['attachments']==session['units'],'ZIP normalized wiring differs')
        need(contract['source_hashes']==state['contract_hashes'],'ZIP frozen contract hashes differ')
        serial=archive.read('serial.log').decode('utf-8');need(result['ready_marker'] in serial and not any(x in serial for x in FAILURES),'ZIP has no healthy guest path')
        for marker in result['required_markers']:need(re.search(r'(?m)^'+re.escape(marker)+r'\r?$',serial),'ZIP lacks required guest marker')
        metrics=frame_valid(archive.read('frames/current.png'))
        return {'session_id':session['session_id'],'pid':session['pid'],'files':names,'native_frame':metrics,'source_cas_sha256':session['source_artifacts'][0]}

def run_case(client,args,row,Observations,validate_io):
    case=row['unit_id'];directory=args.out_dir/case;request=load(directory/'source-request.json')
    result={**row,'expected_runtime_sha256':args.expected_runtime_sha256,'status':'FAIL','checks':{},'injections':[],'required_markers':[],'hardware_validation':'NOT RUN','started_at':now()};session_id=None;pid=None
    with HTTPRecorder(directory/'http'):
        try:
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'live-unit-inventory.json',inventory)
            descriptor=next(u for u in inventory['units'] if u['id']==case);need(descriptor['runtime']['status'] in ('implemented','validated'),'Unit is not admitted by the real service registry')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware)
            result['source']=source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+result['source']['artifact_id'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact)
            need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS artifact metadata differs')
            result['checks']['source_api_cas_base_files_and_firmware_identity']=True
            client.web_ui.call('prepare')
            payload={'device_id':'cores3','firmware_id':firmware['firmware_id'],'runtime':'qemu','ttl_seconds':900,'ready_marker':row['ready_marker'].split()[0],'ready_timeout_seconds':180,'units':row['attachments'],'uiflow_source_sha256':result['source']['metadata']['source_sha256']}
            startup_negatives=[]
            for label,negative,code,kind in (
                ('missing-source-pin',{k:v for k,v in payload.items() if k!='uiflow_source_sha256'},400,'binding_required'),
                ('wrong-source-pin',{**payload,'uiflow_source_sha256':'0'*64},409,'binding_mismatch'),
            ):
                try:client.json('sessions',method='POST',payload=negative,via_ui=False)
                except RuntimeError as error:
                    need(f'HTTP {code} ' in str(error) and kind in str(error),'source pin negative returned the wrong error')
                    startup_negatives.append({'case':label,'request':negative,'error':str(error),'status':'REJECTED'})
                else:raise RuntimeError('session source pin negative was accepted')
            save(directory/'startup-pin-negatives.json',startup_negatives)
            pin_health=client.json('health',via_ui=False);save(directory/'after-pin-negative-health.json',pin_health)
            need(pin_health['capacity']['active_sessions']==0,'source pin negative started a session')
            result['checks']['source_pin_missing_and_mismatch_fail_before_runtime']=True
            save(directory/'session-request.json',payload);session=client.json('sessions',method='POST',payload=payload)
            session_id=result['session_id']=session['session_id'];save(directory/'created-session.json',session)
            print(f'{case}: visible source-API session {session_id}',flush=True)
            case_protocol(client,session_id,case,result,directory,Observations,validate_io)
            current=client.json(f'sessions/{session_id}',via_ui=False);pid=current['pid'];save(directory/'running-session.json',current)
            need(current['firmware_provenance']==result['source'] and current['source_artifacts'][0]==row['source_cas_sha256'],'live session source provenance differs')
            frame=client.raw(f'sessions/{session_id}/frame.png');(directory/'frame.png').write_bytes(frame);result['native_frame']=frame_valid(frame);result['checks']['nonempty_native_frame']=True
            client.web_ui.call('capture',session_id=session_id,phase='observed-units',screenshot=True)
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if session_id:
                try:
                    live=client.json(f'sessions/{session_id}',via_ui=False);pid=pid or live.get('pid');save(directory/'before-evidence-session.json',live)
                    data=client.raw(f'sessions/{session_id}/evidence');(directory/'evidence.zip').write_bytes(data)
                    result['evidence_sha256']=sha(data);result['evidence_summary']=validate_zip(data,result,request);result['checks']['zip_before_stop_and_source_guest_binding']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop_and_source_guest_binding']=False
                try:
                    stopped=client.json(f'sessions/{session_id}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped)
                    history=client.json(f'sessions/{session_id}',via_ui=False);save(directory/'retained-session.json',history)
                    need(stopped['state'] in ('stopped','failed') and history['state'] in ('stopped','failed'),'session did not stop with history')
                    need(history['flash_retained'] is False and history['last_frame_available'] is True,'mutable Flash retained or final frame lost')
                    need(history['firmware_sha256']==result.get('firmware_sha256') and history['firmware_provenance']==result.get('source'),'history provenance differs')
                    need(type(pid) is int and pid>0,'no owned QEMU PID was recorded')
                    deadline=time.monotonic()+15
                    while not pid_gone(pid) and time.monotonic()<deadline:time.sleep(0.1)
                    need(pid_gone(pid),'owned QEMU PID remains after stop')
                    frame=client.raw(f'sessions/{session_id}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(frame);frame_valid(frame)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'health still reports active sessions')
                    result['checks']['stopped_history_pid_exit_flash_release_health_idle']=True
                    result['cleanup']={'owned_pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0}
                except Exception as error:result['cleanup_error']=str(error);result['checks']['stopped_history_pid_exit_flash_release_health_idle']=False
                try:
                    report=load(args.out_dir/'browser'/session_id/'web-report.json');result['browser']=check_browser(report,session_id,result['firmware_sha256']);result['checks']['real_dom_and_captured_http_match']=True
                    if case in ('button','env-iii','encoder'):need(report['actions'] and report['posts'],'input case has no actual UI gesture/POST')
                except Exception as error:result['browser_error']=str(error);result['checks']['real_dom_and_captured_http_match']=False
            result['finished_at']=now();result['status']='PASS' if session_id and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL'
            save(directory/'result.json',result)
    print(f'{case}: {result["status"]} {result.get("error","")}',flush=True);return result

def verify_rgb_observations(directory):
    events=load(directory/'observation-index.json')
    markers={name:next(i for i,event in enumerate(events) if event.get('kind')=='marker' and event.get('marker')==name) for name in ('IO_RGB_FULL 1','IO_RGB_SHORT 1','IO_RGB_FULL 2')}
    need(markers['IO_RGB_FULL 1']<markers['IO_RGB_SHORT 1']<markers['IO_RGB_FULL 2'],'RGB observation order differs')
    for event in events:
        if event['kind']=='marker':
            raw=(directory/event['file']).read_bytes();need(sha(raw)==event['sha256'],'RGB serial observation changed')
            text=raw.decode('utf-8');need(re.search(r'(?m)^'+re.escape(event['marker'])+r'\r?$',text[event['offset']:]),'RGB phase marker is not fresh in recorded serial window')
    def states(a,b):
        return [load(directory/e['file'])['units'][0]['properties'] for e in events[a:b] if e['kind']=='state']
    before=[p for p in states(markers['IO_RGB_FULL 1']+1,markers['IO_RGB_SHORT 1']) if p['led-rgb']==[0x112233,0x445566,0x778899]]
    short=states(markers['IO_RGB_SHORT 1']+1,markers['IO_RGB_FULL 2'])
    after=[p for p in states(markers['IO_RGB_FULL 2']+1,len(events)) if p['led-rgb']==[0xA1B2C3,0x010203,0x040506]]
    need(before and short and after,'RGB full/short/second controller observations missing')
    before=before[-1];short=short[0]
    need(short['led-rgb']==before['led-rgb'] and short['led-frames']==before['led-frames'] and short['incomplete-frames']>before['incomplete-frames'],'short frame changed the complete LED chain or was not counted')
    counters={e['property']:e['value'] for e in events if e['kind']=='qom' and e['path']=='/machine/rmt0'}
    need(counters.get('tx-symbols',0)>=168 and counters.get('tx-threshold-events',0)>0 and counters.get('tx-completions',0)>=3 and counters.get('tx-errors')==0,'real RMT refill/completion counters absent')
    return {'before':before,'short':short,'after':after[-1],'rmt':counters}

def check_saved(output):
    need((output/'SHA256SUMS').is_file(),'frozen artifact SHA256SUMS is absent')
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==expected,'frozen artifact checksum differs: '+name)
    tooling=load(output/'tooling-source-freeze.json')
    for name,expected in tooling.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==expected,'frozen tooling source differs: '+name)
    prepared=load(output/'prepared.json');results=[]
    for row in prepared['cases']:
        case=row['unit_id'];directory=output/case;request=load(directory/'source-request.json');result=load(directory/'result.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS','case did not pass: '+case)
        # Verify saved caller files independently; API metadata is never the guest oracle.
        for name,text in request['files'].items():need((directory/'files'/name).read_bytes()==text.encode(),'frozen guest file bytes differ')
        source=source_provenance(firmware,request);need(source==result['source'],'saved source response differs')
        proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need(proof==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'direct runtime proof differs')
        serial=(directory/'serial.txt').read_bytes().decode('utf-8');need(row['ready_marker'] in serial and not any(x in serial for x in FAILURES),'saved guest serial failed')
        for i,step in enumerate(result['steps']):
            if 'serial_offset' not in step:continue
            before=(directory/f'steps/{i:02d}-before.txt').read_bytes().decode('utf-8');after=(directory/f'steps/{i:02d}-after.txt').read_bytes().decode('utf-8')
            need(len(before)==step['serial_offset'] and sha(before.encode())==step['before_sha256'] and sha(after.encode())==step['after_sha256'] and after.startswith(before),'fresh guest serial window was altered')
            delta=after[len(before):];need(delta==step['fresh_serial'],'fresh serial delta differs')
            values=step['values'];state=load(directory/step['state_file']);props=state['units'][0]['properties']
            if case=='button':need(f'UNIT_BUTTON {0 if values["pressed"] else 1}' in delta and props['pressed'] is values['pressed'],'fresh Button evidence absent')
            elif case=='encoder':need(f'CONTROL_ENCODER {values["counter"]} {int(values["pressed"])}' in delta and props['counter']==values['counter'] and props['pressed'] is values['pressed'],'fresh Encoder evidence absent')
            elif case=='env-iii':need(any(all(abs(float(a)-b)<t for a,b,t in zip(vector,step['expected_vector'],(.2,.2,1.0))) for vector in re.findall(r'UNIT_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)',delta)),'fresh ENV compensated vector absent')
        if case=='relay':need('UNIT_RELAY 0' in serial[result['relay_fresh_offset']:] and 'UNIT_RELAY 1' in serial[result['relay_fresh_offset']:],'fresh relay cycle absent')
        if case=='rgb':
            verify_rgb_observations(directory)
            need(all(re.search(r'(?m)^'+re.escape(m)+r'\r?$',serial) for m in ('IO_RGB_FULL 1','IO_RGB_SHORT 1','IO_RGB_FULL 2')),'RGB guest phases absent')
            need(result['checks'].get('native_rmt_grb_all_three_leds_and_short_frame_negative') is True,'original RGB assertions not completed')
        need(sha((directory/'evidence.zip').read_bytes())==result['evidence_sha256'],'ZIP bytes changed')
        validate_zip((directory/'evidence.zip').read_bytes(),result,request)
        with zipfile.ZipFile(directory/'evidence.zip') as archive:
            contract=json.loads(archive.read('units/contract.json'))
            for name,expected in contract['source_hashes'].items():need(tooling.get('platform/units/'+name)==expected,'ZIP Unit contract source is not the frozen local registry: '+name)
        with zipfile.ZipFile(directory/'evidence.zip') as archive:need(archive.read('serial.log').decode('utf-8').startswith(serial),'ZIP serial does not contain the observed guest serial prefix')
        frame_valid((directory/'frame.png').read_bytes());frame_valid((directory/'history-frame.png').read_bytes())
        check_browser(load(output/'browser'/result['session_id']/'web-report.json'),result['session_id'],result['firmware_sha256'])
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(history['flash_retained'] is False and health['capacity']['active_sessions']==0,'cleanup evidence incomplete')
        need(result['cleanup']['pid_gone'] is True and result['cleanup']['owned_pid']==result['runtime_provenance']['observed_pid'],'PID cleanup record differs')
        # Every claimed direct API payload must have real HTTP transcript bytes.
        events=load(directory/'http/index.json')
        for event in events:
            data=(directory/'http'/event['response_file']).read_bytes();need(len(data)==event['response_size'] and sha(data)==event['response_sha256'],'actual HTTP response bytes changed')
        actual=[]
        for event in events:
            if event.get('status',0)//100==2:
                try:actual.append((event,json.loads((directory/'http'/event['response_file']).read_bytes())))
                except (ValueError,UnicodeDecodeError):pass
        need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and v==firmware and json.loads((directory/'http'/e['request_file']).read_bytes())==request for e,v in actual),'firmware record has no matching real source API request/response')
        need(any(e['path'].endswith('/units') and v==result['unit_state'] for e,v in actual),'final QOM snapshot has no actual API response')
        for observation in load(directory/'observation-index.json'):
            if observation['kind']=='state':need(any(e['path'].endswith('/units') and v==load(directory/observation['file']) for e,v in actual),'controller observation has no actual HTTP response')
            elif observation['kind']=='qom':need(any(e['path'].endswith('/qom') and urllib.parse.parse_qs(e['query'])=={'path':[observation['path']],'property':[observation['property']]} and v.get('value')==observation['value'] for e,v in actual),'RMT controller sample has no actual QOM HTTP response')
        session_request=load(directory/'session-request.json');need(session_request['uiflow_source_sha256']==sha(canonical(request['files'])),'session request source pin differs')
        need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and v.get('session_id')==result['session_id'] and json.loads((directory/'http'/e['request_file']).read_bytes())==session_request for e,v in actual),'session has no matching real HTTP source-pin request/response')
        negatives=load(directory/'startup-pin-negatives.json');need(len(negatives)==2 and all(n['status']=='REJECTED' for n in negatives),'session source pin negatives absent')
        need(load(directory/'after-pin-negative-health.json')['capacity']['active_sessions']==0,'source pin negative executed a runtime')
        results.append({'unit_id':case,'session_id':result['session_id'],'status':'PASS'})
    return {'status':'PASS','cases':results,'scope':'source API + same-session guest/QOM/browser/evidence/cleanup; hardware NOT RUN'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=pathlib.Path,required=True)
    parser.add_argument('--case',choices=(*CASES,'all'),action='append')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--api-url',default='http://127.0.0.1:8787')
    parser.add_argument('--expected-runtime-sha256',default=RUNTIME)
    args=parser.parse_args();args.out_dir=guarded_directory(args.out_dir)
    need(not (args.execute and (args.prepare_only or args.check)),'execute cannot be combined with offline modes')
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    cases=list(CASES) if not args.case or 'all' in args.case else list(dict.fromkeys(args.case))
    prepared=prepare(args.out_dir,cases)
    if not args.execute:
        print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','cases':cases,'out_dir':str(args.out_dir),'source_request_count':len(prepared)},ensure_ascii=False));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','execution requires explicit M5_UNIT_WEB_BRIDGE=1')
    need(re.fullmatch(r'[0-9a-f]{64}',args.expected_runtime_sha256) is not None,'runtime SHA must be exact')
    need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'},'local PID evidence requires localhost API')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256
    sys.path[:0]=[str(UNIT),str(ROOT/'platform/tools'),str(ROOT/'platform/tests')]
    from run_service_cases import Client
    from run_io_cases import Observations,validate_io
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**kwargs):
            need(not (method in ('POST','PUT') and path.split('?')[0] in ('artifacts','firmware')),'binary artifact/firmware intake is forbidden in source acceptance')
            return super().raw(path,method=method,**kwargs)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'service must be idle before acceptance')
            source_negatives(client,load(args.out_dir/cases[0]/'source-request.json'),args.out_dir)
        for row in prepared:
            result=run_case(client,args,row,Observations,validate_io);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close()
        save(args.out_dir/'batch-result.json',{'finished_at':now(),'status':'PASS' if len(results)==len(cases) and all(r['status']=='PASS' for r in results) else 'FAIL','cases':[{k:r.get(k) for k in ('unit_id','session_id','status','error','cleanup_error')} for r in results]})
        files=sorted(p for p in args.out_dir.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
        (args.out_dir/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(args.out_dir).as_posix()+'\n' for p in files))
    need(len(results)==len(cases) and all(r['status']=='PASS' for r in results),'one or more real source-API cases failed')
    print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
