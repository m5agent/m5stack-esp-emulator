"""Read-only guide-evidence audit; imports only local reviewer utility functions."""
from pathlib import Path
import ast
import json
import re
import zipfile
from audit import REPO, OUT, RUNTIME, BASE, sha, canonical, load, require, entries

BATCH = REPO / '.work/unit-guide-live-20261026/live-r1'
BOOT = '_uiflow_run_main = True\n'
raw_guide = (BATCH/'guide-source.md').read_bytes()
current_guide = (REPO/'docs/unit-agent-api.md').read_bytes()
prepared = load(BATCH/'prepared.json')
json_blocks=[json.loads(body) for body in re.findall(r'```json\n(.*?)\n```',raw_guide.decode(),re.S)]
hub_units=next(block['units'] for block in json_blocks if 'units' in block)
hub_inputs=[next(block for block in json_blocks if block.get('id')==name) for name in ('env1','ncir1')]
button_units=[]
for code in re.findall(r"<<'PY'\n(.*?)\nPY",raw_guide.decode(),re.S):
    for node in ast.walk(ast.parse(code)):
        if isinstance(node,ast.Dict):
            for key,value in zip(node.keys,node.values):
                if isinstance(key,ast.Constant) and key.value=='units': button_units.append(ast.literal_eval(value))
require(len(button_units)==1, 'Button units dictionary missing/ambiguous in exact guide')
for row in prepared['cases']:
    require(row['attachments']==(button_units[0] if row['case']=='button' else hub_units), 'session topology differs from exact guide literal')
    if row['case']=='hub-env-ncir': require(row['guide_inputs']==hub_inputs, 'input vectors differ from exact guide JSON literals')
require(sha(raw_guide) == prepared['guide_sha256'] == 'ab01086d32920a3b47c98c8a2a5a39830539136fc06bc6eb89a48397f113f737', 'original guide identity differs')
count = 0
for line in (BATCH/'SHA256SUMS').read_text().splitlines():
    digest, filename = line.split('  ',1); target=(BATCH/filename).resolve()
    require(target.is_relative_to(BATCH.resolve()) and sha(target.read_bytes()) == digest, 'guide frozen file changed: '+filename)
    count += 1

def prop(state, instance): return next(item['properties'] for item in state['units'] if item['id'] == instance)
def vector(text, marker, expected, tolerance):
    rows = re.findall(r'(?m)^'+re.escape(marker)+r' ([^\r\n]+)\r?$',text)
    return any(len(row.split())==len(expected) and all(abs(float(actual)-target)<=tol for actual,target,tol in zip(row.split(),expected,tolerance)) for row in rows)

def audit(row):
    case=row['case'];d=BATCH/case;r=load(d/'result.json');http=entries(d)
    request=load(d/'source-request.json');firmware=load(d/'firmware-response.json')
    source=firmware['source'];meta=source['metadata'];sid=r['session_id'];path='/api/v1/sessions/'+sid
    require(r['status']=='PASS' and r['hardware_validation']=='NOT RUN', 'guide case status/category differs')
    span=row['source_span'];main=(d/'main.py').read_bytes()
    require(main==''.join(raw_guide.decode().splitlines(keepends=True)[span['start_line']-1:span['end_line']]).encode(), 'main differs from exact recorded guide lines')
    require(raw_guide.count(main)==current_guide.count(main)==1, 'guest snippet changed or ambiguous in original/current guide')
    require(set(request['files'])=={'main.py'} and request['files']['main.py'].encode()==main, 'caller payload includes extra files or differs')
    require(sha(main)==row['main_sha256'], 'guide main digest differs')
    caller=sha(canonical(request['files']));effective=sha(canonical({**request['files'],'boot.py':BOOT}))
    require(caller==meta['source_sha256']==source['artifact_id']==row['source_cas_sha256'], 'caller-only canonical CAS differs')
    require(effective==meta['effective_source_sha256']==row['effective_source_sha256'] and caller!=effective, 'generated boot incorrectly enters caller CAS')
    require(meta['generated_files']==['boot.py'] and meta['caller_file_count']==1 and meta['caller_source_bytes']==len(main), 'caller/generation counts differ')
    effective_files={'main.py':main,'boot.py':BOOT.encode()}
    require({item['path'] for item in meta['files']}==set(effective_files), 'effective file list differs')
    for item in meta['files']:
        expected=effective_files[item['path']]
        require(item['size']==len(expected) and item['sha256']==sha(expected) and item['origin']==('generated' if item['path']=='boot.py' else 'caller'), 'caller/generated file provenance differs')
    require(meta['base_sha256']==request['expected_base_sha256']==BASE and meta['firmware_sha256']==firmware['firmware_id']==firmware['sha256']==r['firmware_sha256'], 'guide base/image differs')
    require(any(event['method']=='POST' and event['path']=='/api/v1/firmware/uiflow' and event['status']==201 and event['_request']==request and event['_json']==firmware for event in http), 'guide source lacks actual matching HTTP request/response')
    session_request=load(d/'session-request.json')
    require(session_request['firmware_id']==firmware['firmware_id'] and session_request['uiflow_source_sha256']==caller and session_request['units']==row['attachments'], 'guide session sourcepin/topology differs')
    require(any(event['method']=='POST' and event['path']=='/api/v1/sessions' and event['status']==202 and event['_request']==session_request and event['_json']['session_id']==sid for event in http), 'guide session sourcepin lacks actual captured request')
    proof=load(BATCH/'browser'/sid/'runtime-provenance.json');running=load(d/'running-session.json')
    require(proof==r['runtime_provenance'] and proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==RUNTIME and proof['worker_generation']==11, 'guide runtime proof differs')
    require(running['pid']==proof['observed_pid'] and running['firmware_provenance']==source and running['source_artifacts'][0]==caller, 'guide running PID/source differs')
    def backed(value,suffix): return any(event['path']==path+suffix and event['_json']==value for event in http)
    require(backed(running,''), 'running proof absent in original HTTP')
    steps=[]
    for index,step in enumerate(r['steps']):
        sd=d/step['directory'];before=load(sd/'before-cursor.json');chunks=load(sd/'chunks.json');before_state=load(sd/'before-units.json');after_state=load(sd/'after-units.json')
        action=row['guide_inputs'][index];require(action==step['action'], 'guide input action differs')
        require(backed(before,'/serial') and backed(before_state,'/units') and backed(after_state,'/units'), 'guide step state/cursor lacks real HTTP response')
        cursor=before['next_offset'];fresh=''
        require(cursor==step['initial_cursor'], 'initial guide cursor differs')
        for chunk in chunks:
            require(backed(chunk,'/serial') and chunk['offset']==cursor and chunk['next_offset']==cursor+chunk['bytes'], 'guide serial chunk is unbacked/discontinuous')
            cursor=chunk['next_offset'];fresh+=chunk['data']
        require(cursor==step['final_cursor'] and fresh.encode()==(sd/'fresh-serial.txt').read_bytes() and sha(fresh.encode())==step['fresh_serial_sha256'], 'fresh guide serial differs')
        require(after_state['source']=='live' and after_state['contract_status']=='frozen' and all(unit['source']=='guest-qom' and unit['available'] and not unit['errors'] for unit in after_state['units']), 'guide controller state invalid')
        target=prop(after_state,action['id']);old=prop(before_state,action['id'])
        require(all(target[key]==value for key,value in action['values'].items()), 'guide QOM physical input differs')
        if case=='button':
            require(re.search(r'(?m)^AGENT_BUTTON pressed=%d\r?$'%int(action['values']['pressed']),fresh) and target['input-level']==int(not action['values']['pressed']) and target['input-events']==old['input-events']+1, 'fresh active-low Button result differs')
        else:
            other='ncir1' if action['id']=='env1' else 'env1';fields=('ambient-c','object-c') if other=='ncir1' else ('temperature-c','humidity-pct','pressure-pa')
            require(all(prop(before_state,other)[key]==prop(after_state,other)[key] for key in fields), 'one I2C leaf changed other leaf physical inputs')
            require(prop(before_state,other)['input-events']==prop(after_state,other)['input-events'], 'input events leaked to other leaf')
            require(target['input-events']>old['input-events'] and all(target[key]>0 for key in ('transactions','read-bytes','written-bytes')), 'target leaf lacks independent input/data plane counters')
            if action['id']=='env1': require(vector(fresh,'AGENT_ENV',[28.5,61,100800],[.2,.2,1.5]), 'fresh ENV triplet absent')
            else:
                require(vector(fresh,'AGENT_NCIR',[24,37.5],[.021,.021]) and vector(fresh,'AGENT_ENV',[28.5,61,100800],[.2,.2,1.5]), 'fresh NCIR pair or unchanged ENV triplet absent')
        steps.append({'input':action,'initial_cursor':step['initial_cursor'],'final_cursor':step['final_cursor'],'fresh_serial':fresh,'before':{unit['id']:unit['properties'] for unit in before_state['units']},'after':{unit['id']:unit['properties'] for unit in after_state['units']}})
    final=load(d/'final-units.json')
    require(backed(final,'/units'), 'guide final Unit state lacks actual HTTP response')
    if case=='hub-env-ncir':
        for leaf in ('env1','ncir1'): require(all(prop(final,leaf)[key]>0 for key in ('transactions','read-bytes','written-bytes','input-events')), 'guide leaf has zero independent counter')
        for unit in final['units']: require(unit['pins']=={'yellow':2,'white':1}, 'HUB leaf did not inherit physical CoreS3 port pins')
    data=(d/'evidence.zip').read_bytes();require(sha(data)==r['evidence_sha256'], 'guide ZIP SHA differs')
    with zipfile.ZipFile(d/'evidence.zip') as archive:
        require(archive.testzip() is None and len(set(archive.namelist()))==len(archive.namelist()), 'guide ZIP malformed')
        manifest=json.loads(archive.read('manifest.json'));session=manifest['session']
        require(set(manifest['files'])==set(archive.namelist())-{'manifest.json'}, 'guide ZIP member index differs')
        for filename,item in manifest['files'].items():
            member=archive.read(filename);require(len(member)==item['size'] and sha(member)==item['sha256'], 'guide ZIP member differs: '+filename)
        require(session['state']=='running' and session['session_id']==sid and session['pid']==proof['observed_pid'] and session['worker']['generation']==11 and session['worker']['lease_active'], 'guide ZIP running session/PID/worker differs')
        require(session['firmware_provenance']==source==json.loads(archive.read('firmware/uiflow-source.json')) and session['source_artifacts'][0]==caller, 'guide ZIP source provenance differs')
        zipserial=archive.read('serial.log');require(zipserial.startswith((d/'serial.txt').read_bytes()), 'guide ZIP lost observed serial')
    evidence=[i for i,event in enumerate(http) if event['path']==path+'/evidence' and event['_raw']==data]
    stops=[i for i,event in enumerate(http) if event['method']=='DELETE' and event['path']==path and event['query']=='purge=0' and event['status']==200]
    require(evidence and stops and max(evidence)<min(stops), 'guide ZIP was not requested before retained stop')
    history=load(d/'retained-session.json');health=load(d/'cleanup-health.json')
    require(backed(history,'') and history['state']=='stopped' and history['flash_retained'] is False and history['firmware_provenance']==source, 'guide history differs')
    require(any(event['_json']==health and event['path']=='/api/v1/health' for event in http) and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0, 'guide cleanup health not idle')
    require(r['cleanup']['pid']==proof['observed_pid'] and r['cleanup']['pid_gone'] is True, 'guide recorded PID cleanup differs')
    web=load(BATCH/'browser'/sid/'web-report.json');require(web['session_id']==sid and web['firmware_sha256']==firmware['sha256'] and not web['errors'], 'guide browser identity/errors differ')
    snapshots=[s for s in web['snapshots'] if s['session_state']=='running'];ids={item['id'] for item in row['attachments']};require(snapshots, 'guide running DOM absent')
    for snapshot in snapshots:
        require({unit['instance'] for unit in snapshot['units']}==ids, 'guide DOM attachment set differs')
        for unit in snapshot['units']:
            p=unit['readback']['properties']
            require(any(any(item['id']==unit['instance'] and item['properties']==p for item in event.get('response',{}).get('units',[])) for event in web['readbacks']+web['posts']), 'guide DOM lacks real matching HTTP properties')
            for key,value in p.items():
                cell=next(item for item in unit['values'] if item['field']==key);expected=json.dumps(value,separators=(',',':')) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                require(cell['text']==expected, 'guide DOM text differs from real HTTP')
    for action in row['guide_inputs']:
        for key,value in action['values'].items(): require(any(event['status']==200 and event['request']['id']==action['id'] and event['request']['values'].get(key)==value for event in web['posts']), 'guide field lacks actual browser POST')
    return {'case':case,'status':'PASS','session_id':sid,'guide_main_sha256':sha(main),'same_guest_snippet_in_current_guide':True,'source_cas_sha256':caller,'effective_source_sha256':effective,'firmware_sha256':firmware['sha256'],'generated_boot_verified':True,'runtime_pid':proof['observed_pid'],'runtime_sha256':RUNTIME,'worker_generation':11,'steps':steps,'final_properties':{unit['id']:unit['properties'] for unit in final['units']},'http_events_verified':len(http),'web':{'running_snapshots':len(snapshots),'posts':len(web['posts']),'actions':len(web['actions'])},'evidence_sha256':sha(data),'cleanup':{'state':history['state'],'flash_retained':history['flash_retained'],'active_sessions':health['capacity']['active_sessions'],'pid_gone_recorded':r['cleanup']['pid_gone']}}

cases=[audit(row) for row in prepared['cases']]
require(len({case['session_id'] for case in cases})==len(cases)==2, 'guide cases shared a session')
report={'status':'PASS','category':'independent-offline-guide-virtual-device-evidence-review','api_calls':'NOT RUN','new_execution':'NOT RUN','hardware':'NOT RUN','original_guide_sha256':sha(raw_guide),'current_guide_sha256_at_review':sha(current_guide),'full_guide_changed_after_execution':raw_guide!=current_guide,'guest_snippets_unchanged':True,'frozen_files_verified':count,'cases':cases}
(OUT/'guide-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':'PASS','frozen_files':count,'cases':[case['case'] for case in cases],'guest_snippets_unchanged':True},ensure_ascii=False,indent=2))
