#!/usr/bin/env python3
"""Exercise stock Core2 UIFlow2 startup through visible Device Service sessions.

Only image preparation is local. This runner never launches QEMU or the service.
Raw images, API responses and evidence belong in a fresh ignored output folder.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import ctypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "platform/tools"), str(ROOT / "tests/uiflow2")]
from firmware_analysis import analyze_esp_image, find_app_descriptor, parse_partition_table  # noqa: E402
from run_profile_ui_test import build_image, runtime_files  # noqa: E402
from user_firmware_matrix import png_metrics  # noqa: E402

CASES = ("display", "widgets", "lvgl", "network")
BASE_SHA256 = "b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4"
APP_SHA256 = "c02171cfdde7a51e19c40dbe3e1e1b95033a0087591d34c69f88ebbfdd49de47"
FLASH_SIZE = 16 << 20
FAILURE = re.compile(r"Traceback \(most recent call last\)|Guru Meditation|Interrupt wdt timeout|TG[01]WDT_SYS_RESET|CORE2_STARTUP:\w+:ERROR")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Api:
    def __init__(self, url, token_file=None):
        self.url = url.rstrip("/")
        require(urllib.parse.urlparse(self.url).hostname in {"localhost", "127.0.0.1", "::1"},
                "live executable verification requires a local Device Service")
        self.token = token_file.read_text(encoding="utf-8").strip() if token_file else ""

    def raw(self, path, method="GET", payload=None, body=None, headers=None):
        headers = dict(headers or {})
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if payload is not None:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.url + "/api/v1/" + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # Responses can contain source/configuration. Keep them out of stdout.
            error.close()
            raise RuntimeError(f"{method} {path}: HTTP {error.code}") from error

    def json(self, *args, **kwargs):
        return json.loads(self.raw(*args, **kwargs))


def firmware_identity(raw, expected_base, expected_app):
    require(sha(raw) == expected_base, "base firmware SHA256 mismatch; legacy or unpinned inputs are rejected")
    require(len(raw) <= FLASH_SIZE, "base firmware exceeds Core2 flash capacity")
    data = raw + b"\xff" * (FLASH_SIZE - len(raw))
    table = parse_partition_table(data)
    require(table["valid"], "base partition table is invalid")
    apps = []
    for partition in table["partitions"]:
        if partition["type"] != 0:
            continue
        image = analyze_esp_image(data, partition["offset"])
        if not image["valid"]:
            continue
        require(image["chip_id"] == 0, "base application is not ESP32")
        require(image["image_end"] <= partition["offset"] + partition["size"], "application exceeds its partition")
        descriptor = find_app_descriptor(data, partition["offset"], image["image_end"])
        require(descriptor and descriptor["version"] == "V2.5.3", "base is not UIFlow2 V2.5.3")
        app_sha = sha(data[partition["offset"]:image["image_end"]])
        require(app_sha == expected_app, "application header/segments SHA256 differs from the pinned stock executable")
        apps.append({"offset": partition["offset"], "image_end": image["image_end"],
                     "sha256": app_sha, "descriptor": descriptor})
    require(len(apps) == 1, "expected exactly one pinned stock application")
    vfs = [p for p in table["partitions"] if p["label"] == "vfs" and p["type"] == 1 and p["subtype"] == 0x81]
    require(len(vfs) == 1, "base requires one LittleFS vfs partition")
    layout = vfs[0]
    start, end = layout["offset"], layout["offset"] + layout["size"]
    require(layout["size"] > 0 and start % 4096 == 0 and layout["size"] % 4096 == 0 and end <= FLASH_SIZE,
            "VFS layout is unaligned or out of range")
    require(not any(p is not layout and start < p["offset"] + p["size"] and p["offset"] < end for p in table["partitions"]),
            "VFS overlaps another partition")
    return {"base_sha256": sha(raw), "base_bytes": len(raw), "normalized_sha256": sha(data),
            "application_hash_format": "esp-image-header-through-final-segment/v1", "application": apps[0], "vfs": layout}


def prepare(args, case, output):
    identity = firmware_identity(args.base.read_bytes(), args.expected_base_sha256, args.expected_app_sha256)
    files = output / "files"
    shutil.copytree(Path(__file__).parent / case, files, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (files / "boot.py").write_text('_uiflow_run_main = True\nprint("CORE2_STARTUP_BOOT")\n', encoding="utf-8")
    sources = {p.as_posix(): sha(source.read_bytes()) for p, source in runtime_files(files).items()}
    layout = identity["vfs"]
    with contextlib.redirect_stdout(io.StringIO()):
        image = build_image(SimpleNamespace(base=args.base, flash_size=FLASH_SIZE, files_dir=files,
            mklittlefs=None, preserve_vfs=False, vfs_offset=layout["offset"], vfs_size=layout["size"], prog_size=32, out_dir=output))
    built = image.read_bytes()
    # The probe may change the filesystem, never executable or boot bytes.
    raw = args.base.read_bytes().ljust(FLASH_SIZE, b"\xff")
    start, end = layout["offset"], layout["offset"] + layout["size"]
    require(built[:start] == raw[:start] and built[end:] == raw[end:], "image preparation modified bytes outside VFS")
    identity.update(firmware_sha256=sha(built), source_file_sha256=sources)
    save(output / "prepared.json", identity)
    return image, identity


def serial_checks(serial, case):
    def marker(suffix):
        return bool(re.search(r"(?m)^CORE2_STARTUP:" + re.escape(case + ":" + suffix) + r"\r?$", serial))
    checks = {"uiflow2_version": bool(re.search(r"\bV2\.5\.3\b", serial)),
              "ready_marker": marker("READY"), "done_marker": marker("DONE"),
              "no_traceback_wdt_or_error": not bool(FAILURE.search(serial)),
              "single_boot": serial.count("CORE2_STARTUP_BOOT") == 1 and len(re.findall(r"(?m)^\r?rst:0x", serial)) <= 1}
    if case == "network":
        active = re.search(r"(?m)^CORE2_STARTUP:network:ACTIVE True elapsed_ms (\d+)\r?$", serial)
        ntp = re.search(r"(?m)^CORE2_STARTUP:network:NTP_ERROR .+ elapsed_ms (\d+)\r?$", serial)
        checks.update(wlan_active_returned=bool(active and int(active[1]) <= 10000),
                      disconnected_reported=bool(re.search(r"(?m)^CORE2_STARTUP:network:CONNECTED False\r?$", serial)),
                      bounded_network_transport_error=bool(ntp and int(ntp[1]) <= 5000))
    return checks


def frame_checks(data, case):
    metrics = {**png_metrics(data), "sha256": sha(data), "bytes": len(data)}
    checks = {"application_frame": metrics["width"] == 320 and metrics["height"] == 240 and metrics["unique_colors"] > 1}
    if case == "lvgl":
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            pixels = list(image.convert("RGB").getdata())
            width, height = image.size
        background = Counter(pixels).most_common(1)[0][0]
        foreground = [(index % width, index // width) for index, pixel in enumerate(pixels) if pixel != background]
        bbox = ([min(x for x, _ in foreground), min(y for _, y in foreground),
                 max(x for x, _ in foreground), max(y for _, y in foreground)] if foreground else None)
        max_run, run = 0, 0
        for index, pixel in enumerate(pixels):
            if index % width == 0:
                run = 0
            run = run + 1 if pixel != background else 0
            max_run = max(max_run, run)
        rows = len({y for _, y in foreground})
        metrics.update(background_rgb=list(background), foreground_pixels=len(foreground), foreground_bbox=bbox,
                       foreground_rows=rows, maximum_horizontal_run=max_run)
        # The fixed probe creates one label at (12,24), with an 18-pixel font.
        # Counts alone previously accepted full-width torn scanlines. This
        # spatial gate rejects those while final glyph readability is reviewed.
        checks.update(lvgl_background=all(abs(a - b) <= 8 for a, b in zip(background, (16, 20, 24))),
                      lvgl_label_region=bool(bbox and bbox[0] >= 12 and bbox[2] < 300 and bbox[1] >= 20 and bbox[3] < 64),
                      lvgl_label_foreground=100 < len(foreground) < 5000,
                      lvgl_glyph_structure=10 <= rows <= 36 and max_run <= 24)
    return checks, metrics


def process_identity(pid):
    """Read a real local PID start identity without exposing its arguments."""
    require(type(pid) is int and pid > 0, "runtime PID is invalid")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {"exists": False, "start_token": None}
    result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "lstart="],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2, check=False)
    token = result.stdout.strip() if result.returncode == 0 else ""
    require(bool(token), "live process start identity could not be read")
    return {"exists": True, "start_token": token}


def runtime_executable(pid):
    if sys.platform == "darwin":
        buffer = ctypes.create_string_buffer(4096)
        require(ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(pid, buffer, len(buffer)) > 0,
                "cannot read runtime executable path")
        return Path(buffer.value.decode())
    return Path(f"/proc/{pid}/exe").resolve(strict=True)


def runtime_provenance(api, session, expected_sha256, receipt_path=None):
    pid = session.get("pid")
    require(type(pid) is int and session.get("state") == "running", "running process identity is missing")
    identity = process_identity(pid)
    require(identity["exists"] and identity["start_token"], "runtime process identity is missing")
    executable = runtime_executable(pid)
    actual = sha(executable.read_bytes())
    require(actual == expected_sha256, "live runtime SHA256 differs from the expected binary")
    current = api.json("sessions/" + session["session_id"])
    worker = session.get("worker") or {}
    require(type(worker.get("generation")) is int and bool(worker.get("worker_id")), "worker identity is missing")
    require(current.get("pid") == pid and current.get("worker") == worker and current.get("state") == "running"
            and process_identity(pid) == identity, "runtime ownership changed during executable verification")
    env = current.get("runtime_env") or {}
    require(str(env.get("M5SW_DISABLE_WDT", "0")).lower() in {"0", "false", ""}, "watchdog-disable diagnostics cannot satisfy startup")
    receipt_path = receipt_path or executable.parent.parent / ".m5-unit-runtime-source.json"
    require(receipt_path.is_file(), "runtime source receipt is missing; supply --runtime-source-receipt")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    return {"session_id": session["session_id"], "pid": pid, "process_start_token": identity["start_token"],
            "worker_id": worker["worker_id"], "worker_generation": worker["generation"], "binary_sha256": actual,
            "executable_name": executable.name, "source_receipt_sha256": sha(receipt_path.read_bytes()),
            "source_file_count": len(receipt.get("files", {})), "patches": receipt.get("patches", {})}


def collect_qom(api, prefix, *, offline):
    # Match serve.py and the OpenAPI POST contract, including body parameters.
    snapshot = api.json(prefix + "/qom-snapshot", "POST", payload={"path": "/machine", "depth": 2, "max_nodes": 500})
    listing = api.json(prefix + "/qom/list?" + urllib.parse.urlencode({"path": "/machine/unattached"}))
    candidates = [row["name"] for row in listing.get("properties", []) if row.get("type") == "child<misc.esp32_wifi>"]
    require(len(candidates) == 1, "expected exactly one real Core2 WiFi controller")
    path = "/machine/unattached/" + candidates[0]
    radio = api.json(prefix + "/qom?" + urllib.parse.urlencode({"path": path, "property": "radio-enabled"}))
    require(radio.get("value") is (not offline), "WiFi radio state does not match the selected runtime")
    return snapshot, radio


def validate_bundle(bundle, session):
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and archive.testzip() is None, "evidence ZIP is corrupt or contains duplicate members")
        manifest = json.loads(archive.read("manifest.json"))
        require(set(manifest["files"]) == set(names) - {"manifest.json"}, "evidence ZIP manifest differs from its members")
        for name, record in manifest["files"].items():
            data = archive.read(name)
            require(len(data) == record["size"] and sha(data) == record["sha256"], "evidence member hash/size differs: " + name)
        retained = manifest["session"]
        require(all(retained.get(key) == session.get(key) for key in ("session_id", "firmware_sha256", "device_id", "runtime", "pid")),
                "evidence belongs to another guest or firmware")
        return {"sha256": sha(bundle), "bytes": len(bundle), "member_count": len(names),
                "session_state": retained.get("state"),
                "before_stop": retained.get("state") in {"booting", "running"}}, archive.read("serial.log").decode("utf-8"), archive.read("frames/current.png")


def retained_history(api, prefix, session, frame, serial, output, case):
    history = api.json(prefix)
    save(output / "history.json", history)
    history_frame = api.raw(prefix + "/frame.png")
    (output / "history-frame.png").write_bytes(history_frame)
    history_serial = api.json(prefix + "/serial?offset=0&limit=1048576").get("data", "")
    (output / "history-serial.log").write_text(history_serial, encoding="utf-8")
    old_pid = session.get("pid")
    checks = {"stopped_with_history": history.get("state") == "stopped",
              "flash_released": history.get("flash_retained") is False,
              "runtime_pid_gone": type(old_pid) is int and history.get("pid") in {None, old_pid} and not process_identity(old_pid)["exists"],
              "history_frame_exact": frame is not None and history_frame == frame,
              # A terminal prompt can append after ZIP capture; no earlier byte
              # may disappear, and the entire retained log is independently hashed.
              "history_serial_retained": serial is not None and history_serial.startswith(serial)}
    frame_result, metrics = frame_checks(history_frame, case)
    checks.update({"history_" + name: value for name, value in frame_result.items()})
    checks.update({"history_" + name: value for name, value in serial_checks(history_serial, case).items()})
    return checks, {"frame_sha256": sha(history_frame), "serial_sha256": sha(history_serial.encode("utf-8")),
                    "serial_bytes": len(history_serial.encode("utf-8")), "frame_metrics": metrics}


def run_case(api, args, case):
    output = args.out_dir / case
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema_version": 1, "validation": "virtual-device validation", "hardware_validation": "NOT RUN",
              "started_at": datetime.now(timezone.utc).isoformat(), "case": case, "device_id": "core2",
              "runtime": args.runtime, "profile": "core2-openmac" if args.runtime == "qemu-wifi" else None,
              "status": "FAIL", "checks": {}}
    session_id, latest = None, None
    retained_frame, retained_serial = None, None
    try:
        image, identity = prepare(args, case, output)
        result["firmware"] = identity
        artifact = api.json("artifacts", "POST", body=image.read_bytes(), headers={
            "Content-Type": "application/octet-stream", "X-Artifact-Name": f"core2-startup-{case}.bin"})
        firmware = api.json("firmware", "POST", payload={"device_id": "core2", "kind": "merged", "artifact_id": artifact["artifact_id"]})
        save(output / "firmware.json", firmware)
        require(firmware["sha256"] == identity["firmware_sha256"], "service firmware differs from prepared bytes")
        payload = {"device_id": "core2", "firmware_id": firmware["firmware_id"], "runtime": args.runtime,
                   "ready_marker": f"CORE2_STARTUP:{case}:READY", "ready_timeout_seconds": args.timeout,
                   "ttl_seconds": min(86400, max(300, int(args.timeout) + 120))}
        if args.runtime == "qemu-wifi":
            payload["network"] = {"profile": "core2-openmac", "attempts": 1, "capture_pcap": True,
                                  "expected_markers": [f"CORE2_STARTUP:{case}:DONE"]}
        latest = api.json("sessions", "POST", payload=payload)
        session_id = latest["session_id"]
        result.update(session_id=session_id, firmware_sha256=firmware["sha256"])
        prefix = "sessions/" + session_id
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            latest = api.json(prefix)
            save(output / "session.json", latest)
            serial = api.json(prefix + "/serial?offset=0&limit=1048576").get("data", "")
            (output / "serial.log").write_text(serial, encoding="utf-8")
            result["checks"].update(serial_checks(serial, case))
            if FAILURE.search(serial) or latest["state"] in {"failed", "stopped"}:
                raise RuntimeError("guest failed or reset before startup acceptance")
            if latest["state"] == "running" and all(result["checks"].values()):
                break
            time.sleep(0.25)
        require(latest["state"] == "running" and all(result["checks"].values()), "guest startup markers or bounded network result timed out")
        result["runtime_provenance"] = runtime_provenance(api, latest, args.expected_runtime_sha256, args.runtime_source_receipt)
        qom, radio = collect_qom(api, prefix, offline=args.runtime == "qemu")
        save(output / "qom.json", qom)
        save(output / "radio.json", radio)
        result["radio"] = radio
        result["checks"]["qom_data"] = bool(qom.get("nodes"))
        result["checks"]["radio_matches_runtime"] = radio.get("value") is (args.runtime != "qemu")
        frame = api.raw(prefix + "/frame.png")
        (output / "frame.png").write_bytes(frame)
        checks, result["frame"] = frame_checks(frame, case)
        result["checks"].update(checks)
        if args.runtime == "qemu-wifi":
            save(output / "network.json", api.json(prefix + "/network"))
        result["checks"]["runtime_unchanged"] = runtime_provenance(api, latest, args.expected_runtime_sha256, args.runtime_source_receipt) == result["runtime_provenance"]
    except Exception as error:
        result["error"] = str(error)
    finally:
        if session_id:
            prefix = "sessions/" + session_id
            try:
                # Evidence must be requested while the VM and its Flash still exist.
                latest = api.json(prefix)
                bundle = api.raw(prefix + "/evidence")
                (output / "evidence.zip").write_bytes(bundle)
                result["evidence"], serial, frame = validate_bundle(bundle, latest)
                retained_frame, retained_serial = frame, serial
                result["checks"].update({"zip_" + name: value for name, value in serial_checks(serial, case).items()})
                result["checks"]["evidence_before_stop"] = result["evidence"]["before_stop"]
                result["checks"]["evidence_session_running"] = result["evidence"]["session_state"] == "running"
                checks, result["evidence"]["frame_metrics"] = frame_checks(frame, case)
                result["checks"].update({"zip_" + name: value for name, value in checks.items()})
            except Exception as error:
                result["evidence_error"] = str(error)
            try:
                api.json(prefix + "?purge=0&retain_flash=0", "DELETE")
                checks, result["history"] = retained_history(api, prefix, latest, retained_frame, retained_serial, output, case)
                result["checks"].update(checks)
            except Exception as error:
                result["stop_error"] = str(error)
        result["status"] = "PASS" if session_id and not any(k in result for k in ("error", "evidence_error", "stop_error")) and all(result["checks"].values()) else "FAIL"
        save(output / "result.json", result)
    print(json.dumps({"case": case, "status": result["status"], "session_id": session_id}, ensure_ascii=False), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--case", choices=(*CASES, "all"), default="all")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--base", type=Path, default=ROOT / "platform/.cache/firmware/core2/uiflow2.bin")
    parser.add_argument("--expected-base-sha256", default=BASE_SHA256)
    parser.add_argument("--expected-app-sha256", default=APP_SHA256)
    parser.add_argument("--expected-runtime-sha256", required=True)
    parser.add_argument("--runtime-source-receipt", type=Path)
    parser.add_argument("--runtime", choices=("qemu", "qemu-wifi"), default="qemu")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    for field in ("expected_base_sha256", "expected_app_sha256", "expected_runtime_sha256"):
        if not re.fullmatch("[0-9a-f]{64}", getattr(args, field)):
            parser.error(field.replace("_", "-") + " must be a lowercase SHA256")
    if not 10 <= args.timeout <= 3600:
        parser.error("--timeout must be between 10 and 3600 seconds")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    api = Api(args.api, args.token_file)
    results = [run_case(api, args, case) for case in (CASES if args.case == "all" else (args.case,))]
    save(args.out_dir / "summary.json", {"status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "results": results})
    return 0 if all(result["status"] == "PASS" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
