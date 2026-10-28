"""Replay the Core2 dual-SPI panel routing patch."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack


PATCH = "patches/qemu-m5stack-peripherals/0068-core2-dual-spi-panel-routing.patch"
CORE2 = "hw/m5stopwatch/m5core2.c"


class Core2DualSpiPanelPatchTests(unittest.TestCase):
    def test_patch_routes_the_shared_panel_from_hspi_and_vspi(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
                capture_output=True,
            )
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                subprocess.run(
                    [
                        "git",
                        "apply",
                        "--include=" + CORE2,
                        str(ROOT / patch),
                    ],
                    cwd=root,
                    check=True,
                    capture_output=True,
                )
            subprocess.run(
                ["git", "apply", str(ROOT / PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
            )
            core2 = (root / CORE2).read_text()
            self.assertIn(
                "esp32_spi_attach_m5_panel(DEVICE(&s->spi[2]), panel, 15);",
                core2,
            )
            self.assertIn(
                "esp32_spi_attach_m5_panel(DEVICE(&s->spi[3]), panel, 15);",
                core2,
            )
            self.assertLess(
                core2.index("DEVICE(&s->spi[2])"),
                core2.index("DEVICE(&s->spi[3])"),
            )
            subprocess.run(
                ["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    unittest.main()
