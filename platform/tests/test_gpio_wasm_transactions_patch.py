"""Replay committed native+WASM GPIO sources and execute actual C contracts.

No checkout cache, downloaded source, firmware, QEMU executable or binary fixture
is required. GPIO/AW/RTC algorithms come from the committed patch replay; only
host environment glue and observations are shimmed. This is host C logic
validation, not guest, hardware or performance validation.
"""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_unit_flashlight_cold_pad_patch as replay

ROOT = replay.ROOT
HERE = Path(__file__).resolve().parent
PATCH = HERE.parents[1] / "patches/qemu-wasm-probe/0027-gpio-bounded-transactions.patch"
FIXTURE = HERE / "fixtures/gpio_wasm_transactions_harness.c"
BASE_SHA = "0158efd8e6dade72c68a6fd9bf0086fcba1fe4b39c8816ab2d30e19d0bb18c8f"
POST_SHA = "afb956b4b6b01989ca538fa2a1bddcd74bae7e08391fb498f475e585741bd576"
COMPANION_SHAS = {
    replay.HEADER: "ec1de9ac0f750c81d1ccc30ed7729e1316b2a63121f911eacc5eb9a8bb4b1a81",
    replay.UNIT: "c014cc46116f3a57d23fbd06719bdc9d3b2e04bdf74454caac9f726c8c77514b",
    replay.AUX: "52edd36d9b380b99ac7ece8ecb6a28ff37b79af14fabe8a31f04e03ddbf77c87",
    replay.AUX_HEADER: "e6ebf222cf20d85337168d9ae51399484a466d176d5b9995b125057892ef2a19",
    replay.RUNTIME_HEADER: "ef8a08f266438ac231970a2fb310f00f6587e049f37e7d29d70d52d8e537a222",
}
OLD_ORACLE_LIMITS = {"writer-pull-conflict", "open-drain-direct", "open-drain-mmio"}
AW_CASES = tuple(f"aw-{level}-{n}" for level in ("high", "low")
                 for n in (749, 750, 751, 9999, 10000, 10001)) + (
    "aw-reset-500000", "aw-reset-500001", "aw-settle-timeout")
BANK_CASES = (
    "bank-grid-s3", "bank-grid-classic", "bank-grid-advancing",
    "bank-selected-listener", "bank-selected-hole", "bank-selected-high",
    "bank-unselected-listener", "bank-dynamic-listener", "bank-dynamic-irq",
    "bank-level-hole", "bank-level-other", "bank-pending-disabled",
    "bank-edge-1", "bank-edge-2", "bank-edge-3",
    "bank-hole-edge-1", "bank-hole-edge-2", "bank-hole-edge-3",
    "bank-size-1", "bank-size-2", "bank-size-8",
)
IRQ_CASES = ("irq-grid-s3", "irq-grid-classic", "legacy-reentry-s3",
             "legacy-reentry-classic", "captured-line-s3", "captured-line-classic", "reset-level")


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def actual_program(sources, candidate):
    text, _ = replay.program(sources)
    name = "gpio_snapshot_internal_at" if candidate else "gpio_snapshot_internal"
    body = replay.function(text, name)
    text = text.replace(body, body.replace("\n{", "\n{\n    test_resolve_calls++;", 1), 1)
    if candidate:
        body = replay.function(text, "gpio_try_bank_fast")
        assert body.count("    return true;") == 1
        text = text.replace(body, body.replace("    return true;", "    test_fast_calls++;\n    return true;", 1), 1)
    text = text.replace("#include <inttypes.h>", """#include <inttypes.h>
static int64_t test_clock_step_ns;
static bool test_normalize_timestamp;
static uint64_t test_clock_calls, test_resolve_calls, test_irq_count, test_fast_calls;
static uint64_t test_irq_hash = UINT64_C(1469598103934665603);
static int test_irq_last;""", 1)
    clock = "    assert(type == QEMU_CLOCK_VIRTUAL);\n    return host_now_ns;"
    assert text.count(clock) == 1
    text = text.replace(clock, """    assert(type == QEMU_CLOCK_VIRTUAL);
    test_clock_calls++;
    int64_t sampled = host_now_ns;
    host_now_ns += test_clock_step_ns;
    return sampled;""", 1)
    irq = "void qemu_set_irq(qemu_irq irq, int level) { }"
    assert text.count(irq) == 1
    text = text.replace(irq, r'''void qemu_set_irq(qemu_irq irq, int level) {
    test_irq_last = level; test_irq_count++;
    test_irq_hash ^= (unsigned)level; test_irq_hash *= UINT64_C(1099511628211);
    test_irq_hash ^= g_regs[0x44/4]; test_irq_hash *= UINT64_C(1099511628211);
    test_irq_hash ^= g_regs[0x50/4]; test_irq_hash *= UINT64_C(1099511628211);
    printf("IRQ %d status0=%08x status1=%08x\n", level, g_regs[0x44/4], g_regs[0x50/4]);
    fflush(stdout);
}''', 1)
    text = text.replace("int main(int argc, char **argv)", "int fixture_main(int argc, char **argv)", 1)
    return text + "\n" + FIXTURE.read_text()


@unittest.skipUnless(shutil.which("cc") and shutil.which("git"), "C compiler and git required")
class GpioWasmTransactionPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="m5-gpio-transaction-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        tree = cls.directory / "source"
        cls.before = replay.replay(tree)
        board_bias = ROOT / "patches/qemu-wasm-probe/0021-board-bias-over-internal-pull.patch"
        subprocess.run(["git", "apply", "--include=" + replay.GPIO, str(board_bias)],
                       cwd=tree, check=True, capture_output=True)
        cls.before[replay.GPIO] = (tree / replay.GPIO).read_text()
        if digest(cls.before[replay.GPIO]) != BASE_SHA:
            raise AssertionError("committed replay plus board bias is not exact c6 GPIO")
        for name, expected in COMPANION_SHAS.items():
            if digest(cls.before[name]) != expected:
                raise AssertionError("companion model changed: " + name)
        subprocess.run(["git", "apply", "--check", str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", str(PATCH)], cwd=tree, check=True, capture_output=True)
        cls.after = {**cls.before, replay.GPIO: (tree / replay.GPIO).read_text()}
        if digest(cls.after[replay.GPIO]) != POST_SHA:
            raise AssertionError("overlay GPIO postimage changed")
        subprocess.run(["git", "apply", "--reverse", "--check", str(PATCH)], cwd=tree, check=True, capture_output=True)
        subprocess.run(["git", "apply", "--reverse", str(PATCH)], cwd=tree, check=True, capture_output=True)
        if (tree / replay.GPIO).read_text() != cls.before[replay.GPIO]:
            raise AssertionError("reverse patch did not restore exact c6")
        cls.binaries = {}
        for name, files, candidate in (("reference", cls.before, False), ("candidate", cls.after, True)):
            cls.binaries[name] = cls.compile(actual_program(files, candidate), name, candidate)

    @classmethod
    def compile(cls, source, name, candidate=True):
        path = cls.directory / (name + ".c")
        binary = path.with_suffix("")
        path.write_text(source)
        subprocess.run([shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable", "-Wno-sign-compare",
                        "-DOLD_RUNTIME=0", "-DTEST_BATCHED=" + str(int(candidate)),
                        "-DTEST_STAGE4A=" + str(int(candidate)), "-DTEST_STAGE4B=" + str(int(candidate)),
                        "-DTEST_CANDIDATE=" + str(int(candidate)), str(path), "-o", str(binary)],
                       check=True, capture_output=True, text=True, timeout=30)
        return binary

    def execute(self, name, case):
        # glibc prefixes assertion failures with argv[0]. Keep that diagnostic
        # identity equal while executing the two distinct real binaries.
        p = subprocess.run(["gpio-transaction-contract", case], executable=str(self.binaries[name]),
                           capture_output=True, text=True, timeout=15)
        err = p.stderr.replace(str(self.binaries[name]) + ".c", "actual-source.c")
        err = err.replace(str(self.binaries[name]), "actual-source")
        err = re.sub(r"file [^,\n]+\.c, line \d+", "file actual-source.c, line OMITTED", err)
        err = re.sub(r"actual-source\.c:\d+", "actual-source.c:LINE", err)
        return p.returncode, p.stdout, err

    def test_glibc_assert_diagnostics_preserve_meaningful_differences(self):
        # Captured Linux CI assertion shape, without depending on its raw log
        # or changing the full stderr comparison used by the actual C cases.
        expression = "aw->reset_at_ns == -1 && aw->settle_at_ns == -1 && aw->timeout_at_ns == -1"
        calls = []
        difference = None

        def captured_glibc(args, *, executable, **options):
            calls.append((args, executable))
            stderr = (f"{Path(args[0]).name}: {executable}.c:73: assert_lost: "
                      f"Assertion `{expression}' failed.\n")
            result = (-6, "IRQ 0 status0=00000000 status1=00000000\n", stderr)
            if Path(executable).name == "candidate" and difference:
                result = difference(result)
            return subprocess.CompletedProcess(args, *result)

        with patch.object(subprocess, "run", side_effect=captured_glibc):
            reference = self.execute("reference", "writer-pull-conflict")
            self.assertEqual(reference, self.execute("candidate", "writer-pull-conflict"))
            self.assertEqual(calls[0][0], calls[1][0])
            self.assertEqual(calls[0][0][1], "writer-pull-conflict")
            self.assertEqual([call[1] for call in calls],
                             [str(self.binaries[name]) for name in ("reference", "candidate")])
            self.assertIn("assert_lost: Assertion `" + expression + "' failed.", reference[2])
            differences = {
                "assert-expression": lambda r: (r[0], r[1], r[2].replace("timeout_at_ns == -1", "timeout_at_ns == 0")),
                "assert-function": lambda r: (r[0], r[1], r[2].replace("assert_lost:", "other_assert:")),
                "other-stderr": lambda r: (r[0], r[1], r[2] + "additional controller diagnostic\n"),
                "signal": lambda r: (-11, r[1], r[2]),
                "stdout-tape": lambda r: (r[0], r[1].replace("IRQ 0", "IRQ 1"), r[2]),
            }
            for name, difference in differences.items():
                with self.subTest(difference=name):
                    self.assertNotEqual(reference, self.execute("candidate", "writer-pull-conflict"))

    def test_fixed_clock_original_cases_and_explicit_oracle_limits(self):
        for case in replay.CASES:
            with self.subTest(case=case):
                before, after = self.execute("reference", case), self.execute("candidate", case)
                self.assertEqual(before, after)
                if case in OLD_ORACLE_LIMITS:
                    self.assertNotEqual(after[0], 0, "old native oracle limit must remain visible")
                else:
                    self.assertEqual(after[0], 0, after)

    def test_full_callback_irq_bank_guard_and_structural_parity(self):
        for case in ("grid-s3", "grid-classic", *IRQ_CASES, *BANK_CASES):
            with self.subTest(case=case):
                before, after = self.execute("reference", case), self.execute("candidate", case)
                self.assertEqual(before[0], 0, before)
                self.assertEqual(after[0], 0, after)
                self.assertEqual(before, after)
        # Advancing-clock bank hashes normalize only snapshot.at_ns in the
        # observer; intentional batching is separately asserted below. All
        # other facts and the complete per-call IRQ/STATUS tape remain exact.

    def test_advancing_clock_policy_and_exact_aw_boundaries(self):
        old = self.execute("reference", "advancing-clock")
        new = self.execute("candidate", "advancing-clock")
        self.assertEqual(old[0], 0, old); self.assertEqual(new[0], 0, new)
        self.assertIn("per-pin timestamps differ", old[1])
        self.assertIn("capture=1 notify=1", new[1])
        for case in (*AW_CASES, "bank-guards"):
            with self.subTest(case=case):
                result = self.execute("candidate", case)
                self.assertEqual(result[0], 0, result)

    def test_resolver_work_reduction_without_irq_or_clock_fabrication(self):
        for variant, expected in (("reference", (27900, 27900, 0)), ("candidate", (200, 200, 100))):
            result = self.execute(variant, "bank-work-count")
            self.assertEqual(result[0], 0, result)
            m = re.search(r"COUNT bank clocks=(\d+) resolves=(\d+) fast=(\d+)", result[1])
            self.assertIsNotNone(m)
            self.assertEqual(tuple(map(int, m.groups())), expected)
            measured = result[1].split("BEGIN BANK COUNT\n", 1)[1]
            self.assertEqual(len(re.findall(r"^IRQ ", measured, re.M)), 100)

    def test_wrong_irq_filter_stale_after_and_dropped_calls_are_detected(self):
        gpio = self.after[replay.GPIO]
        mutations = (
            ("filtered-irq", "gpio_update_irq_with_line(false, 0);",
             "gpio_update_irq_with_line(true, gpio_input64());", "irq-grid-s3"),
            ("stale-after", "gpio_transition_irq(full_before, gpio_line64());",
             "gpio_transition_irq(full_before, full_after);", "bank-dynamic-irq"),
            ("dropped-irq", "    qemu_set_irq(g_gpio_device->irq,",
             "    if (g_regs[0x44/4] | g_regs[0x50/4]) qemu_set_irq(g_gpio_device->irq,", "irq-grid-s3"),
        )
        for name, before, after, case in mutations:
            with self.subTest(mutation=name):
                self.assertEqual(gpio.count(before), 1)
                changed = {**self.after, replay.GPIO: gpio.replace(before, after, 1)}
                self.binaries[name] = self.compile(actual_program(changed, True), name)
                self.assertNotEqual(self.execute(name, case)[0], 0, "bad real-source mutation escaped the contract")

    def test_reset_rejects_pre_callback_level_reuse(self):
        # Recreate the former71 tail in the actual translated source. The
        # executed path includes reset_hold, reset listeners, ordinary legacy
        # listeners, nested input/status writes, and both final IRQ refreshes.
        gpio = self.after[replay.GPIO]
        body = replay.function(gpio, "gpio_transition_irq")
        self.assertEqual(body.count("    gpio_update_irq();"), 1)
        stale = body.replace("    gpio_update_irq();", "    gpio_update_irq_with_line(true, after);", 1)
        changed = {**self.after, replay.GPIO: gpio.replace(body, stale, 1)}
        self.binaries["former71-reset"] = self.compile(actual_program(changed, True), "former71-reset")
        result = self.execute("former71-reset", "reset-level")
        self.assertNotEqual(result[0], 0, "stale reset-level implementation escaped the actual reset contract")
        self.assertIn("RESET pending=1", result[1])


if __name__ == "__main__":
    unittest.main()
