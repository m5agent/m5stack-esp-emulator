#!/usr/bin/env python3
"""Prove network API radio loss/recovery on one visible CoreS3 UIFlow guest."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import zipfile

from run_device_api import Client, INVENTORY, ROOT, save
from run_guest import build_image, parse_partition_table


def require(value, message):
    if not value:
        raise RuntimeError(message)


MAIN = '''import M5,network,socket,time
M5.begin()
screen=M5.Display
screen.setBrightness(255)
screen.fillScreen(0x123456)
screen.setTextColor(0xFFFFFF,0x123456)
screen.setTextSize(2)
screen.setCursor(4,4)
screen.print("NETWORK API")
print("API_NETWORK_STARTED")
wlan=network.WLAN(network.STA_IF)
wlan.active(True)
print("API_NET_SCAN",len(wlan.scan()))
def connect(label):
 wlan.connect("myssid")
 for attempt in range(160):
  M5.update()
  if wlan.isconnected() and wlan.status()==1010 and wlan.ifconfig()[0].startswith("10.0.2."):
   print("API_NET_DHCP",label,wlan.ifconfig()[0])
   return
  time.sleep_ms(250)
 raise RuntimeError("DHCP timeout "+str(label))
def http(path):
 sock=socket.socket()
 sock.settimeout(10)
 try:
  sock.connect(("10.0.2.2",__PORT__))
  sock.send(("GET "+path+" HTTP/1.0\\r\\nHost: api-fixture.test\\r\\n\\r\\n").encode())
  response=b""
  while b"API_NETWORK_HTTP_OK" not in response and len(response)<2048:
   part=sock.recv(512)
   if not part: break
   response+=part
  assert response.startswith(b"HTTP/") and b" 200 " in response and b"API_NETWORK_HTTP_OK" in response,"HTTP body/status mismatch"
  print("API_NET_HTTP",path,"PASS")
 finally: sock.close()
connect(1)
http("/before")
wlan.disconnect()
print("API_NET_DISCONNECTED")
time.sleep(1)
print("API_NET_DOWN_SCAN",len(wlan.scan()))
for attempt in range(120):
 count=len(wlan.scan())
 if count:
  print("API_NET_RESTORED_SCAN",count)
  break
 time.sleep_ms(250)
else: raise RuntimeError("radio restoration timeout")
connect(2)
http("/after")
screen.fillScreen(0x225511)
screen.setCursor(4,4)
screen.print("NETWORK API PASS")
screen.setCursor(4,40)
screen.print("DHCP / HTTP x2")
print("API_NETWORK_PASSED")
while True:
 M5.update()
 time.sleep_ms(100)
'''


def run(args):
    if not args.execute:
        print(json.dumps({"mode":"offline-plan","device_id":"cores3","runtime":"qemu-wifi",
                          "profile":"generic-observe","guest_sequence":"DHCP+HTTP; disconnect; radio-down scan=0; restore; DHCP+HTTP",
                          "hardware_validation":"NOT RUN"},indent=2))
        return 0
    require(args.out_dir is not None and args.token_file is not None,"--out-dir and --token-file are required")
    args.out_dir.mkdir(parents=True,exist_ok=False)
    requests=[]

    class Fixture(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append({"path":self.path,"status":200})
            body=b"API_NETWORK_HTTP_OK\n"
            self.send_response(200)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self,*_args):
            pass

    fixture=ThreadingHTTPServer(("127.0.0.1",0),Fixture)
    thread=threading.Thread(target=fixture.serve_forever,daemon=True)
    thread.start()
    client=Client(args.api,args.token_file.read_text().strip(),args.out_dir)
    rows=[]
    report={"schema_version":1,"validation":"virtual-device validation","hardware_validation":"NOT RUN",
            "inventory_sha256":hashlib.sha256(INVENTORY.read_bytes()).hexdigest(),"cases":rows,"status":"FAIL"}
    sid=None

    def call(op,path=None,payload=None,*,status=200,raw=None,headers=None):
        method,template=op.split(" ",1)
        record,body=client.call(method,path or template,payload,raw_body=raw,extra_headers=headers)
        rows.append({"operation_id":op,"coverage":"positive","http_status":record["status"],
                     "status":"PASS" if record["status"]==status else "FAIL","response_sha256":record["response_sha256"]})
        require(record["status"]==status,f"{op}: HTTP {record['status']}: {body}")
        return body,record

    def snapshot_binary(op,path,name):
        _,record=call(op,path)
        raw=(args.out_dir/f"{client.index:04d}.response").read_bytes()
        (args.out_dir/name).write_bytes(raw)
        return raw,record

    try:
        matrix=json.loads((ROOT/"tests/uiflow2/device_matrix.json").read_text())
        device=next(row for row in matrix["devices"] if row["id"]=="cores3")
        base=(ROOT/device["base"]).read_bytes()
        table=parse_partition_table(base,image_size=int(device["flash_size"],0))
        require(table["valid"],"reference partition table is invalid")
        vfs=next(row for row in table["partitions"] if row["label"]=="vfs" and row["type"]==1 and row["subtype"]==0x81)
        files=args.out_dir/"files"; files.mkdir()
        (files/"boot.py").write_text('from machine import UART\nimport os\n_repl_uart=UART(0,baudrate=115200,timeout=0,timeout_char=0)\nos.dupterm(_repl_uart,0)\n_repl_uart.irq(handler=os.dupterm_notify,trigger=UART.IRQ_RX)\n_uiflow_run_main=True\n')
        main=MAIN.replace("__PORT__",str(fixture.server_port))
        (files/"main.py").write_text(main)
        with contextlib.redirect_stdout(io.StringIO()):
            image=build_image(SimpleNamespace(base=ROOT/device["base"],flash_size=int(device["flash_size"],0),files_dir=files,
                              mklittlefs=None,preserve_vfs=False,vfs_offset=vfs["offset"],vfs_size=vfs["size"],prog_size=32,out_dir=args.out_dir))
        raw=image.read_bytes()
        report.update(base_sha256=hashlib.sha256(base).hexdigest(),source_sha256=hashlib.sha256(main.encode()).hexdigest(),firmware_sha256=hashlib.sha256(raw).hexdigest())
        artifact,_=call("POST /artifacts",raw=raw,headers={"Content-Type":"application/octet-stream","X-Artifact-Name":"cores3-network-api.bin"},status=201)
        firmware,_=call("POST /firmware",payload={"device_id":"cores3","kind":"merged","artifact_id":artifact["artifact_id"]},status=201)
        session,_=call("POST /sessions",payload={"device_id":"cores3","firmware_id":firmware["firmware_id"],"runtime":"qemu-wifi",
                       "ttl_seconds":600,"ready_marker":"API_NETWORK_STARTED","ready_timeout_seconds":60,
                       "network":{"profile":"generic-observe","capture_pcap":True,"attempts":1,"expected_markers":["API_NETWORK_PASSED"]}},status=202)
        sid=session["session_id"]; prefix="/sessions/"+sid
        report["session_id"]=sid
        print(json.dumps({"session_id":sid,"phase":"network-api-created"}),flush=True)
        deadline=time.monotonic()+180
        down,up=None,None
        serial_text=""
        while time.monotonic()<deadline:
            state,_=call("GET /sessions/{session_id}",prefix)
            serial,_=call("GET /sessions/{session_id}/serial",prefix+"/serial?limit=262144")
            serial_text=serial["data"]
            (args.out_dir/"serial.txt").write_text(serial_text)
            require(state["state"] not in {"failed","stopped"},"network guest ended: "+str(state.get("error")))
            require("Traceback (most recent call last)" not in serial_text,"network guest raised an exception")
            if "API_NET_DISCONNECTED" in serial_text and down is None:
                down,_=call("POST /sessions/{session_id}/network-fault",prefix+"/network-fault",{"action":"down","target":"radio"})
                qpath=down["network_fault"]["qom_path"]
                value,_=call("GET /sessions/{session_id}/qom",prefix+"/qom?path="+qpath+"&property=radio-enabled")
                require(value["value"] is False,"radio down was not read back false")
            if "API_NET_DOWN_SCAN 0" in serial_text and up is None:
                up,_=call("POST /sessions/{session_id}/network-fault",prefix+"/network-fault",{"action":"up","target":"radio"})
                value,_=call("GET /sessions/{session_id}/qom",prefix+"/qom?path="+up["network_fault"]["qom_path"]+"&property=radio-enabled")
                require(value["value"] is True,"radio up was not read back true")
            if "API_NETWORK_PASSED" in serial_text:
                break
            time.sleep(.1)
        require("API_NETWORK_PASSED" in serial_text,"network probe did not complete")
        require(down is not None and up is not None,"radio loss/restoration was not exercised")
        require("API_NET_DHCP 1 10.0.2." in serial_text and "API_NET_DHCP 2 10.0.2." in serial_text,"two guest DHCP acquisitions missing")
        require([row["path"] for row in requests]==["/before","/after"],"controlled HTTP before/after requests differ")
        network,_=call("GET /sessions/{session_id}/network",prefix+"/network")
        require(network["status"]=="PASS","live network markers did not pass")
        snapshot_binary("GET /sessions/{session_id}/frame.png",prefix+"/frame.png","network-final.png")
        flash,_=call("GET /sessions/{session_id}/flash",prefix+"/flash")
        report["flash"]=flash
        bundle,_=snapshot_binary("GET /sessions/{session_id}/evidence",prefix+"/evidence","network-evidence.zip")
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            require(archive.testzip() is None,"network evidence ZIP corrupt")
            require("network/capture.pcap" in archive.namelist(),"network capture absent before stop")
        report["evidence_sha256"]=hashlib.sha256(bundle).hexdigest()
        call("DELETE /sessions/{session_id}",prefix+"?purge=0&retain_flash=1")
        terminal,_=call("GET /sessions/{session_id}",prefix)
        require(terminal["state"]=="stopped" and terminal["flash_retained"],"network history/Flash retention failed")
        final_network,_=call("GET /sessions/{session_id}/network",prefix+"/network")
        capture=final_network["packet_capture"]
        require(capture["status"]=="PASS","final pcap summary failed")
        dhcp=capture["dhcp"]
        messages=dhcp.get("message_types",dhcp)
        require(all(messages.get(kind,0)>=2 for kind in ("discover","offer","request","ack")),"pcap lacks two DHCP exchanges")
        report.update(packet_capture=capture,http_fixture_requests=requests,status="PASS",final_state=terminal["state"])
        sid=None
    except Exception as error:
        report["error"]=str(error)
        raise
    finally:
        if sid is not None:
            try:
                snapshot_binary("GET /sessions/{session_id}/evidence","/sessions/"+sid+"/evidence","network-failure-evidence.zip")
            finally:
                call("DELETE /sessions/{session_id}","/sessions/"+sid+"?purge=0&retain_flash=1")
        fixture.shutdown();fixture.server_close();thread.join(timeout=2)
        report["positive_operations_tested"]=sorted({row["operation_id"] for row in rows if row["status"]=="PASS"})
        save(args.out_dir/"report.json",report)
    print(json.dumps({"status":report["status"],"cases":len(rows),"network_capture":report["packet_capture"]["status"]}),flush=True)
    return 0


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file",type=Path)
    parser.add_argument("--out-dir",type=Path)
    parser.add_argument("--execute",action="store_true")
    raise SystemExit(run(parser.parse_args()))
