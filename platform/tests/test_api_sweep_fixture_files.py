"""Fixture ingestion preserves guest bytes while rejecting host contamination."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("api_sweep_run_guest_fixture_test", ROOT / "tests/uiflow2/api_sweep/run_guest.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ApiSweepFixtureFilesTests(unittest.TestCase):
    def test_only_guest_files_are_copied_with_original_byte_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture, copied = root / "fixture", root / "copied"
            fixture.mkdir(); copied.mkdir()
            wanted = {"config.py": "LABEL = '相机'\n".encode(), "modules/native.mpy": b"M\x06\x00\xff\x00\x80", "resources/scene.bin": bytes(range(256)), "resources/meta.json": b'{"seed":0}\n'}
            ignored = {"__pycache__/config.cpython-312.pyc": b"host cache", "__pycache__/nested/module.py": b"nested host cache", "cache.pyc": b"bytecode", "resources/cache.pyo": b"optimized bytecode", ".DS_Store": b"finder", "resources/.DS_Store": b"finder nested"}
            for name, payload in {**wanted, **ignored}.items():
                path = fixture / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(payload)
            inventory = [relative.as_posix() for _, relative in RUNNER.fixture_files(fixture)]
            self.assertEqual(inventory, sorted(wanted))
            hashes = RUNNER.copy_fixtures(fixture, copied)
            self.assertEqual(hashes, {name: hashlib.sha256(payload).hexdigest() for name, payload in wanted.items()})
            self.assertEqual({path.relative_to(copied).as_posix(): path.read_bytes() for path in copied.rglob("*") if path.is_file()}, wanted)

    def test_links_fail_closed_even_with_ignored_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"; fixture.mkdir()
            outside = root / "outside.py"; outside.write_bytes(b"outside")
            for name in ("linked.py", "cache.pyc", "__pycache__"):
                with self.subTest(name=name):
                    link = fixture / name; link.symlink_to(outside)
                    with self.assertRaisesRegex(ValueError, "symlinks"):
                        list(RUNNER.fixture_files(fixture))
                    link.unlink()
            linked_root = root / "linked-root"; linked_root.symlink_to(fixture, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                list(RUNNER.fixture_files(linked_root))

    def test_entry_points_cannot_be_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary)
            for name in ("boot.py", "main.py"):
                with self.subTest(name=name):
                    path = fixture / name; path.write_bytes(b"entry point")
                    with self.assertRaisesRegex(ValueError, "entry points"):
                        list(RUNNER.fixture_files(fixture))
                    path.unlink()


if __name__ == "__main__":
    unittest.main()
