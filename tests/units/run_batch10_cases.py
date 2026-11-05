#!/usr/bin/env python3
"""Guest/Device Service evidence for batch-10 a-class Units."""
from __future__ import annotations
import argparse, hashlib, io, json, re, shutil, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(ROOT / "tests/uiflow2"))
from run_service_cases import Client, wait_for  # noqa: E402
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402
MARKER="BATCH10_PROBE_READY"
QEMU_STATE=("canonical 75f1d24 + canonical chain 33 layers (0120-0152, incl. 0152 batch10 model subsets) "
            "+ 0153-unit-batch10-evidence-fixes")
CASES=("dcssr","puzzle","dof6","dof9","dof10","asr")
PORT_IDS={c:"port-a" for c in CASES}
OFFICIAL={"dcssr":"PORT.A","puzzle":"PORT.B","dof6":"PORT.A","dof9":"PORT.A","dof10":"PORT.A","asr":"PORT.C"}
DRIVERS={"dcssr":"DCSSRUnit (unit/acssr.py alias)","puzzle":"RGBUnit/SK6812 generic 64 LEDs (no unit/puzzle.py)",
 "dof6":"driver.BMI270 generic (no Unit DoF driver)","dof9":"driver.BMI270 generic (BMM350 NOT modeled)",
 "dof10":"driver.BMI270 generic (BMM350/SPA06 NOT modeled)","asr":"raw UART AA55 frame (no unit/asr.py)"}
ACCEL=(0.5,-0.25,0.125); GYRO=(100.0,-50.0,25.0); TEMP=27.0
INITIAL={
 "dcssr":{}, "puzzle":{},
 "dof6":{"acceleration-x":ACCEL[0],"acceleration-y":ACCEL[1],"acceleration-z":ACCEL[2],
         "gyroscope-x":GYRO[0],"gyroscope-y":GYRO[1],"gyroscope-z":GYRO[2],"temperature-c":TEMP},
 "dof9":{"acceleration-x":ACCEL[0],"acceleration-y":ACCEL[1],"acceleration-z":ACCEL[2],
         "gyroscope-x":GYRO[0],"gyroscope-y":GYRO[1],"gyroscope-z":GYRO[2],"temperature-c":TEMP},
 "dof10":{"acceleration-x":ACCEL[0],"acceleration-y":ACCEL[1],"acceleration-z":ACCEL[2],
          "gyroscope-x":GYRO[0],"gyroscope-y":GYRO[1],"gyroscope-z":GYRO[2],"temperature-c":TEMP},
 "asr":{"responses-hex":"aa553055aa4f4b"},
}
def now(): return datetime.now(timezone.utc).astimezone().isoformat()
def sha(b): return hashlib.sha256(b).hexdigest()
def serial(client,sid): return client.json(f"sessions/{sid}/serial?limit=262144").get("data","")
def props(client,sid):
    u=client.json(f"sessions/{sid}/units").get("units") or []
    if not u: raise RuntimeError("no unit state")
    return u[0].get("properties") or {}
def wait_props(client,sid,pred,timeout=10,label="QOM"):
    end=time.monotonic()+timeout; samples=[]
    while time.monotonic()<end:
        p=props(client,sid); samples.append({"at":now(),"properties":p})
        if pred(p): return p,samples
        time.sleep(0.1)
    raise RuntimeError(f"{label} condition not observed; last={p}")
def last(p,text):
    m=re.findall(p,text); return m[-1] if m else None
def port_for(client,device,uid):
    reg=client.json(f"units?device_id={device}"); host=reg["hosts"][0]
    row={r["id"]:r for r in reg["units"]}[uid]; adm=row["host_admission"]
    if not adm["admitted"]: raise RuntimeError(f"{uid} not admitted: {adm}")
    pid=PORT_IDS[uid]
    if pid not in adm["port_ids"]: raise RuntimeError(f"{uid} admission missing {pid}: {adm}")
    return next(p for p in host["ports"] if p["id"]==pid)
def run_case(client,args,case):
    device="cores3"; out=args.out_dir/case; out.mkdir(parents=True,exist_ok=True)
    matrix=json.loads((ROOT/"tests/uiflow2/device_matrix.json").read_text())
    device_row=next(r for r in matrix["devices"] if r["id"]==device); port=port_for(client,device,case)
    files=out/"files"; shutil.copytree(Path(__file__).parent/"batch10_probe",files,dirs_exist_ok=True)
    (files/"probe_config.py").write_text(f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n")
    image=build_image(SimpleNamespace(base=ROOT/device_row["base"],flash_size=int(device_row["flash_size"],0),
        files_dir=files,mklittlefs=None,preserve_vfs=False,vfs_offset=int(device_row["vfs_offset"],0),
        vfs_size=int(device_row["vfs_size"],0),prog_size=32,out_dir=out))
    fb=image.read_bytes()
    result={"schema_version":1,"date":now(),"validation":"virtual-device validation",
      "scope":"device-local Unit data plane through a visible Device Service session; not hardware",
      "device_id":device,"unit_id":case,"driver_class":DRIVERS[case],
      "driver_flavor":"reference-firmware-frozen-original-unit-driver" if case=="dcssr" else "reference-firmware-generic-driver-or-raw-uart",
      "runtime":"qemu","status":"FAIL","checks":{},"firmware_sha256":sha(fb),
      "base_firmware_sha256":sha((ROOT/device_row["base"]).read_bytes()),
      "probe_sha256":{p.name:sha(p.read_bytes()) for p in files.glob("*.py")},
      "runtime_binary_sha256": None,
      "fixture_source_baseline":QEMU_STATE,"official_port":OFFICIAL[case],
      "runtime_port_substitution":("cores3 PORT.A harness wiring; the official product PinMap connector is "
        +OFFICIAL[case]+" and is not the admitted runtime host port on cores3") if OFFICIAL[case]!="PORT.A" else None,
      "port":{"id":port["id"],"pins":port["pins"]},"initial_inputs":INITIAL[case],
      "qom_samples":[],"serial_markers":{},"observations":{}}
    sid=None
    try:
        art=client.json("artifacts",method="POST",body=fb,headers={"Content-Type":"application/octet-stream","X-Artifact-Name":f"{device}-batch10-{case}.bin"})
        fw=client.json("firmware",method="POST",payload={"device_id":device,"kind":"merged","artifact_id":art["artifact_id"]})
        result["firmware_id"]=fw["firmware_id"]
        spec={"id":"external1","unit_id":case,"port_id":port["id"]}
        if INITIAL[case]: spec["initial"]=INITIAL[case]
        session=client.json("sessions",method="POST",payload={"device_id":device,"firmware_id":fw["firmware_id"],"runtime":"qemu",
            "ttl_seconds":300,"ready_marker":MARKER,"ready_timeout_seconds":120,"units":[spec]})
        sid=session["session_id"]; result["session_id"]=sid
        print(f"{case}: visible session created on {device}/{port['id']}",flush=True)
        serial(client,sid); wait_for(client,sid,lambda t:MARKER in t,150)
        result["checks"]["official_driver_ready"]=True
        live=client.json(f"sessions/{sid}/units")
        result["checks"]["live_controller_state"]=live.get("source")=="live" and bool(live.get("units"))
        attached=(live.get("units") or [{}])[0]
        result["attached_unit"]={k:attached.get(k) for k in ("id","unit_id","available","source")}
        end={"dcssr":"I2C_DCSSR_END","puzzle":"GPIO_PUZZLE_END","dof6":"I2C_IMU_END","dof9":"I2C_IMU_END",
             "dof10":"I2C_IMU_END","asr":"UART_ASR_END"}[case]
        wait_for(client,sid,lambda t:end in t,120); text=serial(client,sid)
        result["serial_markers"][case]=text[-1200:]
        if case=="dcssr":
            final,samples=wait_props(client,sid,lambda p: int(p.get("relay-transitions",0))>=3,label="dcssr")
            result["qom_samples"].extend(samples)
            on1=last(r"I2C_DCSSR_ON (\d)",text); off=last(r"I2C_DCSSR_OFF (\d)",text); on2=last(r"I2C_DCSSR_ON2 (\d)",text)
            fw=last(r"I2C_DCSSR_FW (\d+)",text)
            result["observations"]["dcssr"]={"guest_on_off_on":[on1,off,on2],"guest_fw":fw,
              "qom":{k:final.get(k) for k in ("relay-level","relay-transitions","led-rgb","fw-version","i2c-address")},
              "boundary":"Official DCSSRUnit/ACSSR I2C 0x50 register subset; Modbus/RS485 mode, SSR 10A/DC24-220V/isolation/switching-life/thermal NOT RUN; 0x50 conflicts with ACSSR."}
            result["checks"]["guest_relay_cycle"]=(on1,off,on2)==("1","0","1")
            result["checks"]["guest_firmware"]=fw=="1"
            result["checks"]["qom_relay_on"]=final.get("relay-level") is True
            result["checks"]["qom_transitions"]=int(final.get("relay-transitions",0))>=3
            result["checks"]["qom_rgb"]=final.get("led-rgb")==0x112233
            result["checks"]["qom_i2c_address"]=final.get("i2c-address")==0x50
        elif case=="puzzle":
            final,samples=wait_props(client,sid,lambda p: len(p.get("led-rgb") or [])==64 and (p.get("led-rgb") or [0])[0]==0x112233,label="puzzle")
            result["qom_samples"].extend(samples); led=final.get("led-rgb") or []
            result["observations"]["puzzle"]={"driver_gap":"public UIFlow2 has no unit/puzzle.py; probe uses generic RGBUnit/SK6812 64-LED path.",
              "qom":{k:final.get(k) for k in ("led-rgb","led-frames","incomplete-frames","output-transitions")},
              "boundary":"8x8 WS2812E matrix via generic SK6812 RMT capture; WS2812E-vs-C timing/order, optics/thermal/power and cascade IN/OUT direction NOT RUN; official PORT.B substituted by cores3 PORT.A harness."}
            result["checks"]["generic_sk6812_driver_used"]="GPIO_PUZZLE_DRIVER generic-SK6812-64" in text
            result["checks"]["guest_frame_written"]="GPIO_PUZZLE_WRITTEN" in text
            result["checks"]["qom_64_leds_match"]=led==[0x112233]*64
            result["checks"]["qom_led_frames"]=int(final.get("led-frames",0))>=1
            result["checks"]["no_incomplete_frames"]=int(final.get("incomplete-frames",0))==0
        elif case in ("dof6","dof9","dof10"):
            final,samples=wait_props(client,sid,lambda p: int(p.get("transactions",0))>0 and p.get("whoami")==0x24,label=case)
            result["qom_samples"].extend(samples)
            accel=last(r"I2C_IMU_ACCEL \(([^)]*)\)",text); gyro=last(r"I2C_IMU_GYRO \(([^)]*)\)",text)
            temp=last(r"I2C_IMU_TEMP (-?[\d.]+)",text); blocked=last(r"I2C_IMU_BLOCKED (.*)",text)
            result["observations"][case]={"guest_accel":accel,"guest_gyro":gyro,"guest_temp":temp,
              "blocked_sensors":blocked,
              "qom":{k:final.get(k) for k in ("acceleration-x","acceleration-y","acceleration-z",
                "gyroscope-x","gyroscope-y","gyroscope-z","temperature-c","whoami","transactions")},
              "boundary":"Only the BMI270 0x68 fixture subset is modeled/asserted; BMM350 0x14 and SPA06 0x76 have no driver/register table and are NOT modeled or faked; real motion/range/calibration physics NOT RUN. The generic BMI270 driver uses its own 4g/2000dps scale factors (guest accel=fixture*0.25, guest gyro=fixture*(16.4/16.384), guest temp=fixture-2 due to the driver 23C offset); these are deterministic fixture readbacks, not physical units."}
            av=[round(float(x),5) for x in accel.split(", ")] if accel else None
            gv=[round(float(x),5) for x in gyro.split(", ")] if gyro else None
            result["checks"]["guest_accel_fixture"]=av is not None and all(abs(a-b)<0.001 for a,b in zip(av,[0.125,-0.0625,0.03125]))
            result["checks"]["guest_gyro_fixture"]=gv is not None and all(abs(a-b)<0.01 for a,b in zip(gv,[100.09765,-50.048824,25.024412]))
            result["checks"]["guest_temp_observation"]=temp is not None and abs(float(temp)-25.0)<=0.01
            result["checks"]["qom_accel_fixture"]=abs(float(final.get("acceleration-x",0))-ACCEL[0])<0.01 and abs(float(final.get("acceleration-y",0))-ACCEL[1])<0.01
            result["checks"]["qom_gyro_fixture"]=abs(float(final.get("gyroscope-z",0))-GYRO[2])<0.01
            result["checks"]["qom_temp_fixture"]=abs(float(final.get("temperature-c",0))-TEMP)<0.01
            result["checks"]["qom_whoami"]=final.get("whoami")==0x24
            result["checks"]["blocked_sensors_recorded"]=(blocked==("bmm350" if case=="dof9" else ("bmm350,spa06" if case=="dof10" else "")))
        elif case=="asr":
            final,samples=wait_props(client,sid,lambda p: int(p.get("frames-sent",0))>=1,label="asr")
            result["qom_samples"].extend(samples); tx=final.get("tx-hex") or ""
            gtx=last(r"UART_ASR_TX ([0-9a-f]+)",text); grx=last(r"UART_ASR_RX ([0-9a-f]*)",text)
            result["observations"]["asr"]={"guest_tx":gtx,"guest_rx":grx,
              "qom":{k:final.get(k) for k in ("responses-hex","tx-hex","frames-sent","frames-injected","command-id")},
              "boundary":"No public Unit ASR driver; raw UART 115200 AA55 <id> 55AA byte frame + fixture reply only. Speech recognition/AEC/microphone/speaker acoustics NOT RUN; PORT.C substituted by cores3 PORT.A harness."}
            result["checks"]["guest_tx_frame"]=gtx=="aa554555aa"
            result["checks"]["guest_rx_fixture"]=bool(grx and grx.lower().startswith("aa55"))
            result["checks"]["qom_command_id"]=final.get("command-id")==0x45
            result["checks"]["qom_tx_bytes"]= "aa554555aa" in tx
            result["checks"]["frames_counted"]=int(final.get("frames-sent",0))>=1 and int(final.get("frames-injected",0))>=1
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
                    required={"manifest.json","serial.log","units/runtime.json","units/state.json","units/contract.json"}
                    result["checks"]["evidence_complete"]=required.issubset(z.namelist())
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
        result["raw_evidence_note"]=("Raw execution artifacts (evidence.zip, frame.png, serial.txt, probe files) stay in local ignored "
            ".work; only concise reports, hashes and reproduction commands are committed.")
        client.finalize_result(result)
        (out/"result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(f"{case}: {result['status']}"+(f" ({result['error']})" if result.get("error") else ""),flush=True)
    return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--api-url",default="http://127.0.0.1:8799")
    ap.add_argument("--case",choices=CASES,required=True); ap.add_argument("--out-dir",type=Path,required=True)
    args=ap.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=True)
    result=run_case(Client(args.api_url),args,args.case)
    raise SystemExit(0 if result["status"]=="PASS" else 1)
if __name__=="__main__": main()
