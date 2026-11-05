"""Official driver expectation changes are selected by exact base SHA."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "peripheral_firmware_expectations", ROOT / "tests/uiflow2/run_peripheral_matrix.py")
matrix = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(matrix)


class FirmwareExpectationTests(unittest.TestCase):
    def test_known_latest_images_select_exact_values_without_mutating_old_oracle(self):
        for name, marker in (("sticks3-peripherals", "STICKS3_IMU -0.500 -0.250 0.750"),
                             ("papercolor-peripherals", "PAPERCOLOR_POWER 87 4000 0")):
            case = next(row for row in matrix.CASES if row["id"] == name)
            base_sha = next(iter(case["firmware_serial_expectations"]))
            old = list(case["serial_expect"])
            effective, identity = matrix.firmware_case_expectations(case, base_sha)
            self.assertIn(marker, effective["serial_expect"])
            self.assertEqual(case["serial_expect"], old)
            self.assertEqual(len(effective["serial_expect"]), len(old))
            self.assertEqual(identity["base_sha256"], base_sha)
            self.assertIn("b67ea7bd2d187d3fa8719edf1b915fd34a128c0d", identity["source"])
            self.assertEqual(effective["qom"], case["qom"])

    def test_other_firmware_does_not_inherit_the_latest_expectation(self):
        for case in matrix.CASES:
            if case.get("firmware_serial_expectations"):
                effective, identity = matrix.firmware_case_expectations(case, "0" * 64)
                self.assertIs(effective, case)
                self.assertEqual(identity["profile"], "legacy-case-default")

    def test_typo_in_sha_bound_override_does_not_remove_an_assertion(self):
        case = {"id": "broken", "serial_expect": ["required"],
                "firmware_serial_expectations": {"1" * 64: {
                    "replace": {"misspelled": "new value"}}}}
        with self.assertRaisesRegex(ValueError, "unknown marker"):
            matrix.firmware_case_expectations(case, "1" * 64)


if __name__ == "__main__":
    unittest.main()
