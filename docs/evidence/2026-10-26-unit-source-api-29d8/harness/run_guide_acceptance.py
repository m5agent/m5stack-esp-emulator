#!/usr/bin/env python3
"""Exact guide examples, prepared offline by default; --execute is root-only live acceptance.

Guest source is extracted as UTF-8 text and parsed for syntax, never executed by
this host. Prepare/check make no HTTP request and launch no child process.
"""
from __future__ import annotations
import argparse,ast,hashlib,io,json,os,pathlib,re,sys,time,urllib.parse,zipfile
from datetime import datetime,timezone
import source_api_common as common

HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1]
GUIDE=ROOT/'docs/unit-agent-api.md';BASE=common.BASE;RUNTIME=common.RUNTIME
BOOT='_uiflow_run_main = True\n';CASES=('button','hub-env-ncir')
need=common.need;sha=common.sha;canonical=common.canonical;save=common.save;load=common.load
FAILURES=common.FAILURES

def now():return datetime.now(timezone.utc).isoformat()
def literal_data(node):
    """Read only literal AST data; no eval/exec/compile of guide programs."""
    if isinstance(node,ast.Constant) and isinstance(node.value,(str,int,float,bool,type(None))):return node.value
    if isinstance(node,(ast.List,ast.Tuple)):return [literal_data(n) for n in node.elts]
    if isinstance(node,ast.Dict):return {literal_data(k):literal_data(v) for k,v in zip(node.keys,node.values)}
    raise RuntimeError('guide value is not literal data')

def extract(raw):
    text=raw.decode('utf-8');need(text.encode()==raw,'guide UTF-8 bytes changed')
    fences=list(re.finditer(r'(?ms)^```(?P<lang>[^\n]*)\n(?P<body>.*?)^```[ \t]*$',text))
    button=[];hub=[];topologies=[];inputs={};button_states=[];button_units=[]
    def record(match,source,start):
        return {'source':source,'start_line':text.count('\n',0,start)+1,'end_line':text.count('\n',0,start+len(source)-1)+1,'sha256':sha(source.encode())}
    for fence in fences:
        language=fence['lang'].strip();body=fence['body']
        if language=='bash':
            found=re.search(r'(?ms)^cat > "\$M5_AGENT_DIR/main.py" <<\x27PY\x27\n(?P<code>.*?)^PY\n',body)
            if found:button.append(record(fence,found['code'],fence.start('body')+found.start('code')))
            # The other heredocs are inspected as AST data only, never imported.
            py=re.search(r'(?ms)^python3[^\n]*<<\x27PY\x27\n(?P<code>.*?)^PY\n',body)
            if py:
                tree=ast.parse(py['code'])
                for node in ast.walk(tree):
                    if isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='pressed':button_states.append(literal_data(node.iter))
                    if isinstance(node,ast.Dict):
                        for k,v in zip(node.keys,node.values):
                            if isinstance(k,ast.Constant) and k.value=='units':button_units.append(literal_data(v))
        elif language=='python' and 'env = ENVUnit(i2c=bus, type=3)' in body and 'ncir = NCIRUnit(bus)' in body:
            hub.append(record(fence,body,fence.start('body')))
        elif language=='json':
            value=json.loads(body)
            if isinstance(value,dict) and isinstance(value.get('units'),list):topologies.append(value['units'])
            elif isinstance(value,dict) and value.get('id') in ('env1','ncir1'):
                need(value['id'] not in inputs,'duplicate guide input block');inputs[value['id']]=value
    need(len(button)==len(hub)==len(topologies)==len(button_states)==len(button_units)==1,'guide examples are missing or ambiguous')
    need(button_states[0]==[True,False] and set(inputs)=={'env1','ncir1'},'guide input sequence changed; review the harness')
    result={}
    for name,code,units,actions in [
        ('button',button[0],button_units[0],[{'id':'button1','values':{'pressed':p}} for p in button_states[0]]),
        ('hub-env-ncir',hub[0],topologies[0],[inputs['env1'],inputs['ncir1']]),
    ]:
        tree=ast.parse(code['source'],filename='guide-main.py')
        ready=[n.args[0].value.rstrip('\r\n') for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='console' and n.func.attr=='write' and n.args and isinstance(n.args[0],ast.Constant) and isinstance(n.args[0].value,str) and n.args[0].value.startswith('AGENT_UNIT_READY')]
        need(ready==['AGENT_UNIT_READY'],'guide ready marker missing or ambiguous')
        result[name]={**code,'units':units,'inputs':actions,'ready_marker':ready[0]}
    need(result['button']['units']==[{'id':'button1','unit_id':'button','port_id':'port-a'}],'guide Button topology changed')
    need(result['hub-env-ncir']['units']==[{'id':'hub1','unit_id':'hub','port_id':'port-a'},{'id':'env1','unit_id':'env-iii','parent_id':'hub1','port_id':'grove-1'},{'id':'ncir1','unit_id':'ncir','parent_id':'hub1','port_id':'grove-2'}],'guide HUB topology changed')
    need(inputs['env1']['values']=={'temperature-c':28.5,'humidity-pct':61.0,'pressure-pa':100800} and inputs['ncir1']['values']=={'ambient-c':24.0,'object-c':37.5},'guide vectors changed; review tolerances')
    return result

def prepare(output,cases):
    need(output.is_relative_to(HERE) and output!=HERE and not output.exists(),'choose a fresh output child of this guide harness directory');output.mkdir(parents=True)
    raw=GUIDE.read_bytes();examples=extract(raw);(output/'guide-source.md').write_bytes(raw)
    tools=['platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','platform/tools/unit_runtime.py','platform/units/catalog.json','platform/units/host-ports.json','platform/units/runtime-profiles.json','tests/units/run_service_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js']
    freeze={}
    for name in tools:
        data=(ROOT/name).read_bytes();target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);freeze[name]=sha(data)
    for name in ('run_guide_acceptance.py','source_api_common.py'):
        data=(HERE/name).read_bytes();target=output/'source-snapshot/HARNESS'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);freeze['HARNESS/'+name]=sha(data)
    save(output/'tooling-source-freeze.json',freeze)
    rows=[]
    for case in cases:
        example=examples[case];directory=output/case;directory.mkdir();source=example['source'];(directory/'main.py').write_bytes(source.encode())
        request={'device_id':'cores3','files':{'main.py':source},'expected_base_sha256':BASE};save(directory/'source-request.json',request)
        row={'case':case,'guide_sha256':sha(raw),'main_sha256':sha(source.encode()),'source_span':{'start_line':example['start_line'],'end_line':example['end_line']},'source_cas_sha256':sha(canonical(request['files'])),'effective_source_sha256':sha(canonical({**request['files'],'boot.py':BOOT})),'device_id':'cores3','runtime':'qemu','base_sha256':BASE,'expected_runtime_sha256':RUNTIME,'ready_marker':example['ready_marker'],'attachments':example['units'],'guide_inputs':example['inputs'],'status':'PREPARED_NO_API_OR_RUNTIME'}
        save(directory/'prepared.json',row);rows.append(row)
    save(output/'prepared.json',{'status':'PREPARED_NO_API_OR_RUNTIME','created_at':now(),'guide_sha256':sha(raw),'cases':rows,'host_exec_of_guest_source':False,'binary_build_or_upload':False})
    return rows

def provenance(firmware,request):
    need(set(request['files'])=={'main.py'},'guide must exercise caller main.py and generated boot')
    files=request['files'];effective={**files,'boot.py':BOOT};source=firmware['source'];meta=source['metadata']
    need(firmware['kind']==source['kind']=='uiflow','wrong source response kind')
    need(source['artifact_id']==meta['source_sha256']==sha(canonical(files)),'caller source CAS differs')
    need(meta['effective_source_sha256']==sha(canonical(effective)) and meta['generated_files']==['boot.py'],'generated boot/effective source identity differs')
    entries={x['path']:x for x in meta['files']};need(len(entries)==len(meta['files'])==2 and set(entries)==set(effective),'source file set differs')
    for name,text in effective.items():
        e=entries[name];need(e['sha256']==sha(text.encode()) and e['size']==len(text.encode()) and e['origin']==('generated' if name=='boot.py' else 'caller'),'file provenance differs: '+name)
    need(meta['base_sha256']==BASE and meta['firmware_sha256']==firmware['firmware_id']==firmware['sha256'],'base/derived firmware identity differs')
    need(meta['status']=='COMPOSED_NOT_EXECUTED' and meta['caller_file_count']==1 and meta['caller_source_bytes']==len(files['main.py'].encode()),'composition metadata is incorrect')
    need(all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified')),'source preservation/readback failed')
    return source

def props(state,instance):return next(u['properties'] for u in state['units'] if u['id']==instance)
def state_valid(state,row):
    need(state['source']=='live' and state['contract_status']=='frozen','guide Unit contract/state is not live/frozen')
    need({u['id']:u['unit_id'] for u in state['units']}=={u['id']:u['unit_id'] for u in row['attachments']},'guide Unit tree differs')
    need(all(u['source']=='guest-qom' and u['available'] and not u.get('errors') for u in state['units']),'guide Unit controller is unavailable')

def vector_present(text,prefix,vector,tolerances):
    return any(len(values)==len(vector) and all(abs(a-b)<=t for a,b,t in zip(values,vector,tolerances)) for values in ([float(x) for x in line.split()] for line in re.findall(r'(?m)^'+re.escape(prefix)+r' ([^\r\n]+)\r?$',text)))

def matches(case,action,fresh,all_inputs):
    if case=='button':return re.search(r'(?m)^AGENT_BUTTON pressed='+str(int(action['values']['pressed']))+r'\r?$',fresh) is not None
    if action['id']=='env1':return vector_present(fresh,'AGENT_ENV',list(action['values'].values()),(.2,.2,1.5))
    env=next(x for x in all_inputs if x['id']=='env1')['values']
    return vector_present(fresh,'AGENT_NCIR',list(action['values'].values()),(.021,.021)) and vector_present(fresh,'AGENT_ENV',list(env.values()),(.2,.2,1.5))

def browser_check(report,row,firmware_sha):
    need(report['session_id']==row['session_id'] and report['firmware_sha256']==firmware_sha and not report['errors'],'browser identity/errors differ')
    ids={a['id'] for a in row['attachments']};snapshots=[s for s in report['snapshots'] if s['session_state']=='running'];need(snapshots,'no running DOM snapshots')
    for snap in snapshots:
        need({u['instance'] for u in snap['units']}==ids,'DOM attachment set differs')
        for unit in snap['units']:
            need(unit['dom_matches_product_readback'] and unit['readback_matches_real_http_response'],'DOM/real HTTP match failed')
            p=unit['readback']['properties']
            need(any(any(u['id']==unit['instance'] and u['properties']==p for u in event.get('response',{}).get('units',[])) for event in report['readbacks']+report['posts']),'DOM readback is not captured in real HTTP')
            for key,value in p.items():
                cell=next((v for v in unit['values'] if v['field']==key),None);need(cell is not None,'DOM property absent')
                expected=json.dumps(value,separators=(',',':'),ensure_ascii=False) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                need(cell['text']==expected,'DOM property differs: '+key)
    need(report['posts'] and report['actions'],'guide inputs lack actual product gestures/POSTs')
    for action in row['guide_inputs']:
        for key,value in action['values'].items():need(any(p['status']==200 and p['request']['id']==action['id'] and p['request']['values'].get(key)==value for p in report['posts']),'guide input field lacks real browser POST: '+key)
    return {'running_snapshots':len(snapshots),'real_posts':len(report['posts']),'actions':len(report['actions'])}

def zip_check(data,row,request,firmware):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();need(len(names)==len(set(names)) and archive.testzip() is None,'corrupt/duplicate ZIP')
        required={'manifest.json','serial.log','frames/current.png','qom/snapshot.json','units/contract.json','units/runtime.json','units/state.json','firmware/uiflow-source.json'};need(required<=set(names),'guide ZIP missing required evidence')
        manifest=json.loads(archive.read('manifest.json'));need(set(manifest['files'])==set(names)-{'manifest.json'},'ZIP file index differs')
        for name,info in manifest['files'].items():raw=archive.read(name);need(info['size']==len(raw) and info['sha256']==sha(raw),'ZIP member hash differs')
        session=manifest['session'];source=provenance(firmware,request)
        need(session['state']=='running' and session['session_id']==row['session_id'] and session['device_id']=='cores3' and session['runtime']=='qemu' and session['firmware_sha256']==firmware['sha256'],'ZIP session identity/state differs')
        proof=row['runtime_provenance'];need(session['pid']==proof['observed_pid'] and session['worker']['worker_id']==proof['worker_id'] and session['worker']['generation']==proof['worker_generation'] and session['worker']['lease_active'],'ZIP worker/PID lease differs')
        need(session['firmware_provenance']==json.loads(archive.read('firmware/uiflow-source.json'))==source and session['source_artifacts'][0]==row['source_cas_sha256'],'ZIP source pin/CAS/provenance differs')
        state=json.loads(archive.read('units/state.json'));state_valid(state,row)
        runtime=json.loads(archive.read('units/runtime.json'));need(runtime['attachments']==session['units'],'ZIP normalized wiring differs')
        contract=json.loads(archive.read('units/contract.json'));need(contract['source_hashes']==state['contract_hashes'],'ZIP frozen Unit hash mismatch')
        serial=archive.read('serial.log').decode('utf-8');need(row['ready_marker'] in serial and not any(f in serial for f in FAILURES),'guide guest failed or never ready')
        for action in row['guide_inputs']:need(matches(row['case'],action,serial,row['guide_inputs']),'ZIP lacks guide guest readings')
        frame=common.frame_valid(archive.read('frames/current.png'))
        if row['case']=='hub-env-ncir':
            for leaf in ('env1','ncir1'):need(all(props(state,leaf)[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events')),'ZIP leaf lacks independent controller traffic')
        return {'pid':session['pid'],'files':names,'native_frame':frame}

def run_case(client,args,row):
    directory=args.out_dir/row['case'];request=load(directory/'source-request.json');result={**row,'status':'FAIL','checks':{},'steps':[],'started_at':now(),'hardware_validation':'NOT RUN'};sid=None;pid=None
    with common.HTTPRecorder(directory/'http'):
        try:
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'live-inventory.json',inventory)
            available={x['id']:x for x in inventory['units']}
            need(all(available[x['unit_id']]['runtime']['status'] in ('implemented','validated') for x in row['attachments']),'guide topology is not admitted by current registry')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware);result['source']=provenance(firmware,request);result['firmware_sha256']=firmware['sha256']
            artifact=client.json('artifacts/'+row['source_cas_sha256'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact);need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS metadata differs')
            payload={'device_id':'cores3','runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ready_marker':row['ready_marker'],'ready_timeout_seconds':180,'ttl_seconds':900,'units':row['attachments']};save(directory/'session-request.json',payload)
            client.web_ui.call('prepare');session=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=session['session_id'];save(directory/'created-session.json',session)
            print(f'{row["case"]}: exact guide session {sid}',flush=True)
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                current=client.json(f'sessions/{sid}',via_ui=False);serial=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False)
                need(current['state'] not in ('failed','stopped'),'guide guest ended before ready');need(not any(f in serial['data'] for f in FAILURES),'guide guest exception')
                if current['state']=='running' and row['ready_marker'] in serial['data']:break
                time.sleep(.2)
            else:raise RuntimeError('guide guest ready timed out')
            save(directory/'ready-session.json',current);save(directory/'ready-serial.json',serial);pid=current['pid']
            proof=client.web_ui.runtime_provenance(current,lambda:client.json(f'sessions/{sid}',via_ui=False));need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==args.expected_runtime_sha256,'guide live runtime hash differs')
            need(type(proof['worker_generation']) is int and proof['worker_id'],'guide runtime proof lacks worker generation');result['runtime_provenance']=proof
            client.web_ui_sessions[sid]['provenance_done']=True;client._open_web_ui(sid)
            initial=client.json(f'sessions/{sid}/units');state_valid(initial,row);save(directory/'initial-units.json',initial)
            for index,action in enumerate(row['guide_inputs']):
                step_dir=directory/'steps'/f'{index:02d}';step_dir.mkdir(parents=True)
                before=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False);save(step_dir/'before-cursor.json',before);cursor=before['next_offset'];need(cursor==before['bytes'],'guide initial serial window was truncated')
                state_before=client.json(f'sessions/{sid}/units',via_ui=False);save(step_dir/'before-units.json',state_before)
                response=client.json(f'sessions/{sid}/unit-input',method='POST',payload=action);save(step_dir/'input-response.json',response)
                chunks=[];fresh='';deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    chunk=client.json(f'sessions/{sid}/serial?offset={cursor}&limit=262144',via_ui=False);need(chunk['offset']==cursor and chunk['next_offset']==cursor+chunk['bytes'],'serial cursor discontinuity')
                    chunks.append(chunk);cursor=chunk['next_offset'];fresh+=chunk['data'];need(not any(f in fresh for f in FAILURES),'guide guest exception after input')
                    if matches(row['case'],action,fresh,row['guide_inputs']):break
                    time.sleep(.2)
                else:raise RuntimeError('fresh guide guest reading timed out')
                save(step_dir/'chunks.json',chunks);(step_dir/'fresh-serial.txt').write_bytes(fresh.encode())
                state=client.json(f'sessions/{sid}/units');state_valid(state,row);save(step_dir/'after-units.json',state)
                actual=props(state,action['id'])
                for key,value in action['values'].items():need(actual[key]==value,'physical QOM input differs from guide input')
                if row['case']=='button':need(actual['input-level']==int(not action['values']['pressed']),'Button is not active-low')
                else:
                    other='ncir1' if action['id']=='env1' else 'env1';fields=('ambient-c','object-c') if other=='ncir1' else ('temperature-c','humidity-pct','pressure-pa')
                    need(all(props(state,other)[k]==props(state_before,other)[k] for k in fields),'one guide leaf input changed another leaf physical values')
                    need(actual['input-events']>props(state_before,action['id'])['input-events'],'guide leaf input counter did not advance')
                    need(all(actual[k]>0 for k in ('transactions','read-bytes','written-bytes')),'guide leaf has no actual I2C traffic')
                time.sleep(.3)  # Guest marker precedes its synchronous display redraw.
                frame=client.raw(f'sessions/{sid}/frame.png');(step_dir/'frame.png').write_bytes(frame);common.frame_valid(frame)
                client.web_ui.call('capture',session_id=sid,phase='guide-step-'+str(index),screenshot=True)
                result['steps'].append({'action':action,'directory':f'steps/{index:02d}','initial_cursor':before['next_offset'],'final_cursor':cursor,'fresh_serial_sha256':sha(fresh.encode())})
            final=client.json(f'sessions/{sid}/units');state_valid(final,row);save(directory/'final-units.json',final)
            if row['case']=='hub-env-ncir':need(all(props(final,leaf)[k]>0 for leaf in ('env1','ncir1') for k in ('transactions','read-bytes','written-bytes','input-events')),'each leaf needs independent nonzero traffic')
            else:need(props(final,'button1')['input-events']>=2,'Button transitions lack input counters')
            running=client.json(f'sessions/{sid}',via_ui=False);save(directory/'running-session.json',running);need(running['firmware_provenance']==result['source'] and running['source_artifacts'][0]==row['source_cas_sha256'],'live session source identity differs')
            serial=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False);save(directory/'final-serial.json',serial);(directory/'serial.txt').write_bytes(serial['data'].encode())
            frame=client.raw(f'sessions/{sid}/frame.png');(directory/'frame.png').write_bytes(frame);common.frame_valid(frame)
            result['checks']['exact_guide_source_generated_boot_and_fresh_guest_qom']=True
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if sid:
                try:
                    before_evidence=client.json(f'sessions/{sid}',via_ui=False);save(directory/'before-evidence-session.json',before_evidence);pid=pid or before_evidence.get('pid')
                    data=client.raw(f'sessions/{sid}/evidence');(directory/'evidence.zip').write_bytes(data);result['evidence_sha256']=sha(data);result['evidence_summary']=zip_check(data,result,request,firmware);result['checks']['zip_before_stop']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop']=False
                try:
                    stopped=client.json(f'sessions/{sid}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped)
                    history=client.json(f'sessions/{sid}',via_ui=False);save(directory/'retained-session.json',history)
                    need(stopped['state'] in ('stopped','failed') and history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True,'history/Flash retention is incorrect')
                    need(history['firmware_provenance']==result.get('source'),'retained source identity differs')
                    need(type(pid) is int and pid>0,'guide did not record an owned PID');deadline=time.monotonic()+15
                    while not common.pid_gone(pid) and time.monotonic()<deadline:time.sleep(.1)
                    need(common.pid_gone(pid),'guide owned PID remains after stop')
                    frame=client.raw(f'sessions/{sid}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(frame);common.frame_valid(frame)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'service not idle after guide stop')
                    result['cleanup']={'pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0};result['checks']['history_pid_flash_and_health_idle']=True
                except Exception as error:result['cleanup_error']=str(error);result['checks']['history_pid_flash_and_health_idle']=False
                try:
                    report=load(args.out_dir/'browser'/sid/'web-report.json');result['browser']=browser_check(report,result,result['firmware_sha256']);result['checks']['actual_guide_dom_and_http_match']=True
                except Exception as error:result['browser_error']=str(error);result['checks']['actual_guide_dom_and_http_match']=False
            result['finished_at']=now();result['status']='PASS' if sid and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL';save(directory/'result.json',result)
    print(f'{row["case"]}: {result["status"]} {result.get("error","")}',flush=True);return result

def check_saved(output):
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==expected,'guide artifact checksum differs: '+name)
    raw=(output/'guide-source.md').read_bytes();examples=extract(raw);prepared=load(output/'prepared.json');freeze=load(output/'tooling-source-freeze.json');results=[]
    for name,expected in freeze.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==expected,'guide tooling snapshot differs')
    for row in prepared['cases']:
        case=row['case'];directory=output/case;result=load(directory/'result.json');request=load(directory/'source-request.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS' and len(result['steps'])==len(row['guide_inputs']),'guide case did not fully pass')
        need((directory/'main.py').read_bytes()==request['files']['main.py'].encode()==examples[case]['source'].encode(),'submitted main.py differs from the exact frozen guide')
        provenance(firmware,request);zip_check((directory/'evidence.zip').read_bytes(),result,request,firmware)
        proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need(proof==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'guide runtime proof differs')
        actual=[]
        for event in load(directory/'http/index.json'):
            body=(directory/'http'/event['response_file']).read_bytes();need(sha(body)==event['response_sha256'] and len(body)==event['response_size'],'HTTP raw bytes differ')
            if event['status']//100==2:
                try:actual.append((event,json.loads(body)))
                except (ValueError,UnicodeDecodeError):pass
        def backed(value,path=None):return any(payload==value and (path is None or event['path'].endswith(path)) for event,payload in actual)
        need(backed(firmware,'/firmware/uiflow'),'firmware response has no real source API bytes')
        need(any(event['path']=='/api/v1/firmware/uiflow' and payload==firmware and json.loads((directory/'http'/event['request_file']).read_bytes())==request for event,payload in actual),'source API request differs')
        for index,step in enumerate(result['steps']):
            sd=directory/step['directory'];before=load(sd/'before-cursor.json');chunks=load(sd/'chunks.json');fresh=(sd/'fresh-serial.txt').read_bytes().decode('utf-8');cursor=before['next_offset'];text=''
            need(backed(before,'/serial'),'guide cursor has no real serial response')
            for chunk in chunks:need(backed(chunk,'/serial') and chunk['offset']==cursor and chunk['next_offset']==cursor+chunk['bytes'],'guide serial cursor is unbacked/discontinuous');cursor=chunk['next_offset'];text+=chunk['data']
            need(text==fresh and sha(fresh.encode())==step['fresh_serial_sha256'] and cursor==step['final_cursor'],'fresh guide serial window differs')
            action=row['guide_inputs'][index];need(step['action']==action and matches(case,action,fresh,row['guide_inputs']),'fresh guide input/guest reading differs')
            state=load(sd/'after-units.json');state_valid(state,row);need(backed(state,'/units'),'guide Unit readback has no actual HTTP response')
            for key,value in action['values'].items():need(props(state,action['id'])[key]==value,'guide physical QOM input differs')
            common.frame_valid((sd/'frame.png').read_bytes())
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(backed(history) and backed(health,'/health') and history['flash_retained'] is False and health['capacity']['active_sessions']==0 and result['cleanup']['pid_gone'],'guide cleanup evidence missing')
        browser_check(load(output/'browser'/result['session_id']/'web-report.json'),result,firmware['sha256'])
        with zipfile.ZipFile(directory/'evidence.zip') as archive:
            contract=json.loads(archive.read('units/contract.json'))
            for name,value in contract['source_hashes'].items():need(freeze['platform/units/'+name]==value,'guide contract does not match frozen registry')
            need(archive.read('serial.log').decode('utf-8').startswith((directory/'serial.txt').read_bytes().decode('utf-8')),'ZIP lost observed guide serial')
        results.append({'case':case,'session_id':result['session_id'],'status':'PASS'})
    need(len({r['session_id'] for r in results})==len(results),'guide examples reused one session')
    return {'status':'PASS','cases':results,'guide_sha256':sha(raw),'hardware':'NOT RUN'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=pathlib.Path,required=True);parser.add_argument('--case',choices=(*CASES,'all'),action='append');parser.add_argument('--execute',action='store_true');parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--api-url',default='http://127.0.0.1:8787');parser.add_argument('--expected-runtime-sha256',default=RUNTIME);args=parser.parse_args();args.out_dir=args.out_dir.resolve();need(args.out_dir.is_relative_to(HERE) and args.out_dir!=HERE,'outputs must stay under guide harness')
    need(not(args.execute and(args.prepare_only or args.check)),'choose live or offline mode')
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    cases=list(CASES) if not args.case or 'all' in args.case else list(dict.fromkeys(args.case));rows=prepare(args.out_dir,cases)
    if not args.execute:print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','cases':cases,'guide_sha256':rows[0]['guide_sha256']}));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','live guide execution requires real Web bridge opt-in');need(urllib.parse.urlparse(args.api_url).hostname in {'localhost','127.0.0.1','::1'},'direct guide PID verification requires local service')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')];from run_service_cases import Client
    class GuideClient(Client):
        def raw(self,path,method='GET',**options):need(not(method in ('POST','PUT') and path.split('?')[0] in ('artifacts','firmware')),'guide harness forbids binary upload/alternate firmware intake');return super().raw(path,method=method,**options)
    client=GuideClient(args.api_url);results=[]
    try:
        with common.HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'guide service must begin idle')
        for row in rows:
            row['expected_runtime_sha256']=args.expected_runtime_sha256;result=run_case(client,args,row);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close();save(args.out_dir/'batch-result.json',{'status':'PASS' if len(results)==len(rows) and all(x['status']=='PASS' for x in results) else 'FAIL','finished_at':now(),'cases':[{k:r.get(k) for k in ('case','session_id','status','error','cleanup_error')} for r in results]})
        files=sorted(p for p in args.out_dir.rglob('*') if p.is_file() and p.name!='SHA256SUMS');(args.out_dir/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(args.out_dir).as_posix()+'\n' for p in files))
    need(len(results)==len(rows) and all(r['status']=='PASS' for r in results),'one or more exact guide cases failed');print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
