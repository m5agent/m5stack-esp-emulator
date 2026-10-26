"""Independent offline review of the terminal default-nine bundle only."""
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import parse_qs
from PIL import Image
import ast, hashlib, io, json, math, re, zipfile
ROOT=Path.cwd();SOURCE=ROOT/'.work/unit-source-io-expanded-20261026/live-default9-r1'
OUT=ROOT/'.work/unit-expanded-cross-review-20261026/io-live'
CASES=('pir','dual-button','limit','key','angle','light','fan','rs485','hub')
RUNTIME='29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
BASE='1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264'
checks=[]
def need(value,label):
 checks.append(label)
 if not value:raise AssertionError(label)
def load(path):return json.loads(path.read_bytes())
def sha(data):return hashlib.sha256(data).hexdigest()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def has(text,line):return re.search(r'(?m)^'+re.escape(line)+r'\r?$',text) is not None
def props(state,instance='external1'):return next(u['properties'] for u in state['units'] if u['id']==instance)
def same_frame(data):
 with Image.open(io.BytesIO(data)) as image:
  image.load();need(image.format=='PNG' and image.size==(320,240) and image.convert('RGB').getcolors(maxcolors=1) is None,'nonblank native PNG')
def function_hashes(text):
 tree=ast.parse(text);names=('Observations','validate_io','validate_evidence','attachments','buzzer_timer_window')
 return {n.name:sha(ast.get_source_segment(text,n).encode()) for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names}

# Whole-bundle integrity and exact original assertion implementation, not result booleans.
bundle_rows=(SOURCE/'SHA256SUMS').read_text().splitlines()
for line in bundle_rows:
 expected,name=line.split('  ',1);p=(SOURCE/name).resolve();need(p.is_relative_to(SOURCE.resolve()) and sha(p.read_bytes())==expected,'saved bundle bytes:'+name)
freeze=load(SOURCE/'tooling-source-freeze.json')
for name,value in freeze.items():
 need(sha((SOURCE/'source-snapshot'/(name+'.txt')).read_bytes())==value,'frozen tooling snapshot:'+name)
 actual=(ROOT/'.work/unit-source-io-expanded-20261026'/name.removeprefix('HARNESS/')) if name.startswith('HARNESS/') else ROOT/name
 need(sha(actual.read_bytes())==value,'live worktree agrees with frozen tooling:'+name)
original_hashes=function_hashes((SOURCE/'source-snapshot/tests/units/run_io_cases.py.txt').read_text())
need(original_hashes==load(SOURCE/'original-functions.json'),'original function AST hashes')
runner=(SOURCE/'source-snapshot/HARNESS/run_expanded_io.py.txt').read_text()
need('module.validate_io(observed,case)' in runner and 'original=module.validate_evidence(data,result)' in runner,'original live assertions directly invoked')
prepared={x['unit_id']:x for x in load(SOURCE/'prepared.json')['cases']}
need(set(prepared)==set(CASES),'exact default-nine scope')
fixture_bytes=(SOURCE/'source-snapshot/platform/units/fixtures/esp32s3-adc-calibration.json.txt').read_bytes();fixture=json.loads(fixture_bytes)
binding=fixture['firmware_binding'];base_path=ROOT/binding['reference_file'];base=base_path.read_bytes();start=binding['application_offset'];length=binding['application_segment_bytes']
need(sha(base)==BASE==binding['reference_sha256'],'ADC actual reference full image hash')
need(sha(base[start:start+length])==binding['application_segment_sha256'],'ADC actual application segment hash')
# Independent integer arithmetic over the frozen official coefficient data.
def adc(mv):
 raw=min(4095,math.floor(mv*4095/3100+.5));reference=next(x['value'] for x in fixture['fields'] if x['name']=='ADC1_CAL_VOL_ATTEN3')+900
 voltage=raw*(65536*850//reference)//65536;error=0;power=1
 if voltage:
  for numerator,denominator,sign in fixture['idf_second_stage_coefficients']['adc1'][3]:
   error+=((power*numerator)&((1<<64)-1))//denominator*sign;power=(power*voltage)&((1<<64)-1)
 return {'raw_12bit':raw,'read_u16':(raw<<4)|(raw>>8),'read_uv':(voltage-error)*1000}

review=[];fan_samples=[]
for case in CASES:
 d=SOURCE/case;row=prepared[case];result=load(d/'result.json');request=load(d/'source-request.json');firmware=load(d/'firmware-response.json');events=load(d/'observation-index.json')
 sid=result['session_id'];http=[]
 for e in load(d/'http/index.json'):
  raw=(d/'http'/e['response_file']).read_bytes();need(sha(raw)==e['response_sha256'] and len(raw)==e['response_size'],case+' actual HTTP response hash')
  try:value=json.loads(raw)
  except (ValueError,UnicodeDecodeError):value=None
  http.append((e,value,raw))
 def backed(value,suffix,method=None,query=None):
  return any(v==value and e['path'].endswith(suffix) and (method is None or e['method']==method) and (query is None or parse_qs(e['query'])==query) for e,v,_ in http)
 need(result['status']=='PASS' and not result['known_original_guest_gap'] and not result['custom_driver_modification'],case+' eligible original default case')
 need(row['original_function_sha256']==original_hashes,case+' original assertion identity')
 cas=sha(canonical(request['files']));need(cas==row['source_cas_sha256']==firmware['source']['artifact_id'],case+' caller source CAS')
 origins=load(d/'guest-source-freeze.json')
 for name,text in request['files'].items():
  need((d/'files'/name).read_bytes()==text.encode() and sha(text.encode())==origins[name]['sha256']==row['probe_sha256'][name],case+' caller file bytes:'+name)
  if name!='probe_config.py':need((ROOT/'tests/units/io_probe'/name).read_bytes()==text.encode(),case+' exact unpatched probe:'+name)
 need(request['files']['probe_config.py']==f"CASE = {case!r}\nWHITE = 1\nYELLOW = 2\nIR_CALLBACK_ROOT_PATCH = False\n",case+' exact config')
 for name,record in load(d/'official-driver-proof.json').items():need(sha(request['files']['io_drivers/'+name].encode())==record['sha256'],case+' official driver:'+name)
 need((d/'license-evidence/LICENSE.MIT').read_bytes()==(ROOT/'tests/units/io_probe/io_drivers/LICENSE.MIT').read_bytes(),case+' exact MIT')
 meta=firmware['source']['metadata'];need(meta['base_sha256']==BASE and meta['source_sha256']==cas==meta['effective_source_sha256'] and meta['generated_files']==[] and meta['firmware_sha256']==firmware['sha256']==firmware['firmware_id'],case+' composed firmware/source identity')
 need(all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified')),case+' real source readback receipt')
 for entry in meta['files']:need(entry['origin']=='caller' and entry['sha256']==sha(request['files'][entry['path']].encode()) and entry['size']==len(request['files'][entry['path']].encode()),case+' source readback file hash')
 need(any(e['path']=='/api/v1/firmware/uiflow' and e['method']=='POST' and v==firmware and load(d/'http'/e['request_file'])==request for e,v,_ in http),case+' actual source compose POST')
 need(not any(e['method']=='POST' and e['path'] in ('/api/v1/artifacts','/api/v1/firmware') for e,_,_ in http),case+' no binary upload lane')
 session_request=load(d/'session-request.json');need(session_request['uiflow_source_sha256']==cas and session_request['units']==row['attachments'],case+' startup source pin/topology')
 need(any(e['path']=='/api/v1/sessions' and e['method']=='POST' and v.get('session_id')==sid and load(d/'http'/e['request_file'])==session_request for e,v,_ in http if isinstance(v,dict)),case+' actual session POST')
 serial=(d/'serial-final.txt').read_text();need(has(serial,'IO_PROBE_READY '+case) and not any(x in serial for x in ('IO_PROBE_FAIL','Traceback (most recent last)','Traceback (most recent call last)','Guru Meditation','Rebooting...')),case+' stable guest marker')
 accepted=[e for e in events if e['kind']=='input' and e['accepted']]
 fresh=[]
 for i,e in enumerate(accepted):
  prior=e['before_cursor']['data'];waits=[x for x in events if x['kind']=='wait-success' and x.get('input_event')==e['event_id']];need(waits,case+' input completed original wait')
  text=(d/waits[-1]['serial_file']).read_bytes().decode();need(text.startswith(prior) and len(text)>len(prior),case+' UART bytes newer than accepted input')
  if i+1<len(accepted):need(len(text)<=len(accepted[i+1]['before_cursor']['data']),case+' UART cannot borrow a later input window')
  fresh.append(text[len(prior):]);need(backed(e['before_cursor'],'/serial','GET'),case+' actual HTTP serial baseline')
 for e in events:
  if e['kind'] in ('wait-success','marker'):
   raw=(d/e['serial_file']).read_bytes();need(sha(raw)==e['serial_sha256'] and any(h['path'].endswith('/serial') and isinstance(v,dict) and v.get('data')==raw.decode() for h,v,_ in http),case+' actual saved guest serial')
  if e['kind']=='state':need(backed(load(d/e['file']),'/units'),case+' actual QOM-backed Unit HTTP')
 final=load(d/'final-units.json');need(backed(final,'/units'),case+' final Unit backing');need(final['source']=='live' and all(u['source']=='guest-qom' and u['available'] and not u['errors'] for u in final['units']),case+' live guest QOM availability')
 # Recompute the original semantics from UART and QOM values, not checks booleans.
 details={}
 if case=='pir':
  markers=['IO_PIR_CALLBACK 1 1','IO_PIR_CALLBACK 0 1','IO_PIR 1 1 1 1','IO_PIR_DISABLED_DONE 1 1','IO_PIR_CALLBACK 1 2','IO_PIR_CALLBACK 0 2']
  need(len(fresh)==6 and [e['values']['motion'] for e in accepted]==[True,False,True,False,True,False],case+' six edge inputs')
  for text,marker in zip(fresh,markers):need(has(text,marker),case+' bounded fresh '+marker)
  disabled=serial.split('IO_PIR_DISABLED 1 1',1)[1].split('IO_PIR_REENABLED',1)[0];need('IO_PIR_CALLBACK' not in disabled and has(serial,'IO_PIR_REENABLED'),case+' disabled IRQ negative and rearm')
  details={'fresh_markers':markers,'disabled_callback_count':0}
 elif case=='dual-button':
  need(len(fresh)==4,case+' four independent inputs')
  for text,raw in zip(fresh,((0,1),(1,1),(1,0),(1,1))):need(re.search(r'(?m)^IO_DUAL %d %d '%raw,text),case+' bounded raw button state')
  need(has(fresh[1],'IO_DUAL_CLICK 1 0') and has(fresh[3],'IO_DUAL_CLICK 1 1'),case+' separate click counters')
  details={'raw_vectors':[[0,1],[1,1],[1,0],[1,1]],'click_vectors':[[1,0],[1,1]]}
 elif case=='limit':
  need(has(serial,'IO_LIMIT_BUTTON_ALIAS 1') and len(fresh)==4,case+' alias and four edges')
  for text,(raw,count) in zip(fresh,((0,0),(1,1),(0,2),(1,3))):need(has(text,f'IO_LIMIT {raw} {count}'),case+' bounded edge/count')
  need(has(fresh[-1],'IO_LIMIT_COUNT_RESET 0'),case+' counter reset')
  details={'edge_vectors':[[0,0],[1,1],[0,2],[1,3]],'reset':0}
 elif case=='key':
  need(len(fresh)==2,case+' two key inputs')
  for text,event,(raw,color) in zip(fresh,accepted,((0,0x123456),(1,0x2468ac))):
   need(has(text,f'IO_KEY_RAW {raw}'),case+' fresh active low')
   need(any(props(load(d/e['file']))['led-rgb']==color for e in events if e['kind']=='state' and e.get('input_event')==event['event_id']),case+' matching guest RGB output')
  need(props(final)['led-frames']>=3 and props(final)['incomplete-frames']==0,case+' native RMT full frames')
  details={'colors':['123456','2468ac'],'led_frames':props(final)['led-frames']}
 elif case in ('angle','light'):
  mv=(0,1250,2500) if case=='angle' else (310,1550,3100);need(len(fresh)==3,case+' three ADC vectors');vectors=[]
  for i,(text,event,voltage) in enumerate(zip(fresh,accepted,mv)):
   expected=adc(voltage);need(event['values']['voltage-mv' if case=='angle' else 'analog-mv']==voltage,case+' actual voltage injection')
   if case=='angle':
    rows=[(int(a),float(b),int(c)) for a,b,c in re.findall(r'(?m)^IO_ANGLE (\d+) ([\d.]+) (\d+)\r?$',text)]
    need(any(a==expected['read_u16'] and c==expected['read_uv'] and abs(b-c/1e6)<=.000002 for a,b,c in rows),case+' exact independent read_u16/read_uv')
   else:need(has(text,f"IO_LIGHT {expected['read_u16']} {i%2}") and event['values']['digital-level'] is bool(i%2),case+' independent analog/digital vector')
   vectors.append({'injected_mv':voltage,**expected})
  need(props(final)['adc-samples']>=3,case+' SAR samples')
  details={'vector_scope':'Expected arithmetic; Angle read_u16/read_uv are both checked against fresh guest serial, Light checks guest read_u16/digital only','guest_read_uv_observed':case=='angle','vectors':vectors,'adc_samples':props(final)['adc-samples'],'fixture_sha256':sha(fixture_bytes),'bound_application_sha256':binding['application_segment_sha256']}
 elif case=='fan':
  stages=[]
  for stage,freq,setting in ((0,1000,0),(1,1000,25),(2,1500,100)):
   marker=f'IO_FAN {stage} {freq} {setting}';need(has(serial,marker),case+' original stage marker');duty=(round((setting-1)*953/99+70)/1023*100) if setting else 0
   states=[props(load(d/e['file'])) for e in events if e['kind']=='state' and e['phase']==marker]
   matching=[p for p in states if abs(p['frequency-hz']-freq)<=max(2,freq*.02) and abs(p['duty-pct']-duty)<=.5];need(matching,case+' LEDC controller output');stages.append({'stage':stage,'setting':setting,'frequency_hz':matching[0]['frequency-hz'],'duty_pct':matching[0]['duty-pct']})
  need(props(final)['output-transitions']>=3,case+' LEDC transitions');details={'stages':stages,'output_transitions':props(final)['output-transitions']}
 elif case=='rs485':
  initial=b'guest-to-peer\0\x7f\xff';incoming=b'peer-to-guest\0\x7f\xff';reply=b'echo:'+incoming
  need(len(fresh)==1 and accepted[0]['values']=={'rx-hex':incoming.hex()},case+' binary RX input')
  need(has(fresh[0],'IO_RS485_ANY 16') and has(fresh[0],'IO_RS485_RX '+incoming.hex()) and has(fresh[0],f'IO_RS485_ECHO {len(reply)} {reply.hex()}'),case+' fresh binary UART markers')
  bad=[(e,v) for e,v,_ in http if e['method']=='POST' and e['path'].endswith('/unit-input') and e['status'] in (400,409,422)];need(len(bad)==1 and 'FIFO' in json.dumps(bad[0][1]),case+' actual FIFO negative HTTP')
  before=props(load(d/'observations/00003-state.json'));after=props(load(d/'observations/00005-state.json'));need(before==after and before['read-bytes']==0,case+' rejected FIFO write leaves all Unit counters/state unchanged')
  p=props(final);need(p['tx-hex']==(initial+reply).hex() and p['read-bytes']==16 and p['written-bytes']==37 and p['input-events']==1,case+' exact UART data plane counters')
  details={'rx_bytes':16,'tx_bytes':37,'negative_http_status':bad[0][0]['status'],'negative_state_unchanged':True}
 else:
  need(has(serial,'IO_HUB_SCAN 68 88 90 112') and [e['id'] for e in accepted]==['env','ncir','tvoc'],case+' passive scan and three independent leaf inputs')
  expected=[[31.5,67,98765,25,32,800,40],[31.5,67,98765,17.3,37.1,800,40],[31.5,67,98765,17.3,37.1,1250,230]]
  for text,target in zip(fresh,expected):
   values=[[float(x) for x in line.split()] for line in re.findall(r'(?m)^IO_HUB ([^\r\n]+)',text)]
   need(any(len(v)==7 and all(abs(a-b)<=tol for a,b,tol in zip(v,target,(.2,.2,1.5,.021,.021,0,0))) for v in values),case+' independently changed leaf with other values retained')
  leaves={u:props(final,u) for u in ('env','ncir','tvoc')}
  need(all(all(p[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events')) for p in leaves.values()),case+' three independent I2C leaf counters')
  need(all(v==0 for v in props(final,'hub1').values()),case+' passive hub has no fabricated I2C transaction')
  details={'fresh_vectors':expected,'independent_leaf_counters':leaves,'passive_hub':props(final,'hub1')}
 # Evidence byte index, identities, native frame, source provenance and actual ordering.
 zbytes=(d/'evidence.zip').read_bytes();need(sha(zbytes)==result['evidence_sha256'],case+' ZIP SHA')
 with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
  need(z.testzip() is None and len(z.namelist())==len(set(z.namelist())),case+' ZIP CRC/no duplicates')
  manifest=load_manifest=json.loads(z.read('manifest.json'));need(set(manifest['files'])==set(z.namelist())-{'manifest.json'},case+' complete ZIP index')
  for name,entry in manifest['files'].items():raw=z.read(name);need(sha(raw)==entry['sha256'] and len(raw)==entry['size'],case+' ZIP member bytes:'+name)
  session=manifest['session'];need(session['state']=='running' and session['session_id']==sid and session['firmware_sha256']==firmware['sha256'] and session['firmware_provenance']==json.loads(z.read('firmware/uiflow-source.json'))==firmware['source'] and session['source_artifacts'][0]==cas,case+' same running ZIP source provenance')
  same_frame(z.read('frames/current.png'));zserial=z.read('serial.log').decode();need(has(zserial,'IO_PROBE_READY '+case),case+' ZIP serial guest marker')
  for marker in result['required_markers']:need(has(zserial,marker),case+' ZIP original marker')
  zs=json.loads(z.read('units/state.json'));need({u['id']:u['unit_id'] for u in zs['units']}=={a['id']:a['unit_id'] for a in row['attachments']},case+' ZIP exact attachments')
  q=json.loads(z.read('qom/snapshot.json'))
  if case=='key':
   r={k:v.get('value') for k,v in q['nodes']['rmt0']['children'].items() if k.startswith('tx-')};need(r['tx-symbols']>=72 and r['tx-completions']>=3 and r['tx-errors']==0,case+' native RMT controller counters');details['rmt_controller']=r
  if case=='rs485':need(z.read('serial1.log')==initial+reply,case+' real UART1 binary stream');details['uart1_stream_sha256']=sha(z.read('serial1.log'))
  if case in ('angle','light'):
   receipt=json.loads(z.read('units/adc-calibration.json'));need(receipt['status']=='applied' and receipt['fixture_sha256']==sha(fixture_bytes) and receipt['application_segment_sha256']==binding['application_segment_sha256'] and receipt['hardware_validation'] is False and receipt['identity_or_security_fields_changed'] is False,case+' applied app-bound synthetic ADC receipt')
  contract=json.loads(z.read('units/contract.json'));need(all(freeze['platform/units/'+name]==value for name,value in contract['source_hashes'].items()),case+' frozen Unit contract source hashes')
 # Recalculate actual browser DOM text against captured HTTP values.
 w=load(SOURCE/'browser'/sid/'web-report.json');need(not w['errors'] and w['session_id']==sid and w['firmware_sha256']==firmware['sha256'],case+' browser identity')
 for name,value in w['source_sha256'].items():need(sha((ROOT/name).read_bytes())==value,case+' browser instrumentation source:'+name)
 snapshots=[s for s in w['snapshots'] if s['session_state']=='running'];need(snapshots,case+' actual running browser snapshots')
 for snap in snapshots:
  need({u['instance'] for u in snap['units']}=={a['id'] for a in row['attachments']},case+' DOM all attachments')
  for u in snap['units']:
   p=u['readback']['properties'];need(any(any(x['id']==u['instance'] and x['properties']==p for x in e.get('response',{}).get('units',[])) for e in w['readbacks']+w['posts']),case+' DOM properties in actual captured HTTP')
   cells={x['field']:x for x in u['values']}
   for key,value in p.items():
    need(key in cells,case+' DOM field exists')
    if key=='led-rgb' and cells[key].get('rgb'):
     colors=value if isinstance(value,list) else [value];need(cells[key]['rgb']==[f'LED[{i}] #{v:06x}' for i,v in enumerate(colors)],case+' actual DOM RGB')
    elif isinstance(value,(int,float)) and not isinstance(value,bool):need(float(cells[key]['text'])==value,case+' actual DOM numeric text')
    else:need(cells[key]['text']==(str(value).lower() if isinstance(value,bool) else str(value)),case+' actual DOM scalar text')
 for event in accepted:
  for key,value in event['values'].items():
   # Same-state ADC baseline has a real action classification; changed values must POST.
   actions=[a for a in w['actions'] if a['instance']==event['id'] and a['field']==key and a.get('value',a.get('request',{}).get('values',{}).get(key))==value]
   need(actions,case+' actual product control action')
   if not any(a.get('kind') in ('already-equal-noop','baseline-no-change') or 'same-state' in a.get('kind','') for a in actions):
    need(any(p.get('request',{}).get('id')==event['id'] and p.get('request',{}).get('values',{}).get(key)==value and key in p.get('request',{}).get('values',{}) and p['status']==200 for p in w['posts']),case+' actual product HTTP POST per changed field')
 proof=load(SOURCE/'browser'/sid/'runtime-provenance.json');need(proof['kind']=='direct-pid' and proof['runtime_binary_sha256']==RUNTIME and proof['worker_generation']==11 and proof['executable_name']=='qemu-system-xtensa',case+' recorded direct PID runtime identity')
 for state_name in ('ready-session.json','running-session.json','before-evidence-session.json'):
  st=load(d/state_name);need(backed(st,'/'+sid,'GET') and st['pid']==proof['observed_pid'] and st['firmware_sha256']==proof['firmware_sha256'] and st['worker']['generation']==proof['worker_generation'] and st['worker']['worker_id']==proof['worker_id'],case+' PID/worker HTTP confirmation:'+state_name)
 need(session['pid']==proof['observed_pid'] and session['worker']['generation']==11 and session['worker']['lease_active'],case+' ZIP PID/lease')
 zip_events=[i for i,(e,_,raw) in enumerate(http) if e['path'].endswith('/evidence') and e['method']=='GET' and raw==zbytes]
 stop_events=[i for i,(e,_,_) in enumerate(http) if e['path'].endswith('/'+sid) and e['method']=='DELETE' and parse_qs(e['query'])=={'purge':['0']}]
 need(len(zip_events)==1 and len(stop_events)==1 and zip_events[0]<stop_events[0],case+' ZIP before actual purge=0 stop')
 history=load(d/'retained-session.json');health=load(d/'cleanup-health.json');stop=load(d/'stop-response.json')
 need(backed(history,'/'+sid,'GET') and backed(stop,'/'+sid,'DELETE',{'purge':['0']}) and history['state']=='stopped' and history['flash_retained'] is False and history['last_frame_available'] and not history['worker']['lease_active'],case+' retained history Flash release/lease inactive')
 need(backed(health,'/health','GET') and health['ok'] and health['capacity']['active_sessions']==0,case+' saved actual idle health')
 same_frame((d/'frame.png').read_bytes());same_frame((d/'history-frame.png').read_bytes())
 need(any(i>stop_events[0] and e['path'].endswith('/frame.png') and raw==(d/'history-frame.png').read_bytes() for i,(e,_,raw) in enumerate(http)),case+' history frame actually fetched after stop')
 if case=='fan':
  for snap in w['snapshots']:
   u=snap['units'][0];joint=next(x for x in u['components'] if x['path'].endswith('/rotor'))
   fan_samples.append({'at':snap['at'],'session_state':snap['session_state'],'duty_pct':u['readback']['properties']['duty-pct'],'frequency_hz':u['readback']['properties']['frequency-hz'],'angle_deg':joint['state']['angleDeg'],'component_rpm':joint['state']['rpm']})
 review.append({'unit_id':case,'status':'PASS','source_cas_sha256':cas,'firmware_sha256':firmware['sha256'],'evidence_sha256':sha(zbytes),'original_inputs':len(accepted),'http_records':len(http),'actual_browser_posts':len(w['posts']),'running_dom_snapshots':len(snapshots),'recorded_pid':proof['observed_pid'],'worker_generation':11,'semantic_recalculation':details,'qom_root_truncated':q['nodes'].get('__truncated__',False),'cleanup':'Saved HTTP: stopped/history retained/Flash false/lease inactive/health active=0; live PID-exit sampler receipt retained.'})

report={'schema_version':1,'reviewed_at':datetime.now(timezone.utc).isoformat(),'result':'NO_ACTIONABLE_FINDINGS','findings':[],
 'scope':'Independent offline review of terminal default-nine evidence; no API/process/runtime invocation or input modification.',
 'input_directory':str(SOURCE.relative_to(ROOT)),'original_bundle_checksum_entries':len(bundle_rows),'independent_check_count':len(checks),
 'runner_offline_check':'runner-check.json','original_function_hashes':original_hashes,'runtime_sha256':RUNTIME,'worker_generation':11,
 'adc_application_binding':{'reference_full_image_sha256':sha(base),'reference_application_segment_sha256':sha(base[start:start+length]),'fixture_sha256':sha(fixture_bytes),'derived_images_not_in_review_bundle':True},
 'cases':review,'fan_activity_samples':fan_samples,
 'fan_activity_scope':{'proved':'Five running snapshots at observed 100% duty have changing rotor angles over 2.532 seconds; visual activity during that sampled interval.',
 'not_proved':['continuous activity throughout every stage','stopped angle time series at zero duty','sustained low-duty angle progression','rpm or electromechanical speed','physical rotation'],
 'other_samples':'Zero duty has one booting sample; 29.39453125% duty has one running sample. All recorded component rpm fields are 0; adapter uses graphical angle activity.'},
 'limitations':['Historical direct PID executable hashing and PID exit rely on the recorded live sampler receipts plus frozen sampler implementation; ended processes cannot be re-sampled offline.',
 'ADC reference application bytes were rehashed; the uploaded/derived image bytes are not in this review bundle. Applied ZIP receipts and source-composition outside-VFS preservation bind the running cases to that application.',
 'Generic depth-two QOM snapshots have a truncated root. Per-Unit states were independently read from actual saved /units HTTP responses and exact observation snapshots, not treated as inferred complete controller dumps.',
 'Native PNG nonblank/geometry checks do not establish readable text or final visual acceptance. Hardware, optical, motor-speed and shared full-regression results are outside this review.',
 'Original IR/Buzzer risk controls were excluded and their running directories were not read by this audit script.']}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'result':report['result'],'cases':len(review),'independent_checks':len(checks),'bundle_entries':len(bundle_rows),'unexpected_network_process_calls':0},ensure_ascii=False))
