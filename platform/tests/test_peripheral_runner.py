#!/usr/bin/env python3
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_peripheral_matrix.py"


class PeripheralRunnerTests(unittest.TestCase):
    def test_case_post_input_wait_reaches_ui_runner(self):
        spec = importlib.util.spec_from_file_location(
            "peripheral_matrix", RUNNER
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        case = next(
            case for case in module.CASES
            if case["id"] == "core2-peripherals"
        )

        command = module.command_for(case, ROOT / ".work/test")

        wait_index = command.index("--post-input-wait") + 1
        self.assertEqual(command[wait_index], "3.0")

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
