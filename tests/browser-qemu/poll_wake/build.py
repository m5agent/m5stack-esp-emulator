#!/usr/bin/env python3
"""Build real SDK3.1.50 poll/notifier controls; no QEMU/guest build or run."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--emcc',required=True);p.add_argument('--node',default='node');p.add_argument('--out-dir',type=Path,required=True);lanes=p.add_mutually_exclusive_group();lanes.add_argument('--cancel-only',action='store_true');lanes.add_argument('--positive-only',action='store_true');args=p.parse_args()
 out=args.out_dir.resolve()
 if out.exists():p.error('--out-dir must be new; preserve prior results')
 version=subprocess.check_output([args.emcc,'--version'],text=True)
 if not re.search(r'\b3\.1\.50\b',version):p.error('Emscripten3.1.50 required')
 sys.path.insert(0,str(ROOT/'platform/tests'))
 from test_wasm_poll_wake_patch import actual_sources,PATCH,FIXTURE
 old,prefix,new,notifier=actual_sources()
 out.mkdir(parents=True)
 inc=out/'actual-poll.inc';inc.write_text(old.replace('qemu_poll_ns','original_poll_ns',1)+'\n'+prefix+'\n'+new+'\n'+notifier+'\n')
 source=Path(__file__).with_name('probe.c')
 (out/'used-probe.c').write_bytes(source.read_bytes())
 (out/'used-build.py').write_bytes(Path(__file__).read_bytes())
 report={'kind':'real-sdk-host-poll-wake-controls','guest_execution':'NOT RUN','sdk':version,'patch_sha256':sha(PATCH),'fixture_sha256':sha(FIXTURE),'probe_sha256':sha(source),'build_script_sha256':sha(Path(__file__)),'actual_source_sha256':sha(inc),'commands':[],'runs':[],'cancel_runs':[],'status':'FAIL'}
 try:
  for proxy in (1,0):
   target=out/f'poll-proxy{proxy}.cjs'
   command=[args.emcc,str(source),'-I'+str(out),'-O2','-pthread','-sPTHREAD_POOL_SIZE=4','-sEXIT_RUNTIME=1','-sSINGLE_FILE=1','-sASSERTIONS=2','-sENVIRONMENT=node,worker','-sPROXY_TO_PTHREAD='+str(proxy),'-o',str(target)]
   report['commands'].append(command)
   with (out/f'build-proxy{proxy}.log').open('wb') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
   for mode in (() if args.cancel_only else ('original','legacy','wake')):
    command=[args.node,str(target),mode];report['commands'].append(command)
    log_path=out/f'run-proxy{proxy}-{mode}.log'
    with log_path.open('w') as log:
     run=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=30)
    output=log_path.read_text()
    row={'proxy':proxy,'mode':mode,'exit_code':run.returncode,'artifact_sha256':sha(target)};report['runs'].append(row)
    run.check_returncode()
    marker=next(line[len('M5_POLL_WAKE '):] for line in output.splitlines() if line.startswith('M5_POLL_WAKE '))
    row['result']=json.loads(marker)
  for proxy in (() if args.cancel_only else (1,0)):
   rows={r['mode']:r['result'] for r in report['runs'] if r['proxy']==proxy}
   if not rows['wake']['notified_median_ms']+1 < rows['original']['notified_median_ms']:
    raise RuntimeError(f'host notification latency improvement not observed proxy{proxy}')
  report['positive_status']='NOT RUN: cancel-only' if args.cancel_only else 'PASS'
  # Cancellation is a separate bounded lane: baseline failure is retained
  # without discarding already completed readiness/latency receipts.
  for proxy in (() if args.positive_only else (1,0)):
   for mode in ('original','wake'):
    target=out/f'poll-proxy{proxy}.cjs';log_path=out/f'cancel-proxy{proxy}-{mode}.log'
    command=[args.node,str(target),mode,'cancel'];report['commands'].append(command)
    row={'proxy':proxy,'mode':mode,'status':'FAIL'};report['cancel_runs'].append(row)
    try:
     with log_path.open('w') as log:run=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,text=True,timeout=5)
     row['exit_code']=run.returncode
     output=log_path.read_text()
     marker=next((line[len('M5_POLL_CANCEL '):] for line in output.splitlines() if line.startswith('M5_POLL_CANCEL ')),None)
     if marker:row['result']=json.loads(marker)
     if run.returncode==0:row['status']='PASS'
    except subprocess.TimeoutExpired:row['error']='bounded 5s cancellation lane timeout'
  report['cancel_status']='NOT RUN: positive-only' if args.positive_only else ('PASS' if all(r['status']=='PASS' for r in report['cancel_runs']) else 'FAIL')
  report['status']='PASS' if report['cancel_status']=='PASS' and report['positive_status']=='PASS' else 'PARTIAL'
 except BaseException as error:
  report['error']=str(error);raise
 finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({'status':report['status'],'out_dir':str(out),'runs':report['runs']}))
 if report['status']!='PASS':raise SystemExit(2)
if __name__=='__main__':main()
