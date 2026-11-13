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
    def test_virtual_keytap_schedules_release_on_qemu_clock(self):
        qmp = mock.Mock()
        with mock.patch.object(runner.time, "sleep") as sleep:
            runner.send_input(qmp, "virtual-keytap:a,0.1", (135, 240), 0.2)
        qmp.cmd.assert_called_once_with(
            "send-key", keys=[{"type": "qcode", "data": "a"}],
            **{"hold-time": 100},
        )
        sleep.assert_called_once_with(0.2)

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

    def test_before_frame_waits_for_both_content_thresholds(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before.ppm"
            qmp, process = mock.Mock(), mock.Mock()
            process.poll.return_value = None
            frames = iter([bytes(6), b"\xff\x00\x00" * 2, b"\xff\x00\x00\x00\xff\x00"])

            def dump(name, filename):
                self.assertEqual(name, "screendump")
                Path(filename).write_bytes(b"P6\n2 1\n255\n" + next(frames))

            qmp.cmd.side_effect = dump
            with mock.patch.object(runner.time, "sleep"):
                self.assertEqual(runner.capture_before_frame(
                    qmp, process, path, (2, 1), timeout=10,
                    min_nonblack_pixels=2, min_unique_colors=2,
                ), (2, 1))
            self.assertEqual(qmp.cmd.call_count, 3)

    def test_before_frame_timeout_preserves_blank_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "before.ppm"
            qmp, process = mock.Mock(), mock.Mock()
            process.poll.return_value = None
            qmp.cmd.side_effect = lambda name, filename: Path(filename).write_bytes(
                b"P6\n2 1\n255\n" + bytes(6)
            )
            with (mock.patch.object(runner.time, "monotonic", side_effect=[0.0, 0.0, 0.1]),
                  mock.patch.object(runner.time, "sleep") as sleep):
                with self.assertRaisesRegex(RuntimeError, "timed out.*0 non-black pixels"):
                    runner.capture_before_frame(
                        qmp, process, path, (2, 1), timeout=0.1,
                        min_nonblack_pixels=2, min_unique_colors=2,
                    )
            sleep.assert_called_once_with(0.1)
            qmp.cmd.assert_called_once()
            self.assertTrue(path.with_suffix(".png").is_file())

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
