#!/usr/bin/env python3
"""Verify post-gen45 host results and gen46 source provenance, offline."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def main():
    index = json.loads((ROOT / "index.json").read_bytes())
    paths = set()
    for item in index["files"]:
        name = item["path"]
        assert name not in paths and not Path(name).is_absolute() and ".." not in Path(name).parts
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), name
        raw = path.read_bytes()
        raw.decode("utf8")
        assert len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"], name
        paths.add(name)
    assert {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()} == paths | {"index.json"}
    for label, terminal in (("platform-r3", "FAILED (failures=2)"), ("platform-r4", "OK")):
        log = (ROOT / label / "tests.log").read_text()
        assert re.search(r"(?m)^Ran 1218 tests in [0-9.]+s$", log), label
        assert log.rstrip().endswith(terminal), label
    mapping = json.loads((ROOT / "source-map.json").read_bytes())
    receipt = json.loads((ROOT / "service/gen46/start.json").read_bytes())
    assert receipt["health"]["capacity"]["worker"]["generation"] == 46
    assert mapping["source_sha256"] == receipt["source_sha256"]
    for source, item in mapping["sources"].items():
        assert item["sha256"] == mapping["source_sha256"][source]
        if item["archive_path"] is None:
            assert source in {"platform/tools/ble_probe.py", "platform/tools/network_fabric.py"}
            continue
        path = (ROOT.parent / item["archive_path"]).resolve()
        assert path.is_relative_to(ROOT.parent)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], source
    assert len(mapping["sources"]) == 83
    before = json.loads((ROOT / "missing-marker-r1/receipt.json").read_bytes())
    after = json.loads((ROOT / "missing-marker-r2/receipt.json").read_bytes())
    assert before["exit_code"] == 1 and after["exit_code"] == 0
    assert after["observation"]["mpy_entrypoint_after_interrupt"] is False
    print(json.dumps({"status": "PASS", "files": len(paths), "source_receipt_files": 83,
                      "full_platform_tests": 1218, "historical_failures": "PRESERVED",
                      "api_contacted": False, "new_guests": 0, "hardware": "NOT RUN"}, sort_keys=True))


if __name__ == "__main__":
    main()
