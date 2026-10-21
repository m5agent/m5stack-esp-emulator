#!/usr/bin/env python3
"""Build the dependency-free AArch64 guest compatibility helper."""
from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUEST = ROOT / "tests/cardputer_zero/guest"
OUT = ROOT / ".work/cardputerzero/guest/m5-fb-shim.so"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    source = GUEST / "m5_fb_shim.c"
    if OUT.exists() and OUT.stat().st_mtime >= source.stat().st_mtime:
        print(OUT)
        return

    cross_gcc = shutil.which("aarch64-linux-gnu-gcc")
    llvm_clang = Path("/opt/homebrew/opt/llvm/bin/clang")
    lld = Path("/opt/homebrew/opt/lld/bin/ld.lld")
    if cross_gcc:
        command = [
            cross_gcc,
            "-shared",
            "-fPIC",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-o", str(OUT),
            str(source),
            "-ldl",
        ]
    elif llvm_clang.is_file() and lld.is_file():
        command = [
            str(llvm_clang),
            "--target=aarch64-linux-gnu",
            f"--ld-path={lld}",
            "-nostdlib",
            "-shared",
            "-fPIC",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wl,-soname,m5-fb-shim.so",
            "-o", str(OUT),
            str(source),
        ]
    else:
        raise SystemExit(
            "need aarch64-linux-gnu-gcc or Homebrew llvm+lld to build "
            "the guest framebuffer shim"
        )
    subprocess.run(command, check=True)
    print(OUT)


if __name__ == "__main__":
    main()
