"""Final ZIP serial is authoritative, including faults after the last poll."""
import ast
import hashlib
import io
import json
from pathlib import Path
import runpy
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SOURCE = Path(__file__).resolve().parents[2] / "tests/firmware/nesso_touch_bus_shared/run_probe.py"


class NessoTouchProbeTests(unittest.TestCase):
    def test_complete_serial_rejects_late_faults(self):
        # Execute the actual helper without importing the CLI/network runner.
        tree = ast.parse(SOURCE.read_text())
        function = next(node for node in tree.body
                        if isinstance(node, ast.FunctionDef) and node.name == "validate_serial")
        namespace = {}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), "exec"), namespace)
        validate = namespace["validate_serial"]
        clean = "ESP-ROM:esp32c6\nPROBE_READY touch_bus_shared=0\nOWNER_RELEASE_OK\n"
        clean += "count=1 x=20 y=30\ncount=1 x=100 y=180\ncount=1 x=60 y=100\n"
        validate(clean, "after")
        for late in ("ESP-ROM:esp32c6\n", "assert failed: xTaskPriorityDisinherit\n",
                     "assert failed: another_function\n", "Guru Meditation Error: Core 0 panic'ed\n",
                     "abort() was called at PC 0x40800000\n",
                     "task_wdt: Task watchdog got triggered\n", "Interrupt wdt timeout on CPU0\n"):
            with self.subTest(late=late), self.assertRaises(AssertionError):
                validate(clean + late, "after")
        for missing in ("PROBE_READY", "touch_bus_shared=0", "OWNER_RELEASE_OK",
                        "count=1 x=20 y=30", "count=1 x=100 y=180", "count=1 x=60 y=100"):
            with self.subTest(missing=missing), self.assertRaises(AssertionError):
                validate(clean.replace(missing, "missing"), "after")
        validate("PROBE_READY touch_bus_shared=1\nassert failed: xTaskPriorityDisinherit", "before")
        with self.assertRaises(AssertionError):
            validate(clean, "before")

    def test_runner_saves_late_failure_after_evidence_and_cleanup(self):
        # Exercise the CLI's real finally/result path. Only host I/O and time
        # are mocked; the final ZIP differs from every clean polling response.
        clean = "ESP-ROM:esp32c6\nPROBE_READY touch_bus_shared=0\nOWNER_RELEASE_OK\n"
        clean += "count=1 x=20 y=30\ncount=1 x=100 y=180\ncount=1 x=60 y=100\n"
        for late in ("ESP-ROM:esp32c6\n", "assert failed: xTaskPriorityDisinherit\n",
                     "Guru Meditation Error: Core 0 panic'ed\n",
                     "abort() was called at PC 0x40800000\n",
                     "task_wdt: Task watchdog got triggered\n"):
            with self.subTest(late=late), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                image = bytearray(b"\xff" * 0x11000)
                struct.pack_into("<HBBII16sI", image, 0x8000,
                                 0x50aa, 0, 0, 0x10000, 0x1000, b"factory", 0)
                firmware = root / "firmware.bin"
                firmware.write_bytes(image)
                runtime = root / "runtime"
                runtime.write_bytes(b"owned-runtime-fixture")
                bundle = io.BytesIO()
                with zipfile.ZipFile(bundle, "w") as archive:
                    archive.writestr("serial.log", clean + late)
                    archive.writestr("flash/virtual-flash.bin", image)
                calls = []
                stopped = False
                clock = 0

                def now():
                    nonlocal clock
                    clock += 1
                    return clock

                def response(request, timeout=None):
                    nonlocal stopped
                    method, path = request.method, request.full_url.split("/api/v1/")[1]
                    calls.append((method, path))
                    if path == "artifacts":
                        value = {"artifact_id": "artifact"}
                    elif path == "firmware/import":
                        value = {"firmware_id": "firmware"}
                    elif path == "sessions":
                        value = {"session_id": "owned"}
                    elif "/serial?" in path:
                        value = {"data": clean}
                    elif "/input" in path:
                        value = {"accepted": True}
                    elif "/evidence?" in path:
                        value = bundle.getvalue()
                    elif "/frame.png?" in path:
                        value = b"frame"
                    else:
                        if method == "DELETE":
                            stopped = True
                        value = {"state": "stopped" if stopped else "running", "pid": 123,
                                 "flash_retained": not stopped,
                                 "worker": {"lease_active": not stopped}}
                    stream = io.BytesIO(value if isinstance(value, bytes) else json.dumps(value).encode())
                    stream.headers = {"Content-Type": "application/octet-stream" if isinstance(value, bytes)
                                      else "application/json"}
                    return stream

                out = root / "result"
                argv = [str(SOURCE), "--base-url", "http://owned.invalid", "--mode", "after",
                        "--firmware", str(firmware), "--firmware-sha256", hashlib.sha256(image).hexdigest(),
                        "--runtime-sha256", hashlib.sha256(runtime.read_bytes()).hexdigest(), "--out", str(out)]
                with patch("sys.argv", argv), patch("urllib.request.urlopen", side_effect=response), \
                        patch("time.monotonic", side_effect=now), patch("time.sleep"), \
                        patch("subprocess.check_output", return_value=str(runtime)), \
                        patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1)), \
                        patch("builtins.print"), self.assertRaises(AssertionError):
                    runpy.run_path(str(SOURCE), run_name="__main__")
                summary = json.loads((out / "summary.json").read_text())
                self.assertEqual(summary["status"], "FAIL")
                self.assertIsNotNone(summary["error"])
                self.assertIsNone(summary["cleanup_error"])
                self.assertEqual(summary["terminal_state"], "stopped")
                self.assertTrue(summary["zip_before_stop"])
                self.assertTrue(summary["flash_released"] and summary["lease_released"])
                evidence_index = next(i for i, (_, path) in enumerate(calls) if "/evidence?" in path)
                stop_index = next(i for i, (method, _) in enumerate(calls) if method == "DELETE")
                self.assertLess(evidence_index, stop_index)


if __name__ == "__main__":
    unittest.main()
