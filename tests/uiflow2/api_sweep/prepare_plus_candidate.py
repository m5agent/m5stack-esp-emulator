#!/usr/bin/env python3
"""Apply the pinned optional-timer fix to an independent candidate module."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare(args):
    args.out_dir.mkdir(parents=True,exist_ok=False)
    manifest=ROOT/'patches/uiflow2-api/0007-labelplus-optional-timer.json';entry=json.loads(manifest.read_text());source=args.uiflow_root/entry['path']
    if digest(source)!=entry['preimage_sha256']:raise ValueError('source preimage mismatch')
    copied=args.out_dir/'source'/entry['path'];copied.parent.mkdir(parents=True);shutil.copyfile(source,copied);patch=manifest.with_suffix('.patch')
    for command in [['git','apply','--check',str(patch)],['git','apply',str(patch)],['git','apply','--reverse','--check',str(patch)]]:subprocess.run(command,cwd=args.out_dir/'source',check=True,capture_output=True)
    if digest(copied)!=entry['candidate_sha256']:raise ValueError('candidate digest mismatch')
    module=args.out_dir/'candidate_label_plus.py';shutil.copyfile(copied,module)
    receipt={**entry,'module':module.name,'module_sha256':digest(module),'original_unchanged':digest(source)==entry['preimage_sha256']};(args.out_dir/'provenance.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'module_sha256':receipt['module_sha256'],'original_unchanged':receipt['original_unchanged']}))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--uiflow-root',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);prepare(p.parse_args())
