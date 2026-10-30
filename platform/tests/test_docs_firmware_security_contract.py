#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest

from _docs_contract_support import DocsContractBase, ROOT, DOCS


class DocsFirmwareSecurityContractTests(DocsContractBase):
    def test_filesystem_permission_policy_does_not_overclaim(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-filesystem-permission-policy.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["scope"], "static filesystem metadata only")
        fat = evidence["filesystems"]["fat12"]
        self.assertEqual(fat["permission_model"]["kind"], "fat-attributes")
        self.assertTrue(fat["sample_file_policy"]["read_only_attribute"])
        self.assertEqual(
            fat["sample_file_policy"]["runtime_enforcement"],
            "not-proven",
        )
        for kind in ("littlefs", "spiffs"):
            filesystem = evidence["filesystems"][kind]
            self.assertEqual(filesystem["permission_model"]["kind"], "none")
            self.assertEqual(
                filesystem["sample_file_policy"]["unix_mode"],
                "not-recorded",
            )
            self.assertEqual(
                filesystem["permission_summary"]["runtime_enforcement"],
                "NOT RUN",
            )

    def test_source_license_scan_is_bounded_and_feeds_policy(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-source-license-scan.json"
            ).read_text()
        )
        scan = evidence["source_license_scan"]
        self.assertEqual(scan["status"], "PASS")
        self.assertEqual(scan["method"], "bounded-source-spdx-header-scan")
        self.assertEqual(scan["coverage"]["files_scanned"], 2)
        self.assertFalse(scan["limits"]["files_truncated"])
        self.assertEqual(
            scan["coverage"]["declared_licenses"],
            ["Apache-2.0", "MIT"],
        )
        self.assertTrue(
            any(row.get("redacted") for row in scan["files"])
        )
        self.assertEqual(
            evidence["license_policy"]["coverage"][
                "source_code_declarations"
            ],
            2,
        )
        self.assertEqual(
            evidence["license_policy"]["status"],
            "REVIEW_REQUIRED",
        )

    def test_public_firmware_identity_is_bound_to_refreshed_bytes(self) -> None:
        matrix = (DOCS / "user-firmware-simulation-matrix.md").read_text()
        manifest = (DOCS / "firmware-manifest.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        tool = (ROOT / "platform/tools/user_firmware_matrix.py").read_text()
        tool_tests = (
            ROOT / "platform/tests/test_user_firmware_matrix.py"
        ).read_text()

        self.assertIn("# Public CDN objects may change", tool)
        self.assertIn("force=True", tool)
        self.assertIn("def refresh_selected_sample", tool)
        self.assertIn("def sample_result_key", tool)
        self.assertIn("selection[\"selected\"] = refreshed_samples", tool)
        self.assertIn("test_public_matrix_refreshes_cached_firmware", tool_tests)
        self.assertIn(
            "test_resume_refresh_rebinds_cached_firmware_to_current_bytes",
            tool_tests,
        )
        self.assertIn("historical artifacts", matrix)
        self.assertIn("Current public-artifact refresh checkpoint", matrix)
        self.assertIn("3 PASS / 1 PARTIAL / 0 FAIL", matrix)
        self.assertIn("runtime_fixture_gap", matrix)
        self.assertIn("fat32-mbr", matrix)
        self.assertIn("storage.sd_image_artifact_id", api)
        self.assertIn("StorageExecution:", openapi)
        self.assertIn("nvs.image_artifact_id", api)
        self.assertIn("NvsExecution:", openapi)
        self.assertIn(
            "公开 CDN 的 URL 和版本元数据不构成不可变内容承诺",
            manifest,
        )
        refreshed = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-public-artifacts-static.json"
            ).read_text()
        )
        self.assertEqual(refreshed["status"], "STATIC_PASS")
        self.assertEqual(refreshed["functional_status"], "NOT RUN")
        self.assertEqual(len(refreshed["samples"]), 4)
        self.assertTrue(
            all(
                sample["static_analysis"] == "PASS"
                for sample in refreshed["samples"]
            )
        )
        refreshed_manifests = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-public-artifacts-manifest.json"
            ).read_text()
        )
        self.assertEqual(refreshed_manifests["status"], "PASS")
        self.assertEqual(
            refreshed_manifests["functional_status"],
            "NOT RUN",
        )
        self.assertEqual(len(refreshed_manifests["samples"]), 4)
        self.assertTrue(
            all(
                sample["validation"] == "PASS"
                and sample["review_status"] == "REVIEW_REQUIRED"
                for sample in refreshed_manifests["samples"]
            )
        )
        capability_observation = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-image-capability-observation.json"
            ).read_text()
        )
        self.assertEqual(capability_observation["status"], "PASS")
        self.assertEqual(
            capability_observation["normal_import"]["status"],
            "PASS",
        )
        self.assertEqual(
            capability_observation["mismatch_import"]["status"],
            "REJECTED",
        )
        self.assertIn(
            "unsupported_capability",
            capability_observation["mismatch_import"]["issues"]["errors"],
        )
        observed_capabilities = {
            item["capability"]
            for item in capability_observation["normal_import"]["observed"]
        }
        self.assertTrue({"wifi", "display"}.issubset(observed_capabilities))
        self.assertIn(
            "capabilities.observed",
            manifest,
        )
        self.assertIn(
            "observed_capability_not_declared",
            manifest,
        )
        firmware_report = (
            ROOT / "platform/web/firmware-report.js"
        ).read_text()
        upload_test = (
            ROOT / "platform/tests/test_firmware_upload.mjs"
        ).read_text()
        self.assertIn("capabilitySummary", firmware_report)
        self.assertIn("validationIssueRows", firmware_report)
        self.assertIn("Image observations", (
            ROOT / "platform/web/firmware.js"
        ).read_text())
        self.assertIn("capabilitySummary", upload_test)
        self.assertIn(
            "webburner-capability-observation.jpg",
            manifest,
        )
        webburner_evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-webburner-capability-display.json"
            ).read_text()
        )
        self.assertEqual(webburner_evidence["status"], "PASS")
        self.assertEqual(
            webburner_evidence["visible_assertions"]["image_scan"],
            "SCANNED · 8.00 MiB / 8.00 MiB · complete",
        )
        screenshot = ROOT / webburner_evidence["screenshot"]["file"]
        self.assertEqual(
            hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            webburner_evidence["screenshot"]["sha256"],
        )
        refreshed_functional = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-four-functional/evidence.json"
            ).read_text()
        )
        self.assertEqual(refreshed_functional["status"], "PARTIAL")
        self.assertEqual(
            refreshed_functional["summary"],
            {"samples": 4, "pass": 2, "partial": 2, "fail": 0},
        )
        by_firmware = {
            sample["firmware_id"]: sample
            for sample in refreshed_functional["samples"]
        }
        self.assertEqual(
            by_firmware["2091144466157694978"]["status_reason"],
            "runtime_fixture_gap",
        )
        self.assertEqual(
            by_firmware["1897200000000000358"]["status_reason"],
            "application_frame_not_ready",
        )
        for sample in refreshed_functional["samples"]:
            screenshot = (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-four-functional"
                / sample["frame"]["path"]
            )
            self.assertTrue(screenshot.is_file(), str(screenshot))
        refreshed_sd_functional = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-four-functional-sd-mbr/"
                "evidence.json"
            ).read_text()
        )
        self.assertEqual(refreshed_sd_functional["status"], "PARTIAL")
        self.assertEqual(
            refreshed_sd_functional["summary"],
            {"samples": 4, "pass": 3, "partial": 1, "fail": 0},
        )
        self.assertEqual(
            refreshed_sd_functional["storage_fixture"]["filesystem"],
            "FAT32",
        )
        self.assertEqual(
            refreshed_sd_functional["storage_fixture"]["partition_layout"],
            "MBR",
        )
        sd_by_firmware = {
            sample["firmware_id"]: sample
            for sample in refreshed_sd_functional["samples"]
        }
        self.assertEqual(
            sd_by_firmware["2091144466157694978"]["status"],
            "PASS",
        )
        self.assertEqual(
            sd_by_firmware["2091144466157694978"]["frame"]["sha256"],
            "076f70454f693443987c5153480fac825939b5cdcb6fa9be604c65fc75943d1e",
        )
        self.assertEqual(
            sd_by_firmware["1897200000000000358"]["status_reason"],
            "application_frame_not_ready",
        )
        for sample in refreshed_sd_functional["samples"]:
            screenshot = (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-refreshed-four-functional-sd-mbr"
                / sample["frame"]["path"]
            )
            self.assertTrue(screenshot.is_file(), str(screenshot))
        resume_live = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-public-resume-refresh-live.json"
            ).read_text()
        )
        self.assertEqual(resume_live["status"], "PASS")
        self.assertEqual(resume_live["mode"], "resume-plan-only")
        self.assertFalse(
            resume_live["checks"]["device_session_created"]
        )
        self.assertFalse(resume_live["checks"]["qemu_started"])

    def test_openai_first_boot_nvs_precondition_is_reconciled(self):
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-openai-nvs-precondition.json"
            ).read_text()
        )
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        matrix = (DOCS / "user-firmware-simulation-matrix.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()

        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["functional_status"], "PARTIAL")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(
            evidence["source"]["sha256"],
            "b3597fcabbff57c98618caa8754af84745e9eac35b2868ab3c4cb0935b7c59b3",
        )
        self.assertTrue(evidence["nvs_partition"]["public_binary_erased"])
        self.assertTrue(
            evidence["open_run"]["markers"][
                "wifi:connected with myssid"
            ]
        )
        self.assertTrue(evidence["open_run"]["markers"]["got ip:"])
        self.assertIn(
            "api.openai.com.",
            evidence["open_run"]["pcap"]["dns_queries"],
        )
        self.assertGreater(
            evidence["open_run"]["pcap"]["tcp_443_flows"],
            0,
        )
        self.assertTrue(
            evidence["secure_run"]["markers"][
                "authmode threshold changes from OPEN to WPA2"
            ]
        )
        self.assertTrue(
            evidence["secure_run"]["markers"][
                "wifi:connected with myssid"
            ]
        )
        self.assertTrue(evidence["secure_run"]["markers"]["got ip:"])
        self.assertTrue(
            evidence["secure_run"]["runtime_markers"][
                "EAPOL 4/4 verified; WPA2-PSK ready"
            ]
        )
        self.assertTrue(
            evidence["wrong_password_run"]["runtime_markers"][
                "EAPOL 2/4 MIC mismatch"
            ]
        )
        self.assertFalse(
            evidence["wrong_password_run"]["markers"][
                "wifi:connected with myssid"
            ]
        )
        self.assertFalse(
            evidence["wrong_password_run"]["markers"]["got ip:"]
        )
        self.assertEqual(
            evidence["classification"]["nvs_precondition"],
            "CONFIRMED_EXTERNAL_CONFIGURATION_REQUIRED",
        )
        self.assertTrue(
            evidence["classification"]["qemu_wifi_security"].startswith(
                "PASS:"
            )
        )
        regression = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-s3-wpa2-regression.json"
            ).read_text()
        )
        self.assertEqual(regression["results"]["cases"], 15)
        self.assertEqual(regression["results"]["pass"], 15)
        self.assertFalse(regression["results"]["retry_used"])
        self.assertEqual(
            regression["network_evidence"]["wpa2_correct_password"],
            "PASS",
        )
        self.assertEqual(
            regression["network_evidence"]["wpa2_wrong_password"],
            "PASS_REJECTED_NO_DHCP",
        )
        for text in (status, workstreams, register, api):
            self.assertIn("RUNTIME-05", text)
        self.assertIn("FW-03", backlog)
        self.assertNotIn("cannot associate", matrix)
        self.assertIn("session-isolated NVS", status)
        self.assertIn("nvs_image.py", api)
        self.assertIn("409\nnvs_not_supported", api)
        self.assertIn(
            "qemu-wifi/profile=generic-observe",
            (DOCS / "device-service-api.md").read_text(),
        )
        architecture = (DOCS / "simulator-service-architecture.md").read_text()
        self.assertNotIn(
            "CIDR/domain-set allowlisting and same-guest firmware IPv6",
            architecture,
        )
        self.assertIn("black frame", matrix)
        self.assertTrue(
            any(
                "real OpenAI" in item
                for item in evidence["not_claimed"]
            )
        )

    def test_runtime_model_gap_register_matches_evidence_and_backlog(self):
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        firmware_matrix = (
            DOCS / "user-firmware-simulation-matrix.md"
        ).read_text()
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-cross-vendor-runtime-model-gaps.json"
            ).read_text()
        )
        reset_fix = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-c6-soft-reset-flash-addressing.json"
            ).read_text()
        )
        zigbee = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json"
            ).read_text()
        )
        core2_firmware = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-core2-public-firmware-model-gaps.json"
            ).read_text()
        )
        reset_evidence = reset_fix["device_service_revalidation"]

        gap_codes = {
            gap["code"]
            for sample in evidence["revalidation"]["runtime_model_gaps"]
            for gap in sample["runtime_model_gaps"]
        }
        self.assertEqual(
            gap_codes,
            {
                "zigbee_runtime_not_modeled",
                "c6_chip_id_lost_after_software_reset",
            },
        )
        self.assertEqual(register.count("| 状态 | `OPEN` |"), 1)
        self.assertEqual(
            register.count(
                "| 状态 | `FIXED`（virtual-device validation） |"
            ),
            4,
        )
        self.assertEqual(
            register.count(
                "| 状态 | `FIXED`（virtual-device stock startup） |"
            ),
            1,
        )
        self.assertIn("RUNTIME-01", register)
        self.assertIn("RUNTIME-02", register)
        self.assertIn("RUNTIME-03", register)
        self.assertIn("RUNTIME-04", register)
        self.assertIn("RUNTIME-05", register)
        self.assertIn("RUNTIME-06", register)
        self.assertIn("0029-esp32s3-wpa2-psk-data-plane.patch", register)
        self.assertIn(
            "WPA2-PSK 成对密钥",
            status,
        )
        self.assertIn("`LP_SW_HPSYS`", register)
        self.assertIn(
            "`Invalid chip id. Expected 13 read 12. Bootloader for wrong chip?`",
            register,
        )
        self.assertIn(
            "ef8249ac7930fa51ac5bf03cea52d8de9a59dcbaf2130663ca0d5087a8053744",
            register,
        )
        self.assertIn(
            "cross-vendor-runtime-model-gaps.json",
            register,
        )
        self.assertIn(
            "c6-soft-reset-flash-addressing.json",
            register,
        )
        self.assertIn(
            "c6-zigbee-thread-sim-feasibility.json",
            register,
        )
        self.assertIn("run_feasibility.py", register)
        self.assertEqual(reset_fix["status"], "PASS")
        self.assertEqual(reset_evidence["status"], "PARTIAL")
        self.assertEqual(
            reset_evidence["status_reason"],
            "fatal_after_application_frame",
        )
        self.assertEqual(reset_evidence["runtime_model_gaps"], [])
        self.assertFalse(reset_evidence["invalid_chip_id_observed"])
        self.assertEqual(zigbee["status"], "PARTIAL")
        self.assertEqual(
            zigbee["classification"],
            "zigbee_commissioning_or_mac_ack_not_completed",
        )
        self.assertTrue(zigbee["radio"]["bidirectional"])
        self.assertTrue(zigbee["markers"]["switch_formed_network"])
        self.assertTrue(zigbee["markers"]["light_started_steering"])
        self.assertFalse(zigbee["markers"]["light_joined_network"])
        self.assertFalse(zigbee["markers"]["light_received_on_off"])
        self.assertEqual(core2_firmware["summary"]["pass"], 0)
        self.assertEqual(core2_firmware["summary"]["partial"], 3)
        self.assertEqual(core2_firmware["summary"]["fail"], 0)
        self.assertEqual(
            {
                sample["runtime_model_gap"]["code"]
                for sample in core2_firmware["samples"]
            },
            {
                "core2_pmic_i2c_model_gap",
                "core2_aws_atecc608_model_gap",
            },
        )
        self.assertEqual(
            reset_fix["official_matrix_regression"]["pass"],
            5,
        )
        self.assertIn(
            "case ERASE_4K:",
            (
                ROOT
                / "patches/qemu-esp32c6-uiflow2-adapters/"
                "0001-qemu-c6-m5stack-uiflow2-adapters.patch"
            ).read_text(),
        )
        self.assertIn(
            "memset(&env->pmp_state",
            (
                ROOT
                / "patches/qemu-esp32c6-uiflow2-adapters/"
                "0006-espressif-riscv-reset-pmp.patch"
            ).read_text(),
        )
        for text in (status, workstreams, firmware_matrix):
            self.assertIn("RUNTIME-01", text)
            self.assertIn("RUNTIME-02", text)
            self.assertIn("RUNTIME-03", text)
            self.assertIn("RUNTIME-04", text)
        for text in (status, backlog, workstreams, register, firmware_matrix):
            self.assertIn("RUNTIME-02", text)
            self.assertIn("RUNTIME-03", text)
            self.assertIn("RUNTIME-04", text)
        self.assertNotIn("RUNTIME-01", backlog)
        self.assertNotIn("RUNTIME-05", backlog)
        self.assertIn(
            "runtime-model-gap-register.md",
            status,
        )
        self.assertIn(
            "historical snapshot classified both samples",
            firmware_matrix,
        )
        self.assertIn(
            "不承诺所有 C6 固件兼容",
            backlog,
        )

    def test_webburner_browser_surface_is_wired(self) -> None:
        html = (ROOT / "platform/web/firmware.html").read_text()
        script = (ROOT / "platform/web/firmware.js").read_text()
        uploader = (ROOT / "platform/web/firmware-upload.js").read_text()
        manifest_doc = (DOCS / "firmware-manifest.md").read_text()
        manifest_code = (
            ROOT / "platform/tools/firmware_manifest.py"
        ).read_text()
        index = (ROOT / "platform/web/index.html").read_text()
        sessions = (ROOT / "platform/web/sessions.html").read_text()

        self.assertIn('id="firmwareFile"', html)
        self.assertIn('id="startBtn"', html)
        self.assertIn('id="cancelBtn"', html)
        self.assertIn('id="createSessionBtn"', html)
        self.assertIn('id="requiredCapabilitiesInput"', html)
        self.assertIn('id="optionalCapabilitiesInput"', html)
        self.assertIn("firmware-upload.js", script)
        self.assertIn("requiredCapabilities", script)
        self.assertIn("required_capabilities", uploader)
        self.assertIn("/api/v1/firmware/import", uploader)
        self.assertIn("/api/v1/artifact-uploads", uploader)
        self.assertIn("/platform/web/firmware.html", index)
        self.assertIn("/platform/web/firmware.html", sessions)
        self.assertIn("both required and optional", manifest_code)
        self.assertIn("unsupported_optional_capability", manifest_code)
        self.assertIn(
            "目标设备缺少 optional",
            manifest_doc,
        )
        self.assertIn(
            "secure_boot_config_disabled_but_runtime_enabled",
            manifest_code,
        )
        self.assertIn(
            "flash_encryption_key_purpose_not_observed",
            manifest_code,
        )
        self.assertIn(
            "config 明确 disabled 但 eFuse 指示 enabled",
            manifest_doc,
        )
        security_conflicts = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-security-evidence-conflicts.json"
            ).read_text()
        )
        self.assertEqual(security_conflicts["status"], "PASS")
        self.assertTrue(all(security_conflicts["checks"].values()))
        radio_detection = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-radio-capability-detection.json"
            ).read_text()
        )
        self.assertEqual(radio_detection["status"], "PASS")
        self.assertTrue(all(radio_detection["checks"].values()))
        self.assertIn("CONFIG_BT_CLASSIC_ENABLED", manifest_code)
        self.assertIn("CONFIG_ZB_ENABLED", manifest_code)
        self.assertIn("_web_part_integrity", manifest_code)
        manifest_schema = json.loads(
            (
                ROOT / "platform/tools/firmware_manifest.schema.json"
            ).read_text()
        )
        self.assertIn(
            "declared_integrity",
            manifest_schema["properties"]["artifact"]["properties"]["segments"][
                "items"
            ]["properties"],
        )
        integrity = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-webburner-part-integrity.json"
            ).read_text()
        )
        self.assertEqual(integrity["status"], "PASS")
        self.assertTrue(all(integrity["checks"].values()))
        self.assertEqual(integrity["positive"]["verified_segments"], 3)
        self.assertEqual(
            integrity["positive"]["declared_integrity"]["algorithms"],
            ["size", "sha256", "sha1", "md5"],
        )
        self.assertIn(
            "source authenticity or publisher identity",
            integrity["not_claimed"],
        )
        self.assertIn(
            "## WebBurner 分段完整性",
            manifest_doc,
        )

    def test_secure_boot_v2_image_evidence_does_not_overclaim(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-26-secure-boot-image-manifest-policy-v2.json"
            ).read_text()
        )
        self.assertEqual(evidence["date"], "2026-10-26")
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(
            evidence["validation"],
            "static secure-boot image validation",
        )
        self.assertTrue(evidence["input_assets_unchanged"])
        self.assertEqual(len(evidence["checks"]), 26)
        self.assertTrue(all(evidence["checks"].values()))
        for name, relative in {
            "runner": (
                "tests/firmware/secure_boot_image/run_test.py"
            ),
            "test_image_builder": (
                "platform/tests/test_firmware_analysis.py"
            ),
            "firmware_analysis": (
                "platform/tools/firmware_analysis.py"
            ),
            "firmware_manifest": (
                "platform/tools/firmware_manifest.py"
            ),
            "manifest_schema": (
                "platform/tools/firmware_manifest.schema.json"
            ),
        }.items():
            self._assert_recorded_tool_hash(
                "secure-boot-recorded-image-20261026-manifest-policy-v2",
                relative,
                evidence["tool_hashes"][name],
            )
        signed = evidence["security_images"]["signed"]
        self.assertEqual(signed["status"], "signed-image-observed")
        self.assertEqual(
            signed["signature_authenticity"],
            "not-verified",
        )
        self.assertEqual(signed["trust_root"], "not-verified")
        self.assertEqual(
            {
                row["label"] for row in signed["images"]
            },
            {"bootloader", "factory"},
        )
        self.assertEqual(
            evidence["security_images"]["tampered"]["status"],
            "invalid",
        )
        self.assertEqual(
            evidence["security_images"]["unsigned"]["status"],
            "not-found",
        )
        self.assertTrue(
            all(
                block["signature_math"] == "valid"
                for image in evidence["security_images"]["signed"][
                    "images"
                ]
                for block in image["blocks"]
            )
        )

        self.assertEqual(
            {
                block["scheme"]
                for block in evidence["security_images"]["ecdsa_p256"][
                    "images"
                ][0]["blocks"]
            },
            {"ecdsa-p256-sha256"},
        )
        self.assertEqual(
            {
                block["scheme"]
                for block in evidence["security_images"]["ecdsa_p192"][
                    "images"
                ][0]["blocks"]
            },
            {"ecdsa-p192-sha256"},
        )
        self.assertEqual(
            {
                block["scheme"]
                for block in evidence["security_images"]["ecdsa_p384"][
                    "images"
                ][0]["blocks"]
            },
            {"ecdsa-p384-sha384"},
        )
        self.assertEqual(
            evidence["security_images"]["bad_signature"]["status"],
            "invalid",
        )
        self.assertEqual(
            evidence["security_images"]["bad_ecdsa_signature"]["status"],
            "invalid",
        )
        self.assertIn(
            "embedded public key trust against live eFuse",
            evidence["not_claimed"],
        )
        trust_comparisons = evidence["efuse_trust_comparisons"]
        self.assertEqual(
            trust_comparisons["match"]["status"],
            "not-verified",
        )
        self.assertEqual(
            trust_comparisons["match"]["comparison"],
            "match-unverified-source",
        )
        self.assertEqual(
            trust_comparisons["mismatch"]["comparison"],
            "mismatch-unverified-source",
        )
        self.assertEqual(
            trust_comparisons["digest_unavailable"]["comparison"],
            "efuse-key-digest-unavailable",
        )
        anti_rollback = evidence["anti_rollback_comparisons"]
        self.assertEqual(
            anti_rollback["below"]["status"],
            "not-verified",
        )
        self.assertEqual(
            anti_rollback["below"]["comparison"],
            "image-below-efuse-unverified-source",
        )
        self.assertEqual(
            anti_rollback["satisfied"]["comparison"],
            "image-satisfies-efuse-unverified-source",
        )
        self.assertEqual(
            anti_rollback["secure_version_unavailable"]["comparison"],
            "efuse-secure-version-unavailable",
        )

        manifest = (DOCS / "firmware-manifest.md").read_text()
        for text in (
            "Secure Boot v2 signature sector",
            "secure_boot_v2_image_signature_authenticity_unverified",
            "secure_boot_v2_image_public_key_digest_mismatch",
            "secure_boot_image_secure_version_below_efuse",
            "secure_boot_v2_image_signature_not_observed",
            "secure_boot_v2_image_signature_invalid",
            "signature_authenticity=not-verified",
            "security.trust_root.status",
            "security.anti_rollback",
            "match-unverified-source",
            "mismatch-unverified-source",
            "image-below-efuse-unverified-source",
        ):
            self.assertIn(text, manifest)
        schema = json.loads(
            (
                ROOT
                / "platform/tools/firmware_manifest.schema.json"
            ).read_text()
        )
        self.assertIn(
            "secure_boot_image",
            schema["properties"]["security"]["properties"],
        )
        self.assertEqual(
            schema["properties"]["security"]["properties"]["trust_root"][
                "properties"
            ]["status"]["const"],
            "not-verified",
        )
        self.assertEqual(
            schema["properties"]["security"]["properties"]["anti_rollback"][
                "properties"
            ]["status"]["const"],
            "not-verified",
        )
        code = (
            ROOT / "platform/tools/firmware_manifest.py"
        ).read_text()
        for warning in (
            "secure_boot_v2_image_signature_authenticity_unverified",
            "secure_boot_v2_image_public_key_digest_mismatch",
            "secure_boot_image_secure_version_below_efuse",
            "secure_boot_v2_image_signature_not_observed",
            "secure_boot_v2_image_signature_invalid",
        ):
            self.assertIn(warning, code)

    def test_security_evidence_cannot_be_understated(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-26-"
                "firmware-security-preflight-fail-closed.json"
            ).read_text()
        )
        self.assertEqual(
            evidence["kind"],
            "m5stack-firmware-security-preflight",
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertTrue(all(evidence["checks"].values()))
        cases = evidence["cases"]
        self.assertEqual(cases["baseline"]["status"], "PASS")
        for name in (
            "aggregate_secure_boot",
            "understated_secure_boot_config",
            "understated_signed_image",
            "invalid_signed_image",
            "understated_flash_encryption_config",
            "understated_efuse_summary",
        ):
            self.assertEqual(cases[name]["status"], "REJECTED", name)
        manifest_doc = (DOCS / "firmware-manifest.md").read_text()
        for code in (
            "secure_boot_config_not_modeled",
            "secure_boot_image_not_modeled",
            "secure_boot_image_invalid",
            "secure_boot_efuse_not_modeled",
            "flash_encryption_config_not_modeled",
            "flash_encryption_efuse_not_modeled",
        ):
            self.assertIn(code, manifest_doc)
        api = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        self.assertIn("cannot\nhide secure boot or Flash Encryption", api)
        self.assertIn("aggregate security fields", openapi)


if __name__ == "__main__":
    unittest.main(verbosity=2)
