#!/usr/bin/env python3
"""Run the S3 cache/atomic fixture in an owned Device Service session."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True, help="Owned service URL ending in /api/v1")
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    token = args.token_file.read_text().strip()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    def request(path, method="GET", payload=None, data=None, raw=False):
        headers = {"Authorization": f"Bearer {token}"}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers.update({"Content-Type": "application/octet-stream",
                            "X-Artifact-Name": "s3-cache-atomic.bin"})
        req = urllib.request.Request(f"{args.api.rstrip('/')}/{path}", data=data,
                                     headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=180) as response:
            body = response.read()
        return body if raw else json.loads(body)

    image = args.image.read_bytes()
    artifact = request("artifacts", "POST", data=image)
    firmware = request("firmware", "POST", {
        "device_id": "stackchan", "kind": "merged",
        "artifact_id": artifact["artifact_id"],
    })
    analysis = request("firmware/analyze", "POST", {"firmware_id": firmware["firmware_id"]})
    session = request("sessions", "POST", {
        "device_id": "stackchan", "runtime": "qemu",
        "firmware_id": firmware["firmware_id"], "ttl_seconds": 600,
        "ready_timeout_seconds": 30,
    })
    sid = session["session_id"]
    result = {"scope": "virtual-device validation", "firmware_sha256": hashlib.sha256(image).hexdigest(),
              "analysis": analysis, "session_id": sid, "status": "FAIL"}
    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            snapshot = request(f"sessions/{sid}")
            logs = request(f"sessions/{sid}/logs?offset=0&limit=1048576")
            serial = logs.get("data", "")
            stderr = logs.get("stderr", logs.get("qemu_stderr", ""))
            if snapshot["state"] == "failed":
                break
            if "S3_CACHE_ATOMIC_WORKER_DONE" in serial:
                result["status"] = "PASS" if (
                    "S3_CACHE_ATOMIC_PASS" in serial
                    and not any(marker in serial + stderr for marker in (
                        "Guru Meditation", "assert failed:", "Task watchdog got triggered",
                        "atomic_mmu_lookup", "Bad ram pointer", "S3_CACHE_ATOMIC_CREATE_FAIL"))
                ) else "FAIL"
                break
            time.sleep(0.5)
        result.update({"snapshot": snapshot, "logs": logs})
        (args.out_dir / "evidence.zip").write_bytes(request(f"sessions/{sid}/evidence", raw=True))
    finally:
        result["stop"] = request(f"sessions/{sid}?purge=0", "DELETE")
        (args.out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "firmware_sha256": result["firmware_sha256"]}))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
