#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "platform/tools"))

from user_firmware_matrix import (  # noqa: E402
    MatrixError,
    apply_execution_expectations,
    baseline_name,
    classify_result,
    detect_runtime_model_gaps,
    download_candidates,
    error_lines,
    evaluate_network_expectation,
    inputs_for_device,
    load_execution_expectations,
    prepare_review_runtime,
    refresh_selected_sample,
    sample_result_key,
    ServiceClient,
)


class UserFirmwareMatrixTests(unittest.TestCase):
    @staticmethod
    def write_expectations(
        root: Path,
        expectations: list[dict],
    ) -> Path:
        path = root / "expectations.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "expectations": expectations,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_expectation_schema_matches_v1_contract(self):
        schema = json.loads(
            (
                ROOT
                / "platform/tools/user_firmware_expectations.schema.json"
            ).read_text(encoding="utf-8")
        )

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(
            set(
                schema["$defs"]["expectation"]["properties"]["mode"]["enum"]
            ),
            {"ui-interactive", "headless-serial", "network-first"},
        )
        network_properties = schema["$defs"]["network"]["properties"]
        self.assertIn("wifi_password_env", network_properties)
        self.assertNotIn("wifi_password", network_properties)

    def test_public_matrix_refreshes_cached_firmware(self):
        row = {
            "firmwareId": "firmware-1",
            "firmwareName": "Community firmware",
            "sourceType": "COMMUNITY",
            "currentVersion": {
                "versionName": "1.0",
                "publishTime": "2026-10-25T00:00:00+08:00",
            },
            "developer": {"nickname": "developer"},
            "statistics": {"downloadCount": 10},
        }
        with tempfile.TemporaryDirectory() as directory, (
            mock.patch(
                "user_firmware_matrix.burner_devices",
                return_value=[
                    {
                        "deviceId": "device-1",
                        "deviceName": "AtomS3R",
                    }
                ],
            )
        ), mock.patch(
            "user_firmware_matrix.burner_search",
            return_value=[row],
        ), mock.patch(
            "user_firmware_matrix.resolve_community_firmware",
            return_value={
                "bytes": 8,
                "sha256": "0" * 64,
                "url": "https://cdn.example/firmware.bin",
            },
        ) as resolve, mock.patch(
            "user_firmware_matrix.analyze_firmware",
            return_value={"valid": True},
        ), mock.patch(
            "user_firmware_matrix.expected_chip_id",
            return_value=9,
        ):
            selection = download_candidates(
                device_id="atoms3r",
                target_name="AtomS3R",
                target_slug="atoms3r",
                base_url="https://burner.example",
                cache_dir=Path(directory),
                candidate_limit=5,
                sample_limit=1,
                device_soc="esp32s3",
            )
        self.assertEqual(len(selection["selected"]), 1)
        self.assertTrue(resolve.call_args.kwargs["force"])

    def test_resume_refresh_rebinds_cached_firmware_to_current_bytes(self):
        sample = {
            "device_id": "atoms3r",
            "firmware_id": "firmware-1",
            "burner_device_slug": "atoms3r",
            "sha256": "0" * 64,
            "path": "/old/firmware.bin",
        }
        with tempfile.TemporaryDirectory() as directory, (
            mock.patch(
                "user_firmware_matrix.resolve_community_firmware",
                return_value={
                    "bytes": 8,
                    "sha256": "1" * 64,
                    "url": "https://cdn.example/firmware.bin",
                },
            )
        ) as resolve, mock.patch(
            "user_firmware_matrix.analyze_firmware",
            return_value={"valid": True},
        ), mock.patch(
            "user_firmware_matrix.expected_chip_id",
            return_value=9,
        ):
            refreshed = refresh_selected_sample(
                sample,
                base_url="https://burner.example",
                cache_dir=Path(directory),
                device_soc="esp32s3",
            )
        self.assertTrue(resolve.call_args.kwargs["force"])
        self.assertEqual(refreshed["sha256"], "1" * 64)
        self.assertEqual(
            sample_result_key(refreshed),
            f"atoms3r:firmware-1:{'1' * 64}",
        )
        self.assertNotEqual(
            sample_result_key(sample),
            sample_result_key(refreshed),
        )

    def test_storage_fixture_participates_in_result_key(self):
        sample = {
            "device_id": "papermono",
            "firmware_id": "firmware-1",
            "sha256": "1" * 64,
        }
        with_storage = {
            **sample,
            "storage_fixture": {
                "artifact_id": "2" * 64,
                "sha256": "2" * 64,
                "bytes": 32 << 20,
            },
        }

        self.assertNotEqual(
            sample_result_key(sample),
            sample_result_key(with_storage),
        )
        self.assertTrue(
            sample_result_key(with_storage).endswith(f":sd={'2' * 64}")
        )

    def test_network_first_expectation_binds_firmware_and_nvs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nvs = root / "network.nvs"
            nvs.write_bytes(b"\xff" * 4096)
            expectations_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "network-first",
                        "runtime": "qemu-wifi",
                        "ready_marker": "got ip:",
                        "required_markers": ["wifi:connected", "got ip:"],
                        "network": {
                            "profile": "generic-observe",
                            "wifi_auth": "open",
                            "expected_markers": ["got ip:"],
                        },
                        "nvs": {
                            "partition_label": "nvs",
                            "image_path": nvs.name,
                        },
                    }
                ],
            )
            expectations = load_execution_expectations(expectations_path)
            sample = {
                "device_id": "atoms3r",
                "firmware_id": "firmware-1",
                "sha256": "1" * 64,
            }
            apply_execution_expectations([sample], expectations)

        self.assertEqual(
            sample["review_expectation"]["mode"],
            "network-first",
        )
        self.assertEqual(
            sample["review_expectation"]["nvs"]["partition_label"],
            "nvs",
        )
        self.assertIn(
            "expectation=",
            sample_result_key(sample),
        )
        self.assertNotIn(
            "wifi_password",
            json.dumps(sample["review_expectation"]),
        )

    def test_stale_expectation_sha_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expectations_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "headless-serial",
                        "required_markers": ["application ready"],
                    }
                ],
            )
            expectations = load_execution_expectations(expectations_path)
            sample = {
                "device_id": "atoms3r",
                "firmware_id": "firmware-1",
                "sha256": "2" * 64,
            }

            with self.assertRaisesRegex(MatrixError, "SHA mismatch"):
                apply_execution_expectations([sample], expectations)

    def test_expectation_rejects_plaintext_password_and_relaxed_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            password_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "network-first",
                        "runtime": "qemu-wifi",
                        "required_markers": ["got ip:"],
                        "network": {
                            "wifi_password": "do-not-store-this",
                        },
                    }
                ],
            )
            with self.assertRaisesRegex(MatrixError, "wifi_password_env"):
                load_execution_expectations(password_path)

            relaxed_ui_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "ui-interactive",
                        "require_frame": False,
                    }
                ],
            )
            with self.assertRaisesRegex(MatrixError, "requires frame"):
                load_execution_expectations(relaxed_ui_path)

            disabled_network_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "network-first",
                        "runtime": "qemu-wifi",
                        "required_markers": ["got ip:"],
                        "require_network": False,
                        "network": {},
                    }
                ],
            )
            with self.assertRaisesRegex(MatrixError, "requires network"):
                load_execution_expectations(disabled_network_path)

    def test_expectation_rejects_unknown_network_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_expectations(
                Path(directory),
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "network-first",
                        "runtime": "qemu-wifi",
                        "required_markers": ["got ip:"],
                        "network": {
                            "proflie": "generic-observe",
                        },
                    }
                ],
            )

            with self.assertRaisesRegex(MatrixError, "proflie"):
                load_execution_expectations(path)

    def test_prepare_runtime_loads_password_environment_and_nvs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nvs = root / "network.nvs"
            nvs.write_bytes(b"\xaa" * 1024)
            expectations_path = self.write_expectations(
                root,
                [
                    {
                        "device_id": "atoms3r",
                        "firmware_id": "firmware-1",
                        "sha256": "1" * 64,
                        "mode": "network-first",
                        "runtime": "qemu-wifi",
                        "required_markers": ["got ip:"],
                        "network": {
                            "wifi_auth": "wpa2-psk",
                            "wifi_password_env": "M5_TEST_REVIEW_PASSWORD",
                        },
                        "nvs": {
                            "partition_label": "nvs",
                            "image_path": nvs.name,
                        },
                    }
                ],
            )
            expectations = load_execution_expectations(expectations_path)
            sample = {
                "device_id": "atoms3r",
                "firmware_id": "firmware-1",
                "sha256": "1" * 64,
            }
            apply_execution_expectations([sample], expectations)
            client = mock.Mock()
            client.upload.return_value = {
                "artifact_id": "3" * 64,
                "sha256": sample["_review_expectation_private"]["_nvs"][
                    "sha256"
                ],
                "size": 1024,
            }
            with mock.patch.dict(
                "os.environ",
                {"M5_TEST_REVIEW_PASSWORD": "synthetic-pass"},
            ):
                prepared = prepare_review_runtime(client, sample)

        self.assertEqual(prepared["runtime"], "qemu-wifi")
        self.assertEqual(prepared["ready_marker"], "got ip:")
        self.assertEqual(
            prepared["network"]["wifi_password"],
            "synthetic-pass",
        )
        self.assertEqual(prepared["nvs"]["partition_label"], "nvs")
        self.assertNotIn(
            "synthetic-pass",
            json.dumps(sample["review_expectation"]),
        )

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

    def test_network_first_expectation_can_pass_without_frame(self):
        status, reason, gaps = classify_result(
            has_screenshot=True,
            nonblack=0,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=False,
            review_expectation={
                "mode": "network-first",
                "require_network": True,
            },
            required_markers_observed=True,
            network_observed=True,
        )

        self.assertEqual(status, "PASS")
        self.assertEqual(reason, "network-first_expectation_ok")
        self.assertEqual(gaps, [])

    def test_network_first_requires_finalized_pcap_when_enabled(self):
        complete = evaluate_network_expectation(
            {
                "status": "PASS",
                "packet_capture": {
                    "status": "PASS",
                    "input": {"sha256": "1" * 64},
                },
            },
            require_capture=True,
        )
        missing = evaluate_network_expectation(
            {
                "status": "PASS",
                "packet_capture": {"status": "CAPTURING"},
            },
            require_capture=True,
        )
        disabled = evaluate_network_expectation(
            {"status": "PASS", "packet_capture": {"status": "NOT_RUN"}},
            require_capture=False,
        )

        self.assertTrue(complete["observed"])
        self.assertTrue(complete["pcap_observed"])
        self.assertFalse(missing["observed"])
        self.assertFalse(missing["pcap_observed"])
        self.assertTrue(disabled["observed"])

    def test_network_first_missing_marker_or_network_does_not_pass(self):
        marker_status, marker_reason, _ = classify_result(
            has_screenshot=True,
            nonblack=0,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=False,
            review_expectation={
                "mode": "network-first",
                "require_network": True,
            },
            required_markers_observed=False,
            network_observed=True,
        )
        network_status, network_reason, _ = classify_result(
            has_screenshot=True,
            nonblack=0,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=False,
            review_expectation={
                "mode": "network-first",
                "require_network": True,
            },
            required_markers_observed=True,
            network_observed=False,
        )

        self.assertEqual((marker_status, marker_reason), (
            "PARTIAL",
            "expected_runtime_marker_missing",
        ))
        self.assertEqual((network_status, network_reason), (
            "PARTIAL",
            "network_expectation_not_met",
        ))

    def test_forbidden_expectation_marker_fails(self):
        status, reason, gaps = classify_result(
            has_screenshot=False,
            nonblack=0,
            running=True,
            crash=False,
            serial_bytes=1024,
            boot_error=None,
            input_observed=False,
            review_expectation={"mode": "headless-serial"},
            required_markers_observed=True,
            forbidden_markers_observed=True,
        )

        self.assertEqual(status, "FAIL")
        self.assertEqual(reason, "forbidden_runtime_marker_observed")
        self.assertIn("forbidden", gaps[0])

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

    def test_detect_papermono_missing_sd_fixture_as_runtime_gap(self):
        serial = "\n".join(
            "E (388) sdmmc_common: sdmmc_init_ocr: "
            "send_op_cond (1) returned 0x107"
            for _ in range(4)
        )
        gaps = detect_runtime_model_gaps(serial, device_id="papermono")

        self.assertEqual(
            [gap["code"] for gap in gaps],
            ["papermono_sd_fixture_unavailable"],
        )
        self.assertEqual(gaps[0]["category"], "fixture")

        status, reason, unmet = classify_result(
            has_screenshot=True,
            nonblack=384000,
            running=True,
            crash=False,
            serial_bytes=len(serial),
            boot_error=None,
            input_observed=True,
            runtime_model_gaps=gaps,
        )
        self.assertEqual(status, "PARTIAL")
        self.assertEqual(reason, "runtime_fixture_gap")
        self.assertIn("papermono_sd_fixture_unavailable", unmet[0])

    def test_detect_papermono_sd_gap_requires_repeated_failures(self):
        serial = (
            "E (388) sdmmc_common: sdmmc_init_ocr: "
            "send_op_cond (1) returned 0x107"
        )
        self.assertEqual(
            detect_runtime_model_gaps(serial, device_id="papermono"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
