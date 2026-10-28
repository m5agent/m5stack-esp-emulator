"""Regression capture must observe guest completion, not a host sleep alone."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
import run_profile_ui_test as runner


class GuestReadinessTests(unittest.TestCase):
    def test_marker_can_arrive_after_initial_poll(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            process = mock.Mock()
            process.poll.return_value = None
            with mock.patch.object(runner.time, "sleep", side_effect=lambda _: path.write_text("DRAW_COMPLETE\n")):
                runner.wait_serial_marker(path, "DRAW_COMPLETE", process)

    def test_exit_and_timeout_are_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            process = mock.Mock()
            process.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, "process exited"):
                runner.wait_serial_marker(path, "MISSING", process)
            process.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                runner.wait_serial_marker(path, "MISSING", process, timeout=0)

    def test_matrix_forwards_the_two_distinct_markers(self):
        spec = importlib.util.spec_from_file_location("readiness_matrix", ROOT / "tests/uiflow2/run_peripheral_matrix.py")
        matrix = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matrix)
        for name in ("cores3-peripherals", "core2-peripherals"):
            case = next(item for item in matrix.CASES if item["id"] == name)
            command = matrix.command_for(case, Path("/tmp/not-executed"))
            self.assertEqual(command[command.index("--pre-input-marker") + 1], case["pre_input_marker"])
            self.assertEqual(command[command.index("--post-input-marker") + 1], case["post_input_marker"])
            self.assertNotEqual(case["pre_input_marker"], case["post_input_marker"])
