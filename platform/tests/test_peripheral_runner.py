#!/usr/bin/env python3
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_peripheral_matrix.py"


class PeripheralRunnerTests(unittest.TestCase):
    def test_device_group_lists_exact_cases(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--device",
                "stackchan",
                "--list-json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        cases = json.loads(result.stdout)
        self.assertEqual(len(cases), 8)
        self.assertEqual(
            {case["machine"] for case in cases},
            {"m5stackchan"},
        )
        self.assertIn(
            "stackchan-peripherals",
            {case["id"] for case in cases},
        )

    def test_unknown_device_group_fails(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--device",
                "missing-device",
                "--list-json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown device runtime group", result.stderr)

    def test_external_only_device_has_no_matrix_cases(self):
        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER),
                "--device",
                "tab5",
                "--list-json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
