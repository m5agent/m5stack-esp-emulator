#!/usr/bin/env python3
"""Run UIFlow protocol recipes through visible service guests and local peers."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import re
from pathlib import Path
import socketserver
import ssl
import threading
from types import SimpleNamespace
import urllib.parse
import zipfile

from probe_protocols import build_program
from protocol_peers import mqtt_handler,modbus_handler,RTUControllerPeer,RTUSlaveControllerPeer
from ppp_peer import PPPControllerPeer
from run_device_api import save
from run_guest import Api, DEVICE_CHOICES, run as run_guest


BLE_IDENTITIES = {
    "cores3": ("M5-CORES3-UNIFIED", "M5_CORES3_UNIFIED"),
    "cardputer-adv": ("M5-CPTR-ADV-UNIFIED", "M5_CPTR_ADV"),
    "stopwatch": ("M5-STOPWATCH-UNIFIED", "M5_STOPWATCH_U"),
    "sticks3": ("M5-STICKS3-UNIFIED", "M5_STICKS3_UNIFIED"),
    "core2": ("M5-CORE2-UNIFIED", "M5_CORE2_UNIFIED"),
}

CORE2_NATIVE_HCI_PROFILE = "core2-native-hci"
BLE_GROUPS = {"ble-nus","m5ble-server","ble-client","m5ble-client"}
BLE_CLIENT_GROUPS = {"ble-client","m5ble-client"}
BLE_PERIPHERAL_PEER_DEVICES = {"cores3","cardputer-adv"}


def radio_profile(device):
    return CORE2_NATIVE_HCI_PROFILE if device == "core2" else "uiflow2-" + device + "-unified"


def library_lane(group, m5ble_source):
    candidate = group in {"requests-candidate", "modbus-candidate"} or (
        group == "m5ble-server" and m5ble_source is not None
    )
    return "candidate-source" if candidate else "stock-frozen"


def candidate_source_sha256(group, config):
    key = {
        "requests-candidate": "requests_source",
        "modbus-candidate": "modbus_master_source",
        "m5ble-server": "m5ble_source",
    }.get(group)
    source = config.get(key) if key else None
    return hashlib.sha256(source.encode()).hexdigest() if source is not None else None


def require_m5ble_source_group(group, source_path):
    if source_path is not None and group != "m5ble-server":
        raise SystemExit("--m5ble-source is only valid for --group m5ble-server")


def require_core2_native_hci_elf(device, group, elf_path):
    if device == "core2" and group in BLE_GROUPS and elf_path is None:
        raise SystemExit("--core2-elf is required for Core2 stock internal-controller BLE")
    if elf_path is not None and not elf_path.is_file():
        raise SystemExit(f"Core2 native-HCI ELF does not exist: {elf_path}")


def ble_nus_exchange_observed(log, ack):
    lines = log.splitlines()
    exact_ack = "BLE_BUMBLE_NOTIFICATION_OK ACK:" + ack
    return bool(
        any(line.startswith("BLE_BUMBLE_CONNECTED") for line in lines)
        and any(line.startswith("BLE_BUMBLE_GATT_DISCOVERED ") for line in lines)
        and any(line.startswith("BLE_BUMBLE_SUBSCRIBED ") for line in lines)
        and any(line.startswith("BLE_BUMBLE_WRITE ") for line in lines)
        and exact_ack in lines
    )


def unsupported_ble_peripheral_peer(device, group):
    return group in BLE_CLIENT_GROUPS and device not in BLE_PERIPHERAL_PEER_DEVICES


def stock_radio_model_blocker(evidence, device, execution_error=None):
    if execution_error and "peripheral BLE peer is admitted only" in execution_error:
        return {
            "api_prefixes": ["bluetooth.BLE", "bleuart.BLEUARTClient", "m5ble.m5ble.Client"],
            "status": "BLOCKED_FIXTURE",
            "reason": (
                "This client probe requires the Device Service to act as a BLE "
                "peripheral. Peripheral peer role admission is currently limited "
                "to CoreS3 and Cardputer-ADV, so this device group is NOT_RUN and "
                "is not a stock controller result."
            ),
            "evidence_refs": evidence,
        }
    if device == "core2":
        reason = (
            "The selected stock Core2 image uses its internal Bluetooth "
            "controller; the core2-native-hci profile did not reach "
            "board I/O readiness before timeout. An HCI test-firmware result "
            "cannot close this stock GATT gap."
        )
    else:
        reason = (
            "The selected stock " + device + " image uses the internal BT "
            "controller. This runtime exposes a UART H4 controller-offload "
            "seam; it does not implement the stock controller. Actual stock "
            "guest/peer exchange timed out. An HCI test firmware result "
            "cannot close this gap."
        )
    return {"api_prefixes":["bluetooth.BLE","bleuart.BLEUARTServer","bleuart.BLEUARTClient",
                            "m5ble.m5ble.Device","m5ble.m5ble.Server","m5ble.m5ble.Client"],
            "status":"BLOCKED_MODEL","reason":reason,
            "evidence_refs":evidence}


def run(args):
    require_m5ble_source_group(args.group, args.m5ble_source)
    if not args.execute:
        print(json.dumps({"mode":"offline-plan","devices":args.device,"group":args.group,
                          "peers":"owned loopback HTTP/TCP/UDP servers via guest actual WiFi/SLiRP",
                          "hardware_validation":"NOT RUN"},indent=2))
        return 0
    if args.out_dir is None:
        raise SystemExit("--out-dir is required with --execute")
    require_core2_native_hci_elf(
        "core2" if "core2" in args.device else None,
        args.group,
        args.core2_elf,
    )
    bases=dict(value.split("=",1)for value in getattr(args,"base_image",[]))
    base_hashes=dict(value.split("=",1)for value in getattr(args,"expected_base_sha256",[]))
    if set(bases)!=set(base_hashes):
        raise ValueError("each alternate device base requires one exact expected SHA256")
    if bases and set(bases)!=set(args.device):
        raise ValueError("alternate firmware lanes require a pinned base for every selected device")
    args.out_dir.mkdir(parents=True,exist_ok=False)
    core2_elf = None
    if args.core2_elf is not None:
        elf_body = args.core2_elf.read_bytes()
        elf_api = Api(args.api, args.token_file)
        uploaded_elf = elf_api.json(
            "artifacts",
            "POST",
            body=elf_body,
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": "core2-native-hci.elf",
            },
        )
        core2_elf = {
            "artifact_id": uploaded_elf["artifact_id"],
            "sha256": hashlib.sha256(elf_body).hexdigest(),
            "bytes": len(elf_body),
        }
        save(args.out_dir / "core2-native-hci-elf.json", core2_elf)
    peer_requests=[]
    ez_values={}
    ez_history={}
    ez_clock=[100]

    class HttpPeer(BaseHTTPRequestHandler):
        def echo(self):
            framing=self.headers.get("Transfer-Encoding","").lower()
            if framing=="chunked":
                chunks=[]
                while True:
                    size=int(self.rfile.readline().split(b";",1)[0],16)
                    if not size:
                        while True:
                            trailer=self.rfile.readline()
                            if trailer==b"\r\n":break
                            if not trailer:raise ValueError("incomplete chunk trailers")
                        break
                    chunks.append(self.rfile.read(size))
                    if self.rfile.read(2)!=b"\r\n":raise ValueError("invalid request chunk boundary")
                    if sum(map(len,chunks))>65536:raise ValueError("fixture request body exceeds bound")
                body=b"".join(chunks)
            else:
                size=int(self.headers.get("Content-Length","0"))
                body=self.rfile.read(size) if size else b""
            row={"method":self.command,"path":self.path,"body_sha256":hashlib.sha256(body).hexdigest(),"bytes":len(body),
                 "framing":framing or "content-length","content_length":self.headers.get("Content-Length")}
            if isinstance(self.connection,ssl.SSLSocket):
                row["tls_peer_certificate_sha256"]=hashlib.sha256(self.connection.getpeercert(binary_form=True)).hexdigest()
                row["tls_version"]=self.connection.version()
            peer_requests.append(row)
            save(args.out_dir/"peer-requests-live.json",peer_requests)
            result={"method":self.command,"body":body.decode("utf-8",errors="replace")}
            if self.path.startswith("/ez/"):
                parts=self.path.split("/")
                operation=parts[3] if len(parts)>3 else ""
                if operation=="add":
                    payload=json.loads(body)
                    key=payload["name"];ez_clock[0]+=1
                    ez_values[key]={"value":payload["value"],"dataType":payload["dataType"],"updateTime":ez_clock[0]}
                    ez_history.setdefault(key,[]).append({"value":payload["value"]})
                    result={"code":200}
                elif operation=="uploadFile":
                    message=BytesParser(policy=email_policy).parsebytes(
                         ("Content-Type: "+self.headers["Content-Type"]+"\r\n\r\n").encode()+body)
                    fields={};file_bytes=None
                    for part in message.iter_parts():
                        key=part.get_param("name",header="content-disposition")
                        if key=="file":file_bytes=part.get_payload(decode=True)
                        else:
                            # Frozen EzData labels simple text parts as nested
                            # multipart, so Python's email parser retains the
                            # transport CRLF in get_payload(). File bytes are
                            # handled separately and remain untouched.
                            fields[key]=part.get_payload(decode=True).decode().rstrip("\r\n")
                    if file_bytes is None:raise ValueError("EzData multipart file absent")
                    key=fields["name"];ez_clock[0]+=1
                    row["multipart_fields"]=fields
                    ez_values[key]={"value":"http://10.0.2.2:"+str(self.server.server_port)+"/ez/files/"+key,
                                    "dataType":"file","updateTime":ez_clock[0],"file_bytes":file_bytes}
                    row["uploaded_file_sha256"]=hashlib.sha256(file_bytes).hexdigest()
                    result={"code":200}
                elif parts[2]=="files":
                    raw=ez_values[parts[3]]["file_bytes"]
                    row["response_body_sha256"]=hashlib.sha256(raw).hexdigest()
                    self.send_response(200);self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
                    return
                elif operation in {"dataByKey","data"}:
                    key=parts[4] if operation=="dataByKey" else "fixture-key"
                    result={"code":200,"data":{name:value for name,value in ez_values[key].items() if name!="file_bytes"}} if key in ez_values else {"code":404}
                elif operation in {"historyByKey","history"}:
                    key=parts[4] if operation=="historyByKey" else "fixture-key"
                    result={"code":200,"data":{"rows":ez_history.get(key,[])}}
                elif operation=="list":
                    result={"code":200,"data":{"rows":[{"name":key,"value":value["value"]} for key,value in ez_values.items()]}}
                elif operation=="delete":
                    ez_values.pop(parts[4],None)
                    result={"code":200}
                else:raise ValueError("unexpected owned EzData fixture route")
            if self.path=="/form":
                parsed=urllib.parse.parse_qs(body.decode(),keep_blank_values=True)
                result["form"]={key:value[0] for key,value in parsed.items()}
            raw=json.dumps(result,ensure_ascii=False).encode()
            save(args.out_dir/"peer-requests-live.json",peer_requests)
            row["response_body_sha256"]=hashlib.sha256(raw).hexdigest()
            self.send_response(200)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("X-Protocol-Fixture","yes")
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            if self.command!="HEAD":
                self.wfile.write(raw)

        do_GET=echo
        do_HEAD=echo
        do_POST=echo
        do_PUT=echo
        do_PATCH=echo
        do_DELETE=echo

        def log_message(self,*_args):
            pass

    class TcpPeer(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(30)
            while True:
                try:data=self.request.recv(4096)
                except OSError:return
                if not data:return
                peer_requests.append({"protocol":"TCP","bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
                self.request.sendall(data)
                if data==b"CLOSE\n":return

    class UdpPeer(socketserver.BaseRequestHandler):
        def handle(self):
            data,sock=self.request
            peer_requests.append({"protocol":"UDP","bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})
            sock.sendto(data,self.client_address)

    class TcpServer(socketserver.ThreadingTCPServer):
        daemon_threads=True

    peers=[ThreadingHTTPServer(("127.0.0.1",0),HttpPeer),TcpServer(("127.0.0.1",0),TcpPeer),socketserver.ThreadingUDPServer(("127.0.0.1",0),UdpPeer),TcpServer(("127.0.0.1",0),mqtt_handler(peer_requests)),TcpServer(("127.0.0.1",0),modbus_handler(peer_requests))]
    tls_config={}
    if args.group=="tls":
        import datetime
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"m5-api.test")])
        certificate=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(datetime.datetime(2020,1,1))
            .not_valid_after(datetime.datetime(2035,1,1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("m5-api.test")]),critical=False).sign(key,hashes.SHA256()))
        certificate_pem=certificate.public_bytes(serialization.Encoding.PEM)
        certificate_der=certificate.public_bytes(serialization.Encoding.DER)
        key_pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,serialization.NoEncryption())
        cert_path=args.out_dir/"owned-test-certificate.pem";key_path=args.out_dir/"owned-test-key.pem"
        cert_path.write_bytes(certificate_pem);key_path.write_bytes(key_pem);key_path.chmod(0o600)
        server_context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(cert_path,key_path)
        server_context.load_verify_locations(cafile=cert_path)
        server_context.verify_mode=ssl.CERT_REQUIRED
        class TLSServer(ThreadingHTTPServer):
            def get_request(self):
                sock,address=super().get_request();sock.settimeout(10)
                try:return server_context.wrap_socket(sock,server_side=True),address
                except Exception as error:
                    peer_requests.append({"protocol":"TLS-handshake","error":str(error)})
                    sock.close();raise
        tls_peer=TLSServer(("127.0.0.1",0),HttpPeer);peers.append(tls_peer)
        tls_config={"tls":tls_peer.server_address[1],"tls_certificate_pem":certificate_pem.decode(),
                    "tls_certificate_der":certificate_der.hex(),"tls_key_pem":key_pem.decode()}
    threads=[]
    for peer in peers:
        thread=threading.Thread(target=peer.serve_forever,daemon=True);thread.start();threads.append(thread)
    runtime_env=json.loads(args.runtime_env_json.read_text()) if args.runtime_env_json else None
    if runtime_env is not None and not isinstance(runtime_env,dict):
        raise ValueError("--runtime-env-json must contain a JSON object")
    config={name:server.server_address[1] for name,server in zip(("http","tcp","udp","mqtt","modbus"),peers)}
    config.update(tls_config)
    config["audio_case"]=args.audio_case
    config["tls_clock_year"]=getattr(args,"tls_clock_year",2026)
    config["espnow_loopback"]=bool(
        runtime_env and runtime_env.get("M5SW_ESPNOW_LOOPBACK")
    )
    if args.group=="requests-candidate":
        if args.requests2_source is None:
            raise SystemExit("--requests2-source is required for candidate source lane")
        config["requests_source"]=args.requests2_source.read_text(encoding="utf-8")
    if args.group=="modbus-candidate":
        if args.modbus_master_source is None:
            raise SystemExit("--modbus-master-source is required for candidate source lane")
        config["modbus_master_source"]=args.modbus_master_source.read_text(encoding="utf-8")
    if args.m5ble_source is not None:
        config["m5ble_source"]=args.m5ble_source.read_text(encoding="utf-8")
    source=build_program(args.group,config)
    source_path=args.out_dir/"probe.py";source_path.write_text(source,encoding="utf-8")
    reports=[]
    try:
        for device in args.device:
            peer_start=len(peer_requests)
            output=args.out_dir/device
            source=build_program(args.group,{
                **config,
                "device_id":device,
                "ble_identity":list(BLE_IDENTITIES[device]),
            })
            source_path=args.out_dir/(device+"-probe.py");source_path.write_text(source,encoding="utf-8")
            plain=args.group.startswith("audio-") or args.group in {"modbus-rtu","modbus-rtu-slave","ppp"}
            radio=args.group in BLE_GROUPS
            wifi_profile={"sticks3":"uiflow2-sticks3-wifi","core2":"core2-openmac"}.get(device,"generic-observe")
            arguments=SimpleNamespace(api=args.api,token_file=args.token_file,device=device,runtime="qemu-unified" if radio else "qemu" if plain else "qemu-wifi",
                       timeout=args.timeout,source=source_path,out_dir=output,done_marker="PROTOCOL_GROUP_DONE "+args.group,
                       network=None if plain else {"profile":wifi_profile,"http_fixture":False,"capture_pcap":True,"attempts":1,
                                "expected_markers":["PROTOCOL_GROUP_DONE "+args.group]})
            arguments.runtime_env=runtime_env
            arguments.uart_repl_bootstrap=args.uart_repl_bootstrap
            if device in bases:
                arguments.base_image=Path(bases[device])
                arguments.expected_base_sha256=base_hashes[device]
                arguments.firmware_lane=("hci-offload-test-firmware" if radio else "caller-pinned-candidate")
            if radio:
                profile=radio_profile(device)
                arguments.network.update(profile=profile,ble_linger_seconds=8)
                if device == "core2":
                    if core2_elf is None:
                        raise ValueError("Core2 native-HCI ELF upload is unavailable")
                    arguments.network["elf_artifact_id"] = core2_elf["artifact_id"]
                if args.group in {"ble-client","m5ble-client"}:arguments.network["ble_peer_role"]="peripheral"
            if args.group in {"modbus-rtu","modbus-rtu-slave","ppp"}:
                if device!="cores3":raise ValueError("Cardputer-ADV RS485 Unit is not admitted")
                arguments.units=[{"id":"rtu","unit_id":"rs485","port_id":"port-a"}]
                arguments.on_session_poll=({"modbus-rtu":RTUControllerPeer,"modbus-rtu-slave":RTUSlaveControllerPeer,"ppp":PPPControllerPeer}[args.group])(peer_requests)
            with contextlib.redirect_stdout(io.StringIO()):
                code=run_guest(arguments)
            execution=json.loads((output/"report.json").read_text())
            results=[]
            serial=(output/"serial.txt").read_text(errors="replace") if (output/"serial.txt").exists() else ""
            for match in re.finditer(r"(?:^|\n)PROTOCOL_API ",serial):
                result,_end=json.JSONDecoder().raw_decode(serial[match.end():])
                results.append(result)
            starts=Counter(re.findall(r"(?:^|\n)PROTOCOL_CALL_BEGIN ([^\r\n]+)",serial))
            completed=Counter(row["api"]for row in results)
            for api,count in starts.items():
                if count>completed[api]:
                    results.append({"api":api,"status":"TIMED_OUT","oracle":"the original guest call began but did not produce a result before the bounded session deadline"})
            peer_rows=peer_requests[peer_start:]
            if args.group=="ppp":
                peer_ok=any(row.get("protocol")=="PPP-UDP-ORACLE"and row.get("status")=="PASS"for row in peer_rows)
                for row in results:
                    if row["status"]=="OBSERVED_PENDING_PPP_PEER":row["status"]="PASS"if peer_ok else"FAIL"
                    if row["status"]=="PASS"and not peer_ok:row["status"]="STATE_PASS"
            if args.group=="modbus-rtu-slave":
                observed={row["sequence"]:row["status"]for row in peer_rows if row.get("protocol")=="ModbusRTUSlave"}
                for row in results:
                    if row["status"]=="OBSERVED_PENDING_UART_PEER":
                        passed=all(observed.get(sequence)=="PASS"for sequence in row["value"]["wire_sequences"])
                        row.update(status="PASS"if passed else"FAIL",oracle="independent master verified exact original slave UART response bytes/CRC and expected register values"if passed else"independent UART master response/CRC/quantity oracle incomplete or failed")
            save(output/"peer-requests.json",peer_rows)
            if args.group=="mqtt":
                for result in results:
                    if result["api"].endswith(".set_last_will"):
                        prefix=result["api"].removesuffix(".set_last_will")
                        match=any(row.get("connect_fields",[])[:3]==[prefix,"fixture/will","owned-offline"]
                                  and row.get("connect_flags",0)&0x2c==0x2c for row in peer_rows)
                        if not match:
                            result.update(status="FAIL",oracle="actual CONNECT must contain configured retained QoS1 last-will fields")
            if args.group=="tls":
                expected=hashlib.sha256(certificate_der).hexdigest()
                authenticated=sum(row.get("tls_peer_certificate_sha256")==expected for row in peer_rows)
                if authenticated<2:
                    for row in results:
                        if row["status"]=="PASS":row.update(status="FAIL",oracle="independent owned TLS peer must authenticate the exact guest certificate in both SSLContext and module-wrapper exchanges")
            evidence={"execution_report_sha256":hashlib.sha256((output/"report.json").read_bytes()).hexdigest(),
                      "evidence_zip_sha256":execution.get("evidence_sha256"),"serial_sha256":hashlib.sha256(serial.encode()).hexdigest(),
                      "firmware_sha256":execution["firmware_sha256"],"runtime_binary_sha256":execution.get("runtime_binary_sha256"),
                      "peer_requests_sha256":hashlib.sha256((output/"peer-requests.json").read_bytes()).hexdigest()}
            if (output/"evidence.zip").exists():
                with zipfile.ZipFile(output/"evidence.zip") as archive:
                    evidence["network_files"]={name:hashlib.sha256(archive.read(name)).hexdigest()
                         for name in archive.namelist() if name.endswith((".pcap",".pcapng")) or name=="network/evidence.json"}
                    evidence["audio_files"]={name:hashlib.sha256(archive.read(name)).hexdigest()
                         for name in archive.namelist() if name.startswith("audio/")}
                    if radio:
                        ble_logs=[archive.read(name).decode(errors="replace") for name in archive.namelist() if "ble" in name.lower() and name.endswith(".log")]
                        peer_ok=any(
                            ble_nus_exchange_observed(
                                log,
                                BLE_IDENTITIES[device][1],
                            )
                            for log in ble_logs
                        )
                        evidence["ble_peer_logs"]={name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if "ble"in name.lower() and name.endswith(".log")}
                        for row in results:
                            if row["status"]=="OBSERVED_PENDING_PEER":
                                row["status"]="PASS" if peer_ok else "FAIL"
                                row["oracle"]="actual NUS write and exact ACK notification independently observed by external Bumble central" if peer_ok else "external central did not confirm exact ACK notification and completed cycle"
                            elif row["status"]=="OBSERVED_PENDING_PERIPHERAL_WRITE":
                                expected=BLE_IDENTITIES[device][1].encode().hex()
                                arrived=any("BLE_PERIPHERAL_WRITE "+expected in log for log in ble_logs)
                                row["status"]="PASS" if arrived else "FAIL"
                                row["oracle"]="exact guest bytes independently received by owned peripheral over real GATT" if arrived else "owned peripheral did not receive exact guest bytes"
            for row in results:
                row.update(device_id=device,required_evidence_met=(row["status"]=="PASS" and bool(execution.get("evidence_sha256"))
                    and execution.get("cleanup",{}).get("runtime_pid_gone")is True),evidence_refs=evidence)
                if args.group.startswith("audio-") and row["api"] not in {"audio.Player.info","audio.Player.set_vol","audio.Player.get_vol","audio.Player.vol","audio.Recorder.config","audio.Recorder.create_pcm_buf"}:
                    row["required_evidence_met"]=False
                    row["remaining_oracle"]="independent PCM/file/lifecycle oracle required; state return alone is not audio functional PASS"
            successful_statuses={"PASS","EXPECTED_REJECTION","NOT_APPLICABLE_LISTENER"}
            if args.group in {"espnow","espnow-native"} and config["espnow_loopback"]:
                successful_statuses.update({"STATE_PASS","CONFIGURED_UNVERIFIED"})
            report={"schema_version":1,"device_id":device,"group":args.group,"validation":"virtual-device validation",
                    "hardware_validation":"NOT RUN","source_sha256":hashlib.sha256(source.encode()).hexdigest(),
                    "execution_report_sha256":hashlib.sha256((output/"report.json").read_bytes()).hexdigest(),
                    "session_id":execution.get("session_id"),"firmware_sha256":execution["firmware_sha256"],
                    "evidence_sha256":execution.get("evidence_sha256"),"cases":results,
                    "counts":dict(Counter(row["status"] for row in results)),
                    "status":"PASS" if code==0 and results and all(row["status"] in successful_statuses for row in results) else "FAIL"}
            report["library_lane"]=library_lane(args.group, args.m5ble_source)
            report["firmware_lane"]=execution.get("firmware_lane","stock-frozen")
            if radio and not bases and code!=0:
                report["model_blockers"]=[stock_radio_model_blocker(
                    evidence,
                    device,
                    execution.get("error"),
                )]
                if unsupported_ble_peripheral_peer(device, args.group):
                    report["status"]="NOT_RUN"
            if args.group.startswith("audio-"):
                report["audio_case"]=args.audio_case
                report["input_fixture_lane"]="explicit-diagnostic-override" if args.runtime_env_json else "service-owned-default"
            if args.group=="tls":
                report["input_fixture_lane"]="explicit-diagnostic-override" if config["tls_clock_year"]!=2026 else "service-owned-default"
                report["tls_clock_year"]=config["tls_clock_year"]
                report["certificate"]={"sha256":hashlib.sha256(certificate_der).hexdigest(),
                    "not_valid_before":certificate.not_valid_before_utc.isoformat(),
                    "not_valid_after":certificate.not_valid_after_utc.isoformat(),"server_name":"m5-api.test"}
            if args.group in {"espnow","espnow-native"} and config["espnow_loopback"]:
                report["espnow_loopback"]={
                    "status":"enabled",
                    "peer_mac":"02:00:00:00:00:42",
                    "scope":"controller DMA TX to same-guest RX DMA echo; not an external ESP-NOW peer",
                }
            candidate_source_sha256_value = candidate_source_sha256(args.group, config)
            if candidate_source_sha256_value is not None:
                report["candidate_source_sha256"] = candidate_source_sha256_value
                report["stock_firmware_result_unchanged"]=True
            save(output/"protocol-results.json",report)
            reports.append({"device_id":device,"status":report["status"],"counts":report["counts"],"failures":[{key:row[key] for key in ("api","status","error","oracle","value") if key in row} for row in results if row["status"] not in {"PASS","NOT_APPLICABLE_LISTENER"}]})
            print(json.dumps(reports[-1],ensure_ascii=False),flush=True)
    finally:
        for peer in peers:peer.shutdown();peer.server_close()
        for thread in threads:thread.join(timeout=2)
        save(args.out_dir/"peer-requests.json",peer_requests)
        save(args.out_dir/"summary.json",{"schema_version":1,"group":args.group,"reports":reports,
             "peer_request_count":len(peer_requests),"peer_requests_sha256":hashlib.sha256((args.out_dir/"peer-requests.json").read_bytes()).hexdigest()})
    return 0 if reports and all(row["status"]=="PASS" for row in reports) else 1


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--device",choices=DEVICE_CHOICES,action="append",default=[])
    parser.add_argument("--group",choices=("http","sockets","easysocket","mqtt","network","modbus","modbus-candidate","modbus-rtu","modbus-rtu-slave","ppp","ezdata","requests-candidate","audio-player","audio-recorder","ble-nus","m5ble-server","ble-client","m5ble-client","espnow","espnow-native","tls"),required=True)
    parser.add_argument("--requests2-source",type=Path)
    parser.add_argument("--modbus-master-source",type=Path)
    parser.add_argument("--m5ble-source",type=Path)
    parser.add_argument("--base-image",action="append",default=[],help="device_id=/path/to/explicit-HCI-test-base.bin")
    parser.add_argument("--expected-base-sha256",action="append",default=[],help="device_id=exact-SHA256; mandatory for each alternate base")
    parser.add_argument("--core2-elf",type=Path,help="matching Core2 UIFlow2 ELF for core2-native-hci")
    parser.add_argument("--uart-repl-bootstrap",choices=("dupterm","native"),
                        help="guest bootstrap for an explicit base with a native UART REPL")
    parser.add_argument("--audio-case",choices=("all","raw","tone","file"),default="all")
    parser.add_argument("--runtime-env-json",type=Path)
    parser.add_argument("--tls-clock-year",type=int,default=2026,help="non-default RTC years are diagnostic input and excluded from stock join")
    parser.add_argument("--token-file",type=Path)
    parser.add_argument("--out-dir",type=Path)
    parser.add_argument("--timeout",type=int,default=150)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.device:args.device=["cores3","cardputer-adv"]
    raise SystemExit(run(args))
