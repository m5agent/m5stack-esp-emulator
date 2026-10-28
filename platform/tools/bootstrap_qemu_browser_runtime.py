#!/usr/bin/env python3
"""Public CLI/import facade for the pinned C/QEMU browser source builder."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_path = Path(__file__).resolve().parents[2] / "scripts/qemu-wasm-build/build.py"
_spec = spec_from_file_location("m5_qemu_wasm_builder", _path)
_builder = module_from_spec(_spec)
_spec.loader.exec_module(_builder)

ASSET_NAMES = _builder.ASSET_NAMES
RUNTIME_KIND = _builder.RUNTIME_KIND
load_lock = _builder.load_lock
runtime_files = _builder.runtime_files

if __name__ == "__main__":
    _builder.main()
