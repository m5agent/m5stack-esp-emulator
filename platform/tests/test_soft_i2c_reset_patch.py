"""Compile exact replayed S3 GPIO/bridge bytes for reset/handoff regression.

The same real source regression must fail before 0097. Endpoint transport is
an explicit local register-bank shim; this proves host bridge protocol logic,
not guest execution, QEMU peripheral correctness or physical hardware.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_unit_flashlight_cold_pad_patch as cold

BRIDGE = "hw/m5stopwatch/esp32s3_soft_i2c.c"
PATCH = "patches/qemu-m5stack-peripherals/0097-s3-soft-i2c-reset-handoff.patch"
FIXTURE = Path(__file__).with_name("fixtures") / "soft_i2c_reset_harness.c"


def replay_bridge(root, current=True):
    stack = [name for name in cold.bootstrap_stack() if name != PATCH]
    if current:
        stack.append(PATCH)
    for name in stack:
        if BRIDGE not in cold.patch_paths(name):
            continue
        command = ["git", "apply", "--include=" + BRIDGE]
        subprocess.run(command + ["--check", str(cold.ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
        subprocess.run(command + [str(cold.ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
    source = (root / BRIDGE).read_text()
    if current:
        subprocess.run(["git", "apply", "--reverse", "--check", "--include=" + BRIDGE,
                        str(cold.ROOT / PATCH)], cwd=root, check=True,
                       capture_output=True, timeout=10)
    return source


def program(sources, bridge):
    controller, manifest = cold.program(sources)
    main = "int main(int argc, char **argv)\n{"
    if controller.count(main) != 1:
        raise AssertionError("cold-pad fixture main entry changed")
    fixture = FIXTURE.read_text()
    if fixture.count("/* BRIDGE_SOURCE */") != 1:
        raise AssertionError("reset fixture needs one bridge insertion point")
    body = cold.without_includes(bridge)
    result = controller[:controller.index(main)] + fixture.replace("/* BRIDGE_SOURCE */", body)
    if body not in result:
        raise AssertionError("actual bridge algorithm was modified")
    return result, {"controller": manifest, "bridge": cold.digest(bridge),
                    "fixture": cold.digest(fixture), "program": cold.digest(result)}


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class SoftI2CResetPatchTests(unittest.TestCase):
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
            source, _ = program(sources, bridge)
            path = directory / (name + ".c")
            path.write_text(source)
            binary = path.with_suffix(".bin")
            result = subprocess.run([
                shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                "-Wno-sign-compare", "-DOLD_RUNTIME=0", str(path), "-o", str(binary),
            ], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries[current] = binary

    def run_case(self, current, case):
        return subprocess.run([str(self.binaries[current]), case], capture_output=True,
                              text=True, timeout=5)

    def test_warm_reset_reopens_probe_then_hands_off_again(self):
        for case in ("cores3", "stopwatch"):
            with self.subTest(case=case):
                before = self.run_case(False, case)
                self.assertNotEqual(before.returncode, 0)
                self.assertIn("!s->hardware_active", before.stderr)
                after = self.run_case(True, case)
                self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
                self.assertIn("ACK/read -> handoff PASS", after.stdout)

    def test_reset_aborts_only_owned_ack_or_receive_transaction(self):
        for case in ("ack", "rx"):
            with self.subTest(case=case):
                before = self.run_case(False, case)
                self.assertNotEqual(before.returncode, 0)
                after = self.run_case(True, case)
                self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
                self.assertIn("registers/line samples retained PASS", after.stdout)

    def test_classic_registration_and_idle_levels_remain_unchanged(self):
        for current in (False, True):
            with self.subTest(current=current):
                result = self.run_case(current, "classic")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fresh_reset_does_not_invent_or_override_external_sda_source(self):
        for case in ("fresh", "external-low"):
            with self.subTest(case=case):
                result = self.run_case(True, case)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("independent external SDA source and board bias PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
