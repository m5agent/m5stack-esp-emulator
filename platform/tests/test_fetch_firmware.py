#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from fetch_firmware import download_url_from_detail  # noqa: E402


class FirmwareResolverTests(unittest.TestCase):
    def test_builds_current_cdn_url_from_public_detail(self):
        url, metadata = download_url_from_detail(
            "1897200000000001693",
            {
                "code": 200,
                "data": {
                    "currentVersion": {
                        "versionId": "2113078299069861889",
                        "versionName": "v2.5.3",
                        "publishTime": "2026-10-22T09:21:42+08:00",
                    },
                    "developer": {"userId": "1"},
                },
            },
        )
        self.assertEqual(
            url,
            "https://m5burner-cdn.m5stack.com/community/1/"
            "1897200000000001693/2113078299069861889/bin/"
            "2113078299069861890.bin",
        )
        self.assertEqual(metadata["resolved_version"], "v2.5.3")

    def test_rejects_metadata_without_current_version(self):
        with self.assertRaises(RuntimeError):
            download_url_from_detail(
                "1897200000000001693",
                {"code": 200, "data": {"developer": {"userId": "1"}}},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
