from pathlib import Path
from datetime import datetime
from contextlib import ExitStack
from unittest.mock import patch
import ast,copy,hashlib,importlib.util,io,json,os,re,socket,subprocess,sys,urllib.request,zipfile
ROOT=Path.cwd();HERE=ROOT/'.work/unit-expanded-cross-review-20261026/controls-live';SOURCE=ROOT/'.work/unit-source-controls-expanded-20261026';LIVE=SOURCE/'live-v2-r1'
sha=lambda b:hashlib.sha256(b).hexdigest()
load=lambda p:json.loads(p.read_bytes())
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
sys.path[:0]=[str(ROOT/'.work/py312'),str(ROOT/'platform/tools'),str(ROOT/'platform/tests'),str(ROOT/'tests/units')]
calls=[]
def deny(*a,**kw):calls.append('forbidden');raise AssertionError('read-only audit attempted API/process')
with ExitStack() as guards:
 for owner,name in ((urllib.request,'urlopen'),(socket,'socket'),(socket,'create_connection'),(subprocess,'Popen'),(subprocess,'run'),(os,'system'),(os,'popen')):guards.enter_context(patch.object(owner,name,deny))
 spec=importlib.util.spec_from_file_location('reviewed_controls',SOURCE/'run_source_controls.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
 contract=load(SOURCE/'contract.json');assert sha((SOURCE/'run_source_controls.py').read_bytes())==contract['harness_sha256'];assert load(LIVE/'batch-result.json')['status']=='PASS'
 parity=h.verify_original_assertions();assert parity['assertion_count']==13
 prep=h.check_prepared(LIVE);replay=h.check_saved(LIVE);save('original-checker-replay.json',{'preparation':prep,'recorded_live':replay})
 rows=load(LIVE/'prepared.json')['cases'];frozen=load(LIVE/'tooling-source-freeze.json');details={}
 fixture=load(LIVE/'source-snapshot/platform/units/fixtures/cardkb-keymap.json.txt')
 for row in rows:
  case=row['unit_id'];d=LIVE/case;r=load(d/'result.json');sid=r['session_id'];prefix='/api/v1/sessions/'+sid;request=load(d/'source-request.json');files=request['files'];events=load(d/'http/index.json');web=load(LIVE/'browser'/sid/'web-report.json')
  actual=[]
  for index,e in enumerate(events):
   raw=(d/'http'/e['response_file']).read_bytes();assert sha(raw)==e['response_sha256'] and len(raw)==e['response_size']
   try:body=json.loads(raw)
   except (ValueError,UnicodeDecodeError):body=None
   actual.append((index,e,body,raw))
  def backed(value,path):return [i for i,e,b,_ in actual if e['path']==path and e['status']//100==2 and b==value]
  source_cas=sha(json.dumps(files,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode());assert source_cas==row['source_cas_sha256']==r['source']['artifact_id']
  source_api=[(i,e,b) for i,e,b,_ in actual if e['path']=='/api/v1/firmware/uiflow' and e['method']=='POST' and e['status']==201]
  assert len(source_api)==1 and json.loads((d/'http'/source_api[0][1]['request_file']).read_bytes())==request and source_api[0][2]==load(d/'firmware-response.json')
  # Reverse display-only substitutions independently and compare actual original bytes.
  original=files['main.py']
  for a,b in reversed(h.DISPLAY_REPLACEMENTS):assert original.count(b)==1;original=original.replace(b,a)
  assert original.encode()==(LIVE/'source-snapshot/tests/units/controls_probe/main.py.txt').read_bytes()
  assert files['host_control_layout.py'].encode()==(LIVE/'source-snapshot/tests/units/host_controls_probe/host_control_layout.py.txt').read_bytes()
  origins=load(d/'guest-source-freeze.json');drivers=load(d/'official-driver-proof.json')
  for name,record in drivers.items():assert sha(files[name].encode())==record['sha256'] and files[name].encode()==(ROOT/origins[name]['repository_path']).read_bytes()
  session_request=load(d/'session-request.json');assert session_request['uiflow_source_sha256']==source_cas and session_request['firmware_id']==r['firmware_sha256']
  creates=[(i,e,b) for i,e,b,_ in actual if e['path']=='/api/v1/sessions' and e['method']=='POST']
  assert [e['status'] for _,e,_ in creates]==[400,409,202]
  for (index,e,body),label,status,code in zip(creates[:2],('missing-source-pin','wrong-source-pin'),(400,409),('binding_required','binding_mismatch')):
   raw=(d/'http'/e['response_file']).read_bytes().decode();assert code in raw and e['status']==status
   payload=json.loads((d/'http'/e['request_file']).read_bytes());assert ('uiflow_source_sha256' not in payload) if status==400 else payload['uiflow_source_sha256']=='0'*64
  assert json.loads((d/'http'/creates[-1][1]['request_file']).read_bytes())==session_request and creates[-1][2]['session_id']==sid
  pinhealth=load(d/'after-pin-negative-health.json');assert backed(pinhealth,'/api/v1/health') and pinhealth['capacity']['active_sessions']==pinhealth['capacity']['worker']['active_lease_count']==0
  proof=load(LIVE/'browser'/sid/'runtime-provenance.json');assert proof==r['runtime_provenance'] and proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==h.RUNTIME and proof['worker_generation']==11
  running=load(d/'running-session.json');assert backed(running,prefix) and running['pid']==proof['observed_pid'] and running['firmware_provenance']==r['source']
  bundle=(d/'evidence.zip').read_bytes();ziprows=[i for i,e,b,raw in actual if e['path']==prefix+'/evidence' and e['status']==200 and raw==bundle];stoprows=[i for i,e,b,raw in actual if e['path']==prefix and e['method']=='DELETE' and e['query']=='purge=0' and e['status']==200];assert ziprows and stoprows and max(ziprows)<min(stoprows)
  with zipfile.ZipFile(io.BytesIO(bundle)) as z:
   serial=z.read('serial.log');manifest=json.loads(z.read('manifest.json'));state=json.loads(z.read('units/state.json'))
   assert manifest['session']['pid']==proof['observed_pid'] and manifest['session']['worker']['worker_id']==proof['worker_id'] and manifest['session']['worker']['generation']==proof['worker_generation'] and manifest['session']['worker']['lease_active'] is True
   assert manifest['session']['firmware_provenance']==r['source']==json.loads(z.read('firmware/uiflow-source.json'))
   for name,meta in manifest['files'].items():assert len(z.read(name))==meta['size'] and sha(z.read(name))==meta['sha256']
   serial_ranges=0
   for index,e,b,raw in actual:
    if index<max(ziprows) and e['path']==prefix+'/serial' and e['status']==200:
     assert b['next_offset']==b['offset']+b['bytes'] and b['bytes']==len(b['data'].encode()) and serial[b['offset']:b['next_offset']]==b['data'].encode();serial_ranges+=1
   assert serial.startswith((d/'serial.txt').read_bytes())
  steps=load(d/'input-steps.json');assert steps==r['steps']
  for step in steps:
   before=(d/step['before_file']).read_bytes();assert sha(before)==step['before_sha256'] and len(before)==step['serial_offset'] and serial.startswith(before)
   assert any(e['path']==prefix+'/serial' and e['status']==200 and isinstance(b,dict) and b.get('data','').encode()==before for _,e,b,_ in actual)
   assert backed(step['state_before'],prefix+'/units')
  final=load(d/'final-units.json');assert final==r['unit_state'] and backed(final,prefix+'/units');props=final['units'][0]['properties']
  assert all(type(props[k]) is int and props[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events'))
  assert all(snap['units'][0]['readback']['properties']==next(u['properties'] for response in web['readbacks']+web['posts'] for u in response.get('response',{}).get('units',[]) if u['id']==snap['units'][0]['instance'] and u['properties']==snap['units'][0]['readback']['properties']) for snap in web['snapshots'] if snap.get('session_state')=='running')
  history=load(d/'retained-session.json');stop=load(d/'stop-response.json');health=load(d/'cleanup-health.json')
  assert backed(history,prefix) and backed(stop,prefix) and backed(health,'/api/v1/health') and history['state']=='stopped' and history['flash_retained'] is False and history['last_frame_available'] is True and history['firmware_provenance']==r['source'] and health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0
  assert r['cleanup']['owned_pid']==proof['observed_pid'] and r['cleanup']['pid_gone'] is True
  detail={'source_cas_sha256':source_cas,'source_files':len(files),'official_driver_proofs':len(drivers),'display_only_reverse_bytes_verified':True,'raw_http_events':len(events),'raw_serial_ranges_bound_to_zip':serial_ranges,'actual_steps':len(steps),'runtime_sha256':proof['runtime_binary_sha256'],'worker_generation':proof['worker_generation'],'zip_before_stop':True,'cleanup_history_flash_idle_raw_http':True,'i2c_counters':{k:props[k] for k in ('transactions','read-bytes','written-bytes','input-events')}}
  text=(d/'serial.txt').read_bytes().decode()
  if case=='rfid2':
   uids=('04010203','04010203040506','04010203040506070809');negatives=('CONTROL_RFID_BAD_CRC 1','CONTROL_RFID_BAD_KEY 1','CONTROL_RFID_SECTOR_DENIED 1','CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40','CONTROL_RFID_HALT_DENIED 1','CONTROL_RFID_ANTENNA_OFF 1');phases=[]
   assert [s['values'] for s in steps]==[{'uid-hex':uid,'card-present':True} for uid in uids]+[{'card-present':False}]
   action_cursor=0;post_cursor=0
   for step in steps:
    for key,value in step['values'].items():
     action=web['actions'][action_cursor];action_cursor+=1;assert action['field']==key and action['value']==value
     if action['kind']=='already-equal-noop':assert step['state_before']['units'][0]['properties'][key]==value
     else:
      post=web['posts'][post_cursor];post_cursor+=1
      assert action['request']==post['request']=={'id':'external1','values':{key:value}} and action['response_status']==post['status']==200
      assert post['response']['units'][0]['properties'][key]==value
    assert all(step['ui_readback_response']['units'][0]['properties'][key]==value for key,value in step['values'].items())
   assert action_cursor==len(web['actions']) and post_cursor==len(web['posts'])
   for i,uid in enumerate(uids):
    start,end=steps[i]['serial_offset'],steps[i+1]['serial_offset'];phase=text[start:end];ordered=['CONTROL_RFID_UID '+uid,*negatives];last=0;positions={}
    for marker in ordered:
     match=re.search(r'(?m)^'+re.escape(marker)+r'\r?$',phase[last:]);assert match is not None,(uid,marker);positions[marker]=start+last+match.start();last+=match.end()
    assert sum(line.startswith('CONTROL_RFID_UID ') for line in phase.splitlines())>=1
    phases.append({'uid_bytes':len(uid)//2,'start':start,'end_exclusive':end,'ordered_marker_offsets':positions})
   assert re.search(r'(?m)^CONTROL_RFID_NO_CARD\r?$',text[steps[-1]['serial_offset']:]) and props['card-present'] is False
   detail['closed_fresh_uid_phases']=phases
  if case=='cardkb':
   normal=[k for k in fixture['keys'] if not k['modifier']];by_id={k['id']:k for k in fixture['keys']};assert len(normal)==47 and len(fixture['keys'])==50
   pieces={'normal':[k['normal'] for k in normal if k['normal']],'one_shots':[]}
   for field in ('shift','sym','fn'):pieces['one_shots'] += [v for v in (by_id['key-q'][field],by_id['key-q']['normal']) if v]
   for field in ('shift','sym','fn'):pieces[field]=[k[field] for k in normal if k[field]]
   pieces['legacy']=[65];expected=sum(pieces.values(),[]);observed=[int(v) for v in re.findall(r'(?m)^CONTROL_CARDKB_KEY (\d+)\r?$',text[r['cardkb_start_offset']:])];assert len(expected)==187 and observed==expected==r['cardkb_expected_stream']
   mask=[False]*50;expected_steps=[];expected_posts=[];double_offsets=[];unlock_offsets=[]
   def tap(key,record_step=True):
    index=by_id[key]['index']
    for down in (True,False):
     mask[index]=down;value={'keys':mask.copy()};expected_posts.append({'id':'external1','values':value})
     if record_step:expected_steps.append(value)
   for key in normal:tap(key['id'])
   for modifier in ('key-shift','key-sym','key-fn'):tap(modifier);tap('key-q');tap('key-q')
   for modifier in ('key-shift','key-sym','key-fn'):
    double_offsets.append(len(expected_posts));tap(modifier,False);tap(modifier,False)
    for key in normal:tap(key['id'])
    tap(modifier);unlock_offsets.append(len(expected_posts)-1)
   expected_posts.append({'id':'external1','values':{'keycode':65}});expected_steps.append({'keycode':65})
   assert [s['values'] for s in steps]==expected_steps and len(steps)==401
   assert len(web['posts'])==413 and [p['request'] for p in web['posts']]==expected_posts and all(p['status']==200 for p in web['posts'])
   doubles=[a for a in web['actions'] if a.get('kind')=='real-mouse-double-click'];assert len(doubles)==3;locks=[]
   for number,(offset,mode,unlock,modifier) in enumerate(zip(double_offsets,(2,4,6),unlock_offsets,('key-shift','key-sym','key-fn'))):
    posts=web['posts'][offset:offset+4];modes=[p['response']['units'][0]['properties']['modifier-mode'] for p in posts];assert modes==[mode-1,mode-1,mode,mode]
    assert web['posts'][unlock]['response']['units'][0]['properties']['modifier-mode']==0
    assert doubles[number]['index']==by_id[modifier]['index'] and doubles[number]['posts']==4 and doubles[number]['field']=='keys'
    down_ms=(datetime.fromisoformat(posts[2]['at'].replace('Z','+00:00'))-datetime.fromisoformat(posts[0]['at'].replace('Z','+00:00'))).total_seconds()*1000;assert 0<down_ms<=200
    assert any(e['path']==prefix+'/units' and e['status']==200 and b['units'][0]['properties']['modifier-mode']==mode for _,e,b,_ in actual if isinstance(b,dict) and b.get('units'))
    locks.append({'modifier':modifier,'post_start':offset,'locked_mode':mode,'raw_post_modes':modes,'down_to_down_ms':down_ms,'unlock_post':unlock,'unlock_mode':0})
   detail.update(cardkb_stream_count=len(observed),independent_stream_sha256=sha(bytes(expected)),stream_piece_lengths={k:len(v) for k,v in pieces.items()},exact_matrix_and_legacy_browser_posts=413,exact_recorded_input_steps=401,double_locks=locks)
  if case=='8encoder':
   assert 'CONTROL_ENCODER8_REGISTER_WRITE -1234567 0' in text and 'CONTROL_ENCODER8_ADDRESS 66' in text
   assert props['led-rgb']==[i*0x010203 for i in range(1,9)]+[0x192939] and props['i2c-address']==0x42
   vector=[1,-2,123456,-123456,2147483647,-2147483648,7,8];buttons=[True,False,True,False,False,True,False,True]
   prefixline='CONTROL_ENCODER8 %s %s 1 INC '%(vector,[int(v) for v in buttons]);matched=[line[len(prefixline):] for line in text[steps[0]['serial_offset']:].splitlines() if line.startswith(prefixline)];assert matched
   inc=ast.literal_eval(matched[-1]);assert len(inc)==8 and all(type(v) is int for v in inc)
   detail.update(guest_register_set_reset=True,all_nine_led_register_triplets=props['led-rgb'],guest_address=props['i2c-address'],increments=inc)
  details[case]=detail
 assert not calls
 save('independent-actual-evidence.json',{'status':'PASS','scope':'terminal controls4 actual recorded evidence independently recomputed; no API/process/guest execution; hardware NOT RUN','harness_sha256':sha((SOURCE/'run_source_controls.py').read_bytes()),'original_assertion_parity':parity,'guarded_api_process_calls':0,'cases':details,'pid_limit':'Replay validates directly proven owned PID and execution-time termination record plus backed stop/history/idle; no new OS PID observation.'})
 print(json.dumps({'status':'PASS','cases':list(details),'cardkb_stream_count':details['cardkb']['cardkb_stream_count'],'cardkb_browser_posts':details['cardkb']['exact_matrix_and_legacy_browser_posts'],'rfid_closed_uid_phases':len(details['rfid2']['closed_fresh_uid_phases']),'api_or_process_calls':len(calls)},indent=2))
