"""Bounded esp-emu DSI framing and per-generation framebuffer tests."""

import socket
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from device_service_errors import ServiceError
from device_service_tab5_dsi import (
    DsiFramebuffer,
    DsiProtocolError,
    MAX_MESSAGE_BYTES,
    REGISTER_VC0,
    Tab5DsiReceiver,
    _fields,
    _read_message,
    tab5_dsi_runtime,
)


def _wire(number: int, payload: bytes) -> bytes:
    return bytes(((number << 3) | 2, len(payload))) + payload


def _format(width: int = 1, height: int = 3, pixel_format: int = 1) -> dict:
    return {36: _wire(2, bytes((8, 1, 16, width, 24, height, 32, pixel_format)))}


def _rows(number: int, y: int, count: int, data: bytes) -> dict:
    return {1: number * 10, 36: _wire(3, bytes((8, number, 16, y, 24, count)) + _wire(4, data))}


class Tab5DsiTests(unittest.TestCase):
    def test_claim_names_virtual_channel_zero(self):
        registration = _fields(_fields(REGISTER_VC0)[4])
        self.assertEqual(registration[1], 1)
        self.assertEqual(registration[2], b"tab5-view")
        self.assertEqual(_fields(registration[3]), {20: b""})

    def test_first_frame_requires_every_row_and_diffs_publish_at_boundary(self):
        display = DsiFramebuffer()
        display.receive(_format())
        display.receive(_rows(1, 0, 2, b"abcd"))
        self.assertIsNone(display.snapshot)
        display.receive(_rows(1, 2, 1, b"ef"))
        self.assertEqual(display.snapshot.pixels, b"abcdef")
        display.receive(_rows(5, 0, 1, b"gh"))
        display.receive(_rows(5, 2, 1, b"ij"))
        self.assertEqual(display.snapshot.pixels, b"abcdef")
        display.receive({1: 50, 2: b""})
        self.assertEqual(display.snapshot.number, 1)
        display.receive({1: 51, 2: b""})
        self.assertEqual(display.snapshot.number, 5)
        self.assertEqual(display.snapshot.pixels, b"ghcdij")
        self.assertEqual(display.snapshot.guest_time_ns, 50)

    def test_new_frame_number_commits_previous_sparse_diff(self):
        display = DsiFramebuffer()
        display.receive(_format())
        display.receive(_rows(1, 0, 3, b"abcdef"))
        display.receive(_rows(2, 0, 1, b"gh"))
        display.receive(_rows(3, 2, 1, b"ij"))
        self.assertEqual(display.snapshot.pixels, b"ghcdef")
        self.assertEqual(display.snapshot.number, 2)

    def test_reset_and_format_change_discard_old_frame(self):
        display = DsiFramebuffer()
        display.receive(_format())
        display.receive(_rows(1, 0, 3, b"abcdef"))
        display.receive({9: b""})
        self.assertIsNone(display.snapshot)
        display.receive(_format(pixel_format=2))
        display.receive(_rows(1, 0, 3, b"abcdefghi"))
        self.assertEqual(display.snapshot.pixel_format, 2)
        display.receive({36: _wire(2, b"")})
        self.assertIsNone(display.snapshot)

    def test_loss_invalid_bounds_and_overlap_fail_instead_of_filling_pixels(self):
        for invalid in (_rows(1, 0, 1, b"x"), _rows(1, 3, 1, b"ab"), _rows(1, 0, 2, b"abcd")):
            with self.subTest(event=invalid):
                display = DsiFramebuffer()
                display.receive(_format())
                display.receive(_rows(1, 0, 1, b"ab"))
                with self.assertRaises(DsiProtocolError):
                    display.receive(invalid)
                self.assertIsNone(display.snapshot)
        display = DsiFramebuffer()
        display.receive(_format())
        display.receive(_rows(1, 0, 1, b"ab"))
        with self.assertRaises(DsiProtocolError):
            display.receive({1: 11, 2: b""})

    def test_transport_bounds_packets_topics_and_fields(self):
        for frame in (
            struct.pack("<I", MAX_MESSAGE_BYTES + 1),
            struct.pack("<IH", 2, 1),
            struct.pack("<IH", 3, 0) + b"\x80",
            struct.pack("<IH", 4, 0) + b"\x12\x03",
        ):
            with self.subTest(frame=frame):
                sender, receiver = socket.socketpair()
                with sender, receiver:
                    sender.sendall(frame)
                    with self.assertRaises(DsiProtocolError):
                        _read_message(receiver)

    def test_runtime_override_does_not_admit_an_unidentified_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            unrelated = Path(directory) / "unqualified"
            unrelated.write_bytes(b"test")
            unrelated.chmod(0o700)
            with self.assertRaises(ServiceError) as raised:
                tab5_dsi_runtime(str(unrelated))
            self.assertEqual(raised.exception.code, "tab5_dsi_runtime_unavailable")

    def test_receiver_shutdown_interrupts_incomplete_socket_message(self):
        emulator, observer = socket.socketpair()
        with emulator, observer:
            emulator.settimeout(2)
            receiver = Tab5DsiReceiver(0)
            self.addCleanup(receiver.close)
            with mock.patch.object(receiver, "_connect", return_value=observer):
                receiver.start()
                self.assertEqual(emulator.recv(4 + len(REGISTER_VC0), socket.MSG_WAITALL)[4:], REGISTER_VC0)
                ack = _wire(5, bytes((40, 1)))
                emulator.sendall(struct.pack("<IH", 2 + len(ack), 0) + ack)
                deadline = time.monotonic() + 1
                while receiver.snapshot()[1] != "connected" and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(receiver.snapshot(), (None, "connected"))
                emulator.sendall(struct.pack("<IH", 2048, 0))
                receiver.close()
                self.assertFalse(receiver._thread.is_alive())
                self.assertEqual(receiver.snapshot(), (None, "disconnected"))
