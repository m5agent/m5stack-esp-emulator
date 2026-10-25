#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import unittest

from _docs_contract_support import DocsContractBase, ROOT, DOCS


class DocsCore2RuntimeContractTests(DocsContractBase):
    def test_core2_axp_i2c_trace_classifies_the_first_failure(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-core2-axp-i2c-trace.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["runtime"]["pmic"], "axp2101")
        self.assertFalse(evidence["runtime"]["address_filter_effective"])
        self.assertEqual(evidence["observations"]["chip_id_value"], "0x4a")
        self.assertTrue(evidence["observations"]["successful_axp_start"])
        self.assertFalse(
            evidence["observations"][
                "subsequent_axp_bus_transaction_observed"
            ]
        )
        self.assertEqual(
            evidence["observations"]["next_controller_transaction"]["address"],
            "0x51",
        )
        self.assertEqual(
            evidence["observations"]["next_controller_transaction"][
                "start_rc"
            ],
            1,
        )
        self.assertEqual(
            evidence["classification"]["code"],
            "i2c_driver_or_bus_handoff_gap",
        )
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        self.assertIn("chip id `0x4a`", register)
        self.assertIn("controller-to-physical-bus routing", register)
        self.assertIn("address `0x51`", register)

    def test_core2_shared_board_i2c_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-core2-shared-board-i2c.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertEqual(
            evidence["firmware"]["source_sha256"],
            "18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a",
        )
        self.assertEqual(evidence["before_fix"]["rtc_start"]["start_rc"], 1)
        self.assertTrue(evidence["after_fix"]["i2c_bus_error_present"] is False)
        self.assertEqual(evidence["after_fix"]["rtc_starts"]["write_ack"], 15)
        self.assertEqual(evidence["after_fix"]["rtc_starts"]["read_ack"], 4)
        self.assertEqual(evidence["regression"]["cases_passed"], 6)
        self.assertEqual(evidence["regression"]["checks_passed"], 24)
        self.assertFalse(evidence["regression"]["retry_used"])
        self.assertEqual(evidence["checks"]["legacy_axp_rtc_ack"], "PASS")
        self.assertEqual(evidence["checks"]["nonempty_application_frame"], "FAIL")
        self.assertIn("interrupt_wdt_after_peripheral_initialization", json.dumps(evidence))

        patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0031-core2-shared-board-i2c.patch"
        ).read_text()
        self.assertIn("[esp32-i2c] transaction controller=%s bus=%s", patch)
        self.assertIn("esp32_i2c_set_bus(DEVICE(&s->i2c[0]), bus0)", patch)
        self.assertIn("esp32_i2c_set_bus(DEVICE(&s->i2c[1]), bus0)", patch)
        self.assertIn(
            "qdev_realize_and_unref(d, (BusState *)bus0, &error_fatal)",
            patch,
        )

        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        matrix = (DOCS / "user-firmware-simulation-matrix.md").read_text()
        firmware_readme = (ROOT / "tests/firmware/README.md").read_text()
        for text in (status, backlog, register, workstreams, matrix):
            self.assertIn("shared", text.lower())
            self.assertIn("WDT", text)
        for text in (status, backlog, register, workstreams):
            self.assertIn("flash-cache", text)
            self.assertIn("DPORT", text)
            self.assertIn("假设", text)
        self.assertIn("后初始化 WDT", workstreams)
        self.assertIn("0031", matrix)
        self.assertIn("Core2FactoryTest", matrix)
        self.assertIn("rerun is `NOT RUN`", matrix)
        self.assertIn("interrupt-WDT", firmware_readme)
        self.assertIn("I2C bus error (19)", register)
        self.assertIn("nonempty_application_frame", evidence["checks"])

    def test_core2_wdt_timing_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-25-core2-wdt-timing.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertEqual(
            evidence["firmware"]["embedded_build"],
            {
                "micropython": "a3bd196ef-dirty",
                "micropython_version": "1.12.0",
                "esp_idf": "3.4.0",
                "compiled": "2026-07-28T16:15:09",
            },
        )
        concurrency = evidence["default_concurrency"]
        self.assertEqual(concurrency["attempts"], 8)
        self.assertEqual(concurrency["interrupt_wdt_failures"], 5)
        self.assertEqual(concurrency["no_wdt"], 3)
        self.assertEqual(
            evidence["single_session_controls"]["default_no_trace"][
                "observation_seconds"
            ],
            285,
        )
        accelerator_failures = {
            item["mode"]: (
                item["hardware_tg_wdt"],
                item["interrupt_wdt"],
            )
            for item in evidence["accelerator_controls"]
        }
        self.assertEqual(
            accelerator_failures["tcg,thread=single,tb-size=128"],
            (4, 0),
        )
        self.assertEqual(
            accelerator_failures["icount shift=0,align=off,sleep=off"],
            (4, 0),
        )
        trace = evidence["icount_wdt_trace"]
        self.assertEqual(trace["feed_to_interrupt_ns"], 800_000_000)
        self.assertEqual(trace["interrupt_to_reset_ns"], 1_600_000_000)
        self.assertEqual(
            evidence["checks"]["accelerator_override_fix"],
            "FAIL",
        )

        patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0032-esp32-timg-wdt-trace.patch"
        ).read_text()
        self.assertIn('getenv("M5SW_TIMG_TRACE")', patch)
        self.assertIn("WDTFEED", patch)
        self.assertIn("WDTCONFIG0", patch)
        self.assertIn("timeout now=", patch)

        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        firmware_readme = (ROOT / "tests/firmware/README.md").read_text()
        qemu_matrix = (
            DOCS / "qemu-device-adaptation-matrix.md"
        ).read_text()
        uiflow_index = (ROOT / "tests/uiflow2/README.md").read_text()
        unified_core2 = (
            ROOT / "tests/uiflow2/unified_core2/README.md"
        ).read_text()
        for text in (status, backlog, register, workstreams, ledger):
            self.assertIn("TIMG", text)
        self.assertIn("flash-cache/IPC/DPORT", qemu_matrix)
        self.assertIn("历史诊断选项", uiflow_index)
        self.assertIn("diagnostic evidence", unified_core2)
        self.assertNotIn(
            "Repeated-lease stability is currently",
            unified_core2,
        )
        self.assertIn("宿主调度", status)
        self.assertIn("timing-sensitive", register)
        self.assertIn("5/8", ledger)
        self.assertIn("M5SW_TIMG_TRACE", firmware_readme)
        self.assertIn(
            "0032-esp32-timg-wdt-trace.patch",
            (
                ROOT / "patches/qemu-m5stack-peripherals/README.md"
            ).read_text(),
        )

    def test_core2_flash_ipc_probe_reconciles_timer_and_legacy_boundaries(
        self,
    ) -> None:
        probe_root = ROOT / "tests/firmware/core2_flash_ipc"
        evidence = json.loads(
            (
                probe_root
                / "evidence-2026-10-26-core2-flash-ipc-wdt.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PARTIAL")
        current = evidence["current_runtime"]
        self.assertEqual(current["attempts"], 5)
        self.assertEqual(current["passed"], 1)
        self.assertEqual(current["interrupt_wdt"], 4)
        self.assertEqual(current["spinlock_owner_assert"], 0)
        self.assertEqual(current["read_start_observed"], 5)
        portable = evidence["portable_runtime_control"]
        self.assertEqual(portable["attempts"], 15)
        self.assertEqual(portable["passed"], 13)
        self.assertEqual(portable["interrupt_wdt"], 2)
        self.assertEqual(portable["spinlock_owner_assert"], 0)
        combined = evidence["combined_result"]
        self.assertEqual(combined["attempts"], 20)
        self.assertEqual(combined["passed"], 14)
        self.assertEqual(combined["interrupt_wdt"], 6)
        self.assertEqual(combined["spinlock_owner_assert"], 0)
        self.assertIn(
            "4096-byte CPU1 task stack",
            evidence["historical_correction"]["observation"],
        )
        equal_deadline = json.loads(
            (
                probe_root
                / "evidence-2026-10-26-core2-ccompare-equal-deadline.json"
            ).read_text()
        )
        self.assertEqual(
            equal_deadline["status"],
            "FIXED_FOR_MINIMAL_PROBE_LEGACY_OPEN",
        )
        self.assertEqual(equal_deadline["post_fix"]["attempts"], 40)
        self.assertEqual(equal_deadline["post_fix"]["passed"], 40)
        self.assertEqual(equal_deadline["post_fix"]["interrupt_wdt"], 0)
        self.assertFalse(
            equal_deadline["legacy_uiflow"]["unique_application_frame"]
        )
        self.assertEqual(
            equal_deadline["legacy_uiflow"]["reset_cpu_pc"],
            "0x0",
        )

        runner_path = probe_root / "run_test.py"
        spec = importlib.util.spec_from_file_location(
            "core2_flash_ipc_runner",
            runner_path,
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        module.validate_artifact_hashes(
            module.EXPECTED_IMAGE_SHA256,
            module.EXPECTED_ELF_SHA256,
            expected_image_sha256=module.EXPECTED_IMAGE_SHA256,
            expected_elf_sha256=module.EXPECTED_ELF_SHA256,
        )
        with self.assertRaisesRegex(ValueError, "image SHA256 mismatch"):
            module.validate_artifact_hashes(
                "0" * 64,
                module.EXPECTED_ELF_SHA256,
                expected_image_sha256=module.EXPECTED_IMAGE_SHA256,
                expected_elf_sha256=module.EXPECTED_ELF_SHA256,
            )
        passed = module.classify_serial(
            "CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd\n"
            "CORE2_FLASH_IPC_READY core=1 prid=0x0000abab\n"
            "CORE2_FLASH_IPC_READ_START core=1\n"
            "CORE2_FLASH_IPC_WORKER_PASS core=1\n"
            "CORE2_FLASH_IPC_PASS\n"
        )
        self.assertEqual(passed["status"], "PASS")
        self.assertTrue(passed["flash_read_started"])
        incomplete = module.classify_serial(
            "CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd\n"
            "CORE2_FLASH_IPC_READY core=1 prid=0x0000abab\n"
            "CORE2_FLASH_IPC_READ_START core=1\n"
            "CORE2_FLASH_IPC_PROGRESS core=1 iteration=50\n"
        )
        self.assertEqual(incomplete["status"], "INCOMPLETE")
        self.assertTrue(incomplete["flash_read_started"])
        spinlock_after_start = module.classify_serial(
            "CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd\n"
            "CORE2_FLASH_IPC_READY core=1 prid=0x0000abab\n"
            "CORE2_FLASH_IPC_READ_START core=1\n"
            "assert failed: spinlock_release spinlock.h:190 "
            "(core_owner_id == lock->owner)\n"
        )
        self.assertEqual(
            spinlock_after_start["status"],
            "REPRODUCED_AFTER_READ_START",
        )
        self.assertTrue(spinlock_after_start["flash_read_started"])
        cross_reboot = module.classify_serial(
            "Guru Meditation Error: Core  0 panic'ed "
            "(Interrupt wdt timeout on CPU0).\n"
            "Rebooting...\n"
            "CORE2_FLASH_IPC_MAIN core=0 prid=0x0000cdcd\n"
            "CORE2_FLASH_IPC_READY core=1 prid=0x0000abab\n"
            "assert failed: spinlock_release spinlock.h:190 "
            "(core_owner_id == lock->owner)\n"
        )
        self.assertEqual(cross_reboot["status"], "INTERRUPT_WDT")
        self.assertTrue(cross_reboot["interrupt_wdt_in_first_boot"])
        self.assertTrue(cross_reboot["reboot_observed"])

        source = (probe_root / "main/app_main.c").read_text()
        self.assertIn("CORE2_FLASH_IPC_READ_START", source)
        self.assertIn("read_raw_prid", source)
        self.assertIn("static uint8_t flash_buffer", source)
        self.assertIn("vTaskDelay", source)
        readme = (probe_root / "README.md").read_text()
        self.assertIn("stack overflow", readme)
        self.assertIn("interrupt-WDT", readme)
        self.assertIn("READ_START", readme)
        self.assertIn("CCOMPARE == CCOUNT", readme)
        self.assertIn(".work/core2-flash-ipc-16m-final.bin", readme)
        self.assertNotIn("--image .work/core2-flash-ipc-16m.bin", readme)

        deadline_patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0034-xtensa-ccompare-equal-deadline.patch"
        ).read_text()
        self.assertIn(
            "uint32_t delta = env->sregs[CCOMPARE + i] - "
            "env->sregs[CCOUNT];",
            deadline_patch,
        )
        self.assertIn("dcc = delta ? delta : 1;", deadline_patch)
        self.assertNotIn("M5SW_XTENSA_IRQ", deadline_patch)

        for path in (
            DOCS / "project-status.md",
            DOCS / "project-backlog.md",
            DOCS / "runtime-model-gap-register.md",
            DOCS / "engineering-handoff.md",
            DOCS / "workstreams.md",
            DOCS / "validation-ledger.md",
        ):
            text = path.read_text()
            self.assertIn("interrupt-WDT", text)
            self.assertIn("READ_START", text)
        for path in (
            DOCS / "project-status.md",
            DOCS / "project-backlog.md",
            DOCS / "runtime-model-gap-register.md",
            DOCS / "engineering-handoff.md",
            DOCS / "workstreams.md",
        ):
            text = path.read_text()
            self.assertIn("CCOMPARE", text)
            self.assertIn("legacy", text.lower())
        for path in (
            ROOT / "README.md",
            DOCS / "project-status.md",
            DOCS / "project-backlog.md",
            DOCS / "engineering-handoff.md",
            DOCS / "workstreams.md",
            DOCS / "qemu-device-adaptation-matrix.md",
            DOCS / "code-map.md",
        ):
            text = path.read_text()
            for volatile_count in (
                "14 PASS",
                "14/20",
                "6/20",
                "6 次 interrupt-WDT",
            ):
                self.assertNotIn(volatile_count, text, path.relative_to(ROOT))
        for path in (
            DOCS / "runtime-model-gap-register.md",
            DOCS / "validation-ledger.md",
        ):
            text = path.read_text()
            self.assertIn("CCOMPARE == CCOUNT", text)
            self.assertIn("0034", text)
        self.assertIn("40/40", (DOCS / "validation-ledger.md").read_text())
        history = (DOCS / "core2-cache-panic-investigation.md").read_text()
        self.assertIn("2026-10-26 update", history)
        self.assertIn("stack overflow", history)
        self.assertIn("idle", history)

    def test_core2_qio_wdt_mask_and_crosscore_boundaries_are_explicit(
        self,
    ) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-26-core2-qio-crosscore-diagnostic.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "DIAGNOSTIC_ONLY")
        self.assertFalse(evidence["runtime"]["artifact_bound"])
        qio = evidence["qio_bulk_read_diagnostic"]
        self.assertEqual(qio["sample_transactions"], 512)
        self.assertEqual(qio["mismatch_count"], 0)
        self.assertIn(
            "MICROPYTHON",
            " ".join(
                marker.upper()
                for marker in qio["temporary_path_result"]["serial_markers"]
            ),
        )
        mask = evidence["wdt_int_ena_semantics"]
        self.assertEqual(mask["observed_register_state"]["INT_ENA"], "0x00000000")
        self.assertEqual(mask["observed_register_state"]["INT_RAW"], "0x00000004")
        self.assertIn("not the root cause", mask["classification"])
        crosscore = evidence["crosscore_stall_diagnostic"]
        self.assertEqual(crosscore["cpu0_wait_address"], "0x3ffc7ec8")
        self.assertIn("spi_flash_op_block_func", crosscore["symbol_hint"])
        self.assertIn(
            "DPORT safe-read",
            crosscore["symbol_hint"],
        )

        patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0035-esp32-timg-wdt-int-ena.patch"
        ).read_text()
        self.assertIn("if (s->int_ena & mask) {", patch)
        self.assertIn(
            "-            if (true) { /* should be checking "
            "s->int_ena & mask",
            patch,
        )
        self.assertIn(
            "+            if (s->int_ena & mask) {",
            patch,
        )
        patches_readme = (
            ROOT / "patches/qemu-m5stack-peripherals/README.md"
        ).read_text()
        self.assertIn("0035-esp32-timg-wdt-int-ena.patch", patches_readme)
        self.assertIn("INT_RAW & INT_ENA", patches_readme)

        ssi_evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-26-core2-ssi-transfer-buf.json"
            ).read_text()
        )
        self.assertEqual(ssi_evidence["status"], "PARTIAL")
        self.assertEqual(
            ssi_evidence["data_plane_equivalence"]["batches"],
            512,
        )
        self.assertEqual(
            ssi_evidence["data_plane_equivalence"]["mismatch_count"],
            0,
        )
        self.assertEqual(ssi_evidence["regression"]["cases_passed"], 6)
        self.assertEqual(ssi_evidence["regression"]["checks_passed"], 24)
        self.assertFalse(ssi_evidence["regression"]["retry_used"])
        self.assertEqual(
            ssi_evidence["regression"]["summary_sha256"],
            "62d7d42568be7758f51f7b61d960b3cadcd02940f4746f960078625afa47f450",
        )
        full_matrix = ssi_evidence["full_matrix_regression"]
        self.assertEqual(full_matrix["cases_passed"], 67)
        self.assertEqual(full_matrix["cases_failed"], 0)
        self.assertEqual(full_matrix["checks_passed"], 274)
        self.assertEqual(full_matrix["checks_failed"], 0)
        self.assertFalse(full_matrix["retry_used"])
        self.assertEqual(
            full_matrix["summary_sha256"],
            "44b65976d60589662e04454c4680cec90c8137a5934cece9bb371099297b3455",
        )
        suite = ssi_evidence["validation_suite"]
        self.assertEqual(suite["platform_unittest"]["passed"], 501)
        self.assertEqual(suite["docs_contract"]["passed"], 41)
        self.assertEqual(suite["qemu_profile_contract"]["passed"], 19)
        self.assertEqual(
            ssi_evidence["checks"]["legacy_normal_watchdog_boot"],
            "FAIL",
        )
        self.assertEqual(
            ssi_evidence["checks"]["full_uiflow2_device_matrix"],
            "PASS",
        )
        self.assertEqual(
            ssi_evidence["checks"]["platform_static_and_contract_checks"],
            "PASS",
        )
        self.assertEqual(
            ssi_evidence["checks"]["crosscore_handshake_completes"],
            "PASS",
        )
        ssi_patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0036-ssi-transfer-buf.patch"
        ).read_text()
        self.assertIn("ssi_transfer_buf", ssi_patch)
        self.assertIn("m25p80_transfer_buf", ssi_patch)
        self.assertIn("STATE_READ", ssi_patch)
        self.assertNotIn("blk_pread", ssi_patch)
        self.assertNotIn("M5SW_ESP32_SPI_DIRECT_READ", ssi_patch)
        self.assertIn("0036-ssi-transfer-buf.patch", patches_readme)

        for path in (
            DOCS / "project-status.md",
            DOCS / "project-backlog.md",
            DOCS / "runtime-model-gap-register.md",
            DOCS / "engineering-handoff.md",
            DOCS / "workstreams.md",
            DOCS / "validation-ledger.md",
        ):
            text = path.read_text()
            self.assertIn("0035", text, path.relative_to(ROOT))
            self.assertIn("QIO", text, path.relative_to(ROOT))
            self.assertIn("cross-core", text, path.relative_to(ROOT))
            self.assertIn("0036", text, path.relative_to(ROOT))
            self.assertIn("0037", text, path.relative_to(ROOT))
        for path in (
            ROOT / "README.md",
            DOCS / "qemu-device-adaptation-matrix.md",
            DOCS / "user-firmware-simulation-matrix.md",
            DOCS / "code-map.md",
        ):
            text = path.read_text()
            self.assertIn("QIO", text, path.relative_to(ROOT))
            self.assertIn("cross-core", text, path.relative_to(ROOT))
            self.assertIn("0037", text, path.relative_to(ROOT))
        history = (DOCS / "core2-cache-panic-investigation.md").read_text()
        self.assertIn("2026-10-26 QIO and cross-core follow-up", history)
        self.assertIn("512 sampled transactions", history)

    def test_core2_reconnect_evidence_is_reconciled(self):
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        adaptation_matrix = (
            DOCS / "qemu-device-adaptation-matrix.md"
        ).read_text()
        core2_backend = (DOCS / "core2-native-hci-backend.md").read_text()
        runtime_contract = (DOCS / "unified-device-runtime.md").read_text()
        project_snapshot = (DOCS / "project-snapshot.md").read_text()
        catalog_source_text = (
            ROOT / "devices/catalog.source.json"
        ).read_text()
        catalog_source = json.loads(catalog_source_text)
        generated_catalog = json.loads(
            (ROOT / "devices/catalog.json").read_text()
        )
        qemu_profiles_text = (
            ROOT / "platform/qemu/profiles.json"
        ).read_text()
        qemu_profiles = json.loads(qemu_profiles_text)
        service = (ROOT / "platform/tools/device_service.py").read_text()
        peer = (ROOT / "platform/tools/ble_probe.py").read_text()
        limits = (
            ROOT / "platform/tools/ble_runtime_limits.py"
        ).read_text()
        openapi = (
            DOCS / "device-service.openapi.yaml"
        ).read_text()
        runner = (
            ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"
        ).read_text()
        service_tests = (
            ROOT / "platform/tests/test_device_service.py"
        ).read_text()
        evidence = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect30-3x.json"
            ).read_text()
        )
        sixty_evidence = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect60-3x.json"
            ).read_text()
        )
        hundred_twenty_evidence = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect120-3x.json"
            ).read_text()
        )
        hold600_evidence = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-active-ble-hold600-2x.json"
            ).read_text()
        )
        resolved_psram = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-core2-native-hci-resolved-psram.json"
            ).read_text()
        )
        artifact_bound = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json"
            ).read_text()
        )
        tb128_hold120 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-tb128-hold120-1x.json"
            ).read_text()
        )
        tb128_hold7200 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-hci4-active-ble-hold7200-"
                "tb128-artifact-bound-1x.json"
            ).read_text()
        )
        readiness_failure = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-hci4-reconnect121-"
                "readiness-timeout-1x.json"
            ).read_text()
        )
        reconnect_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-hci4-reconnect121-1x.json"
            ).read_text()
        )
        accelerator_failure = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-hci4-reconnect121-"
                "accelerator-sampling-fail-1x.json"
            ).read_text()
        )
        reconnect_3x = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-hci4-reconnect121-3x.json"
            ).read_text()
        )
        active_stop = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-active-stop-recovery-3x.json"
            ).read_text()
        )

        self.assertIn("3/3 PASS", ledger)
        self.assertIn("Core2", project_snapshot)
        self.assertIn("physical cache/PSRAM", project_snapshot)
        self.assertIn("one Device Service lease", runtime_contract)
        self.assertIn("one guest instance", runtime_contract)
        self.assertIn("Core2 三 lease 121 轮", ledger)
        self.assertNotIn("3 个独立 lease 各 120 轮", backlog)
        self.assertIn("`CORE2-02`", workstreams)
        self.assertIn("core2-native-hci", adaptation_matrix)
        self.assertIn("core2-native-vhci", adaptation_matrix)
        self.assertIn(
            "| `CORE2-02` 30-cycle extension | `PASS` |",
            core2_backend,
        )
        self.assertIn(
            "| `CORE2-02` 120-cycle extension | `PASS` |",
            core2_backend,
        )
        self.assertIn("Current profiles", runtime_contract)
        self.assertIn("counts and blockers", runtime_contract)
        self.assertNotIn(
            "| `CORE2-02` 30-cycle extension | `NOT RUN` |",
            core2_backend,
        )
        self.assertNotIn("扩大 API 轮次上限", workstreams)

        self.assertIn("MAX_BLE_RECONNECT_CYCLES = 121", limits)
        self.assertIn("MAX_BLE_HOLD_SECONDS = 7200", limits)
        self.assertIn(
            "MAX_BLE_LINGER_SECONDS = MAX_BLE_HOLD_SECONDS + 60",
            limits,
        )
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", service)
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", peer)
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", runner)
        self.assertIn("reconnect_workload_timeout_seconds", limits)
        self.assertIn("reconnect_workload_timeout_seconds", service)
        self.assertIn("reconnect_workload_timeout_seconds", runner)
        self.assertIn(
            "qemu_accelerator = process_qemu_accelerator(",
            runner.split("phase = \"wait_network\"", 1)[0],
        )
        self.assertIn("core2_accel_args", service)
        self.assertIn('"bounded_tcg_cache"', runner)
        self.assertIn('"tool_hashes"', runner)
        self.assertIn("tb-size={CORE2_TCG_TB_SIZE_MIB}", qemu_accel := (
            ROOT / "platform/tools/qemu_accel.py"
        ).read_text())
        self.assertIn("CORE2_TCG_TB_SIZE_MIB = 128", qemu_accel)
        self.assertIn("tcg,thread=single,tb-size=128", ledger)
        self.assertNotIn("323536", workstreams)
        self.assertIn('"ble_reconnect_cycles": 121', service_tests)
        reconnect_schema = openapi.split(
            "ble_reconnect_cycles:",
            1,
        )[1].split("ble_reconnect_delay_seconds:", 1)[0]
        self.assertIn("maximum: 121", reconnect_schema)
        linger_schema = openapi.split(
            "ble_linger_seconds:",
            1,
        )[1].split("ble_reconnect_cycles:", 1)[0]
        self.assertIn("maximum: 7260", linger_schema)
        platform_readme = (ROOT / "platform/README.md").read_text()
        device_readme = (
            ROOT / "devices/esp32-lx6/core2/README.md"
        ).read_text()
        self.assertIn("reconnect contract remains 1-121 with 122 rejected", catalog_source_text)
        self.assertIn(
            "Three independent leases complete 121 reconnect cycles",
            qemu_profiles_text,
        )
        self.assertIn("validation-ledger.md", platform_readme)
        self.assertIn("reconnect", platform_readme)
        self.assertIn("docs/project-status.md", device_readme)
        self.assertIn("docs/validation-ledger.md", device_readme)
        self.assertIn("docs/project-backlog.md", device_readme)
        self.assertIn("docs/code-map.md", device_readme)
        self.assertNotIn("323536", device_readme)
        self.assertNotIn("250880", device_readme)
        self.assertNotIn("29 轮", device_readme)
        self.assertNotIn("121/121", device_readme)
        self.assertNotIn("最终两小时限容复测尚未完成", device_readme)
        for stale in (
            "当前参数上限为 120 并拒绝 121",
            "The accepted reconnect range is 1-120",
            "接受 `1–120` 轮",
        ):
            self.assertNotIn(stale, catalog_source_text)
            self.assertNotIn(stale, qemu_profiles_text)
            self.assertNotIn(stale, platform_readme)
            self.assertNotIn(stale, device_readme)
        self.assertEqual(resolved_psram["cli_memory_mib"], 0)
        self.assertEqual(resolved_psram["resolved_memory_mib"], 4)
        self.assertTrue(resolved_psram["has_psram"])
        self.assertIn(
            "not physical PSRAM or cache timing validation",
            resolved_psram["scope"],
        )
        self.assertEqual(readiness_failure["status"], "FAIL")
        self.assertEqual(readiness_failure["ble_reconnect_cycles"], 121)
        self.assertEqual(
            readiness_failure["observed"]["ble_cycles_passed"],
            29,
        )
        self.assertTrue(
            readiness_failure["observed"]["ble_cycle_30_started"]
        )
        self.assertFalse(readiness_failure["observed"]["guest_panic"])
        self.assertEqual(
            readiness_failure["root_cause"]["classification"],
            "readiness_budget_mismatch_not_controller_failure",
        )
        self.assertEqual(
            readiness_failure["resolution"][
                "effective_timeout_seconds_for_121_cycle_2_second_delay"
            ],
            1028,
        )
        self.assertEqual(reconnect_pass["status"], "PASS")
        self.assertEqual(reconnect_pass["attempts_passed"], 1)
        self.assertEqual(reconnect_pass["ble_reconnect_cycles"], 121)
        self.assertEqual(
            reconnect_pass["observed"]["qemu_accelerator"],
            "tcg,thread=single,tb-size=128",
        )
        self.assertEqual(reconnect_pass["observed"]["hli_posts"], 3405)
        self.assertEqual(reconnect_pass["observed"]["hli_consumed"], 3405)
        self.assertEqual(reconnect_pass["observed"]["trace_gap_adv_start"], 121)
        self.assertFalse(reconnect_pass["observed"]["guest_panic"])
        self.assertEqual(accelerator_failure["functional_status"], "PASS")
        self.assertEqual(
            accelerator_failure["observed"]["ble_cycles_passed"],
            121,
        )
        self.assertIsNone(
            accelerator_failure["observed"]["qemu_accelerator"]
        )
        self.assertEqual(
            accelerator_failure["root_cause"]["classification"],
            "evidence_sampling_bug_not_guest_controller_failure",
        )
        self.assertEqual(reconnect_3x["status"], "PASS")
        self.assertEqual(reconnect_3x["lease_count"], 3)
        self.assertEqual(reconnect_3x["leases_passed"], 3)
        self.assertEqual(reconnect_3x["ble_reconnect_cycles_per_lease"], 121)
        for field in (
            "firmware_equal_across_runs",
            "elf_equal_across_runs",
            "qemu_equal_across_runs",
            "tool_hashes_equal_across_runs",
        ):
            self.assertTrue(reconnect_3x["identity_checks"][field])
        self.assertEqual(
            reconnect_3x["identity_checks"]["input_asset_drift"],
            {},
        )
        for lease in reconnect_3x["leases"]:
            self.assertEqual(lease["hli_posts"], 3405)
            self.assertEqual(lease["hli_consumed"], 3405)
            self.assertEqual(lease["hli_errors"], 0)
            self.assertEqual(lease["panic_count"], 0)

        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["attempts_requested"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertEqual(evidence["attempts_failed"], 0)
        self.assertEqual(evidence["ble_reconnect_cycles"], 30)
        self.assertFalse(evidence["boundary"]["gdb_bridge"])
        for run in evidence["runs"]:
            health = run["native_hci_health"]
            self.assertEqual(health["hli-posts"], 857)
            self.assertEqual(health["hli-consumed"], 857)
            self.assertEqual(health["hli-errors"], 0)
            self.assertEqual(health["hli-c2h-events"], 587)
            self.assertEqual(health["hli-c2h-acls"], 270)
            self.assertEqual(health["hli-queue-depth"], 0)
            self.assertEqual(health["meta-queue-depth"], 0)
            self.assertEqual(health["tx-queue-depth"], 0)
            self.assertEqual(health["peer-closed"], 0)
            self.assertEqual(health["trace-gap-adv-start"], 30)
            self.assertEqual(health["trace-hs-sched-reset"], 0)
            self.assertEqual(
                (health["conn-pool-free"], health["l2cap-pool-free"],
                 health["gatts-pool-free"]),
                (3, 9, 3),
            )

        self.assertEqual(sixty_evidence["status"], "PASS")
        self.assertEqual(sixty_evidence["attempts_requested"], 3)
        self.assertEqual(sixty_evidence["attempts_passed"], 3)
        self.assertEqual(sixty_evidence["attempts_failed"], 0)
        self.assertEqual(sixty_evidence["ble_reconnect_cycles"], 60)
        self.assertFalse(sixty_evidence["boundary"]["gdb_bridge"])
        for run in sixty_evidence["runs"]:
            health = run["native_hci_health"]
            self.assertEqual(health["hli-posts"], 1697)
            self.assertEqual(health["hli-consumed"], 1697)
            self.assertEqual(health["hli-errors"], 0)
            self.assertEqual(health["hli-c2h-events"], 1157)
            self.assertEqual(health["hli-c2h-acls"], 540)
            self.assertEqual(health["hli-queue-depth"], 0)
            self.assertEqual(health["meta-queue-depth"], 0)
            self.assertEqual(health["tx-queue-depth"], 0)
            self.assertEqual(health["peer-closed"], 0)
            self.assertEqual(health["trace-gap-adv-start"], 60)
            self.assertEqual(health["trace-hs-sched-reset"], 0)
            self.assertEqual(
                (health["conn-pool-free"], health["l2cap-pool-free"],
                 health["gatts-pool-free"]),
                (3, 9, 3),
            )

        self.assertEqual(hundred_twenty_evidence["status"], "PASS")
        self.assertEqual(hundred_twenty_evidence["attempts_requested"], 3)
        self.assertEqual(hundred_twenty_evidence["attempts_passed"], 3)
        self.assertEqual(hundred_twenty_evidence["attempts_failed"], 0)
        self.assertEqual(hundred_twenty_evidence["ble_reconnect_cycles"], 120)
        self.assertFalse(hundred_twenty_evidence["boundary"]["gdb_bridge"])
        for run in hundred_twenty_evidence["runs"]:
            health = run["native_hci_health"]
            self.assertEqual(health["hli-posts"], 3377)
            self.assertEqual(health["hli-consumed"], 3377)
            self.assertEqual(health["hli-errors"], 0)
            self.assertEqual(health["hli-c2h-events"], 2297)
            self.assertEqual(health["hli-c2h-acls"], 1080)
            self.assertEqual(health["hli-queue-depth"], 0)
            self.assertEqual(health["meta-queue-depth"], 0)
            self.assertEqual(health["tx-queue-depth"], 0)
            self.assertEqual(health["peer-closed"], 0)
            self.assertEqual(health["trace-gap-adv-start"], 120)
            self.assertEqual(health["trace-hs-sched-reset"], 0)
            self.assertEqual(health["dropped-packets"], 0)
            self.assertEqual(
                (health["conn-pool-free"], health["l2cap-pool-free"],
                 health["gatts-pool-free"]),
                (3, 9, 3),
            )

        self.assertEqual(hold600_evidence["status"], "PASS")
        self.assertEqual(hold600_evidence["attempts_requested"], 2)
        self.assertEqual(hold600_evidence["attempts_passed"], 2)
        self.assertEqual(hold600_evidence["attempts_failed"], 0)
        self.assertEqual(hold600_evidence["hold_seconds_per_attempt"], 600)
        self.assertEqual(hold600_evidence["ble_linger_seconds"], 660)
        self.assertFalse(hold600_evidence["boundary"]["gdb_bridge"])
        for run in hold600_evidence["runs"]:
            health = run["native_hci_health"]
            self.assertEqual(health["hli-posts"], 45)
            self.assertEqual(health["hli-consumed"], 45)
            self.assertEqual(health["hli-errors"], 0)
            self.assertEqual(health["hli-c2h-events"], 36)
            self.assertEqual(health["hli-c2h-acls"], 9)
            self.assertEqual(health["tx-queue-depth"], 0)
            self.assertEqual(health["last-error"], 0)
            self.assertEqual(health["peer-closed"], 0)
            self.assertEqual(health["dropped-packets"], 0)

        self.assertEqual(artifact_bound["status"], "PASS")
        self.assertEqual(artifact_bound["gate_result"], "PASS")
        self.assertEqual(artifact_bound["attempts_requested"], 1)
        self.assertEqual(artifact_bound["attempts_passed"], 1)
        self.assertEqual(artifact_bound["attempts_failed"], 0)
        self.assertEqual(artifact_bound["hold_seconds_per_attempt"], 7200)
        self.assertEqual(artifact_bound["ble_linger_seconds"], 7260)
        self.assertEqual(
            artifact_bound["input_hash_bound_at"],
            "before_first_lease",
        )
        self.assertTrue(
            artifact_bound["input_assets_unchanged_during_run"]
        )
        self.assertEqual(artifact_bound["input_asset_drift"], {})
        self.assertEqual(
            artifact_bound["firmware"]["sha256"],
            "4e1012c419d04e7188bb8c45476f6f5eb4d509f227bc4e385a805ce011916e02",
        )
        self.assertEqual(
            artifact_bound["elf_sha256"],
            "5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49",
        )
        self.assertEqual(
            artifact_bound["qemu_sha256"],
            "d970ddb54bf5fa070cf10d721f024f20a342a3837e3d19b564300f74f3f16fc1",
        )
        self.assertFalse(artifact_bound["boundary"]["gdb_bridge"])
        self.assertTrue(
            all(
                value == "PASS"
                for key, value in artifact_bound[
                    "checks_per_attempt"
                ].items()
                if key
                not in {
                    "hci_transport",
                    "frame_sha256",
                    "qom_nodes",
                }
            )
        )
        artifact_run = artifact_bound["runs"][0]
        artifact_health = artifact_run["native_hci_health"]
        self.assertEqual(artifact_health["hli-posts"], 45)
        self.assertEqual(artifact_health["hli-consumed"], 45)
        self.assertEqual(artifact_health["hli-errors"], 0)
        self.assertEqual(artifact_health["hli-c2h-events"], 36)
        self.assertEqual(artifact_health["hli-c2h-acls"], 9)
        self.assertEqual(artifact_health["hli-queue-depth"], 0)
        self.assertEqual(artifact_health["meta-queue-depth"], 0)
        self.assertEqual(artifact_health["tx-queue-depth"], 0)
        self.assertEqual(artifact_health["dropped-packets"], 0)
        self.assertEqual(artifact_health["last-error"], 0)
        self.assertEqual(artifact_health["peer-closed"], 0)
        self.assertEqual(artifact_run["failure_diagnostics"]["panic_count"], 0)
        self.assertEqual(artifact_run["network_status"], "PASS")
        self.assertEqual(artifact_run["hold_state"], "running")
        self.assertEqual(artifact_run["qom_nodes"], 34)
        self.assertEqual(artifact_run["pcap_bytes"], 66519)
        self.assertEqual(artifact_run["evidence_bytes"], 52743)
        resource_samples = artifact_run["hold_resource_samples"]
        self.assertEqual(resource_samples["state_polls"], 1438)
        self.assertEqual(resource_samples["rss_kib_min"], 744160)
        self.assertEqual(resource_samples["rss_kib_max"], 1202176)
        self.assertEqual(resource_samples["rss_kib_end"], 1202176)
        self.assertEqual(len(resource_samples["rss_kib_samples"]), 240)
        self.assertGreater(
            resource_samples["rss_kib_end"],
            resource_samples["rss_kib_min"],
        )
        self.assertEqual(tb128_hold120["status"], "PASS")
        tb128_run = tb128_hold120["runs"][0]
        self.assertEqual(
            tb128_run["qemu_accelerator"],
            "tcg,thread=single,tb-size=128",
        )
        tb128_resources = tb128_run["hold_resource_samples"]
        self.assertLessEqual(tb128_resources["rss_kib_delta"], 0)
        self.assertLessEqual(
            tb128_resources["phys_footprint_kib_delta"],
            0,
        )
        self.assertLessEqual(
            tb128_resources["phys_footprint_kib_max"],
            220 * 1024,
        )
        self.assertEqual(
            tb128_run["native_hci_health"]["hli-errors"],
            0,
        )
        self.assertEqual(tb128_hold7200["status"], "PASS")
        self.assertEqual(tb128_hold7200["gate_result"], "PASS")
        self.assertEqual(tb128_hold7200["attempts_requested"], 1)
        self.assertEqual(tb128_hold7200["attempts_passed"], 1)
        self.assertEqual(tb128_hold7200["attempts_failed"], 0)
        self.assertEqual(
            tb128_hold7200["hold_seconds_per_attempt"],
            7200,
        )
        self.assertEqual(
            tb128_hold7200["input_hash_bound_at"],
            "before_first_lease",
        )
        self.assertTrue(
            tb128_hold7200["input_assets_unchanged_during_run"]
        )
        self.assertEqual(tb128_hold7200["input_asset_drift"], {})
        self.assertEqual(
            set(tb128_hold7200["tool_hashes"]),
            {
                "runner",
                "device_service",
                "qemu_accel",
                "ble_runtime_limits",
            },
        )
        self.assertTrue(
            all(
                value == "PASS"
                for key, value in tb128_hold7200[
                    "checks_per_attempt"
                ].items()
                if key
                not in {
                    "hci_transport",
                    "frame_sha256",
                    "qom_nodes",
                }
            )
        )
        tb128_hold7200_run = tb128_hold7200["runs"][0]
        self.assertEqual(
            tb128_hold7200_run["qemu_accelerator"],
            "tcg,thread=single,tb-size=128",
        )
        self.assertEqual(tb128_hold7200_run["frame_bytes"], 3710)
        self.assertEqual(tb128_hold7200_run["qom_nodes"], 34)
        self.assertEqual(tb128_hold7200_run["network_status"], "PASS")
        self.assertEqual(tb128_hold7200_run["hold_state"], "running")
        self.assertEqual(tb128_hold7200_run["pcap_bytes"], 71967)
        self.assertEqual(tb128_hold7200_run["evidence_bytes"], 56203)
        hold7200_health = tb128_hold7200_run["native_hci_health"]
        self.assertEqual(hold7200_health["hli-posts"], 45)
        self.assertEqual(hold7200_health["hli-consumed"], 45)
        self.assertEqual(hold7200_health["hli-errors"], 0)
        self.assertEqual(hold7200_health["hli-c2h-events"], 36)
        self.assertEqual(hold7200_health["hli-c2h-acls"], 9)
        self.assertEqual(hold7200_health["hli-queue-depth"], 0)
        self.assertEqual(hold7200_health["meta-queue-depth"], 0)
        self.assertEqual(hold7200_health["tx-queue-depth"], 0)
        self.assertEqual(hold7200_health["dropped-packets"], 0)
        self.assertEqual(hold7200_health["last-error"], 0)
        self.assertEqual(hold7200_health["peer-closed"], 0)
        self.assertEqual(
            tb128_hold7200_run["failure_diagnostics"]["panic_count"],
            0,
        )
        hold7200_resources = tb128_hold7200_run[
            "hold_resource_samples"
        ]
        self.assertEqual(hold7200_resources["state_polls"], 1436)
        self.assertEqual(hold7200_resources["rss_kib_start"], 323536)
        self.assertEqual(hold7200_resources["rss_kib_end"], 252992)
        self.assertEqual(hold7200_resources["rss_kib_max"], 323808)
        self.assertLessEqual(hold7200_resources["rss_kib_delta"], 0)
        self.assertEqual(
            hold7200_resources["phys_footprint_kib_start"],
            250880,
        )
        self.assertEqual(
            hold7200_resources["phys_footprint_kib_end"],
            188416,
        )
        self.assertEqual(
            hold7200_resources["phys_footprint_kib_max"],
            256000,
        )
        self.assertLessEqual(
            hold7200_resources["phys_footprint_kib_delta"],
            0,
        )
        self.assertIn("FUNCTIONAL PASS / RSS REVIEW", core2_backend)
        self.assertIn("final bounded 7200s", core2_backend)
        self.assertIn("323536", ledger)
        self.assertIn("252992", ledger)
        self.assertIn("250880", ledger)
        self.assertIn("188416", ledger)
        self.assertIn("744160", ledger)
        self.assertIn("1202176", ledger)
        self.assertNotIn("250880", workstreams)

        core2_source = next(
            device for device in catalog_source["devices"]
            if device["id"] == "core2"
        )
        source_detail = core2_source["runtime"]["validation"]["detail"]
        self.assertIn("121 轮重连", source_detail)
        self.assertIn("两批六实例为 12/12", source_detail)
        self.assertIn("合计 16/16", source_detail)
        self.assertIn(
            "HLI 45/45",
            core2_source["runtime"]["validation"]["concurrency_validation"],
        )
        self.assertIn("最终 `tb-size=128` 两小时复测", source_detail)
        self.assertIn("323536", source_detail)
        self.assertIn("250880", source_detail)
        self.assertNotIn("更多轮次", source_detail)
        self.assertNotIn("最终两小时限容复测尚未完成", source_detail)

        core2_profile = next(
            device for device in qemu_profiles["devices"]
            if device["id"] == "core2"
        )
        profile_detail = core2_profile["validation"]["detail"]
        self.assertIn("Three independent leases complete 121 reconnect cycles", profile_detail)
        self.assertIn("HLI 3405/3405", profile_detail)
        self.assertIn("artifact-bound tb-size=128 7200s", profile_detail)
        self.assertIn("bounded host memory", profile_detail)
        self.assertNotIn("More than sixty", profile_detail)
        self.assertNotIn("bounded-TCG 7200s rerun remains pending", profile_detail)
        blocker_text = " ".join(core2_profile["blockers"])
        self.assertIn("virtual-device concurrency gates", blocker_text)
        self.assertIn("current service capacity", blocker_text)
        self.assertIn("more-than-eight-instance stability", blocker_text)
        self.assertIn("bounded-TCG host-memory", blocker_text)
        for volatile_count in ("8/8", "6/6", "10/10", "12/12", "16/16"):
            self.assertNotIn(volatile_count, blocker_text)
        self.assertEqual(active_stop["status"], "PASS")
        self.assertEqual(active_stop["attempts_requested"], 3)
        self.assertEqual(active_stop["attempts_passed"], 3)
        self.assertTrue(
            all(run["status"] == "PASS" for run in active_stop["runs"])
        )
        self.assertTrue(
            all(
                run["checks"]["pre_stop_ble_companion_running"]
                and run["checks"]["stop_ble_companion_terminated"]
                and run["checks"]["qemu_process_reaped"]
                and run["checks"]["ble_peer_process_reaped"]
                and run["checks"]["worker_lease_released"]
                for run in active_stop["runs"]
            )
        )
        self.assertIn(
            "run_service_teardown.py",
            (ROOT / "tests/uiflow2/core2_native_hci/README.md").read_text(),
        )
        self.assertIn(
            "active-stop/recovery",
            (DOCS / "core2-native-hci-backend.md").read_text(),
        )

        core2_generated = next(
            device for device in generated_catalog["devices"]
            if device["id"] == "core2"
        )
        self.assertEqual(
            core2_generated["runtime"]["validation"]["detail"],
            source_detail,
        )

    def test_core2_guest_psram_stress_is_reconciled(self) -> None:
        evidence_path = (
            ROOT
            / "tests/uiflow2/core2_native_hci/"
            "evidence-2026-10-25-core2-psram-sustained-3x120.json"
        )
        evidence = json.loads(evidence_path.read_text())
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["validation"], "virtual-device validation")
        self.assertEqual(evidence["attempts_completed"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertEqual(evidence["psram_gate"], "PASS")
        self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
        self.assertTrue(evidence["input_assets_unchanged_during_run"])
        sweep_counts = []
        for run in evidence["runs"]:
            self.assertEqual(run["status"], "PASS")
            self.assertEqual(run["psram"]["external_heap_total_bytes"], 4 << 20)
            self.assertEqual(run["psram"]["requested_bytes"], 1 << 20)
            self.assertGreaterEqual(
                run["psram"]["allocated_bytes"],
                run["psram"]["requested_bytes"],
            )
            sweeps = run["psram"]["sweeps"]
            sweep_counts.append(len(sweeps))
            self.assertEqual(sweeps, list(range(1, len(sweeps) + 1)))
            self.assertGreaterEqual(len(sweeps), 30)
            self.assertEqual(
                run["psram"]["verified_bytes"],
                len(sweeps) * (1 << 20),
            )
            self.assertGreaterEqual(
                run["psram"]["http_recheck_pass_count"],
                8,
            )
            self.assertGreaterEqual(
                run["psram"]["public_recheck_pass_count"],
                2,
            )
            self.assertGreaterEqual(len(run["psram"]["heartbeats"]), 6)
            self.assertEqual(run["psram"]["init_pass_count"], 1)
            self.assertEqual(run["psram"]["stress_pass_count"], 1)
            self.assertEqual(run["psram"]["error_markers"], [])
            self.assertGreater(run["pcap_bytes"], 20_000)
        self.assertEqual(sweep_counts, [36, 35, 35])
        self.assertEqual(sum(sweep_counts), 106)
        checks = evidence["checks_per_attempt"]
        for name in (
            "psram_guest_stress",
            "psram_sustained_stress",
            "wifi_dhcp_http",
            "public_dns_http",
            "external_nus_gatt",
            "frame_png",
            "pcap_file_in_evidence_zip",
            "api_evidence",
        ):
            self.assertEqual(checks[name], "PASS")
        self.assertIn(
            "physical 8 MiB PSRAM capacity",
            evidence["boundary"]["not_claimed"],
        )
        failure = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-threshold-fail-1x.json"
            ).read_text()
        )
        self.assertEqual(failure["status"], "FAIL")
        self.assertEqual(
            failure["checks_per_attempt"]["psram_sustained_stress"],
            "FAIL",
        )
        self.assertEqual(
            failure["runs"][0]["psram_requirements"]["minimum_sweeps"],
            40,
        )
        pcap_summary = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-3x120-pcap-summary.json"
            ).read_text()
        )
        self.assertEqual(pcap_summary["status"], "PASS")
        self.assertEqual(
            [attempt["packets"] for attempt in pcap_summary["attempts"]],
            [222, 205, 211],
        )
        for attempt in pcap_summary["attempts"]:
            self.assertEqual(
                attempt["dhcp_message_types"],
                {"discover": 1, "offer": 1, "request": 1, "ack": 1},
            )
            self.assertIn("example.com.", attempt["dns_queries"])
        soak600 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-1x600.json"
            ).read_text()
        )
        self.assertEqual(soak600["status"], "PASS")
        self.assertEqual(soak600["attempts_completed"], 1)
        self.assertEqual(soak600["hold_seconds_per_attempt"], 600)
        self.assertEqual(soak600["psram_gate"], "PASS")
        soak_run = soak600["runs"][0]
        self.assertEqual(len(soak_run["psram"]["sweeps"]), 179)
        self.assertEqual(soak_run["psram"]["verified_bytes"], 179 * (1 << 20))
        self.assertEqual(soak_run["psram"]["http_recheck_pass_count"], 51)
        self.assertEqual(soak_run["psram"]["public_recheck_pass_count"], 18)
        self.assertEqual(soak_run["pcap_bytes"], 97_951)
        self.assertEqual(soak600["checks_per_attempt"]["psram_sustained_stress"], "PASS")
        soak_pcap = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-1x600-pcap-summary.json"
            ).read_text()
        )
        self.assertEqual(soak_pcap["status"], "PASS")
        self.assertEqual(soak_pcap["packets"], 912)
        self.assertEqual(soak_pcap["flows"], 208)
        self.assertIn("example.com.", soak_pcap["dns_queries"])

        runner = (
            ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"
        ).read_text()
        guest = (
            ROOT / "tests/uiflow2/unified_core2/main.py"
        ).read_text()
        self.assertEqual(
            evidence["tool_hashes"]["runner"],
            "72c8f8a70c3764aa73673385783d97a6412809935bbba0080f1843a6d553e9a4",
        )
        self.assertIn("--require-psram", runner)
        self.assertIn("UNIFIED_CORE2_STRESS_HEARTBEAT", runner)
        self.assertIn("psram_buffer[offset + 2 : end]", guest)
        self.assertIn("UNIFIED_CORE2_PSRAM_STRESS_PASS", guest)
        self.assertIn("UNIFIED_CORE2_HTTP_RECHECK_PASS", guest)
        self.assertIn("UNIFIED_CORE2_PUBLIC_RECHECK_PASS", guest)
        self.assertIn("UNIFIED_CORE2_STRESS_HEARTBEAT", guest)

    def test_core2_concurrent_lease_evidence_is_reconciled(self) -> None:
        root = ROOT / "tests/uiflow2/core2_native_hci"
        concurrent = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-2x120-stagger30.json"
            ).read_text()
        )
        self.assertEqual(concurrent["status"], "PASS")
        self.assertEqual(concurrent["attempts_requested"], 2)
        self.assertEqual(concurrent["attempts_passed"], 2)
        self.assertEqual(concurrent["concurrency_requested"], 2)
        self.assertEqual(concurrent["maximum_concurrent_sessions"], 2)
        self.assertTrue(concurrent["concurrency_observed"])
        self.assertEqual(concurrent["stagger_seconds"], 30)
        self.assertEqual(concurrent["hold_seconds_per_attempt"], 120)
        self.assertTrue(concurrent["input_assets_unchanged_during_run"])
        for run in concurrent["runs"]:
            self.assertEqual(run["status"], "PASS")
            self.assertEqual(run["network_status"], "PASS")
            self.assertEqual(run["native_hci_health"]["hli-posts"], 45)
            self.assertEqual(
                run["native_hci_health"]["hli-posts"],
                run["native_hci_health"]["hli-consumed"],
            )
            self.assertEqual(run["native_hci_health"]["hli-errors"], 0)
            self.assertEqual(run["failure_diagnostics"]["panic_count"], 0)
            self.assertGreaterEqual(len(run["psram"]["sweeps"]), 30)
            self.assertEqual(
                run["qemu_accelerator"],
                "tcg,thread=single,tb-size=128",
            )
        self.assertEqual(
            len({run["frame_sha256"] for run in concurrent["runs"]}),
            1,
        )
        self.assertEqual(
            len({run["qom_nodes"] for run in concurrent["runs"]}),
            1,
        )
        for digest in concurrent["tool_hashes"].values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

        port_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrency-"
                "http-port-collision-fail.json"
            ).read_text()
        )
        self.assertEqual(port_failure["status"], "FAIL")
        self.assertEqual(port_failure["maximum_concurrent_sessions"], 2)
        self.assertEqual(port_failure["attempts_passed"], 1)
        self.assertIn(
            "Address already in use",
            "\n".join(
                str(run.get("hold_error"))
                for run in port_failure["runs"]
            ),
        )

        startup_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrency-"
                "simultaneous-start-fail.json"
            ).read_text()
        )
        self.assertEqual(startup_failure["status"], "FAIL")
        self.assertEqual(startup_failure["maximum_concurrent_sessions"], 2)
        self.assertEqual(startup_failure["attempts_passed"], 1)
        failed_run = next(
            run
            for run in startup_failure["runs"]
            if run["status"] == "FAIL"
        )
        self.assertEqual(
            failed_run["failure_diagnostics"]["first_panic"]["pc"],
            "0x402630cc",
        )

        timeout_pass = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "2x120-simultaneous-timeout30-pass.json"
            ).read_text()
        )
        self.assertEqual(timeout_pass["status"], "PASS")
        self.assertEqual(timeout_pass["attempts_passed"], 2)
        self.assertEqual(timeout_pass["attempts_failed"], 0)
        self.assertEqual(timeout_pass["stagger_seconds"], 0)
        self.assertTrue(
            all(
                run["native_hci_health"]["hli-errors"] == 0
                for run in timeout_pass["runs"]
            )
        )

        hli_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "4x120-hli-errors-fail.json"
            ).read_text()
        )
        self.assertEqual(hli_failure["status"], "FAIL")
        self.assertEqual(hli_failure["attempts_completed"], 4)
        self.assertEqual(hli_failure["attempts_passed"], 3)
        self.assertEqual(hli_failure["attempts_failed"], 1)
        failed_hli_run = next(
            run for run in hli_failure["runs"] if run["status"] == "FAIL"
        )
        self.assertEqual(failed_hli_run["attempt"], "attempt-3")
        self.assertEqual(failed_hli_run["native_hci_health"]["hli-errors"], 3)
        self.assertEqual(failed_hli_run["native_hci_health"]["hli-posts"], 45)
        self.assertEqual(
            failed_hli_run["native_hci_health"]["hli-consumed"], 45
        )
        self.assertEqual(failed_hli_run["failure_diagnostics"]["panic_count"], 0)
        self.assertEqual(failed_hli_run["network_status"], "PASS")

        valid_queue_pass = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "4x120-simultaneous-pass.json"
            ).read_text()
        )
        confirm_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "4x120-simultaneous-confirm-fail.json"
            ).read_text()
        )
        self.assertEqual(valid_queue_pass["status"], "PASS")
        self.assertEqual(valid_queue_pass["attempts_passed"], 4)
        self.assertEqual(valid_queue_pass["attempts_failed"], 0)
        self.assertEqual(valid_queue_pass["stagger_seconds"], 0)
        for run in valid_queue_pass["runs"]:
            self.assertEqual(run["native_hci_health"]["hli-errors"], 0)
            self.assertEqual(run["native_hci_health"]["hli-posts"], 45)
            self.assertEqual(run["native_hci_health"]["hli-consumed"], 45)
            self.assertEqual(run["failure_diagnostics"]["panic_count"], 0)

        self.assertEqual(confirm_failure["status"], "FAIL")
        self.assertEqual(confirm_failure["attempts_completed"], 2)
        self.assertEqual(confirm_failure["attempts_passed"], 1)
        self.assertEqual(confirm_failure["attempts_failed"], 1)
        confirm_run = next(
            run
            for run in confirm_failure["runs"]
            if run["status"] == "FAIL"
        )
        self.assertTrue(confirm_run["failure_diagnostics"]["peer_gatt_timeout"])
        self.assertEqual(
            confirm_run["failure_diagnostics"]["first_panic"]["pc"],
            "0x402630cc",
        )
        self.assertEqual(
            valid_queue_pass["qemu_sha256"],
            confirm_failure["qemu_sha256"],
        )
        self.assertEqual(
            valid_queue_pass["tool_hashes"],
            confirm_failure["tool_hashes"],
        )
        for digest in valid_queue_pass["tool_hashes"].values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

        prealloc_runs = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-"
                "4x120-prealloc-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-"
                "4x120-prealloc-confirm-pass-b.json",
            )
        ]
        for prealloc in prealloc_runs:
            self.assertEqual(prealloc["status"], "PASS")
            self.assertEqual(prealloc["attempts_requested"], 4)
            self.assertEqual(prealloc["attempts_passed"], 4)
            self.assertEqual(prealloc["attempts_failed"], 0)
            self.assertEqual(prealloc["stagger_seconds"], 0)
            self.assertEqual(prealloc["maximum_concurrent_sessions"], 2)
            for run in prealloc["runs"]:
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-fast-path-events"], 36)
                self.assertEqual(health["hli-fast-path-acls"], 9)
                self.assertEqual(health["hli-event-prealloc-depth"], 2)
                self.assertEqual(health["hli-acl-prealloc-depth"], 2)
                self.assertEqual(health["hli-prealloc-failures"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
        self.assertEqual(
            prealloc_runs[0]["qemu_sha256"],
            prealloc_runs[1]["qemu_sha256"],
        )
        self.assertEqual(
            prealloc_runs[0]["tool_hashes"],
            prealloc_runs[1]["tool_hashes"],
        )
        for digest in prealloc_runs[0]["tool_hashes"].values():
            self.assertRegex(digest, r"^[0-9a-f]{64}$")

        peer_timeout_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "3x120-peer-timeout-fail.json"
            ).read_text()
        )
        self.assertEqual(peer_timeout_failure["status"], "FAIL")
        self.assertEqual(peer_timeout_failure["attempts_requested"], 3)
        self.assertEqual(peer_timeout_failure["attempts_passed"], 0)
        self.assertEqual(peer_timeout_failure["attempts_failed"], 3)
        self.assertEqual(peer_timeout_failure["maximum_concurrent_sessions"], 3)
        self.assertTrue(
            all(
                run["hold_error"]
                == "external BLE peer did not complete the GATT exchange"
                for run in peer_timeout_failure["runs"]
            )
        )

        threshold_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "3x120-scan120-threshold-fail.json"
            ).read_text()
        )
        self.assertEqual(threshold_failure["status"], "FAIL")
        self.assertEqual(threshold_failure["attempts_passed"], 1)
        self.assertEqual(threshold_failure["attempts_failed"], 2)
        for run in threshold_failure["runs"]:
            self.assertEqual(
                run["psram_requirements"]["minimum_sweeps"],
                30,
            )
            if run["status"] == "FAIL":
                self.assertEqual(len(run["psram"]["sweeps"]), 29)
                self.assertEqual(run["failure_class"], "check_failed")

        power_monitor_failure = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-core2-power-monitor-"
                "postboot-injection-fail.json"
            ).read_text()
        )
        self.assertEqual(power_monitor_failure["status"], "FAIL")
        self.assertEqual(
            power_monitor_failure["classification"],
            "runtime_fixture_timing",
        )
        self.assertEqual(
            power_monitor_failure["boot_injection_control"]["status"],
            "PASS",
        )

        qom_boot_group = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-core2-qom-boot-device-group.json"
            ).read_text()
        )
        self.assertEqual(qom_boot_group["device_group"]["cases"], 6)
        self.assertEqual(qom_boot_group["device_group"]["pass"], 6)
        self.assertEqual(qom_boot_group["device_group"]["checks"], 24)
        self.assertFalse(qom_boot_group["device_group"]["retry_used"])
        self.assertTrue(
            all(
                case["status"] == "PASS"
                for case in qom_boot_group["cases"].values()
            )
        )
        matrix_runner = (
            ROOT / "tests/uiflow2/run_peripheral_matrix.py"
        ).read_text()
        self.assertIn(
            '"/machine/ina3221-40", "bus1-mv", "4800"',
            matrix_runner,
        )

        three_instance_runs = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-3x120-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-"
                "3x120-confirm-pass-b.json",
            )
        ]
        expected_sweep_counts = ([29, 29, 29], [30, 29, 29])
        for evidence, sweep_counts in zip(
            three_instance_runs,
            expected_sweep_counts,
            strict=True,
        ):
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 3)
            self.assertEqual(evidence["attempts_passed"], 3)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 3)
            self.assertEqual(evidence["stagger_seconds"], 0)
            self.assertTrue(evidence["input_assets_unchanged_during_run"])
            self.assertEqual(
                len({run["frame_sha256"] for run in evidence["runs"]}),
                1,
            )
            for run, sweep_count in zip(
                evidence["runs"],
                sweep_counts,
                strict=True,
            ):
                health = run["native_hci_health"]
                self.assertEqual(run["qom_memory_bytes"], 8 << 20)
                self.assertEqual(
                    run["psram_requirements"]["minimum_sweeps"],
                    24,
                )
                self.assertEqual(
                    len(run["psram"]["sweeps"]),
                    sweep_count,
                )
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-fast-path-events"], 36)
                self.assertEqual(health["hli-fast-path-acls"], 9)
                self.assertEqual(health["hli-event-prealloc-depth"], 2)
                self.assertEqual(health["hli-acl-prealloc-depth"], 2)
                self.assertLessEqual(health["hli-prealloc-failures"], 1)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
        self.assertEqual(
            three_instance_runs[0]["tool_hashes"],
            three_instance_runs[1]["tool_hashes"],
        )

        four_instance_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "4x120-prealloc-4way-fail.json"
            ).read_text()
        )
        self.assertEqual(four_instance_failure["status"], "FAIL")
        self.assertEqual(four_instance_failure["attempts_requested"], 4)
        self.assertEqual(four_instance_failure["attempts_completed"], 4)
        self.assertEqual(four_instance_failure["attempts_passed"], 1)
        self.assertEqual(four_instance_failure["attempts_failed"], 3)
        self.assertEqual(four_instance_failure["maximum_concurrent_sessions"], 4)
        self.assertTrue(four_instance_failure["concurrency_observed"])
        self.assertEqual(four_instance_failure["stagger_seconds"], 0)
        failed_runs = {
            run["attempt"]: run
            for run in four_instance_failure["runs"]
            if run["status"] == "FAIL"
        }
        self.assertEqual(set(failed_runs), {"attempt-2", "attempt-3", "attempt-4"})
        self.assertEqual(
            failed_runs["attempt-2"]["native_hci_health"]["hli-errors"],
            1,
        )
        self.assertEqual(
            failed_runs["attempt-2"]["native_hci_health"][
                "hli-prealloc-failures"
            ],
            2,
        )
        for attempt in ("attempt-3", "attempt-4"):
            run = failed_runs[attempt]
            self.assertEqual(run["failure_class"], "panic_load_prohibited")
            self.assertGreater(run["failure_diagnostics"]["panic_count"], 0)
            self.assertEqual(
                run["failure_diagnostics"]["first_panic"]["pc"],
                "0x402630cc",
            )
            self.assertEqual(
                run["failure_diagnostics"]["last_panic"]["pc"],
                "0x00000000",
            )

        four_instance_passes = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-"
                "4x120-prealloc8x4-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-"
                "4x120-prealloc8x4-confirm-pass-b.json",
            )
        ]
        for evidence in four_instance_passes:
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 4)
            self.assertEqual(evidence["attempts_completed"], 4)
            self.assertEqual(evidence["attempts_passed"], 4)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 4)
            self.assertTrue(evidence["concurrency_observed"])
            self.assertEqual(evidence["stagger_seconds"], 0)
            self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
            self.assertTrue(evidence["input_assets_unchanged_during_run"])
            self.assertEqual(
                len({run["frame_sha256"] for run in evidence["runs"]}),
                1,
            )
            for run in evidence["runs"]:
                health = run["native_hci_health"]
                self.assertEqual(run["qom_memory_bytes"], 8 << 20)
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-fast-path-events"], 36)
                self.assertEqual(health["hli-fast-path-acls"], 9)
                self.assertEqual(health["hli-event-prealloc-depth"], 8)
                self.assertEqual(health["hli-acl-prealloc-depth"], 4)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
                self.assertGreaterEqual(len(run["psram"]["sweeps"]), 24)
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in four_instance_passes[0]["runs"]
            ),
            2,
        )
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in four_instance_passes[1]["runs"]
            ),
            0,
        )
        self.assertEqual(
            four_instance_passes[0]["qemu_sha256"],
            four_instance_passes[1]["qemu_sha256"],
        )
        self.assertEqual(
            four_instance_passes[0]["tool_hashes"],
            four_instance_passes[1]["tool_hashes"],
        )
        five_instance_staggered = [
            json.loads(
                (
                    root / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-"
                "5x120-stagger30-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-"
                "5x120-stagger30-confirm-pass-b.json",
            )
        ]
        for evidence in five_instance_staggered:
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 5)
            self.assertEqual(evidence["attempts_completed"], 5)
            self.assertEqual(evidence["attempts_passed"], 5)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 5)
            self.assertTrue(evidence["concurrency_observed"])
            self.assertEqual(evidence["stagger_seconds"], 30)
            self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
            self.assertTrue(evidence["input_assets_unchanged_during_run"])
            for run in evidence["runs"]:
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-fast-path-events"], 36)
                self.assertEqual(health["hli-fast-path-acls"], 9)
                self.assertEqual(health["hli-event-prealloc-depth"], 8)
                self.assertEqual(health["hli-acl-prealloc-depth"], 4)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
                self.assertGreaterEqual(len(run["psram"]["sweeps"]), 24)
        self.assertEqual(
            five_instance_staggered[0]["qemu_sha256"],
            five_instance_staggered[1]["qemu_sha256"],
        )
        self.assertEqual(
            five_instance_staggered[0]["tool_hashes"],
            five_instance_staggered[1]["tool_hashes"],
        )

        no_stagger_pass = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "5x120-no-stagger-pass-1.json"
            ).read_text()
        )
        no_stagger_fail = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-"
                "5x120-no-stagger-fail-1.json"
            ).read_text()
        )
        self.assertEqual(no_stagger_pass["status"], "PASS")
        self.assertEqual(no_stagger_pass["attempts_passed"], 5)
        self.assertEqual(no_stagger_pass["maximum_concurrent_sessions"], 5)
        self.assertEqual(no_stagger_pass["stagger_seconds"], 0)
        self.assertEqual(no_stagger_fail["status"], "FAIL")
        self.assertEqual(no_stagger_fail["attempts_passed"], 3)
        self.assertEqual(no_stagger_fail["attempts_failed"], 2)
        self.assertEqual(no_stagger_fail["maximum_concurrent_sessions"], 5)
        self.assertEqual(no_stagger_fail["stagger_seconds"], 0)
        self.assertEqual(
            no_stagger_pass["qemu_sha256"],
            no_stagger_fail["qemu_sha256"],
        )
        self.assertEqual(
            no_stagger_pass["tool_hashes"],
            no_stagger_fail["tool_hashes"],
        )
        failed_five = [
            run
            for run in no_stagger_fail["runs"]
            if run["status"] == "FAIL"
        ]
        self.assertEqual(len(failed_five), 2)
        self.assertTrue(
            any(
                run["failure_class"] == "panic_load_prohibited"
                and run["failure_diagnostics"]["first_panic"]["pc"]
                == "0x402630cc"
                for run in failed_five
            )
        )
        self.assertTrue(
            any(
                run["hold_error"]
                == "external BLE peer did not complete the GATT exchange"
                for run in failed_five
            )
        )

        historical_concurrent = [*three_instance_runs, *four_instance_passes]
        historical_tools = historical_concurrent[0]["tool_hashes"]
        self.assertTrue(
            all(
                evidence["tool_hashes"] == historical_tools
                for evidence in historical_concurrent
            )
        )
        legacy_five_concurrent = [
            *five_instance_staggered,
            no_stagger_pass,
            no_stagger_fail,
        ]
        legacy_tools = legacy_five_concurrent[0]["tool_hashes"]
        self.assertTrue(
            all(
                evidence["tool_hashes"] == legacy_tools
                for evidence in legacy_five_concurrent
            )
        )
        self.assertNotEqual(
            historical_tools["runner"],
            legacy_tools["runner"],
        )

        fixed_icount_runs = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-5x120-"
                "fixed-icount-blefirst-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-5x120-"
                "fixed-icount-blefirst-pass-b.json",
            )
        ]
        six_instance_runs = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-6x120-"
                "fixed-icount-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-6x120-"
                "fixed-icount-pass-b.json",
            )
        ]
        eight_instance_failure = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-concurrent-8x120-"
                "threshold-fail.json"
            ).read_text()
        )
        eight_instance_runs = [
            json.loads(
                (
                    root
                    / filename
                ).read_text()
            )
            for filename in (
                "evidence-2026-10-25-core2-concurrent-8x120-"
                "fixed-icount-pass-a.json",
                "evidence-2026-10-25-core2-concurrent-8x120-"
                "fixed-icount-pass-b.json",
            )
        ]
        pre_calibration_runs = [
            *fixed_icount_runs,
            *six_instance_runs,
            eight_instance_failure,
        ]
        pre_calibration_tools = pre_calibration_runs[0]["tool_hashes"]
        self.assertTrue(
            all(
                evidence["tool_hashes"] == pre_calibration_tools
                for evidence in pre_calibration_runs
            )
        )
        current_concurrent = eight_instance_runs
        current_tools = current_concurrent[0]["tool_hashes"]
        self.assertTrue(
            all(
                evidence["tool_hashes"] == current_tools
                for evidence in current_concurrent
            )
        )
        self.assertNotEqual(
            pre_calibration_tools["runner"],
            current_tools["runner"],
        )
        for evidence in fixed_icount_runs:
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 5)
            self.assertEqual(evidence["attempts_passed"], 5)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 5)
            self.assertEqual(evidence["stagger_seconds"], 0)
            self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
            self.assertTrue(evidence["input_assets_unchanged_during_run"])
            for run in evidence["runs"]:
                self.assertEqual(run["qemu_icount"], "shift=5,align=off,sleep=off")
                self.assertEqual(run["qom_nodes"], 31)
                self.assertGreaterEqual(len(run["psram"]["sweeps"]), 12)
                self.assertLessEqual(len(run["psram"]["sweeps"]), 15)
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-c2h-events"], 36)
                self.assertEqual(health["hli-c2h-acls"], 9)
                self.assertEqual(health["hli-event-prealloc-depth"], 8)
                self.assertEqual(health["hli-acl-prealloc-depth"], 4)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(health["dropped-packets"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
        for evidence in six_instance_runs:
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 6)
            self.assertEqual(evidence["attempts_passed"], 6)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 6)
            self.assertEqual(evidence["stagger_seconds"], 0)
            self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
            self.assertTrue(evidence["input_assets_unchanged_during_run"])
            for run in evidence["runs"]:
                self.assertEqual(run["qemu_icount"], "shift=5,align=off,sleep=off")
                self.assertEqual(run["qom_nodes"], 31)
                self.assertGreaterEqual(len(run["psram"]["sweeps"]), 12)
                self.assertLessEqual(len(run["psram"]["sweeps"]), 13)
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-c2h-events"], 36)
                self.assertEqual(health["hli-c2h-acls"], 9)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(health["dropped-packets"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in six_instance_runs[0]["runs"]
            ),
            0,
        )
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in six_instance_runs[1]["runs"]
            ),
            1,
        )
        self.assertEqual(eight_instance_failure["status"], "FAIL")
        self.assertEqual(eight_instance_failure["attempts_requested"], 8)
        self.assertEqual(eight_instance_failure["attempts_passed"], 4)
        self.assertEqual(eight_instance_failure["attempts_failed"], 4)
        self.assertEqual(
            eight_instance_failure["checks_per_attempt"][
                "psram_sustained_stress"
            ],
            "FAIL",
        )
        for run in eight_instance_failure["runs"]:
            self.assertEqual(run["network_status"], "PASS")
            self.assertEqual(run["native_hci_health"]["hli-errors"], 0)
            self.assertEqual(
                run["failure_diagnostics"]["panic_count"],
                0,
            )
            self.assertIn(len(run["psram"]["sweeps"]), (11, 12))
        for evidence in eight_instance_runs:
            self.assertEqual(evidence["status"], "PASS")
            self.assertEqual(evidence["attempts_requested"], 8)
            self.assertEqual(evidence["attempts_passed"], 8)
            self.assertEqual(evidence["attempts_failed"], 0)
            self.assertEqual(evidence["maximum_concurrent_sessions"], 8)
            self.assertEqual(evidence["stagger_seconds"], 0)
            self.assertEqual(evidence["hold_seconds_per_attempt"], 120)
            for run in evidence["runs"]:
                self.assertEqual(run["qemu_icount"], "shift=5,align=off,sleep=off")
                self.assertEqual(run["qom_nodes"], 31)
                self.assertIn(len(run["psram"]["sweeps"]), (11, 12))
                self.assertEqual(
                    run["psram_requirements"]["minimum_sweeps"],
                    10,
                )
                health = run["native_hci_health"]
                self.assertEqual(health["hli-posts"], 45)
                self.assertEqual(health["hli-consumed"], 45)
                self.assertEqual(health["hli-errors"], 0)
                self.assertEqual(health["hli-c2h-events"], 36)
                self.assertEqual(health["hli-c2h-acls"], 9)
                self.assertEqual(health["trace-hs-sched-reset"], 0)
                self.assertEqual(health["dropped-packets"], 0)
                self.assertEqual(
                    run["failure_diagnostics"]["panic_count"],
                    0,
                )
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in eight_instance_runs[0]["runs"]
            ),
            1,
        )
        self.assertEqual(
            sum(
                run["native_hci_health"]["hli-prealloc-failures"]
                for run in eight_instance_runs[1]["runs"]
            ),
            1,
        )

        device_group = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-core2-0009-device-group.json"
            ).read_text()
        )
        self.assertEqual(device_group["device_id"], "core2")
        self.assertEqual(device_group["cases"], 6)
        self.assertEqual(device_group["checks"], 24)
        self.assertEqual(device_group["attempts"], 6)
        self.assertFalse(device_group["retry_used"])
        self.assertTrue(
            all(
                result["status"] == "PASS"
                for result in device_group["results"].values()
            )
        )

        for name, relative in {
            "runner": "tests/uiflow2/core2_native_hci/run_service_5x.py",
            "device_service": "platform/tools/device_service.py",
            "qemu_accel": "platform/tools/qemu_accel.py",
            "ble_runtime_limits": "platform/tools/ble_runtime_limits.py",
            "ble_probe": "platform/tools/ble_probe.py",
            "network_policy": "platform/tools/network_policy.py",
            "unified_http_guestfwd": (
                "platform/tools/unified_http_guestfwd.py"
            ),
        }.items():
            current_digest = hashlib.sha256(
                (ROOT / relative).read_bytes()
            ).hexdigest()
            for evidence in current_concurrent:
                self.assertEqual(
                    evidence["tool_hashes"][name],
                    current_digest,
                )

        latency = json.loads(
            (
                root
                / "evidence-2026-10-25-core2-hli-preallocation-latency.json"
            ).read_text()
        )
        self.assertEqual(latency["validation"], "virtual-device validation")
        self.assertGreater(
            latency["comparison"][0]["delivery_delay_ns"],
            latency["nimble_hci_command_timeout_ns"],
        )
        self.assertLess(
            latency["comparison"][1]["delivery_delay_ns"],
            latency["nimble_hci_command_timeout_ns"],
        )

        full_matrix = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-core2-hli-preallocation-full-matrix.json"
            ).read_text()
        )
        self.assertEqual(full_matrix["peripheral_matrix"]["cases"], 67)
        self.assertEqual(full_matrix["peripheral_matrix"]["pass"], 67)
        self.assertEqual(full_matrix["peripheral_matrix"]["checks"], 274)
        self.assertEqual(full_matrix["peripheral_matrix"]["checks_pass"], 274)
        self.assertFalse(full_matrix["peripheral_matrix"]["retry_used"])
        self.assertEqual(
            sum(
                case["checks"]
                for case in full_matrix["core2_cases"].values()
            ),
            24,
        )
        self.assertTrue(
            all(
                case["status"] == "PASS"
                for case in full_matrix["core2_cases"].values()
            )
        )

        backend = (DOCS / "core2-native-hci-backend.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        platform_readme = (ROOT / "platform/README.md").read_text()
        unified_core2 = (
            ROOT / "tests/uiflow2/unified_core2/README.md"
        ).read_text()
        profiles = (
            ROOT / "platform/qemu/profiles.json"
        ).read_text()
        patch = (
            ROOT
            / "patches/qemu-core2-native-hci/"
            "0007-esp32-native-hci-require-valid-guest-queue.patch"
        ).read_text()
        prealloc_patch = (
            ROOT
            / "patches/qemu-core2-native-hci/"
            "0008-esp32-native-hci-preallocate-hli-objects.patch"
        ).read_text()
        expansion_patch = (
            ROOT
            / "patches/qemu-core2-native-hci/"
            "0009-esp32-native-hci-expand-hli-preallocation.patch"
        ).read_text()
        for text in (
            "staggered concurrent leases",
            "simultaneous cold-start history",
            "simultaneous cold-start preallocation",
            "four-instance initial failure",
            "four-instance expanded reserve",
            "five-instance staggered",
            "five-instance simultaneous cold start",
            "fixed icount",
            "guestfwd",
            "ble_hs_hci_process_ack",
            "hli-errors=3",
            "8/8 PASS",
            "36 events/9 ACLs",
            "0.328s",
        ):
            self.assertIn(text, backend)
        self.assertIn("unified_http_guestfwd.py", code_map)
        self.assertIn("0007", code_map)
        self.assertIn("0008", code_map)
        self.assertIn("0009", code_map)
        self.assertIn("0010", code_map)
        self.assertIn("virtual-device concurrency gates", profiles)
        self.assertIn("current service capacity", profiles)
        self.assertIn(
            "one batch passed 5/5 and an independent confirmation failed 3/5",
            profiles,
        )
        self.assertIn("more-than-eight-instance stability", profiles)
        for text in (unified_core2,):
            self.assertIn("0008", text)
            self.assertIn("0009", text)
            self.assertIn("shift=5", text)
        self.assertIn("当前服务容量内的并发", platform_readme)
        self.assertIn("validation-ledger.md", platform_readme)
        self.assertIn("`5x120s`", unified_core2)
        self.assertIn("`6x120s`", unified_core2)
        self.assertIn("`8x120s`", unified_core2)
        self.assertIn("| P0 | Core2 物理/controller 等价性 |", backlog)
        self.assertNotIn("| P1 | Core2 物理/controller 等价性 |", backlog)
        self.assertIn("`CORE2-02` 仍为 P0", status)
        self.assertIn("!s->hli_valid", patch)
        self.assertIn("ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC", prealloc_patch)
        self.assertIn("ESP32_NATIVE_HCI_HLI_ACL_PREALLOC", prealloc_patch)
        self.assertIn("hli-fast-path-events", prealloc_patch)
        self.assertIn("ESP32_NATIVE_HCI_HLI_EVENT_PREALLOC 8", expansion_patch)
        self.assertIn("ESP32_NATIVE_HCI_HLI_ACL_PREALLOC 4", expansion_patch)
        self.assertTrue(
            (ROOT / "platform/tools/unified_http_guestfwd.py").is_file()
        )

    def test_core2_eight_mib_psram_model_is_reconciled(self) -> None:
        evidence = json.loads(
            (
                ROOT
                / "tests/firmware/core2_psram_himem/"
                "evidence-2026-10-25-core2-himem-bank-switch-3x.json"
            ).read_text()
        )
        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(evidence["validation"], "virtual-device validation")
        self.assertEqual(evidence["attempts_requested"], 3)
        self.assertEqual(evidence["attempts_completed"], 3)
        self.assertEqual(evidence["attempts_passed"], 3)
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(len(evidence["runs"]), 3)
        for run in evidence["runs"]:
            self.assertEqual(run["status"], "PASS")
            self.assertEqual(run["machine_memory_bytes"], 8 << 20)
            self.assertEqual(run["physical_himem_bytes"], 4_456_448)
            self.assertEqual(run["reserved_mmu_bytes"], 262_144)
            self.assertTrue(all(run["checks"].values()))
        self.assertIn(
            "physical PSRAM capacity",
            evidence["boundary"]["not_claimed"],
        )

        sustained = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-8m-3x120.json"
            ).read_text()
        )
        self.assertEqual(sustained["status"], "PASS")
        self.assertEqual(sustained["attempts_requested"], 3)
        self.assertEqual(sustained["attempts_completed"], 3)
        self.assertEqual(sustained["attempts_passed"], 3)
        self.assertEqual(sustained["psram_gate"], "PASS")
        self.assertTrue(sustained["input_assets_unchanged_during_run"])
        self.assertEqual(
            [
                run["qom_memory_bytes"]
                for run in sustained["runs"]
            ],
            [8 << 20, 8 << 20, 8 << 20],
        )
        self.assertEqual(
            [
                run["psram"]["external_heap_total_bytes"]
                for run in sustained["runs"]
            ],
            [4 << 20, 4 << 20, 4 << 20],
        )
        self.assertEqual(
            [
                len(run["psram"]["sweeps"])
                for run in sustained["runs"]
            ],
            [35, 35, 35],
        )
        self.assertEqual(
            sustained["checks_per_attempt"]["psram_machine_capacity"],
            "PASS",
        )
        self.assertIn(
            "physical 8 MiB PSRAM capacity",
            sustained["boundary"]["not_claimed"],
        )
        self.assertRegex(
            sustained["tool_hashes"]["runner"],
            r"^[0-9a-f]{64}$",
        )
        device_group = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-25-core2-psram-device-group.json"
            ).read_text()
        )
        self.assertEqual(device_group["validation"], "virtual-device validation")
        self.assertEqual(device_group["status"], "PASS")
        self.assertEqual(device_group["cases_requested"], 6)
        self.assertEqual(device_group["cases_passed"], 6)
        self.assertEqual(device_group["checks_passed"], 24)
        self.assertEqual(device_group["effective_psram_mib"], 8)
        self.assertFalse(device_group["retry_used"])
        self.assertTrue(
            all(
                case["status"] == "PASS"
                for case in device_group["cases"].values()
            )
        )
        self.assertIn(
            "physical hardware validation",
            device_group["boundary"]["not_claimed"],
        )

        patch = (
            ROOT
            / "patches/qemu-m5stack-peripherals/"
            "0030-core2-eight-mib-psram.patch"
        ).read_text()
        for fragment in (
            "psram-size-mib",
            "requested_size <= 8 * MiB",
            "ESP32_PSRAM_PAGE_SIZE",
            "PRO_DRAM1_MMU_FIRST",
            "memory_region_set_alias_offset",
            "default_ram_size = 8 * MiB",
        ):
            self.assertIn(fragment, patch)

        service = (
            ROOT / "platform/tools/device_service.py"
        ).read_text()
        himem_readme = (
            ROOT / "tests/firmware/core2_psram_himem/README.md"
        ).read_text()
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        core2_doc = (DOCS / "core2-native-hci-backend.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        self.assertIn('SERVICE_MEMORY_OVERRIDES = {"core2": "8"}', service)
        self.assertIn("effective = 8", service)
        self.assertIn("same virtual window", himem_readme.lower())
        for text in (status, backlog, code_map, core2_doc, api):
            self.assertIn("8 MiB", text)
        self.assertIn("upper-bank", status.lower())
        self.assertIn("物理 PSRAM/cache timing", backlog)
        self.assertIn("core2_psram_himem", code_map)

        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        backend = (DOCS / "core2-native-hci-backend.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        index = (DOCS / "README.md").read_text()
        unified_readme = (
            ROOT / "tests/uiflow2/unified_core2/README.md"
        ).read_text()
        uiflow_index = (ROOT / "tests/uiflow2/README.md").read_text()
        device_readme = (
            ROOT / "devices/esp32-lx6/core2/README.md"
        ).read_text()
        device_json = (
            ROOT / "devices/esp32-lx6/core2/device.json"
        ).read_text()
        firmware_json = (
            ROOT / "devices/esp32-lx6/core2/firmware.json"
        ).read_text()
        catalog_source = json.loads(
            (ROOT / "devices/catalog.source.json").read_text()
        )
        profiles = json.loads(
            (ROOT / "platform/qemu/profiles.json").read_text()
        )
        source_core2 = next(
            device
            for device in catalog_source["devices"]
            if device["id"] == "core2"
        )
        profile_core2 = next(
            device for device in profiles["devices"] if device["id"] == "core2"
        )
        for text in (
            status,
            backlog,
            workstreams,
            backend,
            code_map,
            index,
            unified_readme,
            uiflow_index,
            device_readme,
            device_json,
            firmware_json,
        ):
            self.assertIn("PSRAM", text)
        for text in (device_readme, device_json, firmware_json, uiflow_index):
            self.assertNotIn("4 MiB QOM-effective", text)
            self.assertNotIn("35/35/36", text)
            self.assertNotIn("106 MiB", text)
        self.assertIn("物理板载 `8 MiB`", status)
        self.assertIn("物理 PSRAM/cache timing", backlog)
        self.assertIn(
            "core2-psram-sustained-8m-3x120.json",
            backend,
        )
        self.assertIn(
            "core2-psram-sustained-1x600.json",
            backend,
        )
        self.assertIn(
            "memory_validation",
            json.dumps(source_core2["runtime"]["validation"]),
        )
        self.assertIn(
            "memory_validation",
            json.dumps(profile_core2["validation"]),
        )
        self.assertIn(
            "120-second",
            source_core2["runtime"]["validation"]["memory_validation"],
        )
        self.assertIn(
            "120-second",
            profile_core2["validation"]["memory_validation"],
        )
        self.assertIn(
            "600-second",
            source_core2["runtime"]["validation"]["memory_validation"],
        )
        self.assertIn(
            "600-second",
            profile_core2["validation"]["memory_validation"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
