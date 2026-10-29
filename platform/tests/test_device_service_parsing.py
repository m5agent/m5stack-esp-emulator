from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import device_service
import device_service_errors
import device_service_parsing


class DeviceServiceParsingBoundaryTests(unittest.TestCase):
    def test_service_error_keeps_public_payload_and_compatibility_export(self):
        error = device_service_errors.ServiceError(
            "invalid_test",
            "bad value",
            409,
            field="answer",
        )
        self.assertEqual(error.code, "invalid_test")
        self.assertEqual(error.message, "bad value")
        self.assertEqual(error.status, 409)
        self.assertEqual(
            error.payload(),
            {
                "error": {
                    "code": "invalid_test",
                    "message": "bad value",
                    "field": "answer",
                }
            },
        )
        self.assertIs(device_service.ServiceError, device_service_errors.ServiceError)

    def test_parse_int_accepts_decimal_and_prefixed_integers(self):
        self.assertEqual(device_service_parsing.parse_int(12, "value"), 12)
        self.assertEqual(device_service_parsing.parse_int("12", "value"), 12)
        self.assertEqual(device_service_parsing.parse_int("0x10", "value"), 16)

    def test_parse_int_preserves_invalid_request_error(self):
        with self.assertRaises(device_service_errors.ServiceError) as caught:
            device_service_parsing.parse_int("x10", "segments[0].offset")
        self.assertEqual(caught.exception.code, "invalid_request")
        self.assertEqual(caught.exception.status, 400)
        self.assertEqual(
            caught.exception.message,
            "segments[0].offset must be an integer",
        )

    def test_parse_size_preserves_case_insensitive_tuple_contract(self):
        self.assertEqual(
            device_service_parsing.parse_size("320X240"),
            (320, 240),
        )
        self.assertIsNone(device_service_parsing.parse_size(None))
        self.assertIsNone(device_service_parsing.parse_size("320"))
        self.assertIsNone(device_service_parsing.parse_size("320xNaN"))

    def test_capture_pcap_preserves_default_and_bool_only_contract(self):
        self.assertEqual(device_service_parsing.parse_capture_pcap(None), True)
        self.assertEqual(
            device_service_parsing.parse_capture_pcap(None, default=False),
            False,
        )
        self.assertEqual(
            device_service_parsing.parse_capture_pcap(False),
            False,
        )
        with self.assertRaises(device_service_errors.ServiceError) as caught:
            device_service_parsing.parse_capture_pcap("false")
        self.assertEqual(caught.exception.code, "invalid_network")

    def test_sha256_contract_is_lowercase_and_complete(self):
        value = "a" * 64
        self.assertTrue(device_service_parsing.is_sha256(value))
        self.assertTrue(device_service_parsing._is_sha256(value))
        self.assertFalse(device_service_parsing.is_sha256("A" * 64))
        self.assertFalse(device_service_parsing.is_sha256("a" * 63))

    def test_reexported_parser_symbols_keep_identity(self):
        self.assertIs(
            device_service.parse_int,
            device_service_parsing.parse_int,
        )
        self.assertIs(
            device_service.parse_size,
            device_service_parsing.parse_size,
        )
        self.assertIs(
            device_service.parse_capture_pcap,
            device_service_parsing.parse_capture_pcap,
        )
        self.assertIs(
            device_service._is_sha256,
            device_service_parsing._is_sha256,
        )


if __name__ == "__main__":
    unittest.main()
