#!/usr/bin/env python3
"""Verify source identity only; never flash or execute a device."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent


def tree_sha(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and '.git' not in path.parts and '__pycache__' not in path.parts:
            name = path.relative_to(root).as_posix().encode()
            body = path.read_bytes()
            digest.update(struct.pack('<Q', len(name)))
            digest.update(name)
            digest.update(struct.pack('<Q', len(body)))
            digest.update(body)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bsp', type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    for name, expected in lock['source_files'].items():
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit('Source identity mismatch: ' + name)
    if args.bsp and tree_sha(args.bsp.resolve()) != lock['bsp']['source_tree_sha256']:
        raise SystemExit('BSP tree identity mismatch')
    print(json.dumps({'source_identity': 'PASS',
                      'bsp_tree_identity': 'PASS' if args.bsp else 'NOT RUN',
                      'runtime_and_hardware': 'NOT RUN'}))


if __name__ == '__main__':
    main()
