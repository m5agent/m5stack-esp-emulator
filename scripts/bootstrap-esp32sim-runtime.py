#!/usr/bin/env python3
"""Build and install the pinned Device Service esp32sim executable."""
from argparse import ArgumentParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".work/esp32sim-runtime")
    parser.add_argument("--source", help="Git URL or local repository containing the pinned commit")
    parser.add_argument("--rom-dir", type=Path, default=os.environ.get("ESP32SIM_ROM_DIR"),
                        help="optional directory containing the ESP32-S3 mask ROM ELF")
    args = parser.parse_args()
    lock = json.loads((ROOT / "scripts/esp32sim-runtime.lock.json").read_text())
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rom = None
    if args.rom_dir is not None:
        rom = args.rom_dir / "esp32s3_rev0_rom.elf"
        if not rom.is_file():
            parser.error(f"missing {rom.name} in --rom-dir")
    with tempfile.TemporaryDirectory(prefix=".esp32sim-build-", dir=output) as directory:
        work = Path(directory)
        git = ["git", "-C", directory]
        subprocess.run([*git, "init", "--quiet"], check=True)
        subprocess.run([*git, "fetch", "--depth=1", args.source or lock["repository"], lock["commit"]], check=True)
        subprocess.run([*git, "checkout", "--quiet", "--detach", "FETCH_HEAD"], check=True)
        if subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip() != lock["commit"]:
            raise RuntimeError("esp32sim source does not match the pinned commit")
        target = work / "target"
        subprocess.run(["cargo", "build", "--locked", "--release", "-p", "esp32sim", "--bin", "esp32sim",
                        "--target-dir", str(target)], cwd=work, check=True)
        binary = target / "release" / "esp32sim"
        with binary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = {**lock, "binary_sha256": digest}
        manifest_path = work / "runtime.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        if rom is not None:
            (output / "roms").mkdir(exist_ok=True)
            staged = work / rom.name
            shutil.copyfile(rom, staged)
            staged.replace(output / "roms" / rom.name)
        binary.replace(output / "esp32sim")
        manifest_path.replace(output / "runtime.json")
        print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
