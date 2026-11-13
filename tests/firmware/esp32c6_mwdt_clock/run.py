from pathlib import Path
import sys,json,time,urllib.request,hashlib,subprocess,zipfile,io,struct
import argparse
parser=argparse.ArgumentParser(description="Run the C6 MWDT source-clock probe in an owned local Device Service session.")
parser.add_argument('--base-url',required=True)
parser.add_argument('--mode',choices=['before','after'],required=True)
parser.add_argument('--firmware',required=True,type=Path)
parser.add_argument('--firmware-sha256',required=True)
parser.add_argument('--runtime-sha256',required=True)
parser.add_argument('--out',required=True,type=Path)
def validate_serial(serial, mode, off=False):
 assert ('OFF_PROBE_READY' if off else 'MWDT_PROBE_READY') in serial
 assert serial.count('ESP-ROM:esp32c6') == 1
 assert not any(x in serial for x in ('assert failed:', 'Guru Meditation Error', 'abort() was called', 'Task watchdog got triggered'))
 if off:
  assert 'OFF_PROBE_DONE' in serial
  assert 'result=FAIL' not in serial
  assert 'OFF_LIVE hold=1 ' in serial and 'OFF_LIVE hold=0 ' in serial
  assert 'OFF_TO_INT ' in serial and serial.count('result=PASS')==3
  return
 lines=[x for x in serial.splitlines() if x.startswith('MWDT_CASE ')]
 assert len(lines)==6,lines
 expect=1 if mode=='before' else 6
 assert sum('result=PASS' in x for x in lines)==expect,lines
 assert f'MWDT_PROBE_DONE passed={expect} total=6' in serial

parser.add_argument('--off-stages',action='store_true')
args=parser.parse_args()
assert not args.off_stages or args.mode=='after', 'OFF guest probe is a positive control; use host replay for the historical negative'
OFF=args.off_stages
BASE=args.base_url.rstrip('/')+'/api/v1/'
MODE=args.mode
OUT=args.out.resolve();OUT.mkdir(exist_ok=False,parents=True)
RUNTIME=args.runtime_sha256
sha=lambda data:hashlib.sha256(data).hexdigest()
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2)+'\n')
def api(method,path,body=None,timeout=20):
 binary=isinstance(body,bytes);headers={'Content-Type':'application/octet-stream' if binary else 'application/json'}
 if binary:headers['X-Artifact-Name']='mwdt-clock-probe.bin'
 request=urllib.request.Request(BASE+path,method=method,data=body if binary else json.dumps(body).encode() if body is not None else None,headers=headers)
 with urllib.request.urlopen(request,timeout=timeout) as response:
  raw=response.read();return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
image=args.firmware.read_bytes();assert sha(image)==args.firmware_sha256
receipt={'firmware_sha256':sha(image),'note':'Attach the fixed SDK/source/build identity receipt separately.'}
artifact=api('POST','artifacts',image);firmware=api('POST','firmware/import',{'device_id':'nesso-n1','artifact_id':artifact['artifact_id']});save('firmware.json',firmware)
payload={'device_id':'nesso-n1','firmware_id':firmware['firmware_id'],'runtime':'qemu','ttl_seconds':600,'idempotency_key':'c6-mwdt-clock-'+MODE+'-'+str(time.time_ns())};save('request.json',payload)
sid=None;primary=None;cleanup=None;bundle=None;events=[];frames=[];start=None;guest_pid=None
try:
 created=api('POST','sessions',payload);sid=created['session_id'];save('created.json',created)
 limit=time.monotonic()+30
 while time.monotonic()<limit:
  s=api('GET','sessions/'+sid)
  if s.get('pid') and s['state']=='running':break
  if s['state'] in ['failed','stopped']:raise RuntimeError('Guest startup failed')
  time.sleep(.1)
 else:raise TimeoutError('Guest not running')
 guest_pid=s['pid']
 exe=Path(subprocess.check_output(['ps','-p',str(s['pid']),'-o','comm='],text=True).strip());actual=sha(exe.read_bytes());assert actual==RUNTIME
 save('runtime-identity.json',{'binary':str(exe),'binary_sha256':actual,'argv':subprocess.check_output(['ps','-p',str(s['pid']),'-o','command='],text=True)})
 start=time.monotonic();sent=set();got_ready=False
 while time.monotonic()-start<30:
  elapsed=time.monotonic()-start
  serial=api('GET','sessions/'+sid+'/serial?offset=0&limit=262144')['data'];(OUT/'serial-live.log').write_text(serial)
  if ('OFF_PROBE_READY' if OFF else 'MWDT_PROBE_READY') in serial:got_ready=True
  if ('OFF_PROBE_DONE' if OFF else 'MWDT_PROBE_DONE') in serial:break
  if any(x in serial for x in ('assert failed:', 'Guru Meditation Error', 'abort() was called')):raise AssertionError('Probe crashed')
  time.sleep(.25)
 validate_serial(serial,MODE,OFF)
except BaseException as error:primary=error
finally:
 if sid is None:
  try:created=api('POST','sessions',payload);sid=created['session_id'];save('create-recovery.json',created)
  except Exception as error:cleanup=error
 if sid:
  try:bundle=api('GET','sessions/'+sid+'/evidence?include=manifest,serial,frames,logs,qom,flash',timeout=30);(OUT/'evidence.zip').write_bytes(bundle)
  except Exception as error:cleanup=error
  finally:
   try:
    try:api('DELETE','sessions/'+sid+'?purge=0',timeout=10)
    except Exception:pass
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
     s=api('GET','sessions/'+sid,timeout=5)
     if s['state']=='stopped' and s.get('flash_retained') is False and s.get('worker',{}).get('lease_active') is False:break
     time.sleep(.2)
    else:raise TimeoutError('Owned guest stop/lease/Flash release failed')
    save('stopped.json',s)
    if guest_pid is not None:
     assert subprocess.run(['ps','-p',str(guest_pid),'-o','comm='],capture_output=True).returncode!=0,'Owned guest PID still exists'
   except Exception as error:cleanup=error
 result={'mode':MODE,'status':'FAIL' if primary or cleanup else 'EXPECTED_FAIL' if MODE=='before' else 'PASS','validation':'virtual-device validation','firmware_sha256':sha(image),'runtime_sha256':RUNTIME,'source_build':receipt,'observed_seconds':time.monotonic()-start if start else None,'inputs':events,'frames':frames,'error':str(primary) if primary else None,'cleanup_error':str(cleanup) if cleanup else None}
 if bundle:
  z=zipfile.ZipFile(io.BytesIO(bundle));raw=z.read('serial.log');(OUT/'serial.log').write_bytes(raw);flash=z.read('flash/virtual-flash.bin');parts=[]
  try:validate_serial(raw.decode('utf-8',errors='replace'),MODE,OFF)
  except AssertionError as error:
   if primary is None:primary=error
   result.update(status='FAIL',error=str(primary))
  for pos in range(0x8000,0x9000,32):
   magic,kind,sub,offset,size,label,flags=struct.unpack_from('<HBBII16sI',image,pos)
   if magic!=0x50aa:break
   if kind==0:
    before=image[offset:offset+size];before+=b'\xff'*(size-len(before));after=flash[offset:offset+size];parts.append({'offset':offset,'size':size,'before_sha256':sha(before),'after_sha256':sha(after),'unchanged':before==after})
  assert parts and all(p['unchanged'] for p in parts)
  result.update(zip_before_stop=True,zip_sha256=sha(bundle),app_partitions=parts,serial_sha256=sha(raw),boot_banners=raw.count(b'ESP-ROM:esp32c6'),ownership_asserts=raw.count(b'assert failed: xTaskPriorityDisinherit'),release_markers=raw.count(b'OWNER_RELEASE_OK'),terminal_state=s['state'],flash_released=s.get('flash_retained') is False,lease_released=s.get('worker',{}).get('lease_active') is False)
 save('summary.json',result)
 print(json.dumps({k:result.get(k) for k in ['mode','status','observed_seconds','boot_banners','ownership_asserts','release_markers','error','cleanup_error']}),flush=True)
if primary:raise primary
if cleanup:raise cleanup
