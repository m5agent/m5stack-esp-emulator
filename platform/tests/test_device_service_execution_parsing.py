#!/usr/bin/env python3
from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest import mock

import device_service
import device_service_specs
from device_service_errors import ServiceError
from device_service_execution_parsing import (
    parse_nvs_execution,
    parse_storage_execution,
)


ARTIFACT_ID = "a" * 64


class DeviceServiceExecutionParsingTests(unittest.TestCase):
    def test_device_service_reexports_the_same_parser_objects(self) -> None:
        self.assertIs(
            device_service.parse_storage_execution,
            parse_storage_execution,
        )
        self.assertIs(
            device_service.parse_nvs_execution,
            parse_nvs_execution,
        )

    def test_storage_parser_preserves_contract(self) -> None:
        spec = SimpleNamespace(id="cores3", has_sd_card=True)
        self.assertEqual(parse_storage_execution(spec, None), {})
        self.assertEqual(
            parse_storage_execution(
                spec,
                {"sd_image_artifact_id": ARTIFACT_ID},
            ),
            {
                "interface": "spi",
                "format": "raw",
                "sd_image_artifact_id": ARTIFACT_ID,
            },
        )

    def test_storage_protocol_matches_native_board_wiring(self) -> None:
        for device, interface in (("core2", "spi"), ("cores3", "spi"),
                                  ("cardputer", "spi"), ("cardputer-adv", "spi"),
                                  ("papercolor", "spi"),
                                  ("papers3", "spi"),
                                  ("papermono", "sdmmc")):
            with self.subTest(device=device):
                value = parse_storage_execution(
                    device_service.load_device_specs()[device],
                    {"sd_image_artifact_id": ARTIFACT_ID},
                )
                self.assertEqual(value["interface"], interface)

    def test_unsupported_card_slots_stay_unavailable(self) -> None:
        specs = device_service.load_device_specs()
        for device in ("basic-v27", "dial", "sticks3"):
            with self.subTest(device=device):
                spec = specs[device]
                self.assertFalse(spec.has_sd_card)
                with self.assertRaises(ServiceError) as result:
                    parse_storage_execution(spec, {"sd_image_artifact_id": ARTIFACT_ID})
                self.assertEqual(result.exception.code, "storage_not_supported")

    def test_paperdiy_spi_admission_requires_native_card_detect_marker(self) -> None:
        spec = device_service.load_device_specs()["paperdiy"]
        payload = {"sd_image_artifact_id": ARTIFACT_ID}
        with mock.patch.object(device_service_specs, "qemu_has_qom_property", return_value=False) as probe:
            self.assertFalse(spec.has_sd_card)
            with self.assertRaises(ServiceError) as result:
                parse_storage_execution(spec, payload)
            self.assertEqual(result.exception.code, "storage_not_supported")
            probe.return_value = True
            self.assertTrue(spec.has_sd_card)
            self.assertEqual(parse_storage_execution(spec, payload)["interface"], "spi")
            probe.assert_called_with(
                spec.qemu, "m5paperdiy-machine", "sd-card-detect-model", "bool"
            )

    def test_storage_parser_fail_closed(self) -> None:
        no_sd = SimpleNamespace(id="core2", has_sd_card=False)
        for value, code, status in (
            (
                "bad",
                "invalid_storage",
                400,
            ),
            (
                {"sd_image_artifact_id": ARTIFACT_ID, "extra": 1},
                "invalid_storage",
                400,
            ),
            (
                {"sd_image_artifact_id": "bad"},
                "invalid_storage",
                400,
            ),
            (
                {"sd_image_artifact_id": ARTIFACT_ID},
                "storage_not_supported",
                409,
            ),
        ):
            with self.subTest(value=value):
                with self.assertRaises(ServiceError) as caught:
                    parse_storage_execution(no_sd, value)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(caught.exception.status, status)

    def test_nvs_parser_preserves_contract(self) -> None:
        self.assertEqual(parse_nvs_execution(None), {})
        self.assertEqual(
            parse_nvs_execution({"image_artifact_id": ARTIFACT_ID}),
            {
                "partition_label": "nvs",
                "image_artifact_id": ARTIFACT_ID,
            },
        )
        self.assertEqual(
            parse_nvs_execution(
                {
                    "image_artifact_id": ARTIFACT_ID,
                    "partition_label": "factory_nvs",
                }
            ),
            {
                "partition_label": "factory_nvs",
                "image_artifact_id": ARTIFACT_ID,
            },
        )

    def test_nvs_parser_fail_closed(self) -> None:
        for value in (
            "bad",
            {},
            {"image_artifact_id": ARTIFACT_ID, "extra": 1},
            {"image_artifact_id": ARTIFACT_ID, "partition_label": ""},
            {
                "image_artifact_id": ARTIFACT_ID,
                "partition_label": "x" * 17,
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(ServiceError) as caught:
                    parse_nvs_execution(value)
                self.assertEqual(caught.exception.code, "invalid_nvs")
                self.assertEqual(caught.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
