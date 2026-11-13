#!/usr/bin/env python3
"""Prepare the native NanoC6 TSF or identity probe in an isolated PlatformIO directory."""
import argparse
import gzip
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_bytes(source, commit, path):
    return subprocess.check_output(["git", "-C", str(source), "show", f"{commit}:{path}"])


def copy_git_directory(source, commit, directory, destination):
    """Copy the pinned blobs, ignoring dirty and untracked working-tree files."""
    listing = subprocess.check_output([
        "git", "-C", str(source), "ls-tree", "-r", "-z", commit, "--", directory,
    ])
    for item in listing.split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        mode, kind, oid = metadata.decode().split()
        if kind != "blob" or mode not in ("100644", "100755"):
            raise ValueError("Pinned board directory contains a non-file entry")
        relative = Path(raw_path.decode()).relative_to(directory)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.check_output(["git", "-C", str(source), "cat-file", "blob", oid]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--launcher-source", required=True, type=Path)
    parser.add_argument("--archives", required=True, type=Path)
    parser.add_argument("--core-dir", required=True, type=Path)
    parser.add_argument("--kind", choices=("tsf", "identity"), required=True)
    args = parser.parse_args()
    pins = json.loads((HERE.parent / "nesso_touch_bus_shared/source-pins.json").read_text())
    out = args.out.resolve()
    launcher = args.launcher_source.resolve()
    archives = args.archives.resolve()
    core = args.core_dir.resolve()
    if out.exists():
        parser.error("--out must be a new owned directory")
    commit = subprocess.check_output(
        ["git", "-C", str(launcher), "rev-parse", "HEAD"], text=True
    ).strip()
    if commit != pins["launcher_commit"]:
        parser.error("Launcher checkout does not match source-pins.json")
    for name, expected in pins["archives"].items():
        if digest(archives / name) != expected:
            parser.error(f"Archive hash mismatch: {name}")
    for directory in (args.core_dir, args.core_dir / "packages", args.core_dir / "platforms"):
        if directory.is_symlink():
            parser.error("PlatformIO core/packages/platforms must be owned real directories")
    platform = "platform = " + (archives / "platform-espressif32.zip").as_uri()
    packages = "platform_packages =\n" + "\n".join(
        f"  {name} @ {(archives / archive).as_uri()}"
        for name, archive in (
            ("framework-arduinoespressif32", "esp32-core-3.3.9.tar.xz"),
            ("framework-arduinoespressif32-libs", "launcher-keyboot.tar.gz"),
        )
    )
    (out / "src").mkdir(parents=True)
    (out / "boards").mkdir()
    shutil.copy2(HERE / (args.kind + ".cpp"), out / "src/main.cpp")
    shutil.copy2(HERE / "partitions.csv", out / "partitions.csv")
    board = json.loads(git_bytes(launcher, commit, "boards/_jsonfiles/esp32c6.json"))
    board["build"].update(f_flash="40000000L", flash_mode="dio")
    board["upload"].update(flash_size="4MB", maximum_size=4194304)
    (out / "boards/esp32c6.json").write_text(json.dumps(board, indent=2) + "\n")
    copy_git_directory(launcher, commit, "boards/_jsonfiles", out / "boards/_jsonfiles")
    include = core / "packages/framework-arduinoespressif32/libraries"
    ini = "\n".join([
        "[platformio]", "boards_dir = boards", "", "[env:arduino-nesso-n1]",
        platform, packages, "framework = arduino", "board = esp32c6",
        "board_build.variants_dir = boards", "board_build.partitions = partitions.csv",
        "build_flags =", "  -DARDUINO_USB_CDC_ON_BOOT=0", "  -DARDUINO_USB_MODE=0",
        f"  -I{include / 'SPI/src'}", f"  -I{include / 'Wire/src'}", "lib_ldf_mode = deep+", "",
    ])
    (out / "platformio.ini").write_text(ini)
    # The caller sets these three variables for every build; never use shared caches.
    env = {"PLATFORMIO_CORE_DIR": str(core), "PLATFORMIO_PACKAGES_DIR": str(core / "packages"),
           "PLATFORMIO_PLATFORMS_DIR": str(core / "platforms")}
    (out / "owned-build-env.json").write_text(json.dumps(env, indent=2) + "\n")
    print("Prepared NanoC6 probe; build only with pio run -e arduino-nesso-n1 -j 2")


if __name__ == "__main__":
    main()
