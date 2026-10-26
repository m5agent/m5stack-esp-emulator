"""Synthetic offline checker regression only; no Client, API, guest or process."""
from pathlib import Path
import copy, hashlib, importlib.util, importlib.machinery, json
HERE=Path(__file__).resolve().parent
OUT=HERE/'rfid-window-checker-r2'
OUT.mkdir(exist_ok=False)
def module(name,path):
    loader=importlib.machinery.SourceFileLoader(name,str(path));spec=importlib.util.spec_from_loader(name,loader);value=importlib.util.module_from_spec(spec);loader.exec_module(value);return value
old=module('controls_checker_v1',HERE/'freeze-v1/run_source_controls.py.txt')
new=module('controls_checker_v2',HERE/'run_source_controls.py')
UIDS=('04010203','04010203040506','04010203040506070809')
NEGATIVES=('CONTROL_RFID_BAD_CRC 1','CONTROL_RFID_BAD_KEY 1','CONTROL_RFID_SECTOR_DENIED 1','CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40','CONTROL_RFID_HALT_DENIED 1','CONTROL_RFID_ANTENNA_OFF 1')
PREFIX='\r\n'.join(('CONTROL_PROBE_READY rfid2','SOURCE_CONTROL_GEOMETRY 320 240 1','SOURCE_CONTROL_FONT Montserrat12 1.0 15','SOURCE_CONTROL_LAYOUT 6 6 308 24 16 3 72 1','CONTROL_RFID_CRC_VECTOR 1 05bf'))+'\r\n'
def fixture(label,missing=None,reordered=False):
    directory=OUT/label;directory.mkdir();serial=PREFIX;steps=[]
    for index,uid in enumerate(UIDS):
        name=f'step-{index}-before.txt';(directory/name).write_bytes(serial.encode())
        steps.append({'values':{'uid-hex':uid,'card-present':True},'serial_offset':len(serial),'before_file':name,'before_sha256':hashlib.sha256(serial.encode()).hexdigest()})
        lines=['CONTROL_RFID_UID '+uid,*NEGATIVES]
        if index==1 and missing:lines.remove(missing)
        if index==1 and reordered:lines[2],lines[3]=lines[3],lines[2]
        serial+='\r\n'.join(lines)+'\r\n'
    name='step-3-before.txt';(directory/name).write_bytes(serial.encode())
    steps.append({'values':{'card-present':False},'serial_offset':len(serial),'before_file':name,'before_sha256':hashlib.sha256(serial.encode()).hexdigest()})
    serial+='CONTROL_RFID_NO_CARD\r\n';(directory/'serial.txt').write_bytes(serial.encode())
    row={'unit_id':'rfid2','flavor':new.FLAVOR,'display_contract':new.display_contract('rfid2')}
    result={'steps':steps,'unit_state':{'units':[{'properties':{'transactions':100,'read-bytes':50,'written-bytes':50,'input-events':4,'card-present':False}}]}}
    (directory/'fixture.json').write_text(json.dumps({'category':'SYNTHETIC_OFFLINE_CHECKER_FIXTURE','guest_executed':False,'row':row,'result':result},indent=2)+'\n')
    return directory,row,result,serial
results=[]
def replay(which,args):
    try:which.replay_controls(*args,{})
    except RuntimeError as error:return {'accepted':False,'error':str(error)}
    return {'accepted':True}
args=fixture('complete-three-uid-phases')
assert replay(old,args)['accepted'] and replay(new,args)['accepted']
results.append({'case':'complete-three-uid-phases','old':'ACCEPTED','new':'ACCEPTED'})
for index,missing in enumerate(NEGATIVES):
    args=fixture(f'middle-missing-{index}',missing)
    before=replay(old,args);after=replay(new,args)
    assert before['accepted'],('old checker no longer reproduces cross-UID borrowing',missing,before)
    assert not after['accepted'],('new checker borrowed later UID negative',missing)
    results.append({'case':f'middle-missing-{index}','missing_marker':missing,'old':before,'new':after})
args=fixture('middle-uid-marker-missing','CONTROL_RFID_UID '+UIDS[1]);assert not replay(new,args)['accepted']
results.append({'case':'middle-uid-marker-missing','new':replay(new,args)})
args=fixture('middle-negatives-reordered',reordered=True);assert not replay(new,args)['accepted']
results.append({'case':'middle-negatives-reordered','new':replay(new,args)})
report={'status':'PASS','category':'SYNTHETIC_OFFLINE_CHECKER_REGRESSION','guest_executed':False,'device_service_contacted':False,'client_instantiated':False,'binary_built':False,'old_harness_sha256':hashlib.sha256((HERE/'freeze-v1/run_source_controls.py.txt').read_bytes()).hexdigest(),'new_harness_sha256':hashlib.sha256((HERE/'run_source_controls.py').read_bytes()).hexdigest(),'tests':results}
(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
