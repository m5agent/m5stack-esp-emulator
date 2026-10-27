#!/usr/bin/env python3
"""Bound source PR contents, including blobs deleted later in branch history.

Raw execution artifacts belong outside Git. Small evidence summaries are
allowed; runtime assets and reviewed source fixtures remain ordinary source.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[2]
MIB = 1024 * 1024
MAX_NEW_BLOB_BYTES = 150 * MIB
MAX_BLOB_BYTES = 10 * MIB
MAX_SUMMARY_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = MIB
SUMMARY_SUFFIXES = {".md", ".json", ".txt"}


def git(*args: str, data: bytes | None = None) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT, input=data)


def inspect(base: str, head: str) -> dict:
    # Resolve user-supplied refs first so later commands receive full object IDs.
    base = git("rev-parse", "--verify", f"{base}^{{commit}}").decode().strip()
    head = git("rev-parse", "--verify", f"{head}^{{commit}}").decode().strip()
    objects = git("rev-list", "--objects", head, f"^{base}")
    names = {line.split(b" ", 1)[0].decode(): line.partition(b" ")[2].decode()
             for line in objects.splitlines()}
    records = git("cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                  data="".join(oid + "\n" for oid in names).encode())
    blobs = [(oid, int(size), names.get(oid, ""))
             for line in records.decode().splitlines()
             for oid, kind, size in [line.split()] if kind == "blob"]
    errors = []
    total = sum(size for _, size, _ in blobs)
    if total > MAX_NEW_BLOB_BYTES:
        errors.append(f"new blob content {total} exceeds {MAX_NEW_BLOB_BYTES} bytes")
    for _, size, name in blobs:
        if size > MAX_BLOB_BYTES:
            errors.append(f"blob exceeds {MAX_BLOB_BYTES} bytes: {name}")

    # Inspect each commit, so adding then deleting a ZIP cannot bypass the gate.
    # A PR checkout may be GitHub's merge commit. Evidence already present at
    # the exact target path/object is inherited, including on its second parent.
    inherited = {}
    for row in git("ls-tree", "-r", "-z", base, "--", "docs/evidence/").split(b"\0"):
        if row:
            metadata, path = row.split(b"\t", 1)
            inherited[path.decode()] = metadata.split()[2].decode()
    evidence = {}
    for commit in git("rev-list", head, f"^{base}").decode().splitlines():
        paths = git("diff-tree", "--root", "-m", "--no-commit-id", "--name-only",
                    "--diff-filter=AM", "-r", "-z", commit, "--", "docs/evidence/")
        for raw_path in set(paths.split(b"\0")) - {b""}:
            path = raw_path.decode()
            oid = git("rev-parse", f"{commit}:{path}").decode().strip()
            if inherited.get(path) == oid:
                continue
            size = int(git("cat-file", "-s", oid))
            evidence[oid] = size
            if PurePosixPath(path).suffix.lower() not in SUMMARY_SUFFIXES:
                errors.append(f"raw evidence is not source: {path}")
            if size > MAX_SUMMARY_BYTES:
                errors.append(f"evidence summary exceeds {MAX_SUMMARY_BYTES} bytes: {path}")
            else:
                try:
                    body = git("cat-file", "blob", oid).decode("utf-8")
                    if "\0" in body:
                        raise ValueError("NUL is not text")
                    if PurePosixPath(path).suffix.lower() == ".json":
                        json.loads(body)
                except (UnicodeError, ValueError):
                    errors.append(f"evidence summary must be UTF-8 text or valid JSON: {path}")
    evidence_bytes = sum(evidence.values())
    if evidence_bytes > MAX_EVIDENCE_BYTES:
        errors.append(f"new evidence summaries exceed {MAX_EVIDENCE_BYTES} bytes")
    return {"status": "FAIL" if errors else "PASS", "base": base, "head": head,
            "new_blobs": len(blobs), "new_blob_bytes": total,
            "new_evidence_bytes": evidence_bytes, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="target branch commit")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    result = inspect(args.base, args.head)
    print(json.dumps(result, indent=2))
    return int(bool(result["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
