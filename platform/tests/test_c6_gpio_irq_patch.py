"""Replay C6 GPIO IRQ patch against fixed actual sources and sanitizer controls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).with_name("fixtures") / "c6_gpio_irq"
PATCH = ROOT / "patches/qemu-esp32c6-uiflow2-adapters/0024-c6-gpio-interrupt-delivery.patch"
CHECK = ROOT / "tests/firmware/esp32c6_gpio_irq/check_controller_actual_c.py"


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class C6GpioIrqPatchTests(unittest.TestCase):
    def test_actual_controller_before_and_after(self):
        provenance = json.loads((FIXTURE / "source-provenance.json").read_text())
        for name, expected in provenance["fixture_files"].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), expected, name)
        with tempfile.TemporaryDirectory(prefix="m5-c6-gpio-irq-") as temporary:
            candidate = Path(temporary) / "candidate"
            shutil.copytree(FIXTURE, candidate)
            for options in (["--check"], [], ["--reverse", "--check"]):
                result = subprocess.run(["git", "apply", *options, str(PATCH)], cwd=candidate,
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
            machine = (candidate / "hw/riscv/esp32c6.c").read_text()
            self.assertIn("qdev_get_gpio_in(intmatrix_dev, C6_ETS_GPIO_INTR_SOURCE)", machine)
            self.assertIn('"irq-pin-count", 31', (candidate / "hw/gpio/esp32c6_gpio.c").read_text())
            self.assertIn('"irq-pin-count", Esp32GpioState, irq_pin_count, 0',
                          (candidate / "hw/gpio/esp32_gpio.c").read_text())
            for source, args in ((FIXTURE, ["--baseline"]), (candidate, [])):
                with self.subTest(source=source.name):
                    process = subprocess.run([sys.executable, str(CHECK), "--source", str(source), *args],
                                             text=True, capture_output=True, timeout=45)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    result = json.loads(process.stdout)
                    self.assertEqual(result["status"], "PASS")
                    self.assertEqual(len(result["observations"]), 45)
                    if source != FIXTURE:
                        self.assertTrue(all(result["observations"].values()))


if __name__ == "__main__":
    unittest.main()
