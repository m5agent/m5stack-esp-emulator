#!/usr/bin/env python3
"""Guest/Device Service evidence for batch-11 Units with existing models."""
from __future__ import annotations
import argparse, hashlib, io, json, re, shutil, sys, time, zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent)); sys.path.insert(0,str(ROOT/"tests/uiflow2"))
from run_service_cases import Client, wait_for  # noqa: E402
from run_profile_ui_test import build_image  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402
MARKER="BATCH11_PROBE_READY"
QEMU_STATE="canonical 75f1d24 + canonical chain 35 layers (0120-0154) + 0155 if any batch11 evidence fix"
CASES=("glass","lorawan-as923","lorawan-eu868","rf433t","rf433r","audioplayer","fingerprint2")
OFFICIAL={"glass":"PORT.A","lorawan-as923":"PORT.C","lorawan-eu868":"PORT.C","rf433t":"PORT.B","rf433r":"PORT.B","audioplayer":"PORT.C","fingerprint2":"PORT.C"}
DRIVERS={"glass":"GlassUnit (unit/glass.py, M5.addDisplay)","lorawan-as923":"LoRaWANUnit (ASR650x wrapper)","lorawan-eu868":"LoRaWANUnit (ASR650x wrapper)","rf433t":"machine.Pin-OUT driver-gap","rf433r":"machine.Pin-IN driver-gap","audioplayer":"raw UART 9600 driver-gap","fingerprint2":"raw UART 115200 driver-gap"}
OK="4f4b0d0a"
INITIAL={"glass":{},"lorawan-as923":{"responses-hex":";".join([OK,OK,"4f4b2b53454e543a0d0a4f4b0d0a"])},
 "lorawan-eu868":{"responses-hex":";".join([OK,OK,"4f4b2b53454e543a0d0a4f4b0d0a"])},
 "rf433t":{},"rf433r":{"input-level":True},"audioplayer":{"responses-hex":OK},"fingerprint2":{"responses-hex":"ef0107"}}
CW2="41542b43574f524b4d4f44453d320d0a"; CW1="41542b43574f524b4d4f44453d310d0a"; DTRX="41542b445452583d"
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
    port=port_for(client,device,case); files=out/"files"; shutil.copytree(Path(__file__).parent/"batch11_probe",files,dirs_exist_ok=True)
    (files/"probe_config.py").write_text(f"CASE = {case!r}\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = {device!r}\n")
    image=build_image(SimpleNamespace(base=ROOT/row["base"],flash_size=int(row["flash_size"],0),files_dir=files,mklittlefs=None,preserve_vfs=False,vfs_offset=int(row["vfs_offset"],0),vfs_size=int(row["vfs_size"],0),prog_size=32,out_dir=out))
    fb=image.read_bytes(); result={"schema_version":1,"date":now(),"validation":"virtual-device validation",
      "scope":"device-local Unit data plane through a visible Device Service session; not hardware","device_id":device,"unit_id":case,
      "driver_class":DRIVERS[case],"driver_flavor":"reference-firmware-frozen-original-unit-driver" if case in ("glass","lorawan-as923","lorawan-eu868") else "reference-firmware-raw-gpio-uart-driver-gap",
      "runtime":"qemu","status":"FAIL","checks":{},"firmware_sha256":sha(fb),"base_firmware_sha256":sha((ROOT/row["base"]).read_bytes()),
      "probe_sha256":{p.name:sha(p.read_bytes()) for p in files.glob("*.py")},"runtime_binary_sha256": None,
      "fixture_source_baseline":QEMU_STATE,"official_port":OFFICIAL[case],
      "runtime_port_substitution":("cores3 PORT.A harness wiring; official product PinMap is "+OFFICIAL[case]) if OFFICIAL[case]!="PORT.A" else None,
      "port":{"id":port["id"],"pins":port["pins"]},"initial_inputs":INITIAL[case],"qom_samples":[],"serial_markers":{},"observations":{}}
    sid=None
    try:
        art=client.json("artifacts",method="POST",body=fb,headers={"Content-Type":"application/octet-stream","X-Artifact-Name":f"{device}-batch11-{case}.bin"})
        fw=client.json("firmware",method="POST",payload={"device_id":device,"kind":"merged","artifact_id":art["artifact_id"]})
        spec={"id":"external1","unit_id":case,"port_id":port["id"]}
        if INITIAL[case]: spec["initial"]=INITIAL[case]
        session=client.json("sessions",method="POST",payload={"device_id":device,"firmware_id":fw["firmware_id"],"runtime":"qemu","ttl_seconds":300,"ready_marker":MARKER,"ready_timeout_seconds":120,"units":[spec]})
        sid=session["session_id"]; result["session_id"]=sid
        print(f"{case}: visible session created on {device}/{port['id']}",flush=True)
        wait_for(client,sid,lambda t:MARKER in t,150)
        result["checks"]["driver_ready"]=True
        live=client.json(f"sessions/{sid}/units"); result["checks"]["live_controller_state"]=live.get("source")=="live" and bool(live.get("units"))
        result["attached_unit"]={k:(live.get("units") or [{}])[0].get(k) for k in ("id","unit_id","available","source")}
        if case=="rf433r":
            time.sleep(0.6); client.json(f"sessions/{sid}/unit-input",method="POST",payload={"id":"external1","values":{"input-level":False}})
            result["observations"]["injected_level"]=False
        end={"glass":"GLASS_END","lorawan-as923":"LORAWAN_END","lorawan-eu868":"LORAWAN_END","rf433t":"RF433T_END","rf433r":"RF433R_END","audioplayer":"AUDIO_END","fingerprint2":"FINGERPRINT_END"}[case]
        wait_for(client,sid,lambda t:end in t,120); text=serial(client,sid); result["serial_markers"][case]=text[-1200:]
        if case=="glass":
            final,samples=wait_props(client,sid,lambda p:int(p.get("commands",0))>0 and int(p.get("data-bytes",0))>0,label="glass")
            result["qom_samples"].extend(samples)
            result["observations"]["glass"]={"qom":{k:final.get(k) for k in ("command-hex","panel-framebuffer","commands","data-bytes","i2c-address")},
              "boundary":"Official GlassUnit/M5Unified display composition; SSD1309 command/GDDRAM path only; transparent OLED optics, 0x3D conflict with lcd/oled/mini-oled/glass2, and internal-firmware buttons/buzzer are NOT RUN (static fixtures only)."}
            result["checks"]["guest_display_init"] = "GLASS_DRAWN" in text
            result["checks"]["qom_commands"] = int(final.get("commands",0))>0
            result["checks"]["qom_data_bytes"] = int(final.get("data-bytes",0))>0
            result["checks"]["qom_framebuffer_crc"] = bool(re.fullmatch(r"[0-9a-f]{8}",final.get("panel-framebuffer") or ""))
            result["checks"]["qom_command_hex"] = bool(final.get("command-hex"))
            result["checks"]["qom_i2c_address"] = final.get("i2c-address")==0x3D
        elif case in ("lorawan-as923","lorawan-eu868"):
            final,samples=wait_props(client,sid,lambda p:int(p.get("frames-sent",0))>=2,label=case)
            result["qom_samples"].extend(samples); tx=final.get("tx-hex") or ""
            result["observations"][case]={"qom":{k:final.get(k) for k in ("responses-hex","tx-hex","frames-sent","frames-injected","join-status")},
              "boundary":"Official LoRaWANUnit/ASR650x wrapper byte layer only; product STM32WLE5/RAK3172 mismatch unresolved; OTAA/ABP/Join/RF/regulatory NOT RUN; guest pre-init workaround recorded; PORT.C substituted by cores3 PORT.A harness."}
            result["checks"]["guest_mode_sent"]="LORAWAN_MODE_SENT" in text
            result["checks"]["guest_send_called"]="LORAWAN_SENT" in text
            result["checks"]["qom_workmode2"]=CW2 in tx
            result["checks"]["qom_workmode1"]=CW1 in tx
            result["checks"]["qom_dtrx"]=DTRX in tx
            result["checks"]["qom_frames"]=int(final.get("frames-sent",0))>=2 and int(final.get("frames-injected",0))>=1
        elif case=="rf433t":
            final,samples=wait_props(client,sid,lambda p:int(p.get("bit-count",0))>=8,label="rf433t")
            result["qom_samples"].extend(samples)
            result["observations"]["rf433t"]={"qom":{k:final.get(k) for k in ("output-level","edge-count","bit-count","bitstream")},
              "boundary":"No public Unit driver/ASK encoding table; machine.Pin bitbang only; RF 433.92MHz/antenna/10dBm/range NOT RUN; PORT.B substituted by cores3 PORT.A harness."}
            result["checks"]["driver_gap_recorded"]="machine.Pin-OUT driver-gap" in text
            result["checks"]["guest_bitbang"]="RF433T_BITS 10101010" in text
            result["checks"]["qom_bits"]=int(final.get("bit-count",0))>=8
            result["checks"]["qom_edges"]=int(final.get("edge-count",0))>=8
            result["checks"]["qom_bitstream"]="10101010" in (final.get("bitstream") or "")
        elif case=="rf433r":
            final,samples=wait_props(client,sid,lambda p:int(p.get("samples",0))>=1,label="rf433r")
            result["qom_samples"].extend(samples)
            levels=[int(x) for x in re.findall(r"RF433R_LEVEL (\d)",text)]
            result["observations"]["rf433r"]={"guest_levels":levels,"qom":{k:final.get(k) for k in ("input-level","sample-rate","samples")},
              "boundary":"No public Unit driver/decoder; machine.Pin input sampling only; ASK demodulation/-109dBm/antenna/range NOT RUN; PORT.B substituted by cores3 PORT.A harness."}
            result["checks"]["driver_gap_recorded"]="machine.Pin-IN driver-gap" in text
            result["checks"]["guest_saw_high"]=1 in levels
            result["checks"]["guest_saw_low"]=0 in levels
            result["checks"]["qom_samples"]=int(final.get("samples",0))>=1
            result["checks"]["qom_input_low"]=final.get("input-level") is False
        elif case=="audioplayer":
            final,samples=wait_props(client,sid,lambda p:int(p.get("frames-sent",0))>=1,label="audioplayer")
            result["qom_samples"].extend(samples); tx=final.get("tx-hex") or ""
            result["observations"]["audioplayer"]={"qom":{k:final.get(k) for k in ("responses-hex","tx-hex","frames-sent","frames-injected")},
              "boundary":"No public Unit AudioPlayer driver/readable N9301 command table; raw UART 9600 byte layer only; MP3/WAV/microSD/3.5mm/audio NOT RUN; PORT.C substituted by cores3 PORT.A harness."}
            result["checks"]["driver_gap_recorded"]="raw-UART driver-gap" in text
            result["checks"]["guest_tx_frame"]="AUDIO_TX 7e03010203" in text
            result["checks"]["guest_rx_fixture"]="AUDIO_RX 4f4b0d0a" in text
            result["checks"]["qom_tx_bytes"]="7e03010203" in tx
            result["checks"]["qom_frames"]=int(final.get("frames-sent",0))>=1 and int(final.get("frames-injected",0))>=1
        elif case=="fingerprint2":
            final,samples=wait_props(client,sid,lambda p:int(p.get("frames-sent",0))>=1,label="fingerprint2")
            result["qom_samples"].extend(samples); tx=final.get("tx-hex") or ""
            result["observations"]["fingerprint2"]={"qom":{k:final.get(k) for k in ("responses-hex","tx-hex","frames-sent","frames-injected")},
              "boundary":"No public Unit driver/A-K323CP frame table; raw UART 115200 byte layer only; fingerprint capture/match/100 users/RGB ring/security NOT RUN; PORT.C substituted by cores3 PORT.A harness."}
            result["checks"]["driver_gap_recorded"]="raw-UART driver-gap" in text
            result["checks"]["guest_tx_frame"]="FINGERPRINT_TX ef01ffffffff010003010005" in text
            result["checks"]["guest_rx_fixture"]="FINGERPRINT_RX ef0107" in text
            result["checks"]["qom_tx_bytes"]="ef01ffffffff010003010005" in tx
            result["checks"]["qom_frames"]=int(final.get("frames-sent",0))>=1 and int(final.get("frames-injected",0))>=1
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
    ap=argparse.ArgumentParser(); ap.add_argument("--api-url",default="http://127.0.0.1:8809"); ap.add_argument("--case",choices=CASES,required=True); ap.add_argument("--out-dir",type=Path,required=True)
    args=ap.parse_args(); args.out_dir.mkdir(parents=True,exist_ok=True)
    r=run_case(Client(args.api_url),args,args.case); raise SystemExit(0 if r["status"]=="PASS" else 1)
if __name__=="__main__": main()
