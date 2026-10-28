"""Small offline contract checks; no compiler, firmware, guest or service."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("browser_littlefs_build", ROOT / "scripts/browser-littlefs/build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class BrowserLittlefsBuildTests(unittest.TestCase):
    def test_fixture_and_python_configuration_match(self):
        from uiflow_source import FS_CONFIG
        self.assertEqual({key: BUILD.FS_CONFIG[key] for key in FS_CONFIG}, FS_CONFIG)
        contract = json.loads((ROOT / "tests/browser-qemu/cores3_lvgl_pir/contract.json").read_text())
        for key, expected in BUILD.PINNED.items():
            self.assertEqual({name: contract["identity"][key][name] for name in expected}, expected)
        self.assertEqual(contract["identity"]["files"], BUILD.FIXTURE_HASHES)
        self.assertEqual(contract["identity"]["source_sha256"], BUILD.SOURCE_SHA256)

    def test_offline_cache_missing_fails_without_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing pinned offline source"):
                BUILD.sources(Path(directory), offline=True)

    def test_changed_cache_fails_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "lfs.c"
            changed.write_bytes(b"changed source")
            with self.assertRaisesRegex(ValueError, "source SHA256 mismatch"):
                BUILD.sources(Path(directory), offline=True)
            self.assertEqual(changed.read_bytes(), b"changed source")

    def test_unknown_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            output.mkdir()
            user_file = output / "keep.txt"
            user_file.write_text("user data")
            with self.assertRaisesRegex(ValueError, "unowned output"):
                BUILD.build(output, Path(directory) / "cache", Path(directory) / "emcc", Path(directory) / "fixture", offline=True)
            self.assertEqual(user_file.read_text(), "user data")


if __name__ == "__main__":
    unittest.main()
