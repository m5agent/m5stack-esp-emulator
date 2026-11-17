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
BOOT_OFFSETS = {"esp32": "0x1000", "esp32s3": "0x0", "esp32c6": "0x0"}
FLASH_SIZES = {"8MB": 8 * 1024 * 1024, "16MB": 16 * 1024 * 1024}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build, out = args.build.resolve(), args.out.resolve()
    flasher = json.loads((build / "flasher_args.json").read_text())
    chip = flasher["extra_esptool_args"]["chip"]
    settings = flasher["flash_settings"]
    flash_size = settings["flash_size"]
    if chip not in BOOT_OFFSETS or flash_size not in FLASH_SIZES:
        raise ValueError(f"unsupported LittleFS probe target {chip!r} with {flash_size!r}")
    boot_offset = BOOT_OFFSETS[chip]
    flash_files = flasher["flash_files"]
    if set(flash_files) != {boot_offset, "0x8000", "0x10000"}:
        raise ValueError("expected only bootloader, partition table and application in the build")
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
        sys.executable, "-m", "esptool", "--chip", chip, "merge_bin",
        "--flash_mode", settings["flash_mode"], "--flash_freq", settings["flash_freq"],
        "--flash_size", flash_size, "--fill-flash-size", flash_size, "-o", str(boot_image),
        boot_offset, str(build / flash_files[boot_offset]),
        "0x8000", str(build / flash_files["0x8000"]),
        "0x10000", str(build / flash_files["0x10000"]),
    ], check=True)
    boot, empty = boot_image.read_bytes(), empty_image.read_bytes()
    seed = (build / "storage.bin").read_bytes()
    if (
        len(boot) != FLASH_SIZES[flash_size] or len(seed) != PARTITION_SIZE
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
