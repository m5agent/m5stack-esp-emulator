#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from fetch_firmware import (  # noqa: E402
    current_download_from_detail,
    download_url_from_detail,
    merge_current_version,
)


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
                        "visibility": "PUBLIC",
                        "status": "PUBLISHED",
                    },
                    "developer": {"userId": "1"},
                    "supportedDevices": [
                        {
                            "deviceId": "1897100000000001693",
                            "deviceCode": "STICKS3",
                            "deviceSlug": "sticks3",
                            "deviceName": "StickS3",
                        }
                    ],
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
        self.assertEqual(metadata["supported_devices"][0]["device_slug"], "sticks3")

    def test_rejects_metadata_without_current_version(self):
        with self.assertRaises(RuntimeError):
            download_url_from_detail(
                "1897200000000001693",
                {"code": 200, "data": {"developer": {"userId": "1"}}},
            )

    def test_rejects_unpublished_or_wrong_device_firmware(self):
        detail = {
            "code": 200,
            "data": {
                "firmwareName": "Private firmware",
                "currentVersion": {
                    "versionId": "2",
                    "versionName": "1.0",
                    "visibility": "PRIVATE",
                    "status": "PUBLISHED",
                },
                "developer": {"userId": "1"},
                "supportedDevices": [{"deviceSlug": "sticks3"}],
            },
        }
        with self.assertRaisesRegex(RuntimeError, "not public"):
            current_download_from_detail("1", detail)
        detail["data"]["currentVersion"]["visibility"] = "PUBLIC"
        with self.assertRaisesRegex(RuntimeError, "does not support"):
            current_download_from_detail("1", detail, device_slug="cores3")

    def test_merges_current_public_version_lists(self):
        detail = {
            "code": 200,
            "data": {
                "firmwareName": "Firmware",
                "currentVersion": {
                    "versionId": "20",
                    "versionName": "2.0",
                },
                "developer": {"userId": "7"},
                "supportedDevices": [{"deviceSlug": "sticks3"}],
            },
        }
        merged = merge_current_version(
            detail,
            {
                "code": 200,
                "data": [
                    {
                        "versionId": "20",
                        "versionName": "2.0",
                        "visibility": "PUBLIC",
                        "status": "PUBLISHED",
                        "binFileName": "firmware.merged.bin",
                        "current": True,
                    }
                ],
            },
        )
        version = merged["data"]["currentVersion"]
        self.assertEqual(version["visibility"], "PUBLIC")
        self.assertEqual(version["status"], "PUBLISHED")
        self.assertEqual(version["binFileName"], "firmware.merged.bin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
