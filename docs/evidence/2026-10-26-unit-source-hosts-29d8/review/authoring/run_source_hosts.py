#!/usr/bin/env python3
"""Prepare exact host-probe source requests; execution is an explicit root action.

Default and --prepare-only perform zero API/browser/process/BIN operations.
--execute always makes a fresh preparation bound to the root-supplied current
commit after root's commit/fetch. --check is saved-evidence replay only.
"""
from __future__ import annotations
import argparse,ast,io,json,os,pathlib,re,sys,time,urllib.parse,zipfile
import source_api_common as common
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];PROBE=ROOT/'tests/units/host_probe'
RUNTIME='29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
DEVICES=('atoms3r','sticks3','stopwatch');CASES=('button','relay','env-iii')
need=common.need;sha=common.sha;canonical=common.canonical;save=common.save;load=common.load;now=common.now
EXPECTED={'button':{'explicit_guest_canvas_geometry','host_gpio_edges_and_original_button_irq_counter','onboard_identity_after_external_operations'},'relay':{'explicit_guest_canvas_geometry','host_relay_guest_output_readback','onboard_identity_after_external_operations'},'env-iii':{'explicit_guest_canvas_geometry','external_env_two_inputs_and_onboard_i2c_isolation','onboard_identity_after_external_operations'}}

def git_head():
    """Read checkout identity without spawning git or changing refs."""
    location=ROOT/'.git'
    if location.is_file():
        line=location.read_text().strip();need(line.startswith('gitdir: '),'unsupported .git pointer');gitdir=(ROOT/line[8:]).resolve()
    else:gitdir=location
    head=(gitdir/'HEAD').read_text().strip()
    if not head.startswith('ref: '):value=head
    else:
        reference=head[5:];need(reference.startswith('refs/') and '..' not in reference,'invalid Git HEAD ref')
        common_dir=(gitdir/(gitdir/'commondir').read_text().strip()).resolve() if (gitdir/'commondir').exists() else gitdir
        candidates=[gitdir/reference,common_dir/reference];value=next((p.read_text().strip() for p in candidates if p.exists()),None)
        if value is None:
            for p in (gitdir/'packed-refs',common_dir/'packed-refs'):
                if p.exists():
                    value=next((line.split()[0] for line in p.read_text().splitlines() if line and not line.startswith(('#','^')) and line.split()[-1]==reference),None)
                    if value:break
    need(re.fullmatch('[0-9a-f]{40}',value or ''),'cannot resolve exact checkout commit');return value

def original_module():
    sys.path[:0]=[str(ROOT/'tests/units'),str(ROOT/'platform/tools')]
    import run_host_cases
    need(pathlib.Path(run_host_cases.__file__).resolve()==ROOT/'tests/units/run_host_cases.py','wrong original host module')
    need(tuple(run_host_cases.HOSTS)==DEVICES,'host inventory drift requires review');return run_host_cases

def original_functions():
    records={}
    for name,selected in [('tests/units/run_host_cases.py',('reference_layout','validate_case','validate_bundle','HOSTS')),('tests/units/run_io_cases.py',('Observations',))]:
        text=(ROOT/name).read_text();tree=ast.parse(text)
        for node in tree.body:
            key=node.name if isinstance(node,(ast.FunctionDef,ast.ClassDef)) else node.targets[0].id if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) else None
            if key in selected:records[name+'::'+key]=sha(ast.get_source_segment(text,node).encode())
    need(len(records)==5,'missing exact original host contracts');return records

def frame(data,row):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load();need(image.format=='PNG' and list(image.size)==row['expected_size'],'native host PNG geometry differs')
        need(image.convert('RGB').getcolors(maxcolors=1) is None,'native host application frame is single-color')
    return {'sha256':sha(data),'size_bytes':len(data),'native_size':row['expected_size']}

def prepare(output,devices,cases,source_context_commit=None):
    need(output.is_relative_to(HERE) and output!=HERE and not output.exists(),'choose a fresh child output; old evidence is immutable')
    module=original_module();head=git_head()
    if source_context_commit is not None:need(source_context_commit==head,'source context must match current post-sync checkout commit')
    output.mkdir(parents=True);functions=original_functions()
    tool_names=['tests/units/run_host_cases.py','tests/units/run_io_cases.py','tests/units/run_service_cases.py','tests/units/run_control_cases.py','tests/units/run_sensor_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/tools/firmware_analysis.py','platform/tools/unit_runtime.py','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','platform/units/catalog.json','platform/units/runtime-profiles.json','platform/units/host-ports.json','tests/uiflow2/device_matrix.json','platform/web/sessions.js','platform/web/sessions.html','platform/web/unit-panel.js','platform/web/unit-panel.css','platform/web/unit-visual-mappings.js','platform/web/unit-annotations.js','platform/web/unit-assembly-layout.js','platform/web/model-shell.js','platform/web/device-shell-factory.js']
    frozen={}
    for name in tool_names:
        data=(ROOT/name).read_bytes();frozen[name]=sha(data);p=output/'source-snapshot'/(name+'.txt');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    for name in ('run_source_hosts.py','source_api_common.py'):
        data=(HERE/name).read_bytes();frozen['HARNESS/'+name]=sha(data);p=output/'source-snapshot/HARNESS'/(name+'.txt');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    save(output/'tooling-source-freeze.json',frozen);save(output/'original-functions.json',functions)
    matrix=load(ROOT/'tests/uiflow2/device_matrix.json')['devices'];ports=load(ROOT/'platform/units/host-ports.json')['hosts'];rows=[]
    for device_id in devices:
        device=next(d for d in matrix if d['id']==device_id);need(device['backend']=='qemu-esp32s3','host backend changed')
        profile={**module.HOSTS[device_id],'log_tx':43,'log_rx':44,'internal_controller':1,'external_controller':0};profile.setdefault('canvas_size',profile['size'])
        need(profile['size']==[int(x) for x in device['expected_size'].split('x')],'host profile/matrix frame mismatch')
        host=next(h for h in ports if h['device_id']==device_id);choices=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device'];need(len(choices)==1,'ambiguous physical main Grove');port=choices[0]
        base=ROOT/device['base'];layout=module.reference_layout(base,int(device['flash_size'],0));base_sha=sha(base.read_bytes());need(base_sha==layout['base_firmware_sha256'],'reference read changed')
        for case in cases:
            directory=output/device_id/case;directory.mkdir(parents=True);files={};origins={}
            for source in sorted(PROBE.rglob('*.py')):
                name=source.relative_to(PROBE).as_posix();data=source.read_bytes();text=data.decode();need(text.encode()==data,'host probe encoding changed');ast.parse(text,filename=name);files[name]=text;origins[name]={'repository_path':source.relative_to(ROOT).as_posix(),'sha256':sha(data),'size':len(data),'origin':'byte-exact-original-host-probe'}
            need(set(files)=={'main.py','host_program.py','probe_logging.py','boot.py'},'unexpected probe source files require review')
            # Exact dictionary and ordering from run_host_cases.prepare; never call its BIN builder.
            config={'CASE':case,'DEVICE_ID':device_id,'WHITE':port['pins']['white'],'YELLOW':port['pins']['yellow'],'ROTATION':profile['rotation'],'FRAME_WIDTH':profile['size'][0],'FRAME_HEIGHT':profile['size'][1],'CANVAS_WIDTH':profile['canvas_size'][0],'CANVAS_HEIGHT':profile['canvas_size'][1],'TEXT_X':profile['text'][0],'TEXT_Y':profile['text'][1],'TEXT_WIDTH':profile['text'][2],**{name.upper():profile[name] for name in ('internal_sda','internal_scl','internal_controller','external_controller','log_tx','log_rx')}}
            files['probe_config.py']=''.join(f'{key} = {value!r}\n' for key,value in config.items());origins['probe_config.py']={'origin':'generated-exact-original-host-config','sha256':sha(files['probe_config.py'].encode()),'size':len(files['probe_config.py'].encode())}
            files=dict(sorted(files.items()));request={'device_id':device_id,'files':files,'expected_base_sha256':base_sha};need(len(canonical(request))<=1048576,'source HTTP body too large')
            for name,text in files.items():p=directory/'files'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode())
            row={'schema_version':1,'device_id':device_id,'unit_id':case,'runtime':'qemu','source_intake':'uiflow-source-api','source_context_commit':head,'source_context_stage':'ROOT_SUPPLIED_POST_SYNC' if source_context_commit else 'AUTHORING_ONLY_REPREPARE_AFTER_ROOT_SYNC','host_profile':profile,'port_id':port['id'],'attachments':[{'id':'external1','unit_id':case,'port_id':port['id']}],'official_host_evidence':port['evidence'],'reference_layout':layout,'base_firmware_sha256':base_sha,'reference_file':device['base'],'flash_size':int(device['flash_size'],0),'expected_size':profile['size'],'expected_runtime_sha256':RUNTIME,'source_cas_sha256':sha(canonical(files)),'probe_sha256':{name:sha(text.encode()) for name,text in files.items()},'original_function_sha256':functions,'driver_source':'Unchanged reference-firmware-bundled unit/hardware/driver modules; not uploaded, patched or independently rebuilt','uploaded_driver_files':[],'adc_fixture':'NOT USED','host_admission_modified':False,'ready_marker':f'HOST_PROBE_READY {device_id} {case}','status':'PREPARED_NO_API_OR_RUNTIME'}
            save(directory/'source-request.json',request);save(directory/'guest-source-freeze.json',origins);save(directory/'prepared.json',row);rows.append(row)
    save(output/'prepared.json',{'status':'PREPARED_NO_API_OR_RUNTIME','created_at':now(),'source_context_commit':head,'source_context_stage':'ROOT_SUPPLIED_POST_SYNC' if source_context_commit else 'AUTHORING_ONLY_REPREPARE_AFTER_ROOT_SYNC','fresh_prepare_required_after_root_commit_and_fetch':source_context_commit is None,'cases':rows,'binary_build_or_upload':False,'functions_called_during_prepare':['reference_layout (actual reference bytes/partition parser)'],'network_browser_guest_process_calls':0})
    return rows

def source_provenance(firmware,request,row):
    source=firmware['source'];meta=source['metadata'];files=request['files'];cas=sha(canonical(files))
    need(source['kind']=='uiflow' and source['artifact_id']==cas==row['source_cas_sha256'],'source CAS differs')
    need(meta['base_sha256']==request['expected_base_sha256']==row['base_firmware_sha256'],'host-specific source base differs')
    need(meta['firmware_sha256']==firmware['sha256']==firmware['firmware_id'],'derived firmware identity differs')
    entries={e['path']:e for e in meta['files']};need(len(entries)==len(meta['files']) and set(entries)==set(files),'source file set differs')
    for name,text in files.items():need(entries[name]['sha256']==sha(text.encode()) and entries[name]['size']==len(text.encode()) and entries[name]['origin']=='caller','caller source bytes changed')
    need(meta['source_sha256']==meta['effective_source_sha256']==cas and meta['generated_files']==[],'unexpected generated/effective source')
    need(meta['caller_file_count']==5 and meta['caller_source_bytes']==sum(len(v.encode()) for v in files.values()),'source totals differ')
    need(meta['status']=='COMPOSED_NOT_EXECUTED' and meta['kind']=='uiflow2-source-composition','compose overclaims execution')
    need(meta['vfs']['filesystem']=='LittleFS' and meta['vfs']['source']=='actual-base-partition-table' and meta['vfs']['offset']==row['reference_layout']['offset'] and meta['vfs']['size']==row['reference_layout']['size'],'actual VFS partition differs')
    need(all(meta['preservation'][k] is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified')),'source readback/preservation not proven')
    return source

def state_valid(state,row):
    need(state['source']=='live' and state['contract_status']=='frozen','Unit state not live/frozen')
    need(len(state['units'])==1 and state['units'][0]['id']=='external1' and state['units'][0]['unit_id']==row['unit_id'],'wrong Unit topology')
    need(all(u['source']=='guest-qom' and u['available'] and not u['errors'] for u in state['units']),'Unit data plane unavailable')

def recorded_type(module,directory):
    class Recorded(module.Observations):
        def __init__(self,*values):super().__init__(*values);self.trace=[];self.last_input=None;self.phase='startup'
        def record(self,event):event={'at':now(),'event_id':len(self.trace),**event};self.trace.append(event);save(directory/'observation-index.json',self.trace);return event
        def serial_file(self,text,kind):
            name=f'observations/{len(self.trace):05d}-{kind}.txt';p=directory/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(text.encode());return name
        def wait(self,predicate,*,offset=0,timeout=60):
            prior=self.trace[self.last_input]['before_cursor']['data'] if self.last_input is not None else None
            def original_and_fresh(text):
                if not predicate(text):return False
                return prior is None or (self.serial.startswith(prior) and len(self.serial)>len(prior) and predicate(text[max(0,len(prior)-offset):]))
            value=super().wait(original_and_fresh,offset=offset,timeout=timeout)
            self.record({'kind':'wait-success','phase':self.phase,'offset':offset,'input_event':self.last_input,'serial_file':self.serial_file(self.serial,'serial'),'serial_sha256':sha(self.serial.encode())});return value
        def marker(self,marker,*,offset=0,timeout=60):
            super().marker(marker,offset=offset,timeout=timeout);self.phase=marker
            self.record({'kind':'marker','marker':marker,'offset':offset,'input_event':self.last_input,'serial_file':self.serial_file(self.serial,'marker'),'serial_sha256':sha(self.serial.encode())})
        def state(self):
            value=super().state();name=f'observations/{len(self.trace):05d}-state.json';save(directory/name,value);self.record({'kind':'state','file':name,'phase':self.phase,'input_event':self.last_input});return value
        def input(self,values,instance='external1',*,via_ui=True):
            before=self.client.json(f'sessions/{self.session_id}/serial?offset=0&limit=262144',via_ui=False);event=self.record({'kind':'input','id':instance,'values':values,'before_cursor':before,'via_ui':via_ui,'accepted':None})
            try:value=super().input(values,instance,via_ui=via_ui)
            except Exception as error:event.update({'accepted':False,'error':str(error)});save(directory/'observation-index.json',self.trace);raise
            event['accepted']=True;self.last_input=event['event_id'];save(directory/'observation-index.json',self.trace);return value
        def qom(self,path,prop):
            value=super().qom(path,prop);self.record({'kind':'qom','path':path,'property':prop,'value':value});return value
    return Recorded

def browser_check(report,row):
    need(report['session_id']==row['session_id'] and report['device_id']==row['device_id'] and report['firmware_sha256']==row['firmware_sha256'] and not report['errors'],'browser identity/errors differ')
    snaps=[s for s in report['snapshots'] if s.get('session_state')=='running'];need(snaps,'no actual running DOM snapshot')
    for snap in snaps:
        need(len(snap['units'])==1 and snap['units'][0]['instance']=='external1','browser attachment differs')
        for unit in snap['units']:
            p=unit['readback']['properties'];need(unit['dom_matches_product_readback'] and unit['readback_matches_real_http_response'],'browser instrumentation mismatch')
            need(any(any(x['id']==unit['instance'] and x['properties']==p for x in e.get('response',{}).get('units',[])) for e in report['readbacks']+report['posts']),'DOM lacks real browser HTTP backing')
            for key,value in p.items():
                cell=next((x for x in unit['values'] if x['field']==key),None);need(cell is not None,'missing actual DOM property')
                if isinstance(value,(int,float)) and not isinstance(value,bool):need(float(cell['text'])==value,'numeric DOM mismatch')
                else:need(cell['text']==(str(value).lower() if isinstance(value,bool) else str(value)),'DOM scalar mismatch')
    if row['unit_id']!='relay':need(report['actions'] and report['posts'],'positive inputs lack actual browser actions/HTTP')
    return {'running_snapshots':len(snaps),'real_posts':len(report['posts']),'actions':len(report['actions'])}

def evidence_check(data,result,request,module):
    original=module.validate_bundle(data,result)  # Entire original host evidence oracle.
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        manifest=json.loads(z.read('manifest.json'));s=manifest['session'];proof=result['runtime_provenance'];source=source_provenance(load(pathlib.Path(result['case_directory'])/'firmware-response.json'),request,result)
        need(s['firmware_provenance']==json.loads(z.read('firmware/uiflow-source.json'))==source and s['source_artifacts'][0]==result['source_cas_sha256'],'ZIP source identity differs')
        need(s['pid']==proof['observed_pid'] and s['worker']['worker_id']==proof['worker_id'] and s['worker']['generation']==proof['worker_generation'] and s['worker']['lease_active'],'ZIP direct PID/worker differs')
        state=json.loads(z.read('units/state.json'));state_valid(state,result);need(json.loads(z.read('units/contract.json'))['source_hashes']==state['contract_hashes'],'ZIP frozen Unit contract differs');frame(z.read('frames/current.png'),result)
    return {'original':original,'source_cas_sha256':source['artifact_id'],'pid':s['pid']}

def run_case(client,args,row,module):
    directory=args.out_dir/row['device_id']/row['unit_id'];request=load(directory/'source-request.json');result={**row,'case_directory':str(directory),'expected_runtime_sha256':args.expected_runtime_sha256,'expected_worker_generation':args.expected_worker_generation,'status':'FAIL','checks':{'actual_partition_layout_checked':True},'required_markers':[],'injections':[],'started_at':now(),'hardware_validation':'NOT RUN'};sid=None;pid=None
    with common.HTTPRecorder(directory/'http'):
        try:
            need(original_functions()==row['original_function_sha256'],'original host assertions changed')
            inventory=client.json('units?device_id='+row['device_id'],via_ui=False);save(directory/'live-unit-inventory.json',inventory);unit=next(u for u in inventory['units'] if u['id']==row['unit_id']);need(row['device_id'] in unit['runtime'].get('hosts',[]) and unit['runtime']['status'] in ('implemented','validated'),'host/Unit is not admitted')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware);result['source']=source_provenance(firmware,request,row);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+row['source_cas_sha256'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact);need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source artifact metadata differs')
            result['checks']['source_api_caller_bytes_base_cas_and_readback']=True
            payload={'device_id':row['device_id'],'runtime':'qemu','firmware_id':firmware['firmware_id'],'uiflow_source_sha256':row['source_cas_sha256'],'ttl_seconds':900,'ready_marker':'HOST_PROBE_READY','ready_timeout_seconds':180,'units':row['attachments']};save(directory/'session-request.json',payload)
            client.web_ui.call('prepare');session=client.json('sessions',method='POST',payload=payload);sid=result['session_id']=session['session_id'];save(directory/'created-session.json',session);print(row['device_id']+'/'+row['unit_id']+': visible source session '+sid,flush=True)
            observed=recorded_type(module,directory)(client,sid,result);observed.marker(row['ready_marker'],timeout=180)
            current=client.json(f'sessions/{sid}',via_ui=False);pid=current['pid'];save(directory/'ready-session.json',current)
            proof=client.web_ui.runtime_provenance(current,lambda:client.json(f'sessions/{sid}',via_ui=False));need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==args.expected_runtime_sha256 and type(proof['worker_generation']) is int and proof['worker_id'],'direct runtime process provenance differs')
            if args.expected_worker_generation is not None:need(proof['worker_generation']==args.expected_worker_generation,'unexpected worker generation')
            result['runtime_provenance']={**proof,'pid':proof['observed_pid']};result['runtime_provenance_alias']='pid is the identical observed_pid, for the unchanged original validate_bundle contract';client.web_ui_sessions[sid]['provenance_done']=True;client._open_web_ui(sid);result['checks']['live_runtime_pid_sha_verified']=True
            module.validate_case(observed,row['unit_id'])  # Entire original host oracle, including BMI270/display.
            need(EXPECTED[row['unit_id']]<=set(result['checks']) and all(result['checks'][k] is True for k in EXPECTED[row['unit_id']]),'original host assertions absent');result['checks']['original_host_validate_case_completed_without_reduction']=True
            state=observed.state();state_valid(state,row);save(directory/'final-units.json',state);result['unit_state']=state
            current=client.json(f'sessions/{sid}',via_ui=False);save(directory/'running-session.json',current);need(current['firmware_provenance']==result['source'] and current['source_artifacts'][0]==row['source_cas_sha256'],'running source identity differs')
            observed.wait(lambda text:True);(directory/'serial.txt').write_bytes(observed.serial.encode());data=client.raw(f'sessions/{sid}/frame.png');(directory/'frame.png').write_bytes(data);result['frame']=frame(data,row);result['checks']['nonblank_host_application_frame']=True
            client.web_ui.call('capture',session_id=sid,phase='host-original-complete',screenshot=True);need(original_functions()==row['original_function_sha256'],'original host assertions changed during case')
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if sid:
                try:
                    current=client.json(f'sessions/{sid}',via_ui=False);pid=pid or current.get('pid');save(directory/'before-evidence-session.json',current);serial=client.json(f'sessions/{sid}/serial?offset=0&limit=262144',via_ui=False);save(directory/'final-serial-response.json',serial);(directory/'serial-final.txt').write_bytes(serial['data'].encode())
                    data=client.raw(f'sessions/{sid}/evidence');(directory/'evidence.zip').write_bytes(data);result['evidence_sha256']=sha(data);result['evidence_summary']=evidence_check(data,result,request,module);result['checks']['zip_before_stop_original_bundle_and_source_provenance']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop_original_bundle_and_source_provenance']=False
                try:
                    stopped=client.json(f'sessions/{sid}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped);history=client.json(f'sessions/{sid}',via_ui=False);save(directory/'retained-session.json',history)
                    need(stopped['state'] in ('stopped','failed') and history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] and history['firmware_provenance']==result.get('source'),'retained host session/Flash/source differs')
                    need(type(pid) is int and pid>0,'owned runtime PID absent');deadline=time.monotonic()+15
                    while not common.pid_gone(pid) and time.monotonic()<deadline:time.sleep(.1)
                    need(common.pid_gone(pid),'owned QEMU PID remains after stop');data=client.raw(f'sessions/{sid}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(data);frame(data,row)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] and health['capacity']['active_sessions']==0,'service not idle after host case');result['cleanup']={'owned_pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0};result['checks']['purge_zero_history_frame_flash_release_pid_exit_idle']=True
                except Exception as error:result['cleanup_error']=str(error);result['checks']['purge_zero_history_frame_flash_release_pid_exit_idle']=False
                try:result['browser']=browser_check(load(args.out_dir/'browser'/sid/'web-report.json'),result);result['checks']['actual_product_dom_http_match']=True
                except Exception as error:result['browser_error']=str(error);result['checks']['actual_product_dom_http_match']=False
            result['status']='PASS' if sid and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL';result['finished_at']=now();save(directory/'result.json',result)
    print(row['device_id']+'/'+row['unit_id']+': '+result['status']+' '+result.get('error',''),flush=True);return result

def bounded_input_windows(directory,events):
    accepted=[e for e in events if e['kind']=='input' and e['accepted']];windows=[]
    for index,event in enumerate(accepted):
        before=event['before_cursor']['data'];waits=[e for e in events if e['kind']=='wait-success' and e.get('input_event')==event['event_id']];need(waits,'accepted input has no completed original wait')
        text=(directory/waits[-1]['serial_file']).read_bytes().decode();need(text.startswith(before) and len(text)>len(before),'accepted input has no new UART bytes')
        upper=len(accepted[index+1]['before_cursor']['data']) if index+1<len(accepted) else len(text)
        need(len(text)<=upper,'input UART observation crosses the next input boundary')
        windows.append((event,text[len(before):],len(before),len(text),upper))
    return windows

def semantic_check(directory,row,module):
    events=load(directory/'observation-index.json');serial=(directory/'serial-final.txt').read_bytes().decode();need(not any(x in serial for x in module.FAILURES),'host probe guest exception')
    profile=row['host_profile'];marker='HOST_GEOMETRY %d %d %d'%(*profile['canvas_size'],profile['rotation']);has=lambda text,m:re.search(r'(?m)^'+re.escape(m)+r'\r?$',text) is not None
    need(has(serial,row['ready_marker']) and has(serial,marker) and has(serial,'HOST_INTERNAL before 36 1') and has(serial,'HOST_INTERNAL after_init 36 2'),'original host geometry/initial BMI270 reads absent')
    identities=[(phase,int(chip),int(count)) for phase,chip,count in re.findall(r'(?m)^HOST_INTERNAL (before|after_init|loop) (\d+) (\d+)\r?$',serial)]
    need(identities and all(chip==36 for _,chip,_ in identities) and all(a[2]<b[2] for a,b in zip(identities,identities[1:])),'internal BMI270 identity/counter failed')
    windows=bounded_input_windows(directory,events);case=row['unit_id'];final=load(directory/'final-units.json');state_valid(final,row)
    if case=='button':
        need(len(windows)==4,'Button original input count differs')
        for index,((event,text,*_),pressed) in enumerate(zip(windows,(True,False,True,False))):
            need(event['values']=={'pressed':pressed},'Button original edge sequence differs')
            need(any(int(raw)==int(not pressed) and int(count)>=index for raw,count in re.findall(r'(?m)^HOST_BUTTON ([01]) (\d+)\r?$',text)),'fresh bounded Button raw/IRQ counter absent')
    elif case=='relay':
        need(not windows and has(serial,'HOST_RELAY 1') and has(serial,'HOST_RELAY 0'),'Relay original guest output markers absent')
        levels={load(directory/e['file'])['units'][0]['properties']['output-level'] for e in events if e['kind']=='state'};need(levels=={True,False},'Relay actual QOM lacks either output state')
    else:
        need(has(serial,'HOST_EXTERNAL_SCAN 68 112') and len(windows)==2,'ENV III external scan/two inputs absent')
        for (event,text,*_),expected in zip(windows,((31.5,67,98765),(18.75,45.5,103200))):
            need(event['values']==dict(zip(('temperature-c','humidity-pct','pressure-pa'),expected)),'ENV original input vector differs')
            vectors=re.findall(r'(?m)^HOST_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$',text)
            need(any(all(abs(float(a)-b)<=tol for a,b,tol in zip(v,expected,(.2,.2,1))) for v in vectors),'fresh bounded ENV vector absent')
            need('HOST_INTERNAL loop 36 ' in text,'ENV operation lacks new onboard BMI270 read')
        need(all(final['units'][0]['properties'][key]>0 for key in ('transactions','read-bytes','written-bytes','input-events')),'ENV actual controller counters absent')
    last_input=windows[-1][0]['event_id'] if windows else None
    final_waits=[e for e in events if e['kind']=='wait-success' and e.get('input_event')==last_input];need(final_waits,'final original internal-identity wait absent');last=final_waits[-1]
    # Original validate_case ends with an offset-bounded internal read; the later
    # unconditional final save cannot substitute for that observation.
    internal_waits=[e for e in final_waits if 'HOST_INTERNAL loop 36 ' in (directory/e['serial_file']).read_bytes().decode()[e['offset']:]]
    need(internal_waits,'onboard identity was not observed after external operations')
    return {'status':'PASS','accepted_inputs':len(windows),'bounded_windows':[{'event_id':e['event_id'],'lower':lo,'observed_end':end,'next_input_upper':upper} for e,_,lo,end,upper in windows],'internal_reads':len(identities),'last_internal_counter':identities[-1][2]}

def check_saved(output):
    need(output.is_relative_to(HERE) and output!=HERE,'check only a harness child')
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);p=(output/name).resolve();need(p.is_relative_to(output.resolve()) and sha(p.read_bytes())==expected,'saved host artifact checksum changed: '+name)
    module=original_module();frozen=load(output/'tooling-source-freeze.json')
    for name,value in frozen.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==value,'frozen tooling bytes changed: '+name)
    need(original_functions()==load(output/'original-functions.json'),'original host assertions differ from snapshot')
    rows=load(output/'prepared.json')['cases'];results=[]
    for row in rows:
        directory=output/row['device_id']/row['unit_id'];result=load(directory/'result.json');request=load(directory/'source-request.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS' and EXPECTED[row['unit_id']]<=set(result['checks']) and all(result['checks'].values()),'host case lacks all original completed assertions')
        for name,text in request['files'].items():need((directory/'files'/name).read_bytes()==text.encode() and sha(text.encode())==row['probe_sha256'][name],'caller source file changed')
        source_provenance(firmware,request,row);need(result['source']==firmware['source'],'stored source provenance differs')
        proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need({**proof,'pid':proof['observed_pid']}==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'] and type(proof['worker_generation']) is int,'direct PID runtime identity differs')
        if result['expected_worker_generation'] is not None:need(proof['worker_generation']==result['expected_worker_generation'],'recorded worker generation differs from required generation')
        actual=[]
        for event in load(directory/'http/index.json'):
            raw=(directory/'http'/event['response_file']).read_bytes();need(sha(raw)==event['response_sha256'] and len(raw)==event['response_size'],'raw host HTTP bytes changed')
            try:payload=json.loads(raw)
            except (ValueError,UnicodeDecodeError):payload=None
            actual.append((event,payload,raw))
        def backed(value,suffix,method=None):return any(p==value and e['path'].endswith(suffix) and (method is None or e['method']==method) for e,p,_ in actual)
        need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and p==firmware and json.loads((directory/'http'/e['request_file']).read_bytes())==request for e,p,_ in actual),'actual source compose POST differs')
        need(not any(e['method'] in ('POST','PUT') and e['path'] in ('/api/v1/artifacts','/api/v1/firmware') for e,_,_ in actual),'binary intake present')
        startup=load(directory/'session-request.json');need(startup['uiflow_source_sha256']==row['source_cas_sha256'] and startup['units']==row['attachments'],'startup source pin/topology differs')
        need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and p.get('session_id')==result['session_id'] and json.loads((directory/'http'/e['request_file']).read_bytes())==startup for e,p,_ in actual if isinstance(p,dict)),'actual source session POST absent')
        events=load(directory/'observation-index.json')
        for event in events:
            if event['kind'] in ('wait-success','marker'):
                text=(directory/event['serial_file']).read_bytes().decode();need(sha(text.encode())==event['serial_sha256'] and any(e['path'].endswith('/serial') and isinstance(p,dict) and p.get('data')==text for e,p,_ in actual),'serial observation lacks unchanged actual HTTP backing')
                need(0<=event['offset']<=len(text),'serial observation offset out of bounds')
                if event['kind']=='marker':need(re.search(r'(?m)^'+re.escape(event['marker'])+r'\r?$',text[event['offset']:]),'original marker absent in its original window')
            elif event['kind']=='state':need(backed(load(directory/event['file']),'/units'),'Unit/QOM observation lacks actual HTTP backing')
            elif event['kind']=='input':need(event['accepted'] is True and backed(event['before_cursor'],'/serial'),'input or actual UART baseline missing')
            elif event['kind']=='qom':need(any(e['path'].endswith('/qom') and urllib.parse.parse_qs(e['query'])=={'path':[event['path']],'property':[event['property']]} and p.get('value')==event['value'] for e,p,_ in actual if isinstance(p,dict)),'QOM scalar lacks actual HTTP backing')
        semantic=semantic_check(directory,row,module);browser=load(output/'browser'/result['session_id']/'web-report.json');browser_summary=browser_check(browser,result)
        for event in (e for e in events if e['kind']=='input'):
            for key,value in event['values'].items():
                actions=[a for a in browser['actions'] if a['instance']==event['id'] and a['field']==key and a.get('value',a.get('request',{}).get('values',{}).get(key))==value];need(actions,'input has no actual browser control action')
                if not any(a.get('kind')=='already-equal-noop' for a in actions):need(any(p.get('request',{}).get('id')==event['id'] and key in p.get('request',{}).get('values',{}) and p['request']['values'][key]==value and p['status']==200 for p in browser['posts']),'changed input lacks actual product HTTP POST')
        data=(directory/'evidence.zip').read_bytes();need(sha(data)==result['evidence_sha256'],'saved host ZIP changed');evidence_check(data,result,request,module)
        zip_indices=[i for i,(e,_,raw) in enumerate(actual) if e['method']=='GET' and e['path'].endswith('/evidence') and raw==data];stop_indices=[i for i,(e,_,_) in enumerate(actual) if e['method']=='DELETE' and e['path'].endswith('/'+result['session_id']) and urllib.parse.parse_qs(e['query'])=={'purge':['0']}];need(len(zip_indices)==len(stop_indices)==1 and zip_indices[0]<stop_indices[0],'ZIP not captured before purge=0 stop')
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');stopped=load(directory/'stop-response.json');need(backed(history,'/'+result['session_id'],'GET') and backed(stopped,'/'+result['session_id'],'DELETE') and backed(health,'/health','GET'),'cleanup lacks actual HTTP backing')
        need(history['state'] in ('stopped','failed') and history['flash_retained'] is False and history['last_frame_available'] is True and not history['worker']['lease_active'] and history['firmware_provenance']==result['source'],'retained source/Flash/lease differs')
        need(health['ok'] is True and health['capacity']['active_sessions']==0 and result['cleanup']['owned_pid']==proof['observed_pid'] and result['cleanup']['pid_gone'],'recorded PID/idle cleanup incomplete')
        frame((directory/'frame.png').read_bytes(),row);history_png=(directory/'history-frame.png').read_bytes();frame(history_png,row);need(any(i>stop_indices[0] and e['path'].endswith('/frame.png') and raw==history_png for i,(e,_,raw) in enumerate(actual)),'history native frame not actually fetched after stop')
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            contract=json.loads(z.read('units/contract.json'))
            for name,value in contract['source_hashes'].items():need(frozen.get('platform/units/'+name)==value,'ZIP Unit contract not bound to frozen sources')
        results.append({'device_id':row['device_id'],'unit_id':row['unit_id'],'session_id':result['session_id'],'status':'PASS','semantic':semantic,'browser':browser_summary,'worker_generation':proof['worker_generation']})
    return {'status':'PASS','cases':results,'scope':'Exact original host source/validate_case/validate_bundle + real source API/PID/DOM/HTTP/bounded UART/QOM/ZIP/cleanup; hardware NOT RUN'}

def checksums(output):
    files=sorted(p for p in output.rglob('*') if p.is_file() and p.name!='SHA256SUMS');(output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(output).as_posix()+'\n' for p in files))

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=pathlib.Path,required=True);p.add_argument('--device',choices=DEVICES,action='append');p.add_argument('--case',choices=CASES,action='append');p.add_argument('--prepare-only',action='store_true');p.add_argument('--execute',action='store_true');p.add_argument('--check',action='store_true');p.add_argument('--api-url',default='http://127.0.0.1:8787');p.add_argument('--expected-runtime-sha256',default=RUNTIME);p.add_argument('--expected-worker-generation',type=int);p.add_argument('--source-context-commit',help='Exact current commit supplied by root only after commit+fetch; execute always re-prepares a fresh directory');args=p.parse_args(argv);args.out_dir=args.out_dir.resolve()
    need(not(args.execute and (args.prepare_only or args.check)),'choose offline or live mode');need(args.out_dir.is_relative_to(HERE) and args.out_dir!=HERE,'output must be a child of this harness')
    if args.check:print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2));return
    if args.execute:
        need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','root execution requires real product Web bridge');need(args.source_context_commit is not None and args.source_context_commit==git_head(),'root must commit+fetch first, then supply the current exact source context for fresh preparation');need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'},'local service required for actual direct PID verification');need(args.expected_runtime_sha256==RUNTIME,'this authoring freeze requires runtime 29d8');need(args.expected_worker_generation is None or args.expected_worker_generation>=0,'invalid expected generation')
    rows=prepare(args.out_dir,list(dict.fromkeys(args.device or DEVICES)),list(dict.fromkeys(args.case or CASES)),args.source_context_commit)
    if not args.execute:checksums(args.out_dir);print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','combinations':len(rows),'source_context_commit':git_head(),'reprepare_after_root_commit_and_fetch':True,'uploaded_python_files_per_case':5,'extra_drivers':False},ensure_ascii=False));return
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=RUNTIME;module=original_module()
    from run_service_cases import Client
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**kwargs):need(not(method in ('POST','PUT') and path.split('?')[0] in ('artifacts','firmware')),'BIN/merged/alternate firmware upload is prohibited');return super().raw(path,method=method,**kwargs)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with common.HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'root must begin with idle service')
        for row in rows:
            result=run_case(client,args,row,module);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close();save(args.out_dir/'batch-result.json',{'status':'PASS' if len(results)==len(rows) and all(r['status']=='PASS' for r in results) else 'FAIL','finished_at':now(),'cases':[{k:r.get(k) for k in ('device_id','unit_id','session_id','status','error','cleanup_error')} for r in results]});checksums(args.out_dir)
    need(len(results)==len(rows) and all(r['status']=='PASS' for r in results),'host source cases failed');print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
