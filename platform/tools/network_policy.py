#!/usr/bin/env python3
"""Validate fail-closed network policies for virtual-device sessions."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SANDBOX_RUNNER = ROOT / "platform/tools/network_sandbox.py"
ISOLATION_MODES = {"trusted-host", "namespace"}
EGRESS_MODES = {"native", "deny-all", "lab-only"}
DNS_MODES = {"slirp", "deny"}


class NetworkPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class NetworkPolicy:
    isolation: str = "trusted-host"
    egress: str = "native"
    dns: str = "slirp"
    capture_pcap: bool = True

    @classmethod
    def from_mapping(cls, value: Any) -> "NetworkPolicy":
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise NetworkPolicyError("network.policy must be an object")
        isolation = value.get("isolation", "trusted-host")
        egress = value.get("egress", "native")
        dns = value.get("dns", "slirp")
        if isolation not in ISOLATION_MODES:
            raise NetworkPolicyError(
                f"network.policy.isolation must be one of "
                f"{sorted(ISOLATION_MODES)}"
            )
        if egress not in EGRESS_MODES:
            raise NetworkPolicyError(
                f"network.policy.egress must be one of "
                f"{sorted(EGRESS_MODES)}"
            )
        if dns not in DNS_MODES:
            raise NetworkPolicyError(
                f"network.policy.dns must be one of {sorted(DNS_MODES)}"
            )
        if isolation == "trusted-host" and egress != "native":
            raise NetworkPolicyError(
                "non-native egress requires isolation=namespace"
            )
        if isolation == "trusted-host" and dns == "deny":
            raise NetworkPolicyError(
                "dns=deny requires isolation=namespace"
            )
        if isolation == "namespace" and egress == "native":
            raise NetworkPolicyError(
                "isolation=namespace requires egress=deny-all or lab-only"
            )
        if egress in {"deny-all", "lab-only"} and dns != "deny":
            raise NetworkPolicyError(
                "restricted egress requires dns=deny"
            )
        return cls(
            isolation=isolation,
            egress=egress,
            dns=dns,
            capture_pcap=True,
        )

    def evidence(self) -> dict:
        return {
            "isolation": self.isolation,
            "egress": self.egress,
            "dns": self.dns,
            "capture_pcap": self.capture_pcap,
            "claim": (
                "Linux network namespace with no external route"
                if self.isolation == "namespace"
                else "trusted-host user networking"
            ),
            "not_claimed": [
                "malware safety",
                "RF behavior",
                "TLS certificate correctness",
                "external internet allowlist",
            ],
        }


def namespace_capability() -> dict:
    checks = {
        "linux": sys.platform == "linux",
        "python_unshare": hasattr(os, "unshare")
        and hasattr(os, "CLONE_NEWNET"),
        "sandbox_runner": SANDBOX_RUNNER.is_file(),
        "namespace_probe": False,
    }
    errors: list[str] = []
    if not checks["linux"]:
        errors.append("network namespace isolation requires Linux")
    if not checks["python_unshare"]:
        errors.append("Python runtime lacks os.unshare(CLONE_NEWNET)")
    if not checks["sandbox_runner"]:
        errors.append(f"sandbox runner is missing: {SANDBOX_RUNNER}")
    if checks["linux"] and checks["python_unshare"]:
        try:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os;"
                        "os.unshare(os.CLONE_NEWNET);"
                        "print('NETNS_OK')"
                    ),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            checks["namespace_probe"] = (
                completed.returncode == 0
                and "NETNS_OK" in completed.stdout
            )
            if not checks["namespace_probe"]:
                errors.append(
                    "kernel rejected network namespace creation "
                    f"(exit {completed.returncode})"
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            errors.append(f"network namespace probe failed: {error}")
    else:
        checks["namespace_probe"] = False
    return {
        "status": "PASS" if not errors else "UNAVAILABLE",
        "checks": checks,
        "errors": errors,
    }


def build_sandbox_command(
    command: list[str],
    *,
    config_path: Path,
    python: str | None = None,
) -> list[str]:
    capability = namespace_capability()
    if capability["status"] != "PASS":
        raise NetworkPolicyError("; ".join(capability["errors"]))
    executable = python or sys.executable
    return [
        executable,
        str(SANDBOX_RUNNER),
        "--config",
        str(config_path),
        "--",
        *command,
    ]


def qemu_user_netdev(
    *,
    nic: str,
    policy: NetworkPolicy,
) -> str:
    # QEMU user-mode restrict=yes also blocks 10.0.2.2 (host loopback), which
    # is where namespace-local lab fixtures listen. The namespace itself
    # already removes every external route, so lab-only uses unrestricted
    # SLiRP to reach those loopback fixtures.
    restricted = policy.egress == "deny-all"
    suffix = ",restrict=yes" if restricted else ""
    return f"user{suffix},model={nic},id=wifi0"


def main() -> int:
    print(json.dumps(namespace_capability(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
