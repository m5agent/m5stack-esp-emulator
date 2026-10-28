#!/usr/bin/env python3
"""Apply the reviewed requests2 patch to a hash-checked isolated source copy."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[3]


def prepare(source_root, out_dir):
    metadata=json.loads((ROOT/"patches/uiflow2-api/0002-requests2-form-encoding.json").read_text())
    patch=ROOT/"patches/uiflow2-api/0002-requests2-form-encoding.patch"
    source=source_root/metadata["source_path"]
    raw=source.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=metadata["preimage_sha256"]:
        raise ValueError("official source preimage differs from the pinned patch base")
    if hashlib.sha256(patch.read_bytes()).hexdigest()!=metadata["patch_sha256"]:
        raise ValueError("patch digest differs from its reviewed metadata")
    out_dir.mkdir(parents=True,exist_ok=False)
    target=out_dir/metadata["source_path"]
    target.parent.mkdir(parents=True)
    shutil.copyfile(source,target)
    (out_dir/"before.py").write_bytes(raw)
    subprocess.run(["patch","-p1","--batch","--forward","-i",str(patch)],cwd=out_dir,check=True,capture_output=True)
    patched=target.read_bytes()
    if hashlib.sha256(patched).hexdigest()!=metadata["postimage_sha256"]:
        raise ValueError("applied source postimage differs from the reviewed correction")
    (out_dir/"after.py").write_bytes(patched)
    (out_dir/"candidate.json").write_text(json.dumps(metadata,indent=2)+"\n")
    return {"before":str(out_dir/"before.py"),"after":str(out_dir/"after.py"),
            "scope":metadata["scope"]}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root",type=Path,required=True)
    parser.add_argument("--out-dir",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve(),args.out_dir.resolve()),indent=2))
