#!/usr/bin/env python3
"""Explicitly verify historical source blobs; ordinary CI checks metadata only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]


def verify(source_repo: Path, manifest: dict) -> int:
    checked = 0
    for group, record in manifest["groups"].items():
        commit = record["source_snapshot_commit"]
        for relative, expected in record["recorded_tool_hashes"].items():
            result = subprocess.run(
                ["git", "cat-file", "blob", f"{commit}:{relative}"],
                cwd=source_repo, capture_output=True, check=False,
            )
            if result.returncode:
                raise ValueError(f"missing historical source: {group}: {commit}:{relative}")
            if hashlib.sha256(result.stdout).hexdigest() != expected:
                raise ValueError(f"historical source digest mismatch: {group}: {relative}")
            checked += 1
    return checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-repo", required=True, type=Path,
                        help="Independent complete Git checkout containing pinned source commits")
    args = parser.parse_args()
    manifest = json.loads((
        ROOT / "platform/tests/fixtures/historical_tool_provenance.json"
    ).read_text())
    try:
        count = verify(args.source_repo, manifest)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(f"PASS: {count} historical source digests; no current runtime execution was performed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
