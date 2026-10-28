#!/usr/bin/env python3
"""Reconcile Core2 bootloader and task-WDT liveness before reset."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from run_pause_sweep import (
    Api,
    EXPECTED_IMAGE_SHA256,
    SERVE,
    free_port,
    parse_trace,
    sha256_bytes,
    sha256_file,
    stop_service,
    wait_for_health,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_QEMU = (
    ROOT
    / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
TG1_FEED_LIVE_GAP_NS = 10_000_000
TG1_FEED_MAX_GAP_NS = 100_000_000


def _event_u64(event: dict[str, Any], key: str) -> int:
    return int(str(event[key]), 10)


def _wdt_events(stderr: str) -> list[dict[str, Any]]:
    return [
        event
        for event in parse_trace(stderr)
        if event["component"] == "timg"
    ]


def _first_post_boot_reset(events: list[dict[str, Any]]) -> int | None:
    resets = [
        event["now_ns"]
        for event in events
        if event["event"] == "wdt-reset" and event["now_ns"] > 1_000_000_000
    ]
    return min(resets) if resets else None


def _tg1_feed_times_before_reset(
    lines: list[str],
    reset_line: int,
) -> tuple[list[int], list[int]]:
    feed_times: list[int] = []
    feed_lines: list[int] = []
    pending_feed = False
    for line_index, line in enumerate(lines[:reset_line]):
        if line == "[esp32-timg] TG1 WDTFEED":
            pending_feed = True
            continue
        if not pending_feed or not line.startswith("[esp32-timg] TG1 arm now="):
            continue
        try:
            now_ns = int(line.split(" now=", 1)[1].split(" ", 1)[0])
        except (IndexError, ValueError):
            continue
        feed_times.append(now_ns)
        feed_lines.append(line_index)
        pending_feed = False
    return feed_times, feed_lines


def summarize_wdt_liveness(
    stderr: str,
    serial: str,
    frame: bytes,
) -> dict[str, Any]:
    events = _wdt_events(stderr)
    lines = stderr.splitlines()
    first_reset_ns = _first_post_boot_reset(events)

    timeouts = [
        event
        for event in events
        if event["event"] == "wdt-timeout"
        and event["now_ns"] > 1_000_000_000
        and (first_reset_ns is None or event["now_ns"] <= first_reset_ns)
    ]
    first_tg0_stage0 = next(
        (
            event
            for event in timeouts
            if _event_u64(event, "a") == 0
            and _event_u64(event, "b") == 0
        ),
        None,
    )
    first_tg0_stage1 = next(
        (
            event
            for event in timeouts
            if _event_u64(event, "a") == 0
            and _event_u64(event, "b") == 1
        ),
        None,
    )
    tg1_timeouts = [
        event for event in timeouts if _event_u64(event, "a") == 1
    ]
    first_tg0_stage0_gap = None
    if first_tg0_stage0 is not None:
        first_tg0_stage0_gap = next(
            (
                event
                for event in events
                if event["event"] == "wdt-timeout-gap"
                and _event_u64(event, "a") == 0
                and _event_u64(event, "b") == 0
                and first_tg0_stage0["now_ns"]
                <= event["now_ns"]
                <= first_tg0_stage0["now_ns"] + 100_000
            ),
            None,
        )
    masked_after_stage0 = []
    if first_tg0_stage0 is not None:
        masked_after_stage0 = [
            event
            for event in events
            if event["event"] == "wdt-int-masked"
            and first_tg0_stage0["now_ns"]
            <= event["now_ns"]
            <= first_tg0_stage0["now_ns"] + 100_000
            and _event_u64(event, "a") == 0
        ]

    stage0_timeout_line = next(
        (
            index
            for index, line in enumerate(lines)
            if first_tg0_stage0 is not None
            and line.startswith("[esp32-timg] TG0 timeout now=")
            and " stage=0 " in line
            and first_tg0_stage0["now_ns"]
            <= int(line.split(" now=", 1)[1].split(" ", 1)[0])
            <= first_tg0_stage0["now_ns"] + 1_000_000
        ),
        None,
    )
    reset_line = next(
        (
            index
            for index, line in enumerate(lines)
            if first_reset_ns is not None
            and line.startswith("[esp32-timg] TG0 reset ")
            and index >= (stage0_timeout_line or 0)
        ),
        len(lines),
    )

    feed_times, _ = _tg1_feed_times_before_reset(lines, reset_line)
    feed_intervals = [
        later - earlier
        for earlier, later in zip(feed_times, feed_times[1:])
    ]
    last_feed_ns = feed_times[-1] if feed_times else None
    last_feed_gap_ns = (
        first_reset_ns - last_feed_ns
        if first_reset_ns is not None and last_feed_ns is not None
        else None
    )

    tg0_activity_after_stage0 = []
    if stage0_timeout_line is not None:
        for line in lines[stage0_timeout_line + 1 : reset_line]:
            if line.startswith(
                (
                    "[esp32-timg] TG0 WDTFEED",
                    "[esp32-timg] TG0 feed ",
                    "[esp32-timg] TG0 WDTCONFIG",
                    "[esp32-timg] TG0 WDTPROTECT",
                )
            ):
                tg0_activity_after_stage0.append(line)

    if first_reset_ns is None:
        classification = "INCOMPLETE_NO_BOOT_RESET"
    elif tg1_timeouts:
        classification = "TG1_INTERRUPT_WDT_BEFORE_RESET"
    elif (
        last_feed_gap_ns is not None
        and last_feed_gap_ns <= TG1_FEED_LIVE_GAP_NS
        and (not feed_intervals or max(feed_intervals) <= TG1_FEED_MAX_GAP_NS)
    ):
        classification = "BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE"
    else:
        classification = "TG1_FEED_STALLED_BEFORE_TG0_RESET"

    return {
        "first_boot_reset_ns": first_reset_ns,
        "tg0": {
            "stage0_timeout_ns": (
                first_tg0_stage0["now_ns"] if first_tg0_stage0 else None
            ),
            "stage0_feed_gap_ns": (
                _event_u64(first_tg0_stage0_gap, "c")
                if first_tg0_stage0_gap
                else None
            ),
            "stage0_feed_count": (
                _event_u64(first_tg0_stage0_gap, "d")
                if first_tg0_stage0_gap
                else None
            ),
            "stage0_interrupt_masked": bool(masked_after_stage0),
            "stage1_timeout_ns": (
                first_tg0_stage1["now_ns"] if first_tg0_stage1 else None
            ),
            "reconfigure_feed_or_protect_after_stage0": len(
                tg0_activity_after_stage0
            ),
        },
        "tg1": {
            "feed_count_before_reset": len(feed_times),
            "first_feed_ns": feed_times[0] if feed_times else None,
            "last_feed_ns": last_feed_ns,
            "last_feed_gap_to_reset_ns": last_feed_gap_ns,
            "max_feed_interval_ns": (
                max(feed_intervals) if feed_intervals else None
            ),
            "intervals_over_100ms": sum(
                interval > TG1_FEED_MAX_GAP_NS
                for interval in feed_intervals
            ),
            "timeout_count_before_reset": len(tg1_timeouts),
        },
        "serial": {
            "bytes": len(serial.encode()),
            "sha256": sha256_bytes(serial.encode()),
            "has_micropython_banner": "MicroPython" in serial
            or "_   _(_)/ _|" in serial,
            "has_repl_prompt": ">>>" in serial,
        },
        "frame": {
            "bytes": len(frame),
            "sha256": sha256_bytes(frame),
            "png": frame.startswith(b"\x89PNG\r\n\x1a\n"),
        },
        "classification": classification,
    }


def run_once(
    image: Path,
    qemu: Path,
    out_dir: Path,
    attempt: int,
    observe_seconds: float,
    runtime: str,
    icount_shift: str,
    trace_sample: int,
) -> dict[str, Any]:
    run_dir = out_dir / f"attempt-{attempt}"
    run_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    api = Api(f"http://127.0.0.1:{port}")
    state_dir = run_dir / "service-state"
    env = os.environ.copy()
    env.update(
        {
            "M5_QEMU_XTENSA": str(qemu),
            "M5_CORE2_RADIO_QEMU": str(qemu),
            "M5_CORE2_ICOUNT_SHIFT": icount_shift,
            "M5SW_TIMG_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE_SAMPLE": str(trace_sample),
        }
    )
    service_log = (run_dir / "device-service.log").open("wb")
    process = subprocess.Popen(
        [
            sys.executable,
            str(SERVE),
            str(port),
            "--bind",
            "127.0.0.1",
            "--state-dir",
            str(state_dir),
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
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        artifact = json.loads(body)
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
        time.sleep(observe_seconds)
        try:
            status, frame, _ = api.request(
                f"/api/v1/sessions/{session_id}/frame.png",
                timeout=30,
            )
        except RuntimeError:
            status = 0
            frame = b""
        if status != 200:
            frame = b""
        session_dir = state_dir / "sessions" / session_id
        qemu_stderr = (session_dir / "qemu.stderr").read_text(
            errors="replace"
        )
        serial = (session_dir / "serial.log").read_text(errors="replace")
        (run_dir / "qemu.stderr").write_text(qemu_stderr)
        (run_dir / "serial.log").write_text(serial)
        (run_dir / "frame.png").write_bytes(frame)
        summary = summarize_wdt_liveness(qemu_stderr, serial, frame)
        summary.update(
            {
                "attempt": attempt,
                "session_id_sha256": sha256_bytes(session_id.encode()),
                "qemu_stderr_sha256": sha256_bytes(qemu_stderr.encode()),
            }
        )
        return summary
    finally:
        if session_id:
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
        shutil.rmtree(state_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument(
        "--expected-image-sha256",
        default=EXPECTED_IMAGE_SHA256,
        help="exact normalized image SHA256 pin",
    )
    parser.add_argument("--observe-seconds", type=float, default=18)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--trace-sample", type=int, default=1024)
    parser.add_argument(
        "--runtime",
        choices=("qemu", "qemu-wifi"),
        default="qemu",
    )
    parser.add_argument(
        "--icount-shift",
        choices=(
            "auto",
            "0",
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
            "9",
            "10",
        ),
        default="5",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if not args.image.is_file():
        parser.error(f"image does not exist: {args.image}")
    if not args.qemu.is_file():
        parser.error(f"QEMU does not exist: {args.qemu}")
    if not 2 <= args.observe_seconds <= 120:
        parser.error("--observe-seconds must be from 2 to 120")
    if not 1 <= args.attempts <= 10:
        parser.error("--attempts must be from 1 to 10")
    if not 1 <= args.trace_sample <= 1_000_000:
        parser.error("--trace-sample must be from 1 to 1000000")
    image_sha256 = sha256_file(args.image)
    if image_sha256 != args.expected_image_sha256.lower():
        parser.error(
            f"image SHA256 mismatch: expected "
            f"{args.expected_image_sha256}, got {image_sha256}"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    failures = []
    for attempt in range(1, args.attempts + 1):
        try:
            run = run_once(
                args.image,
                args.qemu,
                args.out_dir,
                attempt,
                args.observe_seconds,
                args.runtime,
                args.icount_shift,
                args.trace_sample,
            )
        except Exception as error:
            failures.append({"attempt": attempt, "error": str(error)})
            print(f"WDT attempt {attempt} FAILED: {error}", file=sys.stderr)
            continue
        runs.append(run)
        print(
            f"WDT attempt {attempt} "
            f"classification={run['classification']} "
            f"last_tg1_gap={run['tg1']['last_feed_gap_to_reset_ns']} "
            f"tg1_timeouts={run['tg1']['timeout_count_before_reset']}"
        )

    classifications = sorted(
        {run["classification"] for run in runs}
    )
    status = (
        "PASS"
        if runs
        and not failures
        and classifications
        == ["BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE"]
        else "PARTIAL"
        if runs
        else "FAIL"
    )
    evidence = {
        "schema_version": 1,
        "kind": "core2-wdt-liveness",
        "validation": "virtual-device validation",
        "status": status,
        "firmware": {
            "name": "UIFlow_Core2 v1.15.4",
            "normalized_flash_sha256": image_sha256,
            "bytes": args.image.stat().st_size,
        },
        "runtime": {
            "machine": "m5core2",
            "qemu_binary_sha256": sha256_file(args.qemu),
            "observe_seconds": args.observe_seconds,
            "attempts": args.attempts,
            "runtime": args.runtime,
            "icount_shift": (
                args.icount_shift if args.runtime == "qemu-wifi" else None
            ),
            "pc_trace": "NOT RUN",
            "timg_verbose_trace": "ENABLED",
            "trace_sample": args.trace_sample,
            "tg1_live_gap_limit_ns": TG1_FEED_LIVE_GAP_NS,
            "tg1_max_gap_limit_ns": TG1_FEED_MAX_GAP_NS,
        },
        "runs": runs,
        "failures": failures,
        "classification": {
            "classifications": classifications,
            "tg1_feed_liveness": (
                "LIVE_UNTIL_TG0_STAGE1_RESET"
                if status == "PASS"
                else "MIXED_OR_INCOMPLETE"
            ),
            "single_tg1_800ms_gap": (
                "NOT_REPRODUCED"
                if status == "PASS"
                else "NOT_ESTABLISHED"
            ),
            "legacy_boot": "FAIL",
        },
        "boundaries": [
            "Only virtual-device validation.",
            "TG1 feed liveness does not prove physical watchdog timing.",
            "The exact-time trace is enabled; results do not claim zero perturbation.",
            "No REPL or non-empty application frame is evidence of a successful boot.",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"evidence={evidence_path}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
