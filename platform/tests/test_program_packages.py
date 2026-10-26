"""Immutable package files and failure recovery; no service or guest execution."""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import errno
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from program_packages import (
    MAX_FILE_BYTES, MAX_PACKAGE_BYTES, MAX_PACKAGE_FILES, MAX_RECORD_BYTES,
    ProgramPackageError, ProgramPackageStore, SOURCE_KIND,
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def text(value):
    return {"encoding": "utf8", "data": value}


def binary(value):
    return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}


class ProgramPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "packages"
        self.store = ProgramPackageStore(self.root)

    def payload(self, source="print('温度')\n", **changes):
        result = {"files": {"main.py": text(source)}}
        result.update(changes)
        return result

    def path(self, revision_id):
        return self.root / f"{revision_id}.json"

    def assert_error(self, code, action, *args, status=None, **kwargs):
        with self.assertRaises(ProgramPackageError) as caught:
            action(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        return caught.exception

    def mutate(self, revision_id, change, *, rehash_metadata=False):
        path = self.path(revision_id)
        record = json.loads(path.read_bytes())
        change(record)
        if rehash_metadata:
            record["metadata_sha256"] = sha(canonical(record["metadata"]))
        path.write_bytes(canonical(record))

    def test_full_snapshot_identity_bytes_kinds_and_canonical_replay(self):
        files = {
            "main.py": "raise AssertionError('caller must never execute')\n".encode(),
            "pkg/__init__.py": "VALUE = '你好'\n".encode(),
            "pkg/driver.mpy": b"M\x06\x00\x1f\x01\x00\xff",
            "assets/图像.png": b"\x89PNG\r\n\x00\xff",
            "empty-resource": b"",
        }
        payload = {"source_kind": SOURCE_KIND, "entrypoint": "main.py", "files": {path: binary(data) for path, data in files.items()}}
        metadata = self.store.create(payload)
        hashes = {path: sha(data) for path, data in files.items()}
        self.assertEqual(metadata["source_sha256"], sha(canonical(hashes)))
        self.assertEqual(metadata["revision_id"], sha(canonical({"source_kind": SOURCE_KIND, "entrypoint": "main.py", "files": hashes})))
        self.assertEqual(metadata["source_kind"], SOURCE_KIND)
        self.assertEqual(metadata["total_file_bytes"], sum(map(len, files.values())))
        self.assertEqual(self.store.read_files(metadata["revision_id"]), files)
        self.assertEqual(self.store.get(metadata["revision_id"]), metadata)
        self.assertIsNotNone(datetime.fromisoformat(metadata["created_at"]).tzinfo)
        self.assertNotIn("caller must never execute", json.dumps(metadata))
        kinds = {row["path"]: row["kind"] for row in metadata["files"]}
        self.assertEqual(kinds, {path: "python" if path.endswith(".py") else "mpy" if path.endswith(".mpy") else "resource" for path in files})
        self.assertEqual([row["path"] for row in metadata["files"]], sorted(files))
        replay = self.store.source(metadata["revision_id"])
        self.assertEqual(replay, {"files": payload["files"], "entrypoint": "main.py"})
        self.assertEqual(self.store.create(replay), metadata)

    def test_text_binary_and_order_duplicates_preserve_record_and_mtime(self):
        payload = {"files": {"main.py": text("pass\n"), "data.txt": text("中文")}}
        first = self.store.create(payload)
        path = self.path(first["revision_id"])
        before, mtime = path.read_bytes(), path.stat().st_mtime_ns
        equivalent = {"entrypoint": "main.py", "source_kind": SOURCE_KIND, "files": {"data.txt": binary("中文".encode()), "main.py": binary(b"pass\n")}}
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: ProgramPackageStore(self.root, max_count=1).create(equivalent), range(32)))
        self.assertTrue(all(result == first for result in results))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, mtime)
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_existing_source_revision_identity_does_not_change(self):
        implicit = self.store.create(self.payload("pass\n"))
        explicit = self.store.create(self.payload("pass\n", entrypoint="main.py"))
        self.assertEqual(implicit, explicit)
        self.assertEqual(implicit["revision_id"], "ef0b5c61b07522b198de734f44d31ad9104047c2bcdb68929758f37b92929fd3")

    def test_snapshots_do_not_inherit_files_generate_boot_or_share_mutable_returns(self):
        payload = self.payload()
        payload["files"]["old.py"] = text("OLD = 1")
        first = self.store.create(payload)
        second = self.store.create(self.payload())
        self.assertNotEqual(first["revision_id"], second["revision_id"])
        self.assertEqual(list(self.store.read_files(second["revision_id"])), ["main.py"])
        original = self.store.get(first["revision_id"])
        payload["files"].clear()
        first["files"].clear()
        decoded = self.store.read_files(original["revision_id"])
        decoded.clear()
        self.store.source(original["revision_id"])["files"].clear()
        self.assertEqual(self.store.get(original["revision_id"]), original)
        self.assertIn("old.py", self.store.read_files(original["revision_id"]))
        self.assertNotIn("boot.py", self.store.read_files(original["revision_id"]))

    def test_missing_fields_other_kinds_and_unsupported_entrypoints_are_rejected(self):
        for payload in (None, [], {}, {"files": {}}, {"files": []}, {"files": {"helper.py": text("pass")}}):
            with self.subTest(payload=repr(payload)):
                self.assert_error("invalid_program_package", self.store.create, payload, status=400)
        for field in ("unknown", "firmware_id", "device_id", "expected_execution_id", "resources"):
            self.assert_error("invalid_program_package", self.store.create, self.payload(**{field: []}), status=400)
        for kind in (None, [], "python", "uiflow2-python"):
            self.assert_error("unsupported_program_source_kind", self.store.create, self.payload(source_kind=kind), status=409)
        for entry in (None, [], "pkg/main.py", "pkg/main.mpy", "MAIN.py", "MAIN.mpy"):
            self.assert_error("unsupported_program_entrypoint", self.store.create, self.payload(entrypoint=entry), status=409)

    def test_compiled_entrypoint_is_explicit_in_identity_and_preserves_binary_bytes(self):
        # The store owns inert bytes; guest deployment separately validates
        # the entire pure-bytecode container and the actual guest ABI.
        bytecode = b"M\x06\x00\x1f\x01\x00\xff"
        files = {"main.mpy": binary(bytecode), "helper.py": text("VALUE = 7\n")}
        payload = {"entrypoint": "main.mpy", "files": files}
        metadata = self.store.create(payload)
        hashes = {path: sha(base64.b64decode(value["data"]) if value["encoding"] == "base64" else value["data"].encode()) for path, value in files.items()}
        expected = sha(canonical({"source_kind": SOURCE_KIND, "entrypoint": "main.mpy", "files": hashes}))
        self.assertEqual(metadata["entrypoint"], "main.mpy")
        self.assertEqual(metadata["revision_id"], expected)
        self.assertEqual(self.store.read_files(expected)["main.mpy"], bytecode)
        self.assertEqual(self.store.source(expected), {
            "entrypoint": "main.mpy", "files": {"main.mpy": binary(bytecode), "helper.py": binary(b"VALUE = 7\n")}
        })
        self.assertEqual(self.store.create(self.store.source(expected)), metadata)
        self.assert_error("invalid_program_package", self.store.create, {"files": files})
        self.assert_error("invalid_program_package", self.store.create, self.payload(entrypoint="main.mpy"))

    def test_compiled_entrypoint_cannot_be_shadowed_by_source_or_a_main_path(self):
        for path in ("main.py", "MAIN.PY", "main", "MAIN/data.bin", "main/__init__.py", "main/__init__.mpy"):
            with self.subTest(path=path):
                files = {"main.mpy": binary(b"M\x06\x00\x1f"), path: text("pass")}
                self.assert_error("program_package_entrypoint_conflict", self.store.create,
                                  {"entrypoint": "main.mpy", "files": files}, status=409)

    def test_paths_cannot_escape_alias_or_represent_symlinks(self):
        paths = ("../outside", "/flash/main.py", "a//b", "a/./b", "a/../b", "a\\b", "C:drive",
                 "", "nul\x00", "line\n", "del\x7f", "next-line\x85", "e\u0301.txt", "x" * 256,
                 "/".join(["x"] * 9), "x" * 193, "中" * 64 + "a", "\ud800", 1)
        for path in paths:
            with self.subTest(path=repr(path)):
                self.assert_error("invalid_program_package_path", self.store.create, self.payload(files={"main.py": text("pass"), path: text("inert")}))
        for path in ("boot.py", "BOOT.PY", "nested/Boot.py"):
            self.assert_error("reserved_program_package_path", self.store.create, self.payload(files={"main.py": text("pass"), path: text("pass")}), status=409)
        for value in ({"type": "symlink", "target": "main.py"}, {"encoding": "symlink", "data": "main.py"}, {"encoding": "utf8", "data": "pass", "symlink": True}):
            self.assert_error("invalid_program_package_file", self.store.create, self.payload(files={"main.py": value}))

    def test_guest_path_boundaries_allow_192_utf8_bytes_and_eight_components(self):
        paths = ("x/" * 7 + "z" * 178, "中" * 64, "/".join(["d"] * 7 + ["file"]))
        self.assertEqual(len(paths[0].encode("utf-8")), 192)
        self.assertEqual(len(paths[1].encode("utf-8")), 192)
        self.assertEqual(len(paths[0].split("/")), 8)
        self.assertEqual(len(paths[2].split("/")), 8)
        files = {"main.py": text("pass"), **{path: text("inert") for path in paths}}
        result = self.store.create({"files": files})
        self.assertEqual(set(self.store.read_files(result["revision_id"])), set(files))

    def test_unicode_casefold_and_parent_file_conflicts_are_rejected(self):
        for paths in (("asset.png", "ASSET.png"), ("é.bin", "É.bin"), ("Straße", "STRASSE"), ("pkg", "PKG/item.bin"), ("a/b", "A/B/c"), ("pkg/a", "PKG/b"), ("Straße/a", "STRASSE/b")):
            with self.subTest(paths=paths):
                files = {"main.py": text("pass"), **{path: text("inert") for path in paths}}
                self.assert_error("program_package_path_conflict", self.store.create, {"files": files}, status=409)

    def test_file_descriptors_utf8_base64_and_python_content_are_strict(self):
        values = ("pass", b"pass", None, 3, {}, {"encoding": "utf8"}, {"data": "x"},
                  {"encoding": [], "data": "x"}, {"encoding": "utf8", "data": b"x"},
                  {"encoding": "utf8", "data": "\ud800"},
                  {"encoding": "base64", "data": "YQ"}, {"encoding": "base64", "data": "YQ==\n"},
                  {"encoding": "base64", "data": "YQ==="}, {"encoding": "base64", "data": "YR=="},
                  {"encoding": "base64", "data": "-_=="}, {"encoding": "base64", "data": "中文"})
        for value in values:
            with self.subTest(value=repr(value)):
                self.assert_error("invalid_program_package_file", self.store.create, self.payload(files={"main.py": value}))
        for value in (binary(b"\xff"), binary(b"print(1)\x00"), text("\x00")):
            self.assert_error("invalid_program_package_source", self.store.create, self.payload(files={"main.py": value}))
        source = "\ufeff@micropython.viper\ndef unfinished(\n"
        metadata = self.store.create(self.payload(source))
        self.assertEqual(self.store.read_files(metadata["revision_id"])["main.py"], source.encode())

    def test_mpy_only_checks_header_not_guest_version_architecture_or_execution(self):
        for data in (b"", b"M\x06\x00", b"X\x06\x00\x1f", b"M\x06\x80\x1f"):
            self.assert_error("invalid_program_package_mpy", self.store.create, self.payload(files={"main.py": text("pass"), "helper.mpy": binary(data)}))
        # This is an opaque static header, not an executable .mpy fixture and
        # not compatibility evidence. The live guest will enforce its ABI and
        # the deployment policy must reject native emitters before importing.
        for data in (b"M\x06\x00\x1f", b"M\xcb\x3f\xff"):
            result = self.store.create(self.payload(files={"main.py": text("pass"), "helper.mpy": binary(data)}))
            self.assertEqual(self.store.read_files(result["revision_id"])["helper.mpy"], data)

    def test_decoded_byte_file_and_total_limits_have_exact_boundaries(self):
        data = b"\x00\xff" * (MAX_FILE_BYTES // 2)
        accepted = self.store.create(self.payload(files={"main.py": text(""), "data": binary(data)}))
        self.assertEqual(accepted["total_file_bytes"], MAX_FILE_BYTES)
        for value in (binary(data + b"x"), text("x" * (MAX_FILE_BYTES + 1)), text("中" * (MAX_FILE_BYTES // 3 + 1))):
            self.assert_error("program_package_too_large", self.store.create, self.payload(files={"main.py": text(""), "large": value}), status=413)
        full = {"main.py": text(""), **{f"data-{index}": binary(data) for index in range(MAX_PACKAGE_BYTES // MAX_FILE_BYTES)}}
        accepted = self.store.create({"files": full})
        self.assertEqual(accepted["total_file_bytes"], MAX_PACKAGE_BYTES)
        self.assertLess(self.path(accepted["revision_id"]).stat().st_size, MAX_RECORD_BYTES)
        full["one-more"] = binary(b"x")
        self.assert_error("program_package_too_large", self.store.create, {"files": full}, status=413)

    def test_file_count_includes_zero_byte_resources(self):
        files = {"main.py": text(""), **{f"empty-{index}": binary(b"") for index in range(MAX_PACKAGE_FILES - 1)}}
        self.assertEqual(len(self.store.create({"files": files})["files"]), MAX_PACKAGE_FILES)
        files["one-more"] = binary(b"")
        self.assert_error("program_package_too_large", self.store.create, {"files": files}, status=413)

    def test_atomic_quota_across_instances_preserves_duplicates(self):
        def create(index):
            try:
                return ProgramPackageStore(self.root, max_count=5).create(self.payload(f"VALUE={index}"))
            except ProgramPackageError as error:
                self.assertEqual(error.code, "program_package_quota_exceeded")
                self.assertEqual(error.status, 429)
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            accepted = [result for result in pool.map(create, range(30)) if result is not None]
        self.assertEqual(len(accepted), 5)
        self.assertEqual(len(list(self.root.glob("*.json"))), 5)
        self.assertEqual(ProgramPackageStore(self.root, max_count=5).create(self.store.source(accepted[0]["revision_id"])), accepted[0])
        for maximum in (0, -1, 257, True, 1.0, None):
            self.assert_error("invalid_package_quota", ProgramPackageStore, self.root, max_count=maximum)

    def test_invalid_and_missing_identity_cannot_escape_the_root(self):
        for identity in ("a" * 64, "../private", "A" * 64, "x" * 64, "", None, 1):
            for read in (self.store.get, self.store.read_files, self.store.source):
                self.assert_error("unknown_program_package", read, identity, status=404)

    def test_quota_enumeration_failure_never_publishes_or_treats_storage_as_empty(self):
        result = ProgramPackageStore(self.root, max_count=1).create(self.payload())
        for failure in (PermissionError("fixture denied enumeration"), OSError(errno.EIO, "fixture enumeration failure")):
            with self.subTest(failure=type(failure).__name__):
                with mock.patch("program_packages.os.scandir", side_effect=failure):
                    self.assert_error(
                        "program_package_storage_error", self.store.create, self.payload("# different"), status=503
                    )
                self.assertEqual(list(self.root.glob("*.json")), [self.path(result["revision_id"])])

    def test_corruption_is_never_repaired_by_duplicate_creation(self):
        payload = self.payload()
        metadata = self.store.create(payload)
        revision_id = metadata["revision_id"]
        self.mutate(revision_id, lambda record: record["source"]["files"].update({"main.py": binary(b"changed")}))
        corrupt = self.path(revision_id).read_bytes()
        for read, argument in ((self.store.get, revision_id), (self.store.read_files, revision_id), (self.store.source, revision_id), (self.store.create, payload)):
            self.assert_error("program_package_corrupt", read, argument, status=500)
        self.assertEqual(self.path(revision_id).read_bytes(), corrupt)

    def test_metadata_is_derived_again_even_after_checksum_is_replaced(self):
        for field, value in (("revision_id", "0" * 64), ("source_sha256", "0" * 64), ("source_kind", "other"), ("files", []), ("total_file_bytes", 0), ("entrypoint", "helper.py"), ("created_at", "invalid")):
            with self.subTest(field=field):
                result = self.store.create(self.payload(f"# {field}"))
                self.mutate(result["revision_id"], lambda record: record["metadata"].update({field: value}), rehash_metadata=True)
                self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)

    def test_record_encoding_schema_and_duplicate_json_are_not_silently_normalized(self):
        payload = self.payload()
        result = self.store.create(payload)
        path = self.path(result["revision_id"])
        original = path.read_bytes()
        self.mutate(result["revision_id"], lambda record: record["source"]["files"].update({"main.py": text("print('温度')\n")}))
        self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)
        for invalid in (b"not-json", b"\xff", b'{"schema_version":1,"schema_version":1}', b"x" * (MAX_RECORD_BYTES + 1)):
            path.write_bytes(invalid)
            self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)
            self.assert_error("program_package_corrupt", self.store.create, payload, status=500)
            self.assertEqual(path.read_bytes(), invalid)
        path.write_bytes(original)
        self.mutate(result["revision_id"], lambda record: record.update(schema_version=True))
        self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)

    def test_disk_symlinks_and_nonregular_records_are_not_followed_or_overwritten(self):
        payload = self.payload()
        result = self.store.create(payload)
        path = self.path(result["revision_id"])
        path.unlink()
        outside = Path(self.temporary.name) / "unrelated"
        outside.write_text("unrelated fixture contents")
        path.symlink_to(outside)
        self.assert_error("program_package_corrupt", self.store.read_files, result["revision_id"], status=500)
        self.assert_error("program_package_corrupt", self.store.create, payload, status=500)
        self.assertEqual(outside.read_text(), "unrelated fixture contents")
        path.unlink()
        os.mkfifo(path)
        self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)
        path.unlink()
        link_root = Path(self.temporary.name) / "linked-packages"
        link_root.symlink_to(self.root, target_is_directory=True)
        self.assert_error("program_package_storage_error", ProgramPackageStore, link_root, status=503)
        lock = self.root / ".packages.lock"
        lock.unlink()
        lock.symlink_to(outside)
        self.assert_error("program_package_storage_error", self.store.get, result["revision_id"], status=503)

    def test_permission_and_storage_read_errors_are_not_reported_as_missing(self):
        result = self.store.create(self.payload())
        original = os.open
        path = self.path(result["revision_id"])
        def deny(candidate, *args, **kwargs):
            if Path(candidate) == path:
                raise PermissionError("fixture denied record read")
            return original(candidate, *args, **kwargs)
        with mock.patch("program_packages.os.open", side_effect=deny):
            self.assert_error("program_package_storage_error", self.store.get, result["revision_id"], status=503)

    def test_directory_records_close_the_descriptor_and_report_corruption(self):
        result = self.store.create(self.payload())
        path = self.path(result["revision_id"])
        path.unlink()
        path.mkdir()
        original, descriptors = os.open, []
        def capture(candidate, *args, **kwargs):
            descriptor = original(candidate, *args, **kwargs)
            if Path(candidate) == path:
                descriptors.append(descriptor)
            return descriptor
        with mock.patch("program_packages.os.open", side_effect=capture):
            self.assert_error("program_package_corrupt", self.store.get, result["revision_id"], status=500)
        self.assertEqual(len(descriptors), 1)
        with self.assertRaises(OSError) as caught:
            os.fstat(descriptors[0])
        self.assertEqual(caught.exception.errno, errno.EBADF)

    def test_atomic_publication_failure_leaves_no_partial_record_and_retry_works(self):
        payload = self.payload()
        with mock.patch("program_packages.os.link", side_effect=OSError("fixture publication failure")):
            self.assert_error("program_package_storage_error", self.store.create, payload, status=503)
        self.assertEqual(list(self.root.glob("*.json")), [])
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        result = self.store.create(payload)
        self.assertEqual(self.store.get(result["revision_id"]), result)
        self.assertEqual(self.path(result["revision_id"]).stat().st_mode & 0o777, 0o600)

    def test_publication_readback_detects_storage_corruption_before_success(self):
        publish = self.store._publish
        def damage(path, record):
            publish(path, record)
            path.write_bytes(b"damaged stored bytes")
        with mock.patch.object(self.store, "_publish", side_effect=damage):
            self.assert_error("program_package_corrupt", self.store.create, self.payload(), status=500)
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)
        self.assert_error("program_package_corrupt", self.store.create, self.payload(), status=500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
