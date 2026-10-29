#!/usr/bin/env python3
"""Verify diagnostic source bytes and optionally the exact official BSP tree."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent


def tree_sha256(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob('*')):
        if path.is_file() and '.git' not in path.parts and '__pycache__' not in path.parts:
            relative = path.relative_to(root).as_posix().encode()
            data = path.read_bytes()
            digest.update(struct.pack('<Q', len(relative)))
            digest.update(relative)
            digest.update(struct.pack('<Q', len(data)))
            digest.update(data)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bsp', type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / 'sources.lock.json').read_text())
    expected = {**lock['source_files'], 'platformio.ini': lock['platform_config_sha256']}
    for name, value in expected.items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != value:
            raise SystemExit('Source identity mismatch: ' + name)
    if args.bsp and tree_sha256(args.bsp.resolve()) != lock['bsp']['source_tree_sha256']:
        raise SystemExit('Official BSP source tree identity mismatch')
    print(json.dumps({'source_files': len(expected), 'source_identity': 'PASS',
                      'bsp_tree_identity': 'PASS' if args.bsp else 'NOT RUN',
                      'build_or_runtime_validation': 'NOT RUN'}))


if __name__ == '__main__':
    main()
