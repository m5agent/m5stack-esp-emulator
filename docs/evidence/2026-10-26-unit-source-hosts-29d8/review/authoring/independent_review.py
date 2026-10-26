from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import ast,hashlib,importlib.util,io,json,os,re,socket,subprocess,sys,urllib.request
ROOT=Path.cwd();AUTHOR=ROOT/'.work/unit-source-hosts-expanded-20261026';OUT=Path(__file__).resolve().parent
sha=lambda b:hashlib.sha256(b).hexdigest()
checks=[];calls=[]
def check(name,value):
 if not value:raise AssertionError(name)
 checks.append(name)
def deny(label):
 def rejected(*a,**k):calls.append(label);raise AssertionError('offline forbidden: '+label)
 return rejected
freeze=json.loads((AUTHOR/'delivery-freeze.json').read_bytes());pins={}
for name,row in freeze['files'].items():
 raw=(AUTHOR/name).read_bytes();check('author freeze '+name,sha(raw)==row['sha256'] and len(raw)==row['size']);pins[name]=sha(raw)
# Copy source into independent sandbox; never mutate the frozen author files.
for name in ['run_source_hosts.py','source_api_common.py']:(OUT/name).write_bytes((AUTHOR/name).read_bytes())
sys.path.insert(0,str(OUT));spec=importlib.util.spec_from_file_location('independent_host_source',OUT/'run_source_hosts.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
check('copied harness ROOT remains repository',h.ROOT==ROOT and h.HERE==OUT)
with patch.object(socket,'socket',deny('socket')),patch.object(urllib.request,'urlopen',deny('HTTP')),patch.object(subprocess,'Popen',deny('Popen')),patch.object(subprocess,'run',deny('subprocess.run')),patch.object(subprocess,'check_output',deny('check_output')):
 module=h.original_module()
 import run_service_cases,run_control_cases,run_profile_ui_test
 with patch.object(module,'prepare',deny('legacy prepare')),patch.object(module,'build_control_image',deny('host BIN builder')),patch.object(run_control_cases,'build_control_image',deny('control BIN builder')),patch.object(run_profile_ui_test,'build_image',deny('image BIN builder')),patch.object(module,'Client',deny('host Client')),patch.object(run_service_cases,'Client',deny('service Client')):
  rows=h.prepare(OUT/'preparation-r1',list(h.DEVICES),list(h.CASES))
  check('exact nine combinations',len(rows)==9 and {(r['device_id'],r['unit_id']) for r in rows}=={(d,c) for d in h.DEVICES for c in h.CASES})
  bases={}
  for row in rows:
   label=row['device_id']+'/'+row['unit_id'];directory=OUT/'preparation-r1'/row['device_id']/row['unit_id'];req=h.load(directory/'source-request.json')
   check(label+' reference-specific base',req['expected_base_sha256']==sha((ROOT/row['reference_file']).read_bytes())==row['base_firmware_sha256']);bases[row['device_id']]=row['base_firmware_sha256']
   check(label+' CAS source pin',row['source_cas_sha256']==h.sha(h.canonical(req['files'])))
   check(label+' five files only',set(req['files'])=={'main.py','host_program.py','probe_logging.py','boot.py','probe_config.py'})
   for name,text in req['files'].items():
    ast.parse(text);check(label+' request/local '+name,(directory/'files'/name).read_bytes()==text.encode())
    if name!='probe_config.py':check(label+' byte-exact original '+name,text.encode()==(ROOT/'tests/units/host_probe'/name).read_bytes())
   config={}
   for node in ast.parse(req['files']['probe_config.py']).body:config[node.targets[0].id]=ast.literal_eval(node.value)
   profile=row['host_profile'];check(label+' exact actual display/internal/external wiring',config['INTERNAL_CONTROLLER']==1 and config['EXTERNAL_CONTROLLER']==0 and config['INTERNAL_SDA']==profile['internal_sda'] and config['INTERNAL_SCL']==profile['internal_scl'] and config['FRAME_WIDTH']==profile['size'][0] and config['CANVAS_WIDTH']==profile['canvas_size'][0])
   check(label+' no extra driver/ADC',row['uploaded_driver_files']==[] and row['adc_fixture']=='NOT USED')
  check('three distinct references',len(set(bases.values()))==3)
  watch=next(r for r in rows if r['device_id']=='stopwatch');check('StopWatch native/canvas split retained',watch['expected_size']==[466,466] and watch['host_profile']['canvas_size']==[468,468])
  functions=h.original_functions();check('all original host oracles pinned',len(functions)==5 and all(r['original_function_sha256']==functions for r in rows))
  # Test live wait wrapper independently with synthetic text, never a fake runtime PASS.
  class FakeBase:
   def __init__(self,candidate):self.candidate=candidate;self.serial=''
   def wait(self,predicate,*,offset=0,timeout=60):
    self.serial=self.candidate
    if not predicate(self.serial[offset:]):raise RuntimeError('synthetic predicate rejected')
    return self.serial
  trace=OUT/'synthetic-live-wait';trace.mkdir();cls=h.recorded_type(SimpleNamespace(Observations=FakeBase),trace)
  def observed(candidate):
   value=cls(candidate);value.trace=[{'before_cursor':{'data':'PASS old\r\n'}}];value.last_input=0;return value
  try:observed('PASS old\r\nheartbeat\r\n').wait(lambda t:'PASS' in t)
  except RuntimeError:check('live wrapper rejects old match plus new unrelated UART',True)
  else:raise AssertionError('stale live predicate accepted')
  check('live wrapper accepts genuinely new predicate',observed('PASS old\r\nPASS fresh\r\n').wait(lambda t:'PASS' in t).endswith('PASS fresh\r\n'))
  # Independent lower and next-input upper bound counterexamples.
  windows=OUT/'synthetic-bounded-window';windows.mkdir();(windows/'first.txt').write_text('prior\nfirst\n');(windows/'second.txt').write_text('prior\nfirst\nsecond\n')
  events=[{'kind':'input','event_id':0,'accepted':True,'before_cursor':{'data':'prior\n'}},{'kind':'wait-success','input_event':0,'serial_file':'first.txt'},{'kind':'input','event_id':2,'accepted':True,'before_cursor':{'data':'prior\nfirst\n'}},{'kind':'wait-success','input_event':2,'serial_file':'second.txt'}]
  check('offline bounded valid sequence',len(h.bounded_input_windows(windows,events))==2)
  for text,label in [('prior\nfirst\nsecond\n','next-input borrowing'),('prior\n','stale UART')]:
   (windows/'first.txt').write_text(text)
   try:h.bounded_input_windows(windows,events)
   except RuntimeError:check('offline rejects '+label,True)
   else:raise AssertionError(label+' accepted')
  with patch.dict(os.environ,{'M5_UNIT_WEB_BRIDGE':'1'}):
   try:h.main(['--execute','--out-dir',str(OUT/'forbidden-execute')])
   except RuntimeError:check('execution requires root-supplied sync context before side effects',True)
   else:raise AssertionError('unbound execute admitted')
  check('execution rejection creates no output',not(OUT/'forbidden-execute').exists())
check('zero API/process/build/Client calls',calls==[])
check('no prepared binaries',not list(OUT.rglob('*.bin')))
for name,digest in pins.items():check('frozen author still unchanged '+name,sha((AUTHOR/name).read_bytes())==digest)
report={'schema_version':1,'result':'NO_ACTIONABLE_FINDINGS','scope':'Independent offline/static review and denied-side-effect preparation/synthetic UART counterexamples. No API/browser/guest/QEMU/BIN execution; not functional PASS.','check_count':len(checks),'checks':checks,'unexpected_calls':calls,'prepared_combinations':9,'harness_sha256':pins['run_source_hosts.py'],'all_author_pins':pins,'source_base_sha256':bases,'boundaries':['Root must commit/fetch, then fresh-prepare with exact post-sync HEAD before execution.','Original host guest, config, BMI/display, validate_case and validate_bundle remain intact.','The original BMI observation is not an atomic snapshot with the last QOM/frame; this review does not extend that claim.','Worker generation is observed, optional expected value; no fixed generation 11.']}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['result','check_count','unexpected_calls','prepared_combinations','harness_sha256']},ensure_ascii=False))
