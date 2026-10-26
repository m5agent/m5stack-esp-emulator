#!/usr/bin/env python3
"""Exercise real Button release recovery in one visible Device Service lease."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlparse
import zipfile

from check_batch_evidence import Checker
from run_service_cases import Client, ROOT, build_image, png_metrics, wait_for
from web_ui_bridge import _process_executable


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8787")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--expected-runtime-sha256", required=True)
    args = parser.parse_args()
    if urlparse(args.api_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("direct runtime verification requires a loopback Device Service")
    if os.environ.get("M5_UNIT_WEB_BRIDGE") == "1":
        raise SystemExit("This runner owns its browser; unset M5_UNIT_WEB_BRIDGE")
    output = args.out_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    client = Client(args.api_url)
    if client.json("health")["capacity"]["active_sessions"]:
        raise SystemExit("Run only while the Device Service has no active sessions")
    files = (
        "platform/web/sessions.js", "platform/web/sessions.css",
        "platform/web/unit-panel.js", "platform/web/unit-panel.css",
        "platform/web/unit-visual-mappings.js", "platform/web/model-shell.js",
        "platform/web/unit-annotations.js", "platform/web/unit-assembly-layout.js",
        "tests/uiflow2/lib/rtc_probe.py",
        "platform/web/device-shell-factory.js", "platform/web/sessions.html",
        "platform/web/vendor/m5stack-models/src/devices/cores3/index.js",
        "platform/tests/test_live_unit_recovery.mjs", "tests/units/run_web_recovery.py",
        "tests/units/run_service_cases.py", "tests/units/web_ui_bridge.py",
        "tests/units/check_batch_evidence.py", "tests/uiflow2/run_profile_ui_test.py",
        "platform/tools/firmware_analysis.py", "platform/tools/user_firmware_matrix.py",
        "platform/tools/serve.py", "platform/tools/device_service.py",
        "platform/tools/unit_runtime.py", "platform/units/catalog.json",
        "platform/units/runtime-profiles.json", "platform/units/host-ports.json",
    )
    frozen = {}
    for name in files:
        data = (ROOT / name).read_bytes()
        frozen[name] = digest(data)
        target = output / "tool-sources" / (name + ".txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    write_json(output / "source-freeze.json", frozen)
    result = {"schema_version": 1, "status": "FAIL", "category": "virtual-device-web-recovery",
              "device_id": "cores3", "unit_id": "button", "runtime": "qemu",
              "hardware_execution": "NOT RUN", "checks": {}, "source_sha256": frozen}
    session_id = None
    try:
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        device = next(row for row in matrix["devices"] if row["id"] == "cores3")
        inventory = client.json("units?device_id=cores3")
        port = next(row for row in inventory["hosts"][0]["ports"] if row.get("visual_port") == "grove")
        probe = output / "files"
        shutil.copytree(Path(__file__).parent / "probe", probe)
        (probe / "probe_config.py").write_text(
            f"CASE = 'button'\nWHITE = {port['pins']['white']}\nYELLOW = {port['pins']['yellow']}\nDEVICE_ID = 'cores3'\n",
            encoding="utf-8")
        image = build_image(SimpleNamespace(
            base=ROOT / device["base"], flash_size=int(device["flash_size"], 0),
            files_dir=probe, mklittlefs=None, preserve_vfs=False,
            vfs_offset=int(device["vfs_offset"], 0), vfs_size=int(device["vfs_size"], 0),
            prog_size=32, out_dir=output))
        data = image.read_bytes()
        result["firmware_sha256"] = digest(data)
        result["probe_sha256"] = {p.name: digest(p.read_bytes()) for p in probe.glob("*.py")}
        artifact = client.json("artifacts", method="POST", body=data,
                               headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": "cores3-unit-recovery.bin"})
        firmware = client.json("firmware", method="POST", payload={
            "device_id": "cores3", "kind": "merged", "artifact_id": artifact["artifact_id"]})
        session = client.json("sessions", method="POST", payload={
            "device_id": "cores3", "firmware_id": firmware["firmware_id"], "runtime": "qemu",
            "ttl_seconds": 420, "ready_marker": "UNIT_PROBE_READY", "ready_timeout_seconds": 120,
            "units": [{"id": "external1", "unit_id": "button", "port_id": port["id"]}]})
        session_id = session["session_id"]
        result["session_id"] = session_id
        print("Visible recovery session created", flush=True)
        wait_for(client, session_id, lambda text: "UNIT_PROBE_READY" in text, 150)
        session = client.json(f"sessions/{session_id}")
        executable, method = _process_executable(session["pid"])
        runtime_sha = digest(executable.read_bytes())
        confirmed = client.json(f"sessions/{session_id}")
        assert runtime_sha == args.expected_runtime_sha256
        assert all(confirmed.get(key) == session.get(key) for key in ("pid", "firmware_sha256", "worker"))
        assert confirmed["state"] == "running"
        result["attachments"] = session["units"]
        result["runtime_provenance"] = {"kind": "direct-pid", "status": "VERIFIED",
            "session_id": session_id, "firmware_sha256": session["firmware_sha256"],
            "worker_id": session.get("worker", {}).get("worker_id"),
            "observed_pid": session["pid"], "runtime_binary_sha256": runtime_sha,
            "worker_generation": session.get("worker", {}).get("generation"),
            "method": method + "; session PID, firmware and worker identity confirmed after hashing"}
        write_json(output / "session-for-browser.json", session)
        node = shutil.which("node")
        assert node, "Node.js required"
        with (output / "browser.stdout").open("w") as stdout, (output / "browser.stderr").open("w") as stderr:
            completed = subprocess.run([node, str(ROOT / "platform/tests/test_live_unit_recovery.mjs"),
                args.api_url, str(output / "session-for-browser.json"), str(output / "browser")],
                cwd=ROOT, stdout=stdout, stderr=stderr, check=False, timeout=180)
        browser = json.loads((output / "browser/report.json").read_text())
        result["checks"]["real_browser_recovery"] = completed.returncode == 0 and browser["status"] == "PASS"
        result["checks"]["source_freeze_matches_browser"] = all(frozen.get(k) == v for k, v in browser["source_sha256"].items())
        result["browser_report"] = "browser/report.json"
        final_session = client.json(f"sessions/{session_id}")
        result["checks"]["runtime_identity_unchanged_after_browser"] = final_session["state"] == "running" and all(
            final_session.get(key) == session.get(key) for key in ("pid", "firmware_sha256", "worker"))
        result["checks"]["runtime_binary_unchanged_after_browser"] = digest(executable.read_bytes()) == runtime_sha
        frame = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(frame)
        result["frame_metrics"] = png_metrics(frame)
        result["checks"]["nonempty_frame"] = result["frame_metrics"]["unique_colors"] > 1
        result["checks"]["source_unchanged_during_run"] = all(digest((ROOT / k).read_bytes()) == v for k, v in frozen.items())
    except Exception as error:
        result["error"] = str(error).replace(str(ROOT), "<workspace>")
    finally:
        if session_id:
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence_sha256"] = digest(bundle)
                manifest, member_count = Checker().zip_manifest(output / "evidence.zip", result, "button")
                assert manifest["session"]["pid"] == result["runtime_provenance"]["observed_pid"]
                assert manifest["session"]["worker"].get("generation") == result["runtime_provenance"]["worker_generation"]
                assert manifest["session"]["worker"].get("worker_id") == result["runtime_provenance"]["worker_id"]
                result["evidence_members_verified"] = member_count
                with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
                    serial_bytes = archive.read("serial.log")
                    serial = serial_bytes.decode("utf-8")
                    assert "UNIT_PROBE_READY button" in serial and "UNIT_BUTTON 0" in serial and "UNIT_BUTTON 1" in serial
                    assert not any(text in serial for text in ("Traceback (most recent call last)", "Guru Meditation", "Rebooting..."))
                    (output / "serial.txt").write_bytes(serial_bytes)
                result["checks"]["evidence_complete_and_identity_bound"] = True
            except Exception as error:
                result["evidence_error"] = str(error).replace(str(ROOT), "<workspace>")
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", method="DELETE")
                history = client.json(f"sessions/{session_id}")
                result["checks"]["stopped_with_history"] = stopped["state"] == history["state"] == "stopped"
                result["checks"]["flash_released"] = history.get("flash_retained") is False
                result["checks"]["history_identity"] = history["session_id"] == session_id and history["firmware_sha256"] == result["firmware_sha256"]
                result["checks"]["no_active_session"] = client.json("health")["capacity"]["active_sessions"] == 0
            except Exception as error:
                result["stop_error"] = str(error).replace(str(ROOT), "<workspace>")
        result["status"] = "PASS" if result["checks"] and all(result["checks"].values()) and not any(k in result for k in ("error", "evidence_error", "stop_error")) else "FAIL"
        write_json(output / "result.json", result)
    print("Recovery:", result["status"], result.get("error", ""), flush=True)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
