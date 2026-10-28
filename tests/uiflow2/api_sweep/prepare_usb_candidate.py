#!/usr/bin/env python3
"""Prepare exact official USB core preimage/candidate modules in isolation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
PATCH = ROOT / "patches/uiflow2-api/0011-usb-buffer-readinto.patch"


def prepare(source_root, output):
    metadata = json.loads(PATCH.with_suffix(".json").read_text())
    original = (source_root / metadata["path"]).read_bytes()
    if hashlib.sha256(original).hexdigest() != metadata["preimage_sha256"]:
        raise ValueError("USB core differs from pinned official preimage")
    if hashlib.sha256(PATCH.read_bytes()).hexdigest() != metadata["patch_sha256"]:
        raise ValueError("USB patch checksum changed")
    if output.exists():
        raise ValueError("candidate output must be a fresh directory")
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        source = work / metadata["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(original)
        for flags in (("--check",), (), ("--reverse", "--check")):
            subprocess.run(["git", "apply", *flags, str(PATCH)], cwd=work, check=True, capture_output=True)
        corrected = source.read_bytes()
        if hashlib.sha256(corrected).hexdigest() != metadata["candidate_sha256"]:
            raise ValueError("USB candidate checksum differs")
    output.mkdir(parents=True)
    (output / "usb_core_before.py").write_bytes(original)
    (output / "usb_core_candidate.py").write_bytes(corrected)
    (output / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uiflow-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.uiflow_root, args.out_dir), indent=2))
