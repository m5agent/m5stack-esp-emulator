#!/usr/bin/env python3
"""Lossless API/status/reason/receipt table with shared pools and RLE slots.

API slot order is sorted(source inventory union additional runtime exports).
The public compact artifact retains each selected result, including NOT_RUN,
ERROR and state-only observations.  Raw runs stay in ignored storage.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import zlib


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def packed(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


class Pool:
    def __init__(self):self.values=[];self.ids={}
    def add(self,value):
        key=packed(value)
        if key not in self.ids:self.ids[key]=len(self.values);self.values.append(value)
        return self.ids[key]


def rle(rows):
    result=[]
    for row in rows:
        if result and result[-1][1:]==row:result[-1][0]+=1
        else:result.append([1,*row])
    return result


def compact(inventory,joined,inventory_path):
    source_apis={row['api']for row in inventory['entries']}
    apis=sorted({row['api']for row in joined['entries']})
    if not source_apis.issubset(apis):raise ValueError('join dropped source inventory APIs')
    extra={}
    for api in sorted(set(apis)-source_apis):
        owner,name=api.rsplit('.',1)if'.'in api else('',api)
        extra.setdefault(owner,[]).append(name)
    statuses=Pool();reasons=Pool();hashes=Pool();receipts=Pool()
    receipt_cache={}
    def receipt(directory):
        if directory is None:return -1
        directory=Path(directory)
        key=str(directory)
        if key in receipt_cache:return receipt_cache[key]
        report_path=directory/'report.json'
        if not report_path.exists():return -1
        report=json.loads(report_path.read_text())
        if report.get('firmware_lane','stock-frozen')!='stock-frozen':
            raise ValueError('candidate result cannot be assigned a stock receipt')
        # Avoid committing host-specific absolute paths or any arbitrary report
        # fields; this whitelist contains public audit identifiers only.
        name=key.split('.work/api-sweep/',1)[-1]
        h=lambda value:hashes.add(value)if value else-1
        value=[name,report.get('session_id'),h(report.get('firmware_sha256')),
            h(report.get('runtime_binary_sha256')),h(report.get('source_sha256')),
            h(report.get('evidence_sha256')),h(sha(directory/'serial.txt'))if(directory/'serial.txt').exists()else-1,
            h(sha(report_path)),h(report.get('frame_sha256')),
            bool(report.get('stopped')and report.get('cleanup',{}).get('runtime_pid_gone'))]
        idx=receipts.add(value);receipt_cache[key]=idx;return idx
    # Selected inherited implementation results name their concrete run only in
    # evidence_refs.  Build an exact report hash index before assigning slots.
    report_by_hash={}
    for row in joined['entries']:
        directory=row.get('run_directory')
        if directory and(Path(directory)/'report.json').exists():report_by_hash[sha(Path(directory)/'report.json')]=directory
    devices=list(inventory['devices']);tables={}
    for device in devices:
        indexed={row['api']:row for row in joined['entries']if row['device_id']==device}
        if set(indexed)!=set(apis):raise ValueError('device denominator is not identical')
        rows=[]
        for api in apis:
            row=indexed[api];reason=row.get('blocker')or row.get('oracle')or''
            if row.get('error'):reason+=' | '+row['error']
            if row.get('implementation_target'):reason+=' | implementation='+row['implementation_target']
            directory=row.get('run_directory')or report_by_hash.get(row.get('evidence_refs',{}).get('execution_report_sha256'))
            if not directory and row.get('export_evidence'):directory=str(Path(row['export_evidence']['path']).parent)
            flags=(1 if row.get('required_evidence_met')else 0)|(2 if row.get('export_callable')is True else 8 if row.get('export_callable')is False else 0)|(4 if row.get('export_status')=='PRESENT'else 0)
            rows.append([statuses.add(row['status']),reasons.add(reason),receipt(directory),flags])
        tables[device]=rle(rows)
    result={'schema_version':1,'encoding':'api-slots-pools-rle-v1','validation':'virtual-device validation','hardware_validation':'NOT RUN',
        'source_commit':joined['source_commit'],'inventory':str(inventory_path),'inventory_sha256':sha(inventory_path),
        'join_sha256':hashlib.sha256(packed(joined).encode()).hexdigest(),
        'slots':len(apis),'api_order':'sorted union of source inventory entries.api and additional_exports owner.member',
        'api_order_sha256':hashlib.sha256(('\n'.join(apis)+'\n').encode()).hexdigest(),
        'additional_exports':extra,'devices':devices,'statuses':statuses.values,'sha256':hashes.values,
        'reason_pool':{'encoding':'zlib-base64-json-utf8','count':len(reasons.values),
            'sha256':hashlib.sha256(packed(reasons.values).encode()).hexdigest(),
            'data':base64.b64encode(zlib.compress(packed(reasons.values).encode(),9)).decode()},
        'receipt_columns':['run','session_id','firmware_sha256_id','runtime_sha256_id','source_sha256_id','evidence_zip_sha256_id','serial_sha256_id','report_sha256_id','frame_sha256_id','stopped_pid_gone'],
        'receipts':receipts.values,'rle_columns':['length','status_id','reason_id','receipt_id','flags'],
        'flags':{'required_evidence_met':1,'export_callable_true':2,'export_present':4,'export_callable_false':8},
        'tables':tables,'counts':{device:dict(Counter(row['status']for row in joined['entries']if row['device_id']==device))for device in devices}}
    return result


def expand(document,inventory,inventory_path):
    if sha(inventory_path)!=document['inventory_sha256']:raise ValueError('source inventory SHA256 mismatch')
    apis=sorted({row['api']for row in inventory['entries']}|{owner+'.'+member if owner else member for owner,members in document['additional_exports'].items()for member in members})
    if len(apis)!=document['slots']or hashlib.sha256(('\n'.join(apis)+'\n').encode()).hexdigest()!=document['api_order_sha256']:raise ValueError('API slot order mismatch')
    pool=document['reason_pool'];reason_bytes=zlib.decompress(base64.b64decode(pool['data']))
    if hashlib.sha256(reason_bytes).hexdigest()!=pool['sha256']:raise ValueError('reason pool SHA256 mismatch')
    reasons=json.loads(reason_bytes)
    if len(reasons)!=pool['count']:raise ValueError('reason pool count mismatch')
    output=[]
    for device in document['devices']:
        slot=0
        for length,status,reason,receipt_id,flags in document['tables'][device]:
            if not isinstance(length,int)or length<1:raise ValueError('invalid RLE length')
            rec=None if receipt_id<0 else dict(zip(document['receipt_columns'],document['receipts'][receipt_id]))
            if rec:
                for key in list(rec):
                    if key.endswith('_sha256_id'):
                        idx=rec.pop(key);rec[key[:-3]]=document['sha256'][idx]if idx>=0 else None
            for index in range(length):
                if slot>=len(apis):raise ValueError('RLE overrun')
                output.append({'slot':slot,'api':apis[slot],'device_id':device,'status':document['statuses'][status],
                    'reason':reasons[reason],'receipt':rec,'flags':flags})
                slot+=1
        if slot!=len(apis):raise ValueError('RLE underrun')
    return output


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',type=Path,default=Path(__file__).with_name('inventory_system.source.json'))
    parser.add_argument('--join',type=Path);parser.add_argument('--expand',type=Path);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();inventory=json.loads(args.inventory.read_text())
    if bool(args.join)==bool(args.expand):parser.error('select exactly one of --join and --expand')
    result=expand(json.loads(args.expand.read_text()),inventory,args.inventory)if args.expand else compact(inventory,json.loads(args.join.read_text()),args.inventory)
    encoded=packed(result)+'\n'
    if not args.expand and len(encoded.encode())>65536:raise ValueError('compact summary exceeds the 64 KiB evidence budget: '+str(len(encoded.encode())))
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(encoded,encoding='utf-8')
    print(json.dumps({'bytes':len(encoded.encode()),'output':str(args.out),'slots':len(result)//len(inventory['devices'])if args.expand else result['slots']}))


if __name__=='__main__':main()
