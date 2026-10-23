#!/usr/bin/env python3
"""Validate the reusable private TAP/bridge fabric without QEMU."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_fabric import (  # noqa: E402
    GUEST_ADDRESSES,
    GUEST_MACS,
    LabFabric,
)


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if sys.platform != "linux":
        parser.error("the lab fabric primitive requires Linux")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    ready = out / "dhcp-ready.json"
    leases = out / "dhcp-leases.json"
    fabric = LabFabric.allocate()
    dhcp: subprocess.Popen | None = None
    namespace_before: list[str] = []
    namespace_after: list[str] = []
    rules = ""
    started = time.monotonic()
    try:
        fabric.start()
        namespace_before = subprocess.run(
            ["ip", "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.splitlines()
        config = out / "dhcp.json"
        config.write_text(
            json.dumps(
                {
                    "interface": fabric.bridge,
                    "server_address": fabric.bridge_address,
                    "prefix_length": fabric.prefix_length,
                    "lease_seconds": 3600,
                    "reservations": dict(zip(GUEST_MACS, GUEST_ADDRESSES)),
                    "endpoints": [
                        endpoint.as_dict()
                        for endpoint in fabric.endpoints
                    ],
                    "lease_file": str(leases),
                    "ready_file": str(ready),
                },
                indent=2,
            )
            + "\n"
        )
        dhcp = fabric.run(
            [
                sys.executable,
                str(ROOT / "platform/tools/network_fabric.py"),
                "dhcp",
                "--config",
                str(config),
            ],
            log_path=out / "dhcp.log",
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not ready.is_file():
            if dhcp.poll() is not None:
                break
            time.sleep(0.1)
        rules = fabric.run_checked(
            ["nft", "list", "table", "inet", "m5_lab"]
        ).stdout
    finally:
        stop_process(dhcp)
        if dhcp is not None:
            log = getattr(dhcp, "_m5_log", None)
            if log is not None:
                log.close()
        fabric.cleanup()
        namespace_after = subprocess.run(
            ["ip", "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.splitlines()
    checks = {
        "namespace_created": any(
            line.split(maxsplit=1)[0] == fabric.namespace
            for line in namespace_before
            if line.strip()
        ),
        "dhcp_ready": ready.is_file(),
        "nft_input_drop": "policy drop;" in rules,
        "nft_tap_forwarding": (
            fabric.endpoints[0].tap in rules
            and fabric.endpoints[1].tap in rules
        ),
        "namespace_cleaned": all(
            line.split(maxsplit=1)[0] != fabric.namespace
            for line in namespace_after
            if line.strip()
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-linux-lab-fabric-primitive",
        "scope": "host-fabric-only-not-qemu-or-hardware",
        "date": "2026-10-24",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "fabric": fabric.metadata(),
        "namespace_before": namespace_before,
        "namespace_after": namespace_after,
        "nftables": rules,
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
