#!/usr/bin/env python3
"""Create two ESP-IDF SPIFFS fixtures and an identical-app boot control."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


PARTITION_START = 0x110000
PARTITION_SIZE = 0x100000
FLASH_SIZE = 0x800000
LONG_NAME = "GEOMETRY_CHECK_FILE_LONG.BIN"
BASELINE_PAYLOAD = b"M5EMU_BASELINE_SPIFFS_PAYLOAD"
FIXTURE_PAYLOAD = b"M5EMU_SEEDED_SPIFFS_PAYLOAD"


def make_partition(
    generator: Path, output: Path, *, seeded: bool,
) -> Path:
    role = "seed" if seeded else "baseline"
    files = output / role
    files.mkdir()
    name = "FIXTURE.TXT" if seeded else "BASELINE.TXT"
    (files / name).write_bytes(FIXTURE_PAYLOAD if seeded else BASELINE_PAYLOAD)
    count, step = (11321, 23) if seeded else (9245, 19)
    (files / LONG_NAME).write_bytes(bytes((index * step + 9) & 255 for index in range(count)))
    partition = output / (role + ".spiffs.bin")
    subprocess.run(
        [sys.executable, str(generator), hex(PARTITION_SIZE), str(files), str(partition)],
        check=True,
    )
    return partition


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idf", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=False)
    generator = args.idf / "components/spiffs/spiffsgen.py"
    seed = make_partition(generator, args.out, seeded=True)
    baseline = make_partition(generator, args.out, seeded=False)
    blank = args.out / "blank-flash.bin"
    subprocess.run(
        [sys.executable, "-m", "esptool", "--chip", "esp32s3", "merge_bin",
         "--flash_mode", "dio", "--flash_freq", "80m", "--flash_size", "8MB",
         "--fill-flash-size", "8MB", "-o", str(blank),
         "0x0", str(args.build / "bootloader/bootloader.bin"),
         "0x8000", str(args.build / "partition_table/partition-table.bin"),
         "0x10000", str(args.build / "m5_spiffs_partition_probe.bin")],
        check=True,
    )
    merged, partition = blank.read_bytes(), baseline.read_bytes()
    start, end = PARTITION_START, PARTITION_START + PARTITION_SIZE
    if (
        len(merged) != FLASH_SIZE
        or len(partition) != PARTITION_SIZE
        or seed.stat().st_size != PARTITION_SIZE
        or merged[start:end] != b"\xff" * PARTITION_SIZE
    ):
        raise ValueError("merged boot image has unexpected flash or storage bytes")
    base_image = args.out / "baseline-flash.bin"
    base_image.write_bytes(merged[:start] + partition + merged[end:])
    print(json.dumps({
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (blank, base_image, baseline, seed)
    }, indent=2))


if __name__ == "__main__":
    main()
