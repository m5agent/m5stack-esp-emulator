"""Source delivery boundaries exercised against independent Git histories."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import check_pr_scope as scope


class PrScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.patch = mock.patch.object(scope, "ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.test")
        self.git("config", "user.name", "Offline fixture")
        self.write("README.md", b"base")
        self.base = self.commit("base", "README.md")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root).decode().strip()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def commit(self, message, *paths):
        self.git("add", "--", *paths)
        self.git("commit", "-qm", message)
        return self.git("rev-parse", "HEAD")

    def test_runtime_assets_and_small_summary_are_source(self):
        self.write("platform/web/texture.png", b"runtime asset")
        self.write("docs/evidence/summary.json", json.dumps({"hardware": "NOT RUN"}).encode())
        head = self.commit("source", "platform/web/texture.png", "docs/evidence/summary.json")
        result = scope.inspect(self.base, head)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["new_blobs"], 2)

    def test_deleted_raw_evidence_remains_a_history_failure(self):
        self.write("docs/evidence/session/evidence.zip", b"raw archive")
        self.commit("raw", "docs/evidence/session/evidence.zip")
        self.git("rm", "-q", "docs/evidence/session/evidence.zip")
        self.git("commit", "-qm", "delete raw")
        result = scope.inspect(self.base, "HEAD")
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("raw evidence" in error for error in result["errors"]))

    def test_summary_alias_does_not_hide_raw_path(self):
        for path in ("docs/evidence/a.json", "docs/evidence/a.zip"):
            self.write(path, b"same content")
        self.commit("aliases", "docs/evidence/a.json", "docs/evidence/a.zip")
        self.assertEqual(scope.inspect(self.base, "HEAD")["status"], "FAIL")

    def test_content_budget_counts_blobs_deleted_from_final_tree(self):
        self.write("large.txt", b"x" * 128)
        self.commit("large", "large.txt")
        self.git("rm", "-q", "large.txt")
        self.git("commit", "-qm", "delete large")
        with mock.patch.object(scope, "MAX_NEW_BLOB_BYTES", 64):
            result = scope.inspect(self.base, "HEAD")
        self.assertEqual(result["new_blob_bytes"], 128)
        self.assertEqual(result["status"], "FAIL")

    def test_oversized_summary_is_not_accepted_as_source(self):
        self.write("docs/evidence/summary.md", b"x" * 128)
        self.commit("summary", "docs/evidence/summary.md")
        with mock.patch.object(scope, "MAX_SUMMARY_BYTES", 64):
            self.assertEqual(scope.inspect(self.base, "HEAD")["status"], "FAIL")

    def test_merge_checkout_does_not_count_target_branch_evidence(self):
        self.git("checkout", "-qb", "feature")
        self.write("source.py", b"pass")
        self.commit("feature", "source.py")
        self.git("checkout", "-qb", "target", self.base)
        self.write("docs/evidence/upstream.zip", b"existing target artifact")
        target = self.commit("upstream", "docs/evidence/upstream.zip")
        self.git("merge", "--no-ff", "-qm", "merge preview", "feature")
        result = scope.inspect(target, "HEAD")
        self.assertEqual(result["status"], "PASS", result)

    def test_binary_masquerading_as_summary_is_rejected(self):
        self.write("docs/evidence/summary.json", b"PK\x00\xffnot JSON")
        self.commit("binary", "docs/evidence/summary.json")
        self.assertEqual(scope.inspect(self.base, "HEAD")["status"], "FAIL")
