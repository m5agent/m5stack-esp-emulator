#!/usr/bin/env python3
"""Collect exact-time Core2 handoff state through isolated Device Service leases."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVE = ROOT / "platform/tools/serve.py"
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
EXPECTED_IMAGE_SHA256 = (
    "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc"
)
TRACE_PATTERN = re.compile(
    r"^\[esp32-handoff\] now=(?P<now>\d+) "
    r"cpu=(?P<cpu>-?\d+) pc=(?P<pc>[0-9a-fA-F]+) "
    r"component=(?P<component>\S+) event=(?P<event>\S+) "
    r"a=(?P<a>[0-9a-fA-F]+) b=(?P<b>[0-9a-fA-F]+) "
    r"c=(?P<c>[0-9a-fA-F]+) d=(?P<d>[0-9a-fA-F]+)$"
)


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        headers = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {detail}"
            ) from error

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        data = None
        content_type = None
        if payload is not None:
            data = json.dumps(payload).encode()
            content_type = "application/json"
        status, body, _ = self.request(
            path,
            method=method,
            data=data,
            content_type=content_type,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(api: Api, process: subprocess.Popen, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Device Service exited during startup with {process.returncode}"
            )
        try:
            status, _, _ = api.request("/api/health", timeout=2)
            if status == 200:
                return
        except (OSError, RuntimeError, urllib.error.URLError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Device Service did not become healthy")


def parse_trace(text: str) -> list[dict[str, Any]]:
    events = []
    for line in text.splitlines():
        match = TRACE_PATTERN.match(line)
        if not match:
            continue
        fields = match.groupdict()
        events.append(
            {
                "now_ns": int(fields["now"]),
                "cpu": int(fields["cpu"]),
                "pc": int(fields["pc"], 16),
                "component": fields["component"],
                "event": fields["event"],
                "a": fields["a"],
                "b": fields["b"],
                "c": fields["c"],
                "d": fields["d"],
            }
        )
    return events


def snapshot_at_pause(
    stderr: str,
    target_ns: int,
    tolerance_ns: int,
) -> dict[str, Any]:
    events = parse_trace(stderr)
    pauses = [
        event
        for event in events
        if event["component"] == "cpu" and event["event"] == "pause"
    ]
    if not pauses:
        raise RuntimeError("QEMU did not emit an exact-time pause marker")
    pause = pauses[-1]
    if abs(pause["now_ns"] - target_ns) > tolerance_ns:
        raise RuntimeError(
            f"pause marker missed target by "
            f"{abs(pause['now_ns'] - target_ns)} ns"
        )
    same_time = [
        event for event in events if event["now_ns"] == pause["now_ns"]
    ]
    cpu = {}
    memory = {}
    dport = {}
    io = {}
    registers: dict[str, dict[str, str]] = {}
    points: dict[str, dict[str, str]] = {}
    stack_words: list[dict[str, Any]] = []
    for event in same_time:
        if event["component"] == "cpu" and event["event"] == "freeze":
            cpu[str(event["cpu"])] = {
                "pc": f"0x{event['pc']:08x}",
                "interrupt_request": f"0x{int(event['a'], 16):08x}",
                "state_flags": int(event["b"], 10),
            }
        elif event["component"] == "cpu" and event["event"] == "freeze-reg":
            registers[str(event["cpu"])] = {
                "a0": f"0x{int(event['a'], 16):08x}",
                "a1": f"0x{int(event['b'], 16):08x}",
                "ps": f"0x{int(event['c'], 16):08x}",
            }
        elif event["component"] == "cpu" and event["event"].startswith(
            "freeze-reg"
        ):
            key = str(event["cpu"])
            base = int(event["event"].removeprefix("freeze-reg"))
            values = registers.setdefault(key, {})
            fields = ("a", "b") if base == 14 else ("a", "b", "c", "d")
            for offset, field in enumerate(fields):
                values[f"a{base + offset}"] = (
                    f"0x{int(event[field], 16):08x}"
                )
        elif event["component"] == "mem" and event["event"] == "freeze-point":
            points[f"0x{int(event['a'], 16):08x}"] = {
                "value": f"0x{int(event['b'], 16):08x}",
                "offset24": f"0x{int(event['c'], 16):08x}",
                "offset28": f"0x{int(event['d'], 16):08x}",
            }
        elif event["component"] == "mem" and event["event"] == "stack-word":
            stack_words.append(
                {
                    "cpu": int(event["c"], 10),
                    "index": int(event["d"], 10),
                    "address": f"0x{int(event['a'], 16):08x}",
                    "value": f"0x{int(event['b'], 16):08x}",
                }
            )
        elif event["component"] == "mem" and event["event"] in {
            "freeze-byte",
            "freeze-word",
        }:
            memory[f"0x{int(event['a'], 16):08x}"] = (
                f"0x{int(event['b'], 16):02x}"
                if event["event"] == "freeze-byte"
                else f"0x{int(event['b'], 16):08x}"
            )
        elif event["component"] == "dport" and event["event"].startswith(
            "freeze-"
        ):
            if event["event"].startswith("freeze-state"):
                dport[event["event"]] = {
                    "a": int(event["a"], 10),
                    "b": int(event["b"], 10),
                    "c": f"0x{int(event['c'], 16):08x}",
                    "d": f"0x{int(event['d'], 16):08x}",
                }
            else:
                dport[event["event"]] = {
                    "a": int(event["a"], 10),
                    "b": int(event["b"], 10),
                    "c": int(event["c"], 10),
                    "d": int(event["d"], 10),
                }
        elif event["component"] in {"ssi", "crosscore"} and event[
            "event"
        ].startswith("freeze-"):
            io[f"{event['component']}:{event['event']}"] = {
                "a": int(event["a"], 10),
                "b": int(event["b"], 10),
                "c": int(event["c"], 10),
                "d": int(event["d"], 10),
            }
    required_memory = {
        "0x3ffc7ec8",
        "0x3ffc7ec9",
        "0x3ffc7750",
        "0x3ffc7754",
    }
    if set(cpu) != {"0", "1"}:
        raise RuntimeError(f"incomplete CPU state: {sorted(cpu)}")
    if not required_memory.issubset(memory):
        raise RuntimeError(
            "incomplete memory state: "
            f"missing {sorted(required_memory - set(memory))}"
        )
    if "freeze-state" not in dport:
        raise RuntimeError("missing DPORT freeze state")
    if "ssi:freeze-counters" not in io:
        raise RuntimeError("missing SSI freeze counters")
    snapshot = {
        "pause_target_ns": target_ns,
        "pause_event_ns": pause["now_ns"],
        "pause_delta_ns": pause["now_ns"] - target_ns,
        "cpu": cpu,
        "memory": memory,
        "dport": dport,
        "io": io,
    }
    if registers:
        snapshot["registers"] = registers
    if points:
        snapshot["points"] = points
    if stack_words:
        snapshot["stack_words"] = sorted(
            stack_words,
            key=lambda item: (item["cpu"], item["index"]),
        )
    return snapshot


def stop_service(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_target(
    image: Path,
    qemu: Path,
    out_dir: Path,
    target_ns: int,
    attempt: int,
    runtime: str,
    icount_shift: str,
    timeout: float,
    tolerance_ns: int,
    disable_wdt: bool,
) -> dict[str, Any]:
    run_dir = out_dir / f"pause-{target_ns}-attempt-{attempt}"
    run_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    base_url = f"http://127.0.0.1:{port}"
    api = Api(base_url)
    env = os.environ.copy()
    env.update(
        {
            "M5_QEMU_XTENSA": str(qemu),
            "M5_CORE2_RADIO_QEMU": str(qemu),
            "M5_CORE2_ICOUNT_SHIFT": icount_shift,
            "M5SW_ESP32_HANDOFF_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE_SAMPLE": "1024",
            "M5SW_ESP32_HANDOFF_PAUSE_NS": str(target_ns),
            "M5SW_ESP32_HANDOFF_DUMP_STATE": "1",
            "M5SW_ESP32_HANDOFF_PAUSE_ACTION": "exit",
        }
    )
    if disable_wdt:
        env["M5SW_DISABLE_WDT"] = "1"
    else:
        env.pop("M5SW_DISABLE_WDT", None)
    service_log = (run_dir / "device-service.log").open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVE),
            str(port),
            "--bind",
            "127.0.0.1",
            "--state-dir",
            str(run_dir / "service-state"),
            "--max-sessions",
            "1",
            "--max-per-device",
            "1",
            "--session-ttl",
            "180",
        ],
        cwd=ROOT,
        env=env,
        stdout=service_log,
        stderr=subprocess.STDOUT,
    )
    session_id = ""
    try:
        wait_for_health(api, process, timeout=10)
        status, body, _ = api.request(
            "/api/v1/artifacts",
            method="POST",
            data=image.read_bytes(),
            content_type="application/octet-stream",
            timeout=120,
        )
        artifact = json.loads(body)
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        firmware = api.json(
            "/api/v1/firmware",
            method="POST",
            payload={
                "device_id": "core2",
                "kind": "merged",
                "artifact_id": artifact["artifact_id"],
            },
        )
        session_payload: dict[str, Any] = {
            "device_id": "core2",
            "firmware_id": firmware["firmware_id"],
            "runtime": runtime,
            "ttl_seconds": 180,
        }
        if runtime == "qemu-wifi":
            session_payload["network"] = {
                "profile": "core2-openmac",
                "net_mode": "user",
                "expected_markers": [],
            }
        created = api.json(
            "/api/v1/sessions",
            method="POST",
            payload=session_payload,
        )
        session_id = str(created["session_id"])

        deadline = time.monotonic() + timeout
        logs: dict[str, Any] = {}
        stderr = ""
        while time.monotonic() < deadline:
            logs = api.json(
                f"/api/v1/sessions/{session_id}/logs"
                "?offset=0&limit=1048576"
            )
            stderr = str(logs.get("qemu_stderr") or "")
            if "component=mem event=freeze-byte" in stderr:
                break
            state = str(
                api.json(f"/api/v1/sessions/{session_id}").get("state")
            )
            if state in {"failed", "stopped"} and stderr:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("timed out waiting for exact-time state dump")

        (run_dir / "qemu.stderr").write_text(stderr)
        serial = str(logs.get("data") or "")
        (run_dir / "serial.log").write_text(serial)
        events = api.json(f"/api/v1/sessions/{session_id}/events")
        (run_dir / "events.json").write_text(
            json.dumps(events, indent=2) + "\n"
        )
        snapshot = snapshot_at_pause(stderr, target_ns, tolerance_ns)
        snapshot.update(
            {
                "attempt": attempt,
                "runtime": runtime,
                "icount_shift": icount_shift,
                "wdt_disabled": disable_wdt,
                "session_id_sha256": sha256_bytes(session_id.encode()),
                "qemu_stderr_sha256": sha256_bytes(stderr.encode()),
                "serial_bytes": len(serial.encode()),
                "serial_sha256": sha256_bytes(serial.encode()),
            }
        )
        return snapshot
    finally:
        if session_id:
            session_dir = run_dir / "service-state" / "sessions" / session_id
            for name in ("qemu.stderr", "serial.log", "session.json"):
                source = session_dir / name
                destination = run_dir / name
                if source.is_file() and not destination.exists():
                    shutil.copy2(source, destination)
            try:
                api.json(
                    f"/api/v1/sessions/{session_id}?purge=0",
                    method="DELETE",
                    payload={},
                )
            except Exception:
                pass
        stop_service(process)
        service_log.close()
        shutil.rmtree(run_dir / "service-state", ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument(
        "--pause-seconds",
        type=float,
        action="append",
        required=True,
        help="repeat for each exact virtual-time freeze",
    )
    parser.add_argument(
        "--expected-image-sha256",
        default=EXPECTED_IMAGE_SHA256,
    )
    parser.add_argument("--timeout-seconds", type=float, default=45)
    parser.add_argument("--pause-tolerance-ms", type=float, default=5)
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--disable-wdt", action="store_true")
    parser.add_argument(
        "--runtime",
        choices=("qemu", "qemu-wifi"),
        default="qemu",
    )
    parser.add_argument(
        "--icount-shift",
        choices=("auto", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"),
        default="5",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")
    if not args.qemu.is_file():
        parser.error(f"QEMU does not exist: {args.qemu}")
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    image_sha256 = sha256_file(args.image)
    if image_sha256 != args.expected_image_sha256.lower():
        parser.error(
            f"image SHA256 mismatch: expected "
            f"{args.expected_image_sha256}, got {image_sha256}"
        )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    targets = sorted({round(value, 9) for value in args.pause_seconds})
    snapshots = []
    failures = []
    for seconds in targets:
        target_ns = int(round(seconds * 1_000_000_000))
        for attempt in range(1, args.attempts + 1):
            try:
                snapshot = run_target(
                    args.image,
                    args.qemu,
                    args.out_dir,
                    target_ns,
                    attempt,
                    args.runtime,
                    args.icount_shift,
                    args.timeout_seconds,
                    int(args.pause_tolerance_ms * 1_000_000),
                    args.disable_wdt,
                )
                snapshots.append(snapshot)
                print(
                    f"PAUSE {seconds:.6f}s attempt={attempt} "
                    f"cpu0={snapshot['cpu']['0']['pc']} "
                    f"cpu1={snapshot['cpu']['1']['pc']}"
                )
            except Exception as error:
                failures.append(
                    {
                        "pause_target_ns": target_ns,
                        "attempt": attempt,
                        "error": str(error),
                    }
                )
                print(
                    f"PAUSE {seconds:.6f}s attempt={attempt} FAILED: {error}",
                    file=sys.stderr,
                )

    evidence = {
        "schema_version": 1,
        "kind": "core2-handoff-pause-sweep",
        "validation": "virtual-device validation",
        "status": "PASS" if snapshots and not failures else (
            "PARTIAL" if snapshots else "FAIL"
        ),
        "firmware": {
            "name": "UIFlow_Core2 v1.15.4",
            "normalized_flash_sha256": image_sha256,
            "bytes": args.image.stat().st_size,
        },
        "runtime": {
            "machine": "m5core2",
            "qemu_binary_sha256": sha256_file(args.qemu),
            "trace_sample": 1024,
            "pc_sampling": "NOT RUN",
            "runtime": args.runtime,
            "icount_shift": (
                args.icount_shift if args.runtime == "qemu-wifi" else None
            ),
            "pause_action": "exit",
            "wdt_disabled": args.disable_wdt,
            "attempts_per_target": args.attempts,
            "pause_tolerance_ns": int(
                args.pause_tolerance_ms * 1_000_000
            ),
        },
        "snapshots": snapshots,
        "failures": failures,
        "classification": {
            "uart_storm": "REJECTED",
            "guest_deadlock": "NOT PROVEN",
            "application_frame": "NOT RUN",
        },
        "boundaries": [
            "Only virtual-device validation.",
            "The state dump reads SRAM and DPORT model state at the pause boundary.",
            "Exact-time CPU register snapshots do not prove a permanent deadlock.",
            "No physical cache, PSRAM, Flash, RF, electrical or hardware validation is claimed.",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"evidence={evidence_path}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
