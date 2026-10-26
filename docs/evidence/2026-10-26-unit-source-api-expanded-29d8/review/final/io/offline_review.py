"""Independent read-only authoring audit; no live API, session or runtime."""
from pathlib import Path
import ast, hashlib, importlib.util, json, socket, subprocess, sys, urllib.request
from unittest.mock import patch
from datetime import datetime,timezone
ROOT=Path.cwd();HERE=ROOT/'.work/unit-source-io-expanded-20261026';OUT=ROOT/'.work/unit-expanded-cross-review-20261026/io'
sys.path.insert(0,str(HERE));sys.path[:0]=[str(ROOT/'platform/tools'),str(ROOT/'platform/tests'),str(ROOT/'tests/units')]
module_path=HERE/'run_expanded_io.py';spec=importlib.util.spec_from_file_location('expanded_io_independent_review',module_path);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
calls=[]
def deny(kind):
 def reject(*args,**kwargs):calls.append(kind);raise RuntimeError('independent audit forbidden '+kind)
 return reject
with patch.object(socket,'socket',deny('socket')),patch.object(urllib.request,'urlopen',deny('http')),patch.object(subprocess,'Popen',deny('process')),patch.object(subprocess,'run',deny('process')):
 m=h.io_module()
 with patch.object(m,'prepare',deny('legacy_prepare')),patch.object(m,'build_control_image',deny('binary_builder')):
  prepared=HERE/'independent-readonly-review-r1';rows=h.prepare(prepared,list(h.DEFAULT))
 assert not calls,calls
 original_functions=h.function_hashes();raw=(ROOT/'tests/units/run_io_cases.py').read_text();tree=ast.parse(raw)
 assert {n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in original_functions}==set(original_functions)
 assert Path(m.validate_io.__code__.co_filename).resolve()==ROOT/'tests/units/run_io_cases.py'
 assert Path(m.validate_evidence.__code__.co_filename).resolve()==ROOT/'tests/units/run_io_cases.py'
 for row in rows:
  directory=prepared/row['unit_id'];request=h.load(directory/'source-request.json')
  assert h.sha(h.canonical(request['files']))==row['source_cas_sha256']
  assert row['original_function_sha256']==original_functions
  for name,text in request['files'].items():
   assert (directory/'files'/name).read_bytes()==text.encode()
   if name!='probe_config.py':assert (ROOT/'tests/units/io_probe'/name).read_bytes()==text.encode()
  assert len(h.canonical(request))<=1024*1024
  if row['unit_id']=='hub':assert row['attachments']==m.attachments('hub',row['port_id'])
 from unit_adc_fixture import load_fixture,verify_firmware,expected_ideal_input
 matrix=next(x for x in h.load(ROOT/'tests/uiflow2/device_matrix.json')['devices'] if x['id']=='cores3')
 base=(ROOT/matrix['base']).read_bytes();fixture=load_fixture();verify_firmware(base,fixture)
 assert h.sha(base)==h.BASE
 adc={'reference_base_sha256':h.sha(base),'application_binding':fixture['firmware_binding'],'fixture_sha256':h.sha((ROOT/'platform/units/fixtures/esp32s3-adc-calibration.json').read_bytes()),'angle_vectors':{str(v):expected_ideal_input(v,attenuation=3,adc_unit=1) for v in (0,1250,2500)},'light_vectors':{str(v):expected_ideal_input(v,attenuation=3,adc_unit=1) for v in (310,1550,3100)}}
report={'schema_version':1,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'result':'NO_ACTIONABLE_FINDINGS','findings':[],'scope':['run_expanded_io.py','source_api_common.py','original Observations/validate_io/validate_evidence/attachments/buzzer_timer_window','io_probe/io_program.py and driver-byte manifests','ADC reference application binding and read_uv oracle','Web bridge and source-pin/evidence/cleanup paths'],'harness_sha256':h.sha(module_path.read_bytes()),'common_sha256':h.sha((HERE/'source_api_common.py').read_bytes()),'independent_offline_prepare':{'status':'PASS','output':str(prepared.relative_to(ROOT)),'cases':[r['unit_id'] for r in rows],'source_files_per_case':{r['unit_id']:len(r['probe_sha256']) for r in rows},'unexpected_http_process_builder_prepare_calls':calls,'request_sizes':{r['unit_id']:len(h.canonical(h.load(prepared/r['unit_id']/'source-request.json'))) for r in rows}},'original_function_sha256':original_functions,'adc_offline_binding':adc,'review_evidence':[
'Observed subclass directly invokes super().wait/marker/state/input/qom and the original runtime validate_io plus original validate_evidence functions; there is no replacement controller response or host-computed guest value.',
'Fresh cursor gating is per last accepted input, not per wait. Once serial has grown beyond that input baseline, subsequent property checks or marker reads may succeed without requiring another UART increment. This does not add a spurious per-property UART requirement.',
'Every accepted injection in the nine default original cases is followed by a serial predicate. Same-state first Angle zero is legal: the original guest emits a periodic 1500ms reading even when value stays unchanged, within the unchanged 60s timeout.',
'PIR IRQ disable/rearm and no-callback interval, dual-button raw/click state machines, LIMIT alias/edge counter/reset, and Key native RMT colors remain in original validate_io.',
'Angle includes unchanged exact read_u16/read_uv and monotonic calibrated-voltage assertions. CoreS3 reference application bytes match the fixture binding offline; the actual session ZIP must still prove its applied virtual calibration receipt.',
'RS485 retains original UART1 binary RX/TX/echo and FIFO rejection through direct API, with rejected FIFO writes distinct from accepted Web-driven inputs and UART0 log path.',
'HUB topology is the original passive HUB plus ENV III, NCIR and TVOC. It retains original three independent child inputs, combined-vector checks and per-leaf transaction/byte/input counters.',
'Source composition uses transparent caller Python bytes, pinned base SHA and canonical source CAS. Source sessions send uiflow_source_sha256; original driver source bytes are checked and never patched automatically.',
'Online evidence requires real browser DOM/readback HTTP, direct QEMU executable SHA and worker lease/generation, ZIP before stop, history/frame retention, Flash release, owned PID exit and idle health. All created sessions enter evidence/stop finally blocks.',
'Original IR/Buzzer known-gap controls are excluded from defaults and cannot automatically become PASS; unprepared custom flavor fails closed.'
],'limitations':[
'No 8787 API, guest, QEMU or browser execution performed. No functional, controller, physical-device or audio PASS is asserted.',
'The review checked preparation and original function identity plus code paths, not timing stress or live event ordering.',
'Offline source request preparation is independently verified; live assertions and evidence replay remain root-owned.',
'Native PNG nonblank checks do not prove readable text, physical signals, bit-exact silicon behavior or an untrusted-firmware sandbox.'
]}
(OUT/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'result':report['result'],'cases':len(rows),'unexpected_calls':calls,'harness_sha256':report['harness_sha256'],'report':str(OUT/'review.json')},ensure_ascii=False))
