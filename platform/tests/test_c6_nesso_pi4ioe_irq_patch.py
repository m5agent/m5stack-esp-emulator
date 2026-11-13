"""Run the shared Nesso controller checks against exact before/after sources."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "c6_nesso_pi4ioe_irq"
CONTROLLER = "hw/misc/esp32c6_board_i2c.c"
PATCH = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0023-c6-nesso-shared-interrupt-pad.patch"
CHECK = ROOT / "tests/firmware/esp32c6_nesso_pi4ioe_irq/check_controller_actual_c.py"


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6NessoPi4ioePatchTests(unittest.TestCase):
    def test_actual_controller_before_and_after(self):
        provenance = json.loads((FIXTURE / "source-provenance.json").read_text())
        expected = provenance["fixture_files"][CONTROLLER]
        self.assertEqual(hashlib.sha256((FIXTURE / CONTROLLER).read_bytes()).hexdigest(), expected)
        with tempfile.TemporaryDirectory(prefix="m5-c6-nesso-pi4ioe-") as temporary:
            candidate = Path(temporary) / "candidate"
            shutil.copytree(FIXTURE, candidate)
            for options in (["--check"], [], ["--reverse", "--check"]):
                patch = subprocess.run(["git", "apply", *options, str(PATCH)], cwd=candidate,
                                       text=True, capture_output=True, timeout=10)
                self.assertEqual(patch.returncode, 0, patch.stderr)
            for source, args in ((FIXTURE, ["--baseline"]), (candidate, [])):
                with self.subTest(source=source.name):
                    process = subprocess.run([sys.executable, str(CHECK), "--source", str(source), *args],
                                             text=True, capture_output=True, timeout=45)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    result = json.loads(process.stdout)
                    self.assertEqual(result["status"], "PASS")
                    self.assertEqual(len(result["observations"]), 17)
                    if source == FIXTURE:
                        self.assertEqual(result["controller_source_sha256"], expected)
                    else:
                        self.assertTrue(all(result["observations"].values()))


if __name__ == "__main__":
    unittest.main()
