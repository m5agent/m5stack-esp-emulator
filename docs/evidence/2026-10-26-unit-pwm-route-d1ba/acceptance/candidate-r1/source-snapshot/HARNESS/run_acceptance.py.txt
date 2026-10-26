#!/usr/bin/env python3
"""Offline preparation by default. Only root --execute contacts the local service.

No BIN builder/upload, unit-input, PWM setter, browser audition, or compiler.
A baseline expected zero is FAIL_REPRODUCED, never initialization PASS.
"""
from __future__ import annotations
import argparse,ast,io,json,math,os,pathlib,re,sys,time,urllib.parse,zipfile
import source_api_common as common
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
need=common.need;sha=common.sha;canonical=common.canonical;save=common.save;load=common.load
FAILURES=('PWMR_FAIL','Traceback (most recent call last)','Guru Meditation','Rebooting...')
HOLD_RE=re.compile(r'(?m)^PWMR_HOLD (\d+) (\d+) (\d+) (\d+)\r?$')
GUEST_NAMES={'boot.py','main.py','probe_logging.py','probe_config.py','pwm_route_program.py'}

def guest_audit(files):
    need(set(files)==GUEST_NAMES,'exact five-file caller required')
    constructors=[];getters=[]
    for name,text in files.items():
        tree=ast.parse(text,filename=name)
        for node in ast.walk(tree):
            if isinstance(node,(ast.Import,ast.ImportFrom)):
                names=[x.name for x in node.names];need(not any('haptic' in x.lower() or 'softtimer' in x.lower() or 'buzzerunit' in x.lower() for x in names),'timer/callback driver must remain isolated')
            if isinstance(node,ast.Call):
                if isinstance(node.func,ast.Name) and node.func.id=='PWM':constructors.append(node)
                if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='pwm':
                    need(node.func.attr in {'freq','duty_u16'} and not node.args and not node.keywords,'post-constructor PWM setter or other operation forbidden');getters.append(node.func.attr)
    need(len(constructors)==1,'exactly one PWM construction required')
    node=constructors[0];kw={x.arg:ast.unparse(x.value) for x in node.keywords}
    need(kw=={'freq':'PWM_FREQUENCY_HZ','duty_u16':'0'},'original constructor must request zero duty')
    need(set(getters)=={'freq','duty_u16'},'both read-only getter forms required')
    config={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(files['probe_config.py']).body}
    need(config=={'PWM_GPIO':2,'PWM_FREQUENCY_HZ':2000,'HOLD_MS':60000,'HEARTBEAT_MS':250},'caller config may not encode runtime/expected result')
    return {'five_files':True,'pwm_constructors':1,'post_constructor_setters':0,'getter_calls':getters,'hold_ms':60000,'callback_or_softtimer_driver':'NOT IMPORTED'}

def prepare(output):
    need(output.is_relative_to(HERE) and output!=HERE and not output.exists(),'use fresh child output directory')
    files={p.name:p.read_text(encoding='utf-8') for p in sorted((HERE/'guest').glob('*.py'))};audit=guest_audit(files)
    matrix=load(ROOT/'tests/uiflow2/device_matrix.json')['devices'];device=next(d for d in matrix if d['id']=='cores3');base_sha=sha((ROOT/device['base']).read_bytes());need(base_sha==common.BASE,'CoreS3 reference changed; re-review required')
    request={'device_id':'cores3','files':files,'expected_base_sha256':base_sha};need(len(canonical(request))<=1048576,'source HTTP limit exceeded')
    output.mkdir(parents=True)
    for name,text in files.items():p=output/'files'/name;p.parent.mkdir(exist_ok=True);p.write_bytes(text.encode())
    save(output/'source-request.json',request)
    row={'device_id':'cores3','unit_id':'buzzer','runtime':'qemu','attachments':[{'id':'external1','unit_id':'buzzer','port_id':'port-a'}],'base_sha256':base_sha,'source_cas_sha256':sha(canonical(files)),'caller_request_sha256':sha(canonical(request)),'ready_marker':'PWMR_READY','expected_size':[320,240],'guest_audit':audit,'status':'PREPARED_NO_API_OR_RUNTIME','validation':'custom raw-PWM initialization diagnostic; not original BuzzerUnit/once validation'}
    save(output/'prepared.json',row)
    names=['tests/units/run_service_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/tools/uiflow_source.py','platform/tools/device_service.py','platform/tools/unit_runtime.py','platform/units/catalog.json','platform/units/runtime-profiles.json','platform/units/host-ports.json','platform/web/unit-panel.js','platform/web/sessions.js']
    pins={}
    for name in names:
        raw=(ROOT/name).read_bytes();pins[name]=sha(raw);p=output/'source-snapshot'/(name+'.txt');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    for name in ['run_acceptance.py','source_api_common.py']:
        raw=(HERE/name).read_bytes();pins['HARNESS/'+name]=sha(raw);p=output/'source-snapshot/HARNESS'/(name+'.txt');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    save(output/'tooling-source-freeze.json',pins);return row,request

def valid_serial(value):
    text=value['data'];need('PWMR_READY\r\n' in text and 'PWMR_HOLD_DONE' not in text,'sample outside READY/no-setter hold window')
    need(not any(x in text for x in FAILURES),'guest failure in hold window');rows=HOLD_RE.findall(text);need(rows,'no guest hold heartbeat')
    index,elapsed,freq,duty=map(int,rows[-1]);need(0<=elapsed<60000 and freq==2000 and duty==0,'guest getter/hold disagrees with initialization')
    return {'sample':index,'elapsed_ms':elapsed,'getter_frequency_hz':freq,'getter_duty_u16':duty}

def state_properties(state):
    need(state['source']=='live' and state['contract_status']=='frozen','Unit is not live/frozen')
    need(len(state['units'])==1,'diagnostic must attach only one output Unit');u=state['units'][0]
    need(u['id']=='external1' and u['unit_id']=='buzzer' and u['source']=='guest-qom' and u['available'] and not u['errors'],'buzzer controller unavailable')
    return u['properties']

def evaluate_sample(before,state,after,expect):
    b=valid_serial(before);a=valid_serial(after)
    need(after['data'].startswith(before['data']) and after['next_offset']>before['next_offset'] and a['sample']>b['sample'],'no fresh heartbeat across QOM sampling')
    props=state_properties(state);frequency=props['frequency-hz'];duty=props['duty-pct']
    need(type(frequency) in (int,float) and math.isfinite(frequency) and type(duty) in (int,float) and math.isfinite(duty),'non-finite QOM')
    need(abs(frequency-expect)<= (1 if expect else 1e-9),'observed initial frequency differs from requested experiment outcome')
    need(abs(duty)<=1e-9,'initial QOM duty must remain exact zero')
    return {'before':b,'after':a,'frequency-hz':frequency,'duty-pct':duty,'fresh_uart_interval':[before['next_offset'],after['next_offset']]}

def frame(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as im:
        im.load();need(im.format=='PNG' and im.size==(320,240) and im.convert('RGB').getcolors(1) is None,'nonblank complete native frame missing')
    return {'sha256':sha(data),'size_bytes':len(data),'native_size':[320,240],'readability':'NOT INFERRED_FROM_DECODE'}

def browser_check(report,result):
    need(report['session_id']==result['session_id'] and report['device_id']=='cores3' and report['firmware_sha256']==result['firmware_sha256'] and not report['errors'],'browser identity/error mismatch')
    need(not report['posts'] and not report['actions'],'output-only diagnostic must not send Unit input or browser control actions')
    snaps=[s for s in report['snapshots'] if s.get('session_state')=='running'];need(snaps,'missing actual running DOM snapshots')
    for snap in snaps:
        need(len(snap['units'])==1,'unexpected browser topology');u=snap['units'][0];need(u['instance']=='external1' and u['dom_matches_product_readback'] and u['readback_matches_real_http_response'],'DOM is not backed by actual product HTTP')
        properties=u['readback']['properties'];need(any(any(x['id']=='external1' and x['properties']==properties for x in e.get('response',{}).get('units',[])) for e in report['readbacks']),'missing browser HTTP response backing')
        for key,value in properties.items():
            cell=next((x for x in u['values'] if x['field']==key),None);need(cell is not None,'missing actual DOM field')
            if type(value) in (int,float):need(float(cell['text'])==value,'DOM numeric mismatch')
            else:need(cell['text']==(str(value).lower() if isinstance(value,bool) else str(value)),'DOM scalar mismatch')
    return {'running_snapshots':len(snaps),'unit_input_posts':0,'control_actions':0}

def zip_check(data,result,request):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),'corrupt/duplicate evidence ZIP');m=json.loads(z.read('manifest.json'))
        need(set(m['files'])==set(z.namelist())-{'manifest.json'},'ZIP membership differs')
        for name,meta in m['files'].items():
            parts=pathlib.PurePosixPath(name);need(not parts.is_absolute() and '..' not in parts.parts and '\\' not in name,'unsafe ZIP member');raw=z.read(name);need(sha(raw)==meta['sha256'] and len(raw)==meta['size'],'ZIP member changed')
        s=m['session'];need(s['state']=='running' and all(s[k]==result[k] for k in ['session_id','device_id','runtime','firmware_sha256']),'ZIP session identity mismatch')
        need(s['firmware_provenance']==json.loads(z.read('firmware/uiflow-source.json'))==result['source'] and s['source_artifacts'][0]==result['source_cas_sha256'],'ZIP source pin mismatch')
        proof=result['runtime_provenance'];need(s['pid']==proof['observed_pid'] and s['worker']['worker_id']==proof['worker_id'] and s['worker']['generation']==proof['worker_generation'] and s['worker']['lease_active'],'ZIP PID/worker mismatch')
        serial=z.read('serial.log').decode();need('PWMR_READY' in serial and HOLD_RE.search(serial) and not any(x in serial for x in FAILURES),'ZIP guest hold absent/failure');state_properties(json.loads(z.read('units/state.json')));frame(z.read('frames/current.png'))
        state=json.loads(z.read('units/state.json'));need(json.loads(z.read('units/contract.json'))['source_hashes']==state['contract_hashes'],'ZIP Unit contract mismatch')
    return {'members':len(m['files'])+1,'source_cas_sha256':result['source_cas_sha256'],'pid':proof['observed_pid']}

def compare_peer(peer,result,request):
    need(peer['status']=='FAIL_REPRODUCED' and peer['initialization_status']=='FAIL_REPRODUCED' and peer['expect_init_frequency_hz']==0,'candidate needs an actual zero-Hz baseline result')
    need(peer['firmware_sha256']==result['firmware_sha256'] and peer['source_cas_sha256']==result['source_cas_sha256'] and peer['source']['metadata']['effective_source_sha256']==result['source']['metadata']['effective_source_sha256'],'A/B firmware/caller/effective source are not identical')
    need(peer['caller_request_sha256']==sha(canonical(request)),'A/B source request differs')
    need(peer['runtime_provenance']['runtime_binary_sha256']!=result['expected_runtime_sha256'],'A/B requires distinct exact runtime binaries')
    return {'same_firmware_sha256':result['firmware_sha256'],'same_caller_and_effective_cas':result['source_cas_sha256'],'same_source_request_sha256':result['caller_request_sha256'],'baseline_runtime_sha256':peer['runtime_provenance']['runtime_binary_sha256'],'candidate_runtime_sha256':result['expected_runtime_sha256']}

def checksums(output):
    files=sorted(p for p in output.rglob('*') if p.is_file() and p.name!='SHA256SUMS');(output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(output).as_posix()+'\n' for p in files))

def execute(args,row,request):
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
    from run_service_cases import Client
    class OutputOnlyClient(Client):
        def raw(self,path,method='GET',**kwargs):
            need(not(method in ('POST','PUT') and (path.split('?')[0] in ('artifacts','firmware') or path.split('?')[0].endswith('/unit-input'))),'binary/alternate intake and Unit inputs are forbidden')
            return super().raw(path,method=method,**kwargs)
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256
    result={**row,'status':'FAIL','initialization_status':'NOT ESTABLISHED','expect_init_frequency_hz':args.expect_init_frequency,'expected_runtime_sha256':args.expected_runtime_sha256,'expected_worker_generation':args.expected_worker_generation,'started_at':common.now(),'samples':[],'checks':{},'hardware':'NOT RUN'};sid=None;pid=None;client=OutputOnlyClient(args.api_url)
    with common.HTTPRecorder(args.out_dir/'http') as recorder:
        try:
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] and health['capacity']['active_sessions']==0,'service must be idle')
            inventory=client.json('units?device_id=cores3',via_ui=False);save(args.out_dir/'live-unit-inventory.json',inventory);unit=next(u for u in inventory['units'] if u['id']=='buzzer');need('cores3' in unit['runtime']['hosts'],'buzzer host not admitted')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(args.out_dir/'firmware-response.json',firmware);result['source']=common.source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            if args.peer_result:
                peer=load(args.peer_result);save(args.out_dir/'peer-result.json',peer);result['ab_comparison']=compare_peer(peer,result,request)
            payload={'device_id':'cores3','runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ttl_seconds':300,'ready_marker':'PWMR_READY','ready_timeout_seconds':150,'units':row['attachments']};save(args.out_dir/'session-request.json',payload)
            client.web_ui.call('prepare');created=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=created['session_id'];save(args.out_dir/'created-session.json',created);print('visible init-only session '+sid,flush=True)
            deadline=time.monotonic()+150
            while True:
                current=client.json('sessions/'+sid,via_ui=False);serial=client.json('sessions/'+sid+'/serial?offset=0&limit=262144',via_ui=False)
                if current['state']=='running' and 'PWMR_READY' in serial['data']:valid_serial(serial);break
                need(current['state'] not in ('failed','stopped') and time.monotonic()<deadline,'guest failed or ready timed out');time.sleep(.2)
            pid=current['pid'];save(args.out_dir/'ready-session.json',current);proof=client.web_ui.runtime_provenance(current,lambda:client.json('sessions/'+sid,via_ui=False));need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==args.expected_runtime_sha256 and proof['observed_pid']==pid and type(proof['worker_generation']) is int,'direct runtime proof differs')
            if args.expected_worker_generation is not None:need(proof['worker_generation']==args.expected_worker_generation,'worker generation differs')
            result['runtime_provenance']=proof;client.web_ui_sessions[sid]['provenance_done']=True;client._open_web_ui(sid)
            for index in range(8):
                before=client.json('sessions/'+sid+'/serial?offset=0&limit=262144',via_ui=False);before_http=len(recorder.events)-1;valid_serial(before)
                state=client.json('sessions/'+sid+'/units');state_http=len(recorder.events)-1
                until=time.monotonic()+5
                while True:
                    after=client.json('sessions/'+sid+'/serial?offset=0&limit=262144',via_ui=False);after_http=len(recorder.events)-1;valid_serial(after)
                    if after['next_offset']>before['next_offset'] and int(HOLD_RE.findall(after['data'])[-1][0])>int(HOLD_RE.findall(before['data'])[-1][0]):break
                    need(time.monotonic()<until,'fresh hold heartbeat timed out');time.sleep(.1)
                observed=evaluate_sample(before,state,after,args.expect_init_frequency);name=f'samples/{index:02d}';save(args.out_dir/(name+'-before.json'),before);save(args.out_dir/(name+'-state.json'),state);save(args.out_dir/(name+'-after.json'),after)
                result['samples'].append({**observed,'prefix':name,'http_indices':{'before':before_http,'state':state_http,'after':after_http}});save(args.out_dir/'sampling-progress.json',result['samples']);time.sleep(.25)
            result['initialization_status']='PASS' if args.expect_init_frequency==2000 else 'FAIL_REPRODUCED';result['checks']['eight_fresh_initialization_windows_without_post_init_setter']=True
            data=client.raw('sessions/'+sid+'/frame.png');(args.out_dir/'frame.png').write_bytes(data);result['frame']=frame(data);client.web_ui.call('capture',session_id=sid,phase='initial-no-setter-hold-complete',screenshot=True)
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if sid:
                try:
                    current=client.json('sessions/'+sid,via_ui=False);pid=pid or current.get('pid');save(args.out_dir/'before-evidence-session.json',current);serial=client.json('sessions/'+sid+'/serial?offset=0&limit=262144',via_ui=False);save(args.out_dir/'final-serial-response.json',serial)
                    data=client.raw('sessions/'+sid+'/evidence');(args.out_dir/'evidence.zip').write_bytes(data);result['evidence_sha256']=sha(data);result['evidence_summary']=zip_check(data,result,request);result['checks']['zip_before_stop']=True
                except Exception as error:result['evidence_error']=str(error)
                try:
                    stopped=client.json('sessions/'+sid+'?purge=0',method='DELETE');save(args.out_dir/'stop-response.json',stopped);history=client.json('sessions/'+sid,via_ui=False);save(args.out_dir/'retained-session.json',history)
                    need(history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and not history['worker']['lease_active'] and history['firmware_provenance']==result.get('source'),'retained history/Flash/source differs');need(type(pid) is int and pid>0,'owned PID absent')
                    deadline=time.monotonic()+15
                    while not common.pid_gone(pid) and time.monotonic()<deadline:time.sleep(.1)
                    need(common.pid_gone(pid),'owned QEMU PID remains');data=client.raw('sessions/'+sid+'/frame.png',via_ui=False);(args.out_dir/'history-frame.png').write_bytes(data);frame(data);health=client.json('health',via_ui=False);save(args.out_dir/'cleanup-health.json',health);need(health['ok'] and health['capacity']['active_sessions']==0,'service not idle');result['cleanup']={'pid':pid,'pid_gone':True,'flash_retained':False,'active_sessions':0};result['checks']['history_flash_pid_idle']=True
                except Exception as error:result['cleanup_error']=str(error)
                try:result['browser']=browser_check(load(args.out_dir/'browser'/sid/'web-report.json'),result);result['checks']['real_dom_http_output_only']=True
                except Exception as error:result['browser_error']=str(error)
            try:client.web_ui.close()
            except Exception as error:result['bridge_close_error']=str(error)
            ok=sid and len(result['samples'])==8 and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error','bridge_close_error')) and all(result['checks'].values())
            result['status']=result['initialization_status'] if ok else 'FAIL';result['harness_check_status']='PASS' if ok else 'FAIL';result['finished_at']=common.now();save(args.out_dir/'result.json',result)
    checksums(args.out_dir);return result

def check_saved(output):
    for line in (output/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);p=(output/name).resolve();need(p.is_relative_to(output) and sha(p.read_bytes())==digest,'saved bytes drift: '+name)
    result=load(output/'result.json');request=load(output/'source-request.json');guest_audit(request['files']);firmware=load(output/'firmware-response.json');need(common.source_provenance(firmware,request)==result['source'] and firmware['sha256']==result['firmware_sha256']==result['firmware_id'] and result['source_cas_sha256']==sha(canonical(request['files'])) and result['caller_request_sha256']==sha(canonical(request)),'saved source identity differs');need(result['harness_check_status']=='PASS' and result['status']==('PASS' if result['expect_init_frequency_hz']==2000 else 'FAIL_REPRODUCED'),'experiment result relabeled')
    events=load(output/'http/index.json');actual=[]
    for e in events:
        raw=(output/'http'/e['response_file']).read_bytes();need(sha(raw)==e['response_sha256'] and len(raw)==e['response_size'],'HTTP response changed')
        try:p=json.loads(raw)
        except (ValueError,UnicodeDecodeError):p=None
        actual.append((e,p,raw))
    need(not any(e['method'] in ('POST','PUT') and (e['path'] in ('/api/v1/artifacts','/api/v1/firmware') or e['path'].endswith('/unit-input')) for e,_,_ in actual),'forbidden binary intake or Unit input')
    need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and p==firmware and json.loads((output/'http'/e['request_file']).read_bytes())==request for e,p,_ in actual),'actual source POST absent')
    startup=load(output/'session-request.json');need(startup['firmware_id']==result['firmware_id'] and startup['uiflow_source_sha256']==result['source_cas_sha256'] and startup['units']==result['attachments'],'saved session source/topology differs')
    need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and isinstance(p,dict) and p.get('session_id')==result['session_id'] and json.loads((output/'http'/e['request_file']).read_bytes())==startup for e,p,_ in actual),'actual source-pinned create POST absent')
    session_path='/api/v1/sessions/'+result['session_id']
    need(len(result['samples'])==8,'sample count differs')
    for row in result['samples']:
        values={k:load(output/(row['prefix']+'-'+k+'.json')) for k in ('before','state','after')};observe=evaluate_sample(values['before'],values['state'],values['after'],result['expect_init_frequency_hz'])
        need(all(row[k]==v for k,v in observe.items()),'recorded fresh sample differs');ids=row['http_indices'];need(ids['before']<ids['state']<ids['after'],'sample ordering differs')
        for key in ids:
            e,p,_=actual[ids[key]];need(e['method']=='GET' and p==values[key] and e['path']==session_path+('/units' if key=='state' else '/serial'),'sample not backed by ordered unchanged HTTP')
    data=(output/'evidence.zip').read_bytes();need(sha(data)==result['evidence_sha256'],'ZIP changed');zip_check(data,result,request);zips=[i for i,(e,_,raw) in enumerate(actual) if e['method']=='GET' and e['path']==session_path+'/evidence' and raw==data];stops=[i for i,(e,_,_) in enumerate(actual) if e['method']=='DELETE' and e['path']==session_path and urllib.parse.parse_qs(e['query'])=={'purge':['0']}];need(len(zips)==len(stops)==1 and zips[0]<stops[0],'ZIP not before actual stop')
    browser_check(load(output/'browser'/result['session_id']/'web-report.json'),result);proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need(proof==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'recorded direct PID identity differs')
    if result['expected_worker_generation'] is not None:need(proof['worker_generation']==result['expected_worker_generation'],'recorded expected worker generation differs')
    history=load(output/'retained-session.json');health=load(output/'cleanup-health.json');need(history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and not history['worker']['lease_active'] and health['ok'] and health['capacity']['active_sessions']==0 and result['cleanup']['pid_gone'] and result['cleanup']['pid']==proof['observed_pid'] and history['firmware_provenance']==result['source'],'cleanup result differs')
    for body,suffix in [(history,'/'+result['session_id']),(health,'/health')]:need(any(e['method']=='GET' and e['path'].endswith(suffix) and p==body for e,p,_ in actual),'cleanup lacks raw HTTP backing')
    running_png=(output/'frame.png').read_bytes();frame(running_png);need(any(i<stops[0] and e['path']==session_path+'/frame.png' and raw==running_png for i,(e,_,raw) in enumerate(actual)),'running frame not backed by same-session actual HTTP');history_png=(output/'history-frame.png').read_bytes();frame(history_png);need(any(i>stops[0] and e['path']==session_path+'/frame.png' and raw==history_png for i,(e,_,raw) in enumerate(actual)),'history frame not actually fetched after stop')
    if result['expect_init_frequency_hz']==2000:compare_peer(load(output/'peer-result.json'),result,request)
    return {'status':result['status'],'harness_check_status':'PASS','sample_windows':8,'no_post_init_pwm_setter':True,'hardware':'NOT RUN'}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=pathlib.Path,required=True);p.add_argument('--execute',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--api-url',default='http://127.0.0.1:8787');p.add_argument('--expected-runtime-sha256');p.add_argument('--expected-worker-generation',type=int);p.add_argument('--expect-init-frequency',type=int,choices=(0,2000));p.add_argument('--peer-result',type=pathlib.Path);a=p.parse_args(argv);a.out_dir=a.out_dir.resolve();need(a.out_dir.is_relative_to(HERE) and a.out_dir!=HERE,'output must be fresh harness child');need(not(a.execute and a.check),'choose execute/check')
    if a.check:print(json.dumps(check_saved(a.out_dir),indent=2));return
    if a.execute:
        need(re.fullmatch('[0-9a-f]{64}',a.expected_runtime_sha256 or ''),'execute requires exact expected runtime SHA256');need(a.expect_init_frequency is not None,'execute requires explicit expected experiment frequency');need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','root execution requires actual Web bridge');need(urllib.parse.urlparse(a.api_url).hostname in {'127.0.0.1','localhost','::1'},'only local direct-PID execution allowed');need(a.expected_worker_generation is None or a.expected_worker_generation>=0,'invalid generation')
        need(a.expect_init_frequency==0 or a.peer_result is not None,'candidate requires baseline peer result');need(a.expect_init_frequency==2000 or a.peer_result is None,'baseline has no candidate peer')
    row,request=prepare(a.out_dir)
    if not a.execute:checksums(a.out_dir);print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','source_cas_sha256':row['source_cas_sha256'],'files':5,'post_init_setters':0}));return
    result=execute(a,row,request);need(result['harness_check_status']=='PASS','experiment collection failed: '+result.get('error',''));print(json.dumps(check_saved(a.out_dir),indent=2))
if __name__=='__main__':main()
