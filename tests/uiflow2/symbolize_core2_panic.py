#!/usr/bin/env python3
"""Symbolize ESP32 Core2 panic PCs from a UIFlow2 serial log."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ADDR2LINE = (
    Path.home()
    / ".espressif/tools/xtensa-esp-elf/esp-14.2.0_20260121"
    / "xtensa-esp-elf/bin/xtensa-esp32-elf-addr2line"
)

PC_RE = re.compile(r"\bPC\s*:\s*(0x[0-9a-fA-F]+)")
BACKTRACE_RE = re.compile(r"Backtrace:\s*([0-9a-fA-Fx:\s|<>-]+)")
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{8}")


def extract_addresses(log: str) -> list[str]:
    addresses = []
    for match in PC_RE.finditer(log):
        addresses.append(match.group(1).lower())
    for match in BACKTRACE_RE.finditer(log):
        addresses.extend(value.lower() for value in ADDRESS_RE.findall(match.group(1)))
    seen = set()
    unique = []
    for address in addresses:
        if address not in seen:
            seen.add(address)
            unique.append(address)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--addr2line", type=Path, default=DEFAULT_ADDR2LINE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.log.is_file():
        raise SystemExit(f"missing serial log: {args.log}")
    if not args.elf.is_file():
        raise SystemExit(f"missing ELF: {args.elf}")
    addr2line = args.addr2line
    if not addr2line.is_file():
        resolved = shutil.which("xtensa-esp32-elf-addr2line")
        if not resolved:
            raise SystemExit(f"addr2line not found: {addr2line}")
        addr2line = Path(resolved)

    log = args.log.read_text(errors="replace")
    addresses = extract_addresses(log)
    symbols = []
    if addresses:
        result = subprocess.run(
            [
                str(addr2line),
                "-p",
                "-f",
                "-i",
                "-a",
                "-e",
                str(args.elf),
                *addresses,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        symbols = [
            line
            for line in result.stdout.splitlines()
            if line.strip()
        ]

    payload = {
        "log": str(args.log),
        "elf": str(args.elf),
        "addresses": addresses,
        "symbols": symbols,
        "contains_cache_panic": (
            "Cache disabled but cached memory region accessed" in log
        ),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"cache_panic={payload['contains_cache_panic']}")
    for line in symbols:
        print(line)
    if not addresses:
        print("no panic PC/backtrace addresses found")


if __name__ == "__main__":
    main()
