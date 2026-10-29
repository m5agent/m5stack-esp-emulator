"""Replay exact UART/S3-shim/Fifo8 C for the IDF RXFIFO-reset pulse.

Pinned upstream seeds and tracked patches supply all controller/FIFO code.
Only QOM, character-backend, IRQ sink and deterministic timer plumbing are
shimmed. This is a host controller regression, never a guest or hardware PASS.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_stackchan_scs_patch as scs
import test_unit_flashlight_cold_pad_patch as cold

ROOT = Path(__file__).resolve().parents[2]
SEEDS = Path(__file__).with_name("fixtures") / "uart_rxfifo_reset_upstream"
FIXTURE = Path(__file__).with_name("fixtures") / "uart_rxfifo_reset_harness.c"
PATCH = "patches/qemu-m5stack-peripherals/0098-uart-rxfifo-reset.patch"
PIN = "40edccac415693c5130f91c01d84176ae6008566"
PARENT = "hw/char/esp32_uart.c"
S3 = "hw/char/esp32s3_uart.c"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replay(root, current):
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    manifest = json.loads((SEEDS / "manifest.json").read_text())
    lock = json.loads((ROOT / "scripts/qemu-wasm-build/sources.lock.json").read_text())
    if manifest["commit"] != PIN or lock["qemu"]["commit"] != PIN:
        raise AssertionError("UART upstream pin changed; update exact replay seeds")
    for name, row in manifest["files"].items():
        data = (SEEDS / name).read_bytes()
        if digest(data) != row["sha256"]:
            raise AssertionError("UART seed identity changed: " + name)
        target = root / row["upstream_path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    paths = {row["upstream_path"] for row in manifest["files"].values()}
    stack = [row["path"] for row in lock["patches"] if row["path"] != PATCH]
    if current:
        stack.append(PATCH)
    for name in stack:
        if not cold.patch_paths(name) & paths:
            continue
        command = ["git", "apply", *["--include=" + path for path in sorted(paths)]]
        subprocess.run(command + ["--check", str(ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
        subprocess.run(command + [str(ROOT / name)], cwd=root,
                       check=True, capture_output=True, timeout=10)
    if current:
        subprocess.run(["git", "apply", "--reverse", "--check", str(ROOT / PATCH)],
                       cwd=root, check=True, capture_output=True, timeout=10)
    return {name: (root / name).read_text() for name in paths}


def program(sources, root):
    # Cut only QOM lifecycle/registration and migration metadata. Every tested
    # function, declaration and register definition remains byte-for-byte C.
    parent = cold.span(sources[PARENT], "static gboolean uart_transmit(",
                       "static void esp32_uart_reset_hold(")
    child = cold.span(sources[S3], "#define ESP32_UART_AUTOBAUD",
                      "static void esp32s3_uart_realize(")
    fifo = cold.span(sources["util/fifo8.c"], "void fifo8_reset(",
                     "const VMStateDescription vmstate_fifo8 =")
    headers = "\n".join(cold.without_includes(sources[name]).replace("#pragma once\n", "") for name in (
        "include/qemu/fifo8.h", "include/hw/char/esp32_uart.h",
        "include/hw/char/esp32s3_uart.h"))
    # Use the real tracked SCS packet emitter for six-byte ACK and eight-byte
    # ReadPos-response waveforms, including its checksum calculation.
    model = scs.StackchanScsPatchTests()._replayed_model(root)
    emitter = cold.function(model, "scs_send")
    fixture = FIXTURE.read_text()
    replacements = {"/* REAL_HEADERS */": headers, "/* REAL_FIFO */": fifo,
                    "/* REAL_PARENT */": parent, "/* REAL_S3 */": child,
                    "/* REAL_SCS_SEND */": emitter}
    for marker, code in replacements.items():
        if fixture.count(marker) != 1:
            raise AssertionError("fixture source marker changed: " + marker)
        fixture = fixture.replace(marker, code)
    return fixture


@unittest.skipUnless(shutil.which("git") and shutil.which("cc"), "git and C compiler required")
class UartRxFifoResetPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="m5-uart-rx-reset-")
        cls.addClassCleanup(cls.temporary.cleanup)
        directory = Path(cls.temporary.name)
        cls.binaries = {}
        for current in (False, True):
            root = directory / ("after" if current else "before")
            sources = replay(root, current)
            source = directory / (root.name + ".c")
            source.write_text(program(sources, root))
            binary = source.with_suffix(".bin")
            result = subprocess.run([
                shutil.which("cc"), "-std=c11", "-O1", "-Wall", "-Wextra", "-Werror",
                "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-unused-variable",
                str(source), "-o", str(binary),
            ], text=True, capture_output=True, timeout=30)
            if result.returncode:
                raise AssertionError(result.stderr)
            cls.binaries[current] = binary

    def run_case(self, current, case):
        return subprocess.run([str(self.binaries[current]), case],
                              text=True, capture_output=True, timeout=5)

    def test_idf_rx_reset_pulse_discards_stale_scs_ack(self):
        before = self.run_case(False, "flush-ack-read")
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("fifo8_num_used(&uart.parent.rx_fifo) == 0", before.stderr)
        after = self.run_case(True, "flush-ack-read")
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        self.assertIn("stale SCS ACK -> IDF RXFIFO pulse -> exact ReadPos reply PASS", after.stdout)

    def test_reset_cancels_rx_timeout_and_releases_only_rx_throttle(self):
        before = self.run_case(False, "timeout-throttle")
        self.assertNotEqual(before.returncode, 0)
        self.assertIn("fifo8_is_empty(&uart.parent.rx_fifo)", before.stderr)
        after = self.run_case(True, "timeout-throttle")
        self.assertEqual(after.returncode, 0, after.stdout + after.stderr)
        self.assertIn("RX timers/IRQ cleared; TX/config/interrupt masks retained PASS", after.stdout)

    def test_real_reply_timeout_irq_and_fifo_drain_before_and_after(self):
        for current in (False, True):
            with self.subTest(current=current):
                result = self.run_case(current, "reply-irq-drain")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("real SCS response -> parent FIFO -> RX timeout IRQ -> MMIO drain PASS", result.stdout)

    def test_unrelated_conf0_and_classic_parent_remain_unchanged(self):
        for current in (False, True):
            with self.subTest(current=current):
                result = self.run_case(current, "unrelated")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
