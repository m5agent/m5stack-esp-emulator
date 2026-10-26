from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.parse
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tests/units"))
sys.path.insert(0, str(ROOT / "platform/tools"))
from run_control_cases import build_control_image
from run_sensor_cases import verify_image_files
from run_host_cases import reference_layout
from run_service_cases import Client, png_metrics
from web_ui_bridge import WebUIBridge


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--audio-script", type=Path)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    assert re.fullmatch("[a-f0-9]{64}", args.expected_runtime_sha256)
    out = args.out.resolve()
    assert out.is_relative_to(HERE) and not out.exists()
    out.mkdir(parents=True)
    device = next(row for row in json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_bytes())["devices"] if row["id"] == "cores3")
    base = ROOT / device["base"]
    assert digest(base) == "1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264"
    layout = reference_layout(base, int(device["flash_size"], 0))
    image = build_control_image(SimpleNamespace(base=base, flash_size=int(device["flash_size"], 0),
        files_dir=HERE / "guest_audio", mklittlefs=None, preserve_vfs=False, vfs_offset=layout["offset"],
        vfs_size=layout["size"], prog_size=32, out_dir=out))
    effective = {**device, "vfs_offset": hex(layout["offset"]), "vfs_size": hex(layout["size"])}
    packaged = verify_image_files(image, HERE / "guest_audio", effective)
    sources = [Path(__file__).resolve(), *sorted((HERE / "guest_audio").glob("*.py")),
               ROOT / "tests/units/run_control_cases.py", ROOT / "tests/units/run_host_cases.py",
               ROOT / "tests/units/run_sensor_cases.py", ROOT / "tests/units/run_service_cases.py",
               ROOT / "tests/units/web_ui_bridge.py",
               ROOT / ".work/unit-runtime-source-ledc-readback/qemu/hw/misc/esp32_ledc.c"]
    if args.audio_script:
        sources += [args.audio_script.resolve(), ROOT / "platform/web/unit-audio.js", ROOT / "platform/web/unit-panel.js", ROOT / "platform/web/unit-panel.css"]
    frozen = {path.relative_to(ROOT).as_posix(): digest(path) for path in sources}
    write(out / "source-before.json", frozen)
    for path in sources:
        target = out / "source-snapshot" / (path.relative_to(ROOT).as_posix() + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    report = {"schema_version": 1, "category": "custom-guest-ledc-audio-20s-prelude", "status": "PREPARED_NOT_EXECUTED",
        "device_id": "cores3", "unit_id": "buzzer", "runtime": "qemu", "firmware_flavor": "custom-guest-ledc-audio-20s-prelude-v1",
        "firmware_sha256": digest(image), "base_firmware_sha256": digest(base), "packaged_python_sha256": packaged,
        "source_sha256": frozen, "expected_runtime_sha256": args.expected_runtime_sha256,
        "scope": "Custom audio diagnostic with explicit 20s zero-duty preparation window; real PWM and QOM drive browser synthesis. Different firmware from no-prelude getter A/B; no original Buzzer.once or physical acoustics claim.",
        "hardware_execution": "NOT RUN"}
    if not args.execute:
        write(out / "report.json", report)
        print("PREPARED_NOT_EXECUTED", flush=True)
        return 0
    os.environ["M5_UNIT_EXPECT_RUNTIME_SHA256"] = args.expected_runtime_sha256
    client = Client("http://127.0.0.1:8787")
    assert client.json("health")["capacity"]["active_sessions"] == 0
    sid = None
    observations = []
    audio_process = audio_log = None
    audio_out = ROOT / ".work/unit-audio-live-20261026" / ("run-" + out.name)
    report["status"] = "FAIL"
    try:
        artifact = client.json("artifacts", method="POST", body=image.read_bytes(), headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": "cores3-ledc-mmio.bin"})
        firmware = client.json("firmware", method="POST", payload={"device_id": "cores3", "kind": "merged", "artifact_id": artifact["artifact_id"]})
        session = client.json("sessions", method="POST", payload={"device_id": "cores3", "runtime": "qemu", "firmware_id": firmware["firmware_id"],
            "ttl_seconds": 900, "ready_marker": "LEDC_DIAG_READY", "ready_timeout_seconds": 180,
            "units": [{"id": "external1", "unit_id": "buzzer", "port_id": "port-a"}]})
        sid = report["session_id"] = session["session_id"]
        print("LIVE_SESSION", sid, flush=True)
        if args.audio_script:
            audio_log = (out / "audio.log").open("w")
            audio_process = subprocess.Popen(["node", str(args.audio_script.resolve()),
                "--session-id", sid, "--expected-firmware-sha256", digest(image),
                "--expected-runtime-sha256", args.expected_runtime_sha256,
                "--expected-frequency", "2000", "--expected-duty-sequence", "0,25,50,75,100,0",
                "--duty-tolerance", "0.1", "--out", str(audio_out), "--timeout-seconds", "180"],
                cwd=ROOT, stdout=audio_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 180
        proof = None
        while time.monotonic() < deadline:
            current = client.json(f"sessions/{sid}")
            if current["state"] == "running":
                if proof is None:
                    proof = WebUIBridge.runtime_provenance(SimpleNamespace(url=client.url, output=out), current, lambda: client.json(f"sessions/{sid}"))
                    report["runtime_provenance"] = proof
                before = client.json(f"sessions/{sid}/serial?limit=262144")["data"]
                body = client.raw(f"sessions/{sid}/units")
                after = client.json(f"sessions/{sid}/serial?limit=262144")["data"]
                phases_before = re.findall(r"(?m)^LEDC_DIAG_PHASE (\d+) (\w+) (\d+)\r?$", before)
                phases_after = re.findall(r"(?m)^LEDC_DIAG_PHASE (\d+) (\w+) (\d+)\r?$", after)
                index = len(observations)
                body_path = out / f"units-{index:03d}.json"
                body_path.write_bytes(body)
                observations.append({"at": datetime.now(timezone.utc).isoformat(), "serial_before_length": len(before),
                    "serial_after_length": len(after), "serial_before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                    "serial_after_sha256": hashlib.sha256(after.encode()).hexdigest(), "serial_prefix_preserved": after.startswith(before),
                    "phase_before": phases_before[-1] if phases_before else None, "phase_after": phases_after[-1] if phases_after else None,
                    "body": body_path.name, "body_sha256": digest(body_path)})
                assert "LEDC_DIAG_FAIL" not in after and "Guru Meditation" not in after
                if "LEDC_DIAG_DONE" in after:
                    break
            elif current["state"] in {"failed", "stopped"}:
                raise RuntimeError("session ended before diagnostic completion")
            time.sleep(0.5)
        else:
            raise RuntimeError("diagnostic deadline expired")
        assert proof and proof["status"] == "VERIFIED"
        if audio_process:
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                if "READY_FOR_ROOT_STOP" in (out / "audio.log").read_text(): break
                assert audio_process.poll() is None, "audio observer terminated before ready"
                time.sleep(0.25)
            else: raise RuntimeError("audio observer did not verify six phases")
        serial = client.json(f"sessions/{sid}/serial?limit=262144")["data"]
        (out / "serial.txt").write_bytes(serial.encode())
        frame = client.raw(f"sessions/{sid}/frame.png")
        assert png_metrics(frame)["unique_colors"] > 1
        (out / "frame.png").write_bytes(frame)
        assert all(digest(ROOT / name) == value for name, value in frozen.items())
        report["status"] = "OBSERVATIONS_COLLECTED"
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if sid:
            try:
                (out / "evidence.zip").write_bytes(client.raw(f"sessions/{sid}/evidence"))
            except Exception as error:
                report["evidence_error"] = str(error)
            try:
                client.json(f"sessions/{sid}?purge=0", method="DELETE")
                body = client.raw(f"sessions/{sid}"); (out / "history.json").write_bytes(body)
                history = json.loads(body)
                assert history["state"] == "stopped" and history["flash_retained"] is False
                (out / "history-frame.png").write_bytes(client.raw(f"sessions/{sid}/frame.png"))
                assert subprocess.run(["ps", "-p", str(report["runtime_provenance"]["observed_pid"]), "-o", "pid="], capture_output=True).returncode != 0
            except Exception as error:
                report["cleanup_error"] = str(error)
        if audio_process:
            try:
                code = audio_process.wait(timeout=30)
                if audio_log: audio_log.close()
                report["audio_observer_exit_code"] = code
                assert code == 0, "audio observer failed"
                import shutil
                shutil.copytree(audio_out, out / "audio")
                report["audio_observer_receipts"] = [p.relative_to(out).as_posix() for p in (out / "audio").rglob("*.json")]
            except Exception as error:
                if audio_process.poll() is None:
                    audio_process.terminate()
                    audio_process.wait(timeout=10)
                report["audio_error"] = str(error)
        write(out / "observations.json", observations)
        report["artifact_sha256"] = {p.relative_to(out).as_posix(): digest(p) for p in out.rglob("*") if p.is_file() and p.suffix != ".bin"}
        if any(report.get(key) for key in ("error", "evidence_error", "cleanup_error", "audio_error")):
            report["status"] = "FAIL"
        write(out / "report.json", report)
    print(report["status"], flush=True)
    return 0 if report["status"] == "OBSERVATIONS_COLLECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
