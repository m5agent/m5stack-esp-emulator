#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from user_firmware_matrix import (  # noqa: E402
    baseline_name,
    classify_result,
    detect_runtime_model_gaps,
    error_lines,
    inputs_for_device,
    ServiceClient,
)


class UserFirmwareMatrixTests(unittest.TestCase):
    @mock.patch("user_firmware_matrix.request_json")
    def test_service_client_wait_timeout_tracks_observation_window(
        self,
        request_json,
    ):
        request_json.return_value = {"state": "running"}
        client = ServiceClient("http://127.0.0.1:8787", timeout=90)

        client.post(
            "sessions/example/wait",
            {"timeout_seconds": 90},
            timeout=105,
        )

        self.assertEqual(request_json.call_args.kwargs["timeout"], 105)

    def test_baseline_filter_keeps_user_firmware(self):
        self.assertTrue(baseline_name("UIFlow Core2"))
        self.assertTrue(baseline_name("UIFlow2.0 StamPLC"))
        self.assertFalse(baseline_name("M5Launcher"))
        self.assertFalse(baseline_name("Meshtastic For Cardputer-Adv"))

    def test_error_lines_deduplicates_and_orders_crash_evidence(self):
        lines = error_lines(
            "\n".join(
                (
                    "I (100) boot: ready",
                    "Guru Meditation Error: Core 1 panic'ed",
                    "Rebooting...",
                    "Guru Meditation Error: Core 1 panic'ed",
                )
            )
        )

        self.assertEqual(
            lines,
            [
                "Guru Meditation Error: Core 1 panic'ed",
                "Rebooting...",
            ],
        )

    def test_error_lines_detects_new_user_firmware_failures(self):
        lines = error_lines(
            "\n".join(
                (
                    "assert failed: xTaskPriorityDisinherit tasks.c:5156",
                    "Invalid chip id. Expected 13 read 12.",
                    "E task_wdt: Task watchdog got triggered.",
                )
            )
        )

        self.assertEqual(len(lines), 3)

    def test_inputs_route_touch_and_key_devices(self):
        touch = inputs_for_device(
            {"display": {"width": 320, "height": 240, "touch": True}}
        )
        key = inputs_for_device({"display": {"width": 128, "height": 128}})

        self.assertEqual(len(touch), 5)
        self.assertEqual(touch[0]["kind"], "touch")
        self.assertEqual((touch[0]["x"], touch[0]["y"]), (160, 120))
        self.assertEqual(
            key,
            [
                {"kind": "key", "key": "a", "settle_seconds": 0.8},
                {"kind": "key", "key": "ret", "settle_seconds": 0.8},
            ],
        )

    def test_classify_result_keeps_device_service_startup_separate(self):
        status, reason, gaps = classify_result(
            has_screenshot=True,
            nonblack=512,
            running=False,
            crash=False,
            serial_bytes=100,
            boot_error="QMP socket did not appear",
            input_observed=False,
        )

        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "device_service_startup_failed")
        self.assertIn("QMP socket did not appear", gaps[0])

    def test_classify_result_marks_serial_only_device_partial(self):
        status, reason, gaps = classify_result(
            has_screenshot=False,
            nonblack=0,
            running=True,
            crash=False,
            serial_bytes=512,
            boot_error=None,
            input_observed=False,
        )

        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "serial_only_device")
        self.assertIn("no display", gaps[0])

    def test_classify_result_reports_fatal_after_frame(self):
        status, reason, gaps = classify_result(
            has_screenshot=True,
            nonblack=1024,
            running=True,
            crash=True,
            serial_bytes=1024,
            boot_error=None,
            input_observed=True,
        )

        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "fatal_after_application_frame")
        self.assertIn("fatal serial signature", gaps[0])

    def test_classify_result_requires_observable_input_for_pass(self):
        status, reason, gaps = classify_result(
            has_screenshot=True,
            nonblack=1024,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=False,
        )

        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "no_observable_input_response")
        self.assertIn("input", gaps[0])

    def test_classify_result_passes_with_frame_and_input_evidence(self):
        status, reason, gaps = classify_result(
            has_screenshot=True,
            nonblack=1024,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=True,
        )

        self.assertEqual(status, "PASS")
        self.assertEqual(reason, "application_frame_and_runtime_ok")
        self.assertEqual(gaps, [])

    def test_detect_runtime_model_gaps_keeps_zigbee_watchdog_out_of_firmware_fail(self):
        gaps = detect_runtime_model_gaps(
            "app_main()\n"
            "E (2599) task_wdt: Task watchdog got triggered.\n"
            "E (2599) task_wdt: CPU 0: Zigbee_main\n"
        )

        self.assertEqual(
            [gap["code"] for gap in gaps],
            ["zigbee_runtime_not_modeled"],
        )
        status, reason, unmet = classify_result(
            has_screenshot=False,
            nonblack=0,
            running=True,
            crash=True,
            serial_bytes=1024,
            boot_error=None,
            input_observed=True,
            runtime_model_gaps=gaps,
        )
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "runtime_model_gap")
        self.assertIn("zigbee_runtime_not_modeled", unmet[0])

    def test_detect_runtime_model_gap_requires_c6_software_reset_context(self):
        generic = detect_runtime_model_gaps(
            "Invalid chip id. Expected 13 read 12. Bootloader for wrong chip?"
        )
        software_reset = detect_runtime_model_gaps(
            "Invalid chip id. Expected 13 read 12. Bootloader for wrong chip?\n"
            "rst:0x3 (LP_SW_HPSYS),boot:0x8"
        )

        self.assertEqual(generic, [])
        self.assertEqual(
            [gap["code"] for gap in software_reset],
            ["c6_chip_id_lost_after_software_reset"],
        )

    def test_detect_core2_pmic_and_atecc_model_gaps(self):
        pmic = detect_runtime_model_gaps(
            "M5Core2 initializing...\n"
            "[E][Wire.cpp:513] requestFrom(): i2cRead returned Error -1\n",
            device_id="core2",
        )
        atecc = detect_runtime_model_gaps(
            "Core2forAWS: ATECC608 secure element initialization error!\n"
            "abort() was called at PC 0x400d4f3f on core 0\n",
            device_id="core2",
        )

        self.assertEqual(
            [gap["code"] for gap in pmic],
            ["core2_pmic_i2c_model_gap"],
        )
        self.assertEqual(
            [gap["code"] for gap in atecc],
            ["core2_aws_atecc608_model_gap"],
        )
        self.assertEqual(
            detect_runtime_model_gaps(
                "M5Core2 initializing...\n"
                "[E][Wire.cpp:513] requestFrom(): i2cRead returned Error -1\n",
                device_id="sticks3",
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
