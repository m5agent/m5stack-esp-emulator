#!/usr/bin/env python3
"""Import a saved candidate as device_service, then run the normal test file.

This review-only launcher leaves platform/tools/device_service.py unchanged.
The test file itself has normal direct imports and can move to platform/tests.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "platform/tools"), str(ROOT / "platform/tests")]
parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--result", type=Path, required=True)
args = parser.parse_args()
spec = importlib.util.spec_from_file_location("device_service", args.source)
module = importlib.util.module_from_spec(spec)
module.__file__ = str(ROOT / "platform/tools/device_service.py")
sys.modules[spec.name] = module
spec.loader.exec_module(module)
test_path = Path(__file__).with_name("test_device_service_qmp_startup.py")
spec = importlib.util.spec_from_file_location("test_device_service_qmp_startup", test_path)
tests = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tests
spec.loader.exec_module(tests)
suite = unittest.defaultTestLoader.loadTestsFromModule(tests)
result = unittest.TextTestRunner(verbosity=2).run(suite)
args.result.write_text(json.dumps({
    "schema_version": 1,
    "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
    "test_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
    "scope": "Normal unittest against saved source; no QEMU, port 8787 or live session",
    "tests_run": result.testsRun,
    "failures": [{"test": str(test), "trace": trace} for test, trace in result.failures],
    "errors": [{"test": str(test), "trace": trace} for test, trace in result.errors],
    "status": "PASS" if result.wasSuccessful() else "FAIL",
}, indent=2) + "\n")
raise SystemExit(0 if result.wasSuccessful() else 1)
