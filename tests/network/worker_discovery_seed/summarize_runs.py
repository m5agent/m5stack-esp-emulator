#!/usr/bin/env python3
"""Aggregate independent unicast seed discovery evidence runs."""

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

    documents = []
    for run_dir in args.runs:
        evidence_path = run_dir / "evidence.json"
        document = json.loads(evidence_path.read_text())
        if document.get("status") != "PASS":
            raise SystemExit(f"{evidence_path} is not PASS")
        checks = document.get("checks")
        if not isinstance(checks, dict) or not checks:
            raise SystemExit(f"{evidence_path} has no checks")
        if not all(value is True for value in checks.values()):
            raise SystemExit(f"{evidence_path} has failed checks")
        documents.append((evidence_path, document))

    expected_checks = set(documents[0][1]["checks"])
    if any(set(document["checks"]) != expected_checks for _, document in documents):
        raise SystemExit("independent runs have different check sets")
    for _, document in documents:
        topology = document["topology"]
        if (
            topology.get("control_subnet") != "10.213.1.0/24"
            or topology.get("worker_subnet") != "10.213.2.0/24"
            or topology.get("ipv4_forwarding") is not True
            or topology.get("masquerade") is not True
        ):
            raise SystemExit("independent run topology is inconsistent")
        if document["discovery"].get("control_observed_sources") != [
            "10.213.1.1"
        ]:
            raise SystemExit("independent run did not observe router NAT")

    urls = [document["discovery"]["control_url"] for _, document in documents]
    if len(set(urls)) != len(urls):
        raise SystemExit("independent runs reused the same control endpoint")
    hashes = [document.get("tool_hashes") for _, document in documents]
    if not all(isinstance(value, dict) and value for value in hashes):
        raise SystemExit("independent runs have no tool hashes")
    if any(value != hashes[0] for value in hashes[1:]):
        raise SystemExit("independent runs used different tool hashes")
    if not all(
        document.get("input_assets_unchanged") is True
        for _, document in documents
    ):
        raise SystemExit("tool hashes drifted during a run")

    runs: list[dict[str, Any]] = []
    for evidence_path, document in documents:
        runs.append(
            {
                "evidence_sha256": sha256(evidence_path),
                "control_url": document["discovery"]["control_url"],
                "seed_url": document["discovery"]["seed_url"],
                "initial_token_sha256": document["discovery"][
                    "initial_token_sha256"
                ],
                "rotated_token_sha256": document["discovery"][
                    "rotated_token_sha256"
                ],
                "control_observed_sources": document["discovery"][
                    "control_observed_sources"
                ],
                "workers": document["workers"],
                "cleanup": document["cleanup"],
            }
        )
    output = {
        "schema_version": 1,
        "kind": "m5stack-worker-discovery-unicast-seed-nat-3x",
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
        "not_claimed": [
            "physical cross-host execution",
            "arbitrary NAT traversal without a reachable seed",
            "QEMU execution through the discovered control plane",
            "production multi-host scheduling",
            "physical hardware validation",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
