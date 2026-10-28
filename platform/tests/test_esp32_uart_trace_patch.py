"""Keep Core2 UART transmit traces bound to virtual time."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0070-esp32-uart-tx-virtual-clock.patch"
)


class Esp32UartTracePatchTests(unittest.TestCase):
    def test_trace_is_opt_in_and_timestamped(self):
        text = PATCH.read_text()
        self.assertIn('getenv("M5SW_UART_TRACE")', text)
        self.assertIn("[uart-tx] now=%\" PRId64 \" %02x", text)
        self.assertIn("qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)", text)

    def test_patch_only_changes_the_trace_format(self):
        lines = [
            line[1:]
            for line in PATCH.read_text().splitlines()
            if line.startswith(("+", "-"))
            and not line.startswith(("+++", "---"))
        ]
        removed = [line.strip() for line in lines if line.startswith("-")]
        self.assertNotIn("fifo8_push(&s->tx_fifo, byte);", removed)
        self.assertFalse(any("tx_byte_cb" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
