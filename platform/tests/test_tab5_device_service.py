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

    def session(self, *, source="uploaded"):
        self.sequence += 1
        return service_module.Tab5DeviceSession(
            self.service, session_id=f"test-{self.sequence}",
            spec=self.spec, firmware_id=self.image_sha,
            firmware_path=self.image, firmware_sha=self.image_sha,
            firmware_source=source, source_artifacts=[], ttl_seconds=120,
            ready_marker=None, ready_timeout=1, ready_conditions={}, runtime="tab5",
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
        self.assertEqual(session.flash_info["tab5"]["symbols_status"], "unavailable")
        session._gdb_port = 12345
        for operation, code in ((session.frame_metrics, "screenshot_requires_matching_elf"),
                                (lambda: session.inject({"kind": "touch", "x": 1, "y": 1}), "input_requires_matching_elf")):
            with self.assertRaises(service_module.ServiceError) as raised:
                operation()
            self.assertEqual(raised.exception.code, code)

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

    def launch_commands(self, session):
        commands = []
        def spawn(command, **kwargs):
            commands.append(command)
            return mock.Mock(pid=1234 + len(commands), poll=mock.Mock(return_value=None))
        with mock.patch.object(service_module.subprocess, "Popen", side_effect=spawn), \
                mock.patch.object(service_module, "wait_for_fs_path"), \
                mock.patch.object(service_module, "wait_for_tcp_port"), \
                mock.patch.object(service_module, "free_tcp_port", return_value=12345):
            session._launch_tab5()
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
