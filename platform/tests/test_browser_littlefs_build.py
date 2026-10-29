"""Small offline contract checks; no compiler, firmware, guest or service."""
from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import shutil

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

    def test_wallclock_variant_is_independently_pinned_and_preserves_legacy_identity(self):
        directory = ROOT / "tests/browser-qemu/cores3_lvgl_wallclock"
        files = BUILD.wallclock_sources(directory)
        metadata = BUILD.wallclock_metadata()
        self.assertEqual(set(files), {"boot.py", "candidate_lvgl_loop.py", "main.py"})
        self.assertEqual(metadata["id"], "cores3-wasm-lvgl-wallclock-v1")
        self.assertEqual(metadata["clock_divisor"], 1)
        self.assertEqual(metadata["scheduler_candidate"], "sdk-python-single-schedule-v1")
        self.assertEqual(metadata["composed_firmware"], BUILD.WALLCLOCK_PINNED["composed_firmware"])
        self.assertNotEqual(metadata["composed_firmware"], BUILD.PINNED["composed_firmware"])
        self.assertEqual((metadata["base_file_count"], metadata["derived_file_count"],
                          metadata["preserved_file_count"]), (17, 18, 15))
        for name, data in files.items():
            self.assertEqual(hashlib.sha256(data).hexdigest(), metadata["source_files"][name])
            self.assertEqual(metadata["source_assets"][name], "wallclock." + name)
        self.assertEqual(BUILD.PINNED["composed_firmware"]["sha256"],
                         "78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f")

    def test_wallclock_source_tampering_fails_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture"
            shutil.copytree(ROOT / "tests/browser-qemu/cores3_lvgl_wallclock", fixture)
            changed = fixture / "candidate_lvgl_loop.py"
            changed.write_bytes(changed.read_bytes() + b"\n# modified\n")
            with self.assertRaisesRegex(ValueError, "wallclock fixture source SHA256 mismatch"):
                BUILD.wallclock_sources(fixture)
            self.assertTrue(changed.read_bytes().endswith(b"# modified\n"))

    def test_wallclock_contract_cannot_rebind_base_or_output(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixture"
            shutil.copytree(ROOT / "tests/browser-qemu/cores3_lvgl_wallclock", fixture)
            contract = json.loads((fixture / "contract.json").read_text())
            for key in ("raw_base", "normalized_base", "composed_firmware"):
                with self.subTest(identity=key):
                    changed = json.loads(json.dumps(contract))
                    changed["identity"][key]["sha256"] = "0" * 64
                    (fixture / "contract.json").write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError, "wallclock fixture contract changed"):
                        BUILD.wallclock_sources(fixture)

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
