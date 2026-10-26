#!/usr/bin/env python3
"""Prepare source-only requests, or explicitly execute real API/browser Unit acceptance.

Default: offline request preparation only. No BIN builder, artifact upload,
HTTP request, browser or QEMU is used unless --execute is supplied by root.
--check validates saved evidence offline without contacting the service.
"""
from __future__ import annotations
import argparse, ast, collections, hashlib, io, json, os, pathlib, re, shutil, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from datetime import datetime, timezone

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
UNIT=ROOT/'tests/units'
BASE='1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264'
RUNTIME='29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d'
CASES=('joystick-v11','8encoder','cardkb','rfid2')
FLAVOR='controls-probe-cores3-native-display-v1'
FAILURES=('IO_PROBE_FAIL','CONTROL_PROBE_ERROR','Traceback (most recent call last)','Guru Meditation','A fatal error occurred','Rebooting...')

def need(condition,message):
    if not condition: raise RuntimeError(message)
def sha(data): return hashlib.sha256(data).hexdigest()
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def load(path):return json.loads(path.read_bytes())
def now():return datetime.now(timezone.utc).isoformat()
def guarded_directory(path):
    path=path.resolve();need(path.is_relative_to(HERE) and path!=HERE,'outputs must be in a fresh child of this harness directory');return path

def display_contract(case):
    rows={'joystick-v11':3,'8encoder':10,'cardkb':1,'rfid2':3}[case]
    return {'device_id':'cores3','native':[320,240],'rotation':1,'font':'Montserrat12','scale':1.0,'font_height':15,
      'x':6,'y':6,'width':308,'body_y':24,'line_height':16,'body_rows':rows,'bottom':24+16*rows,'headers':1,
      'flavor':FLAVOR,'evidence':'guest fontHeight/textWidth and native geometry checks required; preparation is not display PASS'}

DISPLAY_WRAPPER = '''from host_control_layout import DISPLAY_PROFILES, FONT_NAME, checked_layout, print_checked, value_lines
DISPLAY_PROFILES["cores3"] = {"native": (320, 240), "canvas": (320, 240), "text": (6, 6, 308), "text_size": 1.0, "font_height": 15}

def prepare_display(screen, case, emit):
    screen.setRotation(1)
    screen.setBrightness(255)
    screen.fillScreen(0xFFFFFF)
    screen.setTextColor(0x0282CB, 0xFFFFFF)
    screen.setFont(screen.FONTS.Montserrat12)
    screen.setTextSize(1.0)
    layout = checked_layout("cores3", case, screen.fontHeight(), screen.textWidth)
    emit("SOURCE_CONTROL_GEOMETRY", screen.width(), screen.height(), 1)
    emit("SOURCE_CONTROL_FONT", FONT_NAME, 1.0, screen.fontHeight())
    emit("SOURCE_CONTROL_LAYOUT", layout["x"], layout["y"], layout["width"], layout["body_y"], layout["line_height"], layout["body_rows"], layout["bottom"], len(layout["headers"]))
    if (screen.width(), screen.height()) != (320, 240):
        raise RuntimeError("CoreS3 native display geometry differs")
    for index, text in enumerate(layout["headers"]):
        print_checked(screen, layout, text, layout["y"] + index * layout["line_height"])
    return layout

def draw_display(screen, layout, case, value):
    lines = value_lines(case, value)
    if len(lines) > layout["body_rows"]:
        raise RuntimeError("Unit readout exceeds native display rows")
    screen.fillRect(layout["x"], layout["body_y"], layout["width"], layout["body_rows"] * layout["line_height"], 0xFFFFFF)
    for index, text in enumerate(lines):
        print_checked(screen, layout, text, layout["body_y"] + index * layout["line_height"])
'''

DISPLAY_REPLACEMENTS = (
    ('from probe_config import CASE, WHITE, YELLOW\n', 'from probe_config import CASE, WHITE, YELLOW\nfrom probe_display import prepare_display, draw_display\n'),
    ('    screen.fillScreen(0xFFFFFF)\n    screen.setTextColor(0x0282CB, 0xFFFFFF)\n    screen.setTextSize(2)\n    screen.setCursor(6, 6)\n    screen.print("Control: " + CASE)\n', '    layout = prepare_display(screen, CASE, emit)\n'),
    ('            screen.fillRect(0, 38, screen.width(), 160, 0xFFFFFF)\n            screen.setCursor(6, 42)\n            screen.print(str(value))\n', '            draw_display(screen, layout, CASE, value)\n'),
)

def source_files(case):
    mapping={};origins={}
    def add(target,source):
        raw=source.read_bytes();text=raw.decode('utf-8');need(text.encode('utf-8')==raw,'source UTF-8 bytes changed')
        mapping[target]=text;origins[target]={'repository_path':source.relative_to(ROOT).as_posix(),'size':len(raw),'sha256':sha(raw),'copy':'byte-exact'}
    add('boot.py',UNIT/'probe/boot.py')
    original=(UNIT/'controls_probe/main.py').read_text(encoding='utf-8');main=original
    for before,after in DISPLAY_REPLACEMENTS:
        need(main.count(before)==1,'display-only flavor patch context changed');main=main.replace(before,after)
    restored=main
    for before,after in reversed(DISPLAY_REPLACEMENTS):
        need(restored.count(after)==1,'display-only reverse context changed');restored=restored.replace(after,before)
    need(restored==original,'guest control/driver path changed outside explicit display-only replacements')
    mapping['main.py']=main
    origins['main.py']={'repository_path':'tests/units/controls_probe/main.py','original_sha256':sha(original.encode()),'sha256':sha(main.encode()),'size':len(main.encode()),'copy':'explicit-display-only-flavor','flavor':FLAVOR,'exact_reverse_verified':True,'changes':[{'before_sha256':sha(a.encode()),'after_sha256':sha(b.encode())} for a,b in DISPLAY_REPLACEMENTS]}
    add('host_control_layout.py',UNIT/'host_controls_probe/host_control_layout.py')
    mapping['probe_display.py']=DISPLAY_WRAPPER;origins['probe_display.py']={'copy':'generated-CoreS3-display-profile-and-observer','sha256':sha(DISPLAY_WRAPPER.encode()),'size':len(DISPLAY_WRAPPER.encode()),'contract':display_contract(case)}
    package=UNIT/'controls_probe/control_drivers'
    drivers={'joystick-v11':('__init__.py','joystick.py','unit_helper.py'),
      '8encoder':('__init__.py','encoder8.py','pahub.py','unit_helper.py'),
      'cardkb':('__init__.py','cardkb.py'),
      'rfid2':('__init__.py','mfrc522/__init__.py','mfrc522/cmd.py','mfrc522/reg.py','mfrc522/firmware.py')}[case]
    manifest=load(package/'source-manifest.json');driver_proof={}
    for name in drivers:
        add('control_drivers/'+name,package/name)
        if name in manifest:
            need(sha(mapping['control_drivers/'+name].encode())==manifest[name]['sha256'],'official driver bytes changed: '+name)
            driver_proof['control_drivers/'+name]=manifest[name]
    ports=load(ROOT/'platform/units/host-ports.json')['hosts'];host=next(h for h in ports if h['device_id']=='cores3')
    choices=[p for p in host['ports'] if p.get('visual_port')=='grove' and p.get('wiring_status')=='confirmed' and p.get('physical_presence')=='main-device']
    need(len(choices)==1,'CoreS3 needs one confirmed main Grove connector');port=choices[0]
    config={'CASE':case,'WHITE':port['pins']['white'],'YELLOW':port['pins']['yellow']}
    text=''.join(f'{k} = {v!r}\n' for k,v in config.items());mapping['probe_config.py']=text
    origins['probe_config.py']={'copy':'generated-explicit-CoreS3-probe-config','size':len(text.encode()),'sha256':sha(text.encode()),'host_ports_sha256':sha((ROOT/'platform/units/host-ports.json').read_bytes())}
    for name,text in mapping.items():ast.parse(text,filename=name)
    need(len(mapping)<=128 and max(len(v.encode()) for v in mapping.values())<=256*1024 and sum(len(v.encode()) for v in mapping.values())<=1024*1024,'source helper limits exceeded')
    need(len(canonical({'device_id':'cores3','files':mapping,'expected_base_sha256':BASE}))<=1024*1024,'HTTP JSON body exceeds source route limit')
    return dict(sorted(mapping.items())),origins,port,driver_proof


def prepare(output,cases):
    need(not output.exists(),'choose a fresh output directory; existing evidence is preserved');output.mkdir(parents=True)
    tooling=['tests/units/run_service_cases.py','tests/units/run_io_cases.py','tests/units/run_control_cases.py','tests/units/web_ui_bridge.py','platform/tests/unit_web_bridge.mjs','platform/web/sessions.js','platform/web/unit-panel.js','platform/web/unit-visual-mappings.js','platform/units/host-ports.json','platform/units/runtime-profiles.json','platform/units/catalog.json','platform/tools/unit_runtime.py','platform/tools/device_service.py','platform/tools/serve.py','platform/tools/uiflow_source.py','tests/units/controls_probe/main.py','tests/units/controls_probe/control_drivers/source-manifest.json','tests/units/host_controls_probe/host_control_layout.py','tests/units/host_controls_probe/font-source.json','platform/units/fixtures/cardkb-keymap.json']
    freeze={}
    for name in tooling:
        data=(ROOT/name).read_bytes();freeze[name]=sha(data)
        target=output/'source-snapshot'/(name+'.txt');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    harness=pathlib.Path(__file__).read_bytes();freeze['HARNESS/run_source_controls.py']=sha(harness)
    target=output/'source-snapshot/HARNESS/run_source_controls.py.txt';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(harness)
    save(output/'tooling-source-freeze.json',freeze)
    verify_original_assertions()
    prepared=[]
    for case in cases:
        directory=output/case;directory.mkdir()
        files,origins,port,drivers=source_files(case)
        request={'device_id':'cores3','files':files,'expected_base_sha256':BASE}
        save(directory/'source-request.json',request)
        for name,text in files.items():
            target=directory/'files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(text.encode())
        save(directory/'guest-source-freeze.json',origins)
        save(directory/'official-driver-proof.json',drivers)
        for package,source in [('io_drivers',UNIT/'io_probe/io_drivers/LICENSE.MIT'),('control_drivers',UNIT/'controls_probe/control_drivers/LICENSE.MIT')]:
            if any(name.startswith(package+'/') for name in files):
                target=directory/'license-evidence'/package/'LICENSE.MIT';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
        row={'unit_id':case,'device_id':'cores3','runtime':'qemu','base_sha256':BASE,'expected_runtime_sha256':RUNTIME,'source_cas_sha256':sha(canonical(files)),'files':{name:{'sha256':sha(text.encode()),'size':len(text.encode())} for name,text in files.items()},'port':port,'attachments':[{'id':'external1','unit_id':case,'port_id':port['id']}],'ready_marker':'CONTROL_PROBE_READY '+case,'flavor':FLAVOR,'display_contract':display_contract(case),'status':'PREPARED_NO_API_OR_RUNTIME'}
        save(directory/'prepared.json',row);prepared.append(row)
    save(output/'prepared.json',{'created_at':now(),'status':'PREPARED_NO_API_OR_RUNTIME','cases':prepared,'source_intake':'POST /api/v1/firmware/uiflow','binary_build_or_upload':False})
    return prepared

class HTTPRecorder:
    """Record actual urllib traffic; all reads return the original response bytes."""
    def __init__(self,directory):self.directory=directory;self.events=[];self.original=None
    def __enter__(self):
        self.directory.mkdir(parents=True,exist_ok=True);self.original=urllib.request.urlopen;urllib.request.urlopen=self.open;return self
    def __exit__(self,*args):
        urllib.request.urlopen=self.original;save(self.directory/'index.json',self.events)
    def open(self,request,*args,**kwargs):
        url=request.full_url if isinstance(request,urllib.request.Request) else str(request)
        method=request.get_method() if isinstance(request,urllib.request.Request) else 'GET'
        need(urllib.parse.urlparse(url).hostname in {'127.0.0.1','localhost','::1'},'runner records only the local Device Service')
        number=len(self.events);prefix=f'{number:05d}';body=getattr(request,'data',None)
        event={'at':now(),'method':method,'url':url,'path':urllib.parse.urlsplit(url).path,'query':urllib.parse.urlsplit(url).query,'request_file':prefix+'.request.raw','response_file':prefix+'.response.raw'}
        self.events.append(event);(self.directory/event['request_file']).write_bytes(body or b'')
        def record(data):
            target=self.directory/event['response_file']
            with target.open('ab') as stream:stream.write(data)
            event['response_sha256']=sha(target.read_bytes());event['response_size']=target.stat().st_size
            save(self.directory/'index.json',self.events)
            return data
        try:response=self.original(request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            event['status']=error.code;real_read=error.read
            def audited_error_read(*read_args,**read_kwargs):return record(real_read(*read_args,**read_kwargs))
            error.read=audited_error_read
            raise
        event['status']=response.status
        class Response:
            def __enter__(self):response.__enter__();return self
            def __exit__(self,*values):return response.__exit__(*values)
            def __getattr__(self,name):return getattr(response,name)
            def read(self,*values,**options):return record(response.read(*values,**options))
        return Response()

def source_provenance(firmware,request):
    files=request['files'];source=firmware['source'];meta=source['metadata'];caller_sha=sha(canonical(files))
    need(source['kind']=='uiflow' and source['artifact_id']==caller_sha,'firmware source kind/CAS does not match canonical caller files')
    need(meta['base_sha256']==BASE and meta['source_sha256']==caller_sha,'source API base/source SHA differs')
    need(meta['firmware_sha256']==firmware['sha256']==firmware['firmware_id'],'returned firmware identity differs')
    entries={entry['path']:entry for entry in meta['files']}
    need(len(entries)==len(meta['files']) and set(entries)==set(files),'effective source file set differs from caller file set')
    for name,text in files.items():
        need(entries[name]['sha256']==sha(text.encode()) and entries[name]['size']==len(text.encode()),'source API file size/hash differs: '+name)
        need(entries[name].get('origin')=='caller','source was not preserved as caller bytes: '+name)
    need(meta['generated_files']==[],'unexpected source generation despite explicit caller boot/main')
    need(meta['effective_source_sha256']==caller_sha,'effective source identity differs')
    for field in ('vfs','toolchain','preservation'):need(isinstance(meta[field],dict) and bool(meta[field]),'source metadata missing '+field)
    need(meta['status']=='COMPOSED_NOT_EXECUTED' and meta['kind']=='uiflow2-source-composition','source composition overclaims guest execution')
    need(meta['vfs']['filesystem']=='LittleFS' and meta['vfs']['source']=='actual-base-partition-table','source VFS metadata has no actual partition layout')
    need(all(meta['preservation'].get(k) is True for k in ('outside_vfs_unchanged','existing_files_readback_verified','source_readback_verified')),'source composition/readback preservation failed')
    need(meta['caller_file_count']==len(files) and meta['caller_source_bytes']==sum(len(s.encode()) for s in files.values()),'caller source totals differ')
    return source

def input_negative(client,session_id,values,stable_fields,directory):
    before=client.json(f'sessions/{session_id}/units',via_ui=False)
    try:
        client.json(f'sessions/{session_id}/unit-input',method='POST',payload={'id':'external1','values':values},via_ui=False)
    except RuntimeError as error:
        need(re.search(r'HTTP (400|409)\b',str(error)) is not None,'invalid input failed outside expected API rejection')
        failure=str(error)
    else:raise RuntimeError('invalid Unit input was accepted')
    after=client.json(f'sessions/{session_id}/units',via_ui=False)
    b=before['units'][0]['properties'];a=after['units'][0]['properties']
    need(all(a[key]==b[key] for key in (*stable_fields,'input-events')),'rejected Unit input changed physical input state')
    save(directory/'negative-input.json',{'request':{'id':'external1','values':values},'error':failure,'before':before,'after':after,'unchanged_fields':[*stable_fields,'input-events']})

def source_negatives(client,request,output):
    cases=[('wrong-base',{**request,'expected_base_sha256':'0'*64}),('path-traversal',{**request,'files':{'main.py':'print("no runtime should be created")\n','../escape.py':'pass\n'}})]
    results=[]
    for label,payload in cases:
        try:client.json('firmware/uiflow',method='POST',payload=payload,via_ui=False)
        except RuntimeError as error:
            need(re.search(r'HTTP (400|409)\b',str(error)) is not None,'source negative failed outside expected API rejection')
            results.append({'case':label,'status':'REJECTED','error':str(error)})
        else:raise RuntimeError('source negative was accepted: '+label)
    save(output/'source-api-negatives.json',results)

def pid_gone(pid):
    try:os.kill(pid,0)
    except ProcessLookupError:return True
    except PermissionError:return False
    return False

def frame_valid(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        image.load();need(image.format=='PNG' and image.size==(320,240),'native framebuffer format or geometry differs')
        need(len(image.convert('RGB').getcolors(maxcolors=1) or [])==0,'native framebuffer has only one color')
    return {'sha256':sha(data),'size':len(data),'width':320,'height':240}

def check_browser(report,session_id,firmware_sha):
    need(report['session_id']==session_id and report['firmware_sha256']==firmware_sha,'browser session/firmware identity differs')
    need(not report.get('errors'),'browser captured product errors')
    snapshots=[s for s in report['snapshots'] if s.get('session_state')=='running']
    need(bool(snapshots),'no actual running DOM snapshots')
    for snap in snapshots:
        need(len(snap['units'])==1,'browser attachment set differs')
        unit=snap['units'][0]
        need(unit['dom_matches_product_readback'] is True and unit['readback_matches_real_http_response'] is True,'DOM is not bound to actual HTTP readback')
        props=unit['readback']['properties']
        need(any(event.get('response',{}).get('units') and any(u['id']==unit['instance'] and u.get('properties')==props for u in event['response']['units']) for event in report['readbacks']+report['posts']),'DOM properties lack an independent captured browser HTTP response')
        for field,value in props.items():
            row=next((r for r in unit['values'] if r['field']==field),None);need(row is not None,'actual DOM property missing')
            if field=='led-rgb' and row.get('rgb'):
                colors=value if isinstance(value,list) else [value]
                need(row['rgb']==[f'LED[{i}] #{color:06x}' for i,color in enumerate(colors)],'RGB DOM label differs')
            else:
                text=json.dumps(value,separators=(',',':'),ensure_ascii=False) if isinstance(value,(dict,list)) else str(value).lower() if isinstance(value,bool) else str(value)
                need(row['text']==text,'actual DOM value differs: '+field)
    return {'snapshots':len(snapshots),'posts':len(report['posts']),'actions':len(report['actions'])}

def original_assertion_text(text):
    tree=ast.parse(text);run=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
    block=next(n for n in run.body if isinstance(n,ast.Try)).body
    first=next(i for i,n in enumerate(block) if isinstance(n,ast.If) and ast.unparse(n.test)=="case == 'joystick-v11'")
    last=next(i for i,n in enumerate(block) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='frame' for t in n.targets))
    import textwrap
    return textwrap.dedent('\n'.join(text.splitlines()[block[first].lineno-1:block[last-1].end_lineno]))

def verify_original_assertions():
    expected=ast.parse(original_assertion_text((UNIT/'run_control_cases.py').read_text()))
    own=ast.parse(pathlib.Path(__file__).read_text());fn=next(n for n in own.body if isinstance(n,ast.FunctionDef) and n.name=='original_control_protocol')
    first=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.If) and ast.unparse(n.test)=="case == 'joystick-v11'")
    actual=ast.Module(body=fn.body[first:first+len(expected.body)],type_ignores=[])
    need(ast.dump(actual,include_attributes=False)==ast.dump(expected,include_attributes=False),'original control assertions changed, omitted or weakened')
    return {'source':'tests/units/run_control_cases.py','source_sha256':sha((UNIT/'run_control_cases.py').read_bytes()),'original_block_sha256':sha(original_assertion_text((UNIT/'run_control_cases.py').read_text()).encode()),'ast_exact_match':True,'assertion_count':sum(isinstance(n,ast.Assert) for n in ast.walk(expected))}

def original_control_protocol(client,session_id,case,result,directory,initial_serial):
    from run_service_cases import wait_for as real_wait_for
    serial=initial_serial
    waits=[]
    def wait_for(actual_client,actual_session,predicate,timeout=60):
        value=real_wait_for(actual_client,actual_session,predicate,timeout)
        name=f'waits/{len(waits):04d}-serial.txt';target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(value.encode())
        waits.append({'file':name,'sha256':sha(value.encode()),'size':len(value.encode())});save(directory/'wait-index.json',waits)
        return value
    def send(values):
        before=client.json(f'sessions/{session_id}/serial?limit=262144',via_ui=False).get('data','')
        state_before=client.json(f'sessions/{session_id}/units',via_ui=False)
        response=client.json(f'sessions/{session_id}/unit-input',method='POST',payload={'id':'external1','values':values})
        number=len(result['steps']);name=f'steps/{number:04d}-before.txt';target=directory/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(before.encode())
        result['steps'].append({'values':values,'serial_offset':len(before),'before_file':name,'before_sha256':sha(before.encode()),'state_before':state_before,'ui_readback_response':response})
        save(directory/'input-steps.json',result['steps'])
        return response
    def wait_marker(marker,offset=0):
        return wait_for(client,session_id,lambda text:marker in text[offset:],40)
    if case == "joystick-v11":
        offset = len(serial)
        send({"x-raw": 31, "y-raw": 240, "button-raw": 1})
        serial = wait_marker("CONTROL_JOYSTICK 31 240 1", offset)
        offset = len(serial)
        send({"x-raw": 255, "y-raw": 0, "button-raw": 0})
        serial = wait_marker("CONTROL_JOYSTICK 255 0 0", offset)
        result["checks"]["three_raw_bytes_reach_guest"] = True
    elif case == "encoder":
        offset = len(serial)
        send({"counter": -12345, "pressed": True})
        serial = wait_marker("CONTROL_ENCODER -12345 1", offset)
        offset = len(serial)
        send({"counter": 32767, "pressed": False})
        serial = wait_marker("CONTROL_ENCODER 32767 0", offset)
        result["checks"]["signed_int16_and_active_low_driver"] = True
    elif case == "8encoder":
        assert "CONTROL_ENCODER8_REGISTER_WRITE -1234567 0" in serial
        assert "CONTROL_ENCODER8_ADDRESS 66" in serial
        counts = [1, -2, 123456, -123456, 2147483647, -2147483648, 7, 8]
        pressed = [True, False, True, False, False, True, False, True]
        offset = len(serial)
        send({"counters": counts, "pressed": pressed, "switch-on": True})
        expected = "CONTROL_ENCODER8 %s %s 1" % (counts, [int(value) for value in pressed])
        serial = wait_marker(expected, offset)
        result["checks"]["eight_signed_channels_buttons_and_switch"] = True
        result["checks"]["guest_counter_write_reset_and_address_change"] = True
    elif case == "cardkb":
        assert "CONTROL_CARDKB_LEGACY 1" in serial
        fixture = json.loads((ROOT / "platform/units/fixtures/cardkb-keymap.json").read_text())
        keys = [False] * 50
        by_id = {row["id"]: row for row in fixture["keys"]}
        expected_stream = []
        start_offset = len(serial)

        def tap(key, expected=None):
            nonlocal serial
            index = by_id[key]["index"]
            offset = len(serial)
            keys[index] = True
            send({"keys": keys.copy()})
            keys[index] = False
            send({"keys": keys.copy()})
            if expected is not None:
                if expected:
                    expected_stream.append(expected)
                    serial = wait_for(client, session_id, lambda text: re.search(
                        rf"(?m)^CONTROL_CARDKB_KEY {expected}\r?$", text[offset:]), 40)

        for row in fixture["keys"]:
            if not row["modifier"]:
                tap(row["id"], row["normal"])
        result["checks"]["all_47_nonmodifier_keys_via_i2c"] = True
        for modifier, field in (("key-shift", "shift"), ("key-sym", "sym"), ("key-fn", "fn")):
            tap(modifier)
            tap("key-q", by_id["key-q"][field])
            tap("key-q", by_id["key-q"]["normal"])
        result["checks"]["all_three_one_shot_modifiers"] = True
        for modifier, field, mode in (("key-shift", "shift", 2), ("key-sym", "sym", 4), ("key-fn", "fn", 6)):
            if client.web_ui:
                # A single real browser gesture preserves the official
                # 200 ms double-click interval; per-input evidence writes
                # must not lengthen a timing-sensitive user gesture.
                client.unit_double_tap(session_id, "external1", "keys", by_id[modifier]["index"])
            else:
                tap(modifier)
                tap(modifier)
            snapshot = client.json(f"sessions/{session_id}/units")
            assert snapshot["units"][0]["properties"]["modifier-mode"] == mode
            for row in fixture["keys"]:
                if not row["modifier"]:
                    tap(row["id"], row[field])
            tap(modifier)  # Unlock returns normal.
            snapshot = client.json(f"sessions/{session_id}/units")
            assert snapshot["units"][0]["properties"]["modifier-mode"] == 0
        result["checks"]["all_four_official_key_tables_and_modifier_locks"] = True
        # Direct keycode is a byte fixture, separate from matrix evidence.
        offset = len(serial)
        send({"keycode": 0x41})
        serial = wait_for(client, session_id, lambda text: re.search(r"(?m)^CONTROL_CARDKB_KEY 65\r?$", text[offset:]), 40)
        expected_stream.append(65)
        observed = [int(value) for value in re.findall(r"(?m)^CONTROL_CARDKB_KEY (\d+)\r?$", serial[start_offset:])]
        assert observed == expected_stream, (observed, expected_stream)
        result["checks"]["legacy_byte_consumption"] = True
    else:
        assert "CONTROL_RFID_CRC_VECTOR 1 05bf" in serial
        offset = len(serial)
        send({"uid-hex": "04010203", "card-present": True})
        serial = wait_marker("CONTROL_RFID_UID 04010203", offset)
        serial = wait_marker("CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40")
        for marker in ("CONTROL_RFID_BAD_KEY 1", "CONTROL_RFID_BAD_CRC 1", "CONTROL_RFID_SECTOR_DENIED 1", "CONTROL_RFID_HALT_DENIED 1", "CONTROL_RFID_ANTENNA_OFF 1"):
            serial = wait_marker(marker)
        result["checks"]["request_anticollision_select_auth_block_write_read_halt"] = True
        result["checks"]["wrong_key_halt_and_antenna_negative_controls"] = True
        for uid in ("04010203040506", "04010203040506070809"):
            offset = len(serial)
            send({"uid-hex": uid, "card-present": True})
            serial = wait_marker("CONTROL_RFID_UID " + uid, offset)
            serial = wait_marker("CONTROL_RFID_ANTENNA_OFF 1", offset)
        result["checks"]["four_seven_ten_byte_uid_cascade_select"] = True
        offset = len(serial)
        send({"card-present": False})
        serial = wait_marker("CONTROL_RFID_NO_CARD", offset)
        result["checks"]["card_removal_reaches_guest"] = True

    snapshot = client.json(f"sessions/{session_id}/units")
    result["unit_state"] = snapshot
    state = snapshot["units"][0]
    properties = state["properties"]
    assert snapshot["source"] == "live" and state["source"] == "guest-qom" and state["available"]
    assert properties["transactions"] > 0 and properties["read-bytes"] > 0
    assert properties["written-bytes"] > 0 and properties["input-events"] > 0
    result["checks"]["same_guest_i2c_controller_counters"] = True
    if case == "encoder":
        assert properties["led-rgb"] == [0x112233, 0x445566]
        result["checks"]["guest_led_writes_read_back"] = True
    if case == "8encoder":
        assert properties["led-rgb"] == [i * 0x010203 for i in range(1, 9)] + [0x192939]
        assert properties["i2c-address"] == 0x42
        result["checks"]["all_nine_guest_rgb_register_triplets"] = True
    if case == 'cardkb':
        result['cardkb_start_offset']=start_offset
        result['cardkb_expected_stream']=expected_stream
    result['original_assertion_parity']=verify_original_assertions()
    return serial,snapshot

def case_protocol(client,session_id,case,result,directory,Observations,validate_io):
    from run_service_cases import wait_for
    from run_control_cases import settled_frame
    serial=wait_for(client,session_id,lambda text:result['ready_marker'] in text,180)
    initial=client.json(f'sessions/{session_id}/units',via_ui=False);save(directory/'initial-units.json',initial)
    session=client.json(f'sessions/{session_id}',via_ui=False)
    proof=client.web_ui.runtime_provenance(session,lambda:client.json(f'sessions/{session_id}',via_ui=False))
    need(proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'live process does not match frozen 29d8 runtime')
    need(isinstance(proof['worker_id'],str) and proof['worker_id'] and type(proof['worker_generation']) is int,'direct runtime proof lacks worker identity/generation')
    result['runtime_provenance']=proof;client.web_ui_sessions[session_id]['provenance_done']=True;client._open_web_ui(session_id)
    negative={'joystick-v11':({'x-raw':256},('x-raw','y-raw','button-raw')),
      '8encoder':({'counters':[2147483648]*8},('counters','pressed','switch-on')),
      'cardkb':({'keycode':256},()),'rfid2':({'uid-hex':'xyz'},('card-present','uid-hex'))}[case]
    input_negative(client,session_id,*negative,directory)
    result['steps']=[]
    serial,snapshot=original_control_protocol(client,session_id,case,result,directory,serial)
    need(snapshot['contract_status']=='frozen','control Unit contract is not frozen')
    final=client.json(f'sessions/{session_id}/units',via_ui=False);save(directory/'final-units.json',final)
    result['unit_state']=final
    index=[{'kind':'state','phase':'startup','file':'initial-units.json'},{'kind':'state','phase':'final','file':'final-units.json'}]
    save(directory/'observation-index.json',index)
    need(not any(marker in serial for marker in FAILURES),'guest exception in control serial')
    (directory/'serial.txt').write_bytes(serial.encode())
    result['protocol_replay']=replay_controls(directory,result,result,serial,load(ROOT/'platform/units/fixtures/cardkb-keymap.json'))
    result['required_markers']=result['protocol_replay']['required_markers']
    result['checks']['original_all_control_assertions_retained']=True
    result['checks']['fresh_controls_serial_and_qom_replayed']=True
    frame=settled_frame(client,session_id);(directory/'settled-frame.png').write_bytes(frame);frame_valid(frame)
    result['checks']['settled_native_frame']=True
    return serial


def validate_zip(data,result,request):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names=archive.namelist();need(len(names)==len(set(names)) and archive.testzip() is None,'duplicate/corrupt evidence ZIP')
        required={'manifest.json','serial.log','frames/current.png','qom/snapshot.json','units/contract.json','units/runtime.json','units/state.json','firmware/uiflow-source.json'}
        need(required<=set(names),'evidence ZIP missing required source/guest/controller files')
        manifest=json.loads(archive.read('manifest.json'));need(set(manifest['files'])==set(names)-{'manifest.json'},'ZIP member index differs')
        for name,info in manifest['files'].items():
            raw=archive.read(name);need(info['size']==len(raw) and info['sha256']==sha(raw),'ZIP member hash differs: '+name)
        session=manifest['session'];need(session['state']=='running','ZIP was not captured before stop')
        for key in ('session_id','device_id','runtime','firmware_sha256'):need(session[key]==result[key],'ZIP session identity differs: '+key)
        proof=result['runtime_provenance'];need(session['pid']==proof['observed_pid'],'ZIP PID differs from direct process proof')
        worker=session['worker'];need(worker['lease_active'] is True and worker['worker_id']==proof['worker_id'] and worker['generation']==proof['worker_generation'],'ZIP worker lease/generation differs')
        need(session['firmware_provenance']==result['source']==json.loads(archive.read('firmware/uiflow-source.json')),'ZIP/session firmware source provenance differs')
        need(session['source_artifacts'][0]==sha(canonical(request['files'])),'ZIP source artifact is not canonical source JSON CAS')
        state=json.loads(archive.read('units/state.json'));runtime=json.loads(archive.read('units/runtime.json'));contract=json.loads(archive.read('units/contract.json'))
        need(state['session_id']==session['session_id'] and state['source']=='live' and state['contract_status']=='frozen','ZIP Unit state unavailable')
        need(len(state['units'])==1 and state['units'][0]['unit_id']==result['unit_id'] and state['units'][0]['available'],'ZIP Unit tree differs')
        need(runtime['attachments']==session['units'],'ZIP normalized wiring differs')
        need(contract['source_hashes']==state['contract_hashes'],'ZIP frozen contract hashes differ')
        serial=archive.read('serial.log').decode('utf-8');need(result['ready_marker'] in serial and not any(x in serial for x in FAILURES),'ZIP has no healthy guest path')
        for marker in result['required_markers']:need(re.search(r'(?m)^'+re.escape(marker)+r'\r?$',serial),'ZIP lacks required guest marker')
        metrics=frame_valid(archive.read('frames/current.png'))
        return {'session_id':session['session_id'],'pid':session['pid'],'files':names,'native_frame':metrics,'source_cas_sha256':session['source_artifacts'][0]}

def run_case(client,args,row,Observations,validate_io):
    case=row['unit_id'];directory=args.out_dir/case;request=load(directory/'source-request.json')
    result={**row,'expected_runtime_sha256':args.expected_runtime_sha256,'status':'FAIL','checks':{},'injections':[],'required_markers':[],'hardware_validation':'NOT RUN','started_at':now()};session_id=None;pid=None
    with HTTPRecorder(directory/'http'):
        try:
            inventory=client.json('units?device_id=cores3',via_ui=False);save(directory/'live-unit-inventory.json',inventory)
            descriptor=next(u for u in inventory['units'] if u['id']==case);need(descriptor['runtime']['status'] in ('implemented','validated'),'Unit is not admitted by the real service registry')
            firmware=client.json('firmware/uiflow',method='POST',payload=request,via_ui=False);save(directory/'firmware-response.json',firmware)
            result['source']=source_provenance(firmware,request);result['firmware_sha256']=firmware['sha256'];result['firmware_id']=firmware['firmware_id']
            artifact=client.json('artifacts/'+result['source']['artifact_id'],via_ui=False);save(directory/'source-artifact-metadata.json',artifact)
            need(artifact['artifact_id']==row['source_cas_sha256'] and artifact['size']==len(canonical(request['files'])),'source CAS artifact metadata differs')
            result['checks']['source_api_cas_base_files_and_firmware_identity']=True
            client.web_ui.call('prepare')
            payload={'device_id':'cores3','firmware_id':firmware['firmware_id'],'runtime':'qemu','ttl_seconds':1800,'ready_marker':row['ready_marker'].split()[0],'ready_timeout_seconds':180,'units':row['attachments'],'uiflow_source_sha256':result['source']['metadata']['source_sha256']}
            startup_negatives=[]
            for label,negative,code,kind in (
                ('missing-source-pin',{k:v for k,v in payload.items() if k!='uiflow_source_sha256'},400,'binding_required'),
                ('wrong-source-pin',{**payload,'uiflow_source_sha256':'0'*64},409,'binding_mismatch'),
            ):
                try:client.json('sessions',method='POST',payload=negative,via_ui=False)
                except RuntimeError as error:
                    need(f'HTTP {code} ' in str(error) and kind in str(error),'source pin negative returned the wrong error')
                    startup_negatives.append({'case':label,'request':negative,'error':str(error),'status':'REJECTED'})
                else:raise RuntimeError('session source pin negative was accepted')
            save(directory/'startup-pin-negatives.json',startup_negatives)
            pin_health=client.json('health',via_ui=False);save(directory/'after-pin-negative-health.json',pin_health)
            need(pin_health['capacity']['active_sessions']==0,'source pin negative started a session')
            result['checks']['source_pin_missing_and_mismatch_fail_before_runtime']=True
            save(directory/'session-request.json',payload);session=client.json('sessions',method='POST',payload=payload)
            session_id=result['session_id']=session['session_id'];save(directory/'created-session.json',session)
            print(f'{case}: visible source-API session {session_id}',flush=True)
            case_protocol(client,session_id,case,result,directory,Observations,validate_io)
            current=client.json(f'sessions/{session_id}',via_ui=False);pid=current['pid'];save(directory/'running-session.json',current)
            need(current['firmware_provenance']==result['source'] and current['source_artifacts'][0]==row['source_cas_sha256'],'live session source provenance differs')
            frame=client.raw(f'sessions/{session_id}/frame.png');(directory/'frame.png').write_bytes(frame);result['native_frame']=frame_valid(frame);result['checks']['nonempty_native_frame']=True
            client.web_ui.call('capture',session_id=session_id,phase='observed-units',screenshot=True)
        except Exception as error:result['error']=type(error).__name__+': '+str(error)
        finally:
            if session_id:
                try:
                    live=client.json(f'sessions/{session_id}',via_ui=False);pid=pid or live.get('pid');save(directory/'before-evidence-session.json',live)
                    data=client.raw(f'sessions/{session_id}/evidence');(directory/'evidence.zip').write_bytes(data)
                    result['evidence_sha256']=sha(data);result['evidence_summary']=validate_zip(data,result,request);result['checks']['zip_before_stop_and_source_guest_binding']=True
                except Exception as error:result['evidence_error']=str(error);result['checks']['zip_before_stop_and_source_guest_binding']=False
                try:
                    stopped=client.json(f'sessions/{session_id}?purge=0',method='DELETE');save(directory/'stop-response.json',stopped)
                    history=client.json(f'sessions/{session_id}',via_ui=False);save(directory/'retained-session.json',history)
                    need(stopped['state'] in ('stopped','failed') and history['state'] in ('stopped','failed'),'session did not stop with history')
                    need(history['flash_retained'] is False and history['last_frame_available'] is True,'mutable Flash retained or final frame lost')
                    need(history['firmware_sha256']==result.get('firmware_sha256') and history['firmware_provenance']==result.get('source'),'history provenance differs')
                    need(type(pid) is int and pid>0,'no owned QEMU PID was recorded')
                    deadline=time.monotonic()+15
                    while not pid_gone(pid) and time.monotonic()<deadline:time.sleep(0.1)
                    need(pid_gone(pid),'owned QEMU PID remains after stop')
                    frame=client.raw(f'sessions/{session_id}/frame.png',via_ui=False);(directory/'history-frame.png').write_bytes(frame);frame_valid(frame)
                    health=client.json('health',via_ui=False);save(directory/'cleanup-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'health still reports active sessions')
                    result['checks']['stopped_history_pid_exit_flash_release_health_idle']=True
                    result['cleanup']={'owned_pid':pid,'pid_gone':True,'flash_retained':False,'health_active_sessions':0}
                except Exception as error:result['cleanup_error']=str(error);result['checks']['stopped_history_pid_exit_flash_release_health_idle']=False
                try:
                    report=load(args.out_dir/'browser'/session_id/'web-report.json');result['browser']=check_browser(report,session_id,result['firmware_sha256']);result['checks']['real_dom_and_captured_http_match']=True
                    if case in CASES:need(report['actions'] and report['posts'],'input case has no actual UI gesture/POST')
                except Exception as error:result['browser_error']=str(error);result['checks']['real_dom_and_captured_http_match']=False
            result['finished_at']=now();result['status']='PASS' if session_id and not any(result.get(k) for k in ('error','evidence_error','cleanup_error','browser_error')) and result['checks'] and all(result['checks'].values()) else 'FAIL'
            save(directory/'result.json',result)
    print(f'{case}: {result["status"]} {result.get("error","")}',flush=True);return result

def expected_cardkb_stream(fixture):
    keys=fixture['keys'];normal=[row for row in keys if not row['modifier']];by_id={row['id']:row for row in keys}
    need(len(normal)==47 and len(keys)==50,'CardKB fixture must describe 47 nonmodifier and 3 modifier keys')
    expected=[row['normal'] for row in normal if row['normal']]
    for _,field in (('key-shift','shift'),('key-sym','sym'),('key-fn','fn')):
        expected.extend(v for v in (by_id['key-q'][field],by_id['key-q']['normal']) if v)
    for field in ('shift','sym','fn'):expected.extend(row[field] for row in normal if row[field])
    return expected+[65]

def replay_controls(directory,row,result,serial,fixture):
    case=row['unit_id'];props=result['unit_state']['units'][0]['properties'];contract=row['display_contract']
    need(row['flavor']==FLAVOR,'unidentified guest display flavor')
    required=[]
    def marker(text,offset=0):
        need(re.search(r'(?m)^'+re.escape(text)+r'\r?$',serial[offset:]) is not None,'guest control marker absent or stale: '+text)
        if text not in required:required.append(text)
    marker('CONTROL_PROBE_READY '+case)
    marker('SOURCE_CONTROL_GEOMETRY 320 240 1')
    fonts=re.findall(r'(?m)^SOURCE_CONTROL_FONT (\S+) ([\d.]+) (\d+)\r?$',serial)
    need(len(fonts)==1 and fonts[0][0]=='Montserrat12' and float(fonts[0][1])==1.0 and int(fonts[0][2])==15,'guest CoreS3 font metrics differ')
    expected_layout='SOURCE_CONTROL_LAYOUT '+' '.join(str(contract[k]) for k in ('x','y','width','body_y','line_height','body_rows','bottom','headers'))
    marker(expected_layout)
    need(all(type(props.get(k)) is int and props[k]>0 for k in ('transactions','read-bytes','written-bytes','input-events')),'guest I2C transaction/byte/input counters absent')
    steps=result['steps'];need(bool(steps),'control protocol has no actual UI injection steps')
    for step in steps:
        raw=(directory/step['before_file']).read_bytes();before=raw.decode('utf-8')
        need(len(before)==step['serial_offset'] and sha(raw)==step['before_sha256'] and serial.startswith(before),'fresh serial baseline was changed or exceeds final observed stream')
    if case=='joystick-v11':
        expected=[{'x-raw':31,'y-raw':240,'button-raw':1},{'x-raw':255,'y-raw':0,'button-raw':0}]
        need([step['values'] for step in steps]==expected,'Joystick test vectors were changed or omitted')
        for step in steps:
            values=step['values'];marker('CONTROL_JOYSTICK %d %d %d'%(values['x-raw'],values['y-raw'],values['button-raw']),step['serial_offset'])
        need(all(props[k]==v for k,v in expected[-1].items()),'Joystick QOM does not retain the second vector')
    elif case=='8encoder':
        marker('CONTROL_ENCODER8_REGISTER_WRITE -1234567 0');marker('CONTROL_ENCODER8_ADDRESS 66')
        counts=[1,-2,123456,-123456,2147483647,-2147483648,7,8];pressed=[True,False,True,False,False,True,False,True]
        expected={'counters':counts,'pressed':pressed,'switch-on':True}
        need(len(steps)==1 and steps[0]['values']==expected,'eight signed channels/button/switch vector changed or omitted')
        prefix='CONTROL_ENCODER8 %s %s 1'%(counts,[int(v) for v in pressed])
        matches=[line.rstrip('\r') for line in serial[steps[0]['serial_offset']:].splitlines() if line.startswith(prefix+' INC ')]
        need(matches,'8Encoder full fresh guest vector absent')
        increments=ast.literal_eval(matches[-1].split(' INC ',1)[1]);need(len(increments)==8 and all(type(v) is int and -2147483648<=v<=2147483647 for v in increments),'8Encoder increment register path not observed')
        marker(matches[-1],steps[0]['serial_offset'])
        need(props['counters']==counts and props['pressed']==pressed and props['switch-on'] is True,'8Encoder QOM vector differs')
        need(props['i2c-address']==0x42 and props['led-rgb']==[i*0x010203 for i in range(1,9)]+[0x192939],'8Encoder address or nine RGB triplets differ')
    elif case=='cardkb':
        marker('CONTROL_CARDKB_LEGACY 1')
        expected=expected_cardkb_stream(fixture);offset=result['cardkb_start_offset']
        need(type(offset) is int and 0<=offset<=len(serial),'CardKB stream origin is invalid')
        observed=[int(v) for v in re.findall(r'(?m)^CONTROL_CARDKB_KEY (\d+)\r?$',serial[offset:])]
        need(observed==expected,'CardKB exact four-table/one-shot/lock/keycode stream differs')
        need(result['cardkb_expected_stream']==expected,'runtime expected CardKB stream differs from independently rebuilt fixture oracle')
        need(steps[-1]['values']=={'keycode':65},'CardKB legacy byte input is absent')
        mode_counts={mode:0 for mode in (0,2,4,6)}
        # Each lock/unlock was independently read through the real HTTP API.
        for event in load(directory/'http/index.json'):
            if event.get('status')==200 and event['path'].endswith('/units'):
                value=load(directory/'http'/event['response_file'])
                mode=value.get('units',[{}])[0].get('properties',{}).get('modifier-mode')
                if mode in mode_counts:mode_counts[mode]+=1
        need(all(mode_counts[mode]>=1 for mode in (2,4,6)) and mode_counts[0]>=3,'CardKB locked modes or unlock-to-normal QOM evidence absent')
        report=load(directory.parent/'browser'/result['session_id']/'web-report.json')
        doubles=[a for a in report['actions'] if a.get('kind')=='real-mouse-double-click']
        modifiers={row['id']:row['index'] for row in fixture['keys'] if row['modifier']}
        need(len(doubles)==3 and {a['index'] for a in doubles}==set(modifiers.values()) and all(a['field']=='keys' and a['posts']==4 for a in doubles),'CardKB modifier locks lack three real down/up/down/up browser gestures')
    else:
        marker('CONTROL_RFID_CRC_VECTOR 1 05bf')
        uids=('04010203','04010203040506','04010203040506070809')
        expected=[{'uid-hex':uid,'card-present':True} for uid in uids]+[{'card-present':False}]
        need([step['values'] for step in steps]==expected,'RFID four/seven/ten UID and removal injections changed or omitted')
        for index,(uid,step) in enumerate(zip(uids,steps)):
            start_offset=step['serial_offset'];end_offset=steps[index+1]['serial_offset']
            need(type(start_offset) is int and type(end_offset) is int and 0<=start_offset<end_offset<=len(serial),'RFID per-UID input window is invalid')
            phase=serial[start_offset:end_offset];uid_marker='CONTROL_RFID_UID '+uid
            start=re.search(r'(?m)^'+re.escape(uid_marker)+r'\r?$',phase);need(start is not None,'fresh RFID UID absent: '+uid)
            phase=phase[start.start():]
            ordered=[uid_marker,'CONTROL_RFID_BAD_CRC 1','CONTROL_RFID_BAD_KEY 1','CONTROL_RFID_SECTOR_DENIED 1','CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40','CONTROL_RFID_HALT_DENIED 1','CONTROL_RFID_ANTENNA_OFF 1']
            position=0
            for text in ordered:
                match=re.search(r'(?m)^'+re.escape(text)+r'\r?$',phase[position:]);need(match is not None,'RFID per-UID ordered positive/negative missing: '+uid+' '+text)
                position+=match.end()
                if text not in required:required.append(text)
        marker('CONTROL_RFID_NO_CARD',steps[-1]['serial_offset']);need(props['card-present'] is False,'RFID removal QOM did not update')
    return {'status':'PASS','unit_id':case,'required_markers':required,'serial_bytes':len(serial.encode()),'fresh_ui_input_steps':len(steps),'display_flavor':FLAVOR,'physical_hardware':'NOT RUN'}


def check_saved(output):
    need((output/'SHA256SUMS').is_file(),'frozen artifact SHA256SUMS is absent')
    for line in (output/'SHA256SUMS').read_text().splitlines():
        expected,name=line.split('  ',1);target=(output/name).resolve();need(target.is_relative_to(output.resolve()) and sha(target.read_bytes())==expected,'frozen artifact checksum differs: '+name)
    tooling=load(output/'tooling-source-freeze.json')
    for name,expected in tooling.items():need(sha((output/'source-snapshot'/(name+'.txt')).read_bytes())==expected,'frozen tooling source differs: '+name)
    prepared=load(output/'prepared.json');results=[]
    for row in prepared['cases']:
        case=row['unit_id'];directory=output/case;request=load(directory/'source-request.json');result=load(directory/'result.json');firmware=load(directory/'firmware-response.json')
        need(result['status']=='PASS','case did not pass: '+case)
        # Verify saved caller files independently; API metadata is never the guest oracle.
        for name,text in request['files'].items():need((directory/'files'/name).read_bytes()==text.encode(),'frozen guest file bytes differ')
        source=source_provenance(firmware,request);need(source==result['source'],'saved source response differs')
        proof=load(output/'browser'/result['session_id']/'runtime-provenance.json');need(proof==result['runtime_provenance'] and proof['status']=='VERIFIED' and proof['runtime_binary_sha256']==result['expected_runtime_sha256'],'direct runtime proof differs')
        serial=(directory/'serial.txt').read_bytes().decode('utf-8');need(row['ready_marker'] in serial and not any(x in serial for x in FAILURES),'saved guest serial failed')
        replay_controls(directory,row,result,serial,load(output/'source-snapshot/platform/units/fixtures/cardkb-keymap.json.txt'))
        need(sha((directory/'evidence.zip').read_bytes())==result['evidence_sha256'],'ZIP bytes changed')
        validate_zip((directory/'evidence.zip').read_bytes(),result,request)
        with zipfile.ZipFile(directory/'evidence.zip') as archive:
            contract=json.loads(archive.read('units/contract.json'))
            for name,expected in contract['source_hashes'].items():need(tooling.get('platform/units/'+name)==expected,'ZIP Unit contract source is not the frozen local registry: '+name)
        with zipfile.ZipFile(directory/'evidence.zip') as archive:need(archive.read('serial.log').decode('utf-8').startswith(serial),'ZIP serial does not contain the observed guest serial prefix')
        frame_valid((directory/'frame.png').read_bytes());frame_valid((directory/'history-frame.png').read_bytes())
        check_browser(load(output/'browser'/result['session_id']/'web-report.json'),result['session_id'],result['firmware_sha256'])
        history=load(directory/'retained-session.json');health=load(directory/'cleanup-health.json');need(history['flash_retained'] is False and health['capacity']['active_sessions']==0,'cleanup evidence incomplete')
        need(result['cleanup']['pid_gone'] is True and result['cleanup']['owned_pid']==result['runtime_provenance']['observed_pid'],'PID cleanup record differs')
        # Every claimed direct API payload must have real HTTP transcript bytes.
        events=load(directory/'http/index.json')
        for event in events:
            data=(directory/'http'/event['response_file']).read_bytes();need(len(data)==event['response_size'] and sha(data)==event['response_sha256'],'actual HTTP response bytes changed')
        actual=[]
        for event in events:
            if event.get('status',0)//100==2:
                try:actual.append((event,json.loads((directory/'http'/event['response_file']).read_bytes())))
                except (ValueError,UnicodeDecodeError):pass
        need(any(e['method']=='POST' and e['path']=='/api/v1/firmware/uiflow' and v==firmware and json.loads((directory/'http'/e['request_file']).read_bytes())==request for e,v in actual),'firmware record has no matching real source API request/response')
        need(any(e['path'].endswith('/units') and v==result['unit_state'] for e,v in actual),'final QOM snapshot has no actual API response')
        for observation in load(directory/'observation-index.json'):
            if observation['kind']=='state':need(any(e['path'].endswith('/units') and v==load(directory/observation['file']) for e,v in actual),'controller observation has no actual HTTP response')
            elif observation['kind']=='qom':need(any(e['path'].endswith('/qom') and urllib.parse.parse_qs(e['query'])=={'path':[observation['path']],'property':[observation['property']]} and v.get('value')==observation['value'] for e,v in actual),'RMT controller sample has no actual QOM HTTP response')
        session_request=load(directory/'session-request.json');need(session_request['uiflow_source_sha256']==sha(canonical(request['files'])),'session request source pin differs')
        need(any(e['method']=='POST' and e['path']=='/api/v1/sessions' and v.get('session_id')==result['session_id'] and json.loads((directory/'http'/e['request_file']).read_bytes())==session_request for e,v in actual),'session has no matching real HTTP source-pin request/response')
        negatives=load(directory/'startup-pin-negatives.json');need(len(negatives)==2 and all(n['status']=='REJECTED' for n in negatives),'session source pin negatives absent')
        need(load(directory/'after-pin-negative-health.json')['capacity']['active_sessions']==0,'source pin negative executed a runtime')
        results.append({'unit_id':case,'session_id':result['session_id'],'status':'PASS'})
    return {'status':'PASS','cases':results,'scope':'source API + same-session guest/QOM/browser/evidence/cleanup; hardware NOT RUN'}

def freeze_checksums(output):
    paths=sorted(p for p in output.rglob('*') if p.is_file() and p.name!='SHA256SUMS' and '__pycache__' not in p.parts and p.suffix!='.pyc')
    (output/'SHA256SUMS').write_text(''.join(sha(p.read_bytes())+'  '+p.relative_to(output).as_posix()+'\n' for p in paths),encoding='utf-8')

def check_prepared(output):
    manifest=load(output/'prepared.json');rows=manifest['cases']
    need(manifest['status']=='PREPARED_NO_API_OR_RUNTIME' and manifest['binary_build_or_upload'] is False,'preparation overclaims execution or binary composition')
    need(rows and len({r['unit_id'] for r in rows})==len(rows) and {r['unit_id'] for r in rows}<=set(CASES),'prepared selection is empty, duplicated or unsupported')
    tooling=load(output/'tooling-source-freeze.json')
    for name,expected in tooling.items():
        frozen=output/'source-snapshot'/(name+'.txt');need(sha(frozen.read_bytes())==expected,'prepared tooling snapshot differs: '+name)
    for row in rows:
        directory=output/row['unit_id'];request=load(directory/'source-request.json');origins=load(directory/'guest-source-freeze.json')
        need(load(directory/'prepared.json')==row,'per-case and batch source contracts differ')
        need(row['status']=='PREPARED_NO_API_OR_RUNTIME' and row['flavor']==FLAVOR and row['device_id']=='cores3','wrong source preparation flavor/host/status')
        need(row['display_contract']==display_contract(row['unit_id']),'display contract differs')
        need(request['device_id']=='cores3' and request['expected_base_sha256']==BASE and set(request)=={'device_id','files','expected_base_sha256'},'source request is not the transparent admitted API payload')
        files=request['files'];need(sha(canonical(files))==row['source_cas_sha256'],'canonical caller source SHA differs')
        actual={p.relative_to(directory/'files').as_posix():p.read_bytes() for p in (directory/'files').rglob('*') if p.is_file()}
        need(set(actual)==set(files)==set(origins)==set(row['files']),'prepared source membership differs')
        for name,text in files.items():
            need(actual[name]==text.encode('utf-8') and row['files'][name]=={'sha256':sha(actual[name]),'size':len(actual[name])},'source bytes/size/hash differ: '+name)
            need(origins[name]['sha256']==sha(actual[name]),'source origin hash differs: '+name);ast.parse(text,filename=name)
        need(origins['main.py']['exact_reverse_verified'] is True and origins['main.py']['flavor']==FLAVOR,'display-only flavor is not reversible')
        need(files['probe_display.py']==DISPLAY_WRAPPER,'generated CoreS3 display observer changed')
        source=files['main.py']
        for before,after in reversed(DISPLAY_REPLACEMENTS):
            need(source.count(after)==1,'display-only flavor reverse context changed');source=source.replace(after,before)
        frozen_original=(output/'source-snapshot/tests/units/controls_probe/main.py.txt').read_bytes()
        need(source.encode()==frozen_original,'prepared guest changed controller/protocol code outside display flavor')
        proof=load(directory/'official-driver-proof.json')
        frozen_manifest=load(output/'source-snapshot/tests/units/controls_probe/control_drivers/source-manifest.json.txt')
        for name,record in proof.items():
            need(record==frozen_manifest[name.removeprefix('control_drivers/')],'official driver proof differs from frozen manifest')
            need(sha(actual[name])==record['sha256'],'official driver bytes changed')
        need(proof,'no official driver identity proof')
        need(len(canonical(request))<=1024*1024,'source HTTP JSON body exceeds its limit')
    need(not any(p.suffix.lower() in {'.bin','.elf','.rom','.pyc'} or '__pycache__' in p.parts for p in output.rglob('*') if p.is_file()),'preparation contains a binary/cache artifact')
    parity=verify_original_assertions()
    return {'status':'PREPARED_NO_API_OR_RUNTIME','cases':[row['unit_id'] for row in rows],'case_count':len(rows),'binary_build_or_upload':False,'guest_execution':False,'original_assertions':parity,'http_json_bytes':{row['unit_id']:len(canonical(load(output/row['unit_id']/'source-request.json'))) for row in rows}}

def offline_self_test(output):
    import socket,subprocess
    from unittest.mock import patch
    calls=[]
    def deny(kind):
        def blocked(*args,**kwargs):calls.append(kind);raise RuntimeError('self-test denied '+kind)
        return blocked
    original_write=pathlib.Path.write_bytes
    def write(path,data):
        if path.suffix.lower() in {'.bin','.elf','.rom'}:return deny('BIN_WRITE')(path,data)
        return original_write(path,data)
    with patch.object(socket,'socket',deny('SOCKET')),patch.object(urllib.request,'urlopen',deny('HTTP')),patch.object(subprocess,'Popen',deny('PROCESS')),patch.object(os,'system',deny('PROCESS')),patch.object(pathlib.Path,'write_bytes',write):
        # Prove the guards themselves reject before preparing anything.
        probes=[('SOCKET',lambda:socket.socket()),('HTTP',lambda:urllib.request.urlopen('http://127.0.0.1:8787/api/v1/health')),('PROCESS',lambda:subprocess.Popen(['true'])),('BIN_WRITE',lambda:(output/'must-not-exist.bin').write_bytes(b'forbidden'))]
        for kind,probe in probes:
            before=len(calls)
            try:probe()
            except RuntimeError as error:need('self-test denied '+kind in str(error),'guard did not block the intended operation')
            else:raise RuntimeError('self-test guard did not reject '+kind)
            need(len(calls)==before+1,'guard probe was not observed')
        guard_calls=list(calls);calls.clear()
        prepare(output,list(CASES));positive=check_prepared(output)
        target=output/CASES[0]/'files/main.py';original=target.read_bytes();target.write_bytes(original+b'\n# deliberately altered offline self-test\n')
        try:
            try:check_prepared(output)
            except RuntimeError:rejected_source_drift=True
            else:raise RuntimeError('checker accepted changed guest source bytes')
        finally:target.write_bytes(original)
        positive=check_prepared(output);need(not calls,'offline preparation/check unexpectedly attempted API/process/BIN')
    report={'status':'PASS','scope':'pure offline source request preparation/check only; no guest/runtime/hardware claim','cases':list(CASES),'guard_probes_blocked':guard_calls,'unexpected_api_process_bin_calls':calls,'source_drift_negative':'REJECTED','original_assertion_parity':verify_original_assertions(),'preparation':positive}
    save(output/'self-test.json',report);freeze_checksums(output);return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',type=pathlib.Path,required=True)
    parser.add_argument('--case',choices=(*CASES,'all'),action='append')
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--api-url',default='http://127.0.0.1:8787')
    parser.add_argument('--expected-runtime-sha256',default=RUNTIME)
    args=parser.parse_args();args.out_dir=guarded_directory(args.out_dir)
    need(not (args.execute and (args.prepare_only or args.check)),'execute cannot be combined with offline modes')
    if args.self_test:print(json.dumps(offline_self_test(args.out_dir),ensure_ascii=False,indent=2));return
    if args.check:
        checker=check_saved if (args.out_dir/'batch-result.json').is_file() else check_prepared
        print(json.dumps(checker(args.out_dir),ensure_ascii=False,indent=2));return
    cases=list(CASES) if not args.case or 'all' in args.case else list(dict.fromkeys(args.case))
    need(__debug__,'original control assertions require Python without -O')
    prepared=prepare(args.out_dir,cases)
    check_prepared(args.out_dir)
    if not args.execute:
        freeze_checksums(args.out_dir)
        print(json.dumps({'status':'PREPARED_NO_API_OR_RUNTIME','cases':cases,'out_dir':str(args.out_dir),'source_request_count':len(prepared)},ensure_ascii=False));return
    need(os.environ.get('M5_UNIT_WEB_BRIDGE')=='1','execution requires explicit M5_UNIT_WEB_BRIDGE=1')
    need(re.fullmatch(r'[0-9a-f]{64}',args.expected_runtime_sha256) is not None,'runtime SHA must be exact')
    need(urllib.parse.urlparse(args.api_url).hostname in {'127.0.0.1','localhost','::1'},'local PID evidence requires localhost API')
    os.environ['M5_UNIT_WEB_BRIDGE_OUT']=str(args.out_dir/'browser');os.environ['M5_UNIT_EXPECT_RUNTIME_SHA256']=args.expected_runtime_sha256
    sys.path[:0]=[str(UNIT),str(ROOT/'platform/tools'),str(ROOT/'platform/tests')]
    from run_service_cases import Client
    Observations=validate_io=None
    class SourceOnlyClient(Client):
        def raw(self,path,method='GET',**kwargs):
            need(not (method in ('POST','PUT') and path.split('?')[0] in ('artifacts','firmware')),'binary artifact/firmware intake is forbidden in source acceptance')
            return super().raw(path,method=method,**kwargs)
    client=SourceOnlyClient(args.api_url);results=[]
    try:
        with HTTPRecorder(args.out_dir/'batch-http'):
            health=client.json('health',via_ui=False);save(args.out_dir/'initial-health.json',health);need(health['ok'] is True and health['capacity']['active_sessions']==0,'service must be idle before acceptance')
            source_negatives(client,load(args.out_dir/cases[0]/'source-request.json'),args.out_dir)
        for row in prepared:
            result=run_case(client,args,row,Observations,validate_io);results.append(result)
            if result.get('cleanup_error'):break
    finally:
        client.web_ui.close()
        save(args.out_dir/'batch-result.json',{'finished_at':now(),'status':'PASS' if len(results)==len(cases) and all(r['status']=='PASS' for r in results) else 'FAIL','cases':[{k:r.get(k) for k in ('unit_id','session_id','status','error','cleanup_error')} for r in results]})
        freeze_checksums(args.out_dir)
    need(len(results)==len(cases) and all(r['status']=='PASS' for r in results),'one or more real source-API cases failed')
    print(json.dumps(check_saved(args.out_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
