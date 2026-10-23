#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import network_sandbox  # noqa: E402


class NetworkSandboxTests(unittest.TestCase):
    def test_non_linux_refuses_to_run(self):
        with mock.patch.object(network_sandbox.sys, "platform", "darwin"):
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "requires Linux",
            ):
                network_sandbox.run({}, ["/bin/true"])

    def test_unshare_failure_refuses_to_run_command(self):
        called = False

        def should_not_run(*_args, **_kwargs):
            nonlocal called
            called = True
            raise AssertionError("command must not start")

        with (
            mock.patch.object(network_sandbox.sys, "platform", "linux"),
            mock.patch.object(
                network_sandbox.os,
                "unshare",
                side_effect=PermissionError("denied"),
                create=True,
            ),
            mock.patch.object(
                network_sandbox.os,
                "CLONE_NEWNET",
                0x40000000,
                create=True,
            ),
            mock.patch.object(
                network_sandbox.subprocess,
                "Popen",
                side_effect=should_not_run,
            ),
        ):
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "cannot create network namespace",
            ):
                network_sandbox.run({}, ["/bin/true"])
        self.assertFalse(called)

    def test_invalid_config_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sandbox.json"
            path.write_text("{broken")
            with self.assertRaisesRegex(
                network_sandbox.SandboxError,
                "invalid sandbox config",
            ):
                network_sandbox.load_config(path)

    def test_main_reports_fail_closed_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sandbox.json"
            path.write_text(json.dumps({}))
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    network_sandbox.sys,
                    "argv",
                    [
                        "network_sandbox.py",
                        "--config",
                        str(path),
                        "--",
                        "/bin/true",
                    ],
                ),
                mock.patch.object(
                    network_sandbox.sys,
                    "platform",
                    "darwin",
                ),
                redirect_stderr(stderr),
            ):
                result = network_sandbox.main()
        self.assertEqual(result, 126)
        self.assertIn("requires Linux", stderr.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
