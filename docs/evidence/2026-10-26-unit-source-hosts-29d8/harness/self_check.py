#!/usr/bin/env python3
"""Offline preparation/no-side-effect and bounded-window counterexample checks."""
from pathlib import Path
from unittest.mock import patch
import ast,contextlib,hashlib,importlib.util,io,json,os,socket,subprocess,sys,urllib.request
ROOT=Path.cwd();HERE=ROOT/'.work/unit-source-hosts-expanded-20261026'
sys.path.insert(0,str(HERE));spec=importlib.util.spec_from_file_location('source_hosts_self_check',HERE/'run_source_hosts.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
calls=[];checks=[]
def deny(label):
 def nope(*args,**kwargs):calls.append(label);raise AssertionError('Forbidden offline operation: '+label)
 return nope
def check(name,value):
 checks.append(name)
 if not value:raise AssertionError(name)
output=HERE/'self-check-r1';check('fresh self-check directory',not output.exists());output.mkdir()
with patch.object(socket,'socket',deny('socket')),patch.object(urllib.request,'urlopen',deny('http')),patch.object(subprocess,'Popen',deny('subprocess.Popen')),patch.object(subprocess,'run',deny('subprocess.run')),patch.object(subprocess,'check_output',deny('subprocess.check_output')):
 module=h.original_module()
 import run_service_cases,run_control_cases,run_profile_ui_test
 with patch.object(module,'prepare',deny('legacy host prepare')),patch.object(module,'build_control_image',deny('host BIN builder')),patch.object(run_control_cases,'build_control_image',deny('control BIN builder')),patch.object(run_profile_ui_test,'build_image',deny('image BIN builder')),patch.object(module,'Client',deny('host Client')),patch.object(run_service_cases,'Client',deny('service Client')):
  with contextlib.redirect_stdout(io.StringIO()) as stdout:h.main(['--out-dir',str(output/'default-preparation')])
  prepared=h.load(output/'default-preparation/prepared.json');rows=prepared['cases'];check('nine default source-only combinations',len(rows)==9 and {(r['device_id'],r['unit_id']) for r in rows}=={(d,c) for d in h.DEVICES for c in h.CASES})
  check('authoring context cannot be mistaken for final execution freeze',prepared['source_context_stage']=='AUTHORING_ONLY_REPREPARE_AFTER_ROOT_SYNC' and prepared['fresh_prepare_required_after_root_commit_and_fetch'])
  for row in rows:
   directory=output/'default-preparation'/row['device_id']/row['unit_id'];request=h.load(directory/'source-request.json');files=request['files'];check(row['device_id']+'/'+row['unit_id']+' has four original Python + explicit config',set(files)=={'boot.py','main.py','probe_logging.py','host_program.py','probe_config.py'})
   check(row['device_id']+'/'+row['unit_id']+' CAS and source body size',h.sha(h.canonical(files))==row['source_cas_sha256'] and len(h.canonical(request))<=1048576)
   check(row['device_id']+'/'+row['unit_id']+' actual reference hash',h.sha((ROOT/row['reference_file']).read_bytes())==request['expected_base_sha256']==row['base_firmware_sha256'])
   check(row['device_id']+'/'+row['unit_id']+' native matrix frame',row['expected_size']==module.HOSTS[row['device_id']]['size'])
   check(row['device_id']+'/'+row['unit_id']+' original host profile',row['host_profile']=={**module.HOSTS[row['device_id']],'canvas_size':module.HOSTS[row['device_id']].get('canvas_size',module.HOSTS[row['device_id']]['size']),'log_tx':43,'log_rx':44,'internal_controller':1,'external_controller':0})
   for name,text in files.items():
    check(row['device_id']+'/'+row['unit_id']+' request/disk bytes '+name,(directory/'files'/name).read_bytes()==text.encode())
    if name!='probe_config.py':check('unmodified original '+row['device_id']+'/'+row['unit_id']+'/'+name,(ROOT/'tests/units/host_probe'/name).read_bytes()==text.encode())
   check(row['device_id']+'/'+row['unit_id']+' no uploaded drivers/ADC',row['uploaded_driver_files']==[] and row['adc_fixture']=='NOT USED')
  # Compare the original host prepare config AST, normalizing only args.device.
  def config_node(source):
   tree=ast.parse(source);prepare=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='prepare')
   return next(n.value for n in ast.walk(prepare) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='config' for t in n.targets))
  class Normalize(ast.NodeTransformer):
   def visit_Attribute(self,node):
    if isinstance(node.value,ast.Name) and node.value.id=='args' and node.attr=='device':return ast.Name(id='device_id',ctx=ast.Load())
    return self.generic_visit(node)
  check('exact original generated config expression',ast.dump(Normalize().visit(config_node((ROOT/'tests/units/run_host_cases.py').read_text())),include_attributes=False)==ast.dump(config_node((HERE/'run_source_hosts.py').read_text()),include_attributes=False))
  with patch.dict(os.environ,{'M5_UNIT_WEB_BRIDGE':'1'}):
   try:h.main(['--execute','--out-dir',str(output/'forbidden-unbound-execution')])
   except RuntimeError as error:check('execute requires fresh post-sync exact context','source context' in str(error))
   else:raise AssertionError('unbound execution unexpectedly admitted')
  check('unbound execution created no directory',not (output/'forbidden-unbound-execution').exists())
  # Pure synthetic cursor tests; no fabricated Client/Unit/runtime PASS.
  synthetic=output/'synthetic-windows';synthetic.mkdir();(synthetic/'a.txt').write_bytes(b'prior\r\nA\r\n');(synthetic/'b.txt').write_bytes(b'prior\r\nA\r\nB\r\n')
  events=[{'kind':'input','event_id':0,'accepted':True,'before_cursor':{'data':'prior\r\n'}},{'kind':'wait-success','input_event':0,'serial_file':'a.txt'},{'kind':'input','event_id':2,'accepted':True,'before_cursor':{'data':'prior\r\nA\r\n'}},{'kind':'wait-success','input_event':2,'serial_file':'b.txt'}]
  check('bounded fresh windows accept valid sequence',len(h.bounded_input_windows(synthetic,events))==2)
  (synthetic/'a.txt').write_bytes(b'prior\r\nA\r\nB\r\n')
  try:h.bounded_input_windows(synthetic,events)
  except RuntimeError as error:check('upper bound rejects borrowing later-input UART','next input boundary' in str(error))
  else:raise AssertionError('later UART borrowing accepted')
  (synthetic/'a.txt').write_bytes(b'prior\r\n')
  try:h.bounded_input_windows(synthetic,events)
  except RuntimeError as error:check('fresh lower bound rejects stale UART','new UART bytes' in str(error))
  else:raise AssertionError('stale UART accepted')
  check('worker generation not hard-coded to 11','==11' not in (HERE/'run_source_hosts.py').read_text() and "'worker_generation':11" not in (HERE/'run_source_hosts.py').read_text())
  check('no prepared firmware binaries',not list((output/'default-preparation').rglob('*.bin')))
  check('zero API/browser/process/BIN calls',calls==[])
  source_calls=[n for n in ast.walk(ast.parse((HERE/'run_source_hosts.py').read_text())) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
  check('exact original validate_case and validate_bundle calls present',any(isinstance(n.func.value,ast.Name) and n.func.value.id=='module' and n.func.attr=='validate_case' for n in source_calls) and any(isinstance(n.func.value,ast.Name) and n.func.value.id=='module' and n.func.attr=='validate_bundle' for n in source_calls))
  printout={'status':'PASS','checks':checks,'check_count':len(checks),'unexpected_calls':calls,'cases':len(rows),'reference_hosts':{device:{'base_sha256':next(r['base_firmware_sha256'] for r in rows if r['device_id']==device),'native_frame':module.HOSTS[device]['size'],'canvas':module.HOSTS[device].get('canvas_size',module.HOSTS[device]['size'])} for device in h.DEVICES},'scope':'Offline authoring/preparation and synthetic cursor checks only; no source API or guest execution.'}
  h.save(output/'result.json',printout)
print(json.dumps({'status':printout['status'],'checks':len(checks),'cases':len(rows),'unexpected_calls':calls},ensure_ascii=False))
