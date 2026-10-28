#!/usr/bin/env python3
"""Join exact device exports and behavioral evidence without treating recipes as PASS."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from build_system_inventory import canonical_api


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def json_records(text,tag):
    for match in re.finditer(r"(?:^|\n)"+re.escape(tag)+r" ",text):
        try:value,_end=json.JSONDecoder().raw_decode(text[match.end():])
        except json.JSONDecodeError:continue
        yield value


def owner(api,scope):
    if scope=="optional-accessory":return "selected-accessory-lane"
    if scope=="shared-runtime-hardware":return "hardware-api-lane"
    if api.startswith(("audio.","network.","socket.","requests2.","easysocket.","umqtt.","modbus.","ezdata.","m5ble.","bleuart.","m5espnow.","bluetooth.","espnow.")):
        return "device-api-protocol-lane"
    return "root-system-lane"


EXPORT_TAGS=("SYSTEM_EXPORT","VISION_EXPORT","DL_EXPORT","USB_EXPORT")
API_TAGS=("SYSTEM_API","VISION_API","DL_API","USB_API")


def execution_receipt_complete(execution):
    fields=('source_sha256','firmware_sha256','runtime_binary_sha256','evidence_sha256')
    return (execution.get('status')=='EXECUTED'and execution.get('cleanup',{}).get('runtime_pid_gone')is True
        and all(isinstance(execution.get(field),str)and re.fullmatch('[0-9a-f]{64}',execution[field])for field in fields))


def add_exports(raw,device,proof,exports,absent,canonical):
    """Accept both typed reflection and explicit complete member-name lists."""
    for tag in EXPORT_TAGS:
        for row in json_records(raw,tag):
            path=canonical(row["path"])
            if row.get("status") in {"ABSENT","UNAVAILABLE_ON_DEVICE"}:
                absent[device][path]=row.get("error")
                continue
            if row.get("status")not in {None,"PRESENT"}:continue
            target=exports[device].setdefault(path,{"members":{},"evidence":proof})["members"]
            for member in row.get("members",[]):
                if isinstance(member,str):
                    target[member]={"type":None,"callable":None,"evidence":proof}
                else:
                    name,type_name,callable_flag=member
                    target[name]={"type":type_name,"callable":callable_flag,"evidence":proof}


def selected_attempt(attempts):
    """Latest run wins; every subcase in that run must satisfy the oracle."""
    if not attempts:return None
    directory=attempts[-1]["run_directory"]
    current=[row for row in attempts if row["run_directory"]==directory]
    failures=[row for row in current if row["status"] not in {"PASS","EXPECTED_REJECTION","NOT_APPLICABLE_LISTENER"}]
    chosen=dict(failures[0] if failures else current[-1])
    chosen["required_evidence_met"]=all(row.get("required_evidence_met") is True for row in current)
    chosen["subcase_count"]=len(current)
    if len(current)>1:
        chosen["subcases"]=[{key:row[key]for key in ("status","value","model","oracle","error","required_evidence_met")if key in row}for row in current]
    return chosen


def summarize(inventory_path,runs,reflections):
    inventory=json.loads(inventory_path.read_text())
    aliases=inventory.get("source_declared_import_aliases",{})
    canonical=lambda api:canonical_api(api,aliases)
    declarations={row["api"]:row for row in inventory["entries"]}
    exports={device:{} for device in inventory["devices"]}
    absent={device:{} for device in inventory["devices"]}
    metadata=[]
    for device,path in reflections:
        raw=path.read_text(errors="replace")
        proof={"path":str(path),"sha256":digest(path)}
        metadata.append({"device_id":device,**proof})
        add_exports(raw,device,proof,exports,absent,canonical)
    observations={}
    identities={device:{}for device in inventory["devices"]}
    model_blockers={device:[]for device in inventory["devices"]}
    diagnostics=[]
    for directory in runs:
        execution_path=directory/"report.json"
        if not execution_path.exists():raise ValueError("missing guest report: "+str(directory))
        execution=json.loads(execution_path.read_text())
        device=execution["device_id"]
        serial=directory/"serial.txt"
        text=serial.read_text(errors="replace") if serial.exists() else ""
        protocol_path=directory/"protocol-results.json"
        report=json.loads(protocol_path.read_text()) if protocol_path.exists() else {}
        firmware_lane=report.get("firmware_lane",execution.get("firmware_lane",
            "caller-pinned-candidate"if execution.get("base_lane")=="caller-pinned-candidate"else"stock-frozen"))
        nonstock=(report.get("library_lane")=="candidate-source" or
                  report.get("input_fixture_lane")=="explicit-diagnostic-override" or
                  firmware_lane!="stock-frozen")
        if nonstock:
            diagnostics.append({"device_id":device,"path":str(protocol_path if protocol_path.exists() else execution_path),
                                "sha256":digest(protocol_path if protocol_path.exists() else execution_path),
                                "lane":report.get("library_lane"),"input_fixture_lane":report.get("input_fixture_lane"),
                                "firmware_lane":firmware_lane})
            continue
        if serial.exists():
            add_exports(text,device,{"path":str(serial),"sha256":digest(serial)},exports,absent,canonical)
            for identity in json_records(text,"SYSTEM_ALIAS"):
                if identity.get("identical")is True:
                    identities[device].setdefault(canonical(identity["api"]),[]).append({
                        "target":canonical(identity["target"]),"scope":identity.get("scope"),
                        "serial_sha256":digest(serial),"run_directory":str(directory)})
        if protocol_path.exists():
            rows=report["cases"]
            model_blockers[device].extend(report.get("model_blockers",[]))
        else:
            rows=[row for tag in API_TAGS for row in json_records(text,tag)]
            for row in rows:
                row["required_evidence_met"]=(execution_receipt_complete(execution)and row["status"]=="PASS")
                row["evidence_refs"]={"execution_report_sha256":digest(execution_path),"serial_sha256":digest(serial),
                                      "evidence_zip_sha256":execution.get("evidence_sha256"),"firmware_sha256":execution.get("firmware_sha256"),
                                      "runtime_binary_sha256":execution.get("runtime_binary_sha256")}
                if row["api"].startswith("dl.DetectionResult."):
                    row["oracle"]=row.get("oracle","Result accessor type/range assertion only; detector inference has its own positive and negative oracles.")
                    row["evaluation_scope"]="result-accessor-only"
                if row["status"]!="PASS":
                    row["remaining_oracle"]=row.get("reason",row.get("required_data_plane","Behavioral assertion did not establish functional PASS."))
        for row in rows:
            key=(device,canonical(row["api"]))
            observed={**row,"run_directory":str(directory)}
            if observed.get('required_evidence_met')is True and not execution_receipt_complete(execution):
                observed['required_evidence_met']=False
                observed['remaining_oracle']='Execution receipt lacks complete firmware/source/runtime/ZIP SHA256 identity or stopped runtime proof.'
            if observed["api"].startswith("audio.") and observed["api"] not in {"audio.Player.info","audio.Player.set_vol","audio.Player.get_vol","audio.Player.vol","audio.Recorder.config","audio.Recorder.create_pcm_buf"}:
                if observed.get("data_plane_oracle")!="PASS":observed["required_evidence_met"]=False
            observations.setdefault(key,[]).append(observed)
    # Every public runtime export remains in the inventory.  Non-callables are
    # inventory-only; they must not silently shrink the denominator or acquire
    # functional PASS from their presence.
    for device,paths in exports.items():
        for path,record in paths.items():
            for name,member in record["members"].items():
                api=canonical(path+"."+name)
                scope="shared-runtime-hardware" if api.startswith(("machine.","esp32.")) else "system-communication"
                declarations.setdefault(api,{"api":api,"kind":"runtime-callable" if member["callable"] else "runtime-noncallable"if member["callable"]is False else"runtime-export-member","scope":scope,
                                              "sources":[],"aliases":[],"runtime_only":True})
    # Original successful method execution is also evidence that an inherited
    # public member exists, even when the initial reflection omitted its owner.
    # Limit this bridge to known concrete Modbus inheritance; synthetic recipe
    # labels remain visible in observations_without_inventory_owner.
    inherited=re.compile(r"^(?:modbus\.ModbusRTUMaster\.[a-z_]+_async|modbus\.frame\.Modbus(?:RTU|TCP)Frame\.get_frame)$")
    for (_device,api),attempts in observations.items():
        if inherited.fullmatch(api):
            declarations.setdefault(api,{"api":api,"kind":"behaviorally-observed-callable","scope":"system-communication",
                                         "sources":[],"aliases":[],"runtime_only":True})
    joined=[]
    for api,declaration in sorted(declarations.items()):
        for device in inventory["devices"]:
            attempts=observations.get((device,api),[])
            chosen=selected_attempt(attempts)
            path,name=api.rsplit(".",1) if "." in api else (api,"")
            exported=path in exports[device] and name in exports[device][path]["members"]
            member=exports[device].get(path,{}).get("members",{}).get(name,{})
            row={"api":api,"device_id":device,"kind":declaration["kind"],"scope":declaration["scope"],
                 "owner":owner(api,declaration["scope"]),"aliases":declaration.get("aliases",[]),
                 "status":"NOT_RUN","required_evidence_met":False,"export_status":"PRESENT" if exported else "NOT_OBSERVED",
                 "export_callable":member.get("callable"),"export_type":member.get("type"),
                 "export_evidence":member.get("evidence"),
                 "blocker":"No behavioral result supplied for this exact API/device; a declared recipe is planning only."}
            missing=next((module for module in absent[device] if api==module or api.startswith(module+".")),None)
            if declaration["kind"] in {"constant","runtime-noncallable"}:
                row.update(status="INVENTORY_ONLY",blocker="Constant or non-callable enumeration is not a functional test.")
            elif missing:
                row.update(status="UNAVAILABLE_ON_DEVICE",blocker=f"Actual stock guest import {missing} failed: {absent[device][missing]}")
            elif declaration["scope"]=="optional-accessory":
                row.update(status="NOT_RUN",blocker="Optional accessory catalog entry; this exact accessory/API/device has no selected joint execution result.")
            elif not exported and path in exports[device] and declaration["kind"]!="constructor":
                row.update(status="UNAVAILABLE_ON_DEVICE",blocker=f"Actual complete public export of {path} lacks member {name}.")
            model_boundary=next((record for record in model_blockers[device]
                if any(api==prefix or api.startswith(prefix+".")for prefix in record["api_prefixes"])),None)
            if model_boundary and not chosen:
                row.update(status="BLOCKED_MODEL",blocker=model_boundary["reason"],evidence_refs=model_boundary.get("evidence_refs",{}))
            if chosen:
                status=chosen["status"]
                met=chosen.get("required_evidence_met") is True
                row.update(status=("PASS" if met else "OBSERVED_INCOMPLETE_EVIDENCE") if status=="PASS" else status,
                           required_evidence_met=met,oracle=chosen.get("oracle"),error=chosen.get("error"),
                           evidence_refs=chosen.get("evidence_refs",{}),run_directory=chosen["run_directory"],
                           blocker=None if met else chosen.get("remaining_oracle","Behavioral failure or required evidence incomplete."),
                           attempts=len(attempts),subcase_count=chosen["subcase_count"])
                if "subcases" in chosen:row["subcases"]=chosen["subcases"]
                if "evaluation_scope"in chosen:row["evaluation_scope"]=chosen["evaluation_scope"]
            elif api in identities[device]:
                # Exact guest function identity closes implementation coverage
                # only through the separately named concrete transport. It is
                # never a standalone abstract-base functional PASS.
                candidates=[(identity,selected_attempt(observations.get((device,identity["target"]),[])))
                    for identity in identities[device][api]]
                candidates=[(identity,result)for identity,result in candidates if result is not None]
                if candidates:
                    identity,result=candidates[-1];met=result.get("required_evidence_met")is True
                    row.update(status="INHERITED_IMPLEMENTATION_"+result["status"],required_evidence_met=met,
                        evaluation_scope=identity["scope"],implementation_target=identity["target"],
                        identity_evidence=identity,evidence_refs=result.get("evidence_refs",{}),
                        oracle="Actual stock guest reports identical inherited function objects; behavioral evidence belongs to the named concrete transport.",
                        blocker=None if met else"Concrete transport result failed or lacks required behavioral evidence.")
            joined.append(row)
    return {"schema_version":1,"scope":"system plus optional accessory source/export/behavior join",
            "inventory_sha256":digest(inventory_path),"source_commit":inventory["source_commit"],
            "validation":"virtual-device validation","hardware_validation":"NOT RUN",
            "reflection_evidence":metadata,"diagnostic_lanes_excluded_from_stock":diagnostics,
            "observations_without_inventory_owner":[{"device_id":device,"api":api,"run_directory":rows[-1]["run_directory"]}
                for (device,api),rows in sorted(observations.items()) if api not in declarations],
            "counts":dict(Counter(row["status"]for row in joined)),
            "system_counts":dict(Counter(row["status"]for row in joined if row["scope"]=="system-communication")),
            "known_callable_not_run_by_device":{device:sum(row["device_id"]==device and row["scope"]=="system-communication"
                and row["status"]=="NOT_RUN"and row["export_callable"]is True for row in joined)for device in inventory["devices"]},
            "entries":joined}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory",type=Path,default=Path(__file__).with_name("inventory_system.source.json"))
    parser.add_argument("--run",type=Path,action="append",default=[])
    parser.add_argument("--reflection",action="append",default=[],help="device_id=/path/to/serial.txt")
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    pairs=[(value.split("=",1)[0],Path(value.split("=",1)[1]))for value in args.reflection]
    result=summarize(args.inventory,args.run,pairs)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"counts":result["counts"],"system_counts":result["system_counts"]},ensure_ascii=False))
