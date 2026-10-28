"""Verify QR geometry patch with identical guest input and independent PNG checks."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile
from check_ui_frame import check_frame


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(root):
    report_path=root/'report.json';report=json.loads(report_path.read_text())
    rows=[]
    for line in (root/'serial.txt').read_text().splitlines():
        if line.startswith('M5EMU_UI_FRAME_ORACLE '):
            row=json.loads(line.split(' ',1)[1]);row.update(check_frame((root/'frame.png').read_bytes(),row['oracle'],row.get('tolerance',8)));rows.append(row)
    assert len(rows)==5,'completion requires all five explicit method/domain observations'
    assert report['status']=='EXECUTED'
    assert sha(root/'frame.png')==report['frame_sha256']
    assert sha(root/'evidence.zip')==report['evidence_sha256']
    assert sha(root/'uiflow2-ui-test.bin')==report['firmware_sha256']
    with zipfile.ZipFile(root/'evidence.zip') as archive:assert archive.testzip() is None
    cleanup=report['cleanup']
    assert cleanup['terminal_state']=='stopped' and all(cleanup[k]for k in ('runtime_pid_gone','history_preserved','companions_cleanup_complete'))
    result={key:report[key] for key in ('status','device_id','session_id','base_sha256','source_sha256','firmware_sha256','runtime_binary_sha256','frame_sha256','evidence_sha256','cleanup')}
    result.update(report=str(report_path),report_sha256=sha(report_path),zip_crc_valid=True,firmware_hash_matches=True,results=rows,counts=dict(Counter(row['status']for row in rows)))
    (root/'frame-oracles.json').write_text(json.dumps(rows,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('stock','preimage','candidate'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--build-receipt',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    lanes={name:evaluate(getattr(args,name))for name in ('stock','preimage','candidate')}
    assert len({row['source_sha256']for row in lanes.values()})==1
    assert len({row['runtime_binary_sha256']for row in lanes.values()})==1
    for name,run in lanes.items():
        expected=['FRAME_PASS','FAIL','FRAME_PASS','FAIL','FRAME_PASS'] if name!='candidate'else['FRAME_PASS']*5
        assert [row['status']for row in run['results']]==expected,(name,run['counts'])
    build=json.loads(args.build_receipt.read_text())
    assert build['base_sha256']==lanes['preimage']['base_sha256']
    assert build['candidate_full_flash_sha256']==lanes['candidate']['base_sha256']
    assert all(build[key]for key in ('outside_application_unchanged','original_source_unchanged','original_library_unchanged'))
    summary={'schema_version':1,'validation':'virtual-device validation','hardware_validation':'NOT RUN','status':'TARGETED_GEOMETRY_PATCH_VERIFIED',
             'scope':'CoreS3 QR relocation, shrinking and unchanged-geometry version4 only. Stock and matching SDK ghost failures remain separate. Candidate stacks 0014 and 0019; this guest never calls setText.',
             'matching_preimage_identity':'The complete HCI-transport SDK cache is bound to its own original application/full-flash SHA; it is distinct from the historical 7ce5ca SDK build.',
             'build_receipt':str(args.build_receipt),'build_receipt_sha256':sha(args.build_receipt),'compiled_source_sha256':build['compiled_source_sha256'],
             'patch_stack':['0014-widgets-qrcode-text','0019-widgets-qrcode-geometry'],'lanes':lanes}
    args.out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({name:row['counts']for name,row in lanes.items()}))


if __name__=='__main__':main()
