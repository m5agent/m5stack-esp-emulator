from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = "patches/qemu-m5stack-peripherals/0048-unit-servos8-joystick2-nfc.patch"


class UnitIssueControllerPatchTests(unittest.TestCase):
    def test_patch_is_part_of_the_cold_build_stack(self):
        tree = ast.parse((ROOT / "scripts/bootstrap-unit-runtime.py").read_text())
        patches = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "PATCHES"
                for target in node.targets
            )
        )
        self.assertIn(PATCH, patches)
        self.assertGreater(patches.index(PATCH), patches.index(
            "patches/qemu-m5stack-peripherals/0047-unit-flashlight-cold-pad-observation.patch"
        ))
        self.assertEqual(len(patches), len(set(patches)))

    def test_patch_only_touches_the_three_unit_controller_sources(self):
        patch = (ROOT / PATCH).read_text()
        paths = {
            line[6:]
            for line in patch.splitlines()
            if line.startswith("+++ b/")
        }
        self.assertEqual(
            paths,
            {
                "hw/m5stopwatch/m5_unit_i2c_controls.c",
                "hw/m5stopwatch/m5_unit_runtime.c",
                "hw/m5stopwatch/m5sw_i2c_devs.c",
            },
        )
        for marker in ("servo8-hat", "8servos", "joystick2", "st25r3916"):
            self.assertIn(marker, patch)


if __name__ == "__main__":
    unittest.main()
