import hashlib
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import device_service_esp32sim as runtime
from device_service import DeviceService, Esp32SimDeviceSession
from device_service_errors import ServiceError
from device_service_specs import load_device_specs


class Esp32SimTests(unittest.TestCase):
    def test_catalog_selects_native_runtime_only_for_the_migrated_boards(self):
        selected = {name: spec.default_runtime for name, spec in load_device_specs().items()}
        self.assertEqual({name for name, value in selected.items() if value == "esp32sim"},
                         {"cores3", "cardputer", "cardputer-adv", "dial", "atomu", "atom-echo", "m5stick", "stickt2"})
        self.assertEqual(selected["tab5"], "qemu")
        self.assertEqual(selected["stopwatch"], "qemu")
        self.assertEqual(set(runtime.BOARDS), set(selected) - {"cardputer-zero"})
        self.assertEqual(runtime.BOARD_VARIANTS["basic-v27"]["flash-4mb"].flash, 4 << 20)
        self.assertEqual(runtime.BOARD_VARIANTS["core2"]["axp192"].name, "m5stack-core2-axp192")
        self.assertEqual(runtime.BOARDS["stopwatch"].size, (466, 466))

    def test_native_only_defaults_advertise_their_session_capabilities(self):
        service = DeviceService.__new__(DeviceService)
        service.specs = load_device_specs()
        for dev in ("m5stick", "stickt2"):
            with self.subTest(device=dev), patch.object(runtime.Installation, "ready", return_value=True):
                service._legacy_review_catalog = False
                row = service.get_device(dev)
                self.assertTrue(row["creatable"])
                self.assertIsNone(row["reason"])
                for feature in ("flash", "serial", "screenshot", "input"):
                    self.assertTrue(row["features"][feature], feature)
                caps = service.get_device_capabilities(dev)
                self.assertEqual(caps["model_status"], "supported")
                self.assertEqual(caps["runtime"]["default_mode"], "esp32sim")
                service._legacy_review_catalog = True
                row = service.get_device(dev)
                self.assertFalse(row["creatable"])
                self.assertFalse(row["features"]["flash"])
                self.assertEqual(service.get_device_capabilities(dev)["model_status"], "unsupported")

    def test_spawn_command_uses_owned_files_and_private_descriptor(self):
        installation = runtime.Installation(Path("/asset/esp32sim"), Path("/asset/rom"), Path("/asset/manifest"))
        board = runtime.BOARDS["cores3"]
        self.assertEqual(
            runtime.spawn_command(installation, board, 12, Path("/session/flash"), sd=Path("/session/sd"),
                                  cam=Path("/asset/cam"), mic=Path("/asset/mic")),
            ["/asset/esp32sim", "--board", "m5stack-cores3", "--rom", "/asset/rom",
             "--boot", "rom", "--flash-image", "/session/flash", "--console", "none", "--service-fd", "12",
             "--sd-rw", "/session/sd", "--cam-image", "/asset/cam", "--mic-wav", "/asset/mic"],
        )

    def test_nat_requires_explicit_unrestricted_trusted_host_policy(self):
        self.assertEqual(runtime.parse_network(None), {})
        for policy in (
            None,
            {"isolation": "namespace", "egress": "deny-all", "dns": "deny"},
            {"isolation": "trusted-host", "egress": "allowlist"},
        ):
            with self.subTest(policy=policy), self.assertRaises(ServiceError):
                runtime.parse_network({"ssid": "fixture", "policy": policy})
        valid = runtime.parse_network({"ssid": "fixture", "psk": "testwifi",
                                       "policy": {"isolation": "trusted-host"}})
        self.assertEqual(valid["profile"], "esp32sim-sta")

    def test_restricted_mode_cannot_fall_back_to_nat_or_claim_a_namespace(self):
        request = {"mode": "restricted", "ssid": "fixture"}
        with self.assertRaises(ServiceError):
            runtime.parse_network(request)
        with self.assertRaises(ServiceError):
            runtime.parse_network(request | {
                "policy": {"isolation": "namespace", "egress": "deny-all", "dns": "deny"},
            }, restricted_supported=True)
        network = runtime.parse_network(request, restricted_supported=True)
        installation = runtime.Installation(Path("/asset/esp32sim"), Path("/asset/rom"), Path("/asset/manifest"))
        command = runtime.spawn_command(installation, runtime.BOARDS["cores3"], 12,
                                        Path("/session/flash"), network=network)
        self.assertEqual(command[command.index("--net") + 1], "restricted")
        self.assertEqual(network["policy"]["isolation"], "emulator")

    def test_qom_snapshot_is_bounded_and_uses_one_sample(self):
        session = Esp32SimDeviceSession.__new__(Esp32SimDeviceSession)
        session._lock = threading.RLock()
        session.state = "running"
        session.spec = SimpleNamespace(id="cores3")
        session.flash_info = {"runtime_identity": {"service_features": ["state-snapshot"]}}
        session.control = Mock()
        session.control.request.return_value = {"value": {
            "/soc": {"cycle": 42}, "/board": {"name": "fixture"},
            "/soc/gpio/3": {"level": False},
        }}
        session._store_qom_snapshot = lambda snapshot: snapshot
        result = session.qom_snapshot(depth=3, max_nodes=100)
        session.control.request.assert_called_once_with("state-snapshot")
        gpio = result["nodes"]["soc"]["children"]["gpio"]["children"]["3"]["children"]
        self.assertEqual(gpio["level"], {"type": "bool", "value": False})
        self.assertEqual(session.qom_snapshot(max_nodes=1)["nodes"]["__truncated__"], True)
        with self.assertRaisesRegex(ServiceError, "No modeled esp32sim component"):
            session.qom_snapshot(path="/machine/missing")

    def test_legacy_camera_sequence_writes_the_pinned_runtime_control(self):
        session = Esp32SimDeviceSession.__new__(Esp32SimDeviceSession)
        session._lock = threading.RLock()
        session.state = "running"
        session.id = "camera-fixture"
        session.spec = SimpleNamespace(id="atoms3r-cam")
        session.flash_info = {"runtime_identity": {
            "service_features": ["state-snapshot", "camera-sequence"]
        }}
        session.control = Mock()
        session._check_cancelled = Mock()
        session._record_event = Mock()
        session._require_runtime_permission = Mock()
        payload = {"path": "/machine/m5-lcd-cam", "property": "auto-increment"}
        with self.assertRaisesRegex(ServiceError, "auto-increment must be a boolean"):
            session.qom_set(payload | {"value": "true"})
        session.qom_set(payload | {"value": True})
        session._require_runtime_permission.assert_called_once_with("input.write")
        session.control.request.assert_called_once_with(
            "state-set", ("/machine/m5-lcd-cam", "auto-increment", "true"))
        session.control.request.return_value = {
            "value": {"/soc": {}, "/board": {}, "/board/camera": {"auto-increment": True, "frames": 5}}
        }
        self.assertIs(session.qom_get(payload["path"], payload["property"])["value"], True)
        self.assertEqual(session.qom_list(payload["path"])["properties"], [
            {"name": "auto-increment", "type": "bool"},
            {"name": "frames", "type": "int"},
        ])
        session.spec = SimpleNamespace(id="cores3")
        with self.assertRaisesRegex(ServiceError, "Operation is unavailable"):
            session.qom_set(payload | {"value": True})

    def test_live_flash_snapshot_binds_digest_to_exported_bytes(self):
        session = Esp32SimDeviceSession.__new__(Esp32SimDeviceSession)
        session._lock = threading.RLock()
        session._stop_event = threading.Event()
        session.state = "running"
        session.id = "fixture"
        session.board = SimpleNamespace(flash=4)
        session.flash_info = {"runtime_identity": {"service_features": ["flash-snapshot"]}}
        session._record_event = Mock()
        session.control = Mock()
        with tempfile.TemporaryDirectory() as directory:
            session.dir = Path(directory)
            session._flash_readback = session.dir / "runtime-readback.bin"

            def export(operation):
                self.assertEqual(operation, "flash-snapshot")
                session._flash_readback.write_bytes(b"abcd")
                return {"value": {"bytes": 4, "cycle": 120}}

            session.control.request.side_effect = export
            try:
                result = session.flash_snapshot()
                stored = session.dir / f"flash-{result['snapshot_id']}.bin"
                self.assertEqual(stored.read_bytes(), b"abcd")
                self.assertEqual(result["sha256"], hashlib.sha256(b"abcd").hexdigest())
                self.assertFalse(session._flash_readback.exists())
            finally:
                session.control.request.side_effect = None
            session.control.request.return_value = {"value": {"bytes": 4, "cycle": 123}}
            with self.assertRaisesRegex(ServiceError, "export is unavailable"):
                session.flash_snapshot()
            self.assertEqual(list(session.dir.glob("flash-*.bin")), [stored])

    def test_inputs_translate_to_board_commands(self):
        cases = [
            ("cores3", {"kind": "touch", "x": 319, "y": 239, "action": "hold", "seconds": .4},
             ("touch", (319, 239, 1, 400), .3)),
            ("cores3", {"kind": "drag", "x1": 15, "y1": 20, "x2": 300, "y2": 30},
             ("drag", (15, 20, 300, 30), .3)),
            ("cores3", {"kind": "button", "control": "power"}, ("pwrkey", (120,), .3)),
            ("core2", {"kind": "button", "control": "b", "action": "hold", "seconds": .45},
             ("touch", (160, 260, 1, 450), .3)),
            ("core2", {"kind": "key", "key": "c", "action": "up"}, ("touch", (258, 260, 0, 0), .3)),
            ("cardputer-adv", {"kind": "button", "control": "G0"}, ("press", (120,), .3)),
            ("cardputer-adv", {"kind": "button", "control": "boot", "action": "up"}, ("gpio", (1,), .3)),
            ("cardputer", {"kind": "key", "key": "f12"}, ("button", ("g0", 0, 120), .3)),
            ("cardputer", {"kind": "key", "key": "f12", "action": "up"}, ("button", ("g0", 1, 0), .3)),
            ("cores3", {"kind": "battery", "mv": 3900, "percent": 70, "charging": False},
             ("battery", (3900, 70, 0), .3)),
            ("cores3", {"kind": "als", "ch0": 1500, "ch1": 300, "proximity": 250},
             ("als", (1500, 300, 250), .3)),
            ("cardputer-adv", {"kind": "imu", "accel": [1, 2, 3], "gyro": [-1, 0, 1]},
             ("imu", (1, 2, 3, -1, 0, 1), .3)),
            ("cardputer-adv", {"kind": "adc", "gpio": 10, "volts": 2.5}, ("adc", (10, 2.5), .3)),
            ("cardputer-adv", {"kind": "keyboard", "key": "fn", "action": "down"}, ("key-edge", ("fn", 1), .3)),
            ("cardputer", {"kind": "keyboard", "key": "fn", "action": "up"}, ("key-edge", ("fn", 0), .3)),
            ("dial", {"kind": "encoder", "delta": -3, "edge_period_ms": 7}, ("encoder", (-3, 7), .3)),
            ("dial", {"kind": "rfid", "uid": "AABBCCDD"}, ("rfid", ("aabbccdd",), .3)),
            ("papermono", {"kind": "nfc-tag", "uid": None}, ("paper-tag", ("none",), .3)),
            ("papercolor", {"kind": "key", "key": "a"}, ("button", ("a", 0, 120), .3)),
            ("tab5", {"kind": "touch-contact", "action": "down", "contact_id": 1, "x": 719, "y": 1279},
             ("contact", (1, 719, 1279, 1), .3)),
            ("tab5", {"kind": "battery", "mv": 7980, "ma": -410, "charging": True},
             ("battery", (7980, -410, 1), .3)),
            ("tab5", {"kind": "usb-hid", "action": "report", "report": [0, 127, 1]},
             ("usb-report", ("00", "7f", "01"), .3)),
        ]
        for key in ("fn", "del", "enter", "space"):
            cases.append(("cardputer-adv", {"kind": "keyboard", "key": key}, ("key", (key, 120), .3)))
        for board, payload, expected in cases:
            with self.subTest(board=board, payload=payload):
                self.assertEqual(runtime.input_command(board, payload), expected)
        for board, payload in (("cores3", {"kind": "encoder", "delta": 1}),
                               ("cardputer-adv", {"kind": "touch", "x": 0, "y": 0})):
            with self.assertRaises(ServiceError) as error:
                runtime.input_command(board, payload)
            self.assertEqual((error.exception.code, error.exception.status), ("not_supported_on_runtime", 409))

    def test_memory_uses_declared_psram_and_flash_layout(self):
        core = runtime.BOARDS["cores3"]
        adv = runtime.BOARDS["cardputer-adv"]
        with patch.object(runtime, "find_flash_bootloader", return_value={"flash_size": 16 << 20}),                 patch.object(runtime, "parse_partition_table", return_value={"partitions": []}):
            runtime.validate_memory(core, b"firmware", 8 << 20)
            with self.assertRaisesRegex(ServiceError, "Flash|flash"):
                runtime.validate_memory(adv, b"firmware", 0)
            with self.assertRaisesRegex(ServiceError, "PSRAM"):
                runtime.validate_memory(adv, b"firmware", 1)
        with patch.object(runtime, "find_flash_bootloader", return_value={"flash_size": 4 << 20}),                 patch.object(runtime, "parse_partition_table", return_value={
                    "partitions": [{"offset": 0x10000, "size": 4 << 20}],
                }), self.assertRaisesRegex(ServiceError, "Flash|flash"):
            runtime.validate_memory(core, b"firmware", 0)

    def test_evidence_identity_is_bound_to_pin_and_binary_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            installation = runtime.Installation(root / "esp32sim", root / runtime.ROM_NAME, root / "runtime.json")
            installation.binary.write_bytes(b"test binary")
            installation.binary.chmod(0o700)
            installation.rom.write_bytes(b"test ROM")
            pin = json.loads(runtime.LOCK.read_text())
            binary_sha = hashlib.sha256(b"test binary").hexdigest()
            rom_sha = hashlib.sha256(b"test ROM").hexdigest()
            pin["roms"][runtime.ROM_NAME] = rom_sha
            lock = root / "lock.json"
            lock.write_text(json.dumps(pin))
            installation.manifest.write_text(json.dumps({**pin, "binary_sha256": binary_sha}))
            board = runtime.BOARDS["cores3"]
            with patch.object(runtime, "LOCK", lock):
                self.assertEqual(installation.identity(board), {
                    "runtime": "esp32sim", "commit": pin["commit"], "board": "m5stack-cores3",
                    "binary_sha256": binary_sha, "rom_sha256": rom_sha,
                    "service_patch_sha256": pin["service_patch_sha256"],
                    "control_protocol": 1, "flash_bytes": 16 << 20, "psram_bytes": 8 << 20,
                    **({"service_features": pin["service_features"]} if pin.get("service_features") else {}),
                })
                installation.rom.write_bytes(b"changed ROM")
                self.assertFalse(installation.ready(board))

    def test_tab5_chooses_revision_rom_from_p4_bootloader(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flash.bin"
            header = bytearray(24)
            header[0], header[12] = 0xe9, 0x12
            for rev, expected in [(299, runtime.P4_ROM_NAME), (300, runtime.P4_REV3_ROM_NAME)]:
                header[15:17] = rev.to_bytes(2, "little")
                path.write_bytes(bytes(0x2000) + header)
                self.assertEqual(runtime.p4_rom_name(path), expected)

    def test_tab5_default_requires_same_firmware_panel_assets_and_request(self):
        service = DeviceService.__new__(DeviceService)
        service.specs = load_device_specs()
        service.tab5_dsi_board = "gt911-ili9881c"
        service.tab5_dsi_board_overrides = {}
        digest = next(sha for sha, panel in runtime.TAB5_DEFAULT_FIRMWARE.items() if panel == "st7123")
        with patch.object(runtime.Installation, "ready", return_value=True):
            self.assertEqual(service._esp32sim_board("tab5", digest).name, "m5stack-tab5")
            self.assertEqual(service._default_tab5_runtime(digest, {}), "qemu")
            service.tab5_dsi_board_overrides[digest] = "st7123"
            self.assertEqual(service._esp32sim_board("tab5", digest).name, "m5stack-tab5-st7123")
            self.assertEqual(service._default_tab5_runtime(digest, {}), "esp32sim")
            self.assertEqual(service._default_tab5_runtime(digest, {"speaker_capture": True}), "qemu")
        with patch.object(runtime.Installation, "ready", return_value=False):
            self.assertEqual(service._default_tab5_runtime(digest, {}), "qemu")

    def test_requested_frame_is_bound_to_its_reply_id(self):
        parent, peer = socket.socketpair()
        self.addCleanup(peer.close)
        consumer = runtime.Control(parent, lambda _: None, lambda *_: None)
        self.addCleanup(consumer.close)
        board = runtime.BOARDS["cardputer-adv"]
        pixels = b"\x00\xf8" * (240 * 135)
        frame = b"\x01" + struct.pack("<HH", *board.size) + pixels

        def simulator():
            with peer.makefile("rb") as request:
                size = struct.unpack(">I", request.read(4))[0]
                message = json.loads(request.read(size))
            # A different request's frame must not turn into a successful capture.
            for request_id in (message["id"] + 1, message["id"]):
                body = b"\x06" + struct.pack("<I", request_id) + frame
                peer.sendall(b"\x82\x7e" + struct.pack(">H", len(body)) + body)

        server = threading.Thread(target=simulator)
        server.start()
        data = consumer.request("frame")
        server.join(timeout=2)
        self.assertEqual(runtime.decode_frame(data, board), (240, 135, pixels))

    def test_poweroff_record_survives_control_eof(self):
        owner, guest = socket.socketpair()
        self.addCleanup(guest.close)
        consumer = runtime.Control(owner, lambda _: None, lambda *_: None)
        self.addCleanup(consumer.close)
        body = b"\x07\x01" + struct.pack("<HH", 80, 160) + b"\x00\x00" * (80 * 160)
        guest.sendall(b"\x82\x7e" + struct.pack(">H", len(body)) + body)
        guest.shutdown(socket.SHUT_WR)
        consumer.reader.join(timeout=2)
        self.assertTrue(consumer.closed)
        self.assertEqual(consumer.poweroff_frame, body[1:])
