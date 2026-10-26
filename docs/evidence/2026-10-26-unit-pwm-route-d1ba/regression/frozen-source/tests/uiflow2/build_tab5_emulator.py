#!/usr/bin/env python3
"""Build the Tab5 UIFlow2 emulator firmware and merged 16 MiB image."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UIFLOW_REPO = Path(
    os.environ.get("UIFLOW_MICROPYTHON_DIR", ROOT / ".work/uiflow-micropython")
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def docker_shell(image: str, repo: Path, command: str) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{repo}:/project",
        "-w",
        "/project/m5stack",
        image,
        "bash",
        "-lc",
        command,
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--uiflow-repo",
        type=Path,
        default=DEFAULT_UIFLOW_REPO,
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / ".work/uiflow2-tab5",
    )
    parser.add_argument("--docker-image", default="uiflow-idf:v5.5.4")
    parser.add_argument("--build-dir", default="build-M5STACK_Tab5-emu")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    repo = args.uiflow_repo.resolve()
    build_dir = repo / "m5stack" / args.build_dir
    if not (repo / "m5stack/boards/M5STACK_Tab5").is_dir():
        raise SystemExit(f"not a UIFlow2 repository: {repo}")
    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)

    base_cmake = (
        "export ADF_PATH=/project/esp-adf; "
        "idf.py "
        "-DMICROPY_BOARD=M5STACK_Tab5 "
        "-DBUILD_WITH_LVGL=0 "
        "-DM5STACK_EMULATOR=1 "
        "-DMICROPY_FROZEN_MANIFEST=/project/m5stack/boards/manifest_emulator.py "
        f"-B{args.build_dir} "
        "-DUSER_C_MODULES=/project/m5stack/cmodules/cmodules.cmake "
        "-DBOARD_TYPE=tab5 "
        "-DCMAKE_EXE_LINKER_FLAGS=-Wl,--allow-multiple-definition"
    )
    run(
        docker_shell(
            args.docker_image,
            repo,
            f"{base_cmake} build",
        ),
        ROOT,
    )

    merged_in_build = build_dir / "tab5-emulator-merged.bin"
    run(
        docker_shell(
            args.docker_image,
            repo,
            (
                f"{base_cmake} merge-bin "
                "--fill-flash-size 16MB "
                f"-o /project/m5stack/{args.build_dir}/tab5-emulator-merged.bin"
            ),
        ),
        ROOT,
    )

    elf_source = build_dir / "micropython.elf"
    image_source = merged_in_build
    if not elf_source.is_file() or not image_source.is_file():
        raise SystemExit("build completed without the expected ELF or merged image")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    elf_target = args.out_dir / "micropython.elf"
    image_target = args.out_dir / "tab5-emulator-merged.bin"
    shutil.copy2(elf_source, elf_target)
    shutil.copy2(image_source, image_target)

    result = {
        "profile": "tab5-emulator",
        "uiflow_repo": str(repo),
        "build_dir": str(build_dir),
        "elf": str(elf_target),
        "elf_sha256": sha256(elf_target),
        "image": str(image_target),
        "image_sha256": sha256(image_target),
        "image_size": image_target.stat().st_size,
        "lvgl_python_bindings": False,
        "display": {"width": 1280, "height": 720, "rotation": 1},
        "touch": {"width": 720, "height": 1280, "driver": "ST7123"},
    }
    (args.out_dir / "build.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
