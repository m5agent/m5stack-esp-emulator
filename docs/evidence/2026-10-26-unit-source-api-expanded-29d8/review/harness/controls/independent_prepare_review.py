"""Read-only control harness/contract review; only reviewer outputs are written."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import sys
import textwrap

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
TARGET=ROOT/'.work/unit-source-controls-expanded-20261026/run_source_controls.py'
raw=TARGET.read_bytes();tree=ast.parse(raw.decode());original=ROOT/'tests/units/run_control_cases.py';origin_raw=original.read_bytes();origin_tree=ast.parse(origin_raw.decode())
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
original_run=next(n for n in origin_tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
body=next(n for n in original_run.body if isinstance(n,ast.Try)).body
begin=next(i for i,n in enumerate(body) if isinstance(n,ast.If) and ast.dump(n.test)==ast.dump(ast.Compare(left=ast.Name(id='case',ctx=ast.Load()),ops=[ast.Eq()],comparators=[ast.Constant(value='joystick-v11')])))
end=next(i for i,n in enumerate(body) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='frame' for t in n.targets))
expected=ast.Module(body=body[begin:end],type_ignores=[])
fn=functions['original_control_protocol'];start=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and ast.unparse(n.test)=="case == 'joystick-v11'")
actual=ast.Module(body=fn.body[start:start+len(expected.body)],type_ignores=[])
assert ast.dump(expected,include_attributes=False)==ast.dump(actual,include_attributes=False),'original control block AST changed'
assertion_count=sum(isinstance(n,ast.Assert) for n in ast.walk(expected));assert assertion_count==13
module_spec=importlib.util.spec_from_file_location('controls_independent_review',TARGET);module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
self_test=module.offline_self_test(HERE/'offline-self-test-cross-r1')
assert self_test['status']=='PASS' and self_test['unexpected_api_process_bin_calls']==[]
prepared=HERE/'offline-self-test-cross-r1';prepared_rows=json.loads((prepared/'prepared.json').read_text())['cases'];driver_manifest=json.loads((ROOT/'tests/units/controls_probe/control_drivers/source-manifest.json').read_text())
cases=[]
for row in prepared_rows:
    d=prepared/row['unit_id'];request=json.loads((d/'source-request.json').read_text());files=request['files'];main=files['main.py']
    for before,after in reversed(module.DISPLAY_REPLACEMENTS):
        assert main.count(after)==1;main=main.replace(after,before)
    assert main.encode()==(ROOT/'tests/units/controls_probe/main.py').read_bytes()
    for name,record in json.loads((d/'official-driver-proof.json').read_text()).items():
        assert record==driver_manifest[name.removeprefix('control_drivers/')]
        assert hashlib.sha256(files[name].encode()).hexdigest()==record['sha256']
    assert files['host_control_layout.py'].encode()==(ROOT/'tests/units/host_controls_probe/host_control_layout.py').read_bytes()
    assert (d/'license-evidence/control_drivers/LICENSE.MIT').read_bytes()==(ROOT/'tests/units/controls_probe/control_drivers/LICENSE.MIT').read_bytes()
    wire_size=len(json.dumps(request).encode());assert wire_size<=1048576
    cases.append({'case':row['unit_id'],'source_cas_sha256':row['source_cas_sha256'],'files':len(files),'actual_Client_json_body_bytes':wire_size,'display_contract':row['display_contract'],'display_exact_reverse':'PASS','official_driver_and_license_bytes':'PASS'})
fixture=json.loads((ROOT/'platform/units/fixtures/cardkb-keymap.json').read_text());normal=[row for row in fixture['keys'] if not row['modifier']];by_id={row['id']:row for row in fixture['keys']}
stream=[row['normal'] for row in normal if row['normal']]
for field in ('shift','sym','fn'):
    stream += [code for code in (by_id['key-q'][field],by_id['key-q']['normal']) if code]
for field in ('shift','sym','fn'):stream += [row[field] for row in normal if row[field]]
stream += [65]
assert len(normal)==47 and len(fixture['keys'])==50 and len(stream)==187 and stream==module.expected_cardkb_stream(fixture)
report={'status':'PASS_AFTER_RFID_WINDOW_FIX','review_category':'static-and-pure-offline-only','api_calls':0,'guest_execution':False,'hardware':'NOT RUN','harness_sha256':hashlib.sha256(raw).hexdigest(),'source_unchanged_during_review':TARGET.read_bytes()==raw,'original_runner_sha256':hashlib.sha256(origin_raw).hexdigest(),'entire_original_control_block_ast_equal':True,'original_assert_count':assertion_count,'display_replacements':len(module.DISPLAY_REPLACEMENTS),'cases':cases,'cardkb':{'physical_nonmodifier_keys':47,'modifier_keys':3,'nonzero_codes_by_table':{field:sum(bool(row[field]) for row in normal) for field in ('normal','shift','sym','fn')},'one_shot_codes':6,'legacy_codes':1,'expected_stream_length':len(stream),'expected_stream_sha256':hashlib.sha256(json.dumps(stream,separators=(',',':')).encode()).hexdigest()},'self_test':{'status':self_test['status'],'guard_probes_blocked':self_test['guard_probes_blocked'],'unexpected_api_process_bin_calls':self_test['unexpected_api_process_bin_calls'],'source_drift_negative':self_test['source_drift_negative']},'rfid_regression_receipts':['baseline-rfid-window.json','current-rfid-window.json']}
(HERE/'review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:report[k] for k in ('status','api_calls','harness_sha256','source_unchanged_during_review','entire_original_control_block_ast_equal','original_assert_count','self_test')},ensure_ascii=False,indent=2))
