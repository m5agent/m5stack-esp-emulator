#!/usr/bin/env python3
"""Replay a frozen runtime receipt from its exact upstream Git preimages.

Only a new output directory is modified. The developer checkout and its Git
index are read-only; no download, reset or firmware execution is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("receipt path must be repository-relative")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    record = json.loads(args.receipt.read_text())
    expected = record["files"]
    patches = []
    touched = set()
    for name, checksum in record["patches"].items():
        patch = ROOT / safe_relative(name)
        if digest(patch) != checksum:
            raise ValueError("patch digest mismatch: " + name)
        patches.append(patch)
        touched.update(line[6:] for line in patch.read_text().splitlines() if line.startswith("+++ b/"))
    if touched != set(expected):
        raise ValueError("receipt does not cover the exact patch file set")
    args.out_dir.mkdir(parents=True, exist_ok=False)
    replay = args.out_dir / "source"
    replay.mkdir()
    subprocess.run(["git", "init", "-q", str(replay)], check=True, capture_output=True)
    commit = record["qemu"]["commit"]
    upstream = {}
    for name in sorted(touched):
        path = safe_relative(name)
        result = subprocess.run(["git", "show", commit + ":" + name], cwd=args.source_dir, capture_output=True)
        if result.returncode:
            # A patch-created file must actually be absent from the upstream
            # tree; all other object/database errors are fatal.
            listing = subprocess.run(["git", "ls-tree", commit, "--", name], cwd=args.source_dir,
                                     capture_output=True, check=True)
            if listing.stdout:
                raise RuntimeError("cannot read upstream file: " + name)
            upstream[name] = None
        else:
            upstream[name] = result.stdout
            target = replay / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(result.stdout)
    def apply(patch, reverse=False, check=False):
        command = ["git", "apply"]
        if reverse:
            command.append("--reverse")
        if check:
            command.append("--check")
        result = subprocess.run(command + [str(patch)], cwd=replay, capture_output=True)
        if result.returncode:
            raise RuntimeError(patch.name + ": " + result.stderr.decode(errors="replace"))
    def verify_map():
        for name, checksum in expected.items():
            if digest(replay / name) != checksum:
                raise ValueError("replayed source digest mismatch: " + name)
    for patch in patches:
        apply(patch, check=True)
        apply(patch)
    verify_map()
    for patch in reversed(patches):
        apply(patch, reverse=True, check=True)
        apply(patch, reverse=True)
    for name, data in upstream.items():
        target = replay / name
        if data is None:
            if target.exists():
                raise ValueError("patch-created file survived reverse replay: " + name)
        elif target.read_bytes() != data:
            raise ValueError("reverse replay differs from upstream: " + name)
    for patch in patches:
        apply(patch, check=True)
        apply(patch)
    verify_map()
    result = {"reverse_check": True, "exact_upstream_preimage": True,
              "forward_check": True, "roundtrip_identical": True,
              "file_count": len(expected), "patch_count": len(patches)}
    (args.out_dir / "validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
