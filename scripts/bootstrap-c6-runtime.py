#!/usr/bin/env python3
"""Build the pinned ESP32-C6 runtime in a new, owned source directory.

Requires native QEMU build prerequisites (compiler, ninja, pkg-config, GLib,
libgcrypt, libgpg-error and libslirp). No system package installation is done.
This is the C6 lane; it does not use the Xtensa Unit runtime patch selection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
QEMU_URL = "https://github.com/espressif/qemu.git"
QEMU_COMMIT = "febae182e132e4055529be423a818225ebddaa3a"
PATCHES = (
    "patches/qemu-esp32c6-uiflow2-adapters/0001-qemu-c6-m5stack-uiflow2-adapters.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0002-nanoc6-board-isolation-gpio.patch",
    "patches/qemu-m5stack-peripherals/0016-gigadevice-status2-qio.patch",
    "patches/qemu-m5stack-peripherals/0017-issi-status2-qio.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0003-modem-syscon-clock-bits.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0004-user-firmware-hot-samples.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0005-c6-uart-timeout-registers.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0006-espressif-riscv-reset-pmp.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0007-wifi-context.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0008-c6-aes-gdma-wiring.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0009-c6-qio-flash-header.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0010-c6-sx1262-hardware-spi.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0011-c6-isolated-wifi-presence.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0012-c6-ble-aes-dma.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0013-c6-lpperi-rng.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0014-c6-nesso-panel-madctl.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0015-c6-spi2-data-length.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0016-c6-spi2-chip-select-routing.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0017-c6-mwdt-pcr-clock.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0018-c6-wifi-tsf-counter.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0019-c6-efuse-lp-subregion.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0020-c6-usb-serial-jtag-endpoints.patch",
    "patches/qemu-esp32c6-uiflow2-adapters/0021-c6-efuse-unprovisioned-defaults.patch",
)
RECEIPT = ".m5-c6-runtime-source.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, cwd=None):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), cwd=cwd, check=True)


def source_files() -> set[str]:
    return {line[6:].split("\t", 1)[0] for patch in PATCHES for line in (ROOT / patch).read_text().splitlines()
            if line.startswith("+++ b/")}


def prepare_source(source: Path) -> dict:
    expected = {patch: digest(ROOT / patch) for patch in PATCHES}
    if source.exists():
        receipt = source / RECEIPT
        if not receipt.is_file():
            raise RuntimeError(f"refusing to modify unowned source directory: {source}")
        record = json.loads(receipt.read_text())
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True).strip()
        if head != QEMU_COMMIT or record.get("patches") != expected:
            raise RuntimeError("source pin or patches changed; use a new --source-dir")
        if set(record.get("files", {})) != source_files():
            raise RuntimeError("source receipt does not cover the patch file set")
        for name, sha in record["files"].items():
            if not (source / name).is_file() or digest(source / name) != sha:
                raise RuntimeError(f"source has local changes: {name}")
        changed = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=source, text=True).splitlines()
        untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard"], cwd=source, text=True).splitlines()
        unexpected = set(changed + untracked) - source_files() - {RECEIPT, "subprojects/.wraplock"}
        if unexpected:
            raise RuntimeError("source has unrelated changes: " + ", ".join(sorted(unexpected)))
        return record
    source.parent.mkdir(parents=True, exist_ok=True)
    run(["git", "init", source])
    run(["git", "remote", "add", "origin", QEMU_URL], source)
    run(["git", "fetch", "--depth", "1", "origin", QEMU_COMMIT], source)
    run(["git", "checkout", "--detach", "FETCH_HEAD"], source)
    for patch in PATCHES:
        run(["git", "apply", "--check", ROOT / patch], source)
        run(["git", "apply", ROOT / patch], source)
    record = {
        "schema_version": 1,
        "qemu": {"url": QEMU_URL, "commit": QEMU_COMMIT},
        "patches": expected,
        "files": {name: digest(source / name) for name in sorted(source_files())},
    }
    (source / RECEIPT).write_text(json.dumps(record, indent=2) + "\n")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / ".work/c6-runtime-source")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 2))
    parser.add_argument("--extra-ldflags", default="", help="e.g. static libgcrypt.a followed by libgpg-error.a")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 64:
        parser.error("--jobs must be between 1 and 64")
    source = args.source_dir.resolve()
    record = prepare_source(source)
    if args.prepare_only:
        return
    run(["pkg-config", "--exists", "glib-2.0", "pixman-1", "slirp", "libgcrypt"])
    build = source / "build"
    build.mkdir(exist_ok=True)
    flags = ["--target-list=riscv32-softmmu", "--disable-werror", "--disable-docs",
             "--enable-slirp", "--enable-gcrypt", "--disable-gtk", "--disable-vnc",
             "--disable-curses", "--disable-tools", "--disable-sdl"]
    if args.extra_ldflags:
        flags.append("--extra-ldflags=" + args.extra_ldflags)
    run([source / "configure", *flags], build)
    run(["ninja", f"-j{args.jobs}", "qemu-system-riscv32"], build)
    binary = build / "qemu-system-riscv32"
    record.update({"binary_sha256": digest(binary), "configure_flags": flags,
                   "rom_sha256": digest(source / "pc-bios/esp32c6-rom.bin"),
                   "source_only_validation": True})
    (build / "build-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    print(f"Built: {binary}\nSHA256: {digest(binary)}\nUse Device Service for functional validation.")


if __name__ == "__main__":
    main()
