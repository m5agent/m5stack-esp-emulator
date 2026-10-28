#!/usr/bin/env python3
"""Prepare hash-checked candidate Python modules from reviewed UIFlow patches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]

CANDIDATES = {
    "ble-uuid32": {
        "manifest": ROOT / "patches/uiflow2-api/0021-ble-advertising-uuid32.json",
        "patch": ROOT / "patches/uiflow2-api/0021-ble-advertising-uuid32.patch",
    },
    "modbus-transform": {
        "manifest": ROOT / "patches/uiflow2-api/0022-modbus-transform-frame.json",
        "patch": ROOT / "patches/uiflow2-api/0022-modbus-transform-frame.patch",
    },
    "modbus-async": {
        "manifest": ROOT / "patches/uiflow2-api/0023-modbus-async-socket.json",
        "patch": ROOT / "patches/uiflow2-api/0023-modbus-async-socket.patch",
    },
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def prepare(name, source_root, out_dir):
    definition = CANDIDATES[name]
    metadata = json.loads(definition["manifest"].read_text(encoding="utf-8"))
    patch = definition["patch"]
    if digest(patch.read_bytes()) != metadata["patch_sha256"]:
        raise ValueError("patch digest differs from its reviewed metadata")
    out_dir.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="m5-uiflow-candidate-") as temporary:
        work = Path(temporary)
        for row in metadata["files"]:
            source = source_root / row["path"]
            payload = source.read_bytes()
            if digest(payload) != row["preimage_sha256"]:
                raise ValueError("official source preimage differs: " + row["path"])
            target = work / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        subprocess.run(
            ["patch", "-p1", "--batch", "--forward", "-i", str(patch)],
            cwd=work,
            check=True,
            capture_output=True,
        )
        rows = []
        for row in metadata["files"]:
            candidate = (work / row["path"]).read_bytes()
            if digest(candidate) != row["candidate_sha256"]:
                raise ValueError("applied source postimage differs: " + row["path"])
            guest_name = row["guest_file"]
            (out_dir / guest_name).write_bytes(candidate)
            rows.append({
                "path": row["path"],
                "guest_file": guest_name,
                "preimage_sha256": row["preimage_sha256"],
                "candidate_sha256": row["candidate_sha256"],
            })
    receipt = {
        "schema_version": 1,
        "candidate": name,
        "source_commit": metadata["source_commit"],
        "patch_sha256": metadata["patch_sha256"],
        "files": rows,
    }
    (out_dir / "candidate.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", choices=tuple(CANDIDATES), required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    receipt = prepare(args.candidate, args.source_root.resolve(), args.out_dir.resolve())
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
