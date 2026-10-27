"""Real-file immutable revision tests; no firmware build, service or guest."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
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

from program_revisions import MAX_CONFIGURED_REVISIONS, MAX_REVISION_BYTES, MAX_REVISIONS, ProgramRevisionStore, RevisionError


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value):
    return hashlib.sha256(value).hexdigest()


class ProgramRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "revisions"
        self.store = ProgramRevisionStore(self.root)

    def payload(self, source="print('你好')\n", **changes):
        result = {"files": {"main.py": source}}
        result.update(changes)
        return result

    def path(self, revision_id):
        return self.root / f"{revision_id}.json"

    def assert_error(self, code, callable, *args, status=None, **kwargs):
        with self.assertRaises(RevisionError) as caught:
            callable(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        if status is not None:
            self.assertEqual(caught.exception.status, status)
        return caught.exception

    def mutate_record(self, revision_id, mutate, *, refresh_metadata_hash=False):
        path = self.path(revision_id)
        record = json.loads(path.read_text(encoding="utf-8"))
        mutate(record)
        if refresh_metadata_hash:
            record["metadata_sha256"] = sha(canonical(record["metadata"]))
        path.write_bytes(canonical(record))

    def test_identity_is_full_canonical_snapshot_and_metadata_does_not_expose_source(self):
        files = {"pkg/helper.py": "VALUE = 3\n", "main.py": "raise AssertionError('never execute caller code')\n"}
        result = self.store.create({"files": files})
        expected = {"source_kind": "uiflow2-python", "entrypoint": "main.py", "files": files}
        self.assertEqual(result["revision_id"], sha(canonical(expected)))
        self.assertEqual(result["source_sha256"], sha(canonical(files)))
        self.assertNotEqual(result["revision_id"], result["source_sha256"])
        self.assertEqual(result["total_source_bytes"], sum(len(value.encode()) for value in files.values()))
        self.assertEqual(result["files"], [
            {"path": path, "size": len(source.encode()), "sha256": sha(source.encode())}
            for path, source in sorted(files.items())
        ])
        self.assertIsNotNone(datetime.fromisoformat(result["created_at"]).tzinfo)
        self.assertEqual(self.store.get(result["revision_id"]), result)
        self.assertNotIn("never execute caller code", json.dumps(result))
        self.assertEqual(self.store.source(result["revision_id"]), {"files": files, "entrypoint": "main.py"})

    def test_defaults_order_and_concurrent_duplicates_preserve_original_record(self):
        payload = {"files": {"main.py": "pass", "pkg/z.py": "z = 1"}}
        equivalent = {"source_kind": "uiflow2-python", "entrypoint": "main.py", "files": dict(reversed(list(payload["files"].items())))}
        first = self.store.create(payload)
        before = self.path(first["revision_id"]).read_bytes()

        def create(index):
            return ProgramRevisionStore(self.root, max_count=1).create(payload if index % 2 else equivalent)

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(create, range(36)))
        self.assertTrue(all(result == first for result in results))
        self.assertEqual(self.path(first["revision_id"]).read_bytes(), before)
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_complete_snapshots_do_not_inherit_files_and_do_not_generate_boot(self):
        first = self.store.create({"files": {"main.py": "pass", "old.py": "OLD = 1"}})
        second = self.store.create(self.payload("pass"))
        self.assertNotEqual(first["revision_id"], second["revision_id"])
        self.assertEqual(self.store.source(second["revision_id"])["files"], {"main.py": "pass"})
        self.assertNotIn("boot.py", self.store.source(first["revision_id"])["files"])
        self.assertIn("old.py", self.store.source(first["revision_id"])["files"])
        explicit = self.store.create({"files": {"main.py": "pass", "boot.py": "_uiflow_run_main = True\n"}})
        self.assertNotEqual(second["revision_id"], explicit["revision_id"])

    def test_caller_and_return_value_mutation_cannot_change_persisted_revision(self):
        payload = self.payload()
        result = self.store.create(payload)
        revision_id = result["revision_id"]
        original = self.store.get(revision_id)
        payload["files"]["main.py"] = "changed"
        result["files"].clear()
        result["created_at"] = "changed"
        source = self.store.source(revision_id)
        source["files"]["main.py"] = "changed again"
        self.assertEqual(self.store.get(revision_id), original)
        self.assertEqual(self.store.source(revision_id)["files"]["main.py"], "print('你好')\n")

    def test_utf8_bom_and_micropython_text_are_preserved_without_compilation(self):
        source = "\ufeff# 温度\n@micropython.viper\ndef unfinished(\n"
        result = self.store.create(self.payload(source))
        self.assertEqual(self.store.source(result["revision_id"])["files"]["main.py"], source)
        self.assertEqual(result["source_sha256"], sha(canonical({"main.py": source})))

    def test_rejects_unknown_fields_assets_and_other_source_kinds(self):
        for field in ("assets", "asset_manifest", "base_sha256", "firmware_id", "device_id", "unknown"):
            with self.subTest(field=field):
                self.assert_error("invalid_program_revision", self.store.create, self.payload(**{field: []}), status=400)
        for kind in ("mpy", "binary", "python", None, []):
            with self.subTest(kind=kind):
                self.assert_error("unsupported_program_source_kind", self.store.create, self.payload(source_kind=kind), status=409)
        self.assert_error("invalid_program_revision", self.store.create, None, status=400)

    def test_entrypoint_is_explicitly_limited_to_root_main(self):
        for entrypoint in ("other.py", "pkg/main.py", "MAIN.py", "../main.py", None):
            with self.subTest(entrypoint=entrypoint):
                self.assert_error("unsupported_program_entrypoint", self.store.create, self.payload(entrypoint=entrypoint), status=409)
        self.assert_error("invalid_uiflow_source", self.store.create, {"files": {"other.py": "pass"}}, status=400)

    def test_rejects_unsafe_noncanonical_and_non_python_paths(self):
        for path in ("../evil.py", "/main.py", "a//b.py", "a/./b.py", "a/../b.py", "a\\b.py", "C:main.py", "bad\x00.py", "bad\x7f.py", "image.png", "module.mpy", "UPPER.PY", "e\u0301.py", "/".join(["x"] * 33) + ".py", "x" * 256 + ".py"):
            with self.subTest(path=path):
                self.assert_error("invalid_uiflow_source_path", self.store.create, {"files": {"main.py": "pass", path: "pass"}}, status=400)

    def test_rejects_case_aliases_generated_boot_alias_and_parent_collisions(self):
        for files in (
            {"main.py": "pass", "MAIN.py": "other"},
            {"main.py": "pass", "Boot.py": "pass"},
            {"main.py": "pass", "pkg.py": "pass", "PKG.py/x.py": "pass"},
        ):
            with self.subTest(files=list(files)):
                self.assert_error("uiflow_source_path_conflict", self.store.create, {"files": files}, status=409)

    def test_rejects_invalid_values_nul_and_non_utf8(self):
        for files in (None, [], {}, {"main.py": b"pass"}, {"main.py": 3}, {1: "pass"}, {"main.py": "\x00"}, {"main.py": "\ud800"}, {"main.py": "pass", "\ud800.py": "pass"}):
            with self.subTest(files=repr(files)):
                self.assert_error("invalid_uiflow_source", self.store.create, {"files": files}, status=400)

    def test_file_count_and_utf8_byte_limits(self):
        self.assert_error("uiflow_source_too_large", self.store.create, self.payload("界" * (262144 // 3 + 1)), status=413)
        files = {"main.py": "pass", **{f"m{i}.py": "pass" for i in range(128)}}
        self.assert_error("uiflow_source_too_large", self.store.create, {"files": files}, status=413)
        files = {"main.py": "x" * 262144, **{f"m{i}.py": "x" * 262144 for i in range(4)}}
        self.assert_error("uiflow_source_too_large", self.store.create, {"files": files}, status=413)

    def test_canonical_json_limit_counts_escaping_and_envelope_fields(self):
        files = {"main.py": '"' * 200000, "a.py": '"' * 200000, "b.py": '"' * 200000}
        self.assert_error("program_revision_too_large", self.store.create, {"files": files}, status=413)
        files = {"main.py": "", "a.py": "x" * 262144, "b.py": "x" * 262144, "c.py": "x" * 262144}
        full = {"source_kind": "uiflow2-python", "entrypoint": "main.py", "files": files}
        remaining = MAX_REVISION_BYTES - len(canonical(full))
        self.assertLessEqual(remaining, 262144)
        files["main.py"] = "x" * remaining
        self.assertEqual(len(canonical(full)), MAX_REVISION_BYTES)
        result = self.store.create({"files": files})
        self.assertEqual(self.store.source(result["revision_id"])["files"], files)
        files["main.py"] += "x"
        self.assert_error("program_revision_too_large", self.store.create, {"files": files}, status=413)

    def test_quota_is_atomic_across_concurrent_store_instances_and_duplicates_still_work(self):
        def create(index):
            try:
                return ProgramRevisionStore(self.root, max_count=5).create(self.payload(f"VALUE = {index}"))
            except RevisionError as error:
                self.assertEqual(error.code, "program_revision_quota_exceeded")
                self.assertEqual(error.status, 429)
                return None

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(create, range(30)))
        accepted = [result for result in results if result is not None]
        self.assertEqual(len(accepted), 5)
        self.assertEqual(len(list(self.root.glob("*.json"))), 5)
        first = accepted[0]
        source = self.store.source(first["revision_id"])
        self.assertEqual(ProgramRevisionStore(self.root, max_count=5).create(source), first)

    def test_configured_quota_above_default_preserves_existing_records_on_reopen(self):
        self.assertEqual(self.store.max_count, 256)
        originals = {}
        for index in range(MAX_REVISIONS):
            payload = self.payload(f"VALUE = {index}\n# 原始版本\n")
            result = self.store.create(payload)
            originals[result["revision_id"]] = (result, payload["files"], self.path(result["revision_id"]).read_bytes())
        fresh = self.payload("VALUE = 256\n")
        self.assert_error("program_revision_quota_exceeded", self.store.create, fresh, status=429)
        expanded = ProgramRevisionStore(self.root, max_count=257)
        added = expanded.create(fresh)
        self.assertEqual(expanded.get(added["revision_id"]), added)
        self.assert_error("program_revision_quota_exceeded", expanded.create, self.payload("VALUE = 257\n"), status=429)
        reopened = ProgramRevisionStore(self.root)
        for revision_id, (metadata, files, raw) in originals.items():
            self.assertEqual(reopened.get(revision_id), metadata)
            self.assertEqual(reopened.source(revision_id), {"entrypoint": "main.py", "files": files})
            self.assertEqual(reopened.create({"files": files}), metadata)
            self.assertEqual(self.path(revision_id).read_bytes(), raw)
        self.assertEqual(reopened.get(added["revision_id"]), added)
        self.assertEqual(len(list(self.root.glob("*.json"))), 257)
        self.assert_error("program_revision_quota_exceeded", reopened.create, self.payload("VALUE = 258\n"), status=429)

    def test_quota_is_bounded_to_4096_and_rejects_non_integer_values(self):
        self.assertEqual(MAX_CONFIGURED_REVISIONS, 4096)
        self.assertEqual(ProgramRevisionStore(self.root, max_count=4096).max_count, 4096)
        self.assertEqual(ProgramRevisionStore(self.root, max_count=1).max_count, 1)
        for count in (0, -1, 4097, 1.0, True, False, "257", None):
            with self.subTest(count=count):
                self.assert_error("invalid_revision_quota", ProgramRevisionStore, self.root, max_count=count, status=400)

    def test_missing_or_invalid_ids_never_escape_root(self):
        for revision_id in ("a" * 64, "../secrets", "A" * 64, "x" * 64, "", None, 1):
            with self.subTest(revision_id=revision_id):
                self.assert_error("unknown_program_revision", self.store.get, revision_id, status=404)
                self.assert_error("unknown_program_revision", self.store.source, revision_id, status=404)

    def test_source_corruption_is_rejected_and_duplicate_create_does_not_overwrite(self):
        payload = self.payload()
        result = self.store.create(payload)
        revision_id = result["revision_id"]
        self.mutate_record(revision_id, lambda record: record["source"]["files"].update({"main.py": "changed"}))
        corrupt = self.path(revision_id).read_bytes()
        for action, argument in ((self.store.get, revision_id), (self.store.source, revision_id), (self.store.create, payload)):
            self.assert_error("program_revision_corrupt", action, argument, status=500)
        self.assertEqual(self.path(revision_id).read_bytes(), corrupt)

    def test_metadata_is_recomputed_even_if_its_checksum_is_updated(self):
        for field, value in (("source_sha256", "0" * 64), ("revision_id", "0" * 64), ("files", []), ("total_source_bytes", 0), ("entrypoint", "other.py")):
            with self.subTest(field=field):
                result = self.store.create(self.payload(field))
                self.mutate_record(result["revision_id"], lambda record: record["metadata"].update({field: value}), refresh_metadata_hash=True)
                self.assert_error("program_revision_corrupt", self.store.get, result["revision_id"], status=500)

    def test_timestamp_and_missing_source_identity_fields_are_not_silently_repaired(self):
        result = self.store.create(self.payload())
        self.mutate_record(result["revision_id"], lambda record: record["metadata"].update(created_at="changed"))
        self.assert_error("program_revision_corrupt", self.store.get, result["revision_id"], status=500)
        result = self.store.create(self.payload("second"))
        self.mutate_record(result["revision_id"], lambda record: record["source"].pop("entrypoint"))
        self.assert_error("program_revision_corrupt", self.store.get, result["revision_id"], status=500)

    def test_malformed_records_and_symlinks_are_not_followed_or_overwritten(self):
        payload = self.payload()
        result = self.store.create(payload)
        path = self.path(result["revision_id"])
        for corrupt in (b"not-json", b"\xff", b'{"schema_version":1,"schema_version":1}', b"x" * (2 * MAX_REVISION_BYTES + 1)):
            with self.subTest(prefix=corrupt[:20]):
                path.write_bytes(corrupt)
                self.assert_error("program_revision_corrupt", self.store.get, result["revision_id"], status=500)
                self.assert_error("program_revision_corrupt", self.store.create, payload, status=500)
                self.assertEqual(path.read_bytes(), corrupt)
        path.unlink()
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_text("private unrelated contents")
        path.symlink_to(outside)
        self.assert_error("program_revision_corrupt", self.store.get, result["revision_id"], status=500)
        self.assert_error("program_revision_corrupt", self.store.create, payload, status=500)
        self.assertEqual(outside.read_text(), "private unrelated contents")

    def test_atomic_publication_failure_leaves_no_partial_record_and_retry_succeeds(self):
        with mock.patch("program_revisions.os.link", side_effect=OSError("inert publish failure")):
            self.assert_error("program_revision_storage_error", self.store.create, self.payload(), status=503)
        self.assertEqual(list(self.root.glob("*.json")), [])
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        result = self.store.create(self.payload())
        self.assertEqual(self.store.get(result["revision_id"]), result)
        self.assertEqual(os.stat(self.path(result["revision_id"])).st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
