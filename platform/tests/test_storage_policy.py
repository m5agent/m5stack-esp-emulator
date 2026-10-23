#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from storage_policy import StoragePolicy, directory_size_bytes


class StoragePolicyTests(unittest.TestCase):
    def test_environment_overrides(self):
        values = {
            "M5_SERVICE_HISTORY_TTL": "120",
            "M5_SERVICE_MAX_HISTORY_SESSIONS": "7",
            "M5_SERVICE_MAX_HISTORY_BYTES": "1024",
            "M5_SERVICE_MAX_CACHE_BYTES": "2048",
            "M5_SERVICE_CACHE_GRACE": "30",
            "M5_SERVICE_MIN_FREE_BYTES": "4096",
            "M5_SERVICE_RETAIN_SESSION_FLASH": "yes",
            "M5_SERVICE_STORAGE_PRUNE_INTERVAL": "5",
        }
        with mock.patch.dict(os.environ, values, clear=False):
            policy = StoragePolicy.from_env()
        self.assertEqual(policy.history_ttl_seconds, 120)
        self.assertEqual(policy.max_history_sessions, 7)
        self.assertEqual(policy.max_history_bytes, 1024)
        self.assertEqual(policy.max_cache_bytes, 2048)
        self.assertEqual(policy.cache_grace_seconds, 30)
        self.assertEqual(policy.min_free_bytes, 4096)
        self.assertTrue(policy.retain_session_flash)
        self.assertEqual(policy.prune_interval_seconds, 5)

    def test_invalid_boolean_is_rejected(self):
        with mock.patch.dict(
            os.environ,
            {"M5_SERVICE_RETAIN_SESSION_FLASH": "sometimes"},
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "must be a boolean"):
                StoragePolicy.from_env()

    def test_directory_size_ignores_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a").write_bytes(b"a" * 10)
            (root / "nested").mkdir()
            (root / "nested" / "b").write_bytes(b"b" * 20)
            self.assertEqual(directory_size_bytes(root), 30)
            self.assertEqual(directory_size_bytes(root / "missing"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
