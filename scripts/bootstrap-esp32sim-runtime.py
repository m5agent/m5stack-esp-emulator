#!/usr/bin/env python3
"""Build and install the pinned Device Service esp32sim executable."""
from argparse import ArgumentParser
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
S3_ROM = "esp32s3_rev0_rom.elf"
CLASSIC_ROM = "esp32_rev300_rom.elf"
C6_ROM = "esp32c6_rev0_rom.elf"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_asset(source, destination, digest):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha256(destination) != digest:
        raise ValueError(f"SHA-256 mismatch: {source.name}")


def stage_tab5_c6(lock, destination, local_build):
    if local_build:
        for row in lock["files"].values():
            asset = Path(row["path"])
            stage_asset(local_build / asset, destination / asset, row["sha256"])
        return
    archive = lock["archive"]
    limit = 4 << 20
    with urlopen(archive["url"], timeout=60) as response:
        package = response.read(limit + 1)
    if len(package) > limit or hashlib.sha256(package).hexdigest() != archive["sha256"]:
        raise ValueError("Tab5 C6 asset archive size or SHA-256 mismatch")
    with ZipFile(BytesIO(package)) as bundle:
        for row in lock["files"].values():
            data = bundle.read(row["path"])
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError(f"Tab5 C6 asset SHA-256 mismatch: {row['path']}")
            path = destination / row["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (destination / "NOTICE.txt").write_bytes(bundle.read("NOTICE.txt"))
        (destination / "licenses").mkdir()
        for name in bundle.namelist():
            path = Path(name)
            if path.parent == Path("licenses") and path.suffix == ".txt":
                (destination / path).write_bytes(bundle.read(name))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".work/esp32sim-runtime")
    parser.add_argument("--source", help="Git URL or local repository containing the pinned commit")
    parser.add_argument("--rom-dir", type=Path, default=os.environ.get("ESP32SIM_ROM_DIR"),
                        help="directory containing the pinned Espressif mask ROM ELFs")
    parser.add_argument("--with-classic", action="store_true", help="stage the classic ESP32 ROM")
    parser.add_argument("--with-c6", action="store_true", help="stage the ESP32-C6 ROM")
    tab5 = parser.add_mutually_exclusive_group()
    tab5.add_argument("--with-tab5", action="store_true", help="fetch the pinned Tab5 C6 asset archive")
    tab5.add_argument("--tab5-c6-build", type=Path,
                      help="ESP-Hosted 2.0.13 SDIO build directory matching the Tab5 asset lock")
    args = parser.parse_args()
    lock = json.loads((ROOT / "scripts/esp32sim-runtime.lock.json").read_text())
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.rom_dir is None:
        parser.error("provide --rom-dir or ESP32SIM_ROM_DIR")
    with tempfile.TemporaryDirectory(prefix=".esp32sim-build-", dir=output) as directory:
        work = Path(directory)
        staged = work / "install"
        with_tab5 = args.with_tab5 or args.tab5_c6_build is not None
        roms = [S3_ROM]
        if with_tab5:
            roms += ["esp32p4_rev0_rom.elf", "esp32p4_rev300_rom.elf"]
        if with_tab5 or args.with_c6:
            roms.append(C6_ROM)
        if args.with_classic:
            roms.append(CLASSIC_ROM)
        for name in roms:
            stage_asset(args.rom_dir / name, staged / "roms" / name, lock["roms"][name])
        if with_tab5:
            stage_tab5_c6(lock["tab5_c6"], staged / "tab5-c6", args.tab5_c6_build)
        git = ["git", "-C", directory]
        subprocess.run([*git, "init", "--quiet"], check=True)
        subprocess.run([*git, "fetch", "--depth=1", args.source or lock["repository"], lock["commit"]], check=True)
        subprocess.run([*git, "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True)
        if subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() != lock["commit"]:
            raise RuntimeError("esp32sim source does not match the pinned commit")
        patch = ROOT / "scripts/esp32sim-service-control.patch"
        if sha256(patch) != lock["service_patch_sha256"]:
            raise ValueError("esp32sim service patch SHA-256 mismatch")
        subprocess.run([*git, "apply", "--index", str(patch)], check=True)
        target = work / "target"
        binaries = {"esp32sim": "binary_sha256"}
        if with_tab5:
            binaries["esp32sim-p4"] = "p4_binary_sha256"
        subprocess.run(["cargo", "build", "--locked", "--release", "-p", "esp32sim",
                        "--target-dir", str(target),
                        *(arg for name in binaries for arg in ("--bin", name))],
                       cwd=work, check=True)
        manifest = dict(lock)
        for name, key in binaries.items():
            binary = target / "release" / name
            manifest[key] = sha256(binary)
            binary.replace(staged / name)
        manifest_path = staged / "runtime.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        for asset in staged.rglob("*"):
            if asset.is_file() and asset != manifest_path:
                destination = output / asset.relative_to(staged)
                destination.parent.mkdir(parents=True, exist_ok=True)
                asset.replace(destination)
        manifest_path.replace(output / "runtime.json")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
