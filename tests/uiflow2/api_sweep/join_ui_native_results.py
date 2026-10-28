#!/usr/bin/env python3
"""Join pinned native own-method declarations to explicit behavioral observations.

Use a reviewed list of selected run roots for publication. Historical fixture
failures remain in raw history and are never silently reclassified. The join
keeps stock, matching SDK preimage and each candidate observation distinct;
shared native owners and inherited methods never grant an unexecuted alias PASS.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib,json
from pathlib import Path
from summarize_ui_results import scan_run


def join(declarations, roots):
    rows={};sources=[]
    for path in declarations:
        data=json.loads(path.read_text());sources.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'binding_sha256':data['binding_sha256']})
        for owner in data['types'].values():
            surface=owner.get('runtime_surface') or 'lvgl.'+owner['name']
            for method,spec in owner['own_methods'].items():
                key=surface+'.'+method
                if key in rows:raise ValueError('native declaration overlap: '+key)
                rows[key]={'surface':surface,'method':method,'implementation_owner':spec['implementation_owner'],'observations':[]}
        for method,spec in data['module_functions'].items():
            key='lvgl.'+method
            if key in rows:raise ValueError('native declaration overlap: '+key)
            rows[key]={'surface':'lvgl','method':method,'implementation_owner':spec['implementation_owner'],'observations':[]}
    seen=set()
    for root in roots:
        for submitted,target,result,context in scan_run(root):
            key=target+'.'+result['method']
            entries=[(key,result)]
            if result.get('paired_getter'):
                entries.append((target+'.'+result['paired_getter'],{**result,'method':result['paired_getter'],'directly_called_by_set_get_recipe':key}))
            for api,outcome in entries:
                if api not in rows or outcome['status'] in ('NOT_RUN','INVENTORY_ONLY'):continue
                observation={'submitted_at':submitted,'result':outcome,**context}
                encoded=json.dumps([api,observation],sort_keys=True)
                if encoded in seen:continue
                seen.add(encoded);rows[api]['observations'].append(observation)
    counts={};missing={}
    devices=('cores3','cardputer-adv')
    lanes=('reference-frozen-implementation','matching-sdk-preimage','candidate-firmware','candidate-source-override')
    for device in devices:
        counts[device]={};missing[device]={}
        for lane in lanes:
            stats=Counter();absent=[]
            for api,row in rows.items():
                observations=[x for x in row['observations'] if x.get('device_id')==device and x.get('implementation_lane','reference-frozen-implementation')==lane]
                if not observations:absent.append(api);continue
                stats['explicitly_observed_own_methods']+=1
                statuses={x['result']['status'] for x in observations}
                for status in statuses:stats['methods_with_'+status]+=1
            stats['NOT_RUN']=len(absent);counts[device][lane]=dict(stats);missing[device][lane]=absent
    return {'schema_version':1,'validation':'virtual-device validation','hardware_validation':'NOT RUN','native_declaration_sources':sources,'own_and_module_method_denominator':len(rows),'coverage_rule':'Counts describe explicitly observed parameter/resource domains only. A STATE_PASS in one domain does not erase FAIL, CALL_OK, configuration blockers, unexecuted aliases or other devices. Choose reviewed run roots to exclude superseded erroneous fixtures.','counts':counts,'missing':missing,'results':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--declarations',type=Path,action='append',required=True)
    parser.add_argument('--run-dir',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=join(args.declarations,args.run_dir);args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'denominator':result['own_and_module_method_denominator'],'counts':result['counts']},indent=2))

if __name__=='__main__':main()
