"""Replay the Core2 touch-button key routing patch without QEMU."""

from pathlib import Path
import subprocess
import tempfile
import unittest

from test_unit_flashlight_cold_pad_patch import ROOT, bootstrap_stack


PATCH = "patches/qemu-m5stack-peripherals/0063-core2-touch-buttons.patch"
PANEL = "hw/m5stopwatch/m5_spi_panel.c"
CORE2 = "hw/m5stopwatch/m5core2.c"


class Core2TouchButtonsPatchTests(unittest.TestCase):
    def test_patch_applies_and_wires_core2_touch_band(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            for patch in bootstrap_stack():
                if patch == PATCH:
                    break
                subprocess.run(
                    [
                        "git",
                        "apply",
                        "--include=" + PANEL,
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
            panel = (root / PANEL).read_text()
            core2 = (root / CORE2).read_text()
            self.assertIn("bool touch_buttons;", panel)
            self.assertIn('DEFINE_PROP_BOOL("touch-buttons"', panel)
            self.assertIn(
                "if (s->touch_buttons\n"
                "            && (q == Q_KEY_CODE_A || q == Q_KEY_CODE_B "
                "|| q == Q_KEY_CODE_C))",
                panel,
            )
            self.assertIn("x = s->vis_w / 6", panel)
            self.assertIn("x = s->vis_w / 2", panel)
            self.assertIn("x = s->vis_w * 5 / 6", panel)
            self.assertIn("s->vis_h + 20", panel)
            touch_branch = panel.index("if (s->touch_buttons")
            power_branch = panel.index("m5sw_pwr_button(down);", touch_branch)
            self.assertLess(touch_branch, power_branch)
            self.assertIn(
                'qdev_prop_set_bit(panel, "touch-buttons", true)',
                core2,
            )
            subprocess.run(
                ["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                cwd=root,
                check=True,
                capture_output=True,
            )


if __name__ == "__main__":
    unittest.main()
