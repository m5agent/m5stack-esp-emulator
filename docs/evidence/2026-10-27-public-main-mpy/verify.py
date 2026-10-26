#!/usr/bin/env python3
"""Read-only integrity verification of archived evidence, not a new VM run."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    manifest = json.loads((ROOT / "artifact-manifest.json").read_bytes())
    require(manifest["schema_version"] == 1, "manifest version")
    seen = set()
    total = 0
    for item in manifest["files"]:
        relative = item["path"]
        require(relative not in seen and not Path(relative).is_absolute()
                and ".." not in Path(relative).parts, "unsafe or duplicate path")
        path = ROOT / relative
        require(path.is_file() and not path.is_symlink(), "missing or linked file: " + relative)
        raw = path.read_bytes()
        require(len(raw) == item["bytes"]
                and hashlib.sha256(raw).hexdigest() == item["sha256"], "changed file: " + relative)
        total += len(raw)
        seen.add(relative)
    actual = {str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if path.is_file()}
    require(actual == seen | {"artifact-manifest.json"}, "unlisted or missing files")
    acceptance = json.loads((ROOT / "final-acceptance.json").read_bytes())
    require(acceptance["status"] == "PASS", "final acceptance status")
    require(acceptance["hardware"] == "NOT RUN", "hardware boundary")
    require(acceptance["optional_browser_capture"] == "PARTIAL", "optional capture boundary")
    schema = json.loads((ROOT / "contracts/original-response-r2/receipt.json").read_bytes())
    require(schema["status"] == "PASS" and schema["counts"]["validated_json_responses"] == 766
            and schema["counts"]["validation_errors"] == 0, "original response contracts")
    typed = json.loads((ROOT / "contracts/typed-control-r2/receipt.json").read_bytes())
    require(typed["status"] == "PASS" and typed["count"] == 48, "typed contract controls")
    require(typed["spec_sha256"] == schema["input_hashes"]["docs/device-service.openapi.yaml"]["sha256"],
            "contract checks used different specifications")
    for relative in acceptance["portable_verifiers"]:
        require(relative in seen, "unlisted verifier")
        process = subprocess.run([sys.executable, "-B", str(ROOT / relative)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=60)
        require(process.returncode == 0, relative + ": " + process.stdout + process.stderr)
    print(json.dumps({"status": "PASS", "category": "OFFLINE_ARCHIVE_VERIFICATION",
                      "files": len(seen), "bytes": total,
                      "child_verifiers": len(acceptance["portable_verifiers"]),
                      "new_guests": 0, "api_contacted": False,
                      "optional_browser_capture": "PARTIAL", "hardware": "NOT RUN"}, sort_keys=True))


if __name__ == "__main__":
    main()
