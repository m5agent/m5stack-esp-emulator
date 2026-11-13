import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "c6_usj_runner", ROOT / "tests/firmware/esp32c6_usb_serial_jtag/run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class C6UsbRunnerTests(unittest.TestCase):
    def test_exact_payload_and_each_final_channel(self):
        uart = "ESP-ROM:esp32c6\nUSJ_RX bytes=197 result=PASS\nUSB_PROBE_DONE\n"
        payload = bytes((i * 37 + 19) & 255 for i in range(257))
        usb = b"ESP-ROM:esp32c6\nUSJ_TX_BEGIN\n" + payload + b"\nUSJ_TX_END\nUSJ_RX_ACK bytes=197 result=PASS\n"
        self.assertTrue(RUNNER.validate_serial(uart, usb, "arduino", "after")["tx_exact_257"])
        for bad_uart, bad_usb in (
            (uart + "ESP-ROM:esp32c6", usb), (uart, usb + b"ESP-ROM:esp32c6"),
            (uart, usb + b"Guru Meditation Error"), (uart, usb.replace(payload, payload[:-1])),
            (uart.replace("197", "196"), usb), (uart, usb.replace(b"USJ_RX_ACK", b"NO_ACK")),
        ):
            with self.subTest(), self.assertRaises(AssertionError):
                RUNNER.validate_serial(bad_uart, bad_usb, "arduino", "after")

    def test_repl_echo_is_not_evaluated_result(self):
        uart = "ESP-ROM:esp32c6\n"
        echo = b'ESP-ROM:esp32c6\n>>> print("USJ_REPL_RX_OK", sum(bytes(range(64))))\n'
        with self.assertRaises(AssertionError):
            RUNNER.validate_serial(uart, echo, "uiflow", "after")
        self.assertTrue(RUNNER.validate_serial(uart, echo + b"USJ_REPL_RX_OK 2016\n", "uiflow", "after")["repl_result"])


if __name__ == "__main__":
    unittest.main()
