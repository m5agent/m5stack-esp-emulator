#!/usr/bin/env python3
import sys
import unittest
import json
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))
import runtime_coverage
from runtime_coverage import validate


class RuntimeCoverageTests(unittest.TestCase):
    def test_every_simulated_model_has_runtime_evidence(self):
        errors, report = validate()
        self.assertEqual(errors, [])
        self.assertEqual(
            report["covered_models"],
            report["simulated_models"],
        )
        self.assertEqual(report["device_case_groups"], 24)
        self.assertEqual(report["assigned_matrix_cases"], 68)
        self.assertEqual(report["assigned_external_cases"], 19)
        self.assertEqual(report["case_model_groups"], 87)

    def test_missing_device_case_group_is_rejected(self):
        coverage = json.loads(runtime_coverage.COVERAGE.read_text())
        coverage["device_case_groups"].pop("stackchan")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime-coverage.json"
            path.write_text(json.dumps(coverage))
            with mock.patch.object(runtime_coverage, "COVERAGE", path):
                errors, _ = validate()
        self.assertIn(
            "device stackchan: no runtime case group for its peripheral "
            "components",
            errors,
        )

    def test_unassigned_matrix_case_is_rejected(self):
        coverage = json.loads(runtime_coverage.COVERAGE.read_text())
        coverage["device_case_groups"]["cardputer-adv"]["matrix"].remove(
            "cardputer-adv-ir"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime-coverage.json"
            path.write_text(json.dumps(coverage))
            with mock.patch.object(runtime_coverage, "COVERAGE", path):
                errors, _ = validate()
        self.assertIn(
            "matrix cases not assigned to a device: ['cardputer-adv-ir']",
            errors,
        )

    def test_device_component_needs_device_local_case_coverage(self):
        coverage = json.loads(runtime_coverage.COVERAGE.read_text())
        coverage["case_models"]["stackchan-peripherals"].remove("bmm150")
        coverage["case_models"]["stackchan-unified"].remove("bmm150")
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime-coverage.json"
            path.write_text(json.dumps(coverage))
            with mock.patch.object(runtime_coverage, "COVERAGE", path):
                errors, _ = validate()
        self.assertIn(
            "device stackchan: no device-local case covers models ['bmm150']",
            errors,
        )

    def test_matrix_flash_and_vfs_ranges_fit(self):
        cases = runtime_coverage.load_matrix_cases()
        for case_id, case in cases.items():
            flash_size = int(case["flash_size"], 0)
            vfs_end = int(case["vfs_offset"], 0) + int(case["vfs_size"], 0)
            self.assertLessEqual(
                vfs_end,
                flash_size,
                f"{case_id}: VFS range exceeds flash size",
            )
            base = ROOT / case["base"]
            if base.is_file():
                self.assertLessEqual(
                    base.stat().st_size,
                    flash_size,
                    f"{case_id}: base image exceeds flash size",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
