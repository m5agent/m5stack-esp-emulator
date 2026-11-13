#!/usr/bin/env python3
"""Prepare an isolated probe or fixed Launcher control without online hooks."""
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
    parser.add_argument("mode", choices=("probe", "launcher"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--launcher-source", required=True, type=Path)
    parser.add_argument("--gfx-source", type=Path)
    parser.add_argument("--archives", required=True, type=Path)
    parser.add_argument("--core-dir", required=True, type=Path)
    args = parser.parse_args()
    pins = json.loads((HERE / "source-pins.json").read_text())
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
    if args.mode == "probe":
        if not args.gfx_source:
            parser.error("--gfx-source is required for the probe")
        gfx = args.gfx_source.resolve()
        subprocess.run(["git", "-C", str(gfx), "rev-parse", "HEAD"], check=True, capture_output=True)
        (out / "src").mkdir(parents=True)
        (out / "lib").mkdir()
        (out / "boards").mkdir()
        shutil.copy2(HERE / "main.cpp", out / "src/main.cpp")
        shutil.copy2(HERE / "partitions.csv", out / "partitions.csv")
        shutil.copy2(launcher / "boards/_jsonfiles/esp32c6.json", out / "boards/esp32c6.json")
        shutil.copytree(launcher / "boards/_jsonfiles", out / "boards/_jsonfiles")
        (out / "lib/M5GFX").symlink_to(gfx, target_is_directory=True)
        include = core / "packages/framework-arduinoespressif32/libraries"
        ini = "\n".join([
            "[platformio]", "boards_dir = boards", "", "[env:arduino-nesso-n1]",
            platform, packages, "framework = arduino", "board = esp32c6",
            "board_build.variants_dir = boards", "board_build.partitions = partitions.csv",
            "build_flags =", "  -DARDUINO_USB_CDC_ON_BOOT=0", "  -DARDUINO_USB_MODE=0",
            f"  -I{include / 'SPI/src'}", f"  -I{include / 'Wire/src'}", "lib_ldf_mode = deep+", "",
        ])
    else:
        shutil.copytree(launcher, out, ignore=shutil.ignore_patterns(".git", ".pio", "__pycache__"))
        ini = (out / "platformio.ini").read_text()
        ini = re.sub(r"^platform =.*$", platform, ini, count=1, flags=re.M)
        ini = re.sub(r"^platform_packages =.*$", packages, ini, count=1, flags=re.M)
        for hook in ("check_submodules.py", "prep_web_files.py", "clang_format.py", "upload_patch.py"):
            ini = re.sub(r"^\s*pre:support_files/" + re.escape(hook) + r"\n", "", ini, flags=re.M)
        ini = re.sub(r"^(\s*-DLAUNCHER=).*$", r'''\g<1>'"3.0.0"' ''', ini, count=1, flags=re.M)
        ini = re.sub(r"^(\s*-DWIFI_ENC_KEY=).*$", r'''\g<1>'"local-control-build-only"' ''', ini, count=1, flags=re.M)
        board = out / "boards/arduino-nesso-n1/platformio.ini"
        board.write_text(board.read_text().replace(
            "m5stack/M5Unified @ ^0.2.17", "m5stack/M5Unified @ 0.2.24\n\tm5stack/M5GFX @ 0.2.31"
        ))
        header = ["#ifndef WEB_FILES_H", "#define WEB_FILES_H", "#include <Arduino.h>",
                  "// Local deterministic gzip of fixed source, without external minifier."]
        for source in sorted((out / "webUi").iterdir()):
            if source.suffix not in (".html", ".css", ".js"):
                continue
            raw = source.read_bytes()
            compressed = gzip.compress(raw, compresslevel=9, mtime=0)
            assert gzip.decompress(compressed) == raw
            name = source.name.replace(".", "_")
            header.append(f"const uint8_t {name}[] PROGMEM = {{")
            for index in range(0, len(compressed), 15):
                header.append("  " + ", ".join(f"0x{byte:02X}" for byte in compressed[index:index + 15]) + ",")
            header.extend(["};", f"const uint32_t {name}_size = {len(compressed)};"])
        header.extend(["#endif", ""])
        (out / "include/webFiles.h").write_text("\n".join(header))
    (out / "platformio.ini").write_text(ini)
    # The caller sets these three variables for every build; never use shared caches.
    env = {"PLATFORMIO_CORE_DIR": str(core), "PLATFORMIO_PACKAGES_DIR": str(core / "packages"),
           "PLATFORMIO_PLATFORMS_DIR": str(core / "platforms")}
    (out / "owned-build-env.json").write_text(json.dumps(env, indent=2) + "\n")
    print(f"Prepared {args.mode}; build only with pio run -e arduino-nesso-n1 -j 2")


if __name__ == "__main__":
    main()
