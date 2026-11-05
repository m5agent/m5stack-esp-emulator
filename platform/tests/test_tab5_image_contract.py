"""Tab5 must preserve application bytes and reject stale GDB/flash assumptions."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/uiflow2"))
import run_tab5_ui_test as runner
from tab5_ui_test.make_image import FLASH_SIZE, application_identity, compose_image
from uiflow_source import UIFlowSourceError

SPEC = importlib.util.spec_from_file_location(
    "tab5_source_fixture", ROOT / "platform/tests/test_uiflow_source.py")
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)
VFS = 0xAA0000
VFS_SIZE = 0x10000
ELF_BYTES = b"synthetic identity fixture, never executed"


def p4_base(*, blank=False):
    data = bytearray(b"\xff" * FLASH_SIZE)
    parts = (fixture.entry("factory", 0x10000, 0x990000, 0, 0)
             + fixture.entry("vfs", VFS, VFS_SIZE))
    table = parts + struct.pack("<H", 0xEBEB) + b"\0" * 14 + hashlib.md5(parts).digest()
    data[0x8000:0x8000 + len(table)] = table
    header = bytearray(24)
    header[0:4] = bytes((0xE9, 1, 2, 0x40))
    struct.pack_into("<H", header, 12, 0x12)
    data[0x10000:0x10018] = header
    struct.pack_into("<II", data, 0x10018, 0x48000020, 0x620000)
    descriptor = bytearray(256)
    struct.pack_into("<I", descriptor, 0, 0xABCD5432)
    descriptor[144:176] = hashlib.sha256(ELF_BYTES).digest()
    data[0x10020:0x10120] = descriptor
    data[0x610000:0x610040] = b"application bytes at the obsolete VFS offset".ljust(64, b"!")
    if not blank:
        old = fixture.real_base()
        data[VFS:VFS + VFS_SIZE] = old[fixture.VFS_OFFSET:fixture.VFS_OFFSET + VFS_SIZE]
    return bytes(data)


@unittest.skipIf(fixture.littlefs is None, "littlefs-python is required")
class CompositionTests(unittest.TestCase):
    def test_actual_partition_preserves_app_and_existing_files(self):
        base = p4_base()
        image, meta = compose_image(base, {"main.py": "print('probe')\n"},
                                   vfs_offset=0x610000, vfs_size=0x1E0000)
        self.assertEqual(application_identity(image), application_identity(base))
        self.assertEqual(image[:VFS], base[:VFS])
        self.assertEqual(image[VFS + VFS_SIZE:], base[VFS + VFS_SIZE:])
        fs = fixture.filesystem(bytearray(image[VFS:VFS + VFS_SIZE]))
        fs.mount()
        try:
            with fs.open('/res/font.bin', 'rb') as handle:
                self.assertEqual(handle.read(), bytes(range(256)) * 4)
        finally:
            fs.unmount()
        self.assertTrue(meta['layout_drift'])
        self.assertTrue(meta['application_bytes_unchanged'])
        self.assertFalse(meta['empty_vfs_initialized'])

    def test_strict_drift_does_not_reinterpret_old_offset(self):
        with self.assertRaisesRegex(ValueError, 'VFS layout drift'):
            compose_image(p4_base(), {'main.py': 'pass\n'},
                          vfs_offset=0x610000, layout_policy='strict')

    def test_erased_legacy_vfs_can_be_initialized_without_changing_app(self):
        base = p4_base(blank=True)
        image, meta = compose_image(base, {'main.py': 'pass\n'})
        self.assertTrue(meta['empty_vfs_initialized'])
        self.assertEqual(meta['input_base_sha256'], hashlib.sha256(base).hexdigest())
        self.assertEqual(application_identity(image), application_identity(base))

    def test_populated_unmountable_vfs_is_never_formatted(self):
        base = bytearray(p4_base(blank=True))
        base[VFS] = 0
        with self.assertRaises(UIFlowSourceError) as raised:
            compose_image(bytes(base), {'main.py': 'pass\n'})
        self.assertEqual(raised.exception.code, 'uiflow_vfs_unmountable')


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.elf = Path(self.temp.name) / 'app.elf'
        self.elf.write_bytes(ELF_BYTES)
        self.base = p4_base(blank=True)

    def test_matching_app_descriptor_binds_exact_elf(self):
        result = runner.admit_image(self.base, self.base, self.elf, probe_only=False)
        self.assertTrue(result['gdb_app_identity_matched'])

    def test_stale_elf_is_rejected_for_both_modes(self):
        self.elf.write_bytes(b'wrong older ELF')
        for probe in (True, False):
            with self.subTest(probe=probe), self.assertRaisesRegex(ValueError, 'ELF does not match'):
                runner.admit_image(self.base, self.base, self.elf, probe_only=probe)

    def test_no_elf_is_only_allowed_for_serial_probe(self):
        self.assertFalse(runner.admit_image(self.base, self.base, None,
                                           probe_only=True)['gdb_app_identity_matched'])
        with self.assertRaisesRegex(ValueError, 'matching emulator ELF'):
            runner.admit_image(self.base, self.base, None, probe_only=False)

    def test_prebuilt_old_vfs_overwrite_is_rejected_as_app_change(self):
        damaged = bytearray(self.base)
        damaged[0x610000] ^= 1
        with self.assertRaisesRegex(ValueError, 'changed the declared base application'):
            runner.admit_image(self.base, bytes(damaged), self.elf, probe_only=False)

    def test_download_ranges_do_not_omit_populated_system_sector(self):
        image = bytearray(b'\xff' * FLASH_SIZE)
        image[0x520000] = 1
        image[0x610000] = 2
        self.assertEqual(runner.download_ranges(bytes(image)),
                         [(0x520000, 0x521000), (0x610000, 0x611000)])

    def test_download_lane_rejects_populated_high_vfs_before_launch(self):
        image = bytearray(b'\xff' * FLASH_SIZE)
        image[VFS] = 1
        with self.assertRaisesRegex(ValueError, 'below 8 MiB'):
            runner.download_ranges(bytes(image))
