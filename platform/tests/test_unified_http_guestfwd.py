#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "platform/tools/unified_http_guestfwd.py"


class UnifiedHttpGuestFwdTests(unittest.TestCase):
    def test_serves_request_and_records_session_log(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "http-fixture.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(HELPER),
                    "--log",
                    str(log),
                    "--body-hex",
                    b"UNIFIED_CORE2_OK\n".hex(),
                ],
                input=(
                    b"GET /unified HTTP/1.0\r\n"
                    b"Host: qemu.test\r\n\r\n"
                ),
                capture_output=True,
                check=False,
                timeout=10,
            )
            rows = json.loads(log.read_text())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith(b"HTTP/1.0 200 OK\r\n"))
        self.assertTrue(
            result.stdout.endswith(b"UNIFIED_CORE2_OK\n")
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], "/unified")
        self.assertEqual(rows[0]["host"], "qemu.test")
        self.assertEqual(rows[0]["transport"], "qemu-guestfwd")


if __name__ == "__main__":
    unittest.main()
