"""Matrix admission and composition must reject unsafe metadata before launch."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
import run_device_matrix as matrix
import run_profile_ui_test as profile

SPEC = importlib.util.spec_from_file_location(
    "matrix_source_fixture", ROOT / "platform/tests/test_uiflow_source.py")
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class PackageTests(unittest.TestCase):
    def test_classic_and_s3_fields_are_distinct_and_bounded(self):
        for driver, offset, shift in (("nvram.esp32.efuse", 12, 9),
                                      ("nvram.esp32s3.efuse", 36, 21)):
            for package in (0, 1, 5, 6, 7):
                with self.subTest(driver=driver, package=package):
                    data = profile.efuse_image(package, driver)
                    self.assertEqual(len(data), 4096)
                    self.assertEqual(int.from_bytes(data[offset:offset + 4], "little"),
                                     package << shift)
                    self.assertEqual(data[:offset] + data[offset + 4:], b"\0" * 4092)
        for value in (-1, 8, True, 1.5, "5"):
            with self.assertRaises(ValueError):
                profile.efuse_image(value, "nvram.esp32.efuse")
        with self.assertRaises(ValueError):
            profile.efuse_image(5, "none")
        with self.assertRaises(ValueError):
            profile.efuse_image(0, "unknown")

    def test_device_efuse_driver_overrides_backend_default(self):
        data = json.loads(matrix.MATRIX.read_text())
        row = next(d for d in data["devices"] if d["id"] == "stickc")
        command = matrix.ui_command(row, data["backends"][row["backend"]], Path("/tmp/out"))
        self.assertEqual(command[command.index("--efuse-driver") + 1], "nvram.esp32.efuse")
        self.assertEqual(command[command.index("--efuse-pkg-version") + 1], "5")

    def test_four_console_fixtures_have_observable_markers(self):
        data = json.loads(matrix.MATRIX.read_text())
        ids = {"atom-lite", "atom-matrix", "atom-matrix-v11", "atoms3-lite"}
        for row in data["devices"]:
            if row["id"] in ids:
                self.assertEqual(row["mode"], "console")
                self.assertEqual(row["serial_index"], 0)
                self.assertGreaterEqual(len(row["serial_expect"]), 2)


@unittest.skipIf(fixture.littlefs is None, "littlefs-python is required")
class ImageCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "base.bin"
        self.base.write_bytes(fixture.real_base())
        self.files = self.root / "files"
        self.files.mkdir()
        (self.files / "boot.py").write_text("_uiflow_run_main = True\n")
        (self.files / "main.py").write_text("print('matrix probe')\n")

    def options(self, **overrides):
        return SimpleNamespace(**{
            "base": self.base, "flash_size": fixture.FLASH_SIZE,
            "vfs_offset": fixture.VFS_OFFSET - 4096,
            "vfs_size": fixture.VFS_SIZE + 4096,
            "files_dir": self.files, "out_dir": self.root / "out",
            "preserve_vfs": False, "mklittlefs": None, "prog_size": 32,
            **overrides,
        })

    def test_actual_layout_preserves_stock_assets_and_all_non_vfs_bytes(self):
        image = profile.build_image(self.options()).read_bytes()
        original = self.base.read_bytes()
        self.assertEqual(image[:fixture.VFS_OFFSET], original[:fixture.VFS_OFFSET])
        end = fixture.VFS_OFFSET + fixture.VFS_SIZE
        self.assertEqual(image[end:], original[end:])
        self.assertEqual(fixture.read_file(image, "/res/font.bin"), bytes(range(256)) * 4)
        self.assertEqual(fixture.read_file(image, "/lib.py"), b"preserve=1\n")
        self.assertEqual(fixture.read_file(image, "/main.py"), b"print('matrix probe')\n")
        metadata = json.loads((self.root / "out/composition.json").read_text())
        self.assertTrue(metadata["layout_drift"])
        self.assertEqual(metadata["vfs"]["offset"], fixture.VFS_OFFSET)
        self.assertTrue(metadata["preservation"]["outside_vfs_unchanged"])
        self.assertTrue(metadata["preservation"]["existing_files_readback_verified"])

    def test_strict_policy_rejects_drift_before_writing(self):
        with self.assertRaisesRegex(SystemExit, "VFS layout drift"):
            profile.build_image(self.options(layout_policy="strict"))
        self.assertFalse((self.root / "out").exists())

    def test_invalid_partition_metadata_does_not_format_or_create_output(self):
        self.base.write_bytes(fixture.base_image(partitions=[
            fixture.entry("vfs", fixture.VFS_OFFSET, fixture.VFS_SIZE, flags=1)]))
        with self.assertRaisesRegex(ValueError, "flagged or encrypted"):
            profile.build_image(self.options())
        self.assertFalse((self.root / "out").exists())

    def test_console_builder_uses_same_layout_without_a_fixture_builder(self):
        device = {"base": str(self.base), "files_dir": str(self.files),
                  "flash_size": hex(fixture.FLASH_SIZE),
                  "vfs_offset": hex(fixture.VFS_OFFSET - 4096),
                  "vfs_size": hex(fixture.VFS_SIZE + 4096)}
        self.assertFalse((self.files / "make_image.py").exists())
        built = matrix.build_console_image(device, self.root / "console", {})
        self.assertEqual(built.name, "uiflow2-console-test.bin")
        self.assertEqual(fixture.read_file(built.read_bytes(), "/lib.py"), b"preserve=1\n")


if __name__ == "__main__":
    unittest.main()
