#!/usr/bin/env python3
"""Audit archive hashes, byte-exact local sources, ZIP transport and privacy."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

from PIL import Image

ARCHIVE = Path(__file__).resolve().parent
ROOT = ARCHIVE.parents[2]
SCANNER = ARCHIVE.parent / "2026-10-26-unit-source-host-io-d1ba/audit_archive.py"
GENERATED = {"archive-audit.json", "SHA256SUMS"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(write):
    spec = importlib.util.spec_from_file_location("privacy_audit", SCANNER)
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    provenance = json.loads((ARCHIVE / "copy-provenance.json").read_bytes())
    for name, row in provenance["files"].items():
        if "!" in name:
            outer, member = name.split("!", 1)
            with zipfile.ZipFile(scanner.safe(ARCHIVE, outer)) as archive:
                raw = archive.read(member)
        else:
            raw = scanner.safe(ARCHIVE, name).read_bytes()
        source = scanner.safe(ROOT, row["source"])
        need(raw == source.read_bytes(), "source/copy mismatch: " + name)
        need(len(raw) == row["bytes"] and sha(raw) == row["sha256"]
             and row["bytes_changed"] is False, "provenance mismatch: " + name)

    candidates = []
    counts = {"archive_files": 0, "zip_files": 0, "zip_members": 0, "images": 0}

    def inspect(raw, name):
        scanner.refuse_native(raw, name)
        if raw.startswith(b"PK\x03\x04"):
            counts["zip_files"] += 1
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                need(archive.testzip() is None, "ZIP CRC failure")
                need(len(archive.namelist()) == len(set(archive.namelist())), "duplicate ZIP member")
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    need(not path.is_absolute() and ".." not in path.parts
                         and "\\" not in member.filename, "unsafe ZIP member")
                    need((member.external_attr >> 16) & 0o170000 != 0o120000, "ZIP symlink")
                    if not member.is_dir():
                        counts["zip_members"] += 1
                        inspect(archive.read(member), name + "!" + member.filename)
            return
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            with Image.open(io.BytesIO(raw)) as picture:
                picture.load()
                need(picture.width > 0 and picture.height > 0, "empty PNG")
            counts["images"] += 1
            return
        text = raw.decode("utf-8")
        need("\x00" not in text, "unexpected binary/NUL: " + name)
        candidates.extend(scanner.privacy_candidates(text, name))

    for path in sorted(ARCHIVE.rglob("*")):
        need(not path.is_symlink(), "archive symlink")
        if path.is_file() and path.name not in GENERATED:
            counts["archive_files"] += 1
            inspect(path.read_bytes(), path.relative_to(ARCHIVE).as_posix())
    need(not candidates, "unreviewed privacy candidate")
    report = {"schema_version": 1, "status": "PASS", **counts,
              "provenance_sources_verified": len(provenance["files"]),
              "privacy_candidates": candidates, "bytes_preserved": True,
              "scanner_repository_path": SCANNER.relative_to(ROOT).as_posix(),
              "scanner_sha256": sha(SCANNER.read_bytes())}
    encoded = (json.dumps(report, indent=2) + "\n").encode()
    if write:
        (ARCHIVE / "archive-audit.json").write_bytes(encoded)
    else:
        need((ARCHIVE / "archive-audit.json").read_bytes() == encoded, "stale audit")
    sums = "\n".join(sha(p.read_bytes()) + "  " + p.relative_to(ARCHIVE).as_posix()
                     for p in sorted(ARCHIVE.rglob("*"))
                     if p.is_file() and p.name != "SHA256SUMS") + "\n"
    if write:
        (ARCHIVE / "SHA256SUMS").write_text(sums)
    else:
        need((ARCHIVE / "SHA256SUMS").read_text() == sums, "stale checksums")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    run(parser.parse_args().write)
