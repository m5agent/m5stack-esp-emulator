#!/usr/bin/env python3
"""Explicit custom-only IR/Buzzer source API acceptance for CoreS3.

Independent fork; default preparation is offline, and only --execute uses the
real Device Service/Web bridge. Original IO assertions remain unchanged.
The caller driver copy is explicitly patched; original-driver PASS is forbidden.
"""
from __future__ import annotations
import argparse,ast,hashlib,io,json,os,pathlib,re,sys,time,urllib.parse,zipfile
from datetime import datetime,timezone
import source_api_common as common
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];PROBE=ROOT/'tests/units/io_probe'
BASE=common.BASE;RUNTIME=common.RUNTIME;CONTEXT_COMMIT='5cf58191af2938ecd86f991455b47145872fb08e'
DEFAULT=('ir','buzzer')
KNOWN_GAP=();ALL=DEFAULT
FLAVORS={'ir':'custom-guest-ir-callback-root-patch','buzzer':'custom-guest-buzzer-callback-arity-patch'}
PATCHES={'ir':'patches/uiflow2-unit-ir/0001-root-native-receive-callback.patch','buzzer':'patches/uiflow2-unit-buzzer/0001-accept-soft-timer-callback.patch'}
need=common.need;sha=common.sha;canonical=common.canonical;save=common.save;load=common.load
EXPECTED={
 'pir':{'both_gpio_edges_and_disable_reenable_irq'},
 'dual-button':{'independent_hardware_button_pins_and_click_state_machines'},
 'limit':{'official_limit_button_alias_irq_counter_and_reset'},
 'key':{'active_low_key_and_guest_brightness_rgb_frames'},
 'angle':{'unchanged_idf_curve_fitting_exact_uv_and_monotonic_voltage','selected_white_adc_ideal_12bit_transfer'},
 'light':{'selected_white_adc_ideal_12bit_transfer','independent_yellow_digital_input'},
 'fan':{'guest_ledc_frequency_and_duty_registers'},
 'rs485':{'uart1_bidirectional_binary_fifo_and_any_read_write','fifo_capacity_rejection_and_uart0_log_separation'},
 'hub':{'passive_hub_three_real_drivers_independent_inputs_same_bus','hub_has_no_i2c_address'},
 'buzzer':{'haptic_once_timer_and_turn_off','guest_ledc_frequency_and_duty_registers'},
 'ir':{'official_wrapper_faithful_raw16_plus_16_payload','separate_native_uint16_packed_nec8_transmit','native_nec_tx_rx_bad_frame_and_rearmed_receiver','native_nec_repeat_preserves_last_address_and_command'},
}

def now():return datetime.now(timezone.utc).isoformat()
def io_module():
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
    import run_io_cases
    need(pathlib.Path(run_io_cases.__file__).resolve()==ROOT/'tests/units/run_io_cases.py','wrong original IO runner module')
    return run_io_cases

def function_hashes():
    raw=(ROOT/'tests/units/run_io_cases.py').read_text();tree=ast.parse(raw)
    selected={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in ('Observations','validate_io','validate_evidence','attachments','buzzer_timer_window'):
            selected[node.name]=sha(ast.get_source_segment(raw,node).encode())
    need(len(selected)==5,'original IO functions missing');return selected

def patch_module():
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
    import prepare_host_io
    need(pathlib.Path(prepare_host_io.__file__).resolve()==ROOT/'tests/units/prepare_host_io.py','wrong pure patch helper module')
    return prepare_host_io


def patch_helper_hashes():
    raw=(ROOT/'tests/units/prepare_host_io.py').read_text();tree=ast.parse(raw)
    hashes={n.name:sha(ast.get_source_segment(raw,n).encode()) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('strict_patch','custom_driver')}
    need(set(hashes)=={'strict_patch','custom_driver'},'pure helper functions missing');return hashes


def config_text(case,pins):
    return f"CASE = {case!r}\nWHITE = {pins['white']}\nYELLOW = {pins['yellow']}\nIR_CALLBACK_ROOT_PATCH = {case=='ir'!r}\n"


def reverse_patch(raw):
    """Reverse the pinned unified patch as bytes; application uses strict_patch."""
    lines=raw.decode('utf-8').splitlines(keepends=True);need(len(lines)>=3,'patch is incomplete')
    output=lines[:2]
    for line in lines[2:]:
        if line.startswith('@@ '):
            match=re.fullmatch(r'@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n',line);need(match is not None,'unsupported pinned hunk')
            a,b,c,d=match.groups();output.append(f'@@ -{c},{d} +{a},{b} @@\n')
        else:
            need(line[:1] in (' ','+','-'),'unsupported pinned hunk line');output.append(('-' if line[0]=='+' else '+' if line[0]=='-' else ' ')+line[1:])
    return ''.join(output).encode()


def source_only_intake(path,method,body=None):
    path=path.split('?',1)[0].strip('/').removeprefix('api/v1/')
    if method in ('POST','PUT','PATCH'):
        need(path not in ('artifacts','firmware','firmware/import') and not path.startswith('artifact-uploads'),'binary intake forbidden; custom copies use source JSON API')
        if path=='firmware/uiflow':need(body is None,'raw source upload is forbidden')


def custom_identity(directory,row,request,freeze):
    """Re-derive custom driver identity instead of trusting custom labels/bools."""
    case=row['unit_id'];need(case in DEFAULT,'custom harness only accepts IR/Buzzer')
    need(row['firmware_flavor']==FLAVORS[case] and row['driver_validation']=='custom-only' and row['custom_driver_modification'] is True and row['published_original_driver_status']=='SEPARATE_RESULT_NOT_INHERITED','custom case was relabeled as an original-driver PASS')
    need(row['custom_flags']=={'ir_callback_root_patch':case=='ir','buzzer_callback_arity_patch':case=='buzzer'},'custom patch flags differ')
    need(row['original_function_sha256']==function_hashes() and row['pure_patch_helper_sha256']==patch_helper_hashes(),'original IO assertions or pure patch helpers changed')
    need(request['device_id']=='cores3' and request['expected_base_sha256']==BASE and row['source_cas_sha256']==sha(canonical(request['files'])),'custom source CAS/base differs')
    need(row['http_json_body_bytes']==len(json.dumps(request,allow_nan=False).encode())<=1024*1024,'custom HTTP source body bytes differ')
    need(row['attachments']==[{'id':'external1','unit_id':case,'port_id':'port-a'}],'custom attachment wiring differs')
    need(row['known_original_guest_gap'] is False,'custom was classified as an original known-gap control')
    proof=load(directory/'custom-driver-proof.json');need(row['custom_driver_patch']==proof and row['ir_callback_patch' if case=='ir' else 'buzzer_callback_patch']==proof,'patch proof differs between record and source')
    need(proof['path']==PATCHES[case] and proof['driver_path']=='io_drivers/'+case+'.py','wrong custom driver/patch')
    snap=directory.parent/'source-snapshot';original=(snap/('tests/units/io_probe/'+proof['driver_path']+'.txt')).read_bytes();patch=(snap/(PATCHES[case]+'.txt')).read_bytes();reverse=reverse_patch(patch)
    helper=patch_module();derived=helper.strict_patch(original,patch,proof['driver_path']);restored=helper.strict_patch(derived,reverse,proof['driver_path'])
    need(restored==original and sha(original)==proof['original_driver_sha256']==proof['restored_driver_sha256'] and sha(derived)==proof['patched_driver_sha256'] and sha(patch)==proof['patch_sha256']==freeze[PATCHES[case]] and sha(reverse)==proof['reverse_patch_sha256'],'patch/original/derived/reverse bytes do not prove reversible identity')
    for name,data in (('original-driver.py.txt',original),('forward.patch',patch),('reverse.patch',reverse),('restored-driver.py.txt',restored)):
        need((directory/'patch-evidence'/name).read_bytes()==data,'patch evidence changed: '+name)
    need((PROBE/proof['driver_path']).read_bytes()==original,'official repository driver was modified')
    need(proof['original_driver_unchanged'] is True and proof['native_module_modified'] is proof['frozen_modules_modified'] is proof['controller_modified'] is False and proof['reversible_byte_exact'] is True,'custom scope overreaches caller wrapper copy')
    drivers=load(snap/'tests/units/io_probe/io_drivers/source-manifest.json.txt')
    need(drivers==row['official_drivers']==load(directory/'official-driver-proof.json'),'official manifest differs')
    need(drivers[case+'.py']['sha256']==sha(original),'original driver is not the pinned official bytes')
    originals={p.relative_to(snap/'tests/units/io_probe').as_posix()[:-4]:p.read_bytes() for p in (snap/'tests/units/io_probe').rglob('*.py.txt')}
    files=request['files'];actual={p.relative_to(directory/'files').as_posix():p.read_bytes() for p in (directory/'files').rglob('*') if p.is_file()};origins=load(directory/'guest-source-freeze.json')
    need(set(files)==set(actual)==set(row['probe_sha256'])==set(origins)==set(originals)|{'probe_config.py'},'custom caller Python membership differs')
    for name,text in files.items():
        raw=text.encode();need(raw==actual[name] and sha(raw)==row['probe_sha256'][name]==origins[name]['sha256'],'custom caller file changed: '+name);ast.parse(text,filename=name)
        expected=config_text(case,{'white':1,'yellow':2}).encode() if name=='probe_config.py' else derived if name==proof['driver_path'] else originals[name]
        need(raw==expected,'unexpected guest modification: '+name)
        if name==proof['driver_path']:need(origins[name]['origin']=='explicit-custom-derived-copy' and origins[name]['original_sha256']==sha(original),'derived caller driver has no explicit custom origin')
        elif name!='probe_config.py':need(origins[name]['origin']=='byte-exact-original-probe-or-driver','original probe provenance changed')
    for name,record in drivers.items():need(sha(files['io_drivers/'+name].encode())==(sha(derived) if name==case+'.py' else record['sha256']),'unexpected non-selected driver change: '+name)
    need((directory/'license-evidence/LICENSE.MIT').read_bytes()==(snap/'tests/units/io_probe/io_drivers/LICENSE.MIT.txt').read_bytes(),'driver MIT license changed')
    return {'firmware_flavor':FLAVORS[case],'original_driver_sha256':sha(original),'patch_sha256':sha(patch),'derived_driver_sha256':sha(derived),'reverse_restores_official_bytes':True}


def prepared_check(output):
    prepared=load(output/'prepared.json');need(prepared['status']=='PREPARED_NO_API_OR_RUNTIME' and prepared['firmware_flavor']=='EXPLICIT_CUSTOM_ONLY','wrong custom preparation category')
    rows=prepared['cases'];need(rows and set(r['unit_id'] for r in rows)<=set(DEFAULT) and len({r['unit_id'] for r in rows})==len(rows),'missing/duplicate custom cases')
    freeze=load(output/'tooling-source-freeze.json')
    for name,digest in freeze.items():
        path=output/'source-snapshot'/(name+'.txt');need(path.is_file() and not path.is_symlink() and sha(path.read_bytes())==digest,'custom frozen tooling changed: '+name)
    need(load(output/'original-functions.json')==function_hashes() and load(output/'pure-patch-helper-functions.json')==patch_helper_hashes(),'original validators/helper source changed')
    details={}
    for row in rows:
        d=output/row['unit_id'];need(row==load(d/'prepared.json'),'custom per-case/root preparation differs');details[row['unit_id']]=custom_identity(d,row,load(d/'source-request.json'),freeze)
    return {'status':'PREPARED_NOT_EXECUTED','cases':details,'api_calls':0,'process_calls':0,'binary_build_or_upload':False,'original_driver_pass':False}


def timer_http_proof(actual,sid,observation,module):
    """Replay the original natural-zero oracle with ordered raw HTTP responses."""
    prefix='/api/v1/sessions/'+sid;need(observation['before_timer_done_and_manual_output'] is True,'natural timer observation was not before manual output')
    before=[];after=[];states=[]
    for i,(event,payload) in enumerate(actual):
        if event['path']==prefix+'/serial' and isinstance(payload.get('data'),str):
            digest=sha(payload['data'].encode())
            if digest==observation['before_serial_sha256']:before.append((i,payload['data']))
            if digest==observation['after_serial_sha256']:after.append((i,payload['data']))
        elif event['path']==prefix+'/units' and payload.get('source')=='live':
            for unit in payload.get('units',[]):
                if unit['id']=='external1' and unit['unit_id']=='buzzer' and unit['source']=='guest-qom' and unit['available'] and unit['properties']==observation['qom']:states.append(i)
    for i,b in before:
        for j,a in after:
            middle=[k for k in states if i<k<j]
            if middle and module.buzzer_timer_window(observation['qom'],b,a,observation['serial_offset']):
                return {'status':'PASS','before_http_index':i,'qom_http_index':middle[0],'after_http_index':j,'frequency_hz':observation['qom']['frequency-hz'],'duty_pct':observation['qom']['duty-pct'],'before_timer_done_and_manual_output':True}
    raise RuntimeError('natural timer zero lacks ordered real HTTP serial/QOM/serial and the unchanged original predicate')


def strict_http(directory,row,result,actual):
    sid=result['session_id'];prefix='/api/v1/sessions/'+sid;events=load(directory/'http/index.json')
    def backed(payload,path):return any(e['path']==path and p==payload for e,p in actual)
    proof=result['runtime_provenance'];ready=load(directory/'ready-session.json');running=load(directory/'running-session.json')
    need(proof['kind']=='direct-pid' and proof['status']=='VERIFIED' and proof['worker_generation']==row['expected_worker_generation'] and proof['runtime_binary_sha256']==row['expected_runtime_sha256'],'direct runtime/worker generation differs')
    need(backed(ready,prefix) and backed(running,prefix) and ready['pid']==running['pid']==proof['observed_pid'] and ready['firmware_provenance']==running['firmware_provenance']==result['source'],'PID/firmware source lacks matching real HTTP session snapshots')
    history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');stopped=load(directory/'stop-response.json')
    need(backed(history,prefix) and backed(health,'/api/v1/health') and backed(stopped,prefix) and history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and history['firmware_provenance']==result['source'],'retained stop/history/source/Flash HTTP differs')
    need(health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0 and result['cleanup']['pid']==proof['observed_pid'] and result['cleanup']['pid_gone'] is True,'cleanup idle worker/service or recorded owned PID differs')
    evidence=(directory/'evidence.zip').read_bytes();zips=[];stops=[]
    for i,event in enumerate(events):
        source_only_intake(event['path'],event['method'])
        raw=(directory/'http'/event['response_file']).read_bytes()
        if event['path']==prefix+'/evidence' and event['status']==200 and raw==evidence:zips.append(i)
        if event['path']==prefix and event['method']=='DELETE' and event['query']=='purge=0' and event['status']==200:stops.append(i)
    need(zips and stops and max(zips)<min(stops),'custom ZIP was not captured before purge=0 stop')
    with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
        serial=archive.read('serial.log')
        need(serial.startswith((directory/'serial-final.txt').read_bytes()),'ZIP lost final observed guest UART')
        for i,event in enumerate(events):
            if i>=max(zips) or event['path']!=prefix+'/serial' or event['status']!=200:continue
            chunk=json.loads((directory/'http'/event['response_file']).read_bytes());need(chunk['next_offset']==chunk['offset']+chunk['bytes'] and chunk['bytes']==len(chunk['data'].encode()) and serial[chunk['offset']:chunk['next_offset']]==chunk['data'].encode(),'actual HTTP serial interval differs from ZIP guest bytes')
    web=load(directory.parent/'browser'/sid/'web-report.json')
    if row['unit_id']=='ir':
        inputs=[e for e in load(directory/'observation-index.json') if e['kind']=='input' and e['accepted']];posts=[e for e in web['posts'] if e['status']==200];cursor=0
        for event in inputs:
            while cursor<len(posts) and posts[cursor]['request']!={'id':event['id'],'values':event['values']}:cursor+=1
            need(cursor<len(posts),'custom IR input has no real browser POST in order');cursor+=1
    return {'status':'PASS','zip_before_stop':True,'raw_serial_zip_ranges':True,'retained_history_and_idle_http':True}


def write_checksums(output):
    files=sorted(p for p in output.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(output).as_posix()+'\n' for p in files))


def self_check(output):
    """Offline preparation + anti-relabel/patch negatives with hard API/process guards."""
    from contextlib import ExitStack
    from unittest.mock import patch
    import copy,socket,subprocess,urllib.request,builtins
    need(not output.exists(),'choose a fresh custom self-check output');output.mkdir(parents=True)
    calls=[]
    def deny(*a,**kw):calls.append('forbidden');raise AssertionError('offline custom check attempted API/process/builder')
    write_bytes=pathlib.Path.write_bytes;write_text=pathlib.Path.write_text
    def no_bin_bytes(path,data):need(path.suffix.lower() not in ('.bin','.elf'),'firmware binary write forbidden');return write_bytes(path,data)
    def no_bin_text(path,data,*a,**kw):need(path.suffix.lower() not in ('.bin','.elf'),'firmware binary write forbidden');return write_text(path,data,*a,**kw)
    checked=[]
    def rejects(label,fn):
        try:fn()
        except (RuntimeError,AssertionError,KeyError):checked.append(label)
        else:raise RuntimeError('negative was incorrectly accepted: '+label)
    original_files={p:sha(p.read_bytes()) for p in PROBE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    original_files.update({ROOT/'.work/unit-source-io-expanded-20261026/run_expanded_io.py':sha((ROOT/'.work/unit-source-io-expanded-20261026/run_expanded_io.py').read_bytes())})
    with ExitStack() as guards:
        for owner,name in ((urllib.request,'urlopen'),(socket,'socket'),(socket,'create_connection'),(subprocess,'Popen'),(subprocess,'run'),(subprocess,'call'),(subprocess,'check_output'),(os,'system'),(os,'popen')):guards.enter_context(patch.object(owner,name,deny))
        guards.enter_context(patch.object(pathlib.Path,'write_bytes',no_bin_bytes));guards.enter_context(patch.object(pathlib.Path,'write_text',no_bin_text))
        module=io_module();helper=patch_module()
        for owner,name in ((module,'prepare'),(module,'run_case'),(module,'build_control_image'),(module,'patch_ir_callback_copy'),(module,'patch_buzzer_callback_copy'),(helper,'prepare_one'),(helper,'build_control_image')):guards.enter_context(patch.object(owner,name,deny))
        import run_control_cases,run_service_cases
        guards.enter_context(patch.object(run_control_cases,'build_control_image',deny));guards.enter_context(patch.object(run_service_cases,'Client',deny))
        rows=prepare(output/'prepared',list(DEFAULT),11);prepared_check(output/'prepared');freeze=load(output/'prepared/tooling-source-freeze.json')
        for row in rows:
            d=output/'prepared'/row['unit_id'];request=load(d/'source-request.json')
            bad=copy.deepcopy(row);bad['firmware_flavor']='reference-app-with-original-unit-drivers';rejects(row['unit_id']+' original-flavor relabel',lambda:custom_identity(d,bad,request,freeze))
            bad=copy.deepcopy(row);bad['custom_driver_modification']=False;rejects(row['unit_id']+' original-driver bool relabel',lambda:custom_identity(d,bad,request,freeze))
            bad=copy.deepcopy(row);bad['custom_flags']={'ir_callback_root_patch':False,'buzzer_callback_arity_patch':False};rejects(row['unit_id']+' missing explicit patch flag',lambda:custom_identity(d,bad,request,freeze))
            bad_request=copy.deepcopy(request);name='io_drivers/'+row['unit_id']+'.py';bad_request['files'][name]=(PROBE/name).read_text();rejects(row['unit_id']+' original bytes in custom payload',lambda:custom_identity(d,row,bad_request,freeze))
            patch_bytes=(ROOT/PATCHES[row['unit_id']]).read_bytes();original=(PROBE/name).read_bytes();lines=original.splitlines(keepends=True);start=int(re.search(rb'@@ -(\d+),',patch_bytes).group(1))-1;lines[start]=b'# changed pinned context\n';rejects(row['unit_id']+' zero-fuzz context',lambda:helper.strict_patch(b''.join(lines),patch_bytes,name))
        for path in ('artifacts','firmware','firmware/import','artifact-uploads','artifact-uploads/x/chunks'):rejects('binary intake '+path,lambda path=path:source_only_intake(path,'POST'))
        anchor='IO_BUZZER_ONCE 2000 50';before=anchor+'\n';offset=len(anchor)
        need(module.buzzer_timer_window({'frequency-hz':2000,'duty-pct':0},before,before,offset),'original natural-zero pure vector rejected')
        for label,props,after in [('manual-off',{'frequency-hz':2000,'duty-pct':0},before+'IO_BUZZER_OFF\n'),('timer-done',{'frequency-hz':2000,'duty-pct':0},before+'IO_BUZZER_TIMER_DONE\n'),('still-active',{'frequency-hz':2000,'duty-pct':50},before),('wrong-frequency',{'frequency-hz':2400,'duty-pct':0},before)]:
            need(not module.buzzer_timer_window(props,before,after,offset),'natural-zero negative accepted: '+label);checked.append('original natural-zero '+label)
        # Synthetic parser vectors only: they are never stored as runtime evidence.
        sid='OFFLINE-PARSER-FIXTURE';prefix='/api/v1/sessions/'+sid;props={'frequency-hz':2000,'duty-pct':0}
        observation={'before_timer_done_and_manual_output':True,'before_serial_sha256':sha(before.encode()),'after_serial_sha256':sha(before.encode()),'serial_offset':offset,'qom':props}
        parser_fixture=[({'path':prefix+'/serial'},{'data':before}),({'path':prefix+'/units'},{'source':'live','units':[{'id':'external1','unit_id':'buzzer','source':'guest-qom','available':True,'properties':props}]}),({'path':prefix+'/serial'},{'data':before})]
        need(timer_http_proof(parser_fixture,sid,observation,module)['status']=='PASS','pure timer HTTP parser reference rejected')
        rejects('pure timer parser missing QOM',lambda:timer_http_proof([parser_fixture[0],parser_fixture[2]],sid,observation,module))
        rejects('pure timer parser QOM outside serial bracket',lambda:timer_http_proof([parser_fixture[1],parser_fixture[0],parser_fixture[2]],sid,observation,module))
        bad=copy.deepcopy(parser_fixture);bad[1][1]['units'][0]['properties']={'frequency-hz':2000,'duty-pct':50}
        rejects('pure timer parser active QOM',lambda:timer_http_proof(bad,sid,observation,module))
        need(all(sha(p.read_bytes())==expected for p,expected in original_files.items()),'original drivers or frozen IO9 harness modified')
        need(not any(p.suffix.lower() in ('.bin','.elf') for p in output.rglob('*') if p.is_file()),'offline self-check generated firmware binaries')
    need(not calls,'offline check reached forbidden entrypoints')
    report={'status':'PASS','custom_cases':list(DEFAULT),'api_calls':0,'process_calls':0,'builder_calls':0,'binary_files_written':0,'legacy_prepare_calls':0,'guest_execution':False,'hardware':'NOT RUN','original_drivers_and_io9_unchanged':True,'negative_checks':checked,'source_cas_sha256':{r['unit_id']:r['source_cas_sha256'] for r in rows},'driver_flavors':FLAVORS}
    save(output/'self-check.json',report);return report


def prepare(output,cases,generation=11):
    need(output.is_relative_to(HERE) and output!=HERE and not output.exists(),'choose a fresh output child of this custom harness')
    need(cases and set(cases)<=set(DEFAULT) and len(set(cases))==len(cases),'custom harness only accepts explicit IR/Buzzer cases')
    need(type(generation) is int and generation>0,'expected worker generation must be positive')
    output.mkdir(parents=True)
    module=io_module();helper=patch_module();drivers=module.driver_manifest();original_functions=function_hashes()
    host=next(x for x in load(ROOT/'platform/units/host-ports.json')['hosts'] if x['device_id']=='cores3')
    ports=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device']
    need(len(ports)==1 and ports[0]['pins']=={'yellow':2,'white':1},'CoreS3 confirmed main Grove wiring differs');port=ports[0]
    matrix=next(x for x in load(ROOT/'tests/uiflow2/device_matrix.json')['devices'] if x['id']=='cores3')
    tools=['tests/units/run_io_cases.py','tests/units/prepare_host_io.py','tests/units/run_service_cases.py','tests/units/run_control_cases.py','tests/units/run_sensor_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/tools/unit_runtime.py','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','platform/units/catalog.json','platform/units/runtime-profiles.json','platform/units/host-ports.json','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js']
    tools += list(PATCHES.values())+[str(pathlib.PurePosixPath(v).parent/'README.md') for v in PATCHES.values()]
    tools += [p.relative_to(ROOT).as_posix() for p in sorted(PROBE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
    freeze={}
    for name in sorted(set(tools)):
        raw=(ROOT/name).read_bytes();freeze[name]=sha(raw);target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    for name in ('run_custom_io.py','source_api_common.py'):
        raw=(HERE/name).read_bytes();freeze['HARNESS/'+name]=sha(raw);target=output/'source-snapshot/HARNESS'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    save(output/'tooling-source-freeze.json',freeze);save(output/'original-functions.json',original_functions);save(output/'pure-patch-helper-functions.json',patch_helper_hashes())
    rows=[]
    for case in cases:
        directory=output/case;directory.mkdir();files_dir=directory/'files';origins={}
        for source in sorted(PROBE.rglob('*.py')):
            name=source.relative_to(PROBE).as_posix();raw=source.read_bytes();target=files_dir/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            origins[name]={'repository_path':source.relative_to(ROOT).as_posix(),'size':len(raw),'sha256':sha(raw),'origin':'byte-exact-original-probe-or-driver'}
        # Only the repository's pure helper is used. No legacy prepare/build path.
        proof=helper.custom_driver(files_dir,case,ir_patch=case=='ir',buzzer_patch=case=='buzzer')
        need(proof is not None,'custom patch was not explicitly applied')
        original=(PROBE/proof['driver_path']).read_bytes();patched=(files_dir/proof['driver_path']).read_bytes();patch=(ROOT/proof['path']).read_bytes();reverse=reverse_patch(patch)
        recovered=helper.strict_patch(patched,reverse,proof['driver_path']);need(recovered==original,'reverse patch does not restore byte-exact official driver')
        evidence=directory/'patch-evidence';evidence.mkdir();(evidence/'original-driver.py.txt').write_bytes(original);(evidence/'forward.patch').write_bytes(patch);(evidence/'reverse.patch').write_bytes(reverse);(evidence/'restored-driver.py.txt').write_bytes(recovered)
        proof.update(native_module_modified=False,frozen_modules_modified=False,controller_modified=False,reverse_patch_sha256=sha(reverse),restored_driver_sha256=sha(recovered),reversible_byte_exact=True,helper='prepare_host_io.custom_driver + strict_patch (pure, no builder/process)')
        save(directory/'custom-driver-proof.json',proof)
        path=proof['driver_path'];origins[path].update(origin='explicit-custom-derived-copy',original_sha256=sha(original),sha256=sha(patched),size=len(patched),patch_path=proof['path'],patch_sha256=sha(patch))
        config=config_text(case,port['pins']);(files_dir/'probe_config.py').write_bytes(config.encode());origins['probe_config.py']={'origin':'generated-explicit-custom-config','sha256':sha(config.encode()),'size':len(config.encode())}
        files={p.relative_to(files_dir).as_posix():p.read_bytes().decode('utf-8') for p in sorted(files_dir.rglob('*.py'))}
        for name,text in files.items():ast.parse(text,filename=name)
        for name,record in drivers.items():need(sha(files['io_drivers/'+name].encode())==(proof['patched_driver_sha256'] if name==case+'.py' else record['sha256']),'unexpected guest driver change: '+name)
        request={'device_id':'cores3','files':files,'expected_base_sha256':BASE};wire=len(json.dumps(request,allow_nan=False).encode());need(wire<=1024*1024,'complete HTTP body exceeds 1 MiB')
        save(directory/'source-request.json',request);save(directory/'guest-source-freeze.json',origins);save(directory/'official-driver-proof.json',drivers)
        license_path=directory/'license-evidence/LICENSE.MIT';license_path.parent.mkdir();license_path.write_bytes((PROBE/'io_drivers/LICENSE.MIT').read_bytes())
        row={'schema_version':1,'unit_id':case,'device_id':'cores3','runtime':'qemu','port_id':port['id'],'attachments':module.attachments(case,port['id']),'expected_size':[int(v) for v in matrix['expected_size'].split('x')],'expected_runtime_sha256':RUNTIME,'expected_worker_generation':generation,'base_firmware_sha256':BASE,'source_cas_sha256':sha(canonical(files)),'http_json_body_bytes':wire,'probe_sha256':{name:sha(text.encode()) for name,text in files.items()},'official_drivers':drivers,'original_function_sha256':original_functions,'original_runner_sha256':freeze['tests/units/run_io_cases.py'],'pure_patch_helper_sha256':patch_helper_hashes(),'ready_marker':'IO_PROBE_READY '+case,'firmware_flavor':FLAVORS[case],'source_intake':'uiflow-source-api','source_context_commit':CONTEXT_COMMIT,'validation':'virtual-device validation','driver_validation':'custom-only','custom_driver_modification':True,'custom_driver_patch':proof,'custom_flags':{'ir_callback_root_patch':case=='ir','buzzer_callback_arity_patch':case=='buzzer'},'known_original_guest_gap':False,'published_original_driver_status':'SEPARATE_RESULT_NOT_INHERITED','status':'PREPARED_NO_API_OR_RUNTIME'}
        row['ir_callback_patch' if case=='ir' else 'buzzer_callback_patch']=proof
        save(directory/'prepared.json',row);rows.append(row)
        custom_identity(directory,row,request,freeze)
        print(case+': PREPARED '+row['firmware_flavor'],flush=True)
    save(output/'prepared.json',{'status':'PREPARED_NO_API_OR_RUNTIME','created_at':now(),'context_commit':CONTEXT_COMMIT,'default_cases':list(DEFAULT),'firmware_flavor':'EXPLICIT_CUSTOM_ONLY','cases':rows,'binary_build_or_upload':False,'functions_called_during_prepare':['driver_manifest (read-only)','attachments (pure topology)','prepare_host_io.custom_driver + strict_patch (pure bytes)']})
    save(output/'flavor-boundaries.json',{'custom_only':True,'cases':FLAVORS,'automatic_original_pass':False,'original_drivers_modified':False,'original_driver_evidence':'separate original runner and retained FAIL/REVIEW_REQUIRED results','scope':'Caller copies only; firmware frozen/native modules, controller, QEMU and original assertions unchanged.'})
    return rows

def state_valid(state,row):
    need(state['source']=='live' and state['contract_status']=='frozen','IO state is not live/frozen')
    need({u['id']:u['unit_id'] for u in state['units']}=={a['id']:a['unit_id'] for a in row['attachments']},'IO attachment tree differs')
    need(all(u['source']=='guest-qom' and u['available'] and not u.get('errors') for u in state['units']),'IO model unavailable')
def properties(state,instance='external1'):return next(u['properties'] for u in state['units'] if u['id']==instance)

def browser_check(report,row):
    need(report['session_id']==row['session_id'] and report['firmware_sha256']==row['firmware_sha256'] and not report['errors'],'browser session/errors differ')
    ids={a['id'] for a in row['attachments']};snapshots=[s for s in report['snapshots'] if s.get('session_state')=='running'];need(snapshots,'no actual running IO DOM snapshots')
    for snap in snapshots:
        need({u['instance'] for u in snap['units']}==ids,'DOM omits an IO attachment')
        for unit in snap['units']:
            need(unit['dom_matches_product_readback'] and unit['readback_matches_real_http_response'],'DOM/HTTP mismatch')
            props=unit['readback']['properties'];need(any(any(u['id']==unit['instance'] and u['properties']==props for u in e.get('response',{}).get('units',[])) for e in report['readbacks']+report['posts']),'DOM state lacks actual browser HTTP response')
            for key,value in props.items():
                cell=next((c for c in unit['values'] if c['field']==key),None);need(cell is not None,'DOM output absent: '+key)
                if key=='led-rgb' and cell.get('rgb'):
                    colors=value if isinstance(value,list) else [value];need(cell['rgb']==[f'LED[{i}] #{v:06x}' for i,v in enumerate(colors)],'DOM LED colors differ')
                else:
                    if isinstance(value,(int,float)) and not isinstance(value,bool):need(float(cell['text'])==value,'numeric DOM output differs: '+key)
                    else:
                        expected=json.dumps(value,separators=(',',':'),ensure_ascii=False) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                        need(cell['text']==expected,'DOM output differs: '+key)
    if row['unit_id'] not in ('fan','buzzer'):need(report['actions'] and report['posts'],'input IO case has no actual UI action/POST')
    if row['unit_id']=='hub':need({'env','ncir','tvoc'}<={p['request']['id'] for p in report['posts'] if p['status']==200},'HUB child lacks its own real UI POST')
    return {'running_snapshots':len(snapshots),'real_posts':len(report['posts']),'actions':len(report['actions'])}

def observed_type(module,directory):
    class RecordedObservations(module.Observations):
        def __init__(self,*values):super().__init__(*values);self.trace=[];self.last_input=None;self.phase='startup'
        def record(self,event):
            event={'at':now(),'event_id':len(self.trace),**event};self.trace.append(event);save(directory/'observation-index.json',self.trace);return event
        def serial_file(self,text,kind):
            name=f'observations/{len(self.trace):05d}-{kind}.txt';target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode());return name
        def wait(self,predicate,*,offset=0,timeout=60):
            # Parent evaluates the exact original predicate and retains its timeout.
            prior=self.trace[self.last_input]['before_cursor']['data'] if self.last_input is not None else None
            def original_and_fresh(text):
                return predicate(text) and (prior is None or (self.serial.startswith(prior) and len(self.serial)>len(prior)))
            value=super().wait(original_and_fresh,offset=offset,timeout=timeout);name=self.serial_file(self.serial,'serial')
            self.record({'kind':'wait-success','offset':offset,'serial_file':name,'serial_sha256':sha(self.serial.encode()),'input_event':self.last_input,'phase':self.phase});return value
        def marker(self,marker,*,offset=0,timeout=60):
            super().marker(marker,offset=offset,timeout=timeout);self.phase=marker
            self.record({'kind':'marker','marker':marker,'offset':offset,'serial_file':self.serial_file(self.serial,'marker'),'serial_sha256':sha(self.serial.encode()),'input_event':self.last_input})
        def state(self):
            value=super().state();name=f'observations/{len(self.trace):05d}-state.json';save(directory/name,value);self.record({'kind':'state','file':name,'phase':self.phase,'input_event':self.last_input});return value
        def input(self,values,instance='external1',*,via_ui=True):
            before=self.client.json(f'sessions/{self.session_id}/serial?offset=0&limit=262144',via_ui=False)
            event=self.record({'kind':'input','id':instance,'values':values,'via_ui':via_ui,'before_cursor':before,'accepted':None})
            try:value=super().input(values,instance,via_ui=via_ui)
            except Exception as error:event.update({'accepted':False,'error':str(error)});save(directory/'observation-index.json',self.trace);raise
            else:event['accepted']=True;self.last_input=event['event_id'];save(directory/'observation-index.json',self.trace);return value
        def qom(self,path,prop):
            value=super().qom(path,prop);self.record({'kind':'qom','path':path,'property':prop,'value':value});return value
    return RecordedObservations

def evidence_check(data,result,request,module):
    # Keep the original serial/frame/Unit/QOM/hash assertions unchanged.
    original=module.validate_evidence(data,result)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        manifest=json.loads(archive.read('manifest.json'));session=manifest['session'];proof=result['runtime_provenance'];source=common.source_provenance(load(pathlib.Path(result['case_directory'])/'firmware-response.json'),request)
        need('firmware/uiflow-source.json' in archive.namelist(),'source provenance absent from ZIP')
        need(session['firmware_provenance']==json.loads(archive.read('firmware/uiflow-source.json'))==source and session['source_artifacts'][0]==result['source_cas_sha256'],'ZIP source provenance/CAS differs')
        need(session['pid']==proof['observed_pid'] and session['worker']['worker_id']==proof['worker_id'] and session['worker']['generation']==proof['worker_generation'] and session['worker']['lease_active'],'ZIP direct PID/worker lease differs')
        state=json.loads(archive.read('units/state.json'));state_valid(state,result)
        contract=json.loads(archive.read('units/contract.json'));need(contract['source_hashes']==state['contract_hashes'],'ZIP frozen Unit source hashes differ')
        if result['unit_id'] in ('angle','light'):
            receipt=json.loads(archive.read('units/adc-calibration.json'));fixture_hash=result['tooling_source_sha256']['platform/units/fixtures/esp32s3-adc-calibration.json']
            need(receipt['status']=='applied' and receipt['fixture_sha256']==fixture_hash and receipt['hardware_validation'] is False and receipt['identity_or_security_fields_changed'] is False,'synthetic ADC fixture was not applied through the original bound path')
    return {'original':original,'source_cas_sha256':source['artifact_id'],'pid':session['pid']}

def run_case(client,args,row,module):
    case=row['unit_id'];directory=args.out_dir/case;request=load(directory/'source-request.json');custom_identity(directory,row,request,load(args.out_dir/'tooling-source-freeze.json'));result={**row,'case_directory':str(directory),'expected_runtime_sha256':args.expected_runtime_sha256,'tooling_source_sha256':load(args.out_dir/'tooling-source-freeze.json'),'status':'FAIL','checks':{},'injections':[],'required_markers':[],'started_at':now(),'hardware_validation':'NOT RUN'};sid=None;pid=None
    with common.HTTPRecorder(directory/'http'):
        try:
            need(function_hashes()==row['original_function_sha256'],'original IO assertion function changed since preparation')
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'live-unit-inventory.json',inventory);by_id={u['id']:u for u in inventory['units']};need(all(by_id[a['unit_id']]['runtime']['status'] in ('implemented','validated') for a in row['attachments']),'IO topology is not admitted')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware);result['source']=common.source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+row['source_cas_sha256'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact);need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS artifact differs')
            result['checks']['source_api_caller_bytes_cas_base_and_firmware']=True
            payload={'device_id':'cores3','runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ttl_seconds':900,'ready_marker':'IO_PROBE_READY','ready_timeout_seconds':180,'units':row['attachments']};save(directory/'session-request.json',payload)
            client.web_ui.call('prepare');session=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=session['session_id'];save(directory/'created-session.json',session);print(f'{case}: {row["firmware_flavor"]} source API visible session {sid}',flush=True)
            # Original ready wait is also preserved. It does not create a runtime itself.
            observed=observed_type(module,directory)(client,sid,result);observed.marker(row['ready_marker'],timeout=180)
            current=client.json(f'sessions/{sid}',via_ui=False);pid=current['pid'];save(directory/'ready-session.json',current)
            proof=client.web_ui.runtime_provenance(current,lambda:client.json(f'sessions/{sid}',via_ui=False));need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==args.expected_runtime_sha256 and proof['kind']=='direct-pid' and proof['worker_generation']==row['expected_worker_generation'] and proof['worker_id'],'direct runtime provenance differs')
            result['runtime_provenance']=proof;client.web_ui_sessions[sid]['provenance_done']=True;client._open_web_ui(sid)
            result['checks']['custom_driver_ready_and_runtime_verified']=True
            module.validate_io(observed,case)  # Unmodified complete original case assertions.
            need(EXPECTED[case]<=set(result['checks']) and all(result['checks'][k] is True for k in EXPECTED[case]),'original IO case assertions are missing')
            result['checks']['original_validate_io_completed_without_reduction']=True
            state=observed.state();state_valid(state,row);result['unit_state']=state;save(directory/'final-units.json',state)
            current=client.json(f'sessions/{sid}',via_ui=False);save(directory/'running-session.json',current);need(current['firmware_provenance']==result['source'] and current['source_artifacts'][0]==row['source_cas_sha256'],'running source identity differs')
            observed.wait(lambda text:True);(directory/'serial.txt').write_bytes(observed.serial.encode())
            frame=client.raw(f'sessions/{sid}/frame.png');(directory/'frame.png').write_bytes(frame);common.frame_valid(frame)
            client.web_ui.call('capture',session_id=sid,phase='observed-units',screenshot=True)
            need(function_hashes()==row['original_function_sha256'],'original IO assertions changed during execution')
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if sid:
                try:
                    current=client.json(f'sessions/{sid}',via_ui=False);pid=pid or current.get('pid');save(directory/'before-evidence-session.json',current)
                    serial=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False);save(directory/'final-serial-response.json',serial);(directory/'serial-final.txt').write_bytes(serial['data'].encode())
                    data=client.raw(f'sessions/{sid}/evidence');(directory/'evidence.zip').write_bytes(data);result['evidence_sha256']=sha(data);result['evidence_summary']=evidence_check(data,result,request,module);result['checks']['zip_before_stop_original_evidence_and_source_binding']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop_original_evidence_and_source_binding']=False
                try:
                    stopped=client.json(f'sessions/{sid}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped);history=client.json(f'sessions/{sid}',via_ui=False);save(directory/'retained-session.json',history)
                    need(stopped['state'] in ('stopped','failed') and history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and history['firmware_provenance']==result.get('source'),'IO history/Flash/provenance retention differs')
                    need(type(pid) is int and pid>0,'owned IO process PID absent');deadline=time.monotonic()+15
                    while not common.pid_gone(pid) and time.monotonic()<deadline:time.sleep(.1)
                    need(common.pid_gone(pid),'owned IO PID remains after stop');frame=client.raw(f'sessions/{sid}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(frame);common.frame_valid(frame)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0,'IO service/worker not idle after stop')
                    result['cleanup']={'pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0};result['checks']['history_pid_exit_flash_released_health_idle']=True
                except Exception as error:result['cleanup_error']=str(error);result['checks']['history_pid_exit_flash_released_health_idle']=False
                try:result['browser']=browser_check(load(args.out_dir/'browser'/sid/'web-report.json'),result);result['checks']['real_product_dom_and_http_match']=True
                except Exception as error:result['browser_error']=str(error);result['checks']['real_product_dom_and_http_match']=False
            protocol_pass=sid and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values())
            result['protocol_status']='PASS' if protocol_pass else 'FAIL';result['status']=('REVIEW_REQUIRED' if row['known_original_guest_gap'] else 'PASS') if protocol_pass else 'FAIL'
            result['original_risk_boundary']='PASS applies only to this explicit custom caller driver; the published original driver remains a separate test result.'
            result['finished_at']=now();save(directory/'result.json',result)
    print(f'{case}: {result["status"]} {result.get("error","")}',flush=True);return result


def verify_trace(directory,row,result,actual):
    events=load(directory/'observation-index.json');inputs={e['event_id']:e for e in events if e['kind']=='input'}
    def backed(value,suffix):return any(event['path'].endswith(suffix) and payload==value for event,payload in actual)
    for event in events:
        if event['kind'] in ('wait-success','marker'):
            data=(directory/event['serial_file']).read_bytes();text=data.decode();need(sha(data)==event['serial_sha256'],'original observation serial changed')
            need(any(e['path'].endswith('/serial') and p.get('data')==text for e,p in actual),'serial observation lacks real HTTP backing')
            need(0<=event['offset']<=len(text),'serial observation offset out of bounds')
            if event['kind']=='marker':need(re.search(r'(?m)^'+re.escape(event['marker'])+r'\r?$',text[event['offset']:]),'original marker absent from requested serial window')
        elif event['kind']=='state':need(backed(load(directory/event['file']),'/units'),'QOM state observation lacks actual HTTP backing')
        elif event['kind']=='input':need(backed(event['before_cursor'],'/serial'),'input cursor lacks actual HTTP backing')
        elif event['kind']=='qom':need(any(e['path'].endswith('/qom') and urllib.parse.parse_qs(e['query'])=={'path':[event['path']],'property':[event['property']]} and p.get('value')==event['value'] for e,p in actual),'QOM scalar lacks actual HTTP backing')
    # Require new UART bytes after every original accepted injection. The original
    # case-specific predicates remain the stronger semantic oracle, never API ACK.
    for event in inputs.values():
        if not event['accepted']:continue
        cursor=event['before_cursor'];candidates=[e for e in events if e['kind']=='wait-success' and e.get('input_event')==event['event_id']]
        need(candidates,'accepted input has no subsequent successful original guest wait')
        need(any((directory/e['serial_file']).read_bytes().decode().startswith(cursor['data']) and len((directory/e['serial_file']).read_bytes().decode())>len(cursor['data']) for e in candidates),'input lacks a fresh guest serial suffix')
    if row['unit_id']=='rs485':need(any(e['kind']=='input' and e['accepted'] is False and not e['via_ui'] and 'FIFO' in e.get('error','') for e in events),'original FIFO rejection trace absent')
    return {'events':len(events),'accepted_inputs':sum(e['accepted'] is True for e in inputs.values()),'rejected_inputs':sum(e['accepted'] is False for e in inputs.values())}


def semantic_trace(directory,row,result,module,actual):
    """Recheck real guest text and backed controller state for the two custom paths."""
    events=load(directory/'observation-index.json');accepted=[e for e in events if e['kind']=='input' and e['accepted']]
    def fresh(event):
        waits=[e for e in events if e['kind']=='wait-success' and e.get('input_event')==event['event_id']]
        need(waits,'IR input lacks original predicate completion');text=(directory/waits[-1]['serial_file']).read_bytes().decode();prior=event['before_cursor']['data']
        need(text.startswith(prior) and len(text)>len(prior),'IR input lacks fresh UART suffix');return text[len(prior):]
    def has(text,marker):return re.search(r'(?m)^'+re.escape(marker)+r'\r?$',text) is not None
    case=row['unit_id'];final=load(directory/'final-units.json');state_valid(final,row)
    serial=(directory/'serial-final.txt').read_bytes().decode();need(not any(x in serial for x in module.GUEST_FAILURES),'custom IO guest failed')
    states=[(e,properties(load(directory/e['file']))) for e in events if e['kind']=='state']
    if case=='ir':
        for marker in ('IO_IR_NATIVE 1','IO_IR_GC_COLLECTED 1 1','IO_IR_TX 18 52','IO_IR_NATIVE_PACKED 60690 52020'):
            need(has(serial,marker),'custom IR original initialization/GC/TX marker absent: '+marker)
        bad=module.nec_pulses(0x12,0x34);bad[0]=200
        vectors=[module.nec_pulses(0x12,0x34),bad,[9000,2250,562],module.nec_pulses(0x56,0x78)]
        need(len(accepted)==4 and all(e['via_ui'] and e['id']=='external1' and e['values']=={'rx-pulses-us':v} for e,v in zip(accepted,vectors)),'IR real Web injection sequence differs')
        need(has(fresh(accepted[0]),'IO_IR_RX 52 18 0 1') and has(fresh(accepted[0]),'IO_IR_NATIVE_PACKED 60690 52020'),'first fresh IR callback/packed TX absent')
        bad_window=fresh(accepted[1]);need(len(re.findall(r'(?m)^IO_IR_HEARTBEAT 1\r?$',bad_window))>=2 and not re.search(r'(?m)^IO_IR_RX ',bad_window),'malformed leader produced callback or lacks two fresh heartbeats')
        need(any(e.get('input_event')==accepted[1]['event_id'] and p['rx-pulses-us']==[] for e,p in states),'malformed IR leader was not consumed by controller')
        need(has(fresh(accepted[2]),'IO_IR_RX 52 18 -1 2'),'fresh NEC repeat did not preserve last address/command')
        need(has(fresh(accepted[3]),'IO_IR_RX 120 86 0 3'),'fresh rearmed NEC receiver absent')
        need(any(e['phase']=='IO_IR_TX 18 52' and module.check_nec_tx(p['tx-pulses-us'],raw16=True) for e,p in states),'official-wrapper raw16 TX controller pulses absent')
        need(any(e['phase']=='IO_IR_NATIVE_PACKED 60690 52020' and module.check_nec_tx(p['tx-pulses-us']) for e,p in states),'native uint16 packed NEC8 TX controller pulses absent')
        need(result['checks'].get('custom_callback_root_survives_forced_normal_gc') is True,'original forced-normal-GC custom assertion absent')
        return {'status':'PASS','unit_id':case,'accepted_inputs':4,'forced_normal_gc':True,'raw16_wrapper_and_native_packed_tx_separate':True}
    need(case=='buzzer' and not accepted,'Buzzer output path must not be host-input driven')
    for stage,freq,duty in ((0,1200,0),(1,2400,25),(2,3600,75)):
        marker=f'IO_BUZZER {stage} {freq} {duty}';need(has(serial,marker),'original Buzzer PWM stage absent')
        need(any(e['phase']==marker and abs(p['frequency-hz']-freq)<=max(2,freq*.02) and abs(p['duty-pct']-duty)<=.5 for e,p in states),'Buzzer PWM stage lacks backed LEDC output')
    need(has(serial,'IO_BUZZER_ONCE 2000 50') and has(serial,'IO_BUZZER_TIMER_DONE') and has(serial,'IO_BUZZER_OFF'),'original once/timer/off guest markers absent')
    need(any(e['phase']=='IO_BUZZER_ONCE 2000 50' and abs(p['frequency-hz']-2000)<=40 and abs(p['duty-pct']-50)<=.5 for e,p in states),'original once active LEDC output absent')
    need(properties(final)['output-transitions']>=3,'Buzzer LEDC transitions absent')
    natural=timer_http_proof(actual,result['session_id'],result['buzzer_timer_zero_observation'],module)
    return {'status':'PASS','unit_id':case,'accepted_inputs':0,'natural_timer_zero':natural,'output_transitions':properties(final)['output-transitions']}

def check_saved(output):
    prepared_check(output)
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==expected,'IO frozen artifact checksum differs: '+name)
    prepared=load(output/'prepared.json');freeze=load(output/'tooling-source-freeze.json');module=io_module();results=[]
    for name,expected in freeze.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==expected,'IO frozen source snapshot differs: '+name)
    for row in prepared['cases']:
        case=row['unit_id'];directory=output/case;result=load(directory/'result.json');request=load(directory/'source-request.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS' and result['protocol_status']=='PASS' and not row['known_original_guest_gap'],'custom IO case did not pass: '+case)
        custom_identity(directory,row,request,freeze)
        need(result['firmware_flavor']==row['firmware_flavor']==FLAVORS[case] and result['custom_driver_modification'] is True and result['custom_driver_patch']==row['custom_driver_patch'] and result['driver_validation']=='custom-only','custom result was relabeled or changed')
        need(EXPECTED[case]<=set(result['checks']) and all(result['checks'][k] is True for k in EXPECTED[case]),'original IO assertions absent')
        for name,text in request['files'].items():need((directory/'files'/name).read_bytes()==text.encode() and sha(text.encode())==row['probe_sha256'][name],'IO caller file bytes differ')
        common.source_provenance(firmware,request);need(firmware['source']==result['source'],'IO source provenance differs')
        proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need(proof==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'IO runtime proof differs')
        need(sha((directory/'evidence.zip').read_bytes())==result['evidence_sha256'],'IO ZIP bytes changed');evidence_check((directory/'evidence.zip').read_bytes(),result,request,module)
        actual=[]
        for event in load(directory/'http/index.json'):
            raw=(directory/'http'/event['response_file']).read_bytes();need(sha(raw)==event['response_sha256'] and len(raw)==event['response_size'],'IO raw HTTP response changed')
            if event['status']//100==2:
                try:actual.append((event,json.loads(raw)))
                except (ValueError,UnicodeDecodeError):pass
        need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and p==firmware and json.loads((directory/'http'/e['request_file']).read_bytes())==request for e,p in actual),'IO source API request/response not real or differs')
        payload=load(directory/'session-request.json');need(payload['uiflow_source_sha256']==row['source_cas_sha256'] and payload['firmware_id']==firmware['firmware_id'] and payload['device_id']==row['device_id'] and payload['runtime']==row['runtime'] and payload['units']==row['attachments'],'IO startup sourcepin/firmware/topology differs')
        need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and p.get('session_id')==result['session_id'] and json.loads((directory/'http'/e['request_file']).read_bytes())==payload for e,p in actual),'IO session creation has no actual HTTP backing')
        trace=verify_trace(directory,row,result,actual);semantic=semantic_trace(directory,row,result,module,actual);strict_http(directory,row,result,actual);browser_check(load(output/'browser'/result['session_id']/'web-report.json'),result)
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(history['flash_retained'] is False and health['capacity']['active_sessions']==0 and result['cleanup']['pid_gone'],'IO cleanup evidence incomplete');common.frame_valid((directory/'frame.png').read_bytes());common.frame_valid((directory/'history-frame.png').read_bytes())
        with zipfile.ZipFile(directory/'evidence.zip') as archive:
            contract=json.loads(archive.read('units/contract.json'))
            for name,value in contract['source_hashes'].items():need(freeze.get('platform/units/'+name)==value,'IO ZIP contract is not bound to frozen sources: '+name)
        results.append({'unit_id':case,'session_id':result['session_id'],'status':'PASS','firmware_flavor':row['firmware_flavor'],'driver_validation':'custom-only','trace':trace,'semantic':semantic})
    need(len({r['session_id'] for r in results})==len(results),'custom cases reused one guest session')
    return {'status':'PASS','cases':results,'scope':'Explicit custom IR/Buzzer caller copies only; original IO assertions + source API/PID/browser/QOM/ZIP/cleanup; original-driver and hardware PASS NOT CLAIMED'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=pathlib.Path,required=True);p.add_argument('--case',choices=(*DEFAULT,'custom2'),action='append');p.add_argument('--flavor',choices=('custom',),default='custom');p.add_argument('--execute',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--check-prepared',action='store_true');p.add_argument('--self-check',action='store_true');p.add_argument('--api-url',default='http://127.0.0.1:8787');p.add_argument('--expected-runtime-sha256',default=RUNTIME);p.add_argument('--expected-worker-generation',type=int,default=11);args=p.parse_args();args.out_dir=args.out_dir.resolve()
    need(args.out_dir.is_relative_to(HERE) and args.out_dir!=HERE,'custom IO outputs must stay in a fresh harness child');need(sum(bool(x) for x in (args.execute,args.prepare_only,args.check,args.check_prepared,args.self_check))<=1,'choose one offline/live mode')
    print('firmware flavor: EXPLICIT CUSTOM ONLY; original-driver PASS cannot be granted',flush=True)
    if args.self_check:print(json.dumps(self_check(args.out_dir),ensure_ascii=False,indent=2));return
    if args.check_prepared:print(json.dumps(prepared_check(args.out_dir),ensure_ascii=False,indent=2));return
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    cases=list(DEFAULT) if not args.case or 'custom2' in args.case else list(dict.fromkeys(args.case));rows=prepare(args.out_dir,cases,args.expected_worker_generation);prepared_check(args.out_dir)
    if not args.execute:print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','cases':cases,'flavors':{row['unit_id']:row['firmware_flavor'] for row in rows},'api_calls':0,'binary_build_or_upload':False}));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','real product Web bridge opt-in is required');need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'},'direct PID verification requires local service');need(args.expected_runtime_sha256==RUNTIME,'custom freeze requires the exact expected runtime SHA')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256;module=io_module()
    from run_service_cases import Client
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**options):source_only_intake(path,method,options.get('body'));return super().raw(path,method=method,**options)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with common.HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==health['capacity']['worker']['active_lease_count']==0 and health['capacity']['worker']['generation']==args.expected_worker_generation,'service must begin idle on expected worker generation')
        for row in rows:
            result=run_case(client,args,row,module);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close();save(args.out_dir/'batch-result.json',{'status':'PASS' if len(results)==len(rows) and all(r['status']=='PASS' for r in results) else 'FAIL','driver_validation':'custom-only','finished_at':now(),'cases':[{k:r.get(k) for k in ('unit_id','firmware_flavor','session_id','status','error','cleanup_error')} for r in results]});write_checksums(args.out_dir)
    need(len(results)==len(rows) and all(r['status']=='PASS' for r in results),'custom IO cases failed')
    try:replay=check_saved(args.out_dir)
    except Exception as error:
        batch=load(args.out_dir/'batch-result.json');batch.update(status='FAIL',offline_replay_error=type(error).__name__+': '+str(error));save(args.out_dir/'batch-result.json',batch);write_checksums(args.out_dir);raise
    save(args.out_dir/'acceptance-replay.json',replay);write_checksums(args.out_dir);print(json.dumps(replay,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
