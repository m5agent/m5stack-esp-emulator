#!/usr/bin/env python3
"""Assemble a boot image with a mountable empty LittleFS and separate seed."""
from argparse import ArgumentParser
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

PARTITION_START = 0x110000
PARTITION_END = 0x210000
PARTITION_SIZE = PARTITION_END - PARTITION_START
FLASH_SIZE = 0x800000


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build, out = args.build.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    empty_dir = out / "empty"
    empty_dir.mkdir()
    empty_image = out / "empty.littlefs.bin"
    boot_image = out / "boot-only.bin"
    subprocess.run([
        str(build / "littlefs_py_venv/bin/littlefs-python"), "create",
        str(empty_dir), str(empty_image), "--fs-size=0x100000", "--name-max=64",
        "--block-size=4096",
    ], check=True)
    subprocess.run([
        sys.executable, "-m", "esptool", "--chip", "esp32s3", "merge_bin",
        "--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "8MB",
        "--fill-flash-size", "8MB", "-o", str(boot_image),
        "0x0", str(build / "bootloader/bootloader.bin"),
        "0x8000", str(build / "partition_table/partition-table.bin"),
        "0x10000", str(build / "m5_littlefs_partition_probe.bin"),
    ], check=True)
    boot, empty = boot_image.read_bytes(), empty_image.read_bytes()
    seed = (build / "storage.bin").read_bytes()
    if (
        len(boot) != FLASH_SIZE or len(seed) != PARTITION_SIZE
        or len(empty) != PARTITION_SIZE
        or boot[PARTITION_START:PARTITION_END] != b"\xff" * PARTITION_SIZE
    ):
        raise ValueError("generated flash or LittleFS partition has an unexpected layout")
    base = boot[:PARTITION_START] + empty + boot[PARTITION_END:]
    (out / "baseline-flash.bin").write_bytes(base)
    (out / "seed.littlefs.bin").write_bytes(seed)
    print(json.dumps({
        "baseline_flash_sha256": sha256(base).hexdigest(),
        "fixture_sha256": sha256(seed).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
