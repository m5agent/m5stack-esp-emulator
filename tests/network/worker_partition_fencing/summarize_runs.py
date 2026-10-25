#!/usr/bin/env python3
"""Aggregate independent worker network-partition fencing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("runs", nargs="+", type=Path)
    args = parser.parse_args()
    if len(args.runs) < 3:
        parser.error("at least three independent runs are required")

    documents: list[tuple[Path, dict[str, Any]]] = []
    for run_dir in args.runs:
        evidence_path = run_dir / "evidence.json"
        document = json.loads(evidence_path.read_text())
        if document.get("status") != "PASS":
            raise SystemExit(f"{evidence_path} is not PASS")
        checks = document.get("checks")
        if not isinstance(checks, dict) or not all(
            value is True for value in checks.values()
        ):
            raise SystemExit(f"{evidence_path} has failed checks")
        if document.get("input_assets_unchanged") is not True:
            raise SystemExit(f"{evidence_path} has tool hash drift")
        documents.append((evidence_path, document))

    expected_checks = set(documents[0][1]["checks"])
    if any(
        set(document["checks"]) != expected_checks
        for _, document in documents
    ):
        raise SystemExit("independent runs have different check sets")
    hashes = [document.get("tool_hashes") for _, document in documents]
    if not all(isinstance(value, dict) and value for value in hashes):
        raise SystemExit("independent runs have no tool hashes")
    if any(value != hashes[0] for value in hashes[1:]):
        raise SystemExit("independent runs used different tool hashes")
    revisions = {
        document.get("base_commit") for _, document in documents
    }
    if len(revisions) != 1 or None in revisions:
        raise SystemExit("independent runs used different source revisions")
    if any(
        document.get("source_worktree_clean") is not True
        for _, document in documents
    ):
        raise SystemExit("source worktree was dirty during an independent run")
    runtime_kinds = {
        document["runtime"]["kind"] for _, document in documents
    }
    if len(runtime_kinds) != 1:
        raise SystemExit("independent runs used different runtime kinds")
    runtime_kind = runtime_kinds.pop()

    runs = []
    for evidence_path, document in documents:
        job = document["job"]
        first = document["first_worker"]
        retry = document["retry_worker"]
        checks = document["checks"]
        if (
            job.get("attempts") != 2
            or job.get("status") != "completed"
            or job.get("result", {}).get("state") != "PASS"
            or first.get("returncode", 0) == 0
            or not first.get("result", {}).get("summary", {}).get(
                "lease_fenced"
            )
            or retry.get("returncode") != 0
            or checks.get("runtime_side_effect_reaped") is not True
            or checks.get("retry_side_effect_reaped") is not True
        ):
            raise SystemExit(f"{evidence_path} does not prove fencing")
        run = {
            "evidence_sha256": sha256(evidence_path),
            "job_id_sha256": job["job_id_sha256"],
            "attempts": job["attempts"],
            "result_state": job["result"]["state"],
            "first_worker_returncode": first["returncode"],
            "first_worker_lease_fenced": True,
            "first_side_effect_reaped": checks[
                "runtime_side_effect_reaped"
            ],
            "retry_worker_returncode": retry["returncode"],
            "retry_side_effect_reaped": checks[
                "retry_side_effect_reaped"
            ],
            "cleanup": document["cleanup"],
            "runtime_kind": document["runtime"]["kind"],
        }
        if runtime_kind == "qemu-unified":
            first_assets = first.get("session", {}).get(
                "unified_assets", {}
            )
            retry_assets = retry.get("unified_assets", {})
            run["companion_fencing"] = {
                "http_requests_before_fence": len(
                    first_assets.get("http_requests") or []
                ),
                "ble_pass_before_fence": (
                    first_assets.get("ble_probe_pass") is True
                ),
                "ble_pid_reaped": checks.get(
                    "unified_ble_pid_reaped"
                )
                is True,
                "pcap_bytes_before_fence": first_assets.get(
                    "pcap_bytes", 0
                ),
                "pcap_summary_after_fence": first_assets.get(
                    "pcap_summary_status"
                ),
                "retry_http_requests": len(
                    retry_assets.get("http_requests") or [],
                ),
                "retry_pcap_summary": retry_assets.get(
                    "pcap_summary_status"
                ),
            }
        runs.append(run)
    not_claimed = list(documents[0][1]["not_claimed"])
    if (
        "QEMU guest/device/controller-internal side effects"
        not in not_claimed
        and all(
            document["runtime"]["kind"] == "qemu"
            for _, document in documents
        )
    ):
        not_claimed.append(
            "QEMU guest/device/controller-internal side effects"
        )
    output = {
        "schema_version": 1,
        "kind": "m5stack-worker-network-partition-fencing-3x",
        "date": "2026-10-25",
        "validation": (
            "virtual control-plane + unified companion validation"
            if runtime_kind == "qemu-unified"
            else "virtual control-plane validation"
        ),
        "status": "PASS",
        "source_revision": next(iter(revisions)),
        "source_worktree_clean": True,
        "attempts_requested": len(documents),
        "attempts_completed": len(documents),
        "attempts_passed": len(documents),
        "tool_hashes": hashes[0],
        "input_assets_unchanged": True,
        "checks_per_attempt": {
            name: "PASS"
            for name in sorted(expected_checks)
        },
        "runs": runs,
        "not_claimed": not_claimed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
