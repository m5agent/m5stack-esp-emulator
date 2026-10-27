#!/usr/bin/env python3
"""Portable verification of this unchanged matrix round and layered host evidence."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib
ROOT=Path(__file__).resolve().parent

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(name):return json.loads((ROOT/name).read_text())
def private_patterns(raw):
    patterns={
        'mac-literal':rb'(?i)(?<![a-f0-9])(?:[a-f0-9]{2}:){5}[a-f0-9]{2}(?![a-f0-9])',
        'private-key':rb'-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----',
        'long-bearer':rb'(?i)Bearer [a-z0-9._~+/-]{24,}',
        'url-userinfo':rb'https?://[^\s/"\x27]+:[^\s/"\x27]+@',
    }
    return [name for name,pattern in patterns.items() if re.search(pattern,raw)]

def png(raw,pixel=None):
    assert raw.startswith(b'\x89PNG\r\n\x1a\n')
    offset=8;chunks=[];data=[];ihdr=None
    while offset<len(raw):
        length=struct.unpack('>I',raw[offset:offset+4])[0];kind=raw[offset+4:offset+8]
        body=raw[offset+8:offset+8+length];crc=struct.unpack('>I',raw[offset+8+length:offset+12+length])[0]
        assert zlib.crc32(kind+body)&0xffffffff==crc
        assert kind not in (b'tEXt',b'iTXt',b'zTXt')
        if kind==b'IHDR':ihdr=struct.unpack('>IIBBBBB',body)
        if kind==b'IDAT':data.append(body)
        chunks.append(kind.decode());offset+=12+length
    assert offset==len(raw) and chunks[-1]=='IEND' and ihdr is not None
    width,height,depth,color,compression,filtermethod,interlace=ihdr
    info={'size':[width,height],'chunks':chunks,'crc':'PASS','text_chunks':False}
    if pixel is not None:
        assert (depth,color,compression,filtermethod,interlace)==(8,2,0,0,0)
        x,y=pixel;assert 0<=x<width and 0<=y<height
        decoded=zlib.decompress(b''.join(data));stride=width*3;assert len(decoded)==height*(stride+1)
        previous=bytearray(stride)
        for row in range(y+1):
            start=row*(stride+1);filtertype=decoded[start];current=bytearray(decoded[start+1:start+1+stride]);assert filtertype in range(5)
            for col in range(stride):
                left=current[col-3] if col>=3 else 0;up=previous[col];upperleft=previous[col-3] if col>=3 else 0
                if filtertype==1:add=left
                elif filtertype==2:add=up
                elif filtertype==3:add=(left+up)//2
                elif filtertype==4:
                    prediction=left+up-upperleft;a=abs(prediction-left);b=abs(prediction-up);c=abs(prediction-upperleft)
                    add=left if a<=b and a<=c else up if b<=c else upperleft
                else:add=0
                current[col]=(current[col]+add)&255
            previous=current
        info['pixel']=list(previous[x*3:x*3+3])
    return info

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-originals',action='store_true')
    parser.add_argument('--repo-root',type=Path)
    args=parser.parse_args()
    if args.check_originals and args.repo_root is None:parser.error('--repo-root is needed with --check-originals')
    index=load('index.json');records=index['records'];fingerprints=index['fingerprints']
    names=[r['archive_path'] for r in records];assert len(names)==len(set(names))
    actual={str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file()}
    assert actual==set(names)|{'index.json'},sorted(actual^(set(names)|{'index.json'}))
    png_count=0
    for item in records:
        name=item['archive_path'];assert not Path(name).is_absolute() and '..' not in Path(name).parts
        p=ROOT/name;assert p.is_file() and not p.is_symlink()
        raw=p.read_bytes();assert len(raw)==item['archive_bytes'] and sha(raw)==item['archive_sha256'],name
        assert p.suffix.lower() not in {'.bin','.rom','.mpy','.zip','.ppm','.pcm','.rmt','.img','.a','.o','.pyc'}
        if item['classification']=='original-bytes':
            assert item['source_bytes']==len(raw) and item['source_sha256']==sha(raw)
        else:assert item['classification']=='generated-after-run'
        if item.get('format')=='original-png':
            assert png(raw)==item['png'];png_count+=1
        else:
            raw.decode('utf-8');assert not private_patterns(raw),(name,private_patterns(raw));assert b'\0' not in raw
    assert png_count==134
    assert not private_patterns((ROOT/'index.json').read_bytes())
    for item in fingerprints:
        assert item['classification']=='fingerprint-only' and item['source_bytes']>=0
        assert re.fullmatch('[0-9a-f]{64}',item['source_sha256'])
    matrix_records=[r for r in records if r.get('category')=='actual-matrix-round']
    matrix_fingerprints=[r for r in fingerprints if r.get('category')=='actual-matrix-round']
    assert len(matrix_records)==402 and len(matrix_fingerprints)==433
    summary=load('matrix/originals/summary.json');results=summary['results'];counts=Counter(r['status'] for r in results.values())
    assert len(results)==67 and counts=={'PASS':66,'FAIL':1}
    assert [name for name,r in results.items() if r['status']=='FAIL']==['core2-imu']
    assert all(r['attempts']==1 and r['retry_used'] is False for r in results.values())
    integrity=load('matrix/after-run-integrity.json');case_checks={r['case']:r for r in integrity['case_checks']}
    assert set(case_checks)==set(results) and integrity['actual_round_status']=='FAIL'
    groups={r['category']:r for r in integrity['runtimes']}
    xtensa=groups['xtensa-route-history-runtime'];c6=groups['riscv32-independent-runtime']
    assert len(xtensa['cases'])==62 and len(c6['cases'])==5 and set(xtensa['cases']).isdisjoint(c6['cases'])
    assert xtensa['sha256']=='3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1'
    assert c6['sha256']=='ff6c2ef71e83253ef35ccc2ef5aa42243270f6a397b169a9af549b47d5ca09c0'
    image_fingerprints={Path(r['source_path']).parent.name:r for r in matrix_fingerprints if Path(r['source_path']).name=='uiflow2-ui-test.bin'}
    assert len(image_fingerprints)==67
    for cid,result in results.items():
        check=case_checks[cid];assert check['original_status']==result['status'] and check['attempts']==1 and not check['retry_used']
        raw=(ROOT/'matrix/originals'/(cid+'.stdout')).read_bytes();match=re.search(rb'^sha256: ([0-9a-f]{64})$',raw,re.M);assert match
        assert match.group(1).decode()==check['launch_composed_sha256']
        assert image_fingerprints[cid]['source_sha256']==check['postrun_mutable_flash_sha256']
        assert check['launch_and_postrun_flash_sha_equal']==(check['launch_composed_sha256']==check['postrun_mutable_flash_sha256'])
        assert check['base_firmware_sha256']==result['reference_layout']['base_firmware_sha256']
        cmd=result['command'];expected=list(map(int,cmd[cmd.index('--expected-size')+1].split('x')))
        assert Path(cmd[1]).name=='run_profile_ui_test.py'
        for frame in ('before.png','after.png'):assert png((ROOT/'matrix/originals'/cid/frame).read_bytes())['size']==expected
    differences=[cid for cid in results if not case_checks[cid]['launch_and_postrun_flash_sha_equal']]
    assert differences==integrity['mutable_flash_hash_differences']==['sticks3-ir','sticks3-ir-rx','stackchan-peripherals','atoms3r-ir','cardputer-adv-ir','papercolor-ir']
    core2=load('matrix/core2-imu-failure-observation.json');serial=(ROOT/core2['serial_source']).read_bytes()
    assert core2['original_case_status']=='FAIL' and core2['guest_exit_code']==0 and sha(serial)==core2['serial_source_sha256']
    assert 'rgb=(0,0,0)' in core2['frame_oracle_output']
    windows=core2['exact_ascii_byte_windows'];assert len(windows)==3
    for window in windows:
        raw=serial[window['byte_offset']:window['byte_offset']+window['byte_length']]
        assert raw.decode('ascii')==window['ascii'] and sha(raw)==window['sha256']
    assert windows[-1]['ascii']=='CORE2_IMU_VALUES a=0.25,-0.50,0.75 g=10.0,-20.0,30.0'
    for pixel in load('matrix/frame-pixel-observation.json')['pixels']:
        raw=(ROOT/'matrix/originals'/pixel['path']).read_bytes();assert sha(raw)==pixel['sha256'] and png(raw,tuple(pixel['at']))['pixel']==pixel['rgb']
    paper=load('matrix/papercolor-command-observation.json');assert paper['command']==results['papercolor-rgb']['command'] and paper['original_case_status']=='PASS'
    assert paper['command_field_is_profile_runner'] and not paper['command_field_is_ws2812_checker']
    assert 'WS2812 PASS' in paper['original_validation'] and 'PASS PaperColor RGB marker' in paper['original_validation']
    old=load('unit-host-22/before/receipt.json');new=load('unit-host-22/after/receipt.json')
    assert old['status']=='FAIL' and new['status']=='PASS'
    assert old['checks']['summary_command_is_ws2812_checker_argv'] and not old['checks']['summary_command_is_actual_profile_launch_argv']
    assert new['checks']['summary_command_is_actual_profile_launch_argv'] and not new['checks']['summary_command_is_ws2812_checker_argv']
    assert all(load('unit-host-22/comparison.json')['checks'].values())
    old_source=(ROOT/'unit-host-22/before/runner.py.txt').read_bytes();new_source=(ROOT/'unit-host-22/after/runner.py.txt').read_bytes()
    assert new_source.count(b'validation_command')==3 and new_source.replace(b'validation_command',b'command')==old_source
    assert sha(new_source)==paper['runner_sha256_after_run']==new['runner_sha256']=='f2c4d784218f482bca380a2781b6b10c349bc3d81b8d7dcd190cd131f8a11f60'
    assert sha((ROOT/'source-snapshots/tests/uiflow2/run_peripheral_matrix.py.txt').read_bytes())==new['runner_sha256']
    platform=load('platform/root-verification.json')
    for key,filename,count in [('full','platform/full.log',1220),('narrow','platform/narrow.log',24)]:
        raw=(ROOT/filename).read_bytes();assert sha(raw)==platform['tests'][key]['sha256']
        assert re.search(rb'Ran '+str(count).encode()+rb' tests in [0-9.]+s\s+OK\s*$',raw)
    assert load('matrix/run-attestation.json')['authoritative_terminal_exit_code']==1
    assert load('archive-diagnostics/attempt-r1-failure.json')['status']=='FAIL' and load('archive-diagnostics/attempt-r2-failure.json')['status']=='FAIL'
    ocr=load('png-privacy/receipt.json');assert ocr['status']=='PASS' and len(ocr['images'])==134 and all(r['exit_code']==0 and not r['findings'] for r in ocr['images'])
    for item in ocr['images']:assert sha((ROOT/'matrix/originals'/item['image_path']).read_bytes())==item['image_sha256']
    report={'archive_integrity':'PASS','host_platform_tests':'1220 + 24 PASS','unit_host_22_old_mock':'FAIL_RETAINED','unit_host_22_new_mock':'PASS','actual_full_matrix':'FAIL','matrix_cases':67,'matrix_pass':66,'matrix_fail':1,'failed_case':'core2-imu','xtensa_cases':62,'independent_c6_cases':5,'png_originals':134,'postrun_mutable_flash_hash_differences':6,'original_records':len(records),'fingerprint_only_inputs':len(fingerprints),'hardware_execution':'NOT RUN'}
    if args.check_originals:
        total=0
        for item in records+fingerprints:
            if 'source_path' not in item:continue
            p=Path(item['source_path']);p=p if p.is_absolute() else args.repo_root/p;raw=p.read_bytes()
            assert len(raw)==item['source_bytes'] and sha(raw)==item['source_sha256'],str(p);total+=1
        report['original_inputs_matched']=total
    print(json.dumps(report,sort_keys=True))
if __name__=='__main__':main()
