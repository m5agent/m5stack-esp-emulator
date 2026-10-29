"""Replay real GPIO/soft-I2C patch bytes; test nominal wiring without QEMU.

The pre-fix bridge runs against the same current GPIO controller as the fixed
bridge, isolating the missing board pull-ups. This is host C logic evidence;
the I2C endpoint methods are shims, not guest or hardware validation.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_unit_flashlight_cold_pad_patch as cold

BRIDGE = "hw/m5stopwatch/esp32s3_soft_i2c.c"
FIXTURE = Path(__file__).with_name("fixtures") / "soft_i2c_pullup_harness.c"


def replay_bridge(root, current=True):
    stack = cold.bootstrap_stack()
    if not current:
        # This negative control is the real pre-0047 bridge. Later bridge
        # patches depend on its pull-up initialization and cannot be applied
        # after deleting their prerequisite from an otherwise current stack.
        stack = stack[:stack.index(cold.PATCH)]
    for name in stack:
        if BRIDGE not in cold.patch_paths(name):
            continue
        command = ["git", "apply", "--include=" + BRIDGE]
        subprocess.run(command + ["--check", str(cold.ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
        subprocess.run(command + [str(cold.ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
    return (root / BRIDGE).read_text()


def program(sources, bridge):
    controller, manifest = cold.program(sources)
    main = "int main(int argc, char **argv)\n{"
    if controller.count(main) != 1:
        raise AssertionError("cold-pad fixture main entry changed")
    fixture = FIXTURE.read_text()
    if fixture.count("/* BRIDGE_SOURCE */") != 1:
        raise AssertionError("soft-I2C fixture requires one source insertion point")
    bridge_body = cold.without_includes(bridge)
    result = controller[:controller.index(main)] + fixture.replace(
        "/* BRIDGE_SOURCE */", bridge_body)
    # Includes alone are shimmed. The entire actual bridge algorithm is kept.
    if bridge_body not in result:
        raise AssertionError("actual bridge bytes changed during composition")
    return result, {"controller": manifest, "bridge": cold.digest(bridge),
                    "fixture": cold.digest(fixture), "program": cold.digest(result)}


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class SoftI2CPullupPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        cls.binaries = {}
        for current in (False, True):
            name = "after" if current else "before"
            root = directory / name
            sources = cold.replay(root)
            bridge = replay_bridge(root, current)
            source, manifest = program(sources, bridge)
            path = directory / (name + ".c")
            path.write_text(source)
            binary = path.with_suffix(".bin")
            # The unmodified GPIO replay uses signed -1/unsigned ternaries.
            # Match the cold-pad harness exception and retain all other -Werror.
            result = subprocess.run([
                shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-sign-compare",
                "-DOLD_RUNTIME=0", "-DWITH_PULLUPS=" + str(int(current)),
                str(path), "-o", str(binary),
            ], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries[current] = binary

    def run_case(self, current, case):
        result = subprocess.run([str(self.binaries[current]), case],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_real_bridge_restores_s3_probe_and_retains_unknown_pull_conflict(self):
        for case in ("cores3", "stopwatch"):
            with self.subTest(case=case):
                self.assertIn("probe=0x1 known=1 conflict=0 board_up=0 external=0 ie=1",
                              self.run_case(False, case))
                self.assertIn("probe=0x3 known=0 conflict=1 board_up=1 external=0 ie=1",
                              self.run_case(True, case))

    def test_core2_legacy_levels_are_unchanged(self):
        for current in (False, True):
            with self.subTest(current=current):
                self.assertIn("core2 high=1,1 driven_low=0 released=1",
                              self.run_case(current, "core2"))


if __name__ == "__main__":
    unittest.main()
