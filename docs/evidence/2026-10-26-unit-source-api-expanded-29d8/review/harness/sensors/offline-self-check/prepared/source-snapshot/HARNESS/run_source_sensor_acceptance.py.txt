#!/usr/bin/env python3
"""Source-only CoreS3 sensor acceptance. Default prepare/check are offline.

Only explicit --execute uses the real Client/Web bridge. It submits source JSON
with /firmware/uiflow, never invokes the old BIN runner or redirects an upload.
"""
from __future__ import annotations
import argparse
import ast
import copy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import zipfile
import source_api_common as common
import sensor_contract as contract

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PROBE=ROOT/'tests/units/sensors_probe'
BASE=common.BASE
RUNTIME=common.RUNTIME
SENSORS=tuple(contract.CASES)
NEGATIVE='thermal-missing-fixture'
CASES=(*SENSORS,NEGATIVE)
FAILURES=(*common.FAILURES,'SENSOR_PROBE_FAIL')
COUNTERS=('transactions','read-bytes','written-bytes','samples-generated','crc-errors')
need=common.need;sha=common.sha;canonical=common.canonical;save=common.save;load=common.load

def now():return datetime.now(timezone.utc).isoformat()
def guarded(path):
    path=path.resolve();need(path.is_relative_to(HERE) and path!=HERE,'output must be a child of this harness directory');return path

def source_only_intake(path,method,body=None):
    path=path.split('?',1)[0].strip('/')
    if method in ('POST','PUT','PATCH'):
        need(path not in ('artifacts','firmware','firmware/import') and not path.startswith('artifact-uploads'),'binary intake is forbidden; use the source API directly')
        if path=='firmware/uiflow':need(body is None,'raw source upload is forbidden; JSON source payload is required')

def verify_contract_origin():
    origin=load(HERE/'contract-origin.json');raw=(ROOT/origin['repository_path']).read_bytes()
    need(sha(raw)==origin['sha256'],'original sensor runner changed; regenerate and review the host contract')
    module=(HERE/'sensor_contract.py').read_text();lines=raw.decode().splitlines(keepends=True)
    for name,row in origin['fragments'].items():
        segment=''.join(lines[row['start_line']-1:row['end_line']])
        need(sha(segment.encode())==row['sha256'] and module.count(segment)==1,'original validator fragment changed: '+name)
    return origin

def source_files(case):
    need(case in CASES,'unknown sensor case');unit='thermal' if case==NEGATIVE else case
    files={};origins={}
    for path in sorted(PROBE.rglob('*.py')):
        name=path.relative_to(PROBE).as_posix();raw=path.read_bytes();files[name]=raw.decode('utf-8');need(files[name].encode()==raw,'guest UTF-8 changed')
        origins[name]={'repository_path':path.relative_to(ROOT).as_posix(),'sha256':sha(raw),'size':len(raw),'copy':'byte-exact'}
    manifest=load(PROBE/'sensor_drivers/source-manifest.json')
    for name,record in manifest.items():need(sha((PROBE/'sensor_drivers'/name).read_bytes())==record['sha256'],'official driver bytes differ: '+name)
    hosts=load(ROOT/'platform/units/host-ports.json')['hosts'];host=next(h for h in hosts if h['device_id']=='cores3')
    ports=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device']
    need(len(ports)==1,'exactly one confirmed CoreS3 main Grove port is required');port=ports[0]
    need(port['pins']=={'yellow':2,'white':1},'CoreS3 wiring changed')
    config=f"CASE = {unit!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = 'cores3'\nNO_FIXTURE = {case==NEGATIVE!r}\n"
    files['probe_config.py']=config;origins['probe_config.py']={'copy':'generated-explicit-probe-config','sha256':sha(config.encode()),'size':len(config.encode()),'host_ports_sha256':sha((ROOT/'platform/units/host-ports.json').read_bytes())}
    for name,text in files.items():ast.parse(text,filename=name)
    need('boot.py' in files and 'main.py' in files and len(files)<=128,'source membership/count invalid')
    need(all(len(text.encode())<=256*1024 for text in files.values()) and sum(len(text.encode()) for text in files.values())<=1024*1024,'helper source byte limits exceeded')
    return dict(sorted(files.items())),origins,port,manifest

def fixture(case,root=HERE/'fixtures'):
    if case=='thermal':return load(root/'fixture.json')
    return None

def case_spec(case,root=HERE/'fixtures'):
    if case==NEGATIVE:return {'unit_id':'thermal','initial':{},'changes':[],'negative':['thermal_missing_fixture_nack'],'validation':'negative-runtime-control'}
    spec=copy.deepcopy(contract.CASES[case]);spec.update(unit_id=case,validation='virtual-device validation')
    if case=='thermal':
        original=load(root/'fixture.json');variant=load(root/'synthetic-plus16.json')
        spec['initial']=original['initial'];spec['changes']=[{k:variant['initial'][k] for k in ('frame0-hex','frame1-hex')}]
    return spec

def freeze(output):
    sources=['tests/units/run_sensor_cases.py','tests/units/run_service_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','platform/tools/unit_runtime.py','platform/units/catalog.json','platform/units/runtime-profiles.json','platform/units/host-ports.json','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js']
    paths={name:ROOT/name for name in sources}
    paths.update({p.relative_to(ROOT).as_posix():p for p in PROBE.rglob('*') if p.is_file() and p.suffix!='.pyc' and '__pycache__' not in p.parts})
    paths.update({'HARNESS/'+name:HERE/name for name in ('run_source_sensor_acceptance.py','source_api_common.py','sensor_contract.py','contract-origin.json')})
    hashes={}
    for name,path in paths.items():
        raw=path.read_bytes();hashes[name]=sha(raw);target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    for path in (HERE/'fixtures').iterdir():
        if path.is_file():
            raw=path.read_bytes();target=output/'fixture-snapshot'/path.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);hashes['FIXTURE/'+path.name]=sha(raw)
    save(output/'tooling-source-freeze.json',hashes)
    return hashes

def prepare(output,cases,generation=11):
    need(not output.exists(),'choose a fresh output directory; old evidence is never overwritten');output.mkdir(parents=True)
    verify_contract_origin();hashes=freeze(output);rows=[]
    for case in cases:
        directory=output/case;directory.mkdir();files,origins,port,drivers=source_files(case);spec=case_spec(case,output/'fixture-snapshot')
        request={'device_id':'cores3','files':files,'expected_base_sha256':BASE}
        wire_bytes=len(json.dumps(request,allow_nan=False).encode());need(wire_bytes<=1024*1024,'complete serialized HTTP JSON body exceeds 1 MiB')
        save(directory/'source-request.json',request);save(directory/'guest-source-freeze.json',origins);save(directory/'official-driver-proof.json',drivers)
        for name,text in files.items():target=directory/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode())
        license_dir=directory/'license-evidence';license_dir.mkdir();(license_dir/'sensor-drivers.LICENSE.MIT').write_bytes((PROBE/'sensor_drivers/LICENSE.MIT').read_bytes())
        if spec['unit_id']=='thermal':
            for name in ('LICENSE.Apache-2.0','NOTICE.md'):(license_dir/name).write_bytes((HERE/'fixtures'/name).read_bytes())
        row={'case':case,'unit_id':spec['unit_id'],'device_id':'cores3','runtime':'qemu','validation':spec['validation'],'status':'PREPARED_NO_API_OR_RUNTIME','base_sha256':BASE,'expected_runtime_sha256':RUNTIME,'expected_worker_generation':generation,'source_cas_sha256':sha(canonical(files)),'source_files':{name:{'size':len(text.encode()),'sha256':sha(text.encode())} for name,text in files.items()},'http_json_body_bytes':wire_bytes,'ready_marker':'SENSOR_PROBE_READY '+spec['unit_id'],'negative_checks':spec['negative'],'required_markers':['SENSOR_PROBE_READY '+spec['unit_id']]+['SENSOR_CHECK '+name+' PASS' for name in spec['negative']],'attachments':[{'id':'external1','unit_id':spec['unit_id'],'port_id':port['id'],'initial':spec['initial']}],'changes':spec['changes'],'expected_size':[320,240]}
        save(directory/'prepared.json',row);rows.append(row)
    save(output/'prepared.json',{'status':'PREPARED_NO_API_OR_RUNTIME','created_at':now(),'cases':rows,'source_intake':'POST /api/v1/firmware/uiflow','binary_build_or_upload':False,'host_execution_of_guest_python':False,'source_snapshot_count':len(hashes)})
    return rows

def negative_markers(row,text):
    return all(re.search(r'(?m)^'+re.escape(marker)+r'\r?$',text) for marker in row['required_markers'])

def reading(row,phase,text,fixtures):
    case=row['case']
    if case==NEGATIVE:return negative_markers(row,text) and 'SENSOR_THERMAL ' not in text
    if case=='thermal':return contract.thermal_reading(text,load(fixtures/('fixture.json' if phase==0 else 'synthetic-plus16.json'))['expected'])
    values=row['attachments'][0]['initial'] if phase==0 else row['changes'][phase-1]
    return contract.reading_matches(case,values,text)

def state_valid(state,row):
    need(state['source']=='live' and state['contract_status']=='frozen' and len(state['units'])==1,'Unit state is not live/frozen/single')
    unit=state['units'][0];need(unit['id']=='external1' and unit['unit_id']==row['unit_id'] and unit['source']=='guest-qom' and unit['available'] and not unit.get('errors'),'Unit controller unavailable or wrong')
    need(unit['pins']=={'yellow':2,'white':1},'Unit host wiring differs')
    return unit['properties']

def serial_full(client,sid):
    chunk=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False)
    need(chunk['offset']==0 and chunk['next_offset']==chunk['bytes'] and len(chunk['data'].encode())==chunk['bytes'],'serial is truncated or has inconsistent UTF-8 byte counts')
    need(not any(marker in chunk['data'] for marker in FAILURES),'guest failure in serial')
    return chunk

def wait_initial(client,sid,row,fixtures,directory):
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        current=client.json(f'sessions/{sid}',via_ui=False);chunk=serial_full(client,sid)
        need(current['state'] not in ('failed','stopped'),'guest ended before initial sensor reading')
        if current['state']=='running' and negative_markers(row,chunk['data']) and reading(row,0,chunk['data'],fixtures):
            save(directory/'initial-reading-serial.json',chunk);save(directory/'running-session.json',current);return chunk,current
        time.sleep(.25)
    raise RuntimeError('original sensor negative markers/initial reading timed out')

def changed_window(client,sid,row,phase,values,directory,fixtures):
    before=serial_full(client,sid);save(directory/'before-cursor.json',before)
    before_state=client.json(f'sessions/{sid}/units',via_ui=False);save(directory/'before-units.json',before_state);state_valid(before_state,row)
    response=client.json(f'sessions/{sid}/unit-input',method='POST',payload={'id':'external1','values':values});save(directory/'input-response.json',response)
    cursor=before['next_offset'];fresh='';chunks=[];deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        chunk=client.json(f'sessions/{sid}/serial?offset={cursor}&limit=262144',via_ui=False)
        need(chunk['offset']==cursor and chunk['next_offset']==cursor+chunk['bytes'] and len(chunk['data'].encode())==chunk['bytes'],'fresh serial cursor/range differs')
        chunks.append(chunk);cursor=chunk['next_offset'];fresh+=chunk['data']
        need(not any(marker in fresh for marker in FAILURES),'guest failure in changed sensor window')
        if reading(row,phase,fresh,fixtures):break
        time.sleep(.25)
    else:raise RuntimeError('changed-input reading absent from fresh guest bytes')
    save(directory/'chunks.json',chunks);(directory/'fresh-serial.txt').write_bytes(fresh.encode())
    state=client.json(f'sessions/{sid}/units');save(directory/'after-units.json',state);props=state_valid(state,row)
    for key,value in values.items():need(props[key]==value,'Unit QOM value differs from submitted input: '+key)
    need(props['input-events']>state_valid(before_state,row)['input-events'],'input-event counter did not advance')
    time.sleep(.3);frame=client.raw(f'sessions/{sid}/frame.png');(directory/'frame.png').write_bytes(frame);metrics=common.frame_valid(frame);need([metrics['width'],metrics['height']]==row['expected_size'],'native sensor frame dimensions differ')
    return {'phase':phase,'values':values,'initial_cursor':before['next_offset'],'final_cursor':cursor,'fresh_serial_sha256':sha(fresh.encode()),'reading':reading(row,phase,fresh,fixtures),'state_file':str(directory.name)+'/after-units.json'}

def qom_counters(client,sid,directory):
    result={}
    for prop in COUNTERS:
        query=urllib.parse.urlencode({'path':'/machine/units/external1/chip','property':prop})
        response=client.json(f'sessions/{sid}/qom?{query}',via_ui=False);save(directory/(prop+'.json'),response);result[prop]=response['value']
    return result

def zip_valid(data,result,request,fixtures):
    common.validate_zip(data,result,request)
    # This is the exact original validator, using this execution's frozen public fixture.
    old=contract.THERMAL;contract.THERMAL=fixtures
    try:summary=contract.validate_evidence(data,result,result['case']==NEGATIVE)
    finally:contract.THERMAL=old
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        serial=archive.read('serial.log').decode();need(not any(marker in serial for marker in FAILURES),'guest failure in ZIP')
        state=json.loads(archive.read('units/state.json'));state_valid(state,result)
        if result['case']!=NEGATIVE:
            for phase in range(len(result['changes'])+1):need(reading(result,phase,serial,fixtures),'ZIP lacks original initial/changed reading')
    return summary

def run_case(client,args,row):
    directory=args.out_dir/row['case'];fixtures=args.out_dir/'fixture-snapshot';request=load(directory/'source-request.json')
    result={**row,'status':'FAIL','started_at':now(),'checks':{},'steps':[],'injections':[],'hardware_validation':'NOT RUN'};sid=None;pid=None
    with common.HTTPRecorder(directory/'http'):
        try:
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'inventory.json',inventory)
            unit=next(u for u in inventory['units'] if u['id']==row['unit_id']);need('cores3' in unit['runtime']['hosts'],'sensor is not admitted on CoreS3')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware);result['source']=common.source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+row['source_cas_sha256'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact);need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS metadata differs')
            payload={'device_id':'cores3','runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ttl_seconds':900,'ready_marker':row['ready_marker'],'ready_timeout_seconds':240,'units':row['attachments']};save(directory/'session-request.json',payload)
            client.web_ui.call('prepare');created=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=created['session_id'];save(directory/'created-session.json',created);client._open_web_ui(sid,verify_runtime=False)
            print(row['case']+': source API visible session '+sid,flush=True)
            initial,running=wait_initial(client,sid,row,fixtures,directory);pid=running['pid']
            proof=client.web_ui.runtime_provenance(running,lambda:client.json(f'sessions/{sid}',via_ui=False));need(proof['status']=='VERIFIED' and proof['kind']=='direct-pid' and proof['runtime_binary_sha256']==row['expected_runtime_sha256'] and proof['worker_generation']==row['expected_worker_generation'],'direct PID/runtime/generation differs');result['runtime_provenance']=proof;client.web_ui_sessions[sid]['provenance_done']=True
            state=client.json(f'sessions/{sid}/units');save(directory/'initial-units.json',state);state_valid(state,row)
            result['initial_reading']=reading(row,0,initial['data'],fixtures);result['checks']['original_negative_markers_and_initial_reading']=bool(result['initial_reading'])
            frame=client.raw(f'sessions/{sid}/frame.png');(directory/'initial-frame.png').write_bytes(frame);common.frame_valid(frame)
            for phase,values in enumerate(row['changes'],1):
                step_dir=directory/'steps'/f'{phase:02d}';step_dir.mkdir(parents=True);step=changed_window(client,sid,row,phase,values,step_dir,fixtures);step['directory']='steps/'+step_dir.name;result['steps'].append(step);result['injections'].append({'sequence':phase,'values':values,'guest_observed':True})
            final=client.json(f'sessions/{sid}/units');save(directory/'final-units.json',final);props=state_valid(final,row);result['unit_state']=final
            counters=qom_counters(client,sid,directory/'qom');result['controller_counters']=counters
            need(all(type(v) is int and v>=0 for v in counters.values()),'I2C counter type/range invalid')
            if row['case']!=NEGATIVE:
                need(all(counters[k]>0 for k in ('transactions','read-bytes','written-bytes','samples-generated')),'original real I2C data plane counters are absent')
                if row['unit_id']=='tvoc':need(counters['crc-errors']>=1,'original invalid-argument CRC was not counted')
                need(len(result['steps'])==len(row['changes']),'initial+changes not completed')
            else:need(props['raw-fixture-ready'] is False,'missing raw fixture did not stay unavailable')
            result['checks']['fresh_changes_real_i2c_samples_and_crc']=True
            serial=serial_full(client,sid);save(directory/'final-serial.json',serial);(directory/'serial.txt').write_bytes(serial['data'].encode())
            frame=client.raw(f'sessions/{sid}/frame.png');(directory/'frame.png').write_bytes(frame);common.frame_valid(frame);result['checks']['native_png']=True
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if sid:
                try:
                    snapshot=client.json(f'sessions/{sid}',via_ui=False);save(directory/'before-evidence-session.json',snapshot);pid=pid or snapshot.get('pid')
                    data=client.raw(f'sessions/{sid}/evidence');(directory/'evidence.zip').write_bytes(data);result['evidence_sha256']=sha(data);result['evidence_summary']=zip_valid(data,result,request,fixtures);result['checks']['zip_before_stop_source_guest_binding']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop_source_guest_binding']=False
                try:
                    stopped=client.json(f'sessions/{sid}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped)
                    history=client.json(f'sessions/{sid}',via_ui=False);save(directory/'retained-session.json',history)
                    need(history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and history['firmware_provenance']==result.get('source'),'history/Flash/source retention differs')
                    need(type(pid) is int and pid>0,'owned PID not recorded');deadline=time.monotonic()+15
                    while not common.pid_gone(pid) and time.monotonic()<deadline:time.sleep(.1)
                    need(common.pid_gone(pid),'owned QEMU PID remains')
                    frame=client.raw(f'sessions/{sid}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(frame);common.frame_valid(frame)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0,'service/worker not idle after stop')
                    result['cleanup']={'owned_pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0};result['checks']['history_pid_flash_and_idle']=True
                except Exception as error:result['cleanup_error']=str(error);result['checks']['history_pid_flash_and_idle']=False
                try:
                    web=load(args.out_dir/'browser'/sid/'web-report.json');result['browser']=common.check_browser(web,sid,result['firmware_sha256'])
                    if row['changes']:need(web['posts'] and web['actions'],'changed sensor lacks real Web gestures/POSTs')
                    result['checks']['real_product_dom_and_http_match']=True
                except Exception as error:result['browser_error']=str(error);result['checks']['real_product_dom_and_http_match']=False
            result['finished_at']=now();result['status']='PASS' if sid and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL';save(directory/'result.json',result)
    print(row['case']+': '+result['status']+' '+result.get('error',''),flush=True);return result

def prepared_check(output):
    prepared=load(output/'prepared.json');need(prepared['status']=='PREPARED_NO_API_OR_RUNTIME','wrong preparation category')
    rows=prepared['cases'];need(rows and len({row['case'] for row in rows})==len(rows),'missing or duplicate prepared cases')
    freeze=load(output/'tooling-source-freeze.json')
    for name,digest in freeze.items():
        path=output/'fixture-snapshot'/name.removeprefix('FIXTURE/') if name.startswith('FIXTURE/') else output/'source-snapshot'/(name+'.txt')
        need(path.is_file() and not path.is_symlink() and sha(path.read_bytes())==digest,'frozen source/fixture changed: '+name)
    for row in rows:
        d=output/row['case'];request=load(d/'source-request.json');origins=load(d/'guest-source-freeze.json')
        need(row==load(d/'prepared.json') and request['expected_base_sha256']==BASE and request['device_id']=='cores3','prepared source/base identity differs')
        need(sha(canonical(request['files']))==row['source_cas_sha256'],'prepared source CAS differs')
        actual={p.relative_to(d/'files').as_posix():p.read_bytes() for p in (d/'files').rglob('*') if p.is_file()}
        need(set(actual)==set(request['files'])==set(row['source_files'])==set(origins),'caller source membership differs')
        for name,text in request['files'].items():
            raw=text.encode();need(actual[name]==raw and sha(raw)==row['source_files'][name]['sha256'] and len(raw)==row['source_files'][name]['size'],'caller file hash/size/body differs')
            origin=origins[name]
            if 'repository_path' in origin:need((output/'source-snapshot'/(origin['repository_path']+'.txt')).read_bytes()==raw,'caller source is not exact repository probe bytes')
            else:need(name=='probe_config.py' and origin['copy']=='generated-explicit-probe-config','unexpected generated source')
            ast.parse(text,filename=name)
        spec=case_spec(row['case'],output/'fixture-snapshot');config=f"CASE = {spec['unit_id']!r}\nWHITE = 1\nYELLOW = 2\nDEVICE_ID = 'cores3'\nNO_FIXTURE = {row['case']==NEGATIVE!r}\n"
        need(request['files']['probe_config.py']==config,'generated sensor configuration differs')
        need(row['attachments']==[{'id':'external1','unit_id':spec['unit_id'],'port_id':'port-a','initial':spec['initial']}] and row['changes']==spec['changes'] and row['negative_checks']==spec['negative'],'original initial/changes/negative contract differs')
        need(row['http_json_body_bytes']==len(json.dumps(request,allow_nan=False).encode())<=1024*1024,'HTTP body limit differs')
        for name,record in load(d/'official-driver-proof.json').items():need(sha(actual['sensor_drivers/'+name])==record['sha256'],'official driver changed')
        need((d/'license-evidence/sensor-drivers.LICENSE.MIT').read_bytes()==(output/'source-snapshot/tests/units/sensors_probe/sensor_drivers/LICENSE.MIT.txt').read_bytes(),'MIT license not frozen')
    return {'status':'PREPARED_NOT_EXECUTED','cases':[row['case'] for row in rows],'api_calls':0,'guest_execution':False,'binary_build_or_upload':False}

def actual_http(directory):
    events=load(directory/'http/index.json')
    for event in events:
        raw=(directory/'http'/event['response_file']).read_bytes();need(len(raw)==event['response_size'] and sha(raw)==event['response_sha256'],'HTTP response bytes changed')
        event['_raw']=raw
        try:event['_json']=json.loads(raw)
        except (ValueError,UnicodeDecodeError):event['_json']=None
        request=(directory/'http'/event['request_file']).read_bytes()
        try:event['_request']=json.loads(request)
        except (ValueError,UnicodeDecodeError):event['_request']=None
        source_only_intake(event['path'].removeprefix('/api/v1/'),event['method'])
    return events

def check_saved(output):
    prepared_check(output)
    need((output/'SHA256SUMS').is_file(),'frozen checksums missing')
    for line in (output/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==digest,'frozen artifact changed: '+name)
    fixtures=output/'fixture-snapshot';rows=load(output/'prepared.json')['cases'];results=[]
    for row in rows:
        d=output/row['case'];request=load(d/'source-request.json');firmware=load(d/'firmware-response.json');result=load(d/'result.json');sid=result['session_id'];prefix='/api/v1/sessions/'+sid
        need(result['status']=='PASS' and result['validation']==row['validation'] and result['hardware_validation']=='NOT RUN','case did not pass the correct category')
        need(common.source_provenance(firmware,request)==result['source'],'source API metadata differs')
        events=actual_http(d)
        def backed(value,suffix=None):return any(event['_json']==value and (suffix is None or event['path']==prefix+suffix) for event in events)
        need(any(event['method']=='POST' and event['path']=='/api/v1/firmware/uiflow' and event['status']==201 and event['_json']==firmware and event['_request']==request for event in events),'source composition lacks actual HTTP request/response')
        session_request=load(d/'session-request.json');need(session_request['uiflow_source_sha256']==row['source_cas_sha256'] and session_request['firmware_id']==firmware['firmware_id'] and session_request['units']==row['attachments'],'session sourcepin/image/topology differs')
        need(any(event['method']=='POST' and event['path']=='/api/v1/sessions' and event['status']==202 and event['_request']==session_request and event['_json']['session_id']==sid for event in events),'session has no actual sourcepin create request')
        proof=load(output/'browser'/sid/'runtime-provenance.json');running=load(d/'running-session.json')
        need(proof==result['runtime_provenance'] and proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==row['expected_runtime_sha256'] and proof['worker_generation']==row['expected_worker_generation'],'direct PID/runtime/worker proof differs')
        need(backed(running,'') and running['pid']==proof['observed_pid'] and running['firmware_provenance']==result['source'],'running PID/source is unbacked or differs')
        initial=load(d/'initial-reading-serial.json');need(backed(initial,'/serial') and negative_markers(row,initial['data']) and reading(row,0,initial['data'],fixtures),'original negative markers or initial guest reading absent')
        need(len(result['steps'])==len(row['changes']),'changed-input sequence incomplete')
        for phase,(step,values) in enumerate(zip(result['steps'],row['changes']),1):
            sd=d/step['directory'];before=load(sd/'before-cursor.json');chunks=load(sd/'chunks.json');fresh=(sd/'fresh-serial.txt').read_bytes().decode();cursor=before['next_offset'];text=''
            need(backed(before,'/serial') and cursor==step['initial_cursor'] and step['values']==values,'changed step initial cursor/input differs')
            for chunk in chunks:
                need(backed(chunk,'/serial') and chunk['offset']==cursor and chunk['next_offset']==cursor+chunk['bytes'] and len(chunk['data'].encode())==chunk['bytes'],'fresh serial chunk discontinuous or has no HTTP response');cursor=chunk['next_offset'];text+=chunk['data']
            need(text==fresh and sha(fresh.encode())==step['fresh_serial_sha256'] and cursor==step['final_cursor'] and reading(row,phase,fresh,fixtures),'fresh changed guest reading not reproduced')
            before_state=load(sd/'before-units.json');after_state=load(sd/'after-units.json');need(backed(before_state,'/units') and backed(after_state,'/units'),'changed QOM state lacks original HTTP')
            props=state_valid(after_state,row);need(all(props[k]==v for k,v in values.items()) and props['input-events']>state_valid(before_state,row)['input-events'],'changed physical input/counter differs')
            metrics=common.frame_valid((sd/'frame.png').read_bytes());need([metrics['width'],metrics['height']]==row['expected_size'],'step native frame dimensions differ')
        final=load(d/'final-units.json');need(backed(final,'/units') and final==result['unit_state'],'final Unit state lacks actual HTTP');state_valid(final,row)
        counters={}
        for prop in COUNTERS:
            response=load(d/'qom'/(prop+'.json'));need(any(event['path']==prefix+'/qom' and urllib.parse.parse_qs(event['query'])=={'path':['/machine/units/external1/chip'],'property':[prop]} and event['_json']==response for event in events),'chip counter lacks actual QOM HTTP response');counters[prop]=response['value']
        need(counters==result['controller_counters'] and all(type(v) is int and v>=0 for v in counters.values()),'recorded counter values differ')
        if row['case']!=NEGATIVE:
            need(all(counters[k]>0 for k in ('transactions','read-bytes','written-bytes','samples-generated')),'sensor data plane/sample counters absent')
            if row['unit_id']=='tvoc':need(counters['crc-errors']>=1,'bad argument CRC not counted')
        else:need(state_valid(final,row)['raw-fixture-ready'] is False,'negative missing fixture is ready')
        data=(d/'evidence.zip').read_bytes();need(sha(data)==result['evidence_sha256'],'ZIP bytes changed');zip_valid(data,result,request,fixtures)
        evidence=[i for i,event in enumerate(events) if event['path']==prefix+'/evidence' and event['_raw']==data];stop=[i for i,event in enumerate(events) if event['path']==prefix and event['method']=='DELETE' and event['query']=='purge=0' and event['status']==200];need(evidence and stop and max(evidence)<min(stop),'ZIP not captured before retained stop')
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            serial=archive.read('serial.log');need(serial.startswith((d/'serial.txt').read_bytes()),'ZIP lost observed guest serial')
            for i,event in enumerate(events):
                if event['path']==prefix+'/serial' and event['status']==200 and i<max(evidence):
                    chunk=event['_json'];need(serial[chunk['offset']:chunk['next_offset']].decode()==chunk['data'],'ZIP serial differs from actual HTTP guest bytes')
            hashes=json.loads(archive.read('units/contract.json'))['source_hashes'];freeze=load(output/'tooling-source-freeze.json')
            need(all(freeze['platform/units/'+name]==value for name,value in hashes.items()),'frozen Unit registry differs from ZIP')
        common.frame_valid((d/'frame.png').read_bytes());common.frame_valid((d/'history-frame.png').read_bytes())
        history=load(d/'retained-session.json');health=load(d/'cleanup-health.json')
        need(backed(history,'') and backed(health) and history['state']=='stopped' and history['flash_retained'] is False and history['firmware_provenance']==result['source'] and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0,'history/source/Flash/idle cleanup differs')
        need(result['cleanup']['pid_gone'] is True and result['cleanup']['owned_pid']==proof['observed_pid'],'recorded PID cleanup differs')
        web=load(output/'browser'/sid/'web-report.json');common.check_browser(web,sid,firmware['sha256'])
        for values in row['changes']:
            for key,value in values.items():need(any(event['status']==200 and event['request']['id']=='external1' and event['request']['values'].get(key)==value for event in web['posts']),'changed field lacks real browser POST')
        results.append({'case':row['case'],'session_id':sid,'status':'PASS','validation':row['validation'],'initial_and_changes_replayed':1+len(row['changes'])})
    need(len({r['session_id'] for r in results})==len(results),'sensor cases reused one guest')
    return {'status':'PASS','cases':results,'scope':'recorded CoreS3 source API + guest/I2C/Web/ZIP/cleanup only; hardware NOT RUN'}

def contract_self_tests():
    checks=0
    for case in SENSORS:
        if case=='thermal':continue
        spec=contract.CASES[case]
        for values in [spec['initial'],*spec['changes']]:
            expected=[values['distance-mm'],values['distance-mm']/10] if case in ('tof','ultrasonic-i2c') else [values[key] for key in spec['fields']]
            good=spec['marker']+' '+' '.join(map(str,expected))+'\n';need(contract.reading_matches(case,values,good),'original reading matcher rejected its exact vector')
            need(not contract.reading_matches(case,values,spec['marker']+' '+' '.join('nan' for _ in expected)+'\n'),'nonfinite values accepted');need(not contract.reading_matches(case,values,spec['marker']+' 0\n'),'wrong arity accepted');checks+=3
    for filename in ('fixture.json','synthetic-plus16.json'):
        expected=load(HERE/'fixtures'/filename)['expected'];text='SENSOR_THERMAL 768 768 '+' '.join(str(expected[k]) for k in ('min_c','max_c','mean_c'))+'\n'+''.join('SENSOR_THERMAL_PIXEL '+i+' '+str(v)+'\n' for i,v in expected['samples_c'].items())
        need(contract.thermal_reading(text,expected),'original thermal matcher rejected full reference')
        for bad in (text.replace('768 768','768 767'),text.replace('768 768','767 768'),text.rsplit('SENSOR_THERMAL_PIXEL',1)[0],text.replace(str(expected['samples_c']['0']),'nan')):need(contract.thermal_reading(bad,expected) is None,'incomplete/nonfinite thermal record accepted');checks+=1
    return checks

def self_check(output):
    from contextlib import ExitStack
    from unittest.mock import patch
    import socket,subprocess,urllib.request,builtins
    need(not output.exists(),'choose a fresh self-check output');output.mkdir(parents=True)
    denied=[]
    def deny(*args,**kwargs):denied.append('attempt');raise AssertionError('offline mode attempted API/process/BIN operation')
    original_import=builtins.__import__;original_write=Path.write_bytes
    def no_builder(name,*args,**kwargs):
        need(name.split('.')[0] not in {'run_service_cases','run_control_cases','run_profile_ui_test','littlefs'},'offline mode imported a builder/live Client');return original_import(name,*args,**kwargs)
    def no_bin(path,data):need(path.suffix.lower() not in {'.bin','.elf'},'offline mode wrote a firmware binary');return original_write(path,data)
    with ExitStack() as stack:
        for owner,name in ((urllib.request,'urlopen'),(socket,'socket'),(socket,'create_connection'),(subprocess,'Popen'),(subprocess,'run'),(subprocess,'call'),(os,'system'),(os,'popen')):stack.enter_context(patch.object(owner,name,deny))
        stack.enter_context(patch.object(builtins,'__import__',no_builder));stack.enter_context(patch.object(Path,'write_bytes',no_bin))
        rows=prepare(output/'prepared',list(CASES),11);prepared_check(output/'prepared');checks=contract_self_tests()
        for path in ('artifacts','firmware','firmware/import','artifact-uploads','artifact-uploads/x/chunks'):
            try:source_only_intake(path,'POST')
            except RuntimeError:pass
            else:raise AssertionError('binary intake path was accepted')
        for row in rows:need(not list((output/'prepared'/row['case']).rglob('*.bin')),'offline preparation created a BIN')
    need(not denied,'offline mode reached API/process entry points')
    report={'status':'PASS','prepared_cases':[r['case'] for r in rows],'original_contract_value_checks':checks,'deny_api_process_bin':True,'api_or_process_calls':0,'binary_files_written':0,'guest_execution':False,'hardware':'NOT RUN'};save(output/'self-check.json',report);return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,required=True);parser.add_argument('--case',choices=(*CASES,'all'),action='append');parser.add_argument('--execute',action='store_true');parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--check',action='store_true');parser.add_argument('--check-prepared',action='store_true');parser.add_argument('--self-check',action='store_true');parser.add_argument('--api-url',default='http://127.0.0.1:8787');parser.add_argument('--expected-worker-generation',type=int,default=11);args=parser.parse_args();args.out_dir=guarded(args.out_dir)
    need(sum(bool(x) for x in (args.execute,args.prepare_only,args.check,args.check_prepared,args.self_check))<=1,'choose one execution/offline mode')
    if args.self_check:print(json.dumps(self_check(args.out_dir),ensure_ascii=False,indent=2));return
    if args.check_prepared:print(json.dumps(prepared_check(args.out_dir),ensure_ascii=False,indent=2));return
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    cases=list(SENSORS) if not args.case or 'all' in args.case else list(dict.fromkeys(args.case));rows=prepare(args.out_dir,cases,args.expected_worker_generation)
    if not args.execute:print(json.dumps(prepared_check(args.out_dir),ensure_ascii=False,indent=2));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','execution requires explicit real Web bridge opt-in');need(urllib.parse.urlparse(args.api_url).hostname in ('localhost','127.0.0.1','::1'),'direct PID evidence requires localhost API');need(args.expected_worker_generation>0,'worker generation must be positive')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=RUNTIME
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
    from run_service_cases import Client
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**options):source_only_intake(path,method,options.get('body'));return super().raw(path,method=method,**options)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with common.HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0 and health['capacity']['worker']['generation']==args.expected_worker_generation,'service must start idle on the expected generation')
        for row in rows:
            result=run_case(client,args,row);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close();save(args.out_dir/'batch-result.json',{'status':'PASS' if len(results)==len(rows) and all(r['status']=='PASS' for r in results) else 'FAIL','finished_at':now(),'cases':[{k:r.get(k) for k in ('case','session_id','status','validation','error','cleanup_error')} for r in results]})
        files=sorted(p for p in args.out_dir.rglob('*') if p.is_file() and p.name!='SHA256SUMS');(args.out_dir/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(args.out_dir).as_posix()+'\n' for p in files))
    need(len(results)==len(rows) and all(r['status']=='PASS' for r in results),'one or more sensor source cases failed');print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
