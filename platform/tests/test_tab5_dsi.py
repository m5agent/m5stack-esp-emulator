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
    Tab5Gt911Touch,
    Tab5St7123Touch,
    _fields,
    _read_message,
    stage_tab5_gt911_part,
    stage_tab5_st7123_i2c_part,
    stage_tab5_st7123_touch_part,
    parse_tab5_board_overrides,
    tab5_dsi_board_devices,
    tab5_dsi_runtime,
)


def _wire(number: int, payload: bytes) -> bytes:
    return bytes(((number << 3) | 2, len(payload))) + payload


def _format(width: int = 1, height: int = 3, pixel_format: int = 1) -> dict:
    return {36: _wire(2, bytes((8, 1, 16, width, 24, height, 32, pixel_format)))}


def _rows(number: int, y: int, count: int, data: bytes) -> dict:
    return {1: number * 10, 36: _wire(3, bytes((8, number, 16, y, 24, count)) + _wire(4, data))}


class Tab5DsiTests(unittest.TestCase):
    def test_gt911_part_rejects_wrong_artifact_or_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unrelated = root / "wrong.wasm"
            unrelated.write_bytes(b"unqualified part")
            for board in ("gt911-ili9881c", ""):
                with self.subTest(board=board), self.assertRaises(ServiceError) as raised:
                    stage_tab5_gt911_part(str(unrelated), board, root)
                self.assertEqual(raised.exception.code, "tab5_gt911_part_unavailable")
            self.assertFalse((root / "tab5-cosim-board.json").exists())

    def test_gt911_tap_waits_for_idle_and_guest_acknowledgement(self):
        touch = Tab5Gt911Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (1, 0, 0, False), (12, 11, 0, False), (12, 12, 0, True),
        ]), mock.patch.object(touch, "_command", return_value="ok") as queue:
            self.assertEqual(touch.tap(640, 160, lambda: None), {"reports": 12, "acknowledged": 12})
        queue.assert_called_once_with("part gt911 input tap:640,160")

    def test_gt911_tap_rejects_busy_input_and_unacknowledged_guest(self):
        touch = Tab5Gt911Touch(1)
        for first, timeout, code in (
            ((1, 0, 0, False), 1, "tab5_gt911_busy"),
            ((0, 0, 0, True), 0.06, "tab5_gt911_ack_timeout"),
        ):
            with self.subTest(code=code), mock.patch.object(
                touch, "_state", return_value=first
            ), mock.patch.object(touch, "_command", return_value="ok") as queue:
                with self.assertRaises(ServiceError) as raised:
                    touch.tap(640, 160, lambda: None, timeout=timeout)
                self.assertEqual(raised.exception.code, code)
                self.assertEqual(queue.call_count, int(code == "tab5_gt911_ack_timeout"))

    def test_gt911_drag_schedules_one_contact_in_guest_time(self):
        touch = Tab5Gt911Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (6, 6, 0, False), (22, 22, 0, True),
        ]), mock.patch.object(touch, "_command", side_effect=["ok 100", *("ok" for _ in range(7))]) as command:
            self.assertEqual(touch.drag(120, 200, 620, 1000, lambda: None), {"reports": 22, "acknowledged": 22})
        self.assertEqual([call.args[0] for call in command.call_args_list], [
            "part clock", "part gt911 input down:120,200 at 160",
            "part gt911 input move:220,360 at 220", "part gt911 input move:320,520 at 280",
            "part gt911 input move:420,680 at 340", "part gt911 input move:520,840 at 400",
            "part gt911 input move:620,1000 at 460", "part gt911 input up at 520",
        ])

    def test_st7123_tap_recovers_after_expired_unread_reports(self):
        touch = Tab5St7123Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (2, 0, 0, True), (3, 0, 0, False), (4, 2, 0, True),
        ]), mock.patch.object(touch, "_command", return_value="ok") as queue:
            self.assertEqual(touch.tap(719, 1279, lambda: None), {"reports": 2, "acknowledged": 2})
        queue.assert_called_once_with("part software-i2c input tap:719,1279")

    def test_st7123_does_not_acknowledge_an_expired_press(self):
        touch = Tab5St7123Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (2, 1, 0, True), (2, 1, 0, True),
        ]), mock.patch.object(touch, "_command", return_value="ok"):
            with self.assertRaises(ServiceError) as raised:
                touch.tap(500, 700, lambda: None, timeout=0.075)
        self.assertEqual(raised.exception.code, "tab5_st7123_ack_timeout")

    def test_st7123_hold_reports_continuous_readbacks_and_guest_duration(self):
        touch = Tab5St7123Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (1, 1, 0, False), (2, 2, 0, True),
        ]), mock.patch.object(touch, "_command", side_effect=[
            "ok", "ok hold_ms=1200 refresh_acknowledged=68",
        ]) as command:
            before, timing = touch.hold(240, 780, 1200, lambda: None)
        self.assertEqual(before, {"reports": 2, "acknowledged": 2})
        self.assertEqual(timing, {"completion": "guest-observed", "hold_seconds": 1.2,
                                  "guest_hold_ms": 1200, "refresh_acknowledged": 68})
        self.assertEqual(command.call_args_list[0].args, ("part software-i2c input hold:240,780,1200",))

    def test_st7123_hold_rejects_an_unobserved_duration(self):
        touch = Tab5St7123Touch(1)
        for state in ("ok hold_ms=1100 refresh_acknowledged=9", "ok hold_ms=1200 refresh_acknowledged=0"):
            with self.subTest(state=state), mock.patch.object(touch, "_state", side_effect=[
                (0, 0, 0, True), (2, 2, 0, True),
            ]), mock.patch.object(touch, "_command", side_effect=["ok", state]), \
                    self.assertRaises(ServiceError) as raised:
                touch.hold(240, 780, 1200, lambda: None)
            self.assertEqual(raised.exception.code, "tab5_st7123_ack_timeout")

    def test_st7123_drag_queues_one_gesture_and_requires_all_guest_positions(self):
        touch = Tab5St7123Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (6, 6, 0, False), (7, 7, 0, True),
        ]), mock.patch.object(touch, "_command", side_effect=["ok", "ok drag_ms=360"]) as command:
            reports, timing = touch.drag(0, 1279, 719, 0, lambda: None)
        self.assertEqual(reports, {"reports": 7, "acknowledged": 7})
        self.assertEqual(timing, {"completion": "guest-observed", "guest_drag_ms": 360, "moves_acknowledged": 5})
        self.assertEqual([call.args[0] for call in command.call_args_list], [
            "part software-i2c input drag:0,1279:719,0", "part software-i2c state",
        ])

    def test_st7123_drag_does_not_acknowledge_a_missing_move(self):
        touch = Tab5St7123Touch(1)
        with mock.patch.object(touch, "_state", side_effect=[
            (0, 0, 0, True), (7, 6, 0, True), (7, 6, 0, True),
        ]), mock.patch.object(touch, "_command", return_value="ok"), self.assertRaises(ServiceError) as raised:
            touch.drag(0, 1279, 719, 0, lambda: None, timeout=0.075)
        self.assertEqual(raised.exception.code, "tab5_st7123_ack_timeout")

    def test_st7123_touch_part_rejects_unqualified_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unrelated = root / "wrong.wasm"
            unrelated.write_bytes(b"unqualified part")
            with self.assertRaises(ServiceError) as raised:
                stage_tab5_st7123_touch_part(str(unrelated), root)
            self.assertEqual(raised.exception.code, "tab5_st7123_touch_part_unavailable")
            self.assertFalse((root / "tab5-cosim-board.json").exists())

    def test_gt911_drag_still_queues_release_after_failed_move(self):
        touch = Tab5Gt911Touch(1)
        for release in ("ok", "err release failed"):
            with self.subTest(release=release), mock.patch.object(touch, "_state", return_value=(0, 0, 0, True)), \
                    mock.patch.object(touch, "_command", side_effect=["ok 100", "ok", "err move failed", release]) as command:
                with self.assertRaises(ServiceError) as raised:
                    touch.drag(120, 200, 620, 1000, lambda: None)
                self.assertEqual(raised.exception.code, "tab5_gt911_unavailable" if release == "ok" else
                                 "tab5_gt911_release_uncertain")
                self.assertEqual(command.call_args.args, ("part gt911 input up at 520",))

    def test_idle_gt911_board_attaches_only_on_selected_controller(self):
        self.assertEqual(tab5_dsi_board_devices(""), ())
        self.assertEqual(tab5_dsi_board_devices("gt911-ili9881c"), (
            "1:0x14,width=2,fill=0,reg=0x8140=0x39,reg=0x8141=0x31,reg=0x8142=0x31",
        ))
        with self.assertRaises(ServiceError) as unknown:
            tab5_dsi_board_devices("unsupported-board")
        self.assertEqual(unknown.exception.code, "tab5_dsi_board_unavailable")

    def test_st7123_identity_isolated_from_gt911(self):
        self.assertEqual(tab5_dsi_board_devices("st7123"), ("1:0x55,width=2,fill=0,reg=0x0000=0x03",))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unrelated = root / "wrong.wasm"
            unrelated.write_bytes(b"unqualified part")
            with self.assertRaises(ServiceError) as raised:
                stage_tab5_st7123_i2c_part(str(unrelated), root)
            self.assertEqual(raised.exception.code, "tab5_st7123_i2c_part_unavailable")
            self.assertFalse((root / "tab5-cosim-board.json").exists())

    def test_st7123_per_firmware_overrides_are_admitted_and_validated(self):
        a, b = "a" * 64, "b" * 64
        self.assertEqual(parse_tab5_board_overrides("", frozenset()), {})
        self.assertEqual(parse_tab5_board_overrides('{"%s":"st7123"}' % a, frozenset({a, b})),
                         {a: "st7123"})
        for value, allowlist in (
            ("[]", frozenset()), ("{", frozenset()), ('{"bad":"st7123"}', frozenset()),
            ('{"%s":"unknown"}' % a, frozenset()), ('{"%s":"st7123"}' % b, frozenset({a})),
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_tab5_board_overrides(value, allowlist)

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
