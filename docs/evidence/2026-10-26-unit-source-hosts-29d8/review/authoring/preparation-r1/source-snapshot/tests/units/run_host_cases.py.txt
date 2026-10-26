#!/usr/bin/env python3
"""Prepare or validate device-local Unit cases; never expands host admission.

Preparation reads each actual reference partition table and makes no API call.
Execution remains a visible Device Service session and requires the current
service registry to admit the exact host/Unit combination.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import sys
import time
from types import SimpleNamespace
import urllib.parse
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "platform/tools"))
from firmware_analysis import parse_partition_table  # noqa: E402
from run_control_cases import build_control_image  # noqa: E402
from run_io_cases import Observations, require  # noqa: E402
from run_sensor_cases import verify_image_files  # noqa: E402
from run_service_cases import Client, png_metrics  # noqa: E402

PROBE = Path(__file__).parent / "host_probe"
CASES = ("boot-control", "button", "relay", "env-iii")
HOSTS = {
    "atoms3r": {"rotation": 0, "size": [128, 128], "text": [4, 4, 120], "internal_sda": 47, "internal_scl": 0},
    "sticks3": {"rotation": 0, "size": [135, 240], "text": [4, 4, 127], "internal_sda": 47, "internal_scl": 48},
    "stopwatch": {"rotation": 0, "size": [466, 466], "canvas_size": [468, 468], "text": [80, 110, 306], "internal_sda": 47, "internal_scl": 48},
}
FAILURES = ("HOST_PROBE_FAIL", "Traceback (most recent call last)", "Guru Meditation", "Rebooting...")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_layout(base, flash_size):
    raw = base.read_bytes()
    table = parse_partition_table(raw, image_size=flash_size)
    require(len(raw) <= flash_size and table["valid"], "invalid reference image or partition table")
    candidates = [p for p in table["partitions"] if p["label"] == "vfs" and p["type"] == 1 and p["subtype"] == 0x81]
    require(len(candidates) == 1, "reference requires exactly one LittleFS vfs partition")
    vfs = candidates[0]
    start, end = vfs["offset"], vfs["offset"] + vfs["size"]
    require(vfs["size"] > 0 and start % 4096 == 0 and vfs["size"] % 4096 == 0 and end <= flash_size,
            "unaligned or out-of-range VFS")
    require(not any(p is not vfs and start < p["offset"] + p["size"] and p["offset"] < end for p in table["partitions"]),
            "VFS overlaps another partition")
    return {"source": "actual-reference-partition-table", "offset": start, "size": vfs["size"],
            "base_firmware_sha256": digest(base)}


def prepare(args, case):
    output = args.out_dir / args.device / case
    require(not (output / "prepared.json").exists(), "choose a fresh output directory; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    device = next(d for d in json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())["devices"] if d["id"] == args.device)
    profile = {**HOSTS[args.device], "log_tx": 43, "log_rx": 44, "internal_controller": 1, "external_controller": 0}
    profile.setdefault("canvas_size", profile["size"])
    require(device["backend"] == "qemu-esp32s3", "this host probe targets the S3 controller family")
    require(profile["size"] == [int(x) for x in device["expected_size"].split("x")], "profile/matrix display geometry differs")
    host = next(h for h in json.loads((ROOT / "platform/units/host-ports.json").read_text())["hosts"] if h["device_id"] == args.device)
    ports = [p for p in host["ports"] if p.get("visual_port") == "grove" and p.get("wiring_status") == "confirmed" and p.get("physical_presence") == "main-device"]
    require(len(ports) == 1, "host requires one explicitly confirmed main Grove connector")
    port = ports[0]
    base = args.base.resolve() if args.base else ROOT / device["base"]
    layout = reference_layout(base, int(device["flash_size"], 0))
    files = output / "files"
    shutil.copytree(PROBE, files, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    config = {"CASE": case, "DEVICE_ID": args.device, "WHITE": port["pins"]["white"], "YELLOW": port["pins"]["yellow"],
              "ROTATION": profile["rotation"], "FRAME_WIDTH": profile["size"][0], "FRAME_HEIGHT": profile["size"][1],
              "CANVAS_WIDTH": profile["canvas_size"][0], "CANVAS_HEIGHT": profile["canvas_size"][1],
              "TEXT_X": profile["text"][0], "TEXT_Y": profile["text"][1], "TEXT_WIDTH": profile["text"][2],
              **{name.upper(): profile[name] for name in ("internal_sda", "internal_scl", "internal_controller", "external_controller", "log_tx", "log_rx")}}
    (files / "probe_config.py").write_text("".join(f"{key} = {value!r}\n" for key, value in config.items()))
    image = build_control_image(SimpleNamespace(base=base, flash_size=int(device["flash_size"], 0), files_dir=files,
        mklittlefs=None, preserve_vfs=False, vfs_offset=layout["offset"], vfs_size=layout["size"], prog_size=32, out_dir=output))
    effective_device = {**device, "vfs_offset": hex(layout["offset"]), "vfs_size": hex(layout["size"])}
    result = {"schema_version": 1, "date": datetime.now(timezone.utc).isoformat(), "status": "PREPARED",
              "validation": "guest-boot-control" if case == "boot-control" else "virtual-device validation",
              "device_id": args.device, "unit_id": case, "runtime": "qemu", "port_id": port["id"],
              "attachments": [] if case == "boot-control" else [{"id": "external1", "unit_id": case, "port_id": port["id"]}],
              "host_profile": profile, "official_host_evidence": port["evidence"], "reference_layout": layout,
              "base_firmware_sha256": digest(base), "firmware_sha256": digest(image), "expected_size": profile["size"],
              "probe_sha256": verify_image_files(image, files, effective_device),
              "driver_source": "Unchanged firmware-bundled unit/hardware/driver modules",
              "adc_fixture": "NOT USED", "host_admission_modified": False,
              "checks": {"actual_partition_layout_checked": True, "packaged_guest_bytes_verified": True},
              "required_markers": [], "injections": []}
    (output / "prepared.json").write_text(json.dumps(result, indent=2) + "\n")
    return output, image, result


def runtime_provenance(client, session_id, expected):
    require(urllib.parse.urlparse(client.url).hostname in {"127.0.0.1", "localhost", "::1"}, "direct runtime verification requires the local Device Service")
    session = client.json(f"sessions/{session_id}")
    pid = session.get("pid")
    require(type(pid) is int and session["state"] == "running", "running local process identity is missing")
    if sys.platform == "darwin":
        buffer = ctypes.create_string_buffer(4096)
        require(ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(pid, buffer, len(buffer)) > 0, "cannot read runtime executable path")
        executable = Path(buffer.value.decode())
        method = "macOS-proc_pidpath"
    else:
        executable = Path(f"/proc/{pid}/exe").resolve(strict=True)
        method = "Linux-proc-exe"
    actual = digest(executable)
    require(actual == expected, "live runtime executable SHA differs from the expected frozen binary")
    return {"schema_version": 1, "status": "PASS", "session_id": session_id, "pid": pid, "method": method,
            "captured_at": datetime.now(timezone.utc).isoformat(), "expected_binary_sha256": expected,
            "observed_binary_sha256": actual, "executable_name": executable.name, "hardware_validation": False}


def validate_bundle(bundle, result):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        require(archive.testzip() is None and len(set(archive.namelist())) == len(archive.namelist()), "corrupt or duplicate ZIP members")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(archive.namelist()) - {"manifest.json"}, "ZIP index differs")
        for name, record in manifest["files"].items():
            content = archive.read(name)
            require(len(content) == record["size"] and hashlib.sha256(content).hexdigest() == record["sha256"], "ZIP member hash/size differs: " + name)
        session = manifest["session"]
        require(session["state"] == "running", "evidence was not captured before stop")
        require(all(session[key] == result[key] for key in ("session_id", "device_id", "runtime", "firmware_sha256")), "ZIP session identity differs")
        require(session["pid"] == result["runtime_provenance"]["pid"], "ZIP runtime PID differs")
        serial = archive.read("serial.log").decode("utf-8")
        require(not any(x in serial for x in FAILURES), "guest exception in evidence")
        for marker in result["required_markers"]:
            require(re.search(r"(?m)^" + re.escape(marker) + r"\r?$", serial), "ZIP lacks guest marker: " + marker)
        if result["attachments"]:
            require({"units/state.json", "units/runtime.json", "units/contract.json", "qom/snapshot.json"} <= set(archive.namelist()), "Unit controller evidence is missing")
            units = manifest["units"]["units"]
            require(len(units) == 1 and units[0]["unit_id"] == result["unit_id"] and units[0]["available"], "ZIP has another Unit attachment")
        with Image.open(io.BytesIO(archive.read("frames/current.png"))) as image:
            require(image.format == "PNG" and list(image.size) == result["expected_size"], "ZIP framebuffer geometry differs")
        return {"files": sorted(archive.namelist()), "pid": session["pid"], "session_id": session["session_id"]}


def validate_case(observed, case):
    profile = observed.result["host_profile"]
    observed.marker("HOST_GEOMETRY %d %d %d" % (*profile["canvas_size"], profile["rotation"]))
    observed.result["checks"]["explicit_guest_canvas_geometry"] = True
    observed.marker("HOST_INTERNAL before 36 1")
    observed.marker("HOST_INTERNAL after_init 36 2")
    if case == "boot-control":
        observed.marker("HOST_BOOT_CONTROL")
        observed.result["checks"]["no_unit_boot_control"] = True
    elif case == "button":
        for index, pressed in enumerate((True, False, True, False)):
            offset = len(observed.serial)
            observed.input({"pressed": pressed})
            observed.wait(lambda text: any(int(raw) == int(not pressed) and int(count) >= index
                          for raw, count in re.findall(r"(?m)^HOST_BUTTON ([01]) (\d+)\r?$", text)), offset=offset)
        observed.result["checks"]["host_gpio_edges_and_original_button_irq_counter"] = True
    elif case == "relay":
        observed.marker("HOST_RELAY 1")
        observed.marker("HOST_RELAY 0")
        states = set()
        for _ in range(16):
            states.add(observed.properties()["output-level"])
            time.sleep(0.25)
        require(states == {True, False}, "host GPIO output did not match both relay states")
        observed.result["checks"]["host_relay_guest_output_readback"] = True
    else:
        observed.marker("HOST_EXTERNAL_SCAN 68 112")
        for expected in ((31.5, 67, 98765), (18.75, 45.5, 103200)):
            offset = len(observed.serial)
            observed.input(dict(zip(("temperature-c", "humidity-pct", "pressure-pa"), expected)))
            observed.wait(lambda text: any(all(abs(float(value) - target) <= tolerance for value, target, tolerance
                in zip(row, expected, (0.2, 0.2, 1))) for row in re.findall(r"(?m)^HOST_ENV ([\d.-]+) ([\d.-]+) ([\d.-]+)\r?$", text)), offset=offset)
            observed.wait(lambda text: "HOST_INTERNAL loop 36 " in text, offset=offset)
        properties = observed.properties()
        require(all(properties[key] > 0 for key in ("transactions", "read-bytes", "written-bytes", "input-events")), "external ENV has no independent controller traffic")
        observed.result["checks"]["external_env_two_inputs_and_onboard_i2c_isolation"] = True
    offset = len(observed.serial)
    observed.wait(lambda text: "HOST_INTERNAL loop 36 " in text, offset=offset)
    observed.result["checks"]["onboard_identity_after_external_operations"] = True


def run_case(client, args, case):
    output, image, result = prepare(args, case)
    if args.prepare_only:
        print(f"{args.device}/{case}: PREPARED (no API request or runtime)", flush=True)
        return result
    session_id = None
    result["status"] = "FAIL"
    try:
        if case != "boot-control":
            registry = client.json(f"units?device_id={args.device}")
            unit = next(row for row in registry["units"] if row["id"] == case)
            require(args.device in unit["runtime"].get("hosts", []), "runtime_model_gap: host/Unit combination is not admitted; runner never expands the whitelist")
        artifact = client.json("artifacts", method="POST", body=image.read_bytes(), headers={"Content-Type": "application/octet-stream", "X-Artifact-Name": f"{args.device}-{case}-host-probe.bin"})
        firmware = client.json("firmware", method="POST", payload={"device_id": args.device, "kind": "merged", "artifact_id": artifact["artifact_id"]})
        session = client.json("sessions", method="POST", payload={"device_id": args.device, "firmware_id": firmware["firmware_id"], "runtime": "qemu", "ttl_seconds": 900, "ready_marker": "HOST_PROBE_READY", "ready_timeout_seconds": 180, "units": result["attachments"]})
        session_id = result["session_id"] = session["session_id"]
        print(f"{args.device}/{case}: visible session {session_id} created", flush=True)
        observed = Observations(client, session_id, result)
        observed.marker(f"HOST_PROBE_READY {args.device} {case}", timeout=180)
        result["runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)
        (output / "runtime-provenance.json").write_text(json.dumps(result["runtime_provenance"], indent=2) + "\n")
        result["checks"]["live_runtime_pid_sha_verified"] = True
        validate_case(observed, case)
        if result["attachments"]:
            result["unit_state"] = observed.state()
        frame = client.raw(f"sessions/{session_id}/frame.png")
        (output / "frame.png").write_bytes(frame)
        with Image.open(io.BytesIO(frame)) as image:
            require(list(image.size) == result["expected_size"], "framebuffer size differs")
        result["frame_sha256"] = hashlib.sha256(frame).hexdigest()
        require(png_metrics(frame)["unique_colors"] > 1, "empty application frame")
        result["checks"]["nonblank_host_application_frame"] = True
    except Exception as error:
        result["error"] = type(error).__name__ + ": " + str(error)
    finally:
        if session_id:
            try:
                serial = client.json(f"sessions/{session_id}/serial?limit=262144")["data"]
                (output / "serial.txt").write_text(serial)
            except Exception as error:
                result["serial_error"] = str(error)
            try:
                bundle = client.raw(f"sessions/{session_id}/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence_sha256"] = hashlib.sha256(bundle).hexdigest()
                result["evidence_summary"] = validate_bundle(bundle, result)
                result["checks"]["evidence_before_stop"] = True
            except Exception as error:
                result["evidence_error"] = str(error)
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", method="DELETE")
                history = client.json(f"sessions/{session_id}")
                require(stopped["state"] in {"stopped", "failed"} and history["state"] in {"stopped", "failed"} and history["firmware_sha256"] == result["firmware_sha256"], "retained session metadata differs")
                frame = client.raw(f"sessions/{session_id}/frame.png")
                (output / "history-frame.png").write_bytes(frame)
                require(png_metrics(frame)["unique_colors"] > 1, "retained host frame is empty")
                result["checks"]["purge_zero_history_and_frame_retained"] = True
            except Exception as error:
                result["stop_error"] = str(error)
        if session_id and not any(result.get(key) for key in ("error", "serial_error", "evidence_error", "stop_error")) and all(v is True for v in result["checks"].values()):
            result["status"] = "PASS"
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"{args.device}/{case}: {result['status']} {result.get('error', '')}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=HOSTS, required=True)
    parser.add_argument("--case", choices=(*CASES, "all"), action="append")
    parser.add_argument("--api-url", default="http://127.0.0.1:8787")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--expected-runtime-sha256")
    args = parser.parse_args()
    if not args.prepare_only and not re.fullmatch(r"[0-9a-f]{64}", args.expected_runtime_sha256 or ""):
        parser.error("execution requires an exact --expected-runtime-sha256")
    args.out_dir = args.out_dir.resolve()
    cases = list(CASES) if not args.case or "all" in args.case else list(dict.fromkeys(args.case))
    client = None if args.prepare_only else Client(args.api_url)
    results = [run_case(client, args, case) for case in cases]
    target = args.out_dir / args.device / "aggregate.json"
    target.write_text(json.dumps({"schema_version": 1, "results": results}, indent=2) + "\n")
    return 0 if all(r["status"] in {"PREPARED", "PASS"} for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
