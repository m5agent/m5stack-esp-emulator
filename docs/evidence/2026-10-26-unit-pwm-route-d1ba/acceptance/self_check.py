#!/usr/bin/env python3
"""Offline-only preparation and synthetic predicate/identity counterexamples."""
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
import contextlib,hashlib,importlib.util,io,json,os,socket,subprocess,sys,urllib.request
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('pwm_route_self_check',HERE/'run_acceptance.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
OUT=HERE/(sys.argv[1] if len(sys.argv)>1 else 'self-check-r1');assert not OUT.exists();OUT.mkdir();checks=[];calls=[]
def check(name,condition):
 if not condition:raise AssertionError(name)
 checks.append(name)
def deny(label):
 def rejected(*a,**k):calls.append(label);raise AssertionError('forbidden offline '+label)
 return rejected
def reject(name,operation):
 try:operation()
 except RuntimeError:check(name,True)
 else:raise AssertionError('negative was accepted: '+name)
with patch.object(socket,'socket',deny('socket')),patch.object(urllib.request,'urlopen',deny('urllib HTTP')),patch.object(subprocess,'Popen',deny('Popen')),patch.object(subprocess,'run',deny('subprocess.run')),patch.object(subprocess,'check_output',deny('check_output')):
 sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
 import run_service_cases,run_control_cases,run_profile_ui_test
 with patch.object(run_service_cases,'Client',deny('Client')),patch.object(run_control_cases,'build_control_image',deny('control BIN builder')),patch.object(run_profile_ui_test,'build_image',deny('BIN builder')):
  with contextlib.redirect_stdout(io.StringIO()):h.main(['--out-dir',str(OUT/'default-preparation')])
  prepared=h.load(OUT/'default-preparation/prepared.json');request=h.load(OUT/'default-preparation/source-request.json');files=request['files']
  check('default has exact five caller files',set(files)==h.GUEST_NAMES)
  check('no callback driver or custom patch',prepared['guest_audit']['callback_or_softtimer_driver']=='NOT IMPORTED')
  check('original constructor/no setter audit',prepared['guest_audit']['pwm_constructors']==1 and prepared['guest_audit']['post_constructor_setters']==0)
  for name,text in files.items():check('exact template bytes '+name,text.encode()==(HERE/'guest'/name).read_bytes()==(OUT/'default-preparation/files'/name).read_bytes())
  check('no runtime or expectation in payload/config',all(x not in files['probe_config.py'].lower() for x in ['runtime','expect','candidate','baseline','generation']))
  row2,request2=h.prepare(OUT/'second-preparation');check('two preparations preserve same source request/CAS',request==request2 and prepared['source_cas_sha256']==row2['source_cas_sha256'])
  check('source-only payload fixed base',request['expected_base_sha256']==prepared['base_sha256']==h.common.BASE)
  reject('post-init duty zero setter rejected',lambda:h.guest_audit({**files,'pwm_route_program.py':files['pwm_route_program.py'].replace('duty = pwm.duty_u16()','duty = pwm.duty_u16(0)')}))
  reject('post-init frequency setter rejected',lambda:h.guest_audit({**files,'pwm_route_program.py':files['pwm_route_program.py'].replace('frequency = pwm.freq()','frequency = pwm.freq(2000)')}))
  reject('extra PWM constructor rejected',lambda:h.guest_audit({**files,'pwm_route_program.py':files['pwm_route_program.py']+'\nextra = PWM(Pin(2), freq=2000, duty_u16=0)\n'}))
  reject('runtime in config rejected',lambda:h.guest_audit({**files,'probe_config.py':files['probe_config.py']+"RUNTIME = 'example'\n"}))
  reject('custom callback import rejected',lambda:h.guest_audit({**files,'pwm_route_program.py':files['pwm_route_program.py']+'\nfrom driver.haptic import Haptic\n'}))
  before={'data':'PWMR_READY\r\nPWMR_HOLD 0 10 2000 0\r\n','next_offset':40};after={'data':before['data']+'PWMR_HOLD 1 260 2000 0\r\n','next_offset':70}
  def state(freq,duty=0):return {'source':'live','contract_status':'frozen','units':[{'id':'external1','unit_id':'buzzer','source':'guest-qom','available':True,'errors':[],'properties':{'frequency-hz':freq,'duty-pct':duty}}]}
  check('zero-Hz baseline can be collected without calling it fixed',h.evaluate_sample(before,state(0),after,0)['frequency-hz']==0)
  check('candidate 2000Hz accepted',h.evaluate_sample(before,state(2000),after,2000)['frequency-hz']==2000)
  check('candidate 1Hz quantization tolerance',h.evaluate_sample(before,state(2000.5),after,2000)['frequency-hz']==2000.5)
  reject('zero does not pass candidate',lambda:h.evaluate_sample(before,state(0),after,2000))
  reject('2000 does not reproduce baseline failure',lambda:h.evaluate_sample(before,state(2000),after,0))
  reject('nonzero duty rejected',lambda:h.evaluate_sample(before,state(2000,.1),after,2000))
  reject('NaN frequency rejected',lambda:h.evaluate_sample(before,state(float('nan')),after,2000))
  reject('stale UART rejected',lambda:h.evaluate_sample(before,state(2000),before,2000))
  reject('new unrelated bytes do not prove fresh heartbeat',lambda:h.evaluate_sample(before,state(2000),{'data':before['data']+'unrelated\r\n','next_offset':70},2000))
  reject('hold completed boundary rejected',lambda:h.evaluate_sample(before,state(2000),{'data':after['data']+'PWMR_HOLD_DONE\r\n','next_offset':80},2000))
  reject('getter zero mismatch rejected',lambda:h.evaluate_sample(before,state(2000),{'data':after['data'].replace('1 260 2000 0','1 260 0 0'),'next_offset':80},2000))
  reject('changed UART prefix rejected',lambda:h.evaluate_sample(before,state(2000),{'data':after['data'].replace('0 10 2000 0','0 20 2000 0'),'next_offset':80},2000))
  fake={'status':'FAIL_REPRODUCED','initialization_status':'FAIL_REPRODUCED','expect_init_frequency_hz':0,'firmware_sha256':'a'*64,'source_cas_sha256':prepared['source_cas_sha256'],'source':{'metadata':{'effective_source_sha256':prepared['source_cas_sha256']}},'caller_request_sha256':h.sha(h.canonical(request)),'runtime_provenance':{'runtime_binary_sha256':'b'*64}}
  candidate={**fake,'expected_runtime_sha256':'c'*64}
  check('same-identity A/B pairing accepted',h.compare_peer(fake,candidate,request)['same_firmware_sha256']=='a'*64)
  for label,field,value in [('different firmware','firmware_sha256','d'*64),('different caller CAS','source_cas_sha256','e'*64),('same runtime','expected_runtime_sha256','b'*64)]:reject('A/B rejects '+label,lambda field=field,value=value:h.compare_peer(fake,{**candidate,field:value},request))
  reject('A/B rejects non-baseline status',lambda:h.compare_peer({**fake,'status':'PASS'},candidate,request))
  reject('execute exact SHA required before side effects',lambda:h.main(['--execute','--out-dir',str(OUT/'forbidden-no-sha')]))
  with patch.dict(os.environ,{'M5_UNIT_WEB_BRIDGE':'1'}):reject('candidate baseline peer mandatory',lambda:h.main(['--execute','--out-dir',str(OUT/'forbidden-no-peer'),'--expected-runtime-sha256','f'*64,'--expect-init-frequency','2000']))
  check('rejected executions create no dirs',not(OUT/'forbidden-no-sha').exists() and not(OUT/'forbidden-no-peer').exists())
  check('no BIN files from default/prepare',not list(OUT.rglob('*.bin')))
  check('zero API/Client/process/BIN-builder calls',calls==[])
report={'status':'PASS','scope':'Offline authoring and explicit synthetic counterexamples only; no runtime/API/guest/QEMU/BIN execution. Not initialization functional PASS.','check_count':len(checks),'checks':checks,'unexpected_calls':calls,'source_cas_sha256':prepared['source_cas_sha256'],'raw_zero_baseline_status':'FAIL_REPRODUCED','setter_workaround_in_new_caller':False}
h.save(OUT/'result.json',report);print(json.dumps({'status':'PASS','checks':len(checks),'unexpected_calls':calls,'source_cas_sha256':prepared['source_cas_sha256']}))
