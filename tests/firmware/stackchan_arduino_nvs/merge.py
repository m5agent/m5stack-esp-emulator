#!/usr/bin/env python3
"""Compose this probe's full Flash; never flash or execute a device."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path,
                        default=Path(__file__).parent / ".pio/build/nvs_probe")
    parser.add_argument("--boot-app0", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    flash = bytearray(b"\xff" * (16 << 20))
    segments = [(0, args.build_dir / "bootloader.bin"),
                (0x8000, args.build_dir / "partitions.bin"),
                (0xe000, args.boot_app0),
                (0x10000, args.build_dir / "firmware.bin")]
    previous_end, receipt = 0, []
    for offset, path in segments:
        data = path.read_bytes()
        if not data or offset < previous_end or offset + len(data) > len(flash):
            raise ValueError("invalid, overlapping or oversized Flash segment")
        flash[offset:offset + len(data)] = data
        previous_end = offset + len(data)
        receipt.append({"offset": offset, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    if flash[0] != 0xe9 or flash[0x10000] != 0xe9:
        raise ValueError("expected ESP32-S3 bootloader and app image headers")
    with args.output.open("xb") as stream:
        stream.write(flash)
    print(json.dumps({"chip": "esp32s3", "bytes": len(flash),
                      "sha256": hashlib.sha256(flash).hexdigest(),
                      "segments": receipt}, indent=2))


if __name__ == "__main__":
    main()
