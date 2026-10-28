#!/usr/bin/env python3
"""Independently check guest-produced recorder PCM/WAV against the owned tone.

This consumes retained serial evidence. It never substitutes samples into the
guest or changes a frozen SDK. Diagnostic input/firmware lanes stay diagnostic.
"""
from __future__ import annotations

import argparse
import array
import base64
from collections import Counter
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import wave


def analyze(raw,rate,frequency,expected_seconds=None):
    samples=array.array("h",raw)
    if sys.byteorder!="little":samples.byteswap()
    crossings=[index for index in range(1,len(samples))if samples[index-1]<=0<samples[index]]
    crossing_hz=(rate*(len(crossings)-1)/(crossings[-1]-crossings[0]))if len(crossings)>1 else 0
    power=sum(value*value for value in samples)
    real=sum(value*math.cos(2*math.pi*frequency*index/rate)for index,value in enumerate(samples))
    imag=sum(value*math.sin(2*math.pi*frequency*index/rate)for index,value in enumerate(samples))
    energy=2*(real*real+imag*imag)/(len(samples)*power)if samples and power else 0
    def spectral_power(hz):
        coefficient=2*math.cos(2*math.pi*hz/rate);previous=older=0
        for value in samples:
            current=value+coefficient*previous-older;older=previous;previous=current
        return previous*previous+older*older-coefficient*previous*older
    coarse=max(range(50,min(rate//2,2000),5),key=spectral_power)if power else 0
    measured=max(range(max(1,coarse-5),coarse+6),key=spectral_power)if power else 0
    dbfs=20*math.log10(math.sqrt(power/len(samples))/32768)if samples and power else None
    duration=len(samples)/rate
    duration_ok=expected_seconds is None or abs(duration-expected_seconds)<=.15*expected_seconds
    passed=len(crossings)>=10 and abs(measured-frequency)<5 and energy>.9 and duration_ok
    return {"status":"PASS"if passed else"FAIL","samples":len(samples),"rate_hz":rate,
            "expected_hz":frequency,"measured_hz":measured,"zero_crossing_hz":crossing_hz,"tone_energy_fraction":energy,
            "duration_seconds":duration,"expected_seconds":expected_seconds,"duration_status":"PASS"if duration_ok else"FAIL",
            "rms_dbfs":dbfs,"sha256":hashlib.sha256(raw).hexdigest()}


def verify(directory,frequency,rate):
    serial=(directory/"serial.txt").read_text(errors="replace")
    outputs={}
    for marker,name in (("AUDIO_WRAPPER_PCM","record-into.pcm"),("AUDIO_WRAPPER_WAV","record.wav")):
        match=re.search(r"(?:^|\n)"+marker+r" ([^\r\n]+)",serial)
        if not match:
            outputs[marker]={"status":"NOT_OBSERVED"};continue
        raw=base64.b64decode(match[1],validate=True)
        (directory/name).write_bytes(raw)
        if marker.endswith("WAV"):
            with wave.open(io.BytesIO(raw),"rb")as handle:
                if handle.getnchannels()!=1 or handle.getsampwidth()!=2 or handle.getframerate()!=rate:
                    raise ValueError("recorded WAV format differs from configured mono s16 sample rate")
                samples=handle.readframes(handle.getnframes())
        else:samples=raw
        outputs[marker]=analyze(samples,rate,frequency,expected_seconds=1)
        outputs[marker]["artifact_sha256"]=hashlib.sha256(raw).hexdigest()
    result={"schema_version":1,"validation":"virtual-device validation","hardware_validation":"NOT RUN",
            "serial_sha256":hashlib.sha256((directory/"serial.txt").read_bytes()).hexdigest(),"outputs":outputs}
    oracle_path=directory/"wrapper-waveform-oracle.json"
    oracle_path.write_text(json.dumps(result,indent=2)+"\n")
    report_path=directory/"protocol-results.json";report=json.loads(report_path.read_text())
    execution=json.loads((directory/"report.json").read_text())
    execution_valid=(execution.get("status")=="EXECUTED"and bool(execution.get("evidence_sha256"))
                     and execution.get("cleanup",{}).get("runtime_pid_gone")is True)
    pcm_ok=outputs["AUDIO_WRAPPER_PCM"].get("status")=="PASS"
    wav_ok=outputs["AUDIO_WRAPPER_WAV"].get("status")=="PASS"
    for row in report["cases"]:
        api=row["api"]
        met=(pcm_ok if api in {"audio.Recorder","audio.Recorder.record_into"}else
             wav_ok if api=="audio.Recorder.record"else None)
        if api=="audio.Recorder.rms"and pcm_ok:
            met=abs(row["value"]-outputs["AUDIO_WRAPPER_PCM"]["rms_dbfs"])<2
        if api=="audio.Recorder.volume"and pcm_ok:
            expected=int((outputs["AUDIO_WRAPPER_PCM"]["rms_dbfs"]+96)/96*100)
            met=abs(row["value"]-expected)<=2
        if met is None:continue
        row.setdefault("guest_status",row["status"])
        row["status"]=row["guest_status"]if met else"FAIL"
        row["data_plane_oracle"]="PASS"if met else"FAIL"
        row["evidence_refs"]["waveform_oracle_sha256"]=hashlib.sha256(oracle_path.read_bytes()).hexdigest()
        row["required_evidence_met"]=bool(execution_valid and met and row["status"]=="PASS")
        if met:row.pop("remaining_oracle",None)
        else:row["remaining_oracle"]="Independent owned-tone sample rate, spectrum or requested one-second output duration failed."
    report["counts"]=dict(Counter(row["status"]for row in report["cases"]))
    report["status"]="FAIL"if any(row["status"]in {"FAIL","ERROR","TIMED_OUT"}for row in report["cases"])else report["status"]
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--expected-frequency",type=float,default=440)
    parser.add_argument("--recording-rate",type=int,default=8000)
    args=parser.parse_args()
    print(json.dumps(verify(args.run,args.expected_frequency,args.recording_rate),indent=2))
