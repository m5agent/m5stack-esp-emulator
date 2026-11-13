"""Final ZIP serial is authoritative, including faults after the last poll."""
import ast
from pathlib import Path
import unittest

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
                     "assert failed: another_function\n"):
            with self.subTest(late=late), self.assertRaises(AssertionError):
                validate(clean + late, "after")
        for missing in ("PROBE_READY", "touch_bus_shared=0", "OWNER_RELEASE_OK",
                        "count=1 x=20 y=30", "count=1 x=100 y=180", "count=1 x=60 y=100"):
            with self.subTest(missing=missing), self.assertRaises(AssertionError):
                validate(clean.replace(missing, "missing"), "after")
        validate("PROBE_READY touch_bus_shared=1\nassert failed: xTaskPriorityDisinherit", "before")
        with self.assertRaises(AssertionError):
            validate(clean, "before")


if __name__ == "__main__":
    unittest.main()
