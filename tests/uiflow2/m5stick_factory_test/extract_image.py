#!/usr/bin/env python3
"""Extract the M5Stick factory-test image from the official EasyLoader package.

The M5Stick (K016) has no public UIFlow1/UIFlow2 firmware.  The only official
executable image is the FactoryTest binary embedded in the Windows EasyLoader
installer.  This tool pins the installer SHA-256, extracts the contiguous
flash region (bootloader at flash 0x1000 through the end of app0) and writes
the normalized 4 MiB image used by the device matrix "firmware" case.

The installer internal layout is not a documented contract: keep the installer
SHA-256 pinned, and re-derive the offsets if the pinned artifact changes.
"""
from __future__ import annotations

import argparse
import hashlib
import urllib.request
from pathlib import Path

INSTALLER_URL = (
    "https://m5stack.oss-cn-shenzhen.aliyuncs.com/EasyLoader/Windows/CORE/"
    "EasyLoader_M5Stick_FactoryTest.exe"
)
INSTALLER_BYTES = 9463808
INSTALLER_SHA256 = (
    "99c640b0ed51bd9670f544164f5542cb9c0303f1b6f84a4ee91e33e6c82e69f4"
)
BOOTLOADER_INSTALLER_OFFSET = 0x527B41
FLASH_EXTRACT_OFFSET = 0x1000
FLASH_EXTRACT_BYTES = 0x571E0
IMAGE_FLASH_BYTES = 0x400000
IMAGE_SHA256 = (
    "84228dfb6f0dd9b84b63c33f93a53545d8d43658893f432e3eaf4313923bffca"
)
SEGMENT_SHA256 = (
    "7435e808475e9774361e4232eb009ce71fdcda33651477d9904e49be4884f036"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--installer",
        type=Path,
        help="existing EasyLoader installer (downloaded when omitted)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("platform/.cache/firmware/m5stick/factory-test-4m.bin"),
        help="normalized 4 MiB image output path",
    )
    args = parser.parse_args()

    if args.installer:
        installer = args.installer.read_bytes()
    else:
        print(f"download {INSTALLER_URL}")
        with urllib.request.urlopen(INSTALLER_URL, timeout=180) as response:
            installer = response.read()
    if len(installer) != INSTALLER_BYTES or sha256(installer) != INSTALLER_SHA256:
        raise SystemExit(
            "EasyLoader installer does not match the pinned bytes/SHA-256: "
            f"bytes={len(installer)} sha256={sha256(installer)}"
        )
    segment = installer[
        BOOTLOADER_INSTALLER_OFFSET:
        BOOTLOADER_INSTALLER_OFFSET + FLASH_EXTRACT_BYTES
    ]
    if sha256(segment) != SEGMENT_SHA256:
        raise SystemExit(
            "extracted flash segment does not match the pinned SHA-256: "
            f"sha256={sha256(segment)}"
        )
    image = bytearray(b"\xff" * IMAGE_FLASH_BYTES)
    image[FLASH_EXTRACT_OFFSET:FLASH_EXTRACT_OFFSET + FLASH_EXTRACT_BYTES] = segment
    if sha256(image) != IMAGE_SHA256:
        raise SystemExit(
            "normalized image does not match the pinned SHA-256: "
            f"sha256={sha256(image)}"
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(image)
    print(f"installer sha256: {INSTALLER_SHA256}")
    print(f"segment sha256: {SEGMENT_SHA256}")
    print(f"image: {args.out}")
    print(f"image sha256: {IMAGE_SHA256}")


if __name__ == "__main__":
    main()
