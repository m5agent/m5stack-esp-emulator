#!/usr/bin/env python3
"""Verify the Core2 for AWS ATECC608 path through Device Service /api/v1."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_IMAGE = (
    ROOT
    / "platform/.cache/service-hostimage/artifacts/"
    "22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a.bin"
)
SOURCE_SHA256 = "22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a"
NORMALIZED_SHA256 = "104062aa0e6f52470f0c7f409d202af5d2dad5c3e5ee8f7e65815508a512ef3c"
ATECC_MARKER = "atecc608: ok: 60 02"


def save(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


class Api:
    def __init__(self, base: str, token: str = ""):
        self.base = base.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, *, payload=None, raw: bytes = None,
             headers: dict | None = None):
        request_headers = dict(headers or {})
        if self.token:
            request_headers["Authorization"] = "Bearer " + self.token
        body = raw
        if payload is not None:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, body, request_headers, method=method
        )
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            content = response.read()
            status = response.code
        try:
            decoded = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None
        if status >= 400:
            detail = decoded.get("error") if isinstance(decoded, dict) else decoded
            raise RuntimeError(f"{method} {path}: HTTP {status}: {detail}")
        return decoded, content, status

    def json(self, method: str, path: str, *, payload=None):
        decoded, _, _ = self.call(method, path, payload=payload)
        if not isinstance(decoded, dict):
            raise RuntimeError(f"{method} {path}: expected a JSON object")
        return decoded


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_pid_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_exists(pid):
            return True
        time.sleep(0.1)
    return not pid_exists(pid)


def run_attempt(api: Api, firmware_id: str, attempt_dir: Path, timeout: int,
                poll_timeout: int) -> dict:
    attempt_dir.mkdir()
    created = api.json(
        "POST",
        "/sessions",
        payload={
            "device_id": "core2",
            "firmware_id": firmware_id,
            "ttl_seconds": max(timeout + 30, 120),
        },
    )
    session_id = created["session_id"]
    prefix = "/sessions/" + session_id
    save(attempt_dir / "created.json", created)
    try:
        wait = api.json(
            "POST",
            prefix + "/wait",
            payload={
                "timeout_seconds": timeout,
                "ready": {
                    "serial_markers": [ATECC_MARKER],
                    "frame_nonblank": True,
                    "frame_min_bytes": 1024,
                    "frame_min_nonblack_pixels": 16,
                    "require_all": True,
                },
            },
        )
        save(attempt_dir / "wait.json", wait)

        session = api.json("GET", prefix)
        serial_record = api.json(
            "GET", prefix + "/serial?offset=0&limit=524288"
        )
        serial = serial_record.get("data", serial_record.get("serial", ""))
        if not isinstance(serial, str):
            raise RuntimeError("serial response did not contain text")
        (attempt_dir / "serial.txt").write_text(serial, encoding="utf-8")

        _, frame, _ = api.call("GET", prefix + "/frame.png")
        (attempt_dir / "frame.png").write_bytes(frame)
        _, evidence, _ = api.call(
            "GET",
            prefix + "/evidence?include=manifest,serial,frames,logs,qom",
        )
        (attempt_dir / "evidence.zip").write_bytes(evidence)
        with zipfile.ZipFile(io.BytesIO(evidence)) as archive:
            if archive.testzip():
                raise RuntimeError("evidence ZIP is corrupt")
        qom = api.json("POST", prefix + "/qom-snapshot", payload={})
        save(attempt_dir / "qom.json", qom)
    finally:
        stop = api.json(
            "DELETE", prefix + "?purge=0&retain_flash=0"
        )
        save(attempt_dir / "stop.json", stop)
        stopped = api.json("GET", prefix)
        save(attempt_dir / "stopped.json", stopped)

    pid = stopped.get("pid") or created.get("pid")
    if pid and not wait_pid_gone(pid, poll_timeout):
        raise RuntimeError(f"QEMU PID {pid} remained alive after stop")

    marker_seen = ATECC_MARKER in serial
    forbidden_markers = [
        marker
        for marker in (
            "atcab_init returned",
            "ATECC608 secure element initialization error",
            "abort() was called",
        )
        if marker in serial
    ]
    frame_metrics = wait.get("frame") or {}
    checks = {
        "ready": wait.get("ready") is True,
        "atecc_marker": marker_seen,
        "no_atecc_failure_marker": not forbidden_markers,
        "frame_nonblank": int(frame_metrics.get("nonblack_pixels", 0)) >= 16,
        "frame_colors": int(frame_metrics.get("unique_colors", 0)) >= 2,
        "evidence_zip_valid": True,
        "terminal_stopped": stop.get("state") == "stopped",
        "history_retained": (
            stopped.get("state") == "stopped"
            and stopped.get("firmware_sha256") == firmware_id
        ),
        "pid_gone": not pid or not pid_exists(pid),
        "lease_released": not (stopped.get("worker") or {}).get(
            "lease_active", False
        ),
    }
    return {
        "session_id": session_id,
        "firmware_sha256": session["firmware_sha256"],
        "frame": frame_metrics,
        "frame_png_sha256": sha256_bytes(frame),
        "evidence_sha256": sha256_bytes(evidence),
        "serial_sha256": sha256_bytes(serial.encode("utf-8")),
        "serial_markers": wait.get("serial_markers", []),
        "forbidden_serial_markers": forbidden_markers,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
    }


def run(args) -> int:
    args.out_dir.mkdir(parents=True, exist_ok=False)
    image_sha = sha256_file(args.image)
    if image_sha != SOURCE_SHA256:
        raise SystemExit(
            f"firmware source SHA256 mismatch: {image_sha} != {SOURCE_SHA256}"
        )
    qemu_sha = sha256_file(args.qemu)
    token = (
        args.token_file.read_text(encoding="utf-8").strip()
        if args.token_file
        else ""
    )
    api = Api(args.api, token)
    _, artifact_raw, _ = api.call(
        "POST",
        "/artifacts",
        raw=args.image.read_bytes(),
        headers={
            "Content-Type": "application/octet-stream",
            "X-Artifact-Name": "Core2_For_AWS.bin",
        },
    )
    artifact = json.loads(artifact_raw)
    if artifact.get("artifact_id") != SOURCE_SHA256:
        raise RuntimeError("uploaded firmware artifact ID changed")
    firmware = api.json(
        "POST",
        "/firmware",
        payload={
            "device_id": "core2",
            "kind": "merged",
            "artifact_id": SOURCE_SHA256,
        },
    )
    if firmware.get("firmware_id") != NORMALIZED_SHA256:
        raise RuntimeError("composed Core2 firmware digest changed")

    report = {
        "schema_version": 1,
        "status": "FAIL",
        "validation": "virtual-device validation",
        "hardware_validation": "NOT RUN",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "api": args.api,
        "device_id": "core2",
        "source_artifact_sha256": SOURCE_SHA256,
        "firmware_sha256": NORMALIZED_SHA256,
        "qemu_sha256": qemu_sha,
        "runner_sha256": sha256_file(Path(__file__)),
        "patch_sha256": sha256_file(
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0085-core2-atecc608.patch"
        ),
        "attempts": [],
    }
    for attempt in range(1, args.attempts + 1):
        try:
            row = run_attempt(
                api,
                NORMALIZED_SHA256,
                args.out_dir / f"attempt-{attempt}",
                args.timeout,
                args.poll_timeout,
            )
        except Exception as error:
            row = {"status": "FAIL", "error": str(error)}
        report["attempts"].append(row)
        save(args.out_dir / "report.json", report)
        print(
            json.dumps(
                {
                    "attempt": attempt,
                    "status": row["status"],
                    "session_id": row.get("session_id"),
                    "frame": row.get("frame"),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        if row["status"] != "PASS":
            break

    report["status"] = (
        "PASS"
        if len(report["attempts"]) == args.attempts
        and all(row["status"] == "PASS" for row in report["attempts"])
        else "FAIL"
    )
    save(args.out_dir / "report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "attempts": len(report["attempts"]),
                "report": str(args.out_dir / "report.json"),
            },
            indent=2,
        )
    )
    return 0 if report["status"] == "PASS" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument(
        "--qemu",
        type=Path,
        default=Path(
            os.environ.get(
                "M5_QEMU_XTENSA",
                ROOT
                / ".work/M5StopWatch-QEMU/build/qemu/build/"
                "qemu-system-xtensa",
            )
        ),
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--poll-timeout", type=int, default=15)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be positive")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
