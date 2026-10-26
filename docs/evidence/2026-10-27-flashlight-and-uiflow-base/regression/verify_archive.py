#!/usr/bin/env python3
"""Verify the portable evidence archive with only Python's standard library."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
index = json.loads((root / "index.json").read_bytes())
checked = 0
for row in [*index["records"], *index["generated_files"]]:
    if row.get("disposition") == "EXCLUDED_BINARY_HASH_ONLY":
        continue
    path = root / row["archive_path"]
    assert path.is_file(), row["archive_path"]
    data = path.read_bytes()
    assert len(data) == row["archive_size"], row["archive_path"]
    assert hashlib.sha256(data).hexdigest() == row["archive_sha256"], row["archive_path"]
    if row.get("disposition") == "ARCHIVED_ORIGINAL_BYTES":
        assert row["archive_sha256"] == row["original_sha256"], row["archive_path"]
    checked += 1
for path in root.rglob("*"):
    assert path.suffix.lower() not in {".bin", ".mpy", ".elf", ".rom", ".img", ".zip", ".pcm", ".rmt", ".ppm"}, path.name
print(json.dumps({"status": "PASS", "files_verified": checked, "firmware_or_runtime_binary_archived": False}))
