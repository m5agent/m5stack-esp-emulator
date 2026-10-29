#!/usr/bin/env python3
"""Build an open-source browser composer; never fetch firmware or ROMs."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE_COMMIT = "6cb4e86540eca0d9ba62500a298385c9d863c8be"
SOURCE_URL = "https://github.com/littlefs-project/littlefs"
SOURCE_HASHES = {
    "lfs.c": "a36d6a095785ddea9571d541d68d3e4ef01d5b255a99d17d3f07fb6ea60ea132",
    "lfs.h": "b1befd7288d08815accc8f9af744c55686c0b9e3ac0061c32ceee38a1b3eb96d",
    "lfs_util.c": "f2fbde533670560434bd9f5a547174cc7c5a4670a02c47b4bd85180dced8b2ec",
    "lfs_util.h": "548d46aa524dc7449e16739286c1a422a52f9de727ff0be0c2ffc5593f5ca981",
    "LICENSE.md": "0cb4ff1daf5fdc1359c6a6ee3116092f08fc100c9d58b1b77ab17bfd801f856d",
}
KIND = "m5stack-browser-littlefs"
FS_CONFIG = {"block_size": 4096, "read_size": 128, "prog_size": 32,
             "lookahead_size": 128, "block_cycles": 100, "cache_size": 128,
             "name_max": 255, "disk_version": 0}
RAW_BASE_URL = "https://m5burner-cdn.m5stack.com/community/1/1897200000000001950/2102696305989775362/bin/2102696305989775363.bin"
FIXTURE_HASHES = {
    "boot.py": "8fc4849761e7bdc252c71759006736f1e5dba98ed486bd934031ac4a08647c33",
    "main.py": "7672397edc3bff5256015c5d857fa3b4c53cba814bac6a982fb7eeb521cef3cb",
}
SOURCE_SHA256 = "cd8cf040b91a824111aba8eead93ffaec8a1ae2969d1fde1a740fd27f3385f60"
PINNED = {
    "raw_base": {"size": 16121856, "sha256": "1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264"},
    "normalized_base": {"size": 16777216, "sha256": "ddad233fb05925421de7a2aad1b0c18ce0e947d5820b318eaca2b1e82464ac73"},
    "composed_firmware": {"size": 16777216, "sha256": "78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f"},
}
WALLCLOCK_FIXTURE_ID = "cores3-wasm-lvgl-wallclock-v1"
WALLCLOCK_SOURCE_SHA256 = "4d60594952ef5af609084fc519e85b7064349b0782da35836b8c1673cdd73ecf"
WALLCLOCK_FIXTURE_HASHES = {
    "boot.py": "8fc4849761e7bdc252c71759006736f1e5dba98ed486bd934031ac4a08647c33",
    "candidate_lvgl_loop.py": "0a460dbbd04838811238dd9022044f4b5e85f76629e44f8b7ba8fb057710363e",
    "main.py": "e793b5ded4dc81510022723b8e10696a93d0cc4122c6cb5e58000a8ce9b84858",
}
WALLCLOCK_PINNED = {**PINNED, "composed_firmware": {
    "size": 16777216, "sha256": "e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554"}}
WALLCLOCK_ASSET_DIRECTORY = "fixtures/cores3-lvgl-wallclock"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def wallclock_sources(directory: Path) -> dict[str, bytes]:
    """Read only the separate, explicitly pinned three-file candidate."""
    contract = json.loads((directory / "contract.json").read_text())
    identity = contract["identity"]
    if (contract["fixture"] != WALLCLOCK_FIXTURE_ID
            or identity["files"] != WALLCLOCK_FIXTURE_HASHES
            or identity["source_sha256"] != WALLCLOCK_SOURCE_SHA256
            or any({key: identity[name][key] for key in expected} != expected
                   for name, expected in WALLCLOCK_PINNED.items())):
        raise ValueError("wallclock fixture contract changed: review composer pins first")
    files = {name: (directory / name).read_bytes() for name in sorted(WALLCLOCK_FIXTURE_HASHES)}
    if any(digest(data) != WALLCLOCK_FIXTURE_HASHES[name] for name, data in files.items()):
        raise ValueError("wallclock fixture source SHA256 mismatch")
    bundle = json.dumps({name: data.decode("utf-8") for name, data in files.items()},
                        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if digest(bundle) != WALLCLOCK_SOURCE_SHA256:
        raise ValueError("wallclock source bundle SHA256 mismatch")
    return files


def wallclock_metadata() -> dict:
    return {"id": WALLCLOCK_FIXTURE_ID, **WALLCLOCK_PINNED, "base_url": RAW_BASE_URL,
            "source_sha256": WALLCLOCK_SOURCE_SHA256,
            "vfs": {"offset": 11141120, "size": 4980736},
            "source_files": dict(WALLCLOCK_FIXTURE_HASHES),
            "source_assets": {name: "wallclock." + name for name in WALLCLOCK_FIXTURE_HASHES},
            "clock_divisor": 1, "scheduler_candidate": "sdk-python-single-schedule-v1",
            "base_file_count": 17, "derived_file_count": 18, "preserved_file_count": 15}


def sources(cache: Path, *, offline: bool) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, expected in SOURCE_HASHES.items():
        path = cache / name
        if path.is_symlink():
            raise ValueError("littlefs source cache cannot contain symlinks")
        if not path.exists():
            if offline:
                raise ValueError(f"missing pinned offline source: {name}")
            url = f"https://raw.githubusercontent.com/littlefs-project/littlefs/{SOURCE_COMMIT}/{name}"
            with urllib.request.urlopen(url, timeout=60) as response:
                raw = response.read(1024 * 1024 + 1)
            if digest(raw) != expected:
                raise ValueError(f"littlefs source SHA256 mismatch: {name}")
            path.write_bytes(raw)
        if digest(path.read_bytes()) != expected:
            raise ValueError(f"littlefs source SHA256 mismatch: {name}")
        result[name] = path
    return result


def build(output: Path, cache: Path, emcc: Path, fixture: Path, *, offline: bool = False,
          wallclock_fixture: Path | None = None) -> dict:
    output, cache, emcc, fixture = (p.resolve() for p in (output, cache, emcc, fixture))
    if output == ROOT or output in ROOT.parents or any(p == output or p in output.parents for p in (ROOT / "platform", ROOT / "devices", ROOT / "scripts", ROOT / "tests", ROOT / ".git")):
        raise ValueError("generated composer must stay outside source directories")
    if output.exists() and any(output.iterdir()):
        try:
            previous = json.loads((output / "manifest.json").read_text())
        except (OSError, ValueError) as error:
            raise ValueError("refusing to overwrite an unowned output directory") from error
        if previous.get("kind") != KIND:
            raise ValueError("output belongs to another artifact")
    version_file = emcc.parent / "emscripten-version.txt"
    if version_file.read_text().strip().strip('"') != "3.1.50":
        raise ValueError("this composer requires pinned Emscripten 3.1.50")
    environment = os.environ.copy()
    config = emcc.parents[2] / ".emscripten"
    if config.is_file():
        environment["EM_CONFIG"] = str(config)
    source = sources(cache, offline=offline)
    contract = json.loads((fixture / "contract.json").read_text())
    for key, expected in PINNED.items():
        if {k: contract["identity"][key][k] for k in expected} != expected:
            raise ValueError("fixture contract changed: review composer pins first")
    if contract["identity"]["source_sha256"] != SOURCE_SHA256 or contract["identity"]["files"] != FIXTURE_HASHES:
        raise ValueError("fixture sources changed: review composer pins first")
    fixture_files = {}
    for name in ("boot.py", "main.py"):
        raw = (fixture / name).read_bytes()
        if digest(raw) != FIXTURE_HASHES[name]:
            raise ValueError(f"fixture source SHA256 mismatch: {name}")
        fixture_files[name] = raw
    wallclock_fixture = (wallclock_fixture or ROOT / "tests/browser-qemu/cores3_lvgl_wallclock").resolve()
    wallclock_files = wallclock_sources(wallclock_fixture)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".littlefs-", dir=output.parent))
    try:
        exports = ["_malloc", "_free", "_m5_lfs_mount", "_m5_lfs_mount_sized", "_m5_lfs_unmount", "_m5_lfs_scan", "_m5_lfs_disk_version", "_m5_lfs_write", "_m5_lfs_read"]
        args = [str(emcc), "-O2", "-std=c11", "-DLFS_MULTIVERSION", "-DLFS_NO_DEBUG", "-DLFS_NO_WARN", "-DLFS_NO_ERROR",
                "-ffile-prefix-map=" + str(cache) + "=littlefs",
                "-ffile-prefix-map=" + str(Path(__file__).resolve().parent) + "=composer",
                "-I", str(cache), str(Path(__file__).with_name("compose.c")), str(source["lfs.c"]), str(source["lfs_util.c"]),
                "-sMODULARIZE=1", "-sEXPORT_ES6=1", "-sEXPORT_NAME=createLittlefs", "-sENVIRONMENT=web,node",
                "-sFILESYSTEM=0", "-sALLOW_MEMORY_GROWTH=1", "-sINITIAL_MEMORY=16MB", "-sMAXIMUM_MEMORY=64MB",
                "-sSTACK_SIZE=64KB", "-sMALLOC=emmalloc", "-sEXPORTED_FUNCTIONS=" + json.dumps(exports, separators=(",", ":")),
                "-o", str(temporary / "littlefs.mjs")]
        subprocess.run(args, env=environment, check=True)
        (temporary / "LICENSE.littlefs").write_bytes(source["LICENSE.md"].read_bytes())
        composer_license_path = ROOT / "LICENSE"
        if not composer_license_path.is_file():
            composer_license_path = Path(__file__).with_name("LICENSE")
        composer_license = composer_license_path.read_bytes()
        (temporary / "LICENSE.composer").write_bytes(composer_license)
        (temporary / "LICENSE.emscripten").write_bytes((emcc.parent / "LICENSE").read_bytes())
        (temporary / "LICENSE.musl").write_bytes((emcc.parent / "system/lib/libc/musl/COPYRIGHT").read_bytes())
        (temporary / "fixture").mkdir()
        for name, raw in fixture_files.items():
            (temporary / "fixture" / name).write_bytes(raw)
        (temporary / WALLCLOCK_ASSET_DIRECTORY).mkdir(parents=True)
        for name, raw in wallclock_files.items():
            (temporary / WALLCLOCK_ASSET_DIRECTORY / name).write_bytes(raw)
        archive = io.BytesIO()
        archive_files = {"littlefs/" + name: path.read_bytes() for name, path in source.items()}
        archive_files.update({"composer/" + name: Path(__file__).with_name(name).read_bytes()
                              for name in ("compose.c", "build.py", "README.md")})
        archive_files["composer/LICENSE"] = composer_license
        archive_files.update({"fixture/" + name: raw for name, raw in fixture_files.items()})
        archive_files["fixture/contract.json"] = (fixture / "contract.json").read_bytes()
        archive_files.update({"wallclock-fixture/" + name: raw for name, raw in wallclock_files.items()})
        archive_files["wallclock-fixture/contract.json"] = (wallclock_fixture / "contract.json").read_bytes()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipped:
            for name, raw in sorted(archive_files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                zipped.writestr(info, raw)
        (temporary / "source.zip").write_bytes(archive.getvalue())
        def asset(path: Path) -> dict:
            raw = path.read_bytes()
            return {"path": path.relative_to(temporary).as_posix(), "bytes": len(raw), "sha256": digest(raw)}
        assets = {"module": asset(temporary / "littlefs.mjs"), "wasm": asset(temporary / "littlefs.wasm"),
                  "license": asset(temporary / "LICENSE.littlefs"), "composer_license": asset(temporary / "LICENSE.composer"),
                  "emscripten_license": asset(temporary / "LICENSE.emscripten"), "musl_license": asset(temporary / "LICENSE.musl"),
                  "source": asset(temporary / "source.zip")}
        assets.update({name: asset(temporary / "fixture" / name) for name in fixture_files})
        assets.update({"wallclock." + name: asset(temporary / WALLCLOCK_ASSET_DIRECTORY / name)
                       for name in wallclock_files})
        manifest = {
            "schema_version": 1, "kind": KIND,
            "source": {"repository": SOURCE_URL, "commit": SOURCE_COMMIT, "tag": "v2.11.3", "license": "BSD-3-Clause", "files": SOURCE_HASHES},
            "build": {"kind": "source-build", "emscripten": "3.1.50", "optimization": "O2", "multiversion": True},
            "fs_config": FS_CONFIG, "assets": assets,
            "partition_mount": {"export": "_m5_lfs_mount_sized", "min_bytes": 8192, "max_bytes": 16777216, "alignment": 4096, "format": False},
            "fixture": {"id": contract["fixture"], **PINNED, "base_url": RAW_BASE_URL,
                        "source_sha256": SOURCE_SHA256,
                        "vfs": {"offset": 11141120, "size": 4980736},
                        "source_files": {name: contract["identity"]["files"][name] for name in fixture_files}},
            "fixtures": {WALLCLOCK_FIXTURE_ID: wallclock_metadata()},
            "firmware_bundled": False, "rom_bundled": False,
        }
        (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        # Only replace files owned by this builder, after successful compilation.
        output.mkdir(parents=True, exist_ok=True)
        for path in temporary.rglob("*"):
            if path.is_file():
                target = output / path.relative_to(temporary)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink():
                    raise ValueError("refusing to replace a symlink in composer output")
                shutil.copyfile(path, target)
        return manifest
    finally:
        shutil.rmtree(temporary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".work/browser-littlefs")
    parser.add_argument("--cache", type=Path, default=ROOT / ".work/browser-littlefs-build/source")
    parser.add_argument("--emcc", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, default=ROOT / "tests/browser-qemu/cores3_lvgl_pir")
    parser.add_argument("--wallclock-fixture-dir", type=Path, default=ROOT / "tests/browser-qemu/cores3_lvgl_wallclock")
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    manifest = build(args.output, args.cache, args.emcc, args.fixture_dir, offline=args.offline,
                     wallclock_fixture=args.wallclock_fixture_dir)
    print(json.dumps({"kind": manifest["kind"], "output": str(args.output), "assets": manifest["assets"]}, sort_keys=True))


if __name__ == "__main__":
    main()
