#!/usr/bin/env python3
"""Materialize hash-pinned M5UI source corrections for an explicit candidate lane.

This does not build, flash or change reference firmware. The output modules
must be uploaded with the probe through Device Service and classified apart
from the default-firmware result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / "patches/uiflow2-api/0001-m5ui-native-marshalling.patch"
MANIFEST = PATCH.with_suffix(".json")


def prepare(source_root: Path, output: Path) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commit = subprocess.check_output(["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True).strip()
    if output.exists():
        raise ValueError("candidate output must be a new directory")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for entry in manifest["files"]:
            source = source_root / entry["path"]
            raw = source.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["preimage_sha256"]:
                raise ValueError("candidate source preimage does not match: " + entry["path"])
            copied = work / entry["path"]
            copied.parent.mkdir(parents=True, exist_ok=True)
            copied.write_bytes(raw)
        subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(PATCH)], cwd=work, check=True, capture_output=True)
        subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=work, check=True, capture_output=True)
        candidates = {}
        for entry in manifest["files"]:
            raw = (work / entry["path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["candidate_sha256"]:
                raise ValueError("patched candidate digest does not match: " + entry["path"])
            candidates[entry["candidate_module"]] = raw
    output.mkdir(parents=True)
    for name, raw in candidates.items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    support_files = []
    for name, source in manifest.get("support_modules", {}).items():
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(source, encoding="utf-8")
        support_files.append({"path": name, "sha256": hashlib.sha256(source.encode()).hexdigest()})
    provenance = {**manifest,
                  "patch_sha256": hashlib.sha256(PATCH.read_bytes()).hexdigest(),
                  "source_commit_actual": commit,
                  "source_commit_matches_manifest": commit == manifest["commit"],
                  "source_admission": "exact-commit" if commit == manifest["commit"]
                  else "all-reviewed-file-preimages-match",
                  "support_files": support_files,
                  "candidate_scope": "uploaded-source override; reference firmware unchanged"}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uiflow-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.uiflow_root, args.out_dir)
    print(json.dumps({"status": result["status"], "commit": result["commit"], "files": len(result["files"])}))


if __name__ == "__main__":
    main()
