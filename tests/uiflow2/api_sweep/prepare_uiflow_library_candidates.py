#!/usr/bin/env python3
"""Prepare hash-checked candidate Python modules from reviewed UIFlow patches."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
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
    "m5ble-server-client-index": {
        "manifest": ROOT / "patches/uiflow2-api/0025-m5ble-server-client-index.json",
        "patch": ROOT / "patches/uiflow2-api/0025-m5ble-server-client-index.patch",
        "depends_on": ("ble-uuid32",),
    },
}


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def prepare(name, source_root, out_dir):
    definition = CANDIDATES[name]
    dependency_names = definition.get("depends_on", ())
    dependency_definitions = [CANDIDATES[dependency] for dependency in dependency_names]
    definitions = [*dependency_definitions, definition]
    manifests = [
        (row, json.loads(row["manifest"].read_text(encoding="utf-8")))
        for row in definitions
    ]
    for row, metadata in manifests:
        if digest(row["patch"].read_bytes()) != metadata["patch_sha256"]:
            raise ValueError("patch digest differs from its reviewed metadata")
    out_dir.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="m5-uiflow-candidate-") as temporary:
        work = Path(temporary)
        copied = set()
        for _row, metadata in manifests:
            for entry in metadata["files"]:
                if entry["path"] in copied:
                    continue
                source = source_root / entry["path"]
                payload = source.read_bytes()
                if digest(payload) != entry["preimage_sha256"]:
                    raise ValueError("official source preimage differs: " + entry["path"])
                target = work / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                copied.add(entry["path"])
        dependencies = []
        for dependency, (row, metadata) in zip(dependency_names, manifests[:-1]):
            subprocess.run(
                ["patch", "-p1", "--batch", "--forward", "-i", str(row["patch"])],
                cwd=work,
                check=True,
                capture_output=True,
            )
            for entry in metadata["files"]:
                if digest((work / entry["path"]).read_bytes()) != entry["candidate_sha256"]:
                    raise ValueError(
                        "dependency source postimage differs: " + entry["path"]
                    )
            dependencies.append({
                "candidate": dependency,
                "patch_sha256": metadata["patch_sha256"],
            })
        metadata = manifests[-1][1]
        subprocess.run(
            ["patch", "-p1", "--batch", "--forward", "-i", str(definition["patch"])],
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
        "dependencies": dependencies,
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
