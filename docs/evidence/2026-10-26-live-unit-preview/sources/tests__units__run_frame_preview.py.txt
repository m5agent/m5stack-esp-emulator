#!/usr/bin/env python3
"""Opt-in real Device Service preview sampling, conditional GET and reset proof."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import zipfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/units"))
from run_live_program import ProbeClient, poll, require, save
from run_host_cases import runtime_provenance


def source(label, color):
    return f'''import M5
import time
M5.begin()
M5.Display.setBrightness(255)
M5.Display.fillScreen({color})
M5.Display.setTextColor(0)
M5.Display.setTextSize(2)
M5.Display.setCursor(5, 5)
M5.Display.print("PREVIEW {label}")
print("FRAME_PREVIEW_{label}_READY")
while True:
 M5.update()
 time.sleep_ms(25)
'''


def run(args):
    require(args.execute, "--execute is required for visible virtual sessions")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    client = ProbeClient(args.api, args.out_dir)
    session_id, expected = None, None
    report = {"validation": "virtual-device validation", "hardware_validation": "NOT RUN", "status": "FAIL",
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
                  "tests/units/run_frame_preview.py", "platform/tools/device_service.py",
                  "platform/tools/serve.py", "platform/tools/frame_cache.py")}, "frames": []}
    try:
        created = client.json("sessions", "POST", {"device_id": "cores3", "program_mode": "uiflow-live", "ttl_seconds": 300})
        session_id = created["session_id"]
        prefix = f"sessions/{session_id}"
        ready = poll(lambda: client.json(prefix), lambda r: r["state"] in {"running", "failed", "stopped"}, 90)
        require(ready["state"] == "running", str(ready.get("error")))
        report.update(session_id=session_id, pid=ready["pid"], firmware_sha256=ready["firmware_sha256"], runtime="qemu", device_id="cores3")
        report["runtime_provenance"] = runtime_provenance(client, session_id, args.expected_runtime_sha256)

        def submit(label, color):
            nonlocal expected
            offset = client.json(prefix + "/serial?limit=1048576")["next_offset"]
            result = client.json(prefix + "/program", "POST", {"source": source(label, color), "expected_execution_id": expected})
            expected = result["program"]["execution_id"]
            save(args.out_dir / f"program-{label}.json", result)
            poll(lambda: client.json(prefix + f"/serial?offset={offset}"), lambda r: f"FRAME_PREVIEW_{label}_READY" in r["data"])
            require(result["program"]["pid"] == ready["pid"], "program replaced guest process")
            return result["program"]

        def frame(age=None, etag=None):
            path = prefix + "/frame.png" + (f"?max_age_ms={age}" if age is not None else "")
            request = urllib.request.Request(args.api.rstrip("/") + "/api/v1/" + path, headers={"If-None-Match": etag} if etag else {})
            started = time.monotonic()
            try:
                response = urllib.request.urlopen(request, timeout=15)
            except urllib.error.HTTPError as error:
                if error.code != 304:
                    raise
                response = error
            with response:
                headers, data, status = dict(response.headers), response.read(), response.status
            row = {"status": status, "headers": headers, "request_seconds": time.monotonic() - started,
                   "body_bytes": len(data), "body_sha256": hashlib.sha256(data).hexdigest()}
            if status == 200:
                require(data.startswith(b"\x89PNG"), "frame is not PNG")
                require(row["body_sha256"] == headers["X-Frame-SHA256"], "frame hash header differs from actual bytes")
            return row, data

        a = submit("A", 0xFFFFFF)
        first, png_a = frame(1000)
        require(first["status"] == 200 and first["headers"]["X-Frame-Execution-ID"] == a["execution_id"], "first frame context differs")
        (args.out_dir / "frame-a.png").write_bytes(png_a)
        with ThreadPoolExecutor(max_workers=8) as pool:
            burst = list(pool.map(lambda _: frame(1000, first["headers"]["ETag"]), range(8)))
        require(all(row["status"] == 304 and not data for row, data in burst), "concurrent readers did not reuse the same sample")
        require(all(row["headers"]["X-Frame-Capture-Seq"] == first["headers"]["X-Frame-Capture-Seq"] for row, _ in burst), "parallel readers republished a sample inside its TTL")
        report["concurrent_readers"] = [row for row, _ in burst]
        report["burst_observation_seconds"] = max(row["request_seconds"] for row, _ in burst)
        app_ready = client.json(prefix + "/wait", "POST", {"ready": {"frame_nonblank": True,
                                             "frame_min_bytes": 1, "frame_min_nonblack_pixels": 1}})
        require("captured_monotonic" not in app_ready["frame"], "internal TTL clock escaped through wait response")
        save(args.out_dir / "application-ready.json", app_ready)
        fresh, _ = frame(None, first["headers"]["ETag"])
        require(fresh["status"] == 200, "default frame capture was silently changed to conditional reuse")
        report["default_fresh"] = fresh
        b = submit("B", 0x88FF88)
        changed, png_b = frame(1000, first["headers"]["ETag"])
        require(changed["status"] == 200 and png_a != png_b, "program replacement reused the previous generation")
        require(changed["headers"]["X-Frame-Execution-ID"] == b["execution_id"], "cached frame got the wrong program identity")
        require(int(changed["headers"]["X-Frame-Capture-Seq"]) > int(first["headers"]["X-Frame-Capture-Seq"]), "new execution did not invalidate prior capture")
        (args.out_dir / "frame-b.png").write_bytes(png_b)
        for name, data in (("A", png_a), ("B", png_b)):
            image = Image.open(io.BytesIO(data)).convert("RGB")
            report["frames"].append({"version": name, "corner_rgb": image.getpixel((image.width - 2, image.height - 2))})
        require(report["frames"][0]["corner_rgb"] != report["frames"][1]["corner_rgb"], "actual application pixels did not change")
        # Exercise reset separately: it intentionally resets VM state, unlike /program.
        serial_before_reset = client.json(prefix + "/serial?limit=1048576")["next_offset"]
        client.json(prefix + "/reset", "POST", {})
        poll(lambda: client.json(prefix + f"/serial?offset={serial_before_reset}"), lambda r: "M5EMU_UART_REPL_READY" in r["data"], 40)
        reset_frame, _ = frame(1000)
        require(int(reset_frame["headers"]["X-Frame-Capture-Seq"]) > int(changed["headers"]["X-Frame-Capture-Seq"]), "reset did not invalidate preview generation")
        c = submit("C", 0x8888FF)
        after_reset, png_c = frame(125)
        require(after_reset["headers"]["X-Frame-Execution-ID"] == c["execution_id"], "post-reset program context differs")
        (args.out_dir / "frame-c.png").write_bytes(png_c)
        # A new execution can deliberately keep identical display pixels.
        # Conditional image reuse must still return its actual new context.
        offset = client.json(prefix + "/serial?limit=1048576")["next_offset"]
        d = client.json(prefix + "/program", "POST", {
            "source": "import time\nprint('FRAME_PREVIEW_D_READY')\nwhile True:\n time.sleep_ms(25)\n",
            "expected_execution_id": expected})["program"]
        expected = d["execution_id"]
        poll(lambda: client.json(prefix + f"/serial?offset={offset}"), lambda r: "FRAME_PREVIEW_D_READY" in r["data"])
        unchanged, body = frame(1000, after_reset["headers"]["ETag"])
        require(unchanged["status"] == 304 and not body, "identical pixels were not conditionally reused")
        require(unchanged["headers"]["X-Frame-Execution-ID"] == d["execution_id"], "304 reused obsolete program context")
        require(int(unchanged["headers"]["X-Frame-Capture-Seq"]) > int(after_reset["headers"]["X-Frame-Capture-Seq"]), "same-pixel execution did not invalidate sample generation")
        report["same_pixels_new_execution"] = unchanged
        report.update(initial_preview=first, changed_preview=changed, reset_preview=reset_frame, after_reset=after_reset)
        evidence = client.raw(prefix + "/evidence")
        (args.out_dir / "evidence.zip").write_bytes(evidence)
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            require(archive.testzip() is None, "evidence ZIP is corrupt")
            metadata = json.loads(archive.read("manifest.json"))
            require(metadata["session"]["firmware_sha256"] == ready["firmware_sha256"], "evidence firmware identity differs")
            require("captured_monotonic" not in metadata["frame"], "internal TTL clock escaped into evidence")
        stopped = client.json(prefix + "?purge=0", "DELETE")
        if stopped["state"] not in {"stopped", "failed"}:
            stopped = poll(lambda: client.json(prefix), lambda r: r["state"] in {"stopped", "failed"}, 40)
        require(stopped["state"] == "stopped" and not stopped["flash_retained"], "cleanup not confirmed")
        save(args.out_dir / "stopped.json", stopped)
        history, png_history = frame(1000)
        require(history["headers"]["X-Frame-Source"] == "persisted", "stopped session returned a cached live frame")
        require(history["headers"]["X-Frame-Captured-At"] >= after_reset["headers"]["X-Frame-Captured-At"], "history lost the final capture time")
        (args.out_dir / "history.png").write_bytes(png_history)
        report.update(status="PASS", history=history, checks={"conditional_get_and_shared_sample": True,
                      "default_capture_remains_fresh": True, "program_and_reset_invalidation": True,
                      "actual_changed_application_pixels": True, "evidence_before_stop_and_retained_history": True})
        session_id = None
    except Exception as error:
        report["error"] = repr(error)
    finally:
        if session_id:
            try:
                (args.out_dir / "failure-evidence.zip").write_bytes(client.raw(f"sessions/{session_id}/evidence"))
            except Exception as error:
                report["evidence_error"] = repr(error)
            try:
                stopped = client.json(f"sessions/{session_id}?purge=0", "DELETE")
                if stopped["state"] not in {"stopped", "failed"}:
                    stopped = poll(lambda: client.json(f"sessions/{session_id}"), lambda r: r["state"] in {"stopped", "failed"}, 40)
                save(args.out_dir / "stopped.json", stopped)
            except Exception as error:
                report["cleanup_error"] = repr(error)
        save(args.out_dir / "report.json", report)
    require(report["status"] == "PASS", report.get("error", "preview test failed"))
    print("FRAME_PREVIEW_PASS", args.out_dir / "report.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8787")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--expected-runtime-sha256", required=True)
    run(parser.parse_args())
