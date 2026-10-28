#!/usr/bin/env python3
"""Rebuild one pinned GFX translation unit into an independent candidate image.

Existing source, cached objects and reference images are read-only. Reuse the
original compiler/link commands, replace only the corrected object in a cloned
static library, and write ELF/BIN/full-flash outputs below a new directory.
This is an incremental build with an explicit preimage, not a cold-build claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))
from firmware_analysis import parse_partition_table


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def segment(command, required):
    parts, current = [], []
    for word in shlex.split(command):
        if word == "&&":
            parts.append(current)
            current = []
        else:
            current.append(word)
    parts.append(current)
    return next(part for part in parts if required in part or any(required in word for word in part))


def build(args):
    args.out_dir.mkdir(parents=True, exist_ok=False)
    out = args.out_dir.resolve()
    source_root = (args.build_root / "uiflow").resolve()
    build_root = args.cached_build or source_root / "m5stack/build-M5STACK_CoreS3"
    build_root = build_root.resolve()
    manifest_path = args.manifest.resolve()
    manifest = json.loads(manifest_path.read_text())
    original = source_root / manifest["path"]
    if digest(original) != manifest["preimage_sha256"]:
        raise ValueError("translation-unit source preimage does not match the pinned correction")
    patch_root = out / "source"
    copied = patch_root / manifest["path"]
    copied.parent.mkdir(parents=True)
    copied.write_bytes(original.read_bytes())
    patch = manifest_path.with_suffix(".patch")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=patch_root, check=True, capture_output=True)
    subprocess.run(["git", "apply", str(patch)], cwd=patch_root, check=True, capture_output=True)
    subprocess.run(["git", "apply", "--reverse", "--check", str(patch)], cwd=patch_root, check=True, capture_output=True)
    if digest(copied) != manifest["candidate_sha256"]:
        raise ValueError("translation-unit candidate digest does not match the correction")
    additional = []
    for manifest_path in args.extra_manifest:
        entry = json.loads(manifest_path.read_text())
        if entry["path"] != manifest["path"]:
            raise ValueError("this incremental build only replaces the single pinned translation unit")
        current = digest(copied)
        if current == entry["preimage_sha256"]:
            expected = entry["candidate_sha256"]
        elif current == entry.get("stack_preimage_sha256"):
            expected = entry["stack_candidate_sha256"]
        else:
            raise ValueError("additional correction preimage does not match the explicit patch stack")
        additional_patch = manifest_path.with_suffix(".patch").resolve()
        subprocess.run(["git", "apply", "--check", str(additional_patch)], cwd=patch_root, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(additional_patch)], cwd=patch_root, check=True, capture_output=True)
        if digest(copied) != expected:
            raise ValueError("additional correction candidate digest does not match")
        additional.append({**entry, "patch_sha256": digest(additional_patch)})
    base = args.base_image.read_bytes()
    table = parse_partition_table(base, image_size=args.flash_size)
    apps = [entry for entry in table["partitions"] if entry["type"] == 0]
    if not table["valid"] or len(apps) != 1:
        raise ValueError("the incremental fixture requires one unambiguous application partition")
    app = apps[0]
    original_bin = (build_root / "micropython.bin").read_bytes()
    if base[app["offset"]:app["offset"] + len(original_bin)] != original_bin:
        raise ValueError("base image is not bound to the cached application build")
    receipt = {"status": "BUILDING", "kind": "incremental-candidate-firmware", "cold_build": False,
               "source_correction": manifest, "patch_sha256": digest(patch), "base_sha256": hashlib.sha256(base).hexdigest(),
               "additional_corrections": additional, "compiled_source_sha256": digest(copied),
               "cached_app_sha256": hashlib.sha256(original_bin).hexdigest(), "cached_elf_sha256": digest(build_root / "micropython.elf"),
               "application_partition": app, "stages": []}
    def save():
        (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    def run(label, command):
        started = time.monotonic()
        with (out / (label + ".log")).open("wb") as log:
            result = subprocess.run(command, cwd=build_root, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        receipt["stages"].append({"label": label, "argv": command, "exit_code": result.returncode, "seconds": round(time.monotonic()-started, 3)})
        save()
        if result.returncode:
            raise RuntimeError(label + " failed; inspect its retained log")
    save()
    commands = json.loads((build_root / "compile_commands.json").read_text())
    original_compile = next(entry for entry in commands if entry["file"] == str(original))
    compile_args = shlex.split(original_compile["command"])
    object_file = out / (original.name + ".obj")
    compile_args[compile_args.index("-o") + 1] = str(object_file)
    compile_args[compile_args.index("-c") + 1] = str(copied)
    run("compile", compile_args)
    original_library = build_root / "esp-idf/M5Unified/libM5Unified.a"
    library = out / "libM5Unified.a"
    shutil.copy2(original_library, library)
    receipt["cached_library_sha256"] = digest(original_library)
    compiler = Path(compile_args[0])
    ar = compiler.with_name(compiler.name.removesuffix("g++") + "ar")
    members = subprocess.check_output([str(ar), "t", str(library)], text=True).splitlines()
    if members.count(object_file.name) != 1:
        raise ValueError("translation-unit archive member is ambiguous")
    run("archive", [str(ar), "r", str(library), str(object_file)])
    ninja = args.build_root / "build-tools/ninja"
    lines = subprocess.check_output([str(ninja), "-C", str(build_root), "-t", "commands", "micropython.elf"], text=True).splitlines()
    link_line = next(line for line in reversed(lines) if " -o micropython.elf " in line)
    link_args = segment(link_line, "-o")
    elf = out / "micropython.elf"
    link_args[link_args.index("-o") + 1] = str(elf)
    for index, word in enumerate(link_args):
        if word == "esp-idf/M5Unified/libM5Unified.a":
            link_args[index] = str(library)
        elif word.startswith("-Wl,--Map="):
            link_args[index] = "-Wl,--Map=" + str(out / "micropython.map")
        elif word.startswith("-Wl,--dependency-file="):
            link_args[index] = "-Wl,--dependency-file=" + str(out / "micropython.d")
    run("link", link_args)
    lines = subprocess.check_output([str(ninja), "-C", str(build_root), "-t", "commands", "gen_project_binary"], text=True).splitlines()
    image_line = next(line for line in reversed(lines) if "elf2image" in line)
    image_args = segment(image_line, "elf2image")
    binary = out / "micropython.bin"
    image_args[image_args.index("-o") + 1] = str(binary)
    image_args = [str(elf) if word == str(build_root / "micropython.elf") else word for word in image_args]
    run("elf2image", image_args)
    raw = binary.read_bytes()
    if len(raw) > app["size"]:
        raise ValueError("candidate application exceeds its partition")
    merged = bytearray(base)
    start, end = app["offset"], app["offset"] + app["size"]
    merged[start:end] = b"\xff" * app["size"]
    merged[start:start+len(raw)] = raw
    if merged[:start] != base[:start] or merged[end:] != base[end:]:
        raise ValueError("candidate changed bytes outside its application partition")
    image = out / "candidate-full-flash.bin"
    image.write_bytes(merged)
    receipt.update(status="BUILT_NOT_EXECUTED", candidate_elf_sha256=digest(elf), candidate_app_sha256=digest(binary),
                   candidate_full_flash_sha256=digest(image), outside_application_unchanged=True,
                   original_source_unchanged=digest(original) == manifest["preimage_sha256"],
                   original_library_unchanged=digest(original_library) == receipt["cached_library_sha256"])
    save()
    print(json.dumps({key: receipt[key] for key in ("status", "candidate_full_flash_sha256", "outside_application_unchanged", "original_source_unchanged", "original_library_unchanged")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--base-image", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--flash-size", type=lambda value: int(value, 0), default=16 << 20)
    parser.add_argument("--manifest", type=Path, default=ROOT / "patches/uiflow2-api/0003-display-raw-buffer-length.json")
    parser.add_argument("--cached-build", type=Path, help="Explicit matching cached build for a board other than CoreS3")
    parser.add_argument("--extra-manifest", type=Path, action="append", default=[])
    build(parser.parse_args())
