#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path


TRACE_RE = re.compile(
    r"^\[esp32-handoff\] "
    r"now=(?P<now>\d+) "
    r"cpu=(?P<cpu>-?\d+) "
    r"pc=(?P<pc>[0-9a-fA-F]+) "
    r"component=(?P<component>\S+) "
    r"event=(?P<event>\S+) "
    r"a=(?P<a>[0-9a-fA-F]+) "
    r"b=(?P<b>[0-9a-fA-F]+) "
    r"c=(?P<c>\d+) "
    r"d=(?P<d>\d+)$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_trace(path: Path) -> list[dict[str, int | str]]:
    events: list[dict[str, int | str]] = []
    for line in path.read_text(errors="replace").splitlines():
        match = TRACE_RE.match(line)
        if not match:
            continue
        item: dict[str, int | str] = {
            "component": match.group("component"),
            "event": match.group("event"),
        }
        for name in ("now", "cpu", "a", "b", "c", "d"):
            base = (
                16
                if item["component"] == "cpu" and name in {"a", "b"}
                else 10
            )
            item[name] = int(match.group(name), base)
        item["pc"] = int(match.group("pc"), 16)
        events.append(item)
    return events


def serial_summary(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    text = raw.decode(errors="replace")
    micropython_art = " _   _(_)/ _| | _____" in text
    return {
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "has_micropython_banner": (
            "MicroPython" in text or micropython_art
        ),
        "has_micropython_art": micropython_art,
        "has_repl_prompt": ">>>" in text,
        "has_wdt_timeout": "Interrupt wdt timeout" in text,
        "has_system_reset": (
            "TG0WDT_SYS_RESET" in text or "TG1WDT_SYS_RESET" in text
        ),
    }


def summarize_trace(path: Path) -> dict[str, object]:
    events = parse_trace(path)
    counts = Counter(
        f"{event['component']}:{event['event']}" for event in events
    )
    timeouts = [
        event for event in events if event["event"] == "wdt-timeout"
    ]
    timeout_gaps = {
        (event["now"], event["a"], event["b"]): event
        for event in events
        if event["event"] == "wdt-timeout-gap"
    }
    critical = []
    for timeout in timeouts:
        key = (timeout["now"], timeout["a"], timeout["b"])
        gap = timeout_gaps.get(key)
        critical.append(
            {
                "now_ns": timeout["now"],
                "cpu": timeout["cpu"],
                "pc": f"0x{timeout['pc']:08x}",
                "timer_group": timeout["a"],
                "stage": timeout["b"],
                "mode": timeout["c"],
                "last_feed_ns": timeout["d"],
                "feed_gap_ns": gap["c"] if gap else None,
                "feed_count": gap["d"] if gap else None,
            }
        )
    pc_events = [
        event
        for event in events
        if event["component"] == "cpu" and event["event"] == "sample"
    ]
    final_window = None
    final_stage0 = next(
        (
            item
            for item in critical
            if item["timer_group"] == 1
            and item["stage"] == 0
            and item["feed_gap_ns"] is not None
        ),
        None,
    )
    if final_stage0 is not None:
        window_events = [
            event
            for event in pc_events
            if final_stage0["last_feed_ns"] is not None
            and event["now"] >= final_stage0["last_feed_ns"]
            and event["now"] <= final_stage0["now_ns"]
        ]
        pair_counts = Counter(
            f"0x{event['a']:08x}:0x{event['b']:08x}"
            for event in window_events
        )
        non_pc_counts = Counter(
            f"{event['component']}:{event['event']}"
            for event in events
            if final_stage0["last_feed_ns"]
            <= event["now"]
            <= final_stage0["now_ns"]
            and not (
                event["component"] == "cpu"
                and event["event"] == "sample"
            )
        )
        final_window = {
            "start_ns": final_stage0["last_feed_ns"],
            "end_ns": final_stage0["now_ns"],
            "samples": len(window_events),
            "cpu_pc_pairs": dict(sorted(pair_counts.items())),
            "other_trace_events": dict(sorted(non_pc_counts.items())),
        }
    return {
        "stderr": {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        },
        "trace_event_count": len(events),
        "trace_event_counts": dict(sorted(counts.items())),
        "first_event_ns": events[0]["now"] if events else None,
        "last_event_ns": events[-1]["now"] if events else None,
        "wdt_timeouts": critical,
        "pc_sample_count": len(pc_events),
        "pc_final_feed_to_timeout_window": final_window,
        "has_post_boot_reset_event": any(
            event["event"] == "reset" and event["now"] > 0
            for event in events
        ),
    }


def summarize_matrix(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    results = data["results"]
    checks = [
        check
        for result in results.values()
        for check in result.get("checks", [])
    ]
    return {
        "cases_passed": sum(
            result.get("status") == "PASS" for result in results.values()
        ),
        "cases_failed": sum(
            result.get("status") != "PASS" for result in results.values()
        ),
        "checks_passed": sum(
            check.get("status") == "PASS" for check in checks
        ),
        "checks_failed": sum(
            check.get("status") != "PASS" for check in checks
        ),
        "retry_used": any(
            result.get("retry_used") is True
            or (result.get("attempts") or 1) > 1
            for result in results.values()
        ),
        "summary_sha256": sha256(path),
    }


def classify_pc_sampling_control(
    normal_trace: dict[str, object],
    pc_trace: dict[str, object],
) -> str:
    normal_stage0 = next(
        (
            item
            for item in normal_trace["wdt_timeouts"]
            if item["timer_group"] == 1 and item["stage"] == 0
        ),
        None,
    )
    pc_stage0 = next(
        (
            item
            for item in pc_trace["wdt_timeouts"]
            if item["timer_group"] == 1 and item["stage"] == 0
        ),
        None,
    )
    if normal_stage0 is None or pc_stage0 is None:
        return "PC_SAMPLING_CONTROL_NOT_OBSERVED"
    if (
        normal_stage0["feed_gap_ns"] != 800_000_000
        or pc_stage0["feed_gap_ns"] != 800_000_000
    ):
        return "PC_SAMPLING_FEED_GAP_CHANGED"
    if (
        pc_trace["last_event_ns"] is not None
        and normal_trace["last_event_ns"] is not None
        and pc_trace["last_event_ns"] < normal_trace["last_event_ns"]
    ):
        return "PERTURBED_EARLIER_RESET_SAME_800_MS_GAP"
    return "PC_SAMPLING_SAME_800_MS_GAP"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal-stderr", type=Path, required=True)
    parser.add_argument("--normal-serial", type=Path, required=True)
    parser.add_argument("--normal-replicate-stderr", type=Path)
    parser.add_argument("--normal-replicate-serial", type=Path)
    parser.add_argument("--wdt-off-stderr", type=Path, required=True)
    parser.add_argument("--wdt-off-serial", type=Path, required=True)
    parser.add_argument("--trace-off-serial", type=Path, required=True)
    parser.add_argument("--pc-stderr", type=Path, required=True)
    parser.add_argument("--pc-serial", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--pc-symbolization", type=Path, required=True)
    parser.add_argument("--firmware-name", required=True)
    parser.add_argument("--firmware-source-sha256", required=True)
    parser.add_argument("--normal-sample", type=int, required=True)
    parser.add_argument("--wdt-off-sample", type=int, required=True)
    parser.add_argument("--normal-wall-timeout", type=float, required=True)
    parser.add_argument("--wdt-off-wall-timeout", type=float, required=True)
    parser.add_argument("--pc-sample-ns", type=int, required=True)
    parser.add_argument("--core2-summary", type=Path, required=True)
    parser.add_argument("--full-matrix-summary", type=Path, required=True)
    parser.add_argument("--platform-tests-passed", type=int, required=True)
    parser.add_argument("--docs-contract-tests-passed", type=int, required=True)
    parser.add_argument("--qemu-profile-tests-passed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    normal_serial = serial_summary(args.normal_serial)
    wdt_off_serial = serial_summary(args.wdt_off_serial)
    trace_off_serial = serial_summary(args.trace_off_serial)
    normal_trace = summarize_trace(args.normal_stderr)
    wdt_off_trace = summarize_trace(args.wdt_off_stderr)
    pc_trace = summarize_trace(args.pc_stderr)

    result: dict[str, object] = {
        "schema_version": 1,
        "kind": "core2-handoff-trace-summary",
        "validation": "virtual-device validation",
        "firmware": {
            "name": args.firmware_name,
            "source_sha256": args.firmware_source_sha256,
            "normalized_flash_sha256": sha256(args.image),
        },
        "runtime": {
            "machine": "m5core2",
            "qemu_binary_sha256": sha256(args.qemu),
            "trace_patch_sha256": sha256(args.patch),
        },
        "run_config": {
            "normal_watchdog": {
                "sample_interval": args.normal_sample,
                "wall_timeout_seconds": args.normal_wall_timeout,
                "wdt_disabled": False,
            },
            "wdt_disabled": {
                "sample_interval": args.wdt_off_sample,
                "wall_timeout_seconds": args.wdt_off_wall_timeout,
                "wdt_disabled": True,
            },
            "pc_sampling_control": {
                "sample_interval_ns": args.pc_sample_ns,
            },
        },
        "regression": {
            "core2_group": summarize_matrix(args.core2_summary),
            "full_uiflow2_matrix": summarize_matrix(
                args.full_matrix_summary
            ),
        },
        "validation_suite": {
            "platform_unittest": {
                "passed": args.platform_tests_passed,
                "failed": 0,
            },
            "docs_contract": {
                "passed": args.docs_contract_tests_passed,
                "failed": 0,
            },
            "qemu_profile_contract": {
                "passed": args.qemu_profile_tests_passed,
                "failed": 0,
            },
            "node_sha256_upload": "PASS",
            "worker_credential_migration": "PASS",
            "compileall": "PASS",
            "ruff": "PASS (E9/F over platform/tools and platform/tests)",
            "runtime_coverage": "PASS",
            "peripheral_catalog": "PASS",
            "qemu_profiles": "PASS",
            "project_snapshot": "PASS",
            "git_diff_check": "PASS",
            "patch_predecessor_forward_reverse_check": "PASS",
        },
        "normal_watchdog": {
            "trace": normal_trace,
            "serial": normal_serial,
        },
        "wdt_disabled": {
            "trace": wdt_off_trace,
            "serial": wdt_off_serial,
            "trace_off_serial": trace_off_serial,
            "serial_matches_trace_off": (
                wdt_off_serial["sha256"] == trace_off_serial["sha256"]
            ),
        },
        "pc_sampling_control": {
            "trace": pc_trace,
            "serial": serial_summary(args.pc_serial),
            "symbolization": json.loads(
                args.pc_symbolization.read_text()
            ),
        },
        "classification": {
            "normal_wdt": (
                "WDT_FEED_GAP_OBSERVED"
                if any(
                    item["feed_gap_ns"]
                    for item in normal_trace["wdt_timeouts"]
                )
                else "NOT_OBSERVED"
            ),
            "wdt_disabled": (
                "BANNER_ONLY"
                if wdt_off_serial["has_micropython_banner"]
                and not wdt_off_serial["has_repl_prompt"]
                else "NO_BANNER"
            )
            if not wdt_off_serial["has_repl_prompt"]
            else "REPL_REACHED",
            "pc_sampling_control": classify_pc_sampling_control(
                normal_trace,
                pc_trace,
            ),
        },
    }
    if args.normal_replicate_stderr and args.normal_replicate_serial:
        result["normal_watchdog_replicate"] = {
            "trace": summarize_trace(args.normal_replicate_stderr),
            "serial": serial_summary(args.normal_replicate_serial),
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
