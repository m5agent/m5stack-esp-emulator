#!/usr/bin/env python3
import importlib.util
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_peripheral_matrix.py"


class PeripheralRunnerTests(unittest.TestCase):
    def test_refreshed_reference_partition_controls_probe_placement(self):
        spec = importlib.util.spec_from_file_location("peripheral_matrix", RUNNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "reference.bin"
            image = bytearray(b"\xff" * 0x80000)
            entries = b"".join(struct.pack("<HBBII16sI", 0x50AA, kind, subtype, offset, size, label, 0)
                               for kind, subtype, offset, size, label in (
                                   (0, 0, 0x10000, 0x20000, b"factory"),
                                   (1, 0x81, 0x30000, 0x10000, b"vfs"),
                               ))
            image[0x8000:0x8000 + len(entries)] = entries
            base.write_bytes(image)
            case = {**module.CASES[0], "base": str(base), "flash_size": "0x80000",
                    "vfs_offset": "0x20000", "vfs_size": "0x20000"}
            reference = module.reference_layout(case)
            self.assertEqual(reference["effective"], {"offset": 0x30000, "size": 0x10000})
            self.assertEqual(reference["base_firmware_sha256"], hashlib.sha256(image).hexdigest())
            command = module.command_for(case, Path(tmp) / "out", reference=reference)
            self.assertEqual(command[command.index("--vfs-offset") + 1], "0x30000")
            self.assertEqual(command[command.index("--vfs-size") + 1], "0x10000")

    def test_invalid_reference_partition_never_composes_over_application(self):
        spec = importlib.util.spec_from_file_location("peripheral_matrix", RUNNER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "reference.bin"
            case = {**module.CASES[0], "base": str(base), "flash_size": "0x80000"}
            for bad_parts in (
                [(1, 0x81, 0x30000, 0x10000, b"vfs"), (1, 0x81, 0x40000, 0x10000, b"vfs")],
                [(0, 0, 0x10000, 0x30000, b"factory"), (1, 0x81, 0x30000, 0x10000, b"vfs")],
                [(1, 0x81, 0x70000, 0x20000, b"vfs")],
                [(1, 0x81, 0x30100, 0x10000, b"vfs")],
            ):
                with self.subTest(partitions=bad_parts):
                    image = bytearray(b"\xff" * 0x80000)
                    entries = b"".join(struct.pack("<HBBII16sI", 0x50AA, *part, 0) for part in bad_parts)
                    image[0x8000:0x8000 + len(entries)] = entries
                    base.write_bytes(image)
                    with self.assertRaises(ValueError):
                        module.reference_layout(case)

    def test_interactive_case_settle_times_reach_ui_runner(self):
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

        keyboard = next(
            case for case in module.CASES
            if case["id"] == "cardputer-adv-keyboard"
        )
        keyboard_command = module.command_for(
            keyboard,
            ROOT / ".work/test",
        )
        wait_index = keyboard_command.index("--wait") + 1
        post_input_index = (
            keyboard_command.index("--post-input-wait") + 1
        )
        self.assertEqual(keyboard_command[wait_index], "10")
        self.assertEqual(keyboard_command[post_input_index], "2")

    def test_core2_cases_use_deterministic_scheduling_without_retries(self):
        spec = importlib.util.spec_from_file_location(
            "peripheral_matrix", RUNNER
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        core2_cases = [
            case for case in module.CASES if case["machine"] == "m5core2"
        ]
        self.assertEqual(len(core2_cases), 6)
        for case in core2_cases:
            self.assertIs(case.get("deterministic"), True, case["id"])
            self.assertNotIn("retries", case, case["id"])
            command = module.command_for(case, ROOT / ".work/test")
            self.assertIn("--deterministic", command, case["id"])

        device_matrix = json.loads(
            (ROOT / "tests" / "uiflow2" / "device_matrix.json").read_text()
        )
        core2_device = next(
            device for device in device_matrix["devices"]
            if device["id"] == "core2"
        )
        self.assertIs(core2_device.get("deterministic"), True)
        self.assertNotIn("retries", core2_device)
        self.assertEqual(core2_device["wait"], 18)
        self.assertEqual(core2_device["input"], "longpress:160,183,1.5")

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
