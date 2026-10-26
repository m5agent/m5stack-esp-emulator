"""Replay saved bytes only. Never imports Client or calls the Device Service."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,zipfile,subprocess,difflib,ast
ROOT=Path.cwd();RUN=ROOT/'.work/unit-source-io-expanded-20261026/live-original-risk-r1';OUT=ROOT/'.work/unit-expanded-cross-review-20261026/original-risk'
RUNTIME='29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
def need(x,message):
 if not x:raise RuntimeError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(p):return json.loads(p.read_bytes())
def save(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def exact(text,marker):return re.search(r'(?m)^'+re.escape(marker)+r'\r?$',text) is not None
def http(directory):
 events=load(directory/'http/index.json');values=[]
 for i,event in enumerate(events):
  raw=(directory/'http'/event['response_file']).read_bytes();need(len(raw)==event['response_size'] and sha(raw)==event['response_sha256'],'raw HTTP bytes changed')
  try:value=json.loads(raw)
  except (ValueError,UnicodeDecodeError):value=None
  values.append((i,event,value,raw))
 return values
def props(value):
 if not isinstance(value,dict) or value.get('source')!='live':return None
 units=value.get('units',[])
 if len(units)!=1:return None
 u=units[0]
 return u['properties'] if u.get('id')=='external1' and u.get('source')=='guest-qom' and u.get('available') and not u.get('errors') else None

def common_case(case):
 directory=RUN/case;request=load(directory/'source-request.json');r=load(directory/'result.json');row=load(directory/'prepared.json');values=http(directory);sid=r['session_id'];prefix='/api/v1/sessions/'+sid
 need(r['status']=='REVIEW_REQUIRED' and r['protocol_status']=='PASS' and row['known_original_guest_gap'] and row['custom_driver_modification'] is False and r['firmware_flavor']=='reference-app-with-original-unit-drivers','original IR status/flavor/risk boundary differs')
 source_sha=sha(canonical(request['files']));need(source_sha==r['source_cas_sha256']==row['source_cas_sha256'],'canonical source CAS differs')
 for name,text in request['files'].items():need((directory/'files'/name).read_bytes()==text.encode() and sha(text.encode())==r['probe_sha256'][name],'actual source bytes differ')
 firmware=load(directory/'firmware-response.json');meta=firmware['source']['metadata']
 need(source_sha==firmware['source']['artifact_id']==meta['source_sha256']==meta['effective_source_sha256'],'source API source identities differ')
 need(firmware['sha256']==firmware['firmware_id']==r['firmware_sha256']==meta['firmware_sha256'],'firmware identity differs')
 filemeta={f['path']:f for f in meta['files']};need(set(filemeta)==set(request['files']),'source API file set differs')
 for name,text in request['files'].items():need(filemeta[name]['sha256']==sha(text.encode()) and filemeta[name]['size']==len(text.encode()) and filemeta[name]['origin']=='caller','source API file readback identity differs')
 need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and e['status']==201 and v==firmware and load(directory/'http'/e['request_file'])==request for _,e,v,_ in values),'source POST lacks raw HTTP backing')
 session_request=load(directory/'session-request.json');need(session_request['uiflow_source_sha256']==source_sha and session_request['firmware_id']==firmware['firmware_id'],'startup source pin differs')
 need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and e['status']==202 and v.get('session_id')==sid and load(directory/'http'/e['request_file'])==session_request for _,e,v,_ in values if isinstance(v,dict)),'session source-pin POST lacks raw backing')
 proof=load(RUN/'browser'/sid/'runtime-provenance.json');need(proof==r['runtime_provenance'] and proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==RUNTIME and proof['worker_generation']==11,'recorded direct executable/generation proof differs')
 for name in ('ready-session.json','running-session.json'):
  record=load(directory/name);need(any(v==record and e['path']==prefix for _,e,v,_ in values),'session identity lacks raw HTTP backing');need(record['pid']==proof['observed_pid'] and record['firmware_provenance']==firmware['source'] and record['source_artifacts'][0]==source_sha,'same session source/PID differs')
 evidence=(directory/'evidence.zip').read_bytes();need(sha(evidence)==r['evidence_sha256'],'ZIP hash differs')
 with zipfile.ZipFile(directory/'evidence.zip') as z:
  need(z.testzip() is None and len(set(z.namelist()))==len(z.namelist()),'invalid ZIP')
  m=json.loads(z.read('manifest.json'));need(set(m['files'])==set(z.namelist())-{'manifest.json'},'ZIP index differs')
  for n,p in m['files'].items():need(sha(z.read(n))==p['sha256'] and len(z.read(n))==p['size'],'ZIP member differs')
  s=m['session'];need(s['state']=='running' and s['session_id']==sid and s['firmware_sha256']==r['firmware_sha256'] and s['pid']==proof['observed_pid'] and s['worker']['generation']==11 and s['worker']['lease_active'],'ZIP is not same live lease')
  need(s['firmware_provenance']==firmware['source']==json.loads(z.read('firmware/uiflow-source.json')) and s['source_artifacts'][0]==source_sha,'ZIP source provenance differs')
  serial=z.read('serial.log');need(serial.startswith((directory/'serial-final.txt').read_bytes()),'ZIP loses observed final serial prefix')
  for _,e,v,_ in values:
   if e['path']==prefix+'/serial' and e['status']==200:
    need(v['bytes']==len(v['data'].encode()) and v['next_offset']==v['offset']+v['bytes'] and serial[v['offset']:v['next_offset']]==v['data'].encode(),'raw HTTP serial does not match ZIP bytes')
 raw_zips=[i for i,e,v,b in values if e['path']==prefix+'/evidence' and e['status']==200 and b==evidence];stops=[i for i,e,v,b in values if e['path']==prefix and e['method']=='DELETE' and e['query']=='purge=0' and e['status']==200]
 need(raw_zips and stops and max(raw_zips)<min(stops),'ZIP ordering differs from stop')
 history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(any(e['path']==prefix and v==history for _,e,v,_ in values) and any(e['path']=='/api/v1/health' and v==health for _,e,v,_ in values),'history/health lack raw HTTP backing')
 need(history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] and history['firmware_provenance']==firmware['source'],'history/Flash/frame/source differs')
 need(health['ok'] and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0 and r['cleanup']['pid']==proof['observed_pid'] and r['cleanup']['pid_gone'],'recorded cleanup incomplete')
 web=load(RUN/'browser'/sid/'web-report.json');need(web['session_id']==sid and web['firmware_sha256']==r['firmware_sha256'] and not web['errors'],'browser identity/errors differ')
 snapshots=[s for s in web['snapshots'] if s.get('session_state')=='running'];need(snapshots,'no actual running DOM observations')
 for s in snapshots:
  need(len(s['units'])==1,'browser attachment tree differs')
  for u in s['units']:
   need(u['dom_matches_product_readback'] and u['readback_matches_real_http_response'],'DOM is not same HTTP readback')
   p=u['readback']['properties'];need(any(any(x['id']==u['instance'] and x['properties']==p for x in v.get('response',{}).get('units',[])) for v in web['posts']+web['readbacks']),'DOM readback lacks captured browser HTTP')
   cells={c['field']:c for c in u['values']}
   for k,v in p.items():
    need(k in cells,'DOM field absent');expected=json.dumps(v,separators=(',',':')) if isinstance(v,(list,dict)) else str(v).lower() if isinstance(v,bool) else str(v)
    need(cells[k]['text']==expected or isinstance(v,(int,float)) and float(cells[k]['text'])==v,'DOM value differs')
 # Prove original byte identity for every caller file against immutable source snapshots of the same probe.
 baseline=ROOT/'.work/unit-source-custom-io-20261026/live-custom2-r1/source-snapshot/tests/units/io_probe'
 original=(baseline/'io_drivers/ir.py.txt').read_bytes()
 need(request['files']['io_drivers/ir.py'].encode()==original,'original risk control contains a patched IR driver')
 need(sha(original)=='b342ff962ffe119e0f1e4d072182a6ea1b251d9dd52dcea8980e386b04ce3896','original IR source no longer matches the pinned official driver')
 unchanged=[]
 for name,text in request['files'].items():
  if name=='probe_config.py':continue
  need((baseline/(name+'.txt')).read_bytes()==text.encode(),'original risk source was changed: '+name);unchanged.append(name)
 need(request['files']['probe_config.py']=="CASE = 'ir'\nWHITE = 1\nYELLOW = 2\nIR_CALLBACK_ROOT_PATCH = False\n",'original IR custom flag/config changed')
 custom=load(ROOT/'.work/unit-source-custom-io-20261026/live-custom2-r1/ir/source-request.json')['files']
 need(set(custom)==set(request['files']),'original and custom caller memberships differ')
 changed=[n for n in custom if custom[n]!=request['files'][n]];need(set(changed)=={'io_drivers/ir.py','probe_config.py'},'original/custom source differences exceed driver patch + explicit flag')
 differences={n:{'original_sha256':sha(request['files'][n].encode()),'custom_sha256':sha(custom[n].encode()),'diff':''.join(difflib.unified_diff(request['files'][n].splitlines(True),custom[n].splitlines(True),fromfile='original/'+n,tofile='custom/'+n))} for n in changed}
 save(OUT/'source-comparison.json',{'category':'source byte comparison, no new runtime execution','caller_file_count':len(custom),'original_byte_exact_files':len(unchanged),'unchanged_between_original_and_custom':len(custom)-len(changed),'changed':differences})
 return {'directory':directory,'request':request,'result':r,'row':row,'values':values,'web':web,'summary':{'session_id':sid,'firmware_sha256':r['firmware_sha256'],'source_cas_sha256':source_sha,'driver_validation':'original-driver-observed-protocol-only-risk-open','original_driver_sha256':sha(original),'original_caller_files_byte_exact':len(unchanged),'original_vs_custom_only_driver_patch_and_flag_differ':True,'raw_http_responses':len(values),'zip_http_index':raw_zips[-1],'stop_http_index':stops[0],'runtime_binary_sha256':RUNTIME,'worker_generation':11,'owned_pid':proof['observed_pid'],'recorded_pid_exit':True,'flash_retained':False,'cleanup_active_sessions':0,'browser_running_snapshots':len(snapshots),'browser_posts':len(web['posts'])}}

def buzzer_audit(data):
 values=data['values'];sid=data['result']['session_id'];prefix='/api/v1/sessions/'+sid;matches=[]
 for position,(i,e,v,_) in enumerate(values):
  p=props(v)
  if e['path']!=prefix+'/units' or not p or abs(p.get('frequency-hz',0)-2000)>40 or p.get('duty-pct')!=0:continue
  previous=[x for x in values[:position] if x[1]['path']==prefix+'/serial' and x[1]['status']==200];following=[x for x in values[position+1:] if x[1]['path']==prefix+'/serial' and x[1]['status']==200]
  if not previous or not following:continue
  bi,be,b,_=previous[-1];ai,ae,a,_=following[0];before=b['data'];after=a['data'];anchors=list(re.finditer(r'(?m)^IO_BUZZER_ONCE 2000 50\r?$',before))
  if not anchors:continue
  offset=anchors[-1].end()
  if not after.startswith(before) or re.search(r'(?m)^IO_BUZZER(?: |_)',before[offset:]) or re.search(r'(?m)^IO_BUZZER(?: |_)',after[offset:]):continue
  active=[(j,q) for j,ee,payload,_ in values[:position] if ee['path']==prefix+'/units' and (q:=props(payload)) and abs(q.get('frequency-hz',0)-2000)<=40 and abs(q.get('duty-pct',0)-50)<=.5 and q.get('output-transitions',0)<p.get('output-transitions',0)]
  if not active:continue
  matches.append({'before_http_index':bi,'qom_http_index':i,'after_http_index':ai,'before_at':be['at'],'qom_at':e['at'],'after_at':ae['at'],'serial_offset_derived_from_anchor':offset,'before_serial_sha256':sha(before.encode()),'after_serial_sha256':sha(after.encode()),'actual_zero_qom':p,'earlier_active_qom_http_index':active[-1][0],'earlier_active_qom':active[-1][1]})
 need(matches,'no independent natural once-zero serial/QOM/serial bracket before later guest writes')
 chosen=matches[0];final=(data['directory']/'serial-final.txt').read_bytes().decode();need(exact(final,'IO_BUZZER_TIMER_DONE') and exact(final,'IO_BUZZER_OFF'),'timer/manual markers absent')
 later=[i for i,e,v,_ in values if e['path']==prefix+'/serial' and e['status']==200 and exact(v['data'],'IO_BUZZER_TIMER_DONE')]
 need(later and min(later)>chosen['after_http_index'],'TIMER_DONE appeared before natural zero proof')
 need(not data['web']['posts'] and not any(e['path']==prefix+'/unit-input' and e['method']=='POST' for _,e,v,_ in values),'Buzzer was host input driven')
 obs=data['result']['buzzer_timer_zero_observation'];need(chosen['actual_zero_qom']==obs['qom'] and chosen['before_serial_sha256']==obs['before_serial_sha256']==obs['after_serial_sha256'],'independently derived zero proof differs from runner record')
 chosen.update({'status':'PASS','first_timer_done_http_index':min(later),'host_input_posts':0,'source_once_duration_ms':2000,'source_timer_done_wait_ms':3000,'manual_final_zero_is_separate':True})
 return chosen

def pulses(address,command,raw16=False):
 seq=[9000,4500];payload=(address&255,address>>8,command&255,command>>8) if raw16 else (address,address^255,command,command^255)
 for byte in payload:
  for bit in range(8):seq.extend([562,1687 if byte&(1<<bit) else 562])
 return seq+[562]
def pulse_match(actual,expected):return len(actual) in (len(expected),len(expected)+1) and all(abs(a-b)<=max(30,b*.06) for a,b in zip(actual,expected))
def ir_audit(data):
 directory=data['directory'];serial=(directory/'serial-final.txt').read_bytes().decode();events=load(directory/'observation-index.json');inputs=[e for e in events if e['kind']=='input' and e['accepted']]
 bad=pulses(0x12,0x34);bad[0]=200;expected=[pulses(0x12,0x34),bad,[9000,2250,562],pulses(0x56,0x78)]
 need(len(inputs)==4 and all(e['via_ui'] and e['id']=='external1' and e['values']=={'rx-pulses-us':v} for e,v in zip(inputs,expected)),'actual IR injected waveforms differ')
 positions=[]
 for marker in ('IO_IR_GC_COLLECTED 1 0','IO_IR_NATIVE 1','IO_IR_TX 18 52','IO_PROBE_READY ir'):
  match=re.search(r'(?m)^'+re.escape(marker)+r'\r?$',serial);need(match,'IR initialization/forced GC marker absent');positions.append(match.start())
 need(positions==sorted(positions) and positions[-1]<len(inputs[0]['before_cursor']['data']),'forced GC/setup not before actual RX input')
 windows=[]
 for n,event in enumerate(inputs):
  prior=event['before_cursor']['data'];start=len(prior);end=len(inputs[n+1]['before_cursor']['data']) if n+1<len(inputs) else len(serial)
  need(serial.startswith(prior) and 0<=start<end<=len(serial),'IR fresh bounded cursor interval invalid');text=serial[start:end];windows.append(text)
 need(exact(windows[0],'IO_IR_RX 52 18 0 1') and exact(windows[0],'IO_IR_NATIVE_PACKED 60690 52020'),'first callback/native packed TX absent from its bounded input phase')
 need(len(re.findall(r'(?m)^IO_IR_HEARTBEAT 1\r?$',windows[1]))>=2 and not re.search(r'(?m)^IO_IR_RX ',windows[1]),'bad leader produced callback or lacked two fresh guest heartbeats')
 need(exact(windows[2],'IO_IR_RX 52 18 -1 2') and exact(windows[3],'IO_IR_RX 120 86 0 3'),'repeat/rearmed callbacks absent from separate bounded phases')
 states=[]
 for e in events:
  if e['kind']!='state':continue
  state=load(directory/e['file']);p=props(state);need(p is not None,'IR state not live guest QOM')
  need(any(record['path'].endswith('/units') and payload==state for _,record,payload,_ in data['values']),'IR controller state lacks real HTTP backing');states.append((e,p))
 raw=[(e,p) for e,p in states if e['event_id']<inputs[0]['event_id'] and pulse_match(p['tx-pulses-us'],pulses(0x12,0x34,True))]
 packed=[(e,p) for e,p in states if e.get('input_event')==inputs[0]['event_id'] and pulse_match(p['tx-pulses-us'],pulses(0x12,0x34))]
 need(raw and packed,'separate raw16/native-packed RMT transmit state missing')
 consumed=[(e,p) for e,p in states if e.get('input_event')==inputs[1]['event_id'] and p['rx-pulses-us']==[]];need(consumed,'bad leader not consumed by controller')
 posts=[p for p in data['web']['posts'] if p['status']==200];need([p['request'] for p in posts]==[{'id':'external1','values':{'rx-pulses-us':v}} for v in expected],'four IR injections lack exact real browser POST order')
 final=props(load(directory/'final-units.json'));need(final['input-events']==4 and final['output-transitions']>=2,'IR RMT input/transmit counters absent')
 return {'status':'PASS','forced_normal_gc_before_first_rx':True,'bounded_input_serial_windows':[{'input_event':e['event_id'],'cursor_bytes':len(e['before_cursor']['data'].encode()),'suffix_bytes':len(text.encode()),'sha256':sha(text.encode())} for e,text in zip(inputs,windows)],'real_browser_input_posts':len(posts),'raw16_state_event':raw[0][0]['event_id'],'native_packed_state_event':packed[0][0]['event_id'],'bad_leader_consumed_state_event':consumed[0][0]['event_id'],'malformed_window_rx_callbacks':0,'malformed_window_heartbeat1_count':len(re.findall(r'(?m)^IO_IR_HEARTBEAT 1\r?$',windows[1])),'repeat_preserves_address_command':True,'receiver_rearmed':True,'final_rmt_counters':{'input-events':final['input-events'],'output-transitions':final['output-transitions']}}

for line in (RUN/'SHA256SUMS').read_text().splitlines():
 digest,name=line.split('  ',1);need(sha((RUN/name).read_bytes())==digest,'frozen custom artifact hash mismatch: '+name)
freeze=load(RUN/'tooling-source-freeze.json');need(sha((RUN/'source-snapshot/HARNESS/run_expanded_io.py.txt').read_bytes())==freeze['HARNESS/run_expanded_io.py'],'executed runner freeze hash mismatch')
reviews=[]
for case in ('ir',):
 data=common_case(case);specific=ir_audit(data) if case=='ir' else buzzer_audit(data);reviews.append({**data['summary'],'protocol':specific})
report={'schema_version':1,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'status':'OBSERVED_PROTOCOL_PASS_RISK_OPEN','findings':[],'scope':'Independent offline replay of exact original IR source/HTTP/guest/RMT/browser/ZIP/cleanup bytes; historical GC lifetime risk remains OPEN','run':str(RUN.relative_to(ROOT)),'executed_harness_sha256':freeze['HARNESS/run_expanded_io.py'],'cases':reviews,'original_driver_pass_claimed':False,'hardware_validation':'NOT RUN','device_service_contacted_by_reviewer':False,'limits':['This exact original IR firmware/session observed the required protocol behavior once; it is not a stable original-driver or family-wide PASS. Historical original GC failures remain unchanged and OPEN.','The recorded direct PID/executable proof was captured during root live execution; exited processes cannot be rehashed by this offline review.','The official original wrapper/native callback remains unrooted in the inspected source pattern. One normal gc.collect run can retain objects conservatively and does not prove lifetime safety across allocation pressure, repeated GC, timing or firmware variants.', 'Web/frame and controller evidence is virtual-device evidence; physical optical/acoustic/electrical or RF behavior is outside scope.']}
save(OUT/'review.json',report);print(json.dumps(report,ensure_ascii=False,indent=2))
