#!/usr/bin/env python3
"""Summarize cross-container worker QEMU runs and startup diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def diagnostic_failure(run: Path) -> dict[str, Any]:
    evidence = load_json(run / "evidence.json")
    error = str(evidence.get("error", ""))
    worker_result = (
        load_json(run / "worker-result.json")
        if (run / "worker-result.json").is_file()
        else {}
    )
    result_error = str(
        worker_result.get("result", {}).get("summary", {}).get("error", "")
    )
    combined = error + "\n" + result_error
    if "service did not become ready" in combined:
        stage = "central_service_unreachable_from_worker_container"
    elif "backend_not_ready" in combined and ".work/" in combined:
        stage = "host_absolute_qemu_path_used_inside_container"
    else:
        stage = "unclassified_cross_container_failure"
    return {
        "label": run.name,
        "status": evidence.get("status", "FAIL"),
        "stage": stage,
        "central_reachable": (
            evidence.get("checks", {}).get(
                "central_api_reachable_over_container_network"
            )
            is True
        ),
        "worker_local_execution": (
            evidence.get("checks", {}).get("worker_local_execution") is True
        ),
        "qemu_started": (evidence.get("checks", {}).get("qemu_started") is True),
        "classification": "cross-container harness/runtime-asset failure before a passing guest path",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument(
        "--diagnostic-failure",
        type=Path,
        action="append",
        default=[],
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    runs = []
    common_artifact_hashes: dict[str, Any] | None = None
    common_checks: dict[str, bool] | None = None
    for run in args.run:
        evidence = load_json(run / "evidence.json")
        if evidence.get("status") != "PASS":
            raise SystemExit(f"run is not PASS: {run}")
        checks = evidence.get("checks")
        if not isinstance(checks, dict) or not all(checks.values()):
            raise SystemExit(f"run has incomplete checks: {run}")
        artifacts = {
            key: evidence.get("artifacts", {}).get(key)
            for key in (
                "firmware_source_sha256",
                "firmware_normalized_sha256",
                "qemu_sha256",
                "runner_sha256",
                "worker_fixture_sha256",
                "device_service_sha256",
                "worker_agent_sha256",
                "dockerfile_sha256",
            )
        }
        if common_artifact_hashes is None:
            common_artifact_hashes = artifacts
            common_checks = checks
        elif artifacts != common_artifact_hashes:
            raise SystemExit(f"artifact hash drift: {run}")
        elif checks != common_checks:
            raise SystemExit(f"check-set drift: {run}")
        runs.append(
            {
                "label": run.name,
                "status": "PASS",
                "duration_seconds": evidence.get("environment", {}).get(
                    "duration_seconds"
                ),
                "image_id_sha256": evidence.get("environment", {}).get(
                    "image_id_sha256"
                ),
                "network_id_sha256": evidence.get("environment", {}).get(
                    "network_id_sha256"
                ),
                "central_container_sha256": evidence.get("environment", {}).get(
                    "central_container_sha256"
                ),
                "worker_container_sha256": evidence.get("environment", {}).get(
                    "worker_container_sha256"
                ),
                "worker_result_sha256": evidence.get("artifacts", {}).get(
                    "worker_result_sha256"
                ),
                "evidence_names": evidence.get("evidence_names", []),
            }
        )

    current_hashes = {
        "runner_sha256": sha256_file(
            ROOT / "tests/network/worker_cross_container/run_test.py"
        ),
        "worker_fixture_sha256": sha256_file(
            ROOT / "tests/network/worker_cross_netns/run_test.py"
        ),
        "device_service_sha256": sha256_file(ROOT / "platform/tools/device_service.py"),
        "worker_agent_sha256": sha256_file(ROOT / "platform/tools/worker_agent.py"),
        "dockerfile_sha256": sha256_file(
            ROOT / "tests/network/worker_cross_container/Dockerfile"
        ),
    }
    if any(value is None for value in current_hashes.values()):
        raise SystemExit("current implementation file is missing")
    drift = {
        key: {
            "run": (common_artifact_hashes or {}).get(key),
            "current": value,
        }
        for key, value in current_hashes.items()
        if (common_artifact_hashes or {}).get(key) != value
    }
    if drift:
        raise SystemExit(
            "current code drifted from cross-container runs: "
            + json.dumps(drift, sort_keys=True)
        )
    first_evidence = load_json(args.run[0] / "evidence.json")

    aggregate = {
        "schema_version": 1,
        "kind": "m5stack-worker-qemu-cross-container",
        "date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "validation": "virtual-device validation",
        "scope": "three-independent-cross-container-runs-one-docker-daemon-not-physical-hosts",
        "environment": {
            "host_os": first_evidence.get("environment", {}).get("host_os"),
            "docker_os": first_evidence.get("environment", {}).get("docker_os"),
            "docker_arch": first_evidence.get("environment", {}).get("docker_arch"),
            "docker_version": first_evidence.get("environment", {}).get(
                "docker_version"
            ),
            "image": first_evidence.get("environment", {}).get("image"),
            "lease_count": len(runs),
        },
        "artifacts": {
            **common_artifact_hashes,
            "summarizer": sha256_file(Path(__file__)),
        },
        "checks": common_checks,
        "runs": runs,
        "diagnostic_failures": [
            diagnostic_failure(path) for path in args.diagnostic_failure
        ],
        "not_claimed": [
            "physically separate hosts",
            "cross-host process migration or re-attach",
            "NAT or cross-subnet discovery",
            "companion HTTP/BLE continuity",
            "production multi-host scheduling",
            "physical RF or hardware validation",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
