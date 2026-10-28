#!/usr/bin/env python3
"""Build a pinned esp32sim WASM runtime into ignored storage; never fetch firmware.

An explicit diagnostic mode can package the independently hashed deployed WASM.
It remains labelled downloaded-diagnostic, never a source-build verification.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
SOURCE_URL = "https://github.com/zhuzhe1983/esp-online-tester.git"
SOURCE_COMMIT = "3cd3db3b7202e9fc559328c7247c11134c0437f9"
RUST_VERSION = "1.99.1"
RUST_FLAGS = "-Cllvm-args=-inline-threshold=2000"
ROM_SHA256 = "c0ce0f338d1de1bdc6efbef1591779a2a42c1ab7d759d3c6ae8ae63a7dd34cfd"
ROM_RELEASE = "20260528"
ROM_ARCHIVE_URL = f"https://github.com/espressif/esp-rom-elfs/releases/download/{ROM_RELEASE}/esp-rom-elfs-{ROM_RELEASE}.tar.gz"
ROM_ARCHIVE_SHA256 = "caa463d3cbef2430a5a35847c1d9f2f152403b17a802050927ff60c8da54fe46"
DIAGNOSTIC_WASM_SHA256 = "8ef640bf8d525c5fec9d071bf12fba43765a5de549c1fcc8f4b4772d3a1fc72a"
CRATES = ["emu-core", "esp-periph", "esp-soc", "xtensa-lx7", "esp32s3", "cli", "wasm", "wasm-jit", "riscv-rv32", "esp32c3", "esp32c6", "esp32", "esp32p4", "esp32s31"]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def command(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, env=env, text=True).strip()


def verified_bytes(path: Path, expected: str) -> bytes:
    data = path.read_bytes()
    if sha256(data) != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}")
    return data


def acquire_rom(path: Path | None, *, fetch: bool = False) -> bytes:
    if path:
        return verified_bytes(path, ROM_SHA256)
    if not fetch:
        raise ValueError("provide --rom <esp32s3_rev0_rom.elf> or explicitly request --fetch-rom")
    request = urllib.request.Request(ROM_ARCHIVE_URL, headers={"User-Agent": "m5stack-public-runtime-bootstrap"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(32 * 1024 * 1024 + 1)
    if len(data) > 32 * 1024 * 1024 or sha256(data) != ROM_ARCHIVE_SHA256:
        raise ValueError("Espressif ROM archive size or SHA-256 mismatch")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = [member for member in archive.getmembers() if Path(member.name).name == "esp32s3_rev0_rom.elf" and member.isfile()]
        if len(members) != 1:
            raise ValueError("Espressif archive does not contain exactly one S3 ROM ELF")
        stream = archive.extractfile(members[0])
        assert stream is not None
        rom = stream.read()
    if sha256(rom) != ROM_SHA256:
        raise ValueError("Espressif S3 ROM SHA-256 mismatch")
    return rom


def source_checkout(path: Path | None, cache: Path) -> Path:
    if path:
        source = path.resolve()
    else:
        source = cache / "source"
        if not source.exists():
            subprocess.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--no-checkout", SOURCE_URL, str(source)], check=True)
            subprocess.run(["git", "sparse-checkout", "init", "--cone"], cwd=source, check=True)
            subprocess.run(["git", "sparse-checkout", "set", *CRATES], cwd=source, check=True)
        subprocess.run(["git", "fetch", "--depth", "1", "origin", SOURCE_COMMIT], cwd=source, check=True)
        subprocess.run(["git", "checkout", "--detach", SOURCE_COMMIT], cwd=source, check=True)
    if command("git", "rev-parse", "HEAD", cwd=source) != SOURCE_COMMIT:
        raise ValueError("source checkout does not match the reviewed commit")
    if command("git", "status", "--porcelain", "--untracked-files=no", cwd=source):
        raise ValueError("source checkout contains modified tracked files")
    # Cargo uses these exact Git objects, not an arbitrary replacement worker.
    vendor = json.loads((ROOT / "platform/web/vendor/esp32sim/source.json").read_text())
    for row in vendor["files"].values():
        data = subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:{row['source_path']}"], cwd=source)
        if sha256(data) != row["sha256"]:
            raise ValueError("runtime glue differs from the reviewed source manifest")
    return source


def build_environment(cache: Path) -> dict[str, str]:
    environment = os.environ.copy()
    # Encoded flags and wrappers otherwise override the flags reported in our
    # receipt, even though the source archive and rustup version are pinned.
    for name in ("CARGO_ENCODED_RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
        environment.pop(name, None)
    environment.update({"RUSTFLAGS": RUST_FLAGS, "CARGO_PROFILE_RELEASE_DEBUG": "0", "CARGO_PROFILE_RELEASE_STRIP": "debuginfo", "CARGO_TARGET_DIR": str(cache / "target")})
    return environment


def source_identity(source: Path) -> dict[str, str]:
    return {
        "cargo_lock_sha256": sha256(subprocess.check_output(["git", "show", f"{SOURCE_COMMIT}:Cargo.lock"], cwd=source)),
        "source_tree": command("git", "rev-parse", f"{SOURCE_COMMIT}^{{tree}}", cwd=source),
    }


def compile_runtime(source: Path, cache: Path, cargo: str) -> tuple[bytes, dict]:
    environment = build_environment(cache)
    version = command(cargo, f"+{RUST_VERSION}", "--version", env=environment)
    rustc = str(Path(cargo).parent / "rustc") if Path(cargo).is_absolute() else "rustc"
    compiler_version = command(rustc, f"+{RUST_VERSION}", "--version", env=environment)
    if not compiler_version.startswith(f"rustc {RUST_VERSION} "):
        raise ValueError("the reviewed Rust compiler version is required")
    # Build exact Git blobs in a new snapshot, excluding untracked/ignored Cargo
    # configuration, assets and user experiments from the source checkout.
    with tempfile.TemporaryDirectory(prefix="source-", dir=cache) as snapshot_name:
        snapshot = Path(snapshot_name)
        archive_data = subprocess.check_output(["git", "archive", SOURCE_COMMIT, "Cargo.toml", "Cargo.lock", "LICENSE", *CRATES], cwd=source)
        with tarfile.open(fileobj=io.BytesIO(archive_data)) as archive:
            for member in archive.getmembers():
                target = snapshot / member.name
                if member.issym() or member.islnk() or target.is_absolute() and snapshot not in target.resolve().parents or ".." in Path(member.name).parts:
                    raise ValueError("source archive contains an unsafe path")
            archive.extractall(snapshot)
        subprocess.run([cargo, f"+{RUST_VERSION}", "build", "--locked", "--offline", "--release", "--target", "wasm32-unknown-unknown", "--package", "esp32sim-wasm"], cwd=snapshot, env=environment, check=True)
    data = (cache / "target/wasm32-unknown-unknown/release/esp32sim_wasm.wasm").read_bytes()
    return data, {
        "kind": "source-build", "rust": compiler_version, "cargo": version,
        "rustflags": RUST_FLAGS, "debug": 0, "strip": "debuginfo",
        "target": "wasm32-unknown-unknown", "locked": True, "offline": True,
        **source_identity(source),
    }


def prepare_runtime(output: Path, wasm: bytes, rom: bytes, build: dict) -> dict:
    if not wasm.startswith(b"\0asm\x01\0\0\0"):
        raise ValueError("runtime is not a WebAssembly 1.0 module")
    if sha256(rom) != ROM_SHA256:
        raise ValueError("S3 ROM is not the reviewed ELF")
    output = output.resolve()
    if output == ROOT or any(path == output or path in output.parents for path in (ROOT / "platform", ROOT / "devices", ROOT / ".git")):
        raise ValueError("runtime binaries must remain outside tracked source directories")
    if output.exists() and any(output.iterdir()) and not (output / "runtime.json").is_file():
        raise ValueError("refusing to overwrite an unowned runtime directory")
    output.mkdir(parents=True, exist_ok=True)
    (output / "esp32sim.wasm").write_bytes(wasm)
    (output / "esp32s3_rev0_rom.elf").write_bytes(rom)
    (output / "LICENSE").write_bytes((ROOT / "platform/web/vendor/esp32sim/LICENSE").read_bytes())
    (output / "ROM_LICENSE").write_bytes((ROOT / "platform/runtime/wasm/LICENSE").read_bytes())
    (output / "NOTICE").write_text("esp32sim: MIT, https://github.com/mikroverk/esp32sim and the pinned esp-online-tester fork.\nESP32-S3 mask ROM ELF: Espressif esp-rom-elfs, Apache-2.0, release " + ROM_RELEASE + ". Firmware is not bundled.\n")
    manifest = {
        "schema_version": 1, "source": {"repository": SOURCE_URL.removesuffix(".git"), "commit": SOURCE_COMMIT, "license": "MIT"},
        "profiles": ["papers3", "stopwatch"], "build": build,
        "wasm": {"path": "esp32sim.wasm", "bytes": len(wasm), "sha256": sha256(wasm)},
        "rom": {"path": "esp32s3_rev0_rom.elf", "bytes": len(rom), "sha256": ROM_SHA256, "source": "https://github.com/espressif/esp-rom-elfs", "release": ROM_RELEASE, "license": "Apache-2.0"},
        "firmware_bundled": False,
    }
    (output / "runtime.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".work/browser-runtime")
    parser.add_argument("--cache", type=Path, default=ROOT / ".work/browser-runtime-build")
    parser.add_argument("--source-checkout", type=Path)
    parser.add_argument("--cargo", default=shutil.which("cargo") or "cargo")
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--fetch-rom", action="store_true")
    parser.add_argument("--diagnostic-wasm", type=Path, help="explicitly package only the pinned online WASM; not a source-build claim")
    args = parser.parse_args()
    try:
        rom = acquire_rom(args.rom, fetch=args.fetch_rom)
        if args.diagnostic_wasm:
            wasm = verified_bytes(args.diagnostic_wasm, DIAGNOSTIC_WASM_SHA256)
            build = {"kind": "downloaded-diagnostic", "rebuild_verified": False, "source": "https://zhuzhe1983.github.io/esp-online-tester/wasm/esp32sim.wasm"}
        else:
            args.cache.mkdir(parents=True, exist_ok=True)
            source = source_checkout(args.source_checkout, args.cache.resolve())
            wasm, build = compile_runtime(source, args.cache.resolve(), args.cargo)
        manifest = prepare_runtime(args.output.resolve(), wasm, rom, build)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"browser runtime bootstrap failed: {error}\n")
    print(json.dumps({"output": str(args.output), "build": manifest["build"]["kind"], "wasm_sha256": manifest["wasm"]["sha256"], "firmware_bundled": False}))


if __name__ == "__main__":
    main()
