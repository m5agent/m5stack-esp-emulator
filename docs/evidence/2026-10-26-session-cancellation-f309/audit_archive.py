#!/usr/bin/env python3
"""Offline byte/provenance/privacy audit; --write refreshes generated metadata."""
from __future__ import annotations

import argparse
import ast
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
FIXTURE = "source/test_network_lane_cancellation.py.txt"
FIXTURE_SHA = "1748a0180bec30444926b72339c9343587e08d5492b0c41079af00b4be7e76cd"
VALUE_SHA = "2383a794bd060c39ba88684747de22ddaedf8309115d5f86a7c5717ce1e7815b"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(write=False):
    spec = importlib.util.spec_from_file_location("prior_privacy_audit", SCANNER)
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    provenance = json.loads((ARCHIVE / "copy-provenance.json").read_bytes())
    for name, row in provenance["files"].items():
        relative = PurePosixPath(name)
        need(not relative.is_absolute() and ".." not in relative.parts, "unsafe copy path")
        target = ARCHIVE / name
        source = ROOT / row["source"]
        need(not target.is_symlink() and not source.is_symlink(), "symlink in provenance")
        raw = target.read_bytes()
        need(raw == source.read_bytes(), "source/copy byte mismatch: " + name)
        need(digest(raw) == row["sha256"] and len(raw) == row["bytes"]
             and row["bytes_changed"] is False, "provenance mismatch: " + name)

    fixture = (ARCHIVE / FIXTURE).read_bytes()
    need(digest(fixture) == FIXTURE_SHA, "reviewed fixture file changed")
    matches = [node.value.value for node in ast.walk(ast.parse(fixture.decode("utf-8")))
               if isinstance(node, ast.keyword) and node.arg == "password"
               and isinstance(node.value, ast.Constant) and node.value.lineno == 165]
    need(len(matches) == 1 and len(matches[0]) == 24
         and digest(matches[0].encode()) == VALUE_SHA, "synthetic fixture classification changed")

    findings = []
    counts = {"archive_files": 0, "zip_files": 0, "zip_members": 0, "images": 0}

    def inspect(raw, locator):
        scanner.refuse_native(raw, locator)
        if raw.startswith(b"PK\x03\x04"):
            counts["zip_files"] += 1
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                need(archive.testzip() is None, "ZIP CRC failure: " + locator)
                names = archive.namelist()
                need(len(names) == len(set(names)), "duplicate ZIP member")
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    need(not path.is_absolute() and ".." not in path.parts
                         and "\\" not in member.filename, "unsafe ZIP member")
                    need((member.external_attr >> 16) & 0o170000 != 0o120000,
                         "ZIP symlink forbidden")
                    if not member.is_dir():
                        counts["zip_members"] += 1
                        inspect(archive.read(member), locator + "!" + member.filename)
            return
        if raw.startswith((b"\x89PNG\r\n\x1a\n", b"P6\n")):
            with Image.open(io.BytesIO(raw)) as picture:
                picture.load()
                need(picture.width > 0 and picture.height > 0, "empty image")
            counts["images"] += 1
            return
        text = raw.decode("utf-8")
        need("\x00" not in text, "unexpected NUL: " + locator)
        findings.extend(scanner.privacy_candidates(text, locator))

    for path in sorted(ARCHIVE.rglob("*")):
        need(not path.is_symlink(), "archive symlink forbidden")
        if path.is_file() and path.name not in GENERATED:
            counts["archive_files"] += 1
            inspect(path.read_bytes(), path.relative_to(ARCHIVE).as_posix())
    need(findings == [{"kind": "credential-literal", "locator": FIXTURE,
                       "raw_value_printed": False}], "unreviewed privacy candidate")
    report = {
        "schema_version": 1, "status": "PASS", **counts,
        "provenance_sources_verified": len(provenance["files"]),
        "bytes_preserved": True, "privacy_candidates": len(findings),
        "reviewed_synthetic_test_literals": 1, "unreviewed_privacy_candidates": 0,
        "review": {
            **findings[0], "file_sha256": FIXTURE_SHA,
            "classification": "NONWORKING_SYNTHETIC_MOCK_TEST_INPUT",
            "ast_keyword": "password", "source_line": 165,
            "literal_length": 24, "literal_sha256": VALUE_SHA,
            "basis": "Fake Popen/children; verifies that credentials are excluded from lifecycle receipts.",
            "general_allowlist": False, "bytes_changed": False,
        },
        "scanner_repository_path": SCANNER.relative_to(ROOT).as_posix(),
        "scanner_sha256": digest(SCANNER.read_bytes()),
    }
    encoded = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    if write:
        (ARCHIVE / "archive-audit.json").write_bytes(encoded)
    else:
        need((ARCHIVE / "archive-audit.json").read_bytes() == encoded, "audit report stale")
    lines = [digest(path.read_bytes()) + "  " + path.relative_to(ARCHIVE).as_posix()
             for path in sorted(ARCHIVE.rglob("*"))
             if path.is_file() and path.name != "SHA256SUMS"]
    sums = ("\n".join(lines) + "\n").encode()
    if write:
        (ARCHIVE / "SHA256SUMS").write_bytes(sums)
    else:
        need((ARCHIVE / "SHA256SUMS").read_bytes() == sums, "checksum manifest stale")
    print(json.dumps({key: report[key] for key in (
        "status", "archive_files", "provenance_sources_verified", "zip_files", "zip_members",
        "privacy_candidates", "reviewed_synthetic_test_literals", "unreviewed_privacy_candidates")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    run(parser.parse_args().write)
