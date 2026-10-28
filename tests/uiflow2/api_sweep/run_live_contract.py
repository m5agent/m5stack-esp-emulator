#!/usr/bin/env python3
"""Exercise session and Preview contracts with visible CoreS3 UIFlow2 guests.

Inputs are explicit virtual fixtures. Guest original Unit drivers must consume
them over the emulated I2C controller; host input acceptance is not the oracle.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import uuid
import zipfile

from run_device_api import Client, INVENTORY, save


def require(value, message):
    if not value:
        raise RuntimeError(message)


def attachments():
    return [{"id": "hub", "unit_id": "hub", "port_id": "port-a"},
            {"id": "env", "unit_id": "env-iii", "parent_id": "hub", "port_id": "grove-1"},
            {"id": "ncir", "unit_id": "ncir", "parent_id": "hub", "port_id": "grove-2"},
            {"id": "encoder", "unit_id": "encoder", "parent_id": "hub", "port_id": "grove-3"}]


def source(nonce, phase, pins):
    color = 0x113355 if phase == "A" else 0x225511
    return f'''import sys,json,time,M5
from machine import I2C,Pin
from unit import ENVUnit,NCIRUnit,EncoderUnit
key={"_m5_api_contract_" + nonce!r}
state=sys.modules.get(key)
if state is None:
 state={{"runs":0}}
 sys.modules[key]=state
state["runs"]+=1
M5.begin()
screen=M5.Display
screen.setBrightness(255)
screen.fillScreen({color})
screen.setTextColor(0xFFFFFF,{color})
screen.setTextSize(1)
bus=I2C(0,scl=Pin({pins['white']}),sda=Pin({pins['yellow']}),freq=100000)
scan=sorted(bus.scan())
assert scan==[64,68,90,112],"wrong HUB bus"
env=ENVUnit(bus,type=3)
ncir=NCIRUnit(bus)
encoder=EncoderUnit(bus)
encoder.fill_color({0xFF0000 if phase == 'A' else 0x00FF00})
print("API_CONTRACT_READY",json.dumps({{"nonce":{nonce!r},"phase":{phase!r},"runs":state['runs'],"scan":scan}}))
previous=None
while True:
 M5.update()
 values={{"env":[env.read_temperature(),env.read_humidity(),env.read_pressure()*100],"ncir":[ncir.get_ambient_temperature(),ncir.get_object_temperature()],"encoder":[encoder.get_rotary_value(),bool(encoder.get_button_status())]}}
 if values!=previous:
  screen.fillRect(0,0,320,90,{color})
  screen.setCursor(4,4)
  screen.print({phase!r}+" ENV %.1f C %.1f %%" % tuple(values['env'][:2]))
  screen.setCursor(4,24)
  screen.print("P %.1f Pa" % values['env'][2])
  screen.setCursor(4,44)
  screen.print("IR %.1f C ENC %d" % (values['ncir'][1],values['encoder'][0]))
  print("API_CONTRACT_SAMPLE",json.dumps({{"nonce":{nonce!r},"phase":{phase!r},"values":values}}))
  previous=values
 time.sleep_ms(50)
'''


def run(args):
    if not args.execute:
        print(json.dumps({"mode": "offline-plan", "device_id": "cores3", "units": attachments(),
                          "guests": ["ordinary same-guest UART session"] + (["managed Preview"] if args.preview else []),
                          "cleanup": "evidence ZIP before stop/close; preserve history"}, indent=2))
        return 0
    if args.out_dir is None or args.token_file is None:
        raise SystemExit("--out-dir and --token-file are required with --execute")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = Client(args.api, args.token_file.read_text().strip(), args.out_dir)
    rows = []
    report = {"schema_version": 1, "validation": "virtual-device validation", "hardware_validation": "NOT RUN",
              "inventory_sha256": hashlib.sha256(INVENTORY.read_bytes()).hexdigest(), "cases": rows, "status": "FAIL"}
    owned = []
    preview = None

    def call(op, path=None, payload=None, *, status=200, headers=None, label=""):
        method, template = op.split(" ", 1)
        record, body = client.call(method, path or template, payload, extra_headers=headers)
        row = {"operation_id": op, "label": label, "coverage": "positive" if status < 400 else "rejection-only",
               "http_status": record["status"], "status": "PASS" if record["status"] == status else "FAIL",
               "response_sha256": record["response_sha256"], "elapsed_seconds": record["elapsed_seconds"]}
        rows.append(row)
        save(args.out_dir / "report.json", report)
        require(record["status"] == status, f"{op}: HTTP {record['status']} (expected {status}): {body}")
        return body

    def poll(fn, predicate, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            row = fn()
            if predicate(row):
                return row
            time.sleep(.1)
        raise RuntimeError("live observation deadline exceeded")

    def binary(op, path, name, *, headers=None, expected=200):
        method = op.split(" ", 1)[0]
        rec, _ = client.call(method, path, extra_headers=headers)
        rows.append({"operation_id": op, "label": name, "coverage": "positive", "http_status": rec["status"],
                     "status": "PASS" if rec["status"] == expected else "FAIL", "response_sha256": rec["response_sha256"]})
        raw = (args.out_dir / f"{client.index:04d}.response").read_bytes()
        if expected == 200:
            (args.out_dir / name).write_bytes(raw)
        require(rec["status"] == expected, "binary response status differs: " + path)
        return rec, raw

    def serial(session_id, offset=0):
        return call("GET /sessions/{session_id}/serial", f"/sessions/{session_id}/serial?offset={offset}&limit=262144")

    def sample(session_id, nonce, phase, expected=None, offset=0, execution_id=None):
        def observed(row):
            text = row["data"]
            if execution_id is not None and not offset:
                marker = "__M5_EXEC_" + execution_id + "__:START"
                if marker not in text:
                    return False
                text = text.split(marker, 1)[1]
            if "Traceback (most recent call last)" in text:
                raise RuntimeError("guest program raised an exception")
            for line in text.splitlines():
                if line.startswith("API_CONTRACT_SAMPLE "):
                    value = json.loads(line.split(" ", 1)[1])
                    if value.get("nonce") != nonce or value.get("phase") != phase:
                        continue
                    if expected is None:
                        return True
                    got = value["values"]
                    if all(abs(a-b) < .2 for a,b in zip(got["env"][:2], expected["env"][:2])) and abs(got["env"][2]-expected["env"][2]) < 2:
                        if all(abs(a-b) < .03 for a,b in zip(got["ncir"],expected["ncir"])) and got["encoder"] == expected["encoder"]:
                            return True
            return False
        return poll(lambda: serial(session_id, offset), observed, 30)

    def evidence(session_id, name):
        _, raw = binary("GET /sessions/{session_id}/evidence", f"/sessions/{session_id}/evidence", name)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            require(archive.testzip() is None, "evidence ZIP is corrupt")
            require(any("serial" in filename for filename in archive.namelist()), "serial missing from ZIP")
        return hashlib.sha256(raw).hexdigest()

    try:
        created = call("POST /sessions", payload={"device_id": "cores3", "program_mode": "uiflow-live",
                       "units": attachments(), "ttl_seconds": 600, "ready_timeout_seconds": 60}, status=202)
        sid = created["session_id"]
        owned.append(sid)
        print(json.dumps({"session_id": sid, "phase": "api-contract-created"}), flush=True)
        path = "/sessions/" + sid
        ready = poll(lambda: call("GET /sessions/{session_id}", path), lambda row: row["state"] in {"running", "failed", "stopped"})
        require(ready["state"] == "running", "ordinary session did not become running")
        pid = ready["pid"]
        report["ordinary_session"] = {"session_id": sid, "pid": pid, "firmware_sha256": ready["firmware_sha256"]}
        pins = next(row["pins"] for row in ready["units"] if row["id"] == "env")
        call("POST /sessions/{session_id}/wait", path + "/wait", {"ready_marker": "M5EMU_UART_REPL_READY", "timeout_seconds": 10})
        call("POST /sessions/{session_id}/renew", path + "/renew", {"ttl_seconds": 600})
        nonce = uuid.uuid4().hex
        program_a = call("POST /sessions/{session_id}/program", path + "/program", {
                         "source": source(nonce, "A", pins), "expected_execution_id": None, "timeout_seconds": 30})["program"]
        sample(sid, nonce, "A", execution_id=program_a["execution_id"])
        call("GET /sessions/{session_id}/program", path + "/program")
        before = serial(sid)["next_offset"]
        call("POST /sessions/{session_id}/unit-input", path + "/unit-input", {"id": "env", "values": {"temperature-c": 31.5, "humidity-pct": 67, "pressure-pa": 98765}})
        call("POST /sessions/{session_id}/unit-input", path + "/unit-input", {"id": "ncir", "values": {"ambient-c": 17.3, "object-c": 37.1}})
        call("POST /sessions/{session_id}/unit-input", path + "/unit-input", {"id": "encoder", "values": {"counter": -12345, "pressed": True}})
        sample(sid, nonce, "A", {"env": [31.5,67,98765], "ncir": [17.3,37.1], "encoder": [-12345,True]}, before)
        units_a = call("GET /sessions/{session_id}/units", path + "/units")
        byid = {unit["id"]: unit for unit in units_a["units"]}
        require(byid["encoder"]["properties"]["led-rgb"] == [0xFF0000,0xFF0000], "guest LED writes not observed through I2C")
        require(all(byid[name]["properties"]["transactions"] > 0 for name in ("env","ncir","encoder")), "Unit controller did not observe transactions")
        call("GET /sessions/{session_id}/events", path + "/events")
        call("GET /sessions/{session_id}/device-state", path + "/device-state")
        call("GET /sessions/{session_id}/logs", path + "/logs?limit=262144")
        binary("GET /sessions/{session_id}/frame.png", path + "/frame.png", "ordinary-a.png")
        frame, _ = binary("GET /sessions/{session_id}/frame.png", path + "/frame.png?max_age_ms=1000", "ordinary-a-shared.png")
        etag = next(value for key,value in frame["headers"].items() if key.lower()=="etag")
        binary("GET /sessions/{session_id}/frame.png", path + "/frame.png?max_age_ms=1000", "ordinary-a-etag", headers={"If-None-Match": etag}, expected=304)
        call("GET /sessions/{session_id}/qom/list", path + "/qom/list?path=/machine/units/encoder")
        call("GET /sessions/{session_id}/qom", path + "/qom?path=/machine/units/encoder&property=counter")
        qom_a = call("POST /sessions/{session_id}/qom-snapshot", path + "/qom-snapshot", {"path":"/machine/units/encoder","depth":0})
        call("POST /sessions/{session_id}/qom", path + "/qom", {"path":"/machine/units/encoder","property":"counter","value":42})
        qom_b = call("POST /sessions/{session_id}/qom-snapshot", path + "/qom-snapshot", {"path":"/machine/units/encoder","depth":0})
        diff = call("GET /sessions/{session_id}/qom/diff", path + f"/qom/diff?before={qom_a['snapshot_id']}&after={qom_b['snapshot_id']}")
        require(diff.get("changed"), "QOM snapshot diff failed to detect controller input")
        call("GET /sessions/{session_id}/flash", path + "/flash")
        flash_a = call("POST /sessions/{session_id}/flash-snapshot", path + "/flash-snapshot")
        flash_b = call("POST /sessions/{session_id}/flash-snapshot", path + "/flash-snapshot")
        require(call("GET /sessions/{session_id}/flash/diff", path + f"/flash/diff?before={flash_a['snapshot_id']}&after={flash_b['snapshot_id']}")["changed_bytes"] == 0, "identical Flash snapshots differ")
        call("POST /sessions/{session_id}/input", path + "/input", {"kind":"touch","x":20,"y":20})
        program_b = call("POST /sessions/{session_id}/program", path + "/program", {
                         "source": source(nonce, "B", pins), "expected_execution_id": program_a["execution_id"], "timeout_seconds":30})["program"]
        result_b = sample(sid, nonce, "B", execution_id=program_b["execution_id"])
        require('"runs": 2' in result_b["data"] or '"runs":2' in result_b["data"], "same-guest sys.modules state did not survive Run")
        require(program_a["pid"] == program_b["pid"] == pid, "program replacement changed guest PID")
        report["ordinary_evidence_sha256"] = evidence(sid, "ordinary-evidence.zip")
        if args.reset:
            reset_offset=serial(sid)["next_offset"]
            call("POST /sessions/{session_id}/reset", path + "/reset")
            call("POST /sessions/{session_id}/wait", path + "/wait", {"ready_marker":"M5EMU_UART_REPL_READY","timeout_seconds":15})
            poll(lambda:serial(sid,reset_offset),lambda row:"ESP-ROM:" in row["data"] and "M5EMU_UART_REPL_READY" in row["data"],30)
            require(call("GET /sessions/{session_id}",path)["pid"]==pid,"controller reset replaced the VM process")
            report["ordinary_final_evidence_sha256"] = evidence(sid, "ordinary-final-evidence.zip")
        call("DELETE /sessions/{session_id}", path + "?purge=0&retain_flash=1")
        terminal = call("GET /sessions/{session_id}", path)
        require(terminal["state"] in {"stopped","failed"}, "ordinary session did not terminate")
        require(terminal["firmware_sha256"] == ready["firmware_sha256"], "retained history firmware changed")
        owned.remove(sid)
        if args.preview:
            create_body = {"device_id":"cores3","units":attachments(),"ttl_seconds":600}
            create_headers = {"Idempotency-Key":"api-contract-preview-"+uuid.uuid4().hex}
            preview = call("POST /previews", payload=create_body, headers=create_headers, status=202)
            pp = "/previews/"+preview["preview_id"]
            require(call("POST /previews", payload=create_body, headers=create_headers, status=202)["preview_id"] == preview["preview_id"], "Preview idempotency allocated a second guest")
            preview = poll(lambda:call("GET /previews/{preview_id}", pp),lambda row:row["state"] in {"ready","failed","closed","unknown"})
            require(preview["state"]=="ready", "Preview did not become ready")
            epoch = preview["owner_epoch"]
            psid = preview["session_id"]
            pguest = call("GET /sessions/{session_id}", "/sessions/"+psid)
            ppins = next(unit["pins"] for unit in pguest["units"] if unit["id"]=="env")
            pnonce=uuid.uuid4().hex
            report["preview_session"]={"preview_id":preview["preview_id"],"session_id":psid,"pid":pguest["pid"],"firmware_sha256":pguest["firmware_sha256"]}

            def preview_run(phase):
                package={"source_kind":"uiflow2-package","entrypoint":"main.py","files":{"main.py":{"encoding":"utf8","data":source(pnonce,phase,ppins)}}}
                revision=call("POST /program-revisions",payload=package,status=201)["revision"]
                current=call("GET /previews/{preview_id}",pp)
                body={"revision_id":revision["revision_id"],"expected_owner_epoch":epoch,"expected_generation":current["generation"],"timeout_seconds":60}
                headers={"Idempotency-Key":"api-contract-run-"+uuid.uuid4().hex}
                receipt=call("POST /previews/{preview_id}/runs",pp+"/runs",body,status=202,headers=headers)
                require(call("POST /previews/{preview_id}/runs",pp+"/runs",body,status=202,headers=headers)["run_id"]==receipt["run_id"],"Run retry allocated twice")
                rp=pp+"/runs/"+receipt["run_id"]
                running=poll(lambda:call("GET /previews/{preview_id}/runs/{run_id}",rp),lambda row:row["state"] in {"running","failed","unknown","cancelled"})
                require(running["state"]=="running","Preview Run did not become running")
                sample(psid,pnonce,phase,execution_id=running["execution_id"])
                return running,rp

            arun,arun_path=preview_run("A")
            offset=serial(psid)["next_offset"]
            for instance,values in (("env",{"temperature-c":18.2,"humidity-pct":42,"pressure-pa":102345}),
                                    ("ncir",{"ambient-c":31.5,"object-c":53.2}),("encoder",{"counter":32767,"pressed":False})):
                receipt=call("POST /previews/{preview_id}/input",pp+"/input",{"expected_owner_epoch":epoch,"expected_run_id":arun["run_id"],"unit_input":{"id":instance,"values":values}})
                require(receipt["execution_id"]==arun["execution_id"],"Preview input receipt changed Run identity")
            sample(psid,pnonce,"A",{"env":[18.2,42,102345],"ncir":[31.5,53.2],"encoder":[32767,False]},offset)
            frame,_=binary("GET /previews/{preview_id}/runs/{run_id}/frame.png",arun_path+"/frame.png?max_age_ms=1000","preview-a.png")
            frame_headers={k.lower():v for k,v in frame["headers"].items()}
            require(frame_headers["x-run-id"]==arun["run_id"] and frame_headers["x-frame-execution-id"]==arun["execution_id"],"Preview frame is not fenced to this Run")
            binary("GET /previews/{preview_id}/runs/{run_id}/frame.png",arun_path+"/frame.png?max_age_ms=1000","preview-a-etag",headers={"If-None-Match":frame_headers["etag"]},expected=304)
            call("POST /previews/{preview_id}/renew",pp+"/renew",{"expected_owner_epoch":epoch,"ttl_seconds":600})
            brun,brun_path=preview_run("B")
            require(call("GET /sessions/{session_id}","/sessions/"+psid)["pid"]==pguest["pid"],"Preview replaced the guest")
            call("POST /previews/{preview_id}/runs/{run_id}/cancel",brun_path+"/cancel",{"expected_owner_epoch":epoch},status=202)
            cancelled=poll(lambda:call("GET /previews/{preview_id}/runs/{run_id}",brun_path),lambda row:row["state"] in {"cancelled","unknown","failed"})
            require(cancelled["state"]=="cancelled" and cancelled["interrupt_ack"]=="confirmed","Preview cancel lacks actual raw-prompt confirmation")
            preview_run("A")
            report["preview_evidence_sha256"]=evidence(psid,"preview-evidence.zip")
            call("POST /previews/{preview_id}/close",pp+"/close",{"expected_owner_epoch":epoch},status=202)
            closed=poll(lambda:call("GET /previews/{preview_id}",pp),lambda row:row["state"] in {"closed","failed","unknown"})
            require(closed["state"]=="closed","Preview did not close")
            retained=call("GET /sessions/{session_id}","/sessions/"+psid)
            require(retained["state"]=="stopped" and not retained.get("flash_retained"),"Preview close did not release guest Flash while retaining history")
            preview=None
        report["status"] = "PASS"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if preview is not None:
            try:
                if preview.get("session_id"):
                    evidence(preview["session_id"],"preview-failure-evidence.zip")
            finally:
                pp="/previews/"+preview["preview_id"]
                call("POST /previews/{preview_id}/close",pp+"/close",{"expected_owner_epoch":preview["owner_epoch"]},status=202)
                poll(lambda:call("GET /previews/{preview_id}",pp),lambda row:row["state"] in {"closed","failed","unknown"})
        for sid in owned:
            try:
                evidence(sid, "failure-evidence.zip")
            finally:
                call("DELETE /sessions/{session_id}", "/sessions/" + sid + "?purge=0&retain_flash=1")
        report["positive_operations_tested"] = sorted({row["operation_id"] for row in rows if row["coverage"] == "positive" and row["status"] == "PASS"})
        save(args.out_dir / "report.json", report)
    print(json.dumps({"status":report["status"], "cases":len(rows), "positive_operations":len(report["positive_operations_tested"])}), flush=True)
    return 0


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file",type=Path)
    parser.add_argument("--out-dir",type=Path)
    parser.add_argument("--reset",action="store_true",help="exercise reset after all application oracles/evidence are collected")
    parser.add_argument("--preview",action="store_true",help="also exercise the authenticated managed Preview/Run lifecycle")
    parser.add_argument("--execute",action="store_true")
    raise SystemExit(run(parser.parse_args()))
