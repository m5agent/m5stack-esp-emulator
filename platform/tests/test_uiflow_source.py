from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import uiflow_source as source

try:
    import littlefs
except (ImportError, OSError):
    littlefs = None

FLASH_SIZE = 0x40000
VFS_OFFSET = 0x20000
VFS_SIZE = 0x10000


def sha(data):
    return hashlib.sha256(data).hexdigest()


def entry(label, start, size, kind=1, subtype=0x81, flags=0):
    return struct.pack("<HBBII16sI", 0x50AA, kind, subtype, start, size,
                       label.encode().ljust(16, b"\0"), flags)


def base_image(*, partitions=None, vfs=None):
    image = bytearray(b"\xa5" * FLASH_SIZE)
    image[0x8000:0x9000] = b"\xff" * 0x1000
    if partitions is None:
        partitions = [entry("factory", 0x10000, 0x10000, 0, 0),
                      entry("vfs", VFS_OFFSET, VFS_SIZE)]
    table = b"".join(partitions)
    image[0x8000:0x8000 + len(table)] = table
    md5 = struct.pack("<H", 0xEBEB) + b"\0" * 14 + hashlib.md5(table).digest()
    image[0x8000 + len(table):0x8000 + len(table) + 32] = md5
    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs if vfs is not None else b"\xff" * VFS_SIZE
    return bytes(image)


def filesystem(buffer):
    return littlefs.LittleFS(context=littlefs.UserContext(buffer=buffer),
        block_count=len(buffer) // 4096, mount=False, filename_encoding="utf-8",
        **source.FS_CONFIG)


def real_base():
    buffer = bytearray(b"\xff" * VFS_SIZE)
    fs = filesystem(buffer)
    fs.format()
    fs.mount()
    fs.makedirs("/res", exist_ok=True)
    fs.makedirs("/script.py", exist_ok=True)
    for path, data in {
        "/main.py": b"old main\n", "/boot.py": b"old boot\n",
        "/res/font.bin": bytes(range(256)) * 4, "/lib.py": b"preserve=1\n",
    }.items():
        with fs.open(path, "wb") as handle:
            handle.write(data)
    fs.unmount()
    return base_image(vfs=buffer)


def read_file(image, path):
    fs = filesystem(bytearray(image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE]))
    fs.mount()
    try:
        with fs.open(path, "rb") as handle:
            return handle.read()
    finally:
        fs.unmount()


class SourceAssertions:
    def assert_code(self, code, function, *args, status=None, **kwargs):
        with self.assertRaises(source.UIFlowSourceError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        self.assertEqual(caught.exception.message, str(caught.exception))
        return caught.exception

    def build(self, files, base=None, **kwargs):
        return source.build_uiflow_source_image(base if base is not None else base_image(), FLASH_SIZE, files, **kwargs)

class SourceValidationTests(SourceAssertions, unittest.TestCase):
    def test_argument_types_and_required_main(self):
        for files in (None, [], {}, {"main.py": b"bytes"}, {1: "text"}, {"nested/main.py": "pass\n"}):
            with self.subTest(files=files):
                self.assert_code("invalid_uiflow_source", self.build, files)
        for base, size in ((b"", FLASH_SIZE), (bytearray(b"a"), FLASH_SIZE), (b"a", True),
                           (b"a", 0), (b"a", FLASH_SIZE + 1), (b"a", 65 * 1024 * 1024),
                           (base_image(), FLASH_SIZE // 2)):
            with self.subTest(base_type=type(base), size=size):
                self.assert_code("invalid_uiflow_base", source.build_uiflow_source_image,
                                 base, size, {"main.py": "pass\n"})

    def test_unsafe_and_noncanonical_paths(self):
        paths = ("/outside.py", "../outside.py", "pkg/../outside.py", "./outside.py",
                 "pkg//outside.py", "pkg/./outside.py", "pkg\\outside.py", "C:outside.py",
                 "pkg/", "main.py/", "outside.py\x00", "out\nout.py", "out\x7f.py",
                 "outside.txt", "", "e\u0301.py", "x" * 256 + ".py", "\ud800.py",
                 "/".join(["pkg"] * 33) + "/x.py")
        for path in paths:
            with self.subTest(path=repr(path)):
                self.assert_code("invalid_uiflow_source_path" if path != "\ud800.py" else "invalid_uiflow_source",
                                 self.build, {"main.py": "pass\n", path: "pass\n"})

    def test_case_and_generated_boot_collisions(self):
        for files in ({"main.py": "pass", "pkg/Foo.py": "1", "pkg/foo.py": "2"},
                      {"main.py": "pass", "Boot.py": "pass"},
                      {"main.py": "pass", "pkg.py": "1", "pkg.py/child.py": "2"}):
            with self.subTest(files=files):
                self.assert_code("uiflow_source_path_conflict", self.build, files, status=409)

    def test_source_nul_or_surrogate(self):
        for text in ("x=1\0", "\ud800"):
            self.assert_code("invalid_uiflow_source", self.build, {"main.py": text})

    def test_count_single_file_and_total_utf8_byte_limits(self):
        cases = [
            {"main.py": "pass", **{f"f{i}.py": "pass" for i in range(source.MAX_SOURCE_FILES)}},
            {"main.py": "中" * (source.MAX_FILE_BYTES // 3 + 1)},
            {"main.py": "x" * source.MAX_FILE_BYTES,
             **{f"f{i}.py": "x" * source.MAX_FILE_BYTES for i in range(4)}},
        ]
        for files in cases:
            self.assert_code("uiflow_source_too_large", self.build, files, status=413)

    def test_base_hash_validation(self):
        self.assert_code("uiflow_base_hash_mismatch", self.build, {"main.py": "pass"},
                         expected_base_sha256="0" * 64, status=409)
        for value in (False, "abc", "A" * 64):
            self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"}, expected_base_sha256=value)

    def test_bad_partition_table(self):
        self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"}, base=b"not an image")
        corrupt = bytearray(base_image()); corrupt[0x8000] = 0
        self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"}, base=bytes(corrupt))
        corrupt = bytearray(base_image()); corrupt[0x8050] ^= 1
        self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"}, base=bytes(corrupt))

    def test_missing_duplicate_wrong_or_encrypted_vfs(self):
        for parts in ([entry("fat", VFS_OFFSET, VFS_SIZE)],
                      [entry("vfs", VFS_OFFSET, 0x8000), entry("vfs", VFS_OFFSET + 0x8000, 0x8000)],
                      [entry("vfs", VFS_OFFSET, VFS_SIZE, subtype=0x83)],
                      [entry("vfs", VFS_OFFSET, VFS_SIZE, flags=1)]):
            self.assert_code("unsupported_uiflow_vfs", self.build, {"main.py": "pass"},
                             base=base_image(partitions=parts), status=409)

    def test_empty_overlapping_out_of_range_or_reserved_partitions(self):
        for parts in ([entry("vfs", VFS_OFFSET, 0)],
                      [entry("vfs", VFS_OFFSET, VFS_SIZE), entry("data", VFS_OFFSET + 4096, 4096)],
                      [entry("vfs", FLASH_SIZE - 4096, 8192)],
                      [entry("vfs", 0x8000, VFS_SIZE)]):
            self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"}, base=base_image(partitions=parts))

    def test_unaligned_or_truncated_existing_vfs(self):
        for parts in ([entry("vfs", VFS_OFFSET + 1, VFS_SIZE)],
                      [entry("vfs", VFS_OFFSET, VFS_SIZE - 1)],
                      [entry("vfs", VFS_OFFSET, 4096)]):
            self.assert_code("unsupported_uiflow_vfs", self.build, {"main.py": "pass"}, base=base_image(partitions=parts))
        self.assert_code("invalid_uiflow_base", self.build, {"main.py": "pass"},
                         base=base_image()[:VFS_OFFSET + VFS_SIZE - 1])

    def test_missing_littlefs_is_structured_and_not_silently_formatted(self):
        with mock.patch.dict(sys.modules, {"littlefs": None}):
            self.assert_code("uiflow_source_dependency_unavailable", self.build, {"main.py": "pass"}, status=503)


@unittest.skipUnless(littlefs is not None, "compatible littlefs-python is unavailable")
class RealLittleFSTests(SourceAssertions, unittest.TestCase):
    def test_preserve_base_binary_resources_recursive_utf8_and_generated_boot(self):
        base = real_base(); original = bytes(base)
        files = {"main.py": "raise RuntimeError('must not execute on host')\n", "pkg/__init__.py": "",
                 "pkg/传感器.py": "value = '温度'\n"}
        before = dict(files)
        image, metadata = self.build(files, base=base, expected_base_sha256=sha(base))
        self.assertEqual(base, original); self.assertEqual(files, before)
        self.assertEqual(len(image), FLASH_SIZE)
        self.assertEqual(image[:VFS_OFFSET], base[:VFS_OFFSET])
        self.assertEqual(image[VFS_OFFSET + VFS_SIZE:], base[VFS_OFFSET + VFS_SIZE:])
        self.assertEqual(read_file(image, "/res/font.bin"), bytes(range(256)) * 4)
        self.assertEqual(read_file(image, "/lib.py"), b"preserve=1\n")
        self.assertEqual(read_file(image, "/pkg/传感器.py"), files["pkg/传感器.py"].encode())
        self.assertEqual(read_file(image, "/boot.py"), source.DEFAULT_BOOT.encode())
        self.assertEqual(metadata["generated_files"], ["boot.py"])
        self.assertEqual(metadata["status"], "COMPOSED_NOT_EXECUTED")
        self.assertEqual(metadata["base_sha256"], sha(base)); self.assertEqual(metadata["firmware_sha256"], sha(image))
        self.assertEqual(metadata["source_sha256"], sha(json.dumps(files, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()))
        row = next(row for row in metadata["files"] if row["path"] == "pkg/传感器.py")
        self.assertEqual(row["sha256"], sha(files["pkg/传感器.py"].encode())); self.assertEqual(row["origin"], "caller")
        self.assertEqual(metadata["preservation"]["preserved_file_count"], 2)
        json.dumps(metadata)

    def test_explicit_boot_bytes_are_preserved(self):
        boot = "# explicit caller boot\r\n_uiflow_run_main = False\r\n"
        image, metadata = self.build({"main.py": "pass\n", "boot.py": boot}, base=real_base())
        self.assertEqual(read_file(image, "/boot.py"), boot.encode())
        self.assertEqual(metadata["generated_files"], [])
        self.assertTrue(all(row["origin"] == "caller" for row in metadata["files"]))

    def test_results_do_not_depend_on_mapping_insertion_order(self):
        base = real_base(); files = {"main.py": "pass\n", "pkg/x.py": "x=1\n", "boot.py": "pass\n"}
        first, meta1 = self.build(files, base=base)
        second, meta2 = self.build(dict(reversed(list(files.items()))), base=base)
        self.assertEqual(first, second); self.assertEqual(meta1, meta2)

    def test_short_base_only_pads_existing_trailing_flash(self):
        base = real_base()[:VFS_OFFSET + VFS_SIZE]
        image, metadata = self.build({"main.py": "pass\n"}, base=base)
        self.assertEqual(len(image), FLASH_SIZE)
        self.assertEqual(image[VFS_OFFSET + VFS_SIZE:], b"\xff" * (FLASH_SIZE - VFS_OFFSET - VFS_SIZE))
        self.assertEqual(metadata["base_size"], len(base))

    def test_unmountable_vfs_never_calls_format(self):
        with mock.patch.object(littlefs.LittleFS, "format", side_effect=AssertionError("format must not run")):
            self.assert_code("uiflow_vfs_unmountable", self.build, {"main.py": "pass"}, base=base_image(), status=409)

    def test_existing_file_parent_directory_and_case_conflicts(self):
        for path in ("lib.py/x.py", "script.py", "Main.py", "RES/x.py"):
            with self.subTest(path=path):
                self.assert_code("uiflow_source_path_conflict", self.build, {"main.py": "pass", path: "pass"}, base=real_base(), status=409)

    def test_insufficient_vfs_space_is_structured_and_base_unchanged(self):
        base = real_base(); original = sha(base)
        self.assert_code("uiflow_vfs_full", self.build, {"main.py": "x" * (128 * 1024)}, base=base, status=413)
        self.assertEqual(sha(base), original)

    def test_fresh_mount_readback_detects_source_or_preserved_file_corruption(self):
        original_factory = source._filesystem
        for target in ("/main.py", "/res/font.bin"):
            calls = 0
            def damaged_readback(module, payload):
                nonlocal calls
                calls += 1
                fs = original_factory(module, payload)
                if calls == 2:
                    mount = fs.mount
                    def mount_then_damage():
                        result = mount()
                        with fs.open(target, "wb") as handle:
                            handle.write(b"corrupted after persistence")
                        return result
                    fs.mount = mount_then_damage
                return fs
            with self.subTest(target=target), mock.patch.object(source, "_filesystem", side_effect=damaged_readback):
                self.assert_code("uiflow_source_verification_failed", self.build, {"main.py": "pass"}, base=real_base(), status=500)

    def test_unmount_failure_is_not_swallowed(self):
        original_factory = source._filesystem
        calls = 0
        def unmount_failure(module, payload):
            nonlocal calls
            calls += 1
            fs = original_factory(module, payload)
            if calls == 1:
                unmount = fs.unmount
                def fail():
                    unmount()
                    raise OSError("injected unmount failure")
                fs.unmount = fail
            return fs
        with mock.patch.object(source, "_filesystem", side_effect=unmount_failure):
            self.assert_code("uiflow_source_build_failed", self.build, {"main.py": "pass"}, base=real_base(), status=500)


if __name__ == "__main__":
    unittest.main()
