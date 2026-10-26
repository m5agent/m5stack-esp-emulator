#!/usr/bin/env python3
"""Source-only API acceptance for CoreS3's remaining original IO probes.

Default preparation performs no API/process/BIN operation. --execute is owned
by root. Original Observations/validate_io/validate_evidence execute unchanged.
"""
from __future__ import annotations
import argparse,ast,hashlib,io,json,os,pathlib,re,sys,time,urllib.parse,zipfile
from datetime import datetime,timezone
import source_api_common as common
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];PROBE=ROOT/'tests/units/io_probe'
BASE=common.BASE;RUNTIME=common.RUNTIME;CONTEXT_COMMIT='5cf58191af2938ecd86f991455b47145872fb08e'
DEFAULT=('pir','dual-button','limit','key','angle','light','fan','rs485','hub')
KNOWN_GAP=('buzzer','ir');ALL=(*DEFAULT,*KNOWN_GAP)
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

def prepare(output,cases):
    need(output.is_relative_to(HERE) and output!=HERE and not output.exists(),'choose a fresh output child of this harness');output.mkdir(parents=True)
    module=io_module();drivers=module.driver_manifest();original_functions=function_hashes()
    ports=load(ROOT/'platform/units/host-ports.json')['hosts'];host=next(x for x in ports if x['device_id']=='cores3');ports=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device'];need(len(ports)==1,'CoreS3 main Grove port ambiguous');port=ports[0]
    matrix=next(x for x in load(ROOT/'tests/uiflow2/device_matrix.json')['devices'] if x['id']=='cores3')
    tools=['tests/units/run_io_cases.py','tests/units/run_service_cases.py','tests/units/run_control_cases.py','tests/units/run_sensor_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/tools/unit_runtime.py','platform/tools/unit_adc_fixture.py','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','platform/units/catalog.json','platform/units/runtime-profiles.json','platform/units/host-ports.json','platform/units/fixtures/esp32s3-adc-calibration.json','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js','tests/units/io_probe/io_drivers/source-manifest.json']
    freeze={}
    for name in tools:
        data=(ROOT/name).read_bytes();freeze[name]=sha(data);target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    for name in ('run_expanded_io.py','source_api_common.py'):
        data=(HERE/name).read_bytes();freeze['HARNESS/'+name]=sha(data);target=output/'source-snapshot/HARNESS'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    save(output/'tooling-source-freeze.json',freeze);save(output/'original-functions.json',original_functions)
    rows=[]
    for case in cases:
        directory=output/case;directory.mkdir();files={};origins={}
        for source in sorted(PROBE.rglob('*.py')):
            relative=source.relative_to(PROBE).as_posix();data=source.read_bytes();text=data.decode('utf-8');need(text.encode()==data,'guest source UTF-8 changed');ast.parse(text,filename=relative)
            files[relative]=text;origins[relative]={'repository_path':source.relative_to(ROOT).as_posix(),'size':len(data),'sha256':sha(data),'origin':'byte-exact-original-probe-or-driver'}
        config=f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nIR_CALLBACK_ROOT_PATCH = False\n"
        files['probe_config.py']=config;origins['probe_config.py']={'origin':'generated-exact-original-prepare-config','sha256':sha(config.encode()),'size':len(config.encode())}
        # Every driver manifest entry is checked against the exact request bytes.
        for name,record in drivers.items():need(sha(files['io_drivers/'+name].encode())==record['sha256'],'official driver in source request changed: '+name)
        for name,text in files.items():target=directory/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode())
        request={'device_id':'cores3','files':dict(sorted(files.items())),'expected_base_sha256':BASE};save(directory/'source-request.json',request);save(directory/'guest-source-freeze.json',origins);save(directory/'official-driver-proof.json',drivers)
        target=directory/'license-evidence/LICENSE.MIT';target.parent.mkdir(parents=True);target.write_bytes((PROBE/'io_drivers/LICENSE.MIT').read_bytes())
        row={'schema_version':1,'unit_id':case,'device_id':'cores3','runtime':'qemu','port_id':port['id'],'attachments':module.attachments(case,port['id']),'expected_size':[int(v) for v in matrix['expected_size'].split('x')],'expected_runtime_sha256':RUNTIME,'base_firmware_sha256':BASE,'source_cas_sha256':sha(canonical(request['files'])),'probe_sha256':{name:sha(text.encode()) for name,text in files.items()},'official_drivers':drivers,'original_function_sha256':original_functions,'original_runner_sha256':freeze['tests/units/run_io_cases.py'],'ready_marker':'IO_PROBE_READY '+case,'firmware_flavor':'reference-app-with-original-unit-drivers','source_intake':'uiflow-source-api','source_context_commit':CONTEXT_COMMIT,'custom_driver_modification':False,'known_original_guest_gap':case in KNOWN_GAP,'status':'PREPARED_NO_API_OR_RUNTIME'}
        save(directory/'prepared.json',row);rows.append(row)
    save(output/'prepared.json',{'status':'PREPARED_NO_API_OR_RUNTIME','created_at':now(),'context_commit':CONTEXT_COMMIT,'default_cases':list(DEFAULT),'cases':rows,'binary_build_or_upload':False,'functions_called_during_prepare':['driver_manifest (read-only bytes)','attachments (pure topology)']})
    save(output/'flavor-boundaries.json',{'original':{'default_cases':list(DEFAULT),'known_guest_gap_controls':list(KNOWN_GAP),'automatic_driver_changes':False,'automatic_original_pass':False},'custom':{'status':'NOT PREPARED IN DEFAULT FREEZE','requires':'Separate explicitly selected IR callback-root or Buzzer callback-arity guest-copy patch, exact patch/original/derived hashes and unchanged original assertions. No automatic patch is allowed.','patches':['patches/uiflow2-unit-ir/0001-root-native-receive-callback.patch','patches/uiflow2-unit-buzzer/0001-accept-soft-timer-callback.patch']}})
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
    if row['unit_id']!='fan':need(report['actions'] and report['posts'],'input IO case has no actual UI action/POST')
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
    case=row['unit_id'];directory=args.out_dir/case;request=load(directory/'source-request.json');result={**row,'case_directory':str(directory),'expected_runtime_sha256':args.expected_runtime_sha256,'tooling_source_sha256':load(args.out_dir/'tooling-source-freeze.json'),'status':'FAIL','checks':{},'injections':[],'required_markers':[],'started_at':now(),'hardware_validation':'NOT RUN'};sid=None;pid=None
    with common.HTTPRecorder(directory/'http'):
        try:
            need(function_hashes()==row['original_function_sha256'],'original IO assertion function changed since preparation')
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'live-unit-inventory.json',inventory);by_id={u['id']:u for u in inventory['units']};need(all(by_id[a['unit_id']]['runtime']['status'] in ('implemented','validated') for a in row['attachments']),'IO topology is not admitted')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware);result['source']=common.source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+row['source_cas_sha256'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact);need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS artifact differs')
            result['checks']['source_api_caller_bytes_cas_base_and_firmware']=True
            payload={'device_id':'cores3','runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ttl_seconds':900,'ready_marker':'IO_PROBE_READY','ready_timeout_seconds':180,'units':row['attachments']};save(directory/'session-request.json',payload)
            client.web_ui.call('prepare');session=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=session['session_id'];save(directory/'created-session.json',session);print(f'{case}: source API visible session {sid}',flush=True)
            # Original ready wait is also preserved. It does not create a runtime itself.
            observed=observed_type(module,directory)(client,sid,result);observed.marker(row['ready_marker'],timeout=180)
            current=client.json(f'sessions/{sid}',via_ui=False);pid=current['pid'];save(directory/'ready-session.json',current)
            proof=client.web_ui.runtime_provenance(current,lambda:client.json(f'sessions/{sid}',via_ui=False));need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==args.expected_runtime_sha256 and type(proof['worker_generation']) is int and proof['worker_id'],'direct runtime provenance differs')
            result['runtime_provenance']=proof;client.web_ui_sessions[sid]['provenance_done']=True;client._open_web_ui(sid)
            result['checks']['original_driver_ready_and_runtime_verified']=True
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
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'IO service not idle after stop')
                    result['cleanup']={'pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0};result['checks']['history_pid_exit_flash_released_health_idle']=True
                except Exception as error:result['cleanup_error']=str(error);result['checks']['history_pid_exit_flash_released_health_idle']=False
                try:result['browser']=browser_check(load(args.out_dir/'browser'/sid/'web-report.json'),result);result['checks']['real_product_dom_and_http_match']=True
                except Exception as error:result['browser_error']=str(error);result['checks']['real_product_dom_and_http_match']=False
            protocol_pass=sid and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values())
            result['protocol_status']='PASS' if protocol_pass else 'FAIL';result['status']=('REVIEW_REQUIRED' if row['known_original_guest_gap'] else 'PASS') if protocol_pass else 'FAIL'
            result['original_risk_boundary']='Original IR/Buzzer guest known gap remains OPEN; an unexpected success needs independent review and never inherits custom-driver evidence.' if row['known_original_guest_gap'] else None
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


def semantic_trace(directory,row,result,module):
    """Independently recheck guest text + actual QOM; never treats HTTP ACK as consumption."""
    events=load(directory/'observation-index.json');accepted=[e for e in events if e['kind']=='input' and e['accepted']]
    def fresh(event):
        waits=[e for e in events if e['kind']=='wait-success' and e.get('input_event')==event['event_id']]
        need(waits,'input has no original predicate completion');text=(directory/waits[-1]['serial_file']).read_bytes().decode();prior=event['before_cursor']['data']
        need(text.startswith(prior) and len(text)>len(prior),'input has no fresh UART suffix');return text[len(prior):]
    def has(text,marker):return re.search(r'(?m)^'+re.escape(marker)+r'\r?$',text) is not None
    case=row['unit_id'];final=load(directory/'final-units.json');state_valid(final,row)
    serial=(directory/'serial-final.txt').read_bytes().decode();need(not any(x in serial for x in module.GUEST_FAILURES),'IO guest failed')
    if case=='pir':
        expected=['IO_PIR_CALLBACK 1 1','IO_PIR_CALLBACK 0 1','IO_PIR 1 1 1 1','IO_PIR_DISABLED_DONE 1 1','IO_PIR_CALLBACK 1 2','IO_PIR_CALLBACK 0 2']
        need(len(accepted)==6 and [e['values'] for e in accepted]==[{'motion':x} for x in (True,False,True,False,True,False)],'PIR input sequence differs')
        for event,marker in zip(accepted,expected):need(has(fresh(event),marker),'fresh PIR state/callback absent')
        need('IO_PIR_CALLBACK' not in fresh(accepted[2])+fresh(accepted[3]) and has(fresh(accepted[3]),'IO_PIR_REENABLED'),'PIR disabled IRQ produced callback or failed to rearm')
    elif case=='dual-button':
        need(len(accepted)==4,'Dual button input count differs')
        for i,(raw,clicks) in enumerate((((0,1),None),((1,1),(1,0)),((1,0),None),((1,1),(1,1)))):
            text=fresh(accepted[i]);need(re.search(r'(?m)^IO_DUAL %d %d ' % raw,text),'fresh dual raw GPIO absent')
            if clicks:need(has(text,'IO_DUAL_CLICK %d %d'%clicks),'fresh dual click absent')
    elif case=='limit':
        need(len(accepted)==4 and has(serial,'IO_LIMIT_BUTTON_ALIAS 1'),'LIMIT alias/input count differs')
        for event,(raw,count) in zip(accepted,((0,0),(1,1),(0,2),(1,3))):need(has(fresh(event),f'IO_LIMIT {raw} {count}'),'fresh LIMIT edge counter absent')
        need(has(fresh(accepted[-1]),'IO_LIMIT_COUNT_RESET 0'),'LIMIT reset absent')
    elif case=='key':
        need(len(accepted)==2,'Key input count differs')
        for event,(raw,color) in zip(accepted,((0,0x123456),(1,0x2468AC))):
            need(has(fresh(event),f'IO_KEY_RAW {raw}'),'fresh key raw GPIO absent')
            states=[load(directory/e['file']) for e in events if e['kind']=='state' and e.get('input_event')==event['event_id']]
            need(any(properties(st)['led-rgb']==color for st in states),'Key guest RGB frame absent')
        need(properties(final)['led-frames']>=3,'Key native RMT frames absent')
    elif case in ('angle','light'):
        voltages=(0,1250,2500) if case=='angle' else (310,1550,3100);need(len(accepted)==3,'ADC vector count differs');uv=[]
        for i,(event,voltage) in enumerate(zip(accepted,voltages)):
            field='voltage-mv' if case=='angle' else 'analog-mv';need(event['values'][field]==voltage,'ADC vector differs');expected=module.expected_ideal_input(voltage,attenuation=3,adc_unit=1);text=fresh(event)
            if case=='angle':
                readings=[(int(a),float(b),int(c)) for a,b,c in re.findall(r'(?m)^IO_ANGLE (\d+) ([\d.]+) (\d+)\r?$',text)]
                candidates=[r for r in readings if r[0]==expected['read_u16'] and r[2]==expected['read_uv'] and abs(r[1]-expected['read_uv']/1000000)<=.000002]
                need(candidates,'fresh calibrated ADC read_uv does not match unchanged curve oracle');uv.append(candidates[-1][1])
            else:
                need(event['values']['digital-level'] is bool(i%2),'Light digital vector differs')
                need(any(int(a)==expected['read_u16'] and int(b)==i%2 for a,b in re.findall(r'(?m)^IO_LIGHT (\d+) (\d+)\r?$',text)),'fresh Light ADC/digital reading absent')
        need(properties(final)['adc-samples']>=3,'SAR sample counter absent')
        if uv:need(uv[0]<uv[1]<uv[2],'calibrated voltages are not increasing')
    elif case=='fan':
        for stage,freq,setting in ((0,1000,0),(1,1000,25),(2,1500,100)):
            marker=f'IO_FAN {stage} {freq} {setting}';need(has(serial,marker),'Fan guest stage absent');duty=round((setting-1)*953/99+70)/1023*100 if setting else 0
            states=[properties(load(directory/e['file'])) for e in events if e['kind']=='state' and e['phase']==marker]
            need(any(abs(p['frequency-hz']-freq)<=max(2,freq*.02) and abs(p['duty-pct']-duty)<=.5 for p in states),'Fan LEDC frequency/duty not observed')
        need(properties(final)['output-transitions']>=3,'Fan LEDC transitions absent')
    elif case=='rs485':
        need(len(accepted)==1,'RS485 accepted RX count differs');incoming=b'peer-to-guest\0\x7f\xff';initial=b'guest-to-peer\0\x7f\xff';reply=b'echo:'+incoming
        need(accepted[0]['values']=={'rx-hex':incoming.hex()},'RS485 binary RX differs');text=fresh(accepted[0])
        need(has(text,'IO_RS485_RX '+incoming.hex()) and has(text,f'IO_RS485_ECHO {len(reply)} {reply.hex()}'),'fresh UART binary RX/echo absent')
        p=properties(final);need(p['tx-hex']==(initial+reply).hex() and p['read-bytes']==len(incoming) and p['written-bytes']==len(initial+reply),'UART byte/counter evidence differs')
    elif case=='hub':
        need(has(serial,'IO_HUB_SCAN 68 88 90 112') and len(accepted)==3,'passive HUB scan or injection count differs');current={k:dict(v) for k,v in module.HUB_INITIAL.items()}
        for event,instance in zip(accepted,('env','ncir','tvoc')):
            need(event['id']==instance,'HUB child injection order differs');current[instance].update(event['values']);expected=[*current['env'].values(),*current['ncir'].values(),*current['tvoc'].values()]
            vectors=[[float(x) for x in line.split()] for line in re.findall(r'(?m)^IO_HUB ([^\r\n]+)',fresh(event))]
            need(any(len(v)==7 and all(abs(a-b)<=t for a,b,t in zip(v,expected,(.2,.2,1.5,.021,.021,0,0))) for v in vectors),'fresh HUB multi-driver vector absent')
        for instance in current:need(all(properties(final,instance)[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events')),'HUB leaf independent counters absent')
    return {'status':'PASS','unit_id':case,'accepted_inputs':len(accepted)}

def check_saved(output):
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==expected,'IO frozen artifact checksum differs: '+name)
    prepared=load(output/'prepared.json');freeze=load(output/'tooling-source-freeze.json');module=io_module();results=[]
    for name,expected in freeze.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==expected,'IO frozen source snapshot differs: '+name)
    for row in prepared['cases']:
        case=row['unit_id'];directory=output/case;result=load(directory/'result.json');request=load(directory/'source-request.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS' and not row['known_original_guest_gap'],'IO case is not an independently eligible PASS: '+case)
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
        payload=load(directory/'session-request.json');need(payload['uiflow_source_sha256']==row['source_cas_sha256'] and payload['units']==row['attachments'],'IO startup pin/topology differs')
        need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and p.get('session_id')==result['session_id'] and json.loads((directory/'http'/e['request_file']).read_bytes())==payload for e,p in actual),'IO session creation has no actual HTTP backing')
        trace=verify_trace(directory,row,result,actual);semantic=semantic_trace(directory,row,result,module);browser_check(load(output/'browser'/result['session_id']/'web-report.json'),result)
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(history['flash_retained'] is False and health['capacity']['active_sessions']==0 and result['cleanup']['pid_gone'],'IO cleanup evidence incomplete');common.frame_valid((directory/'frame.png').read_bytes());common.frame_valid((directory/'history-frame.png').read_bytes())
        with zipfile.ZipFile(directory/'evidence.zip') as archive:
            contract=json.loads(archive.read('units/contract.json'))
            for name,value in contract['source_hashes'].items():need(freeze.get('platform/units/'+name)==value,'IO ZIP contract is not bound to frozen sources: '+name)
        results.append({'unit_id':case,'session_id':result['session_id'],'status':'PASS','trace':trace,'semantic':semantic})
    return {'status':'PASS','cases':results,'scope':'Original IO predicates + source API/PID/browser/QOM/evidence/cleanup; hardware NOT RUN'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=pathlib.Path,required=True);p.add_argument('--case',choices=(*ALL,'default'),action='append');p.add_argument('--flavor',choices=('original','custom'),default='original');p.add_argument('--execute',action='store_true');p.add_argument('--prepare-only',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--api-url',default='http://127.0.0.1:8787');p.add_argument('--expected-runtime-sha256',default=RUNTIME);args=p.parse_args();args.out_dir=args.out_dir.resolve();need(args.out_dir.is_relative_to(HERE) and args.out_dir!=HERE,'IO outputs must stay in a fresh harness child');need(not(args.execute and(args.prepare_only or args.check)),'choose offline or live mode')
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    need(args.flavor=='original','Custom IR/Buzzer is explicitly NOT PREPARED in this default freeze; no automatic guest patch is permitted')
    cases=list(DEFAULT) if not args.case or 'default' in args.case else list(dict.fromkeys(args.case));rows=prepare(args.out_dir,cases)
    if not args.execute:print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','cases':cases,'official_drivers':len(rows[0]['official_drivers'])}));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','real product Web bridge opt-in is required');need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'},'direct PID verification requires local service');need(re.fullmatch('[0-9a-f]{64}',args.expected_runtime_sha256),'runtime SHA must be exact')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256;module=io_module()
    from run_service_cases import Client
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**options):need(not(method in ('POST','PUT') and path.split('?')[0] in ('artifacts','firmware')),'binary artifact/alternate firmware intake is forbidden');return super().raw(path,method=method,**options)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with common.HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'service must begin idle')
        for row in rows:
            result=run_case(client,args,row,module);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close();save(args.out_dir/'batch-result.json',{'status':'PASS' if len(results)==len(rows) and all(r['status']=='PASS' for r in results) else 'FAIL_OR_REVIEW_REQUIRED','finished_at':now(),'cases':[{k:r.get(k) for k in ('unit_id','session_id','status','error','cleanup_error')} for r in results]});files=sorted(p for p in args.out_dir.rglob('*') if p.is_file() and p.name!='SHA256SUMS');(args.out_dir/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(args.out_dir).as_posix()+'\n' for p in files))
    need(len(results)==len(rows) and all(r['status']=='PASS' for r in results),'IO cases failed or original known-gap controls need review');print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
