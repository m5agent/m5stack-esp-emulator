#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from fetch_firmware import (  # noqa: E402
    current_download_from_detail,
    download_url_from_detail,
    intake_status,
    legacy_download_from_detail,
    merge_current_version,
    resolve_community_firmware,
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

    def test_prefers_current_bin_file_name_for_modern_cdn(self):
        url, metadata = current_download_from_detail(
            "1897200000000000013",
            {
                "code": 200,
                "data": {
                    "currentVersion": {
                        "versionId": "1897300000000000019",
                        "versionName": "1.16",
                        "visibility": "PUBLIC",
                        "status": "PUBLISHED",
                        "binFileName": "03a8270bc364570ba4663a063dcb7957.bin",
                    },
                    "developer": {"userId": "83286"},
                    "supportedDevices": [{"deviceSlug": "core2"}],
                },
            },
            device_slug="core2",
        )
        self.assertEqual(
            url,
            "https://m5burner-cdn.m5stack.com/firmware/"
            "03a8270bc364570ba4663a063dcb7957.bin",
        )
        self.assertEqual(metadata["url_source"], "binFileName")

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

    def test_legacy_download_url_is_available_as_a_fallback(self):
        detail = {
            "code": 200,
            "data": {
                "currentVersion": {
                    "versionId": "2112130111324377090",
                },
                "developer": {"userId": "1"},
            },
        }
        self.assertEqual(
            legacy_download_from_detail("1897200000000002129", detail),
            "https://m5burner-cdn.m5stack.com/community/1/"
            "1897200000000002129/2112130111324377090/bin/"
            "2112130111324377091.bin",
        )

    def test_community_download_falls_back_after_direct_cdn_404(self):
        firmware_id = "1897200000000002129"
        detail = {
            "code": 200,
            "data": {
                "firmwareName": "StackChan-UserDemo",
                "currentVersion": {
                    "versionId": "2112130111324377090",
                    "versionName": "V1.6.0",
                    "visibility": "PUBLIC",
                    "status": "PUBLISHED",
                    "binFileName": "missing-direct-name.bin",
                },
                "developer": {"userId": "1"},
                "supportedDevices": [
                    {"deviceId": "15", "deviceSlug": "stackchan"}
                ],
            },
        }
        calls = []

        def fake_download(url, destination, force=False, extra_metadata=None):
            calls.append((url, extra_metadata))
            if len(calls) == 1:
                raise RuntimeError(f"download failed with HTTP 404: {url}")
            return {
                "url": url,
                "path": str(destination),
                "bytes": 1,
                "sha256": "0" * 64,
                "source": "download",
                **(extra_metadata or {}),
            }

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("fetch_firmware.request_json", return_value=detail),
                patch("fetch_firmware.download", side_effect=fake_download),
            ):
                result = resolve_community_firmware(
                    firmware_id,
                    Path(tmp) / "firmware.bin",
                    api_base="https://burner.example",
                    device_slug="stackchan",
                    force=False,
                    analyze=False,
                    expected_chip_id_value=None,
                )

        self.assertEqual(len(calls), 2)
        self.assertIn("/community/1/", calls[1][0])
        self.assertEqual(
            calls[1][1]["url_source"],
            "legacy-fallback-after-404",
        )
        self.assertEqual(result["url"], calls[1][0])

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

    def test_intake_status_separates_download_and_static_validity(self):
        self.assertEqual(intake_status(analyze=False, result={}), "PASS")
        self.assertEqual(
            intake_status(
                analyze=True,
                result={"analysis": {"valid": True}},
            ),
            "PASS",
        )
        self.assertEqual(
            intake_status(
                analyze=True,
                result={"analysis": {"valid": False}},
            ),
            "PARTIAL",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
