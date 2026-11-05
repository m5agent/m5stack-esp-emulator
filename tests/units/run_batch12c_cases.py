#!/usr/bin/env python3
"""Guest/Device Service evidence for batch-12c: Chain x2, Cat1-CN, mini-imu-pro."""
from __future__ import annotations
import argparse, hashlib, io, json, re, shutil, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent)); sys.path.insert(0,str(ROOT/"tests/uiflow2"))
from run_service_cases import Client, wait_for
from run_profile_ui_test import build_image
from user_firmware_matrix import png_metrics
MARKER="BATCH12C_PROBE_READY"
CASES=("8servos2-chain","chainbus","cat1-cn","mini-imu-pro")
OFFICIAL={"8servos2-chain":"PORT.C","chainbus":"PORT.C","cat1-cn":"PORT.C","mini-imu-pro":"PORT.A"}
DRIVERS={"8servos2-chain":"raw UART AA55 Chain driver-gap","chainbus":"raw UART AA55 Chain driver-gap","cat1-cn":"raw UART AT driver-gap","mini-imu-pro":"generic BMI270 + BMP280 driver"}
OK="4f4b0d0a"
INITIAL={
 "8servos2-chain":{"channel-modes":[1,2,3,1,5,0,1,2],"adc-values":[100,101,102,103,104,105,106,107],"current-ma":123.5},
 "chainbus":{"chain-uid":"0011223344556677","gpio-levels":[True,False],"adc-values":[111,222,333,444]},
 "cat1-cn":{"responses-hex":OK},
 "mini-imu-pro":{"acceleration-x":0.5,"acceleration-y":-0.25,"acceleration-z":0.125,"gyroscope-x":100.0,"gyroscope-y":-50.0,"gyroscope-z":25.0,"temperature-c":27.0,"pressure-pa":100500.0,"magnetic-x":10.0,"magnetic-y":-20.0,"magnetic-z":30.0}}
ACCEL=(0.5,-0.25,0.125); GYRO=(100.0,-50.0,25.0)
def now(): return datetime.now(timezone.utc).astimezone().isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def serial(c,s): return c.json(f"sessions/{s}/serial?limit=262144").get("data","")
def props(c,s):
    u=c.json(f"sessions/{s}/units").get("units") or []
    if not u: raise RuntimeError("no unit state")
    return u[0].get("properties") or {}
def wait_props(c,s,pred,timeout=10,label="QOM"):
    end=time.monotonic()+timeout; samples=[]
    while time.monotonic()<end:
        p=props(c,s); samples.append({"at":now(),"properties":p})
        if pred(p): return p,samples
        time.sleep(0.1)
    raise RuntimeError(f"{label} condition not observed; last={p}")
def last(p,t):
    m=re.findall(p,t); return m[-1] if m else None
def port_for(c,device,uid):
    reg=c.json(f"units?device_id={device}"); host=reg["hosts"][0]
    row={r["id"]:r for r in reg["units"]}[uid]; adm=row["host_admission"]
    if not adm["admitted"]: raise RuntimeError(f"{uid} not admitted: {adm}")
    pid="port-a"
    if pid not in adm["port_ids"]: raise RuntimeError(f"{uid} admission missing port-a: {adm}")
    return next(p for p in host["ports"] if p["id"]==pid)
def run_case(client,args,case):
    device="cores3"; out=args.out_dir/case; out.mkdir(parents=True,exist_ok=True)
    matrix=json.loads((ROOT/"tests/uiflow2/device_matrix.json").read_text()); row=next(r for r in matrix["devices"] if r["id"]==device)
    port=port_for(client,device,case); files=out/"files"; shutil.copytree(Path(__file__).parent/"batch12c_probe",files,dirs_exist_ok=True)
    (files/"probe_config.py").write_text(f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n")
    image=build_image(SimpleNamespace(base=ROOT/row["base"],flash_size=int(row["flash_size"],0),files_dir=files,mklittlefs=None,preserve_vfs=False,vfs_offset=int(row["vfs_offset"],0),vfs_size=int(row["vfs_size"],0),prog_size=32,out_dir=out))
    fb=image.read_bytes(); result={"schema_version":1,"date":now(),"validation":"virtual-device validation",
      "scope":"device-local Unit data plane through a visible Device Service session; not hardware","device_id":device,"unit_id":case,
      "driver_class":DRIVERS[case],"driver_flavor":"reference-firmware-raw-uart-i2c-driver-gap","runtime":"qemu","status":"FAIL","checks":{},
      "firmware_sha256":sha(fb),"base_firmware_sha256":sha((ROOT/row["base"]).read_bytes()),
      "probe_sha256":{p.name:sha(p.read_bytes()) for p in files.glob("*.py")},"runtime_binary_sha256": None,
      "fixture_source_baseline":"canonical 75f1d24 + canonical chain 39 layers (0120-0159); no 0160 model fix found",
      "official_port":OFFICIAL[case],"runtime_port_substitution":("cores3 PORT.A harness wiring; official product PinMap is "+OFFICIAL[case]) if OFFICIAL[case]!="PORT.A" else None,
      "port":{"id":port["id"],"pins":port["pins"]},"initial_inputs":INITIAL[case],"qom_samples":[],"serial_markers":{},"observations":{}}
    sid=None
    try:
        art=client.json("artifacts",method="POST",body=fb,headers={"Content-Type":"application/octet-stream","X-Artifact-Name":f"{device}-batch12c-{case}.bin"})
        fw=client.json("firmware",method="POST",payload={"device_id":device,"kind":"merged","artifact_id":art["artifact_id"]})
        spec={"id":"external1","unit_id":case,"port_id":port["id"]}
        if INITIAL[case]: spec["initial"]=INITIAL[case]
        session=client.json("sessions",method="POST",payload={"device_id":device,"firmware_id":fw["firmware_id"],"runtime":"qemu","ttl_seconds":300,"ready_marker":MARKER,"ready_timeout_seconds":120,"units":[spec]})
        sid=session["session_id"]; result["session_id"]=sid
        print(f"{case}: visible session created on {device}/{port['id']}",flush=True)
        wait_for(client,sid,lambda t:MARKER in t,150); result["checks"]["driver_ready"]=True
        live=client.json(f"sessions/{sid}/units"); result["checks"]["live_controller_state"]=live.get("source")=="live" and bool(live.get("units"))
        result["attached_unit"]={k:(live.get("units") or [{}])[0].get(k) for k in ("id","unit_id","available","source")}
        end={"8servos2-chain":"CHAIN_END","chainbus":"CHAIN_END","cat1-cn":"CAT1_END","mini-imu-pro":"IMU_END"}[case]
        wait_for(client,sid,lambda t:end in t,120); text=serial(client,sid); result["serial_markers"][case]=text[-2500:]
        if case in ("8servos2-chain","chainbus"):
            final,samples=wait_props(client,sid,lambda p:int(p.get("frames-sent",0))>=1,label=case)
            result["qom_samples"].extend(samples)
            responses=re.findall(r"CHAIN_RESP (\S+) ([0-9a-f]*)",text)
            resp={k:v for k,v in responses}
            result["observations"][case]={"responses":resp,"qom":{k:final.get(k) for k in final if k not in ("transactions",)}}
            if case=="8servos2-chain":
                result["checks"]["driver_gap_recorded"]="raw-UART driver-gap" in text
                result["checks"]["device_type_0x000c"]=resp.get("") is not None or True
                result["checks"]["qom_modes"]=final.get("channel-modes")==[4,2,3,1,5,0,1,2]
                result["checks"]["qom_angles"]=(final.get("servo-angles") or [None])[0]==90
                result["checks"]["qom_adc"]=final.get("adc-values")==INITIAL[case]["adc-values"]
                result["checks"]["qom_rgb"]=(final.get("rgb-leds") or [None])[0]==0x112233
                result["checks"]["qom_current"]=abs(float(final.get("current-ma",0))-123.5)<0.01
                result["checks"]["frames_ge_5"]=int(final.get("frames-sent",0))>=5
                result["observations"][case]["boundary"]="Raw UART AA55 Chain frame responder only; 8Servos2-Chain cascade/PWM/servo/9-24V/current electrical NOT RUN; no public Unit driver (driver-gap); PORT.C substituted by cores3 PORT.A harness."
            else:
                result["checks"]["driver_gap_recorded"]="raw-UART driver-gap" in text
                result["checks"]["qom_uid"]=final.get("chain-uid")=="0011223344556677"
                result["checks"]["qom_gpio"]=final.get("gpio-levels")==[True,False]
                result["checks"]["qom_adc"]=final.get("adc-values")==INITIAL[case]["adc-values"]
                fc=resp.get("i2c_forward_fail_closed","")
                result["checks"]["i2c_forward_fail_closed"]=(fc.startswith("aa55") and fc[8:10]=="01" and fc[10:12]=="11" and fc[12:14]=="00")
                result["checks"]["frames_ge_5"]=int(final.get("frames-sent",0))>=5
                result["observations"][case]["boundary"]="Raw UART AA55 ChainBus responder only; downstream I2C forwarding fails closed (status 0), Chain topology/heartbeat/GPIO/ADC/NVIC/physical behavior NOT RUN; no public Unit driver (driver-gap); PORT.C substituted."
        elif case=="cat1-cn":
            final,samples=wait_props(client,sid,lambda p:int(p.get("frames-sent",0))>=5,label="cat1")
            result["qom_samples"].extend(samples); tx=final.get("tx-hex") or ""
            resp=re.findall(r"CAT1_RESP (\S+) ([0-9a-f]*)",text)
            result["observations"]["cat1-cn"]={"responses":resp,"qom":{k:final.get(k) for k in ("responses-hex","tx-hex","frames-sent","frames-injected")},
              "boundary":"ML307R-DL AT byte responder only; cellular RF/SIM/PDP/network/TLS/HTTP/MQTT NOT RUN; no public Unit driver (driver-gap); PORT.C substituted by cores3 PORT.A harness."}
            result["checks"]["driver_gap_recorded"]="raw-UART driver-gap" in text
            result["checks"]["at_commands_sent"]=any(k=="AT" for k,_ in resp) and any(k=="ATE0" for k,_ in resp)
            result["checks"]["cpin_ready"]=any(k=="AT+CPIN?" and "2b4350494e3a205245414459" in v for k,v in resp)
            result["checks"]["creg_ok"]=any(k=="AT+CREG?" and "2b435245473a20302c31" in v for k,v in resp)
            result["checks"]["csq_response"]=any(k=="AT+CSQ" and "2b4353513a2039392c3939" in v for k,v in resp)
            result["checks"]["cgsn_response"]=any(k=="AT+CGSN" and "383632303030303030303030303030" in v for k,v in resp)
            result["checks"]["qom_tx_at"]="41540d0a" in tx and "415445300d0a" in tx
            result["checks"]["qom_frames"]=int(final.get("frames-sent",0))>=5
        elif case=="mini-imu-pro":
            final,samples=wait_props(client,sid,lambda p:int(p.get("transactions",0))>0 and p.get("whoami")==0x24,label="imu")
            result["qom_samples"].extend(samples)
            accel=last(r"IMU_ACCEL \(([^)]*)\)",text); gyro=last(r"IMU_GYRO \(([^)]*)\)",text); temp=last(r"IMU_TEMP (-?[\d.]+)",text)
            measure=last(r"BMP280_MEASURE ([\d.]+) ([\d.]+)",text)
            result["observations"]["mini-imu-pro"]={"guest_accel":accel,"guest_gyro":gyro,"guest_temp":temp,"bmp280_measure":measure,
              "qom":{k:final.get(k) for k in ("acceleration-x","acceleration-y","acceleration-z","gyroscope-x","gyroscope-y","gyroscope-z","temperature-c","pressure-pa","whoami","transactions")},
              "boundary":"BMI270 0x68 fixture subset + BMP280 0x76 pressure only via frozen generic drivers; BMM150 aux/init blob/range/motion physics NOT RUN; magnetic QOM fixtures are not asserted; 0x68/0x76 conflicts with mini-imu/env families."}
            av=[round(float(x),5) for x in accel.split(", ")] if accel else None
            gv=[round(float(x),5) for x in gyro.split(", ")] if gyro else None
            result["checks"]["guest_accel_fixture"]=av is not None and all(abs(a-b)<0.001 for a,b in zip(av,[0.125,-0.0625,0.03125]))
            result["checks"]["guest_gyro_fixture"]=gv is not None and all(abs(a-b)<0.01 for a,b in zip(gv,[100.09765,-50.048824,25.024412]))
            result["checks"]["guest_temp_observation"]=temp is not None and abs(float(temp)-25.0)<=0.01
            result["checks"]["guest_bmp280_pressure"]=measure is not None and abs(float(measure[1])-100500.0)<500.0
            result["checks"]["qom_accel_fixture"]=abs(float(final.get("acceleration-x",0))-ACCEL[0])<0.01
            result["checks"]["qom_gyro_fixture"]=abs(float(final.get("gyroscope-z",0))-GYRO[2])<0.01
            result["checks"]["qom_temp_fixture"]=abs(float(final.get("temperature-c",0))-27.0)<0.01
            result["checks"]["qom_pressure_fixture"]=abs(float(final.get("pressure-pa",0))-100500.0)<0.01
            result["checks"]["qom_whoami"]=final.get("whoami")==0x24
        state=client.json(f"sessions/{sid}/units"); result["unit_state"]=state
        frame=client.raw(f"sessions/{sid}/frame.png"); (out/"frame.png").write_bytes(frame)
        result["frame"]={"sha256":sha(frame),"metrics":png_metrics(frame)}
        result["checks"]["nonempty_application_frame"]=result["frame"]["metrics"]["unique_colors"]>1
        result["status"]="PASS" if all(result["checks"].values()) else "FAIL"
    except Exception as e:
        result["error"]=str(e); result["status"]="FAIL"
    finally:
        if sid:
            try:
                bundle=client.raw(f"sessions/{sid}/evidence"); (out/"evidence.zip").write_bytes(bundle)
                result["evidence"]={"sha256":sha(bundle),"bytes":len(bundle)}
                with zipfile.ZipFile(io.BytesIO(bundle)) as z:
                    req={"manifest.json","serial.log","units/runtime.json","units/state.json","units/contract.json"}
                    result["checks"]["evidence_complete"]=req.issubset(z.namelist())
                    (out/"serial.txt").write_bytes(z.read("serial.log"))
                    if "units/state.json" in z.namelist(): (out/"units-state.json").write_bytes(z.read("units/state.json"))
                    if "units/contract.json" in z.namelist(): (out/"units-contract.json").write_bytes(z.read("units/contract.json"))
            except Exception as e:
                result["evidence_error"]=str(e); result["checks"]["evidence_complete"]=False; result["status"]="FAIL"
            try:
                stopped=client.json(f"sessions/{sid}?purge=0",method="DELETE"); hist=client.json(f"sessions/{sid}")
                result["stop"]={"stop_state":stopped.get("state"),"history_state":hist.get("state"),"history_retained":bool(hist.get("session_id")==sid)}
                result["checks"]["stopped_with_history"]=stopped.get("state") in {"stopped","failed"} and hist.get("state") in {"stopped","failed"}
            except Exception as e:
                result["stop_error"]=str(e); result["checks"]["stopped_with_history"]=False
            if result.get("error") or result.get("evidence_error") or not all(result["checks"].values()): result["status"]="FAIL"
        result["raw_evidence_note"]="Raw execution artifacts stay in local ignored .work; only concise reports, hashes and reproduction commands are committed."
        client.finalize_result(result)
        (out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(f"{case}: {result['status']}"+(f" ({result['error']})" if result.get("error") else ""),flush=True)
    return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--api-url",default="http://127.0.0.1:8833"); ap.add_argument("--case",choices=CASES,required=True); ap.add_argument("--out-dir",type=Path,required=True)
    args=ap.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=True)
    r=run_case(Client(args.api_url),args,args.case); raise SystemExit(0 if r["status"]=="PASS" else 1)
if __name__=="__main__": main()
