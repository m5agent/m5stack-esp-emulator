#!/usr/bin/env python3
"""Prepare the native C6 MWDT probe in an isolated PlatformIO directory."""
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--launcher-source", required=True, type=Path)
    parser.add_argument("--archives", required=True, type=Path)
    parser.add_argument("--core-dir", required=True, type=Path)
    parser.add_argument("--off-stages", action="store_true", help="Build the OFF/zero-stage control instead of source-clock cases")
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
    shutil.copy2(HERE / ("off-main.cpp" if args.off_stages else "main.cpp"), out / "src/main.cpp")
    shutil.copy2(HERE / "partitions.csv", out / "partitions.csv")
    shutil.copy2(launcher / "boards/_jsonfiles/esp32c6.json", out / "boards/esp32c6.json")
    shutil.copytree(launcher / "boards/_jsonfiles", out / "boards/_jsonfiles")
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
    print("Prepared MWDT probe; build only with pio run -e arduino-nesso-n1 -j 2")


if __name__ == "__main__":
    main()
