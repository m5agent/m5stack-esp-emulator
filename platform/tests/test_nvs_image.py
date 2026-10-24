#!/usr/bin/env python3

import hashlib
import struct
import unittest
import zlib

from nvs_image import (
    ACTIVE_STATE,
    BITMAP_OFFSET,
    FIRST_ENTRY_OFFSET,
    PAGE_SIZE,
    NvsImageError,
    build_string_nvs_image,
)


class NvsImageTests(unittest.TestCase):
    def test_matches_esp_idf_generator_for_empty_password_vector(self):
        data = build_string_nvs_image(
            0x6000,
            {
                "config": {
                    "wifi_ssid": "myssid",
                    "wifi_password": "",
                    "openaikey": "test-openai-key-not-secret",
                }
            },
        )

        self.assertEqual(
            hashlib.sha256(data).hexdigest(),
            "14f0acc47e1e1bef7e19d29c90febd0fe3707599fd8fc42eeb14dd27cfc26e5d",
        )
        self.assertEqual(len(data), 0x6000)

    def test_page_header_bitmap_and_unused_pages(self):
        data = build_string_nvs_image(
            PAGE_SIZE * 2,
            {
                "config": {
                    "wifi_ssid": "myssid",
                    "wifi_password": "mypassword",
                    "openaikey": "test-key",
                }
            },
        )

        self.assertEqual(
            struct.unpack_from("<I", data, 0)[0],
            ACTIVE_STATE,
        )
        self.assertEqual(data[8], 0xFE)
        self.assertEqual(
            struct.unpack_from("<I", data, 28)[0],
            zlib.crc32(data[4:28], 0xFFFFFFFF) & 0xFFFFFFFF,
        )
        self.assertNotEqual(data[BITMAP_OFFSET], 0xFF)
        self.assertEqual(
            data[FIRST_ENTRY_OFFSET],
            0,
        )
        self.assertEqual(data[PAGE_SIZE:], b"\xFF" * PAGE_SIZE)

    def test_rejects_values_that_do_not_fit_one_page(self):
        with self.assertRaisesRegex(NvsImageError, "maximum"):
            build_string_nvs_image(
                PAGE_SIZE,
                {
                    "config": {
                        f"key{i}": "x" * 200
                        for i in range(30)
                    }
                },
            )

    def test_rejects_invalid_keys_and_partition_sizes(self):
        with self.assertRaisesRegex(NvsImageError, "15"):
            build_string_nvs_image(
                PAGE_SIZE,
                {"config": {"key-that-is-too-long": "value"}},
            )
        with self.assertRaisesRegex(NvsImageError, "multiple of 4096"):
            build_string_nvs_image(
                PAGE_SIZE + 1,
                {"config": {"key": "value"}},
            )
        with self.assertRaisesRegex(NvsImageError, "namespace"):
            build_string_nvs_image(
                PAGE_SIZE,
                {"config": {}},
            )


if __name__ == "__main__":
    unittest.main()
