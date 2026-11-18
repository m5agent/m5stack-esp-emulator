"""Tab5 service admission and launch contracts; no emulator executes here."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import device_service as service_module
import test_tab5_image_contract as image_fixture


class Tab5ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = service_module.DeviceService(state_dir=self.root / "state")
        self.addCleanup(self.service.close_all)
        self.base = image_fixture.p4_base(blank=True)
        self.image = self.root / "original.bin"
        self.image.write_bytes(self.base)
        self.image_sha = hashlib.sha256(self.base).hexdigest()
        self.elf = self.root / "matching.elf"
        self.elf.write_bytes(image_fixture.ELF_BYTES)
        self.seed = self.root / "reusable.efuse"
        self.seed.write_bytes(bytes(range(256)) + bytes(80))
        self.spec = replace(self.service.specs["tab5"], elf=self.elf, efuse=self.seed)
        self.service.specs["tab5"] = self.spec
        self.sequence = 0

    def session(self, *, source="uploaded", storage_config=None):
        self.sequence += 1
        return service_module.Tab5DeviceSession(
            self.service, session_id=f"test-{self.sequence}",
            spec=self.spec, firmware_id=self.image_sha,
            firmware_path=self.image, firmware_sha=self.image_sha,
            firmware_source=source, source_artifacts=[], ttl_seconds=120,
            ready_marker=None, ready_timeout=1, ready_conditions={}, runtime="qemu",
            storage_config=storage_config,
        )

    def provision(self, session):
        with mock.patch.object(session, "_launch_tab5"):
            session._provision_runtime()

    def test_full_application_and_high_flash_bytes_survive_cache_repair(self):
        prepared = self.service.prepare_flash(self.spec, self.image, self.image_sha)
        cached = prepared["path"]
        damaged = bytearray(cached.read_bytes())
        for offset in (0x520000, 0x610000, 0xAA0000, 0xF60000):
            damaged[offset] ^= 1
        cached.write_bytes(damaged)
        with mock.patch.object(self.service, "flash_preparer", side_effect=AssertionError("must use complete host image")):
            session = self.session()
            self.provision(session)
        self.assertEqual(session.virtual_flash.read_bytes(), self.base)
        self.assertEqual(cached.read_bytes(), self.base)
        identity = session.flash_info["tab5"]
        self.assertTrue(identity["application_bytes_unchanged"])
        self.assertEqual(identity["application"], image_fixture.application_identity(self.base))
        self.assertEqual(identity["execution_firmware_sha256"], self.image_sha)
        persisted = json.loads((session.dir / "session.json").read_text())
        self.assertEqual(persisted["flash"]["tab5"], identity)

    def test_source_identity_change_is_rejected_before_launch(self):
        session = self.session()
        self.image.write_bytes(self.base[:-1] + b"x")
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._provision_runtime()
        self.assertEqual(raised.exception.code, "firmware_hash_mismatch")
        spawn.assert_not_called()

    def test_changed_prepared_application_is_rejected_before_launch(self):
        session = self.session()
        broken = self.root / "broken.bin"
        data = bytearray(self.base)
        data[0x610000] ^= 1
        broken.write_bytes(data)
        with mock.patch.object(self.service, "prepare_flash", return_value={"path": broken, "info": {}}), \
                mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._provision_runtime()
        self.assertEqual(raised.exception.code, "tab5_flash_mismatch")
        spawn.assert_not_called()

    def test_reference_with_stale_elf_fails_before_companions(self):
        self.elf.write_bytes(b"unrelated old ELF")
        session = self.session(source="reference")
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._provision_runtime()
        self.assertEqual(raised.exception.code, "tab5_elf_mismatch")
        spawn.assert_not_called()

    def test_uploaded_image_without_matching_symbols_has_explicit_limits(self):
        self.elf.write_bytes(b"unrelated reference ELF")
        session = self.session()
        self.provision(session)
        self.assertFalse(session.flash_info["tab5"]["gdb_app_identity_matched"])
        self.assertEqual(session.flash_info["tab5"]["frame_capture_admission"], "native_dsi_not_configured")
        self.assertEqual(session.flash_info["tab5"]["symbols_status"], "unavailable")
        session._gdb_port = 12345
        for operation, code in ((session.frame_metrics, "screenshot_requires_matching_elf"),
                                (lambda: session.inject({"kind": "touch", "x": 1, "y": 1}), "input_requires_matching_elf")):
            with self.assertRaises(service_module.ServiceError) as raised:
                operation()
            self.assertEqual(raised.exception.code, code)
            if code == "screenshot_requires_matching_elf":
                self.assertEqual(raised.exception.extra["capture_admission"], "native_dsi_not_configured")

    def test_admitted_ota_upload_does_not_inherit_factory_symbols(self):
        data = bytearray(self.base)
        data[0x8003] = 0x10  # factory -> ota_0, preserving a valid table digest
        data[0x8050:0x8060] = hashlib.md5(data[0x8000:0x8040]).digest()
        self.base = bytes(data)
        self.image.write_bytes(self.base)
        self.image_sha = hashlib.sha256(self.base).hexdigest()
        session = self.session()
        self.provision(session)
        self.assertEqual(session.virtual_flash.read_bytes(), self.base)
        self.assertIsNone(session.flash_info["tab5"]["application"])
        self.assertEqual(session.flash_info["tab5"]["symbols_status"], "unavailable")
        self.assertNotIn("--elf", self.launch_commands(session)[1])

    def test_single_ota0_identity_is_reported_without_binding_reference_elf(self):
        self.base = image_fixture.p4_ota_base()
        self.image.write_bytes(self.base)
        self.image_sha = hashlib.sha256(self.base).hexdigest()
        session = self.session()
        self.provision(session)
        identity = session.flash_info["tab5"]
        self.assertEqual(identity["application"]["partition_subtype"], 0x10)
        self.assertEqual(identity["application"]["selection"], "ota0_erased_otadata")
        self.assertEqual(identity["application"]["elf_sha256"], hashlib.sha256(self.elf.read_bytes()).hexdigest())
        self.assertEqual(identity["symbols_status"], "unavailable")
        self.assertIsNone(identity["elf_sha256"])
        self.assertNotIn("--elf", self.launch_commands(session)[1])

    def launch_commands(self, session, launch=None):
        commands = []
        def spawn(command, **kwargs):
            commands.append(command)
            return mock.Mock(pid=1234 + len(commands), poll=mock.Mock(return_value=None))
        with mock.patch.object(service_module.subprocess, "Popen", side_effect=spawn), \
                mock.patch.object(service_module, "wait_for_fs_path"), \
                mock.patch.object(service_module, "wait_for_tcp_port"), \
                mock.patch.object(service_module, "free_tcp_port", return_value=12345):
            (launch or session._launch_tab5)()
        return commands

    def test_launch_uses_owned_seed_and_matching_elf_snapshot(self):
        seed_before = (self.seed.read_bytes(), self.seed.stat().st_mtime_ns)
        session = self.session()
        self.provision(session)
        self.elf.write_bytes(b"operator replaces global reference ELF later")
        commands = self.launch_commands(session)
        command = commands[1]
        self.assertEqual(Path(command[command.index("--efuse") + 1]), session.dir / "runtime.efuse")
        self.assertEqual(Path(command[command.index("--elf") + 1]), session.dir / "runtime.elf")
        session._tab5_efuse.write_bytes(b"changed by guest")
        self.launch_commands(session)
        self.assertEqual(session._tab5_efuse.read_bytes(), b"changed by guest")
        self.assertEqual((self.seed.read_bytes(), self.seed.stat().st_mtime_ns), seed_before)
        self.assertEqual(session._require_tab5_symbols("unexpected", "test").read_bytes(), image_fixture.ELF_BYTES)

    def test_unmatched_upload_launch_omits_stale_elf(self):
        self.elf.write_bytes(b"wrong build")
        session = self.session()
        self.provision(session)
        self.assertNotIn("--elf", self.launch_commands(session)[1])

    def test_dsi_candidate_runtime_is_explicit_and_does_not_replace_reference(self):
        self.service.tab5_dsi_emulator = "/missing/esp-emu"
        reference = self.session(source="reference")
        self.provision(reference)
        self.assertIsNone(reference._tab5_dsi_emulator)
        self.assertEqual(reference.flash_info["tab5"]["frame_capture_admission"], "matching_elf")
        self.assertIn("--elf", self.launch_commands(reference)[1])
        self.elf.write_bytes(b"wrong build")
        upload = self.session()
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                upload._provision_runtime()
        self.assertEqual(raised.exception.code, "tab5_dsi_runtime_unavailable")
        spawn.assert_not_called()

    def test_dsi_board_and_part_are_scoped_to_admitted_firmware(self):
        self.elf.write_bytes(b"wrong build")
        self.service.tab5_dsi_emulator = "/missing/esp-emu"
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_gt911_part = "/missing/gt911.wasm"
        self.service.tab5_dsi_firmware_sha256s = {"1" * 64}
        session = self.session()
        self.provision(session)
        sidecar, p4 = self.launch_commands(session)
        self.assertNotIn("--cosim-tcp", sidecar)
        self.assertNotIn("--cosim-board", p4)
        self.assertNotIn("--control-tcp", p4)
        self.assertNotIn("touch_model", session.flash_info["tab5"])
        self.assertIn("--i2c-dev", p4)
        self.assertEqual(session.flash_info["tab5"]["frame_capture_admission"], "native_dsi_firmware_not_admitted")
        session._gdb_port = 12345
        with self.assertRaises(service_module.ServiceError) as missing_frame:
            session.frame_metrics()
        self.assertEqual(missing_frame.exception.code, "screenshot_requires_matching_elf")
        self.assertEqual(missing_frame.exception.extra["capture_admission"], "native_dsi_firmware_not_admitted")
        with self.assertRaises(service_module.ServiceError) as raised:
            session.inject({"kind": "touch", "x": 640, "y": 160})
        self.assertEqual(raised.exception.code, "input_requires_matching_elf")

    def test_native_gt911_uses_panel_coordinates_and_records_controller_receipt(self):
        self.elf.write_bytes(b"wrong build")
        candidate = Path("/qualified/esp-emu")
        self.service.tab5_dsi_emulator = str(candidate)
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_gt911_part = "/qualified/gt911.wasm"
        self.service.tab5_dsi_firmware_sha256s = {self.image_sha}
        session = self.session()
        board = session.dir / "tab5-cosim-board.json"
        digest = "b" * 64
        with mock.patch.object(service_module, "tab5_dsi_runtime", return_value=candidate), \
                mock.patch.object(service_module, "stage_tab5_gt911_part", return_value=(board, digest)) as stage, \
                mock.patch.object(service_module, "Tab5DsiReceiver"), \
                mock.patch.object(service_module, "Tab5Gt911Touch") as controller:
            self.provision(session)
            sidecar, p4 = self.launch_commands(session)
            stage.assert_called_once_with(self.service.tab5_gt911_part, self.service.tab5_dsi_board, session.dir)
            self.assertNotIn("--cosim-board", sidecar)
            self.assertEqual(p4[p4.index("--cosim-board") + 1], str(board))
            self.assertIn("--control-tcp", p4)
            self.assertNotIn("--i2c-dev", p4)
            self.assertEqual(session.flash_info["tab5"]["touch_model"], "esp-emu-gt911")
            self.assertEqual(session.flash_info["tab5"]["touch_part_sha256"], digest)
            self.assertEqual(session.flash_info["tab5"]["touch_coordinate_space"], "panel-native")
            for x, y in ((720, 160), (640, 1280), (False, 160), (640.5, 160), (640, None)):
                with self.subTest(x=x, y=y), self.assertRaises(service_module.ServiceError) as raised:
                    session.inject({"kind": "touch", "x": x, "y": y})
                self.assertEqual(raised.exception.code, "invalid_input")
            with self.assertRaises(service_module.ServiceError) as raised:
                session.inject({"kind": "longpress", "x": 640, "y": 160})
            self.assertEqual(raised.exception.code, "unsupported_input")
            controller.return_value.tap.assert_not_called()
            controller.return_value.tap.return_value = {"reports": 13, "acknowledged": 13}
            receipt = session.inject({"kind": "touch", "x": 640, "y": 160})
            controller.return_value.tap.assert_called_once_with(640, 160, session._check_cancelled)
            self.assertEqual(receipt["raw"], [640, 160])
            self.assertEqual(receipt["controller_reports"], {"reports": 13, "acknowledged": 13})
            self.assertEqual(session.events[-1]["event"], "gt911_touch_acknowledged")
            with self.assertRaises(service_module.ServiceError) as raised:
                session.inject({"kind": "drag", "x1": 1, "y1": 1, "x2": 720, "y2": 10})
            self.assertEqual(raised.exception.code, "invalid_input")
            controller.return_value.drag.assert_not_called()
            controller.return_value.drag.return_value = {"reports": 22, "acknowledged": 22}
            drag = session.inject({"kind": "drag", "x1": 120, "y1": 200, "x2": 620, "y2": 1000})
            controller.return_value.drag.assert_called_once_with(120, 200, 620, 1000, session._check_cancelled)
            self.assertEqual(drag["raw"], [120, 200, 620, 1000])
            self.assertEqual(session.events[-1]["kind"], "drag")
            session._proc = session._c6_proc = None
            session._terminate_tab5()
            self.assertIsNone(session._tab5_native_touch)

    def test_st7123_launch_keeps_hardware_i2c_and_does_not_offer_gt911_input(self):
        self.elf.write_bytes(b"wrong build")
        candidate = Path("/qualified/esp-emu")
        self.service.tab5_dsi_emulator = str(candidate)
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_dsi_board_overrides = {self.image_sha: "st7123"}
        self.service.tab5_st7123_i2c_part = "/qualified/st7123-gpio.wasm"
        session = self.session()
        board = session.dir / "tab5-cosim-board.json"
        with mock.patch.object(service_module, "tab5_dsi_runtime", return_value=candidate), \
                mock.patch.object(service_module, "stage_tab5_st7123_i2c_part", return_value=board) as stage, \
                mock.patch.object(service_module, "Tab5DsiReceiver"):
            self.provision(session)
            sidecar, p4 = self.launch_commands(session)
        stage.assert_called_once_with(self.service.tab5_st7123_i2c_part, session.dir)
        self.assertNotIn("--cosim-board", sidecar)
        self.assertEqual(p4[p4.index("--cosim-board") + 1], str(board))
        self.assertNotIn("--control-tcp", p4)
        self.assertIn("1:0x55,width=2,fill=0,reg=0x0000=0x03", p4)
        self.assertEqual(session.flash_info["tab5"]["board_probe"], "esp-emu-gpio-i2c")
        self.assertIsNone(session._tab5_native_touch)
        with self.assertRaises(service_module.ServiceError) as raised:
            session.inject({"kind": "touch", "x": 120, "y": 200})
        self.assertEqual(raised.exception.code, "input_requires_matching_elf")

    def test_st7123_touch_part_is_scoped_and_reports_guest_consumption(self):
        self.elf.write_bytes(b"wrong build")
        candidate = Path("/qualified/esp-emu")
        self.service.tab5_dsi_emulator = str(candidate)
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_dsi_firmware_sha256s = {self.image_sha}
        self.service.tab5_dsi_board_overrides = {self.image_sha: "st7123"}
        self.service.tab5_st7123_touch_part = "/qualified/st7123-touch.wasm"
        session = self.session()
        board = session.dir / "tab5-cosim-board.json"
        with mock.patch.object(service_module, "tab5_dsi_runtime", return_value=candidate), \
                mock.patch.object(service_module, "stage_tab5_st7123_touch_part",
                                  return_value=(board, service_module.TAB5_ST7123_HOLD_PART_SHA256)) as stage, \
                mock.patch.object(service_module, "stage_tab5_st7123_i2c_part") as legacy, \
                mock.patch.object(service_module, "Tab5DsiReceiver"), \
                mock.patch.object(service_module, "Tab5St7123Touch") as controller:
            self.provision(session)
            sidecar, p4 = self.launch_commands(session)
            stage.assert_called_once_with(self.service.tab5_st7123_touch_part, session.dir)
            legacy.assert_not_called()
            self.assertNotIn("--control-tcp", sidecar)
            self.assertIn("--control-tcp", p4)
            self.assertEqual(p4[p4.index("--cosim-board") + 1], str(board))
            self.assertNotIn("--i2c-dev", p4)
            self.assertEqual(session.flash_info["tab5"]["touch_model"], "esp-emu-st7123")
            self.assertEqual(session.flash_info["tab5"]["touch_coordinate_space"], "panel-native")
            self.assertTrue(session.flash_info["tab5"]["touch_hold_supported"])
            self.assertFalse(session.flash_info["tab5"]["touch_drag_supported"])
            with self.assertRaises(service_module.ServiceError) as invalid:
                session.inject({"kind": "touch", "x": 720, "y": 20})
            self.assertEqual(invalid.exception.code, "invalid_input")
            with self.assertRaises(service_module.ServiceError) as drag:
                session.inject({"kind": "drag", "x1": 1, "y1": 1, "x2": 20, "y2": 10})
            self.assertEqual(drag.exception.code, "unsupported_input")
            controller.return_value.tap.assert_not_called()
            controller.return_value.tap.return_value = {"reports": 2, "acknowledged": 2}
            tap = session.inject({"kind": "touch", "x": 719, "y": 1279})
            controller.return_value.tap.assert_called_once_with(719, 1279, session._check_cancelled)
            self.assertEqual(tap["controller"], "st7123")
            self.assertEqual(tap["raw"], [719, 1279])
            self.assertEqual(tap["controller_reports"], {"reports": 2, "acknowledged": 2})
            self.assertEqual(session.events[-1]["event"], "st7123_touch_acknowledged")
            for seconds in (True, 0.2, 5.01, float("nan")):
                with self.subTest(seconds=seconds), self.assertRaises(service_module.ServiceError) as hold_error:
                    session.inject({"kind": "touch", "action": "hold", "x": 719, "y": 1279, "seconds": seconds})
                self.assertEqual(hold_error.exception.code, "invalid_input")
            controller.return_value.hold.assert_not_called()
            timing = {"completion": "guest-observed", "hold_seconds": 1.2,
                      "guest_hold_ms": 1200, "refresh_acknowledged": 68}
            controller.return_value.hold.return_value = ({"reports": 2, "acknowledged": 2}, timing)
            hold = session.inject({"kind": "touch", "action": "hold", "x": 719, "y": 1279, "seconds": 1.2})
            controller.return_value.hold.assert_called_once_with(719, 1279, 1200, session._check_cancelled)
            self.assertEqual(hold["action"], "hold")
            self.assertEqual(hold["timing"], timing)

    def test_st7123_power_state_does_not_reuse_previous_board_during_reset(self):
        session = self.session()
        session.flash_info = {"tab5": {"power_model": "esp-emu-tab5-standby-latch"}}
        session.state = "booting"
        touch = service_module.Tab5St7123Touch(1)
        session._tab5_native_touch = touch
        with mock.patch.object(touch, "power_state") as probe:
            state = session.device_state()
        self.assertTrue(state["supported"])
        self.assertFalse(state["available"])
        probe.assert_not_called()

    def test_st7123_drag_part_exposes_bounded_panel_trajectory(self):
        self.elf.write_bytes(b"wrong build")
        candidate = Path("/qualified/esp-emu")
        self.service.tab5_dsi_emulator = str(candidate)
        self.service.tab5_dsi_board_overrides = {self.image_sha: "st7123"}
        self.service.tab5_st7123_touch_part = "/qualified/st7123-drag.wasm"
        session = self.session()
        staged = (session.dir / "tab5-cosim-board.json", service_module.TAB5_ST7123_DRAG_PART_SHA256)
        with mock.patch.object(service_module, "tab5_dsi_runtime", return_value=candidate), \
                mock.patch.object(service_module, "stage_tab5_st7123_touch_part", return_value=staged), \
                mock.patch.object(service_module, "Tab5DsiReceiver"), \
                mock.patch.object(service_module, "Tab5St7123Touch") as controller:
            self.provision(session)
            self.launch_commands(session)
            self.assertTrue(session.flash_info["tab5"]["touch_hold_supported"])
            self.assertTrue(session.flash_info["tab5"]["touch_drag_supported"])
            request = {"kind": "drag", "x1": 0, "y1": 1279, "x2": 719, "y2": 0}
            for invalid in ({"x2": 720}, {"x2": 0, "y2": 1279}, {"y1": True}):
                with self.subTest(invalid=invalid), self.assertRaises(service_module.ServiceError) as failure:
                    session.inject({**request, **invalid})
                self.assertEqual(failure.exception.code, "invalid_input")
            controller.return_value.drag.assert_not_called()
            counts = {"reports": 7, "acknowledged": 7}
            timing = {"completion": "guest-observed", "guest_drag_ms": 360, "moves_acknowledged": 5}
            controller.return_value.drag.return_value = (counts, timing)
            receipt = session.inject(request)
            controller.return_value.drag.assert_called_once_with(0, 1279, 719, 0, session._check_cancelled)
            self.assertEqual(receipt["raw"], [0, 1279, 719, 0])
            self.assertEqual(receipt["controller_reports"], counts)
            self.assertEqual(receipt["timing"], timing)

    def test_dsi_session_launches_capture_receiver_only_for_its_p4(self):
        self.elf.write_bytes(b"wrong build")
        self.service.tab5_dsi_emulator = str(self.root / "qualified")
        session = self.session()
        with mock.patch.object(service_module, "tab5_dsi_runtime", return_value=Path(self.service.tab5_dsi_emulator)), \
                mock.patch.object(service_module, "Tab5DsiReceiver") as receiver:
            self.provision(session)
            sidecar, p4 = self.launch_commands(session)
            self.assertNotIn("--cosim-tcp", sidecar)
            self.assertNotIn("--elf", p4)
            self.assertIn("--cosim-tcp", p4)
            self.assertEqual(p4[0], sidecar[0])
            self.assertEqual(session.flash_info["tab5"]["frame_capture"], "esp-emu-dsi")
            self.assertEqual(session.flash_info["tab5"]["frame_capture_admission"], "native_dsi")
            receiver.return_value.start.assert_called_once()
            receiver.return_value.snapshot.return_value = (None, "connected")
            with self.assertRaises(service_module.ServiceError) as raised:
                session.frame_png()
            self.assertEqual(raised.exception.code, "tab5_dsi_frame_unavailable")
            self.assertEqual(raised.exception.extra["capture_status"], "connected")
            session._close_dsi_receiver()
            receiver.return_value.close.assert_called_once()

    def test_native_sd_is_only_attached_to_p4_and_reopened_after_reset(self):
        self.elf.write_bytes(b"unrelated reference ELF")
        backend = self.root / "qualified-esp-emu"
        self.service.tab5_dsi_emulator = str(backend)
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_dsi_firmware_sha256s = {self.image_sha}
        seed = b"S" * (512 * 1024)
        artifact = self.service.upload_artifact(seed)["artifact_id"]
        session = self.session(storage_config={"interface": "sdmmc", "sd_image_artifact_id": artifact})
        with (
            mock.patch.object(service_module, "tab5_dsi_runtime", return_value=backend),
            mock.patch.object(service_module, "Tab5DsiReceiver"),
        ):
            self.provision(session)
            self.assertEqual(session.sd_card_image.read_bytes(), seed)
            self.assertEqual(session.storage_info["sha256"], artifact)
            self.assertTrue(session.storage_info["session_isolated_copy"])
            sidecar, p4 = self.launch_commands(session)
            self.assertNotIn("--sd", sidecar)
            self.assertEqual(p4[p4.index("--sd") + 1], f"{session.sd_card_image.resolve()},slot=0")
            written = b"G" + seed[1:]
            session.sd_card_image.write_bytes(written)
            sidecar, relaunched = self.launch_commands(session)
            self.assertNotIn("--sd", sidecar)
            self.assertEqual(relaunched[relaunched.index("--sd") + 1], p4[p4.index("--sd") + 1])
            self.assertEqual(session.sd_card_image.read_bytes(), written)
        self.assertEqual(self.service.artifacts.read(artifact), seed)

    def test_tab5_sd_admission_rejects_legacy_elf_and_invalid_capacity_before_lease(self):
        backend = self.root / "qualified-esp-emu"
        self.service.tab5_dsi_emulator = str(backend)
        self.service.tab5_dsi_board = "st7123"
        self.service.tab5_dsi_firmware_sha256s = {"e" * 64}
        supported_media = self.service.upload_artifact(b"F" * (512 * 1024))["artifact_id"]
        misaligned_media = self.service.upload_artifact(b"G" * (512 * 1024 + 512))["artifact_id"]
        firmware = {"device_id": "tab5", "sha256": self.image_sha, "source": {}}
        request = {"device_id": "tab5", "firmware_id": self.image_sha}
        with (
            mock.patch.object(type(self.spec), "backend_ready", new_callable=mock.PropertyMock, return_value=True),
            mock.patch.object(self.service.firmware, "get", return_value=firmware),
            mock.patch.object(self.service.firmware, "path", return_value=self.image),
            mock.patch.object(service_module, "tab5_dsi_runtime", return_value=backend),
            mock.patch.object(service_module.Tab5DeviceSession, "start") as start,
        ):
            with self.assertRaises(service_module.ServiceError) as unlisted:
                self.service.create_session({**request, "storage": {"sd_image_artifact_id": supported_media}})
            self.assertEqual((unlisted.exception.status, unlisted.exception.code), (409, "storage_not_supported"))
            self.service.tab5_dsi_firmware_sha256s = {self.image_sha}
            with self.assertRaises(service_module.ServiceError) as legacy:
                self.service.create_session({**request, "storage": {"sd_image_artifact_id": supported_media}})
            self.assertEqual((legacy.exception.status, legacy.exception.code), (409, "storage_not_supported"))
            self.elf.write_bytes(b"unrelated reference ELF")
            with self.assertRaises(service_module.ServiceError) as misaligned:
                self.service.create_session({**request, "storage": {"sd_image_artifact_id": misaligned_media}})
            self.assertEqual((misaligned.exception.status, misaligned.exception.code), (400, "invalid_storage_image"))
            with self.assertRaises(service_module.ServiceError) as ejected:
                self.service.create_session({**request, "storage": {
                    "sd_image_artifact_id": supported_media, "sd_initially_ejected": True,
                }})
            self.assertEqual((ejected.exception.status, ejected.exception.code), (409, "sd_hotplug_not_supported"))
            self.assertEqual(self.service.worker_status()["active_lease_count"], 0)
            start.assert_not_called()

    def test_native_sd_write_stamp_requires_a_live_owned_p4_and_rotates_on_reset(self):
        self.elf.write_bytes(b"unrelated reference ELF")
        backend = self.root / "qualified-esp-emu"
        self.service.tab5_dsi_emulator = str(backend)
        self.service.tab5_dsi_board = "gt911-ili9881c"
        self.service.tab5_dsi_firmware_sha256s = {self.image_sha}
        seed = b"S" * (512 * 1024)
        artifact = self.service.upload_artifact(seed)["artifact_id"]
        session = self.session(storage_config={"interface": "sdmmc", "sd_image_artifact_id": artifact})
        with (
            mock.patch.object(service_module, "tab5_dsi_runtime", return_value=backend),
            mock.patch.object(service_module, "Tab5DsiReceiver"),
            mock.patch.object(type(self.spec), "backend_ready", new_callable=mock.PropertyMock, return_value=True),
        ):
            self.provision(session)
            self.assertEqual(
                self.service.get_device_capabilities("tab5")["fixtures"]["sd"],
                {"admission": "eligible", "interface": "sdmmc", "write_stamp": True},
            )
            with self.assertRaises(service_module.ServiceError) as missing_process:
                session.sd_write_stamp()
            self.assertEqual(missing_process.exception.code, "sd_session_not_running")
            self.launch_commands(session)
            before = session.sd_write_stamp()
            self.assertEqual(session.sd_write_stamp(), before)
            self.assertEqual(before["source_artifact_id"], artifact)
            self.assertEqual(before["firmware_sha256"], self.image_sha)
            self.assertEqual(before["session_id"], session.id)

            real_launch = session._launch_tab5
            # Keep the same mocked PID so the generation check can also catch PID reuse.
            with mock.patch.object(session, "_launch_tab5", side_effect=lambda: self.launch_commands(session, real_launch)):
                session.reset()
            after = session.sd_write_stamp()
            self.assertEqual(after["modified_ns"], before["modified_ns"])
            self.assertNotEqual(after["media_id"], before["media_id"])
            session._proc.poll.return_value = 1
            with self.assertRaises(service_module.ServiceError) as exited:
                session.sd_write_stamp()
            self.assertEqual(exited.exception.code, "sd_session_not_running")

    def test_tab5_public_qemu_selection_rejects_shared_frame_cache(self):
        session = self.session()
        self.assertEqual(session.runtime, "qemu")
        with self.assertRaises(service_module.ServiceError) as raised:
            session.preview_frame(1000)
        self.assertEqual((raised.exception.status, raised.exception.code), (409, "frame_preview_not_available"))

    def test_dsi_reuses_only_the_current_immutable_observation(self):
        session = self.session()
        session.state = "running"
        receiver = mock.Mock()
        session._tab5_dsi = receiver
        first = service_module.DsiFrame(1, 1, service_module.RGB565_LE, b"\xff\xff", 1, 2, 3)
        receiver.snapshot.return_value = (first, "connected")
        with mock.patch.object(service_module, "write_rgb_png", wraps=service_module.write_rgb_png) as encode, \
                mock.patch.object(service_module, "rgb_metrics", wraps=service_module.rgb_metrics) as analyze:
            original = session._dsi_frame_metrics(analyze=False, force_persist=True)
            observed = session._dsi_frame_metrics(analyze=True, force_persist=True)
            self.assertNotIn("nonblack_pixels", original)
            self.assertEqual(observed["nonblack_pixels"], 1)
            self.assertEqual(observed["png"], original["png"])
            observed["width"] = 99
            self.assertEqual(session._dsi_frame_metrics(analyze=True, force_persist=False)["width"], 1)
            self.assertNotIn("nonblack_pixels", session._dsi_frame_metrics(analyze=False, force_persist=False))
            encode.assert_called_once()
            analyze.assert_called_once()
            session._close_dsi_receiver()
            replacement = mock.Mock()
            session._tab5_dsi = replacement
            # In a new timeline the frame sequence and timestamp can repeat.
            replacement.snapshot.return_value = (replace(first, pixels=b"\0\0"), "connected")
            current = session._dsi_frame_metrics(analyze=True, force_persist=True)
            self.assertEqual(current["nonblack_pixels"], 0)
            self.assertNotEqual(current["png"], original["png"])
            self.assertEqual(encode.call_count, 2)

    def test_modified_session_elf_is_rejected_before_any_launch(self):
        session = self.session()
        self.provision(session)
        session._tab5_elf.write_bytes(b"changed session ELF")
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._launch_tab5()
        self.assertEqual(raised.exception.code, "tab5_elf_mismatch")
        spawn.assert_not_called()

    def test_missing_session_elf_is_a_bounded_identity_error(self):
        session = self.session()
        self.provision(session)
        session._tab5_elf.unlink()
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._launch_tab5()
        self.assertEqual(raised.exception.code, "tab5_elf_mismatch")
        spawn.assert_not_called()

    def test_changed_application_cannot_reuse_symbols_after_reset(self):
        session = self.session()
        self.provision(session)
        data = bytearray(session.virtual_flash.read_bytes())
        data[0x610000] ^= 1
        session.virtual_flash.write_bytes(data)
        with mock.patch.object(service_module.subprocess, "Popen") as spawn:
            with self.assertRaises(service_module.ServiceError) as raised:
                session._launch_tab5()
        self.assertEqual(raised.exception.code, "tab5_elf_mismatch")
        spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
