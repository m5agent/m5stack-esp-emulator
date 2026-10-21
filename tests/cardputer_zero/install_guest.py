#!/usr/bin/env python3
"""Install repeatable CardputerZero guest probes into an ext4 image."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUEST = HERE / "guest"


def require_tool(name: str, fallback: str | None = None) -> str:
    path = shutil.which(name)
    if not path and fallback and Path(fallback).is_file():
        path = fallback
    if not path:
        raise SystemExit(f"missing required tool: {name}")
    return path


def attach_image(image: Path) -> tuple[str, str]:
    if os.uname().sysname == "Darwin":
        result = subprocess.run(
            [
                "hdiutil",
                "attach",
                "-nomount",
                "-readwrite",
                str(image),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        disk = result.stdout.splitlines()[0].split()[0]
        return disk, f"{disk}s2"

    result = subprocess.run(
        ["losetup", "--find", "--show", "--partscan", str(image)],
        check=True,
        capture_output=True,
        text=True,
    )
    loop = result.stdout.strip()
    return loop, f"{loop}p2"


def detach_image(disk: str) -> None:
    if os.uname().sysname == "Darwin":
        subprocess.run(["hdiutil", "detach", disk], check=True)
    else:
        subprocess.run(["losetup", "--detach", disk], check=True)


def debugfs(debugfs_tool: str, partition: str, command: str) -> None:
    subprocess.run(
        [debugfs_tool, "-w", "-R", command, partition],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def fsck_image(image: Path) -> None:
    e2fsck = require_tool("e2fsck", "/opt/homebrew/opt/e2fsprogs/sbin/e2fsck")
    disk, partition = attach_image(image)
    try:
        result = subprocess.run([e2fsck, "-fy", partition])
        if result.returncode not in (0, 1):
            raise SystemExit(f"e2fsck failed with status {result.returncode}")
    finally:
        detach_image(disk)


def install_file(
    debugfs_tool: str,
    partition: str,
    source: Path,
    destination: str,
    mode: str | None = None,
) -> None:
    subprocess.run(
        [debugfs_tool, "-w", "-R", f"rm {destination}", partition],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    debugfs(
        debugfs_tool,
        partition,
        f"write {source.resolve()} {destination}",
    )
    if mode:
        debugfs(
            debugfs_tool,
            partition,
            f"sif {destination} mode {mode}",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--debugfs")
    args = parser.parse_args()
    if not args.image.is_file():
        raise SystemExit(f"missing image: {args.image}")

    fsck_image(args.image)
    shim = HERE.parents[1] / ".work/cardputerzero/guest/m5-fb-shim.so"
    subprocess.run(
        ["python3", str(HERE / "build_guest_helpers.py")],
        cwd=HERE.parents[1],
        check=True,
    )
    debugfs_tool = require_tool(
        "debugfs", "/opt/homebrew/opt/e2fsprogs/sbin/debugfs"
    )
    disk, partition = attach_image(args.image)
    try:
        install_file(
            debugfs_tool,
            partition,
            GUEST / "m5_probe.sh",
            "/usr/local/sbin/m5-probe",
            "0100755",
        )
        install_file(
            debugfs_tool,
            partition,
            GUEST / "m5_key_frame_probe.sh",
            "/usr/local/sbin/m5-key-frame-probe",
            "0100755",
        )
        install_file(
            debugfs_tool,
            partition,
            shim,
            "/usr/local/lib/m5-fb-shim.so",
            "0100644",
        )
        install_file(
            debugfs_tool,
            partition,
            GUEST / "m5_eth_probe.py",
            "/usr/local/sbin/m5-eth-probe",
            "0100755",
        )
        install_file(
            debugfs_tool,
            partition,
            GUEST / "m5-probe.service",
            "/etc/systemd/system/m5-probe.service",
        )
        install_file(
            debugfs_tool,
            partition,
            GUEST / "m5-key-frame-probe.service",
            "/etc/systemd/system/m5-key-frame-probe.service",
        )

        wants = "/etc/systemd/system/multi-user.target.wants"
        for service in ("m5-probe.service", "m5-key-frame-probe.service"):
            link = f"{wants}/{service}"
            debugfs(debugfs_tool, partition, f"rm {link}")
            debugfs(
                debugfs_tool,
                partition,
                f"symlink {link} /etc/systemd/system/{service}",
            )
    finally:
        detach_image(disk)

    fsck_image(args.image)
    print(f"installed CardputerZero guest probes into {args.image}")


if __name__ == "__main__":
    main()
