"""Replay 0092 and execute its actual SENS C with a controlled virtual clock.

The fixture is the complete preimage for this historical patch boundary. Only
the QEMU timer/MMIO/QOM transport and ADC sample provider are test doubles;
register writes, controller state, conversion and reset use the patched C.
This is a native source contract, not guest/QEMU or physical touch evidence.
"""

from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/qemu-m5stack-peripherals/0092-classic-touch-measurement.patch"
FIXTURE = ROOT / "platform/tests/fixtures/classic_touch_sens"
SOURCE = Path("hw/m5stopwatch/esp32s3_sens.c")
PREIMAGE_SHA256 = "5983b01086efb7710f04de12c3871e93cab41c81d23bd2cf880d08ef3769e5a5"
IMPLEMENTATION_MARKER = "/* EXACT_SENS_IMPLEMENTATION */"
CASES = {
    "factory_defaults_and_qom_inputs",
    "software_timing_pulse_readonly_and_slots",
    "threshold_status_clear_and_saturation",
    "timer_gate_and_repeated_cycles",
    "rtc_slow_clock_selection",
    "timer_to_software_during_sleep_requires_start",
    "timer_to_software_inflight_still_completes",
    "disable_gate_fsm_and_invalid_starts",
    "latched_workmask_timing_and_results",
    "reset_cancels_inflight_and_restores_status",
    "adc_s3_and_classic_regression",
    "tsens_and_invalid_access_regression",
}


class ClassicTouchFixtureTests(unittest.TestCase):
    def test_pinned_complete_preimage(self):
        self.assertEqual(
            hashlib.sha256((FIXTURE / "esp32s3_sens.c").read_bytes()).hexdigest(),
            PREIMAGE_SHA256,
        )


@unittest.skipUnless(shutil.which("git"), "Git is required to replay the actual SENS patch")
@unittest.skipUnless(shutil.which("cc"), "A C compiler is required for the actual SENS contract")
class ClassicTouchMeasurementPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="m5-classic-touch-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        target = cls.root / SOURCE
        target.parent.mkdir(parents=True)
        target.write_bytes((FIXTURE / "esp32s3_sens.c").read_bytes())
        for options in (("--check",), (), ("--reverse", "--check")):
            subprocess.run(
                ["git", "apply", *options, str(PATCH)], cwd=cls.root,
                check=True, capture_output=True, text=True, timeout=30,
            )
        cls.source = target.read_text()
        cls.template = (FIXTURE / "contract.c.in").read_text()
        if cls.template.count(IMPLEMENTATION_MARKER) != 1:
            raise AssertionError("The contract must have one exact-source insertion point")

    def compile_and_run(self, source, label):
        # Keep all source after QEMU's include block verbatim, including the
        # real factory, QOM registration, reset, read/write and timer callbacks.
        marker = "#define SENS_SIZE"
        self.assertEqual(source.count(marker), 1)
        implementation = source[source.index(marker):]
        program = self.template.replace(IMPLEMENTATION_MARKER, implementation)
        cfile, binary = self.root / (label + ".c"), self.root / label
        cfile.write_text(program)
        compiled = subprocess.run(
            [shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
             str(cfile), "-o", str(binary)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        return subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)

    def test_actual_controller_clock_register_input_and_reset_contracts(self):
        result = self.compile_and_run(self.source, "candidate")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        passed = {line.removeprefix("PASS ") for line in result.stdout.splitlines()
                  if line.startswith("PASS ")}
        self.assertEqual(passed, CASES, result.stdout)
        self.assertIn("TOTAL 12 FAIL 0", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_independent_negative_controls_reject_controller_regressions(self):
        controls = (
            (
                "sleep-to-software-ignores-transition",
                "    if ((s->regs[TOUCH_CTRL2 / 4] & TOUCH_SW) && s->touch_sleeping) {\n"
                "        timer_del(s->touch_timer);\n"
                "        s->touch_sleeping = false;\n"
                "    }\n",
                "",
                "timer_to_software_during_sleep_requires_start",
            ),
            (
                "new-start-keeps-stale-done",
                "s->regs[TOUCH_CTRL2 / 4] &= ~(TOUCH_DONE | TOUCH_START);",
                "s->regs[TOUCH_CTRL2 / 4] &= ~TOUCH_START;",
                "software_timing_pulse_readonly_and_slots",
            ),
            (
                "readonly-output-forgery",
                "return; /* Measurement counters are read-only. */",
                "s->regs[addr / 4] = value; return; /* Negative control. */",
                "software_timing_pulse_readonly_and_slots",
            ),
            (
                "qom-input-is-ignored",
                "uint64_t frequency = s->touch_input_hz[channel];",
                "uint64_t frequency = 1000000;",
                "factory_defaults_and_qom_inputs",
            ),
        )
        for label, original, replacement, rejected_case in controls:
            with self.subTest(control=label):
                self.assertEqual(self.source.count(original), 1)
                result = self.compile_and_run(self.source.replace(original, replacement), label)
                # An assertion rejection is expected, not a compiler failure,
                # crash, timeout or merely a missing PASS marker.
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("FAIL " + rejected_case + "\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
