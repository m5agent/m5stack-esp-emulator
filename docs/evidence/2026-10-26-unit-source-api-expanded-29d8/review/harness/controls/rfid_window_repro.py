"""Pure checker counterexample, synthetic local text; never runtime evidence."""
from pathlib import Path
from importlib.machinery import SourceFileLoader
import hashlib
import json
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
TARGET=REPO/'.work/unit-source-controls-expanded-20261026/run_source_controls.py'

def sha(data): return hashlib.sha256(data).hexdigest()
def exercise(path,tag):
    module=SourceFileLoader('controls_cross_review_'+tag,str(path)).load_module()
    out=HERE/tag;out.mkdir(exist_ok=True)
    contract=module.display_contract('rfid2')
    header='CONTROL_PROBE_READY rfid2\nSOURCE_CONTROL_GEOMETRY 320 240 1\nSOURCE_CONTROL_FONT Montserrat12 1.0 15\nSOURCE_CONTROL_LAYOUT '+' '.join(str(contract[k]) for k in ('x','y','width','body_y','line_height','body_rows','bottom','headers'))+'\nCONTROL_RFID_CRC_VECTOR 1 05bf\n'
    uids=('04010203','04010203040506','04010203040506070809')
    checks='\n'.join(('CONTROL_RFID_BAD_CRC 1','CONTROL_RFID_BAD_KEY 1','CONTROL_RFID_SECTOR_DENIED 1','CONTROL_RFID_BLOCK 1 1 1 3132333435363738393a3b3c3d3e3f40','CONTROL_RFID_HALT_DENIED 1','CONTROL_RFID_ANTENNA_OFF 1'))+'\n'
    outcomes={}
    for healthy in (True,False):
        serial=header;steps=[];scenario=out/('healthy' if healthy else 'missing-first-two-negatives');scenario.mkdir(exist_ok=True)
        for index,uid in enumerate(uids):
            before=serial;filename=f'{index}-before.txt';(scenario/filename).write_bytes(before.encode())
            steps.append({'values':{'uid-hex':uid,'card-present':True},'serial_offset':len(before),'before_file':filename,'before_sha256':sha(before.encode())})
            serial+='CONTROL_RFID_UID '+uid+'\n'
            if healthy or index==2:serial+=checks
        before=serial;(scenario/'3-before.txt').write_bytes(before.encode());steps.append({'values':{'card-present':False},'serial_offset':len(before),'before_file':'3-before.txt','before_sha256':sha(before.encode())});serial+='CONTROL_RFID_NO_CARD\n'
        (scenario/'serial.txt').write_bytes(serial.encode())
        result={'unit_id':'rfid2','flavor':module.FLAVOR,'display_contract':contract,'unit_state':{'units':[{'properties':{'transactions':1,'read-bytes':1,'written-bytes':1,'input-events':4,'card-present':False}}]},'steps':steps}
        try:
            replay=module.replay_controls(scenario,result,result,serial,{})
            outcomes[scenario.name]={'accepted':True,'replay':replay}
        except Exception as error:
            outcomes[scenario.name]={'accepted':False,'error':type(error).__name__+': '+str(error)}
    return {'harness_sha256':sha(path.read_bytes()),'synthetic_checker_only':True,'api_calls':0,'guest_execution':False,'outcomes':outcomes}

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'baseline'
    snapshot=HERE/'v1-harness.py.txt'
    if mode=='baseline':
        if not snapshot.exists():
            old=TARGET.parent/'freeze-v1/run_source_controls.py.txt'
            snapshot.write_bytes((old if old.exists() else TARGET).read_bytes())
        result=exercise(snapshot,'baseline')
    else:result=exercise(TARGET,'current')
    (HERE/(mode+'-rfid-window.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
