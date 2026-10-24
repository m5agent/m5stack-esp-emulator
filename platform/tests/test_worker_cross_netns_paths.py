import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/network/worker_cross_netns/run_test.py"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "worker_cross_netns_run_test",
        RUNNER,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WorkerCrossNetnsPathTests(unittest.TestCase):
    def test_registered_qemu_path_uses_executable_device_matrix(self):
        runner = load_runner()

        path = runner.registered_qemu_path("sticks3")

        self.assertEqual(
            path,
            ROOT
            / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa",
        )

    def test_qemu_process_scan_ignores_command_arguments(self):
        runner = load_runner()

        processes = runner.qemu_process_lines(
            "123 python3 run.py --qemu-path /tmp/qemu-system-xtensa\n"
            "789 sh -c echo qemu-system-xtensa\n"
            "456 /opt/qemu/qemu-system-xtensa -M m5sticks3"
        )

        self.assertEqual(
            processes,
            ["456 /opt/qemu/qemu-system-xtensa -M m5sticks3"],
        )

    def test_diagnostic_redaction_removes_ephemeral_identifiers(self):
        runner = load_runner()
        token = "test-token"

        redacted = runner.redact_diagnostic(
            "Authorization: test-token "
            "job job-0123456789abcdef0123 "
            "session/0123456789abcdef0123456789abcdef "
            "http://127.0.0.1:8787",
            token,
        )

        self.assertNotIn(token, redacted)
        self.assertNotIn("job-0123456789abcdef0123", redacted)
        self.assertNotIn("0123456789abcdef0123456789abcdef", redacted)
        self.assertNotIn("127.0.0.1", redacted)


if __name__ == "__main__":
    unittest.main()
