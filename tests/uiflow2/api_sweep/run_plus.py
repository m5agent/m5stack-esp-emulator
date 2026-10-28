#!/usr/bin/env python3
"""Run Plus widgets through real board WiFi/HTTP with a retained peer log."""
from __future__ import annotations
import argparse,base64,hashlib,json,threading,shutil
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import probe_ui,probe_protocols,run_guest
from check_ui_frame import check_frame

def run(args):
    args.out_dir.mkdir(parents=True,exist_ok=False);events=[]
    png=base64.b64decode(probe_ui.fixture_files()['fixture.png']['data'])
    class Peer(BaseHTTPRequestHandler):
        def do_GET(self):
            stop=next((i for i in reversed(range(len(events))) if events[i]['path']=='/disabled-marker'),None)
            stats={'label_count':sum(x['path']=='/label' for x in events),'png_count':sum(x['path']=='/fixture.png' for x in events),'png_after_stop':sum(x['path']=='/fixture.png' for x in events[stop+1:]) if stop is not None else 0}
            payload=(png if self.path=='/fixture.png' else json.dumps(stats if self.path in ('/stats','/disabled-marker') else {'value':'PLUS42' if self.path=='/label' else 'ALT9','nested':{'chosen':'NEXT7' if self.path=='/label' else 'ALT9'}}).encode())
            events.append({'method':'GET','path':self.path,'response_sha256':hashlib.sha256(payload).hexdigest(),'size':len(payload)})
            self.send_response(200);self.send_header('Content-Type','image/png' if self.path.endswith('.png') else 'application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*values):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Peer);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    prefix=probe_protocols.COMMON+'\nTEST_BASE_URL='+repr('http://10.0.2.2:'+str(server.server_port))+'\nEXPECTED_PNG_DIGEST='+repr(hashlib.sha256(png).digest())+'\n'
    source=args.out_dir/'main.py';source.write_text(('PLUS_CANDIDATE=True\n' if args.candidate_dir else '')+prefix+Path(__file__).with_name('probe_plus.py').read_text())
    fixture_dir=None
    if args.candidate_dir:
        provenance=json.loads((args.candidate_dir/'provenance.json').read_text());module=args.candidate_dir/provenance['module']
        if hashlib.sha256(module.read_bytes()).hexdigest()!=provenance['module_sha256']:raise ValueError('candidate module digest changed')
        fixture_dir=args.out_dir/'candidate-fixture';fixture_dir.mkdir();shutil.copyfile(module,fixture_dir/module.name)
        (args.out_dir/'candidate-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    try:
        result=run_guest.run(SimpleNamespace(api=args.api,token_file=args.token_file,device=args.device,runtime='qemu-wifi',network={'profile':'generic-observe','capture_pcap':True,'attempts':1,'expected_markers':['M5EMU_PLUS_DONE']},source=source,out_dir=args.out_dir/'execution',done_marker='M5EMU_PLUS_DONE',timeout=150,prepare_timeout=600,base_image=None,expected_base_sha256=None,fixture_dir=fixture_dir,firmware_lane='stock-frozen-with-candidate-python-override' if args.candidate_dir else 'stock-frozen'))
    finally:
        server.shutdown();server.server_close();thread.join();(args.out_dir/'peer.json').write_text(json.dumps(events,indent=2)+'\n')
    frame=args.out_dir/'execution/frame.png';serial=args.out_dir/'execution/serial.txt'
    if frame.exists() and serial.exists():
        checks=[]
        for line in serial.read_text(errors='replace').splitlines():
            if line.startswith('M5EMU_UI_FRAME_ORACLE '):
                row=json.loads(line.split(' ',1)[1]);checks.append({**row,**check_frame(frame.read_bytes(),row['oracle'])})
        (args.out_dir/'frame-results.json').write_text(json.dumps(checks,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--api", required=True);p.add_argument('--token-file',type=Path,required=True);p.add_argument('--device',choices=['cores3','cardputer-adv'],required=True);p.add_argument('--out-dir',type=Path,required=True);p.add_argument('--candidate-dir',type=Path);raise SystemExit(run(p.parse_args()))
