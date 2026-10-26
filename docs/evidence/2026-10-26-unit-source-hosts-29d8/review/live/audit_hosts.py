#!/usr/bin/env python3
"""Independent offline audit of the root-terminal host9 source API batch."""
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import ast,hashlib,importlib.util,io,json,os,re,socket,subprocess,sys,urllib.request,zipfile
ROOT=Path.cwd();OUT=ROOT/'.work/unit-source-hosts-live-review-20261026';SOURCE=ROOT/'.work/unit-source-hosts-expanded-20261026';LIVE=SOURCE/'live-post-sync-r1';COMMIT='0fe6a013b7ca040583339ef7827d4daf8e3810dc'
load=lambda p:json.loads(p.read_bytes());sha=lambda b:hashlib.sha256(b).hexdigest()
def save(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
sys.path[:0]=[str(SOURCE),str(ROOT/'.work/py312'),str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
forbidden=[]
def deny(*a,**k):forbidden.append('attempt');raise AssertionError('offline host review attempted API/process')
with ExitStack() as guards:
 for owner,name in ((urllib.request,'urlopen'),(socket,'socket'),(socket,'create_connection'),(subprocess,'Popen'),(subprocess,'run'),(subprocess,'check_output'),(os,'system'),(os,'popen')):guards.enter_context(patch.object(owner,name,deny))
 batch=load(LIVE/'batch-result.json');assert batch['status']=='PASS' and batch['finished_at']
 spec=importlib.util.spec_from_file_location('reviewed_host_harness',SOURCE/'run_source_hosts.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 original=h.original_module();guards.enter_context(patch.object(original,'prepare',deny));guards.enter_context(patch.object(original,'build_control_image',deny))
 report=h.check_saved(LIVE);save('runner-offline-replay.json',report)
 contract=load(OUT/'expected-contract.json');prepared=load(LIVE/'prepared.json');rows=prepared['cases'];frozen=load(LIVE/'tooling-source-freeze.json')
 assert len(rows)==9 and {(r['device_id'],r['unit_id']) for r in rows}=={(d,c) for d in contract['hosts'] for c in contract['cases']}
 assert prepared['source_context_commit']==COMMIT and prepared['source_context_stage']=='ROOT_SUPPLIED_POST_SYNC'
 assert sha((LIVE/'source-snapshot/HARNESS/run_source_hosts.py.txt').read_bytes())==frozen['HARNESS/run_source_hosts.py']==contract['prepared_harness_snapshot_sha256']
 for name,digest in frozen.items():assert sha((LIVE/'source-snapshot'/(name+'.txt')).read_bytes())==digest
 expected_functions=h.original_functions();assert expected_functions==load(LIVE/'original-functions.json')
 details=[]
 for row in rows:
  device,case=row['device_id'],row['unit_id'];d=LIVE/device/case;r=load(d/'result.json');sid=r['session_id'];prefix='/api/v1/sessions/'+sid;request=load(d/'source-request.json');files=request['files'];profile=contract['hosts'][device]
  assert row['source_context_commit']==COMMIT and row['source_context_stage']=='ROOT_SUPPLIED_POST_SYNC' and r['status']=='PASS'
  assert set(files)=={'boot.py','main.py','host_program.py','probe_logging.py','probe_config.py'} and row['uploaded_driver_files']==[] and row['adc_fixture']=='NOT USED'
  for name,rawhash in contract['source_files'].items():assert sha(files[name].encode())==rawhash and files[name].encode()==(ROOT/'tests/units/host_probe'/name).read_bytes()
  assert {p.relative_to(d/'files').as_posix():p.read_bytes() for p in (d/'files').rglob('*.py')}=={name:text.encode() for name,text in files.items()}
  cfg={n.targets[0].id:ast.literal_eval(n.value) for n in ast.parse(files['probe_config.py']).body if isinstance(n,ast.Assign)}
  assert cfg=={'CASE':case,'DEVICE_ID':device,'WHITE':profile['grove_pins']['white'],'YELLOW':profile['grove_pins']['yellow'],'ROTATION':profile['rotation'],'FRAME_WIDTH':profile['native'][0],'FRAME_HEIGHT':profile['native'][1],'CANVAS_WIDTH':profile['canvas'][0],'CANVAS_HEIGHT':profile['canvas'][1],'TEXT_X':profile['text'][0],'TEXT_Y':profile['text'][1],'TEXT_WIDTH':profile['text'][2],'INTERNAL_SDA':profile['internal_sda'],'INTERNAL_SCL':profile['internal_scl'],'INTERNAL_CONTROLLER':1,'EXTERNAL_CONTROLLER':0,'LOG_TX':43,'LOG_RX':44}
  cas=sha(json.dumps(files,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode());assert cas==row['source_cas_sha256']==r['source']['artifact_id'] and request['expected_base_sha256']==row['base_firmware_sha256']==profile['base_sha256']
  if (ROOT/profile['reference_file']).is_file():assert sha((ROOT/profile['reference_file']).read_bytes())==profile['base_sha256']
  firmware=load(d/'firmware-response.json');meta=firmware['source']['metadata'];assert meta['base_sha256']==profile['base_sha256'] and meta['source_sha256']==meta['effective_source_sha256']==cas and not meta['generated_files'] and meta['caller_file_count']==5
  assert meta['vfs']['offset']==row['reference_layout']['offset'] and meta['vfs']['size']==row['reference_layout']['size'] and all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified'))
  actual=[]
  for index,e in enumerate(load(d/'http/index.json')):
   raw=(d/'http'/e['response_file']).read_bytes();assert sha(raw)==e['response_sha256'] and len(raw)==e['response_size']
   try:body=json.loads(raw)
   except (ValueError,UnicodeDecodeError):body=None
   actual.append((index,e,body,raw))
  def backed(value,path,method=None):return [i for i,e,b,_ in actual if e['path']==path and e['status']//100==2 and b==value and (method is None or e['method']==method)]
  source_posts=[(i,e,b) for i,e,b,_ in actual if e['path']=='/api/v1/firmware/uiflow' and e['method']=='POST' and e['status']==201];assert len(source_posts)==1 and source_posts[0][2]==firmware and json.loads((d/'http'/source_posts[0][1]['request_file']).read_bytes())==request
  startup=load(d/'session-request.json');assert startup['device_id']==device and startup['firmware_id']==firmware['firmware_id']==r['firmware_sha256'] and startup['uiflow_source_sha256']==cas and startup['units']==row['attachments']
  creates=[(i,e,b) for i,e,b,_ in actual if e['path']=='/api/v1/sessions' and e['method']=='POST' and e['status']==202];assert len(creates)==1 and creates[0][2]['session_id']==sid and json.loads((d/'http'/creates[0][1]['request_file']).read_bytes())==startup
  assert not any(e['method'] in ('POST','PUT','PATCH') and (e['path'] in ('/api/v1/artifacts','/api/v1/firmware','/api/v1/firmware/import') or e['path'].startswith('/api/v1/artifact-uploads')) for _,e,_,_ in actual)
  proof=load(LIVE/'browser'/sid/'runtime-provenance.json');assert proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==h.RUNTIME and proof['worker_generation']==11 and r['runtime_provenance']=={**proof,'pid':proof['observed_pid']}
  ready,running=load(d/'ready-session.json'),load(d/'running-session.json');assert backed(ready,prefix,'GET') and backed(running,prefix,'GET') and ready['pid']==running['pid']==proof['observed_pid'] and running['firmware_provenance']==r['source']
  data=(d/'evidence.zip').read_bytes();zipindices=[i for i,e,_,raw in actual if e['path']==prefix+'/evidence' and e['status']==200 and raw==data];stopindices=[i for i,e,_,_ in actual if e['path']==prefix and e['method']=='DELETE' and e['query']=='purge=0' and e['status']==200];assert len(zipindices)==len(stopindices)==1 and zipindices[0]<stopindices[0]
  with zipfile.ZipFile(io.BytesIO(data)) as z:
   assert z.testzip() is None and len(z.namelist())==len(set(z.namelist()));manifest=json.loads(z.read('manifest.json'));zipserial=z.read('serial.log');zs=manifest['session'];zu=json.loads(z.read('units/state.json'))
   assert zs['pid']==proof['observed_pid'] and zs['worker']['worker_id']==proof['worker_id'] and zs['worker']['generation']==11 and zs['worker']['lease_active'] is True and zs['firmware_provenance']==r['source']==json.loads(z.read('firmware/uiflow-source.json'))
   for name,record in manifest['files'].items():assert len(z.read(name))==record['size'] and sha(z.read(name))==record['sha256']
   for name,digest in json.loads(z.read('units/contract.json'))['source_hashes'].items():assert frozen['platform/units/'+name]==digest
   uart_ranges=0
   for index,e,b,_ in actual:
    if index<zipindices[0] and e['path']==prefix+'/serial' and e['status']==200:
     assert b['next_offset']==b['offset']+b['bytes'] and b['bytes']==len(b['data'].encode()) and zipserial[b['offset']:b['next_offset']]==b['data'].encode();uart_ranges+=1
   assert zipserial.startswith((d/'serial.txt').read_bytes()) and zipserial.startswith((d/'serial-final.txt').read_bytes())
  trace=load(d/'observation-index.json');serial=(d/'serial-final.txt').read_bytes().decode();assert not any(marker in serial for marker in original.FAILURES)
  assert re.search(r'(?m)^HOST_GEOMETRY %d %d %d\r?$'%(*profile['canvas'],profile['rotation']),serial) and re.search(r'(?m)^HOST_PROBE_READY '+device+' '+case+r'\r?$',serial)
  internal=[(phase,int(identity),int(count)) for phase,identity,count in re.findall(r'(?m)^HOST_INTERNAL (before|after_init|loop) (\d+) (\d+)\r?$',serial)];assert internal[:2]==[('before',36,1),('after_init',36,2)] and all(value==36 for _,value,_ in internal) and all(a[2]<b[2] for a,b in zip(internal,internal[1:]))
  for event in trace:
   if event['kind'] in ('wait-success','marker'):
    text=(d/event['serial_file']).read_bytes().decode();assert sha(text.encode())==event['serial_sha256'] and any(e['path']==prefix+'/serial' and e['status']==200 and isinstance(b,dict) and b.get('data')==text for _,e,b,_ in actual)
   elif event['kind']=='state':assert backed(load(d/event['file']),prefix+'/units','GET')
   elif event['kind']=='input':assert event['accepted'] is True and backed(event['before_cursor'],prefix+'/serial','GET')
  inputs=[e for e in trace if e['kind']=='input'];windows=[]
  for index,event in enumerate(inputs):
   before=event['before_cursor'];waits=[e for e in trace if e['kind']=='wait-success' and e.get('input_event')==event['event_id']];assert waits
   observed=(d/waits[-1]['serial_file']).read_bytes();start=before['next_offset'];end=len(observed);upper=inputs[index+1]['before_cursor']['next_offset'] if index+1<len(inputs) else end
   assert before['offset']==0 and start==before['bytes']==len(before['data'].encode()) and observed.startswith(before['data'].encode()) and start<end<=upper
   windows.append({'input_event':event['event_id'],'lower':start,'observed_end':end,'next_input_upper':upper,'fresh':observed[start:].decode()})
  final=load(d/'final-units.json');assert final==r['unit_state'] and backed(final,prefix+'/units','GET');unit=final['units'][0];props=unit['properties'];assert unit['id']=='external1' and unit['unit_id']==case and unit['pins']==profile['grove_pins'] and unit['source']=='guest-qom' and unit['available'] and not unit['errors']
  states=[(e,load(d/e['file'])['units'][0]['properties']) for e in trace if e['kind']=='state']
  if case=='button':
   assert len(inputs)==4 and [e['values'] for e in inputs]==[{'pressed':v} for v in (True,False,True,False)]
   irq=[]
   for index,(window,pressed) in enumerate(zip(windows,(True,False,True,False))):
    values=[(int(raw),int(count)) for raw,count in re.findall(r'(?m)^HOST_BUTTON ([01]) (\d+)\r?$',window['fresh'])];matches=[v for v in values if v[0]==int(not pressed) and v[1]>=index];assert matches;irq.append({'pressed':pressed,'original_minimum_irq':index,'observed_matches':matches})
   semantics={'button_fresh_edges':irq,'oracle':'Original raw level + count>=index preserved; no new exact-count/stability gate'}
  elif case=='relay':
   assert not inputs and re.search(r'(?m)^HOST_RELAY 1\r?$',serial) and re.search(r'(?m)^HOST_RELAY 0\r?$',serial)
   levels=[p['output-level'] for _,p in states];assert set(levels)=={True,False} and len(levels)>=16
   semantics={'relay_recorded_qom_levels':levels,'input_count':0,'oracle':'Both original guest output markers and actual QOM levels; no host-forced output'}
  else:
   assert len(inputs)==2 and re.search(r'(?m)^HOST_EXTERNAL_SCAN 68 112\r?$',serial)
   vectors=[]
   for event,window,expected in zip(inputs,windows,((31.5,67,98765),(18.75,45.5,103200))):
    assert event['values']==dict(zip(('temperature-c','humidity-pct','pressure-pa'),expected));values=[[float(v) for v in fields] for fields in re.findall(r'(?m)^HOST_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$',window['fresh'])];matches=[v for v in values if all(abs(a-b)<=tol for a,b,tol in zip(v,expected,(.2,.2,1)))];assert matches and 'HOST_INTERNAL loop 36 ' in window['fresh'];vectors.append({'expected':expected,'observed_matches':matches})
   assert all(props[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events'))
   semantics={'env_fresh_vectors':vectors,'external_scan':[68,112],'onboard_bmi_after_each_vector':True,'controller_counters':{k:props[k] for k in ('transactions','read-bytes','written-bytes','input-events')}}
  # Preserve the original final internal-read wait, not only an unconditional save.
  final_waits=[e for e in trace if e['kind']=='wait-success' and e.get('input_event')==(inputs[-1]['event_id'] if inputs else None)];assert any(e['offset']>0 and 'HOST_INTERNAL loop 36 ' in (d/e['serial_file']).read_bytes().decode()[e['offset']:] for e in final_waits)
  web=load(LIVE/'browser'/sid/'web-report.json');h.browser_check(web,r)
  expected_posts=[{'id':'external1','values':{key:value}} for event in inputs for key,value in event['values'].items()]
  assert [p['request'] for p in web['posts']]==expected_posts and all(p['status']==200 for p in web['posts']) and len(web['actions'])==len(expected_posts)
  for post in web['posts']:
   assert all(post['response']['units'][0]['properties'][key]==value for key,value in post['request']['values'].items())
  history,stop,health=load(d/'retained-session.json'),load(d/'stop-response.json'),load(d/'cleanup-health.json');assert backed(history,prefix,'GET') and backed(stop,prefix,'DELETE') and backed(health,'/api/v1/health','GET')
  assert history['state']=='stopped' and history['flash_retained'] is False and history['last_frame_available'] is True and not history['worker']['lease_active'] and history['firmware_provenance']==r['source'] and health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0 and r['cleanup']['owned_pid']==proof['observed_pid'] and r['cleanup']['pid_gone'] is True
  for name in ('frame.png','history-frame.png'):
   raw=(d/name).read_bytes();h.frame(raw,row);assert any(e['path']==prefix+'/frame.png' and body==raw for _,e,_,body in actual)
  details.append({'device_id':device,'unit_id':case,'session_id':sid,'status':'PASS','source_context_commit':COMMIT,'source_cas_sha256':cas,'base_sha256':profile['base_sha256'],'five_original_config_source_files':True,'native':profile['native'],'guest_canvas':profile['canvas'],'grove_pins':profile['grove_pins'],'internal_i2c':{'controller':1,'sda':profile['internal_sda'],'scl':profile['internal_scl'],'chip_id':36,'reads':len(internal),'last_read_counter':internal[-1][2]},'semantics':semantics,'fresh_windows':[{k:v for k,v in w.items() if k!='fresh'} for w in windows],'real_browser_posts':len(web['posts']),'raw_http_events':len(actual),'raw_serial_ranges_bound_to_zip':uart_ranges,'runtime_sha256':proof['runtime_binary_sha256'],'worker_generation':11,'zip_before_stop':True,'raw_history_flash_idle_cleanup':True,'native_frame_sha256':sha((d/'frame.png').read_bytes()),'pid_exit':'Execution-time owned-PID record verified; no new OS process sampling'})
 assert len({r['session_id'] for r in details})==9 and not forbidden
 save('independent-live-review.json',{'status':'PASS','scope':'Exact terminal post-sync host9 source/guest/controller/Web/ZIP/cleanup bytes; native visual inspection is reported separately','source_context_commit':COMMIT,'harness_sha256':sha((SOURCE/'run_source_hosts.py').read_bytes()),'api_or_process_calls':0,'hardware':'NOT RUN','cases':details,'limitations':['Only these captured post-sync sources/firmware/runtime and three hosts are covered.','Bundled reference drivers were not independently rebuilt or tied to an upstream driver source commit.','Button retains the original variable count>=index oracle; no additional exact count/stability gate.','Runtime PID exit is historical executor evidence, not a new process observation.','Readability conclusions are restricted to separately opened captured final PNGs.']})
 print(json.dumps({'status':'PASS','cases':len(details),'hosts':sorted({r['device_id'] for r in details}),'api_or_process_calls':0,'source_context_commit':COMMIT},indent=2))
