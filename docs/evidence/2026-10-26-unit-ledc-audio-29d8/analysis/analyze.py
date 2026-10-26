"""Read-only post-analysis; preserves all raw and non-atomic observations."""
import argparse, collections, hashlib, json, pathlib, re

def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('run', type=pathlib.Path); ap.add_argument('--out', type=pathlib.Path, required=True); args=ap.parse_args()
    p=args.run; report=json.loads((p/'report.json').read_bytes()); assert report['status']=='OBSERVATIONS_COLLECTED'
    for name, value in report['artifact_sha256'].items(): assert sha((p/name).read_bytes())==value, name
    serial=(p/'serial.txt').read_bytes().decode(); observations=json.loads((p/'observations.json').read_bytes())
    patterns={
      'sample':r'(?m)^LEDC_DIAG_SAMPLE (\d+) (\d+) (\d+) (\d+) (\d+) (.+)\r?$',
      'global':r'(?m)^LEDC_DIAG_GLOBAL (\d+) (\d+) (\d+)\r?$',
      'timer':r'(?m)^LEDC_DIAG_TIMER (\d+) (\d+) (\d+) (\d+)\r?$',
      'raw':r'(?m)^LEDC_DIAG_RAW (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+) (\d+)\r?$'}
    tables={k:[m.groups() for m in re.finditer(v,serial)] for k,v in patterns.items()}
    assert len(tables['sample'])==60 and len(tables['raw'])==480
    grids={'sample':{(a,b) for a in range(6) for b in range(10)},
      'global':{(a,b) for a in range(6) for b in range(10)},
      'timer':{(a,b,c) for a in range(6) for b in range(10) for c in range(4)},
      'raw':{(a,b,c) for a in range(6) for b in range(10) for c in range(8)}}
    for kind, expected in grids.items():
        width=3 if kind in ('timer','raw') else 2
        keys=[tuple(map(int,r[:width])) for r in tables[kind]]
        assert len(keys)==len(set(keys)) and set(keys)==expected, 'duplicate/incomplete grid: '+kind
    raw={(int(a),int(b),int(c)):list(map(int, rest)) for a,b,c,*rest in tables['raw']}
    timers={(int(a),int(b),int(c)):int(v) for a,b,c,v in tables['timer']}
    globals_={(int(a),int(b)):int(v) for a,b,v in tables['global']}
    rows=[]
    for a,b,requested,getter,route,description in tables['sample']:
        phase,sample,requested,getter,route=map(int,(a,b,requested,getter,route)); channel=(route&511)-73
        assert 0<=channel<8 and globals_[phase,sample]==1
        conf0,hpoint,duty,conf1,duty_r=raw[phase,sample,channel]; timer=conf0&3; tc=timers[phase,sample,timer]; res=tc&15
        assert 0<res<=14
        rows.append(dict(phase=phase,sample=sample,requested=requested,getter=getter,route_raw=route,channel=channel,
          conf0=conf0,hpoint=hpoint,duty_raw=duty,duty_r_raw=duty_r,conf1=conf1,timer=timer,timer_conf=tc,resolution=res,
          duty_count=(duty&0x7ffff)>>4,duty_r_count=(duty_r&0x7ffff)>>4,
          expected_count_rounded=requested*(1<<res)/65535,
          getter_quantization_tolerance=(65535/(1<<res))+1))
    stable=[]; excluded=[]
    phase_counts=collections.defaultdict(collections.Counter)
    for i,o in enumerate(observations):
        prefixes=[]
        for key in ('before','after'):
            prefix=serial[:o[f'serial_{key}_length']]
            assert sha(prefix.encode())==o[f'serial_{key}_sha256']; prefixes.append(prefix)
        assert prefixes[1].startswith(prefixes[0]) and o['serial_prefix_preserved']
        assert sha((p/o['body']).read_bytes())==o['body_sha256']
        body=json.loads((p/o['body']).read_bytes())
        assert body['session_id']==report['session_id'] and body['state']=='running'
        unit=body['units'][0]
        assert unit['id']=='external1' and unit['unit_id']=='buzzer' and unit['source']=='guest-qom' and unit['available']
        properties=unit['properties']; duty=properties['duty-pct']; frequency=properties['frequency-hz']
        last=[]
        for prefix in prefixes:
            found=list(re.finditer(patterns['sample'],prefix)); last.append(found[-1].groups()[:2] if found else None)
        if o['phase_before']==o['phase_after'] and o['phase_before']:
            phase_counts[o['phase_before'][0]][str(duty)]+=1
        why=None
        if last[0]!=last[1] or not last[0]: why='sample-boundary-or-no-sample'
        elif not 1<=int(last[0][1])<=8: why='edge-sample-0-or-9'
        elif o['phase_before']!=o['phase_after'] or not o['phase_before'] or int(o['phase_before'][0])!=int(last[0][0]): why='phase-boundary'
        if why: excluded.append({'index':i,'reason':why,'phase_before':o['phase_before'],'phase_after':o['phase_after'],'duty_pct':duty}); continue
        phase,sample=map(int,last[0]); expected=(0,25,50,75,100,0)[phase]
        assert abs(duty-expected)<=0.1 and frequency==2000,(i,phase,duty,frequency)
        stable.append({'index':i,'phase':phase,'sample':sample,'duty_pct':duty,'frequency_hz':frequency,'body_sha256':o['body_sha256']})
    assert {x['phase'] for x in stable}==set(range(6))
    nonzero=[r for r in rows if r['phase'] in (1,2,3,4)]
    getter_repaired=all(r['duty_raw']==r['duty_r_raw'] and abs(r['duty_count']-r['expected_count_rounded'])<=1 and
      abs(r['getter']-r['requested'])<=r['getter_quantization_tolerance'] for r in rows)
    result={'schema_version':1,'status':'ANALYZED','firmware_sha256':report['firmware_sha256'],'runtime_provenance':report['runtime_provenance'],
      'input_report_sha256':sha((p/'report.json').read_bytes()),'raw_artifacts_verified':len(report['artifact_sha256']),
      'samples':rows,'raw_channel_records':len(tables['raw']),'qom_observations':len(observations),
      'strict_stable_observations':stable,'excluded_observations':excluded,'phase_only_counts':dict(phase_counts),
      'nonzero_requested_getter_all_zero':all(r['getter']==0 for r in nonzero),
      'all_channels_duty_and_duty_r_zero':all(v[2]==0 and v[4]==0 for v in raw.values()),
      'settled_readback_matches_resolution':getter_repaired,
      'boundary':'Sample 1..8 in same serial bracket only. Phase-only equality is insufficient; excluded observations remain raw. Tests stable full set/update driver path; pending/current-cycle/fade not tested. Virtual device only.'}
    assert not args.out.exists(); args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','raw_artifacts_verified','raw_channel_records','qom_observations','settled_readback_matches_resolution','nonzero_requested_getter_all_zero')}))
    print('strict_stable',len(stable),'excluded',len(excluded),'phase_only_counts',dict(phase_counts))
if __name__=='__main__':main()
