#!/usr/bin/env python3
"""Independent owned-tone spectrum and duration for original ADF player output."""
from __future__ import annotations
import argparse,array,hashlib,json,sys,zipfile
from collections import Counter
from pathlib import Path
from verify_audio_wrappers import analyze


def verify(directory):
    report=json.loads((directory/'protocol-results.json').read_text());case=report['audio_case']
    frequency={'raw':660,'tone':880,'file':990}[case]
    with zipfile.ZipFile(directory/'evidence.zip')as archive:
        raw=archive.read('audio/speaker.pcm')if 'audio/speaker.pcm'in archive.namelist()else b''
    if raw:
        if len(raw)%4:raise ValueError('speaker capture is not complete stereo s16 frames')
        samples=array.array('h',raw)
        if sys.byteorder!='little':samples.byteswap()
        mono=array.array('h',(samples[index]for index in range(0,len(samples),2)))
        result=analyze(mono.tobytes(),48000,frequency,expected_seconds=1 if case in{'raw','tone'}else None)
        result['stereo_channels_identical']=all(samples[index]==samples[index+1]for index in range(0,len(samples),2))
        result['capture_sha256']=hashlib.sha256(raw).hexdigest()
        result['channels']=2;result['sample_width_bits']=16
    else:result={'status':'FAIL','reason':'retained evidence ZIP contains no speaker PCM output','expected_hz':frequency}
    path=directory/'player-waveform-oracle.json';path.write_text(json.dumps(result,indent=2)+'\n')
    for row in report['cases']:
        if row['api']not in{'audio.Player.play_raw','audio.Player.play_tone','audio.Player.play','audio.Player'}:continue
        row.setdefault('guest_status',row['status']);passed=result['status']=='PASS'and row['guest_status']=='PASS'
        row.update(status='PASS'if passed else'FAIL',data_plane_oracle=result['status'],required_evidence_met=passed)
        row['evidence_refs']['waveform_oracle_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        if not passed:row['remaining_oracle']='Original native status, independent expected spectrum or requested output duration failed.'
    report['counts']=dict(Counter(row['status']for row in report['cases']))
    if any(row['status']in{'FAIL','ERROR','TIMED_OUT'}for row in report['cases']):report['status']='FAIL'
    (directory/'protocol-results.json').write_text(json.dumps(report,indent=2)+'\n')
    return {'audio_case':case,'counts':report['counts'],'waveform':result}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    print(json.dumps(verify(parser.parse_args().run),indent=2))
