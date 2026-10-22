#!/usr/bin/env python3
"""Check that a QEMU build has the user-mode network backend used by lab tests."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QEMU = (
    ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
)
DEFAULT_BUILD_DIR = DEFAULT_QEMU.parent


def has_slirp_define(config_header: str) -> bool:
    return bool(
        re.search(r"(?m)^#define\s+CONFIG_SLIRP(?:\s+1)?\s*$", config_header)
    )


def has_user_netdev(netdev_help: str) -> bool:
    return bool(re.search(r"(?m)^user\s*$", netdev_help))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def inspect_qemu_network(
    qemu: Path = DEFAULT_QEMU,
    build_dir: Path = DEFAULT_BUILD_DIR,
) -> dict:
    checks: dict[str, bool] = {}
    details: dict[str, str] = {}
    errors: list[str] = []

    checks["qemu_exists"] = qemu.is_file()
    checks["qemu_executable"] = qemu.is_file() and qemu.stat().st_mode & 0o111 != 0
    config_header_path = build_dir / "config-host.h"
    checks["config_header"] = config_header_path.is_file()
    if checks["config_header"]:
        checks["config_slirp"] = has_slirp_define(
            config_header_path.read_text(errors="replace")
        )
    else:
        checks["config_slirp"] = False
        errors.append(f"missing QEMU config header: {config_header_path}")

    netdev_help = ""
    if checks["qemu_executable"]:
        completed = subprocess.run(
            [str(qemu), "-netdev", "help"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        netdev_help = completed.stdout + completed.stderr
        checks["netdev_help_exit_zero"] = completed.returncode == 0
        if completed.returncode != 0:
            errors.append(
                f"QEMU -netdev help exited {completed.returncode}: "
                f"{netdev_help[-1000:]}"
            )
    else:
        checks["netdev_help_exit_zero"] = False
        errors.append(f"QEMU is not executable: {qemu}")
    checks["netdev_user"] = has_user_netdev(netdev_help)
    if checks["qemu_executable"] and not checks["netdev_user"]:
        errors.append("QEMU does not advertise the user-mode netdev backend")
    if checks["config_header"] and not checks["config_slirp"]:
        errors.append("QEMU was built without CONFIG_SLIRP")

    passed = all(checks.values())
    return {
        "schema_version": 1,
        "status": "PASS" if passed else "FAIL",
        "scope": "host-build-preflight-not-guest-network-proof",
        "qemu": display_path(qemu),
        "build_dir": display_path(build_dir),
        "checks": checks,
        "netdevs": [
            line.strip()
            for line in netdev_help.splitlines()
            if line.strip() and not line.startswith("Available ")
        ],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    args = parser.parse_args()
    evidence = inspect_qemu_network(args.qemu, args.build_dir)
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
