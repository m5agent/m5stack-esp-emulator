from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import device_service
from device_service import load_device_specs, set_qemu_efuse_package
import runtime_coverage


ROOT = Path(__file__).resolve().parents[2]


class AtomS3CandidateTests(unittest.TestCase):
    def test_original_atoms3_is_an_independent_no_psram_candidate(self):
        specs = load_device_specs()
        atom, atom_r = specs["atoms3"], specs["atoms3r"]
        self.assertEqual((atom.machine, atom.memory, atom.flash_size), ("m5atoms3", "0", 8 << 20))
        self.assertEqual((atom.sku, atom.soc), ("C123", "ESP32-S3FN8"))
        self.assertTrue(atom.supported)
        self.assertEqual(atom.peripheral_status, "partial")
        self.assertNotEqual(atom.machine, atom_r.machine)
        self.assertNotEqual(atom.reference_path, atom_r.reference_path)
        source = json.loads((ROOT / "devices/catalog.source.json").read_text())
        row = next(row for row in source["devices"] if row["id"] == "atoms3")
        self.assertEqual(row["hardware"]["psram_bytes"], 0)
        self.assertEqual(row["runtime"]["validation"]["status"], "native-display-input-imu-rgb-pass")
        self.assertEqual(row["uiflow2"]["firmware"]["firmware_id"], "1897200000000002444")

    def test_soc_specific_package_fields_preserve_neighboring_efuses(self):
        for backend, offset, shift, package in (
            ("qemu-esp32s3", 36, 21, 0),
            ("qemu-esp32s3", 36, 21, 1),
            ("qemu-esp32lx6", 12, 9, 6),
        ):
            with self.subTest(backend=backend, package=package):
                efuse = bytearray(b"\xa5" * 64)
                before = efuse[:]
                set_qemu_efuse_package(efuse, backend, package)
                word = int.from_bytes(efuse[offset:offset + 4], "little")
                original = int.from_bytes(before[offset:offset + 4], "little")
                self.assertEqual((word >> shift) & 7, package)
                self.assertEqual(word & ~(7 << shift), original & ~(7 << shift))
                self.assertEqual(efuse[:offset], before[:offset])
                self.assertEqual(efuse[offset + 4:], before[offset + 4:])

    def test_unknown_or_invalid_package_cannot_write_a_different_soc_field(self):
        for backend, package, size in (
            ("qemu-esp32c6", 0, 64), ("qemu-esp32s3", True, 64),
            ("qemu-esp32s3", -1, 64), ("qemu-esp32lx6", 8, 64),
            ("qemu-esp32s3", 0, 39), ("qemu-esp32lx6", 6, 15),
        ):
            with self.subTest(backend=backend, package=package, size=size):
                efuse = bytearray(size)
                with self.assertRaises(ValueError):
                    set_qemu_efuse_package(efuse, backend, package)
                self.assertEqual(efuse, bytearray(size))

    def test_explicit_efuse_driver_does_not_change_the_legacy_backend_default(self):
        original = load_device_specs()
        self.assertEqual(original["core2"].efuse_driver, "none")
        matrix = json.loads((ROOT / "tests/uiflow2/device_matrix.json").read_text())
        row = next(row for row in matrix["devices"] if row["id"] == "core2")
        row["efuse_driver"] = "nvram.esp32.efuse"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix.json"
            path.write_text(json.dumps(matrix))
            with mock.patch.object(device_service, "MATRIX", path):
                overridden = load_device_specs()
        self.assertEqual(overridden["core2"].efuse_driver, "nvram.esp32.efuse")
        self.assertEqual(overridden["atoms3"].efuse_driver, original["atoms3"].efuse_driver)
        self.assertEqual(load_device_specs()["core2"].efuse_driver, "none")

    def test_candidate_coverage_cannot_hide_a_simulated_model_or_missing_blocker(self):
        catalog = json.loads((ROOT / "platform/peripherals/catalog.json").read_text())
        coverage = json.loads((ROOT / "platform/peripherals/runtime-coverage.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            catalog_path, coverage_path = path / "catalog.json", path / "coverage.json"
            catalog_path.write_text(json.dumps(catalog))
            coverage_path.write_text(json.dumps(coverage))
            with mock.patch.object(runtime_coverage, "CATALOG", catalog_path), \
                    mock.patch.object(runtime_coverage, "COVERAGE", coverage_path):
                self.assertEqual(runtime_coverage.validate()[0], [])
                catalog["devices"]["atoms3"]["components"][0]["status"] = "simulated"
                catalog_path.write_text(json.dumps(catalog))
                errors, _ = runtime_coverage.validate()
                self.assertIn("device atoms3: candidate case group cannot cover simulated components", errors)
                self.assertTrue(any("device-local case" in error for error in errors))
                catalog["devices"]["atoms3"]["components"][0]["status"] = "partial"
                catalog_path.write_text(json.dumps(catalog))
                coverage["device_case_groups"]["atoms3"]["blocker"] = " "
                coverage_path.write_text(json.dumps(coverage))
                errors, _ = runtime_coverage.validate()
                self.assertIn("device atoms3: candidate case group needs a concrete blocker", errors)
                self.assertIn("device atoms3: runtime case group is empty", errors)


if __name__ == "__main__":
    unittest.main()
