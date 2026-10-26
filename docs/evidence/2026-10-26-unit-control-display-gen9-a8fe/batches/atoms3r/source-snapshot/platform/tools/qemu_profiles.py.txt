#!/usr/bin/env python3
"""Inspect the virtual-host adaptation registry for M5Stack devices."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "platform/qemu/profiles.json"
STATUSES = {"ready", "shared-backend", "backend-pending", "blocked", "separate-backend"}


def load():
    return json.loads(REGISTRY.read_text())


def cmd_list(registry, group=None):
    rows = registry["devices"]
    if group:
        rows = [row for row in rows if row["group"] == group]
    print(f"{'device':16} {'soc':24} {'backend':18} {'status':18} {'display'}")
    print("-" * 100)
    for row in rows:
        display = row.get("display") or {}
        size = f"{display.get('width')}x{display.get('height')}" if display.get("width") else "none"
        print(f"{row['id']:16} {str(row.get('soc'))[:24]:24} {row['backend']:18} {row['qemu_status']:18} {display.get('driver') or 'none'} {size}")


def cmd_check(registry):
    errors = []
    ids = [row["id"] for row in registry["devices"]]
    qemu_count = sum(
        row["backend"].startswith("qemu-esp32")
        for row in registry["devices"]
    )
    native_count = sum(
        row["backend"] == "esp-emulator-native"
        for row in registry["devices"]
    )
    if len(ids) != len(set(ids)):
        errors.append("duplicate device ids")
    for row in registry["devices"]:
        if row["qemu_status"] not in STATUSES:
            errors.append(f"{row['id']}: bad status {row['qemu_status']}")
    summary = registry.get("validation_matrix", {}).get("result", "")
    qemu_summary = f"{qemu_count} QEMU-backed ESP32"
    native_summary = "Tab5 through esp-emu"
    if qemu_summary not in summary:
        errors.append(f"validation summary must contain {qemu_summary!r}")
    if native_count and native_summary not in summary:
        errors.append(f"validation summary must contain {native_summary!r}")
    print("QEMU_PROFILES_OK" if not errors else "\n".join(errors))
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--group")
    parser.add_argument("--device")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    registry = load()
    if args.device:
        for row in registry["devices"]:
            if row["id"] == args.device:
                print(json.dumps(row, ensure_ascii=False, indent=2))
                return 0
        raise SystemExit(f"unknown device: {args.device}")
    if args.check:
        raise SystemExit(cmd_check(registry))
    cmd_list(registry, args.group)


if __name__ == "__main__":
    main()
