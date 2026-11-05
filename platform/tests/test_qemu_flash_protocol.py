"""Verify ROM readiness framing and passive stock-stub UART observations."""
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
import esp_flash


def slip(data):
    return b"\xc0" + data.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc") + b"\xc0"


class ProtocolTests(unittest.TestCase):
    def test_counts_real_reply_headers_and_distinct_stub_ohai(self):
        raw = b"ROM boot log\r\n" + slip(b"OHAI")
        for opcode in (5, 7, 6, 0x10, 0x11, 0x11, 0x12, 0x13):
            raw += slip(struct.pack("<BBHI", 1, opcode, 2, 0) + b"\0\0")
        observed = esp_flash.download_protocol_evidence(raw)
        self.assertTrue(observed["stub_ohai"])
        self.assertEqual(observed["reply_opcodes"]["0x11"], 2)
        self.assertEqual(observed["reply_opcodes"]["0x07"], 1)

    def test_unframed_or_malformed_bytes_cannot_be_stub_protocol_evidence(self):
        raw = b"OHAI" + slip(b"\x01\x03\xff\xff\0\0\0\0")
        raw += b"\xc0\xdb\x00OHAI\xc0"
        observed = esp_flash.download_protocol_evidence(raw)
        self.assertFalse(observed["stub_ohai"])
        self.assertEqual(observed["reply_opcodes"], {})

    def readiness(self, payload):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        def serve():
            with listener:
                connection, _ = listener.accept()
                with connection:
                    midpoint = len(payload) // 2
                    connection.sendall(payload[:midpoint])
                    connection.sendall(payload[midpoint:])
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 2)
        class LiveProcess:
            def poll(self):
                return None
        return port, LiveProcess()

    def test_waits_for_real_download_mode_and_retains_banner(self):
        payload = b"ROM\r\nrst:0x1,boot:0xf (UART_BOOT(UART0))\r\n"
        port, proc = self.readiness(payload)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            esp_flash.wait_for_qemu_download(port, proc, out, timeout=2)
            self.assertEqual((out / "rom-download.log").read_bytes(), payload)

    def test_spi_boot_or_closed_uart_is_not_download_ready(self):
        payload = b"boot:0x12 (SPI_FAST_FLASH_BOOT)\r\n"
        port, proc = self.readiness(payload)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "before readiness"):
                esp_flash.wait_for_qemu_download(port, proc, Path(directory), timeout=2)


if __name__ == "__main__":
    unittest.main()
