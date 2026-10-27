#!/usr/bin/env python3
"""Portable, offline verification and exact-output C rebuild for this archive."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def verify():
    index = json.loads((ROOT / "index.json").read_text())
    assert index["frozen_input_count"] == len(index["records"]) == 96
    assert Counter(r["classification"] for r in index["records"]) == {
        "original-bytes": 86, "fingerprint-only": 10}
    assert index["api_contacted"] is False
    assert index["guest_execution"] == index["hardware_execution"] == "NOT RUN"
    expected_files = {"index.json"}
    for record in index["records"] + index["supplemental"] + index["generated"]:
        if record["classification"] == "fingerprint-only":
            assert record["archive_path"] is None and "archive_sha256" not in record
            assert re.fullmatch("[0-9a-f]{64}", record["source_sha256"])
            assert record["source_bytes"] > 0
            continue
        relative = record["archive_path"]
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        expected_files.add(relative)
        raw = (ROOT / relative).read_bytes()
        assert len(raw) == record["archive_bytes"] and sha(raw) == record["archive_sha256"], relative
        if record["classification"] == "original-bytes":
            assert record["source_bytes"] == record["archive_bytes"]
            assert record["source_sha256"] == record["archive_sha256"]
        raw.decode("utf-8")
        assert b"\0" not in raw
    actual_files = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()}
    assert actual_files == expected_files, (actual_files - expected_files, expected_files - actual_files)
    mac = re.compile(rb"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")
    private_key = re.compile(rb"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----")
    bearer = re.compile(rb"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}")
    credential = re.compile(rb'''(?i)["'](?:api_key|access_token|secret_key|password)["']\s*:\s*["'][A-Za-z0-9._~+/-]{20,}["']''')
    for relative in actual_files:
        path = ROOT / relative
        raw = path.read_bytes()
        raw.decode("utf-8")
        assert b"\0" not in raw and not mac.search(raw) and not private_key.search(raw)
        assert not bearer.search(raw) and not credential.search(raw)
        assert path.suffix.lower() not in {".bin", ".rom", ".mpy", ".zip"}
    assert sha((ROOT / "originals/cases.c").read_bytes()) == index["same_cases_sha256"]
    assert sha((ROOT / "originals/permanent-test.source.py.txt").read_bytes()) == index["permanent_test_sha256"]
    return index, len(actual_files)


def run_original(rebuild_out):
    argv = [sys.executable, "-I", "-B", str(ROOT / "originals/verify.py"), "--allow-missing-executables"]
    if rebuild_out is not None:
        argv += ["--rebuild-out", str(rebuild_out)]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    result = subprocess.run(argv, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["result"] == "PASS"
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--out-dir", type=Path)
    args = ap.parse_args()
    assert args.out_dir is None or args.rebuild, "--out-dir requires --rebuild"
    index, count = verify()
    if args.rebuild and args.out_dir is None:
        with tempfile.TemporaryDirectory(prefix="unit-host38-controller-") as temporary:
            original = run_original(Path(temporary) / "rebuilt")
    else:
        original = run_original(args.out_dir.resolve() if args.out_dir else None)
    print(json.dumps({"result": "PASS", "files": count, "frozen_inputs": 96,
                      "original_byte_inputs": 86, "executable_fingerprints_only": 10,
                      "index_sha256": sha((ROOT / "index.json").read_bytes()),
                      "permanent_test_sha256": index["permanent_test_sha256"],
                      "rebuilt": args.rebuild, "comparison": original["comparisons"],
                      "api_contacted": False, "guest_execution": "NOT RUN", "hardware_execution": "NOT RUN"}))


if __name__ == "__main__":
    main()
