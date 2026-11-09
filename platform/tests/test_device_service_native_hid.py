"""The native hook addresses must never be used with a different guest image."""
from __future__ import annotations

import unittest

from device_service_errors import ServiceError
from device_service_native_hid import (
    AIRMOUSE_FLASH_SHA256,
    AIRMOUSE_SOURCE_SHA256,
    require_airmouse_image,
)


class NativeHidImageAdmissionTests(unittest.TestCase):
    def test_exact_source_and_composed_flash_are_both_required(self):
        source = {"kind": "merged", "artifact_id": AIRMOUSE_SOURCE_SHA256}
        require_airmouse_image(source, AIRMOUSE_FLASH_SHA256)
        for candidate, flash in (
            ({"kind": "merged", "artifact_id": "0" * 64}, AIRMOUSE_FLASH_SHA256),
            (source, "0" * 64),
            (dict(source, kind="manifest"), AIRMOUSE_FLASH_SHA256),
            ({}, AIRMOUSE_FLASH_SHA256),
        ):
            with self.subTest(source=candidate, flash=flash):
                with self.assertRaises(ServiceError) as rejected:
                    require_airmouse_image(candidate, flash)
                self.assertEqual(rejected.exception.code, "sticks3_native_hid_image_mismatch")
                self.assertEqual(rejected.exception.status, 409)
