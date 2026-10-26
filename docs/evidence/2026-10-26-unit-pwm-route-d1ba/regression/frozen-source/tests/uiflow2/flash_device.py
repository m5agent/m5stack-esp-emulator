#!/usr/bin/env python3
"""Create a bootable virtual flash image for a registered M5Stack device."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from esp_flash import default_env, flash_with_esp_emu, flash_with_qemu

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"


def direct_flash(image: Path, flash_size: int, out_dir: Path) -> dict:
    data = image.read_bytes()
    if len(data) > flash_size:
        raise SystemExit(
            f"firmware is larger than virtual flash: {len(data)} > {flash_size}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "virtual-flash.bin"
    target.write_bytes(data + b"\xff" * (flash_size - len(data)))
    return {
        "transport": "host-image",
        "image": str(image),
        "virtual_flash": str(target),
        "flash_size": flash_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "verified": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--firmware", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--transport",
        choices=("esp-emu", "copy"),
        default="esp-emu",
    )
    args = parser.parse_args()

    matrix = json.loads(MATRIX.read_text())
    device = next(
        (item for item in matrix["devices"] if item["id"] == args.device),
        None,
    )
    if not device:
        raise SystemExit(f"unknown device: {args.device}")
    backend = matrix["backends"][device["backend"]]
    flash_size = int(device["flash_size"], 0)
    chip = backend.get("esp_emu_chip")
    qemu_chip = backend.get("qemu_esptool_chip")
    firmware = args.firmware.resolve()
    if not firmware.is_file():
        raise SystemExit(f"firmware not found: {firmware}")

    if args.transport == "esp-emu" and chip:
        result = flash_with_esp_emu(
            chip=chip,
            image=firmware,
            flash_size=flash_size,
            out_dir=args.out_dir,
            env=default_env(),
        )
    elif args.transport == "esp-emu" and qemu_chip:
        result = flash_with_qemu(
            chip=qemu_chip,
            machine=device["machine"],
            image=firmware,
            flash_size=flash_size,
            out_dir=args.out_dir,
            env=default_env(),
            qemu=ROOT / backend["qemu"],
            rom_dir=ROOT / backend["rom_dir"],
            timeout=600,
            memory=device.get("memory"),
        )
    else:
        result = direct_flash(firmware, flash_size, args.out_dir)
    result["device"] = args.device
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
