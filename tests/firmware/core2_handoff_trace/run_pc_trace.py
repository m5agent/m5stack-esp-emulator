#!/usr/bin/env python3
"""Trace the Core2 flash/cache handoff setter PCs across a normal boot."""

from __future__ import annotations

import argparse
from bisect import bisect_right
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
EXPECTED_IMAGE_SHA256 = (
    "152127c808b9212e3a5b55dd9e0a2d24e71b902e225452b67db381c76caba1cc"
)
DEFAULT_PCS = (
    0x40087965,
    0x4008797A,
    0x40087A25,
    0x40087B02,
)
HANDOFF_BLOCK_CLEAR_PC = 0x40087965
HANDOFF_BLOCK_READY_PC = 0x4008797A
HANDOFF_FLASH_RELEASE_PC = 0x40087A25
HANDOFF_IPC_RETURN_PC = 0x40087A31
HANDOFF_BLOCK_COMPLETE_PC = 0x40087B02
IPC_TASK_QUEUE_WAIT_PC = 0x400889EE
IPC_TASK_QUEUE_WAKE_PC = 0x400889FB
IPC_TASK_CALLBACK_ENTER_PC = 0x40088A2E
IPC_TASK_CALLBACK_RETURN_PC = 0x40088A31


def first_boot_serial(serial: str) -> str:
    marker = "WDT reset info: APP CPU PC=0x0"
    index = serial.find(marker)
    if index < 0:
        return serial
    end = serial.find("\n", index)
    return serial if end < 0 else serial[: end + 1]


def duration_profile(values: list[int]) -> dict[str, int]:
    if not values:
        return {
            "count": 0,
            "total_ns": 0,
            "mean_ns": 0,
            "p50_ns": 0,
            "p95_ns": 0,
            "max_ns": 0,
        }
    ordered = sorted(values)

    def percentile(fraction: float) -> int:
        index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction)))
        return ordered[index]

    total = sum(ordered)
    return {
        "count": len(ordered),
        "total_ns": total,
        "mean_ns": total // len(ordered),
        "p50_ns": percentile(0.50),
        "p95_ns": percentile(0.95),
        "max_ns": ordered[-1],
    }


def configured_icount_max_percpu_ns() -> int:
    value = os.environ.get(
        "M5SW_ICOUNT_MAX_PERCPU_NS",
        os.environ.get("M5_CORE2_ICOUNT_MAX_PERCPU_NS", "10000"),
    )
    return int(value)


def summarize_handoff_episodes(
    events: list[dict[str, Any]],
    reset_ns: int | None,
) -> dict[str, Any]:
    """Measure each CPU0 flash-block wait using four BIN-bound setter PCs."""
    selected = [
        event
        for event in events
        if event["component"] == "cpu"
        and event["event"] == "pc-trace"
        and event["now_ns"] > 1_000_000_000
        and (reset_ns is None or event["now_ns"] <= reset_ns)
    ]
    block_wait = []
    can_start_latency = []
    can_start_to_complete = []
    complete_to_prepare = []
    prepare_to_block_clear = []
    complete_to_block_clear = []
    clear_ns: int | None = None
    ready_ns: int | None = None
    prepare_ns: int | None = None
    last_complete_ns: int | None = None

    for event in selected:
        now_ns = event["now_ns"]
        pc = event["pc"]
        if pc == HANDOFF_BLOCK_CLEAR_PC:
            if last_complete_ns is not None:
                complete_to_block_clear.append(now_ns - last_complete_ns)
            if prepare_ns is not None:
                prepare_to_block_clear.append(now_ns - prepare_ns)
            clear_ns = now_ns
            ready_ns = None
        elif pc == HANDOFF_BLOCK_READY_PC and clear_ns is not None:
            can_start_latency.append(now_ns - clear_ns)
            ready_ns = now_ns
        elif pc == HANDOFF_FLASH_RELEASE_PC:
            if last_complete_ns is not None:
                complete_to_prepare.append(now_ns - last_complete_ns)
            prepare_ns = now_ns
        elif pc == HANDOFF_BLOCK_COMPLETE_PC and clear_ns is not None:
            block_wait.append(now_ns - clear_ns)
            if ready_ns is not None:
                can_start_to_complete.append(now_ns - ready_ns)
            last_complete_ns = now_ns
            clear_ns = None
            ready_ns = None

    return {
        "events": len(selected),
        "incomplete_blocks": int(clear_ns is not None),
        "block_wait": duration_profile(block_wait),
        "clear_to_can_start": duration_profile(can_start_latency),
        "can_start_to_complete": duration_profile(can_start_to_complete),
        "complete_to_initiator_prepare": duration_profile(
            complete_to_prepare
        ),
        "initiator_prepare_to_block_clear": duration_profile(
            prepare_to_block_clear
        ),
        "complete_to_block_clear": duration_profile(
            complete_to_block_clear
        ),
    }


def summarize_ipc_handoff_phases(
    events: list[dict[str, Any]],
    reset_ns: int | None,
) -> dict[str, Any]:
    """Pair initiator and peer IPC-task phases from BIN-bound PCs."""
    selected = [
        event
        for event in events
        if event["component"] == "cpu"
        and event["event"] == "pc-trace"
        and event["now_ns"] > 1_000_000_000
        and (reset_ns is None or event["now_ns"] <= reset_ns)
    ]
    times: dict[tuple[int, int], list[int]] = {}
    for event in selected:
        times.setdefault((event["cpu"], event["pc"]), []).append(
            event["now_ns"]
        )

    def next_pc(cpu: int, pc: int, after_ns: int) -> int | None:
        values = times.get((cpu, pc), [])
        index = bisect_right(values, after_ns)
        return values[index] if index < len(values) else None

    phase_names = (
        "prepare_to_queue_wake",
        "queue_wake_to_callback_enter",
        "callback_enter_to_block_clear",
        "block_clear_to_can_start",
        "can_start_to_call_return",
        "call_return_to_complete",
        "complete_to_callback_return",
    )
    result: dict[str, Any] = {}
    for initiator in (0, 1):
        peer = 1 - initiator
        durations = {name: [] for name in phase_names}
        incomplete = 0
        prepare_times = times.get(
            (initiator, HANDOFF_FLASH_RELEASE_PC),
            [],
        )
        for prepare_ns in prepare_times:
            queue_wake_ns = next_pc(
                peer, IPC_TASK_QUEUE_WAKE_PC, prepare_ns
            )
            callback_ns = (
                next_pc(peer, IPC_TASK_CALLBACK_ENTER_PC, queue_wake_ns)
                if queue_wake_ns is not None
                else None
            )
            block_clear_ns = (
                next_pc(peer, HANDOFF_BLOCK_CLEAR_PC, callback_ns)
                if callback_ns is not None
                else None
            )
            can_start_ns = (
                next_pc(peer, HANDOFF_BLOCK_READY_PC, block_clear_ns)
                if block_clear_ns is not None
                else None
            )
            call_return_ns = (
                next_pc(initiator, HANDOFF_IPC_RETURN_PC, can_start_ns)
                if can_start_ns is not None
                else None
            )
            complete_ns = (
                next_pc(initiator, HANDOFF_BLOCK_COMPLETE_PC, call_return_ns)
                if call_return_ns is not None
                else None
            )
            callback_return_ns = (
                next_pc(peer, IPC_TASK_CALLBACK_RETURN_PC, complete_ns)
                if complete_ns is not None
                else None
            )
            chain = (
                prepare_ns,
                queue_wake_ns,
                callback_ns,
                block_clear_ns,
                can_start_ns,
                call_return_ns,
                complete_ns,
                callback_return_ns,
            )
            if any(value is None for value in chain[1:]):
                incomplete += 1
                continue
            concrete = [int(value) for value in chain]
            for index, name in enumerate(phase_names):
                durations[name].append(
                    concrete[index + 1] - concrete[index]
                )
        result[f"cpu{initiator}_initiator"] = {
            "prepare_events": len(prepare_times),
            "complete_episodes": len(durations["prepare_to_queue_wake"]),
            "incomplete_episodes": incomplete,
            "queue_wait_events": len(
                times.get((initiator, IPC_TASK_QUEUE_WAIT_PC), [])
            ),
            "phases": {
                name: duration_profile(values)
                for name, values in durations.items()
            },
        }
    return result


def summarize_trace(
    qemu_stderr: str,
    serial: str,
    frame: bytes,
    pcs: tuple[int, ...],
) -> dict[str, Any]:
    events = parse_trace(qemu_stderr)
    pc_events = [
        event
        for event in events
        if event["component"] == "cpu" and event["event"] == "pc-trace"
    ]
    reset_events = [
        event
        for event in events
        if event["component"] == "timg"
        and event["event"] == "wdt-reset"
        and event["now_ns"] > 1_000_000_000
    ]
    timeout_events = [
        event
        for event in events
        if event["component"] == "timg"
        and event["event"] == "wdt-timeout"
        and event["now_ns"] > 1_000_000_000
    ]
    first_reset_ns = (
        min(event["now_ns"] for event in reset_events)
        if reset_events
        else None
    )
    first_boot_events = [
        event
        for event in pc_events
        if first_reset_ns is None or event["now_ns"] <= first_reset_ns
    ]
    counts = {
        f"0x{pc:08x}": sum(event["pc"] == pc for event in first_boot_events)
        for pc in pcs
    }
    first_boot = first_boot_serial(serial)
    complete_count = counts.get("0x40087b02", 0)
    episodes = summarize_handoff_episodes(first_boot_events, first_reset_ns)
    ipc_phases = summarize_ipc_handoff_phases(
        first_boot_events,
        first_reset_ns,
    )
    return {
        "trace_events": len(events),
        "pc_events": len(pc_events),
        "first_boot_pc_events": len(first_boot_events),
        "first_wdt_reset_ns": first_reset_ns,
        "first_wdt_timeout_ns": (
            min(event["now_ns"] for event in timeout_events)
            if timeout_events
            else None
        ),
        "pc_counts": counts,
        "first_boot_first_pc_ns": (
            first_boot_events[0]["now_ns"] if first_boot_events else None
        ),
        "first_boot_last_pc_ns": (
            first_boot_events[-1]["now_ns"] if first_boot_events else None
        ),
        "handoff_episodes": episodes,
        "ipc_handoff_phases": ipc_phases,
        "serial": {
            "bytes": len(serial.encode()),
            "sha256": sha256_bytes(serial.encode()),
            "first_boot_bytes": len(first_boot.encode()),
            "first_boot_sha256": sha256_bytes(first_boot.encode()),
            "has_micropython_banner": "MicroPython" in serial
            or "_   _(_)/ _|" in serial,
            "has_repl_prompt": ">>>" in serial,
            "has_wdt_reset": first_reset_ns is not None,
        },
        "frame": {
            "bytes": len(frame),
            "sha256": sha256_bytes(frame),
            "png": frame.startswith(b"\x89PNG\r\n\x1a\n"),
        },
        "classification": {
            "handoff_cycles": "REPEATED"
            if complete_count > 1
            else "INSUFFICIENT",
            "permanent_deadlock": "NOT SUPPORTED"
            if complete_count > 1
            else "UNKNOWN",
            "legacy_boot": "FAIL" if first_reset_ns is not None else "NOT RUN",
        },
    }


def run(
    image: Path,
    qemu: Path,
    out_dir: Path,
    observe_seconds: float,
    pcs: tuple[int, ...],
    runtime: str,
    icount_shift: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    api = Api(f"http://127.0.0.1:{port}")
    state_dir = out_dir / "service-state"
    env = os.environ.copy()
    env.update(
        {
            "M5_QEMU_XTENSA": str(qemu),
            "M5_CORE2_RADIO_QEMU": str(qemu),
            "M5_CORE2_ICOUNT_SHIFT": icount_shift,
            "M5SW_XTENSA_PC_TRACE": ",".join(f"0x{pc:08x}" for pc in pcs),
            "M5SW_TIMG_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE": "1",
            "M5SW_ESP32_HANDOFF_TRACE_SAMPLE": "1024",
        }
    )
    service_log = (out_dir / "device-service.log").open("wb")
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
        (out_dir / "qemu.stderr").write_text(qemu_stderr)
        (out_dir / "serial.log").write_text(serial)
        (out_dir / "frame.png").write_bytes(frame)
        summary = summarize_trace(qemu_stderr, serial, frame, pcs)
        summary.update(
            {
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
    parser.add_argument("--observe-seconds", type=float, default=20)
    parser.add_argument(
        "--pc",
        action="append",
        type=lambda value: int(value, 0),
        default=None,
    )
    parser.add_argument(
        "--ipc-phases",
        action="store_true",
        help="add BIN-bound ipc_task dispatch and return PCs",
    )
    parser.add_argument(
        "--expected-image-sha256",
        default=EXPECTED_IMAGE_SHA256,
    )
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
    image_sha256 = sha256_file(args.image)
    if image_sha256 != args.expected_image_sha256.lower():
        parser.error(
            f"image SHA256 mismatch: expected "
            f"{args.expected_image_sha256}, got {image_sha256}"
        )
    if args.observe_seconds < 2 or args.observe_seconds > 120:
        parser.error("--observe-seconds must be from 2 to 120")
    pcs = list(args.pc or DEFAULT_PCS)
    if args.ipc_phases:
        for pc in (
            0x400889C4,
            IPC_TASK_QUEUE_WAIT_PC,
            IPC_TASK_QUEUE_WAKE_PC,
            IPC_TASK_CALLBACK_ENTER_PC,
            HANDOFF_IPC_RETURN_PC,
            IPC_TASK_CALLBACK_RETURN_PC,
        ):
            if pc not in pcs:
                pcs.append(pc)
    pcs = tuple(pcs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    summary = run(
        args.image,
        args.qemu,
        args.out_dir,
        args.observe_seconds,
        pcs,
        args.runtime,
        args.icount_shift,
    )
    evidence = {
        "schema_version": 1,
        "kind": "core2-handoff-pc-trace",
        "validation": "virtual-device validation",
        "status": "DIAGNOSTIC",
        "firmware": {
            "name": "UIFlow_Core2 v1.15.4",
            "normalized_flash_sha256": image_sha256,
            "bytes": args.image.stat().st_size,
        },
        "runtime": {
            "machine": "m5core2",
            "qemu_binary_sha256": sha256_file(args.qemu),
            "pc_trace": [f"0x{pc:08x}" for pc in pcs],
            "observe_seconds": args.observe_seconds,
            "runtime": args.runtime,
            "icount_shift": (
                args.icount_shift if args.runtime == "qemu-wifi" else None
            ),
            "icount_max_percpu_ns": (
                configured_icount_max_percpu_ns()
                if args.runtime == "qemu-wifi"
                else None
            ),
        },
        "summary": summary,
        "boundaries": [
            "Only virtual-device validation.",
            "The PC list is BIN-bound and does not imply matching ELF symbols.",
            "Repeated handoff completion does not prove physical cache timing.",
            "A watchdog reset under this execution model is not a hardware result.",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={evidence_path}")
    return 0 if summary["classification"]["handoff_cycles"] == "REPEATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
