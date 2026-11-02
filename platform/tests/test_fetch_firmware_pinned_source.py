#!/usr/bin/env python3
"""Reviewed non-M5Burner firmware sources: SHA-pinned official GitHub releases.

No network access: urlopen is mocked so the failure paths stay deterministic.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

import fetch_firmware  # noqa: E402

PINNED_URL = (
    "https://github.com/m5stack/uiflow-micropython/releases/download/"
    "2.5.4/uiflow-test-esp32-4mb-atomu-v2.5.4.bin"
)


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.headers = {"Content-Length": str(len(data))}

    def read(self, amount: int = -1) -> bytes:
        if amount is not None and amount >= 0:
            return self._data[:amount]
        return self._data

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def pinned_device(data: bytes, *, url: str = PINNED_URL,
                  sha256: str | None = None) -> dict:
    return {
        "id": "atomu",
        "uiflow2": {
            "firmware": {
                "version": "v2.5.4",
                "source": "official-github-release",
                "download_url": url,
                "sha256": sha256 if sha256 is not None else hashlib.sha256(data).hexdigest(),
            }
        },
    }


class PinnedFirmwareSourceTests(unittest.TestCase):
    def test_pinned_download_verifies_sha_and_records_provenance(self) -> None:
        data = b"\xe9" + b"pinned-firmware" * 32
        device = pinned_device(data)
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "atomu" / "uiflow2.bin"
            with mock.patch.object(
                fetch_firmware.urllib.request, "urlopen",
                return_value=FakeResponse(data),
            ) as urlopen:
                result = fetch_firmware.fetch_pinned_firmware(
                    device, destination,
                    force=False, analyze=False, expected_chip_id_value=None,
                )
            self.assertEqual(destination.read_bytes(), data)
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())
            self.assertTrue(result["sha256_verified"])
            self.assertEqual(result["url_source"], "catalog-pinned")
            self.assertEqual(result["expected_sha256"], device["uiflow2"]["firmware"]["sha256"])
            metadata = json.loads(destination.with_suffix(".json").read_text())
            self.assertEqual(metadata["firmware_source"], "official-github-release")
            self.assertEqual(metadata["pinned_version"], "v2.5.4")
            urlopen.assert_called_once()

    def test_sha_mismatch_is_rejected_and_leaves_no_artifact(self) -> None:
        device = pinned_device(b"expected-bytes")
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "atomu" / "uiflow2.bin"
            with mock.patch.object(
                fetch_firmware.urllib.request, "urlopen",
                return_value=FakeResponse(b"tampered-bytes"),
            ):
                with self.assertRaisesRegex(RuntimeError, "sha256 mismatch"):
                    fetch_firmware.fetch_pinned_firmware(
                        device, destination,
                        force=False, analyze=False, expected_chip_id_value=None,
                    )
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".json").exists())

    def test_stale_cache_is_refreshed_instead_of_trusted(self) -> None:
        data = b"fresh-bytes"
        device = pinned_device(data)
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "atomu" / "uiflow2.bin"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"stale-old-build")
            with mock.patch.object(
                fetch_firmware.urllib.request, "urlopen",
                return_value=FakeResponse(data),
            ) as urlopen:
                result = fetch_firmware.fetch_pinned_firmware(
                    device, destination,
                    force=False, analyze=False, expected_chip_id_value=None,
                )
            urlopen.assert_called_once()
            self.assertEqual(destination.read_bytes(), data)
            self.assertEqual(result["source"], "download")

    def test_matching_cache_avoids_network(self) -> None:
        data = b"cached-bytes"
        device = pinned_device(data)
        with tempfile.TemporaryDirectory() as raw:
            destination = Path(raw) / "atomu" / "uiflow2.bin"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(data)
            with mock.patch.object(
                fetch_firmware.urllib.request, "urlopen",
                side_effect=AssertionError("network must not be used for a verified cache hit"),
            ):
                result = fetch_firmware.fetch_pinned_firmware(
                    device, destination,
                    force=False, analyze=False, expected_chip_id_value=None,
                )
            self.assertEqual(result["source"], "cache")
            self.assertEqual(result["sha256"], hashlib.sha256(data).hexdigest())

    def test_invalid_pins_fail_before_network(self) -> None:
        cases = [
            {"source": "official-github-release", "download_url": "https://example.com/x.bin",
             "sha256": "a" * 64},
            {"source": "official-github-release", "download_url": PINNED_URL},
            {"source": "official-github-release", "download_url": PINNED_URL,
             "sha256": "A" * 64},
            {"source": "official-github-release", "download_url": PINNED_URL,
             "sha256": "not-a-digest"},
            {"source": "m5burner", "download_url": PINNED_URL, "sha256": "a" * 64},
        ]
        with mock.patch.object(
            fetch_firmware.urllib.request, "urlopen",
            side_effect=AssertionError("network must not be used for invalid pins"),
        ):
            for firmware in cases:
                with self.subTest(firmware=firmware):
                    with self.assertRaises(RuntimeError):
                        fetch_firmware.validate_pinned_firmware(firmware)


if __name__ == "__main__":
    unittest.main(verbosity=2)
