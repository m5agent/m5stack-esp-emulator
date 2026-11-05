"""Synthetic LittleFS fault controls for exact stock-plus-probe membership."""
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import prepare_host_controls as prep
import run_host_control_cases as controls
import run_host_sensor_cases as sensors

try:
    import littlefs
except ImportError:
    littlefs = None


@unittest.skipIf(littlefs is None, 'littlefs-python is unavailable')
class PreservedVFSWhitelistTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.common = self.root / 'common'
        self.files = self.root / 'files'
        self.common.mkdir()
        self.files.mkdir()
        (self.common / 'rtc_probe.py').write_bytes(b'# shared\n')
        (self.files / 'boot.py').write_bytes(b'# replacement boot\n')
        (self.files / 'main.py').write_bytes(b'# new main\n')
        self.layout = {'offset': 8192, 'size': 131072}
        self.stock = {'boot.py': b'# old boot\n', 'res/stock.bin': b'\x00\xffstock',
                      'libs/vendor.py': b'# frozen vendor\n'}
        self.base = self.image('base.bin', self.stock)
        self.overlay = {'rtc_probe.py': b'# shared\n', 'boot.py': b'# replacement boot\n',
                        'main.py': b'# new main\n'}
        self.expected = {**self.stock, **self.overlay}
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(prep, 'ROOT', self.root))
        stack.enter_context(patch.object(prep, 'COMMON', self.common))
        for runner in (controls, sensors):
            stack.enter_context(patch.object(runner, 'ROOT', self.root))
        matrix = self.root / 'tests/uiflow2/device_matrix.json'
        matrix.parent.mkdir(parents=True)
        matrix.write_text(json.dumps({'devices': [{'id': 'test', 'base': 'base.bin'}]}))

    def image(self, name, members):
        fs = littlefs.LittleFS(block_size=4096, block_count=32, read_size=128,
                              prog_size=32, lookahead_size=128, block_cycles=100)
        for name_in_vfs, data in sorted(members.items()):
            for parent in reversed(Path(name_in_vfs).parents):
                if str(parent) != '.':
                    try:
                        fs.mkdir('/' + str(parent))
                    except FileExistsError:
                        pass
            with fs.open('/' + name_in_vfs, 'wb') as stream:
                stream.write(data)
        fs.unmount()
        path = self.root / name
        path.write_bytes(b'\xff' * 8192 + bytes(fs.context.buffer) + b'outside')
        return path

    def record(self, image, members):
        sha = lambda raw: hashlib.sha256(raw).hexdigest()
        return {'device_id': 'test', 'firmware_sha256': sha(image.read_bytes()),
                'base_firmware_sha256': sha(self.base.read_bytes()),
                'reference_layout': self.layout,
                'probe_sha256': {n: sha(v) for n, v in self.overlay.items() if n != 'rtc_probe.py'},
                'packaged_full_py_sha256': {n: sha(v) for n, v in members.items()}}

    def test_stock_binary_and_python_survive_and_only_explicit_overlay_changes(self):
        image = self.image('good.bin', self.expected)
        hashes, sources = prep.verify_full_python(image, self.files, self.layout, self.base)
        self.assertEqual(hashes, self.record(image, self.expected)['packaged_full_py_sha256'])
        self.assertEqual(sources['res/stock.bin']['role'], 'preserved-base-vfs')
        self.assertEqual(sources['boot.py']['role'], 'prepared-probe-source')
        for runner in (controls, sensors):
            self.assertEqual(runner.full_vfs(image, self.record(image, self.expected)), hashes)

    def test_extra_missing_changed_stock_or_changed_overlay_is_rejected(self):
        for label, name, value in [('extra', 'extra.dat', b'unexpected'),
                                   ('missing', 'libs/vendor.py', None),
                                   ('changed-stock', 'res/stock.bin', b'corrupt'),
                                   ('changed-probe', 'main.py', b'corrupt')]:
            members = dict(self.expected)
            if value is None:
                del members[name]
            else:
                members[name] = value
            with self.subTest(label=label), self.assertRaisesRegex(AssertionError, 'VFS contains'):
                prep.verify_full_python(self.image(label + '.bin', members), self.files,
                                        self.layout, self.base)

    def test_forged_matching_image_hash_and_whitelist_cannot_add_a_file(self):
        members = {**self.expected, 'extra.dat': b'unexpected'}
        image = self.image('forged.bin', members)
        for runner in (controls, sensors):
            with self.subTest(runner=runner.__name__), self.assertRaisesRegex(AssertionError, 'whitelist differs'):
                runner.full_vfs(image, self.record(image, members))


if __name__ == '__main__':
    unittest.main()
