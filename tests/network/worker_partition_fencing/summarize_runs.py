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

    runs = []
    for evidence_path, document in documents:
        job = document["job"]
        first = document["first_worker"]
        retry = document["retry_worker"]
        if (
            job.get("attempts") != 2
            or job.get("status") != "completed"
            or job.get("result", {}).get("state") != "PASS"
            or first.get("returncode", 0) == 0
            or not first.get("result", {}).get("summary", {}).get(
                "lease_fenced"
            )
            or not first.get("session", {}).get("side_effect_reaped")
            or retry.get("returncode") != 0
            or not retry.get("session", {}).get("side_effect_reaped")
        ):
            raise SystemExit(f"{evidence_path} does not prove fencing")
        runs.append(
            {
                "evidence_sha256": sha256(evidence_path),
                "job_id_sha256": job["job_id_sha256"],
                "attempts": job["attempts"],
                "result_state": job["result"]["state"],
                "first_worker_returncode": first["returncode"],
                "first_worker_lease_fenced": True,
                "first_side_effect_reaped": True,
                "retry_worker_returncode": retry["returncode"],
                "retry_side_effect_reaped": True,
                "cleanup": document["cleanup"],
            }
        )
    output = {
        "schema_version": 1,
        "kind": "m5stack-worker-network-partition-fencing-3x",
        "date": "2026-10-25",
        "validation": "virtual control-plane validation",
        "status": "PASS",
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
        "not_claimed": documents[0][1]["not_claimed"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
