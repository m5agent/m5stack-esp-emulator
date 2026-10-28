#!/usr/bin/env python3
"""Bind public helper assertions to retained serial, frame and cleanup evidence."""
from __future__ import annotations
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from PIL import Image
from summarize_system_results import json_records


def verify(directory):
    execution=json.loads((directory/'report.json').read_text());raw=(directory/'serial.txt').read_text(errors='replace')
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    frame=Image.open(directory/'frame.png').convert('RGB')
    red=sum(red>80 and red>2*green and red>2*blue for red,green,blue in frame.getdata())
    frame_ok=red>=30 and 'ValueError: OWNED_API_SWEEP_ERROR_73' in raw
    oracle={'frame_sha256':digest(directory/'frame.png'),'red_glyph_pixels':red,
        'exact_serial_exception_present':'ValueError: OWNED_API_SWEEP_ERROR_73'in raw,
        'status':'PASS'if frame_ok else'FAIL','scope':'original error-helper serial text and LCD red glyph output'}
    target=directory/'helper-oracle.json';target.write_text(json.dumps(oracle,indent=2)+'\n')
    evidence={'execution_report_sha256':digest(directory/'report.json'),'serial_sha256':digest(directory/'serial.txt'),
        'frame_sha256':digest(directory/'frame.png'),'helper_oracle_sha256':digest(target),
        'evidence_zip_sha256':execution.get('evidence_sha256'),'firmware_sha256':execution.get('firmware_sha256'),
        'runtime_binary_sha256':execution.get('runtime_binary_sha256')}
    complete=execution.get('status')=='EXECUTED'and bool(execution.get('evidence_sha256'))and execution.get('cleanup',{}).get('runtime_pid_gone')is True
    cases=list(json_records(raw,'SYSTEM_API'))
    for row in cases:
        if row['api']=='utility.print_error_msg':
            row['status']='PASS'if frame_ok else'FAIL'
            row['oracle']='exact original exception appears on serial and independently retained framebuffer contains red error glyph pixels on the cleared black canvas'
        row.update(required_evidence_met=complete and row['status']=='PASS',evidence_refs=evidence)
    result={'schema_version':1,'device_id':execution['device_id'],'firmware_lane':execution.get('firmware_lane','stock-frozen'),
        'cases':cases,'counts':dict(Counter(row['status']for row in cases)),
        'status':'FAIL'if any(row['status']in{'FAIL','ERROR'}for row in cases)else'PASS'}
    (directory/'protocol-results.json').write_text(json.dumps(result,indent=2)+'\n')
    return {'device_id':result['device_id'],'counts':result['counts'],'frame_oracle':oracle}


def verify_factories(directory):
    execution=json.loads((directory/'report.json').read_text());raw=(directory/'serial.txt').read_text(errors='replace')
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    expected=[0xa1&31,(0xa1>>5)&3,0xa1>>7]
    cases=list(json_records(raw,'SYSTEM_API'))
    oracle={'input':0xa1,'normalized_recipient_type_direction':expected,
        'basis':'USB bmRequestType normalized recipient/type/direction bit fields',
        'correction':'early guest assertion used unshifted masks in a different order; actual retained return is checked independently'}
    path=directory/'factory-helper-oracle.json';path.write_text(json.dumps(oracle,indent=2)+'\n')
    for row in cases:
        if row['api']=='usb.device.hid.split_bmRequestType':
            row['guest_status']=row['status'];row['status']='PASS'if row['value']==expected else'FAIL'
            row['oracle']='actual HID helper return equals independent normalized USB recipient/type/direction bit fields; original incorrect guest assertion is retained as guest_status'
        row['required_evidence_met']=(row['status']=='PASS'and execution['status']=='EXECUTED'
            and bool(execution.get('evidence_sha256'))and execution['cleanup']['runtime_pid_gone']is True)
        row['evidence_refs']={'execution_report_sha256':digest(directory/'report.json'),'serial_sha256':digest(directory/'serial.txt'),
            'evidence_zip_sha256':execution.get('evidence_sha256'),'firmware_sha256':execution['firmware_sha256'],
            'runtime_binary_sha256':execution.get('runtime_binary_sha256'),'helper_oracle_sha256':digest(path)}
    report={'device_id':execution['device_id'],'firmware_lane':execution.get('firmware_lane','stock-frozen'),'cases':cases,
        'counts':dict(Counter(row['status']for row in cases))}
    (directory/'protocol-results.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'device_id':report['device_id'],'counts':report['counts']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--kind',choices=('helpers','factories'),default='helpers')
    args=parser.parse_args()
    print(json.dumps((verify_factories if args.kind=='factories'else verify)(args.run),indent=2))
