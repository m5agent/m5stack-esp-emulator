#!/usr/bin/env python3
"""Build a matching UIFlow2 Core2 ELF for panic symbolization."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_UIFLOW = ROOT / ".work/uiflow-core2-2.5.3"
DEFAULT_IDF = ROOT / ".work/esp-idf-v5.5.4"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
    ).strip()


def run(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uiflow-repo", type=Path, default=DEFAULT_UIFLOW)
    parser.add_argument("--idf-path", type=Path, default=DEFAULT_IDF)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / ".work/uiflow2-core2-symbols",
    )
    parser.add_argument("--board", default="M5STACK_Core2")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    repo = args.uiflow_repo.resolve()
    idf_path = args.idf_path.resolve()
    board_dir = repo / "m5stack/boards" / args.board
    if not board_dir.is_dir():
        raise SystemExit(f"unknown UIFlow2 board: {args.board}")
    if not (idf_path / "export.sh").is_file():
        raise SystemExit(f"ESP-IDF v5.5.4 tree not found: {idf_path}")

    version = (repo / "m5stack/version.txt").read_text().strip()
    build_dir = repo / "m5stack" / f"build-{args.board}"
    if args.clean and build_dir.exists():
        shutil.rmtree(build_dir)

    env = os.environ.copy()
    env["IDF_PATH"] = str(idf_path)
    env["IDF_PYTHON_ENV_PATH"] = str(
        Path.home() / ".espressif/python_env/idf5.5_py3.13_env"
    )
    idf_python = Path(env["IDF_PYTHON_ENV_PATH"]) / "bin/python"
    if not idf_python.is_file():
        raise SystemExit(f"ESP-IDF Python environment not found: {idf_python}")
    run([str(idf_python), "-m", "pip", "install", "future"], ROOT, env)
    env["PATH"] = f"{idf_path / 'tools'}:{env.get('PATH', '')}"
    export = (
        f"source {idf_path}/export.sh >/dev/null || exit 1; "
        f"export IDF_PATH={idf_path}"
    )
    make = f"make -C {repo / 'm5stack'} BOARD={args.board}"
    run(
        [
            "bash",
            "-c",
            f"{export} && {make} submodules && {make} patch && "
            f"{make} littlefs && {make} build",
        ],
        ROOT,
        env,
    )

    elf_source = build_dir / "micropython.elf"
    app_source = build_dir / "micropython.bin"
    if not elf_source.is_file():
        raise SystemExit(f"build completed without ELF: {elf_source}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    elf_target = args.out_dir / "micropython.elf"
    app_target = args.out_dir / "micropython.bin"
    shutil.copy2(elf_source, elf_target)
    if app_source.is_file():
        shutil.copy2(app_source, app_target)

    result = {
        "profile": "core2-symbols",
        "board": args.board,
        "uiflow_version": version,
        "uiflow_commit": git_head(repo),
        "idf_commit": git_head(idf_path),
        "elf": str(elf_target),
        "elf_sha256": sha256(elf_target),
        "app": str(app_target) if app_target.is_file() else None,
        "app_sha256": sha256(app_target) if app_target.is_file() else None,
    }
    (args.out_dir / "build.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
