#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from collections import Counter

import project_snapshot

from _docs_contract_support import DocsContractBase, ROOT, DOCS


class DocsIndexContractTests(DocsContractBase):
    def test_required_contract_documents_exist(self) -> None:
        for relative in (
            "README.md",
            "AGENTS.md",
            "docs/README.md",
            "docs/engineering-handoff.md",
            "docs/workstreams.md",
            "docs/project-status.md",
            "docs/project-backlog.md",
            "docs/validation-ledger.md",
            "docs/project-snapshot.md",
            "docs/unified-device-runtime.md",
            "docs/runtime-model-gap-register.md",
            "docs/device-service-api.md",
            "docs/device-service.openapi.yaml",
            "docs/code-map.md",
            "docs/firmware-manifest.md",
            "docs/network-simulation-plan.md",
            "docs/network-lane.md",
            "docs/core2-native-hci-backend.md",
            "tests/README.md",
            "tests/network/README.md",
            "patches/README.md",
            "platform/README.md",
            "platform/tests/test_ble_probe.py",
            "platform/tests/fixtures/stale_doc_claims.json",
            "tests/uiflow2/README.md",
            "tests/uiflow2/core2_native_vhci/README.md",
            "tests/uiflow2/core2_native_hci/README.md",
            "tests/uiflow2/core2_native_hci/test_transport.py",
            "tests/uiflow2/core2_native_hci/test_guest_h2c.py",
            "tests/uiflow2/core2_native_hci/test_hli_event.py",
            "patches/qemu-core2-native-hci/0002-esp32-native-hci-hli-event.patch",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-diagnostic.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-safe-point-audit.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-controller-entry-audit.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-api-boundary-audit.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-queue-diagnostic.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-event-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci3b-hli-api-notification-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hli-api-gatt-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-service-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-extended-run-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-halted-gate-confirm-5x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold600-2x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-tb128-hold120-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold7200-artifact-bound-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-active-ble-hold7200-tb128-artifact-bound-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-accelerator-sampling-fail-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-hci4-reconnect121-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-reconnect2-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect2-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect5-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect20-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect30-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect60-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-hci4-reconnect10-timeout-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-oversize-att-mtu.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-active-stop-recovery-3x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-hli-preallocation-latency.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-pass-a.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-confirm-pass-b.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-peer-timeout-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-scan120-threshold-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-pass-a.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-3x120-confirm-pass-b.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc-4way-fail.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-pass-a.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-4x120-prealloc8x4-confirm-pass-b.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-concurrent-5x20-ack-observability.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-default-1x.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-summary.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-trace-summary.log",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-serial-summary.log",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-25-core2-ack-observability-peer-summary.log",
            "tests/uiflow2/evidence-2026-10-25-core2-hli-preallocation-full-matrix.json",
            "tests/uiflow2/evidence-2026-10-25-core2-0009-device-group.json",
            "tests/uiflow2/evidence-2026-10-25-core2-power-monitor-postboot-injection-fail.json",
            "tests/uiflow2/evidence-2026-10-25-core2-qom-boot-device-group.json",
            "tests/uiflow2/core2_native_hci/run_full.py",
            "tests/uiflow2/core2_native_hci/run_service_5x.py",
            "tests/uiflow2/core2_native_hci/run_service_teardown.py",
            "patches/qemu-core2-native-hci/0003-esp32-native-hci-api-transaction.patch",
            "patches/qemu-core2-native-hci/0004-xtensa-ccount-tb-yield.patch",
            "patches/qemu-core2-native-hci/0005-esp32-native-hci-guest-call-sregs.patch",
            "patches/qemu-core2-native-hci/0006-esp32-native-hci-observability.patch",
            "patches/qemu-core2-native-hci/0007-esp32-native-hci-require-valid-guest-queue.patch",
            "patches/qemu-core2-native-hci/0008-esp32-native-hci-preallocate-hli-objects.patch",
            "patches/qemu-core2-native-hci/0009-esp32-native-hci-expand-hli-preallocation.patch",
            "patches/qemu-core2-native-hci/0010-esp32-native-hci-ack-observability.patch",
            "patches/qemu-esp32c6-uiflow2-adapters/0006-espressif-riscv-reset-pmp.patch",
            "tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json",
            "tests/network/tls_allowlist/README.md",
            "tests/network/tls_allowlist/run_test.py",
            "tests/network/dns_cname_chain/README.md",
            "tests/network/dns_cname_chain/run_test.py",
            (
                "tests/network/dns_cname_chain/"
                "evidence-2026-10-25-controlled-cname-chain.json"
            ),
            "tests/network/cname_guest_lifecycle/README.md",
            "tests/network/cname_guest_lifecycle/boot.py",
            "tests/network/cname_guest_lifecycle/main.py",
            "tests/network/cname_guest_lifecycle/run_test.py",
            "tests/network/cname_guest_lifecycle/summarize_runs.py",
            (
                "tests/network/cname_guest_lifecycle/"
                "evidence-2026-10-25-cname-guest-lifecycle-3x.json"
            ),
            "tests/network/worker_cross_container/Dockerfile",
            "tests/network/worker_cross_container/README.md",
            "tests/network/worker_cross_container/run_test.py",
            "tests/network/worker_cross_container/summarize_runs.py",
            (
                "tests/network/worker_cross_container/"
                "evidence-2026-10-25-cross-container-qemu-3x.json"
            ),
            "platform/tools/worker_discovery.py",
            "platform/tools/worker_discovery_seed.py",
            "tests/network/worker_discovery/README.md",
            "tests/network/worker_discovery/run_test.py",
            "tests/network/worker_discovery/evidence-2026-10-25-discovery-rotation-pass.json",
            "tests/network/worker_discovery_seed/README.md",
            "tests/network/worker_discovery_seed/run_test.py",
            "tests/network/worker_discovery_seed/summarize_runs.py",
            (
                "tests/network/worker_discovery_seed/"
                "evidence-2026-10-25-seed-nat-3x.json"
            ),
            "tests/network/worker_partition_fencing/README.md",
            "tests/network/worker_partition_fencing/runtime_fixture.py",
            "tests/network/worker_partition_fencing/run_test.py",
            "tests/network/worker_partition_fencing/summarize_runs.py",
            (
                "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-3x.json"
            ),
            (
                "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-qemu-3x.json"
            ),
            (
                "tests/network/worker_partition_fencing/"
                "evidence-2026-10-25-partition-fencing-unified-3x.json"
            ),
            (
                "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-25-core2-psram-sustained-8m-3x120.json"
            ),
            (
                "tests/uiflow2/"
                "evidence-2026-10-25-core2-psram-device-group.json"
            ),
            "tests/network/wrong_password/README.md",
            "tests/network/wrong_password/run_test.py",
            "tests/network/wrong_password/evidence-2026-10-24-wrong-password-pass.json",
            "tests/network/idf_dns_udp/evidence-2026-10-24-dns-udp-pass.json",
            "tests/network/core2_openmac_wifi/README.md",
            "tests/network/core2_openmac_wifi/evidence-2026-10-24-deterministic-5x.json",
            "tests/network/egress_allowlist/README.md",
            "tests/network/egress_allowlist/run_test.py",
            "tests/network/idf_dhcp_renewal/README.md",
            "tests/network/idf_dhcp_renewal/run_test.py",
            "tests/network/ipv6_end_to_end/README.md",
            "tests/network/ipv6_end_to_end/boot.py",
            "tests/network/ipv6_end_to_end/main.py",
            "tests/network/ipv6_end_to_end/run_test.py",
            "tests/network/ipv6_end_to_end/uiflow2-sticks3-ipv6-test-build.patch",
            "tests/network/ipv6_end_to_end/evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json",
            "tests/network/ipv6_end_to_end/evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json",
            "platform/tools/network_fabric.py",
            "platform/tools/transport_security.py",
            "platform/tools/worker_registry.py",
            "platform/tools/worker_directory.py",
            "platform/tools/worker_queue.py",
            "platform/tools/worker_auth.py",
            "platform/tools/worker_agent.py",
            "platform/tools/nvs_image.py",
            "platform/tools/qemu_accel.py",
            "platform/tools/ble_runtime_limits.py",
            "platform/tests/test_ble_runtime_limits.py",
            "platform/tests/test_network_fabric.py",
            "platform/tests/test_transport_security.py",
            "platform/tests/test_worker_registry.py",
            "platform/tests/test_worker_directory.py",
            "platform/tests/test_worker_queue.py",
            "platform/tests/test_worker_auth.py",
            "platform/tests/test_worker_agent.py",
            "platform/tests/test_nvs_image.py",
            "platform/tests/test_worker_cross_netns_paths.py",
            "tests/network/lab_fabric/README.md",
            "tests/network/lab_fabric/run_test.py",
            "tests/network/lab_fabric/check_fabric.py",
            "tests/network/lab_fabric/role_a/boot.py",
            "tests/network/lab_fabric/role_a/main.py",
            "tests/network/lab_fabric/role_b/boot.py",
            "tests/network/lab_fabric/role_b/main.py",
            "tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json",
            "patches/qemu-m5stack-peripherals/0028-esp32-wifi-dual-guest-fabric.patch",
            "patches/qemu-m5stack-peripherals/0029-esp32s3-wpa2-psk-data-plane.patch",
            "tests/network/worker_lifecycle/README.md",
            "tests/network/worker_lifecycle/run_test.py",
            "tests/network/worker_lifecycle/evidence-2026-10-24-pass.json",
            "tests/network/worker_queue/README.md",
            "tests/network/worker_queue/evidence-2026-10-24-queue-pass.json",
            "tests/network/worker_executor/README.md",
            "tests/network/worker_executor/evidence-2026-10-24-executor-pass.json",
            "tests/network/worker_executor/evidence-2026-10-24-executor-auth-pass.json",
            "tests/network/worker_tls/README.md",
            "tests/network/worker_tls/run_test.py",
            "tests/network/worker_tls/run_rotation_test.py",
            "tests/network/worker_tls/evidence-2026-10-24-tls-mtls-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-security-rotation-job-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json",
            "tests/network/worker_tls/evidence-2026-10-24-fleet-credential-migration-pass.json",
            "tests/network/worker_tls/run_fleet_migration_test.py",
            "tests/network/worker_cross_netns/README.md",
            "tests/network/worker_cross_netns/run_test.py",
            "tests/network/worker_cross_netns/evidence-2026-10-25-worker-local-qemu-cross-netns-pass.json",
            "tests/network/worker_reattach/README.md",
            "tests/network/worker_reattach/evidence-2026-10-24-reattach-pass.json",
            (
                "tests/network/worker_runtime_restart/"
                "evidence-2026-10-25-runtime-companion-continuity-pass.json"
            ),
            "tests/network/tls_allowlist/evidence-2026-10-23-blocked.json",
            "tests/network/tls_allowlist/evidence-2026-10-23-pass.json",
            "tests/network/tls_allowlist/evidence-2026-10-24-linux-namespace-pass.json",
            "tests/network/tls_allowlist/evidence-2026-10-24-controlled-dns-pass.json",
            "tests/network/tls_allowlist/evidence-2026-10-24-ip-port-nftables-pass.json",
            "tests/network/egress_allowlist/evidence-2026-10-24-ip-port-pass.json",
            "tests/network/egress_allowlist/evidence-2026-10-24-github-actions-pass.json",
            "tests/network/idf_dhcp_renewal/evidence-2026-10-24-renewal-pass.json",
            "tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-pass.json",
            "tests/network/reconnect_probe/README.md",
            "tests/network/reconnect_probe/run_test.py",
            "tests/network/reconnect_probe/evidence-2026-10-24-radio-loss-recovery-pass.json",
            "tests/uiflow2/evidence-2026-10-23-zero-retry-matrix.json",
            "tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json",
            "tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json",
            "tests/firmware/evidence-2026-10-23-static-review.json",
            "tests/firmware/evidence-2026-10-24-filesystem-inventory.json",
            "tests/firmware/evidence-2026-10-24-fat-inventory.json",
            "tests/firmware/evidence-2026-10-24-spiffs-inventory.json",
            "tests/firmware/evidence-2026-10-24-filesystem-permission-policy.json",
            "tests/firmware/evidence-2026-10-24-source-license-scan.json",
            "tests/firmware/evidence-2026-10-24-core2-axp-i2c-trace.json",
            "tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json",
            "tests/firmware/evidence-2026-10-25-core2-wdt-timing.json",
            "tests/firmware/evidence-2026-10-24-efuse-security.json",
            "tests/firmware/secure_boot_image/README.md",
            "tests/firmware/secure_boot_image/run_test.py",
            "tests/firmware/evidence-2026-10-25-secure-boot-image.json",
            "tests/firmware/evidence-2026-10-24-license-policy.json",
            "tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json",
            "tests/firmware/evidence-2026-10-24-webburner-ui.json",
            "tests/firmware/evidence-2026-10-24-public-manifest-web-conformance.json",
            "tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json",
            "tests/firmware/evidence-2026-10-24-c6-soft-reset-flash-addressing.json",
            "tests/firmware/evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json",
            "tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json",
            "tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json",
            "tests/firmware/evidence-2026-10-25-image-capability-observation.json",
            "tests/firmware/evidence-2026-10-25-webburner-capability-display.json",
            "tests/firmware/image_capability_observation/README.md",
            "tests/firmware/image_capability_observation/run_test.py",
            "tests/uiflow2/evidence-2026-10-25-s3-wpa2-regression.json",
            "tests/firmware/openai_nvs_precondition/README.md",
            "tests/firmware/openai_nvs_precondition/run_test.py",
            "tests/firmware/core2_psram_himem/CMakeLists.txt",
            "tests/firmware/core2_psram_himem/main/CMakeLists.txt",
            "tests/firmware/core2_psram_himem/main/app_main.c",
            "tests/firmware/core2_psram_himem/sdkconfig.defaults",
            "tests/firmware/core2_psram_himem/README.md",
            "tests/firmware/core2_psram_himem/run_test.py",
            (
                "tests/firmware/core2_psram_himem/"
                "evidence-2026-10-25-core2-himem-bank-switch-3x.json"
            ),
            "platform/tests/test_core2_psram_himem_runner.py",
            (
                "patches/qemu-m5stack-peripherals/"
                "0030-core2-eight-mib-psram.patch"
            ),
            "patches/qemu-m5stack-peripherals/0031-core2-shared-board-i2c.patch",
            "patches/qemu-m5stack-peripherals/0032-esp32-timg-wdt-trace.patch",
            (
                "patches/qemu-m5stack-peripherals/"
                "0034-xtensa-ccompare-equal-deadline.patch"
            ),
            "patches/qemu-m5stack-peripherals/0035-esp32-timg-wdt-int-ena.patch",
            "patches/qemu-m5stack-peripherals/0036-ssi-transfer-buf.patch",
            "patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch",
            (
                "tests/firmware/"
                "evidence-2026-10-26-core2-qio-crosscore-diagnostic.json"
            ),
            "tests/firmware/evidence-2026-10-26-core2-ssi-transfer-buf.json",
            "tests/firmware/core2_handoff_trace/README.md",
            "tests/firmware/core2_handoff_trace/summarize.py",
            "tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py",
            "patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch",
            "patches/qemu-m5stack-peripherals/0039-esp32-handoff-state-dump.patch",
            "patches/qemu-m5stack-peripherals/0040-xtensa-handoff-pc-trace.patch",
            (
                "tests/firmware/core2_handoff_trace/"
                "pc-symbolization-2026-10-26-core2-handoff.json"
            ),
            (
                "tests/firmware/core2_handoff_trace/"
                "evidence-2026-10-26-core2-pc-mapping-audit.json"
            ),
            (
                "tests/firmware/core2_handoff_trace/"
                "evidence-2026-10-26-core2-handoff-pause.json"
            ),
            (
                "tests/firmware/core2_handoff_trace/"
                "evidence-2026-10-26-core2-handoff-state-sweep.json"
            ),
            (
                "tests/firmware/core2_handoff_trace/"
                "evidence-2026-10-26-core2-handoff-pc-trace.json"
            ),
            (
                "tests/firmware/core2_handoff_trace/"
                "evidence-2026-10-26-core2-handoff-timeline.json"
            ),
            "platform/tests/test_core2_handoff_trace.py",
            "platform/tests/test_core2_pc_mapping_audit.py",
            "platform/tests/test_core2_handoff_pause.py",
            "platform/tests/test_core2_handoff_state_sweep.py",
            "platform/tests/test_core2_handoff_pc_trace.py",
            "tests/firmware/core2_handoff_trace/run_pause_sweep.py",
            "tests/firmware/core2_handoff_trace/run_pc_trace.py",
            "tests/firmware/c6_zigbee_thread_sim/README.md",
            "tests/firmware/c6_zigbee_thread_sim/run_feasibility.py",
            "tests/firmware/README.md",
            "platform/web/firmware.html",
            "platform/web/firmware.css",
            "platform/web/firmware.js",
            "platform/web/firmware-report.js",
            "platform/web/firmware-upload.js",
            "platform/web/sha256.js",
            "platform/tests/test_firmware_upload.mjs",
            "platform/tests/test_sha256.mjs",
            "docs/images/webburner-capability-observation.jpg",
            "patches/qemu-core2-openmac-wifi/README.md",
            "patches/qemu-core2-ble-controller/README.md",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_documentation_index_covers_every_document(self) -> None:
        index = (DOCS / "README.md").read_text()
        linked = set(
            re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", index)
        )
        freshness = index.split("## 新鲜度台账", 1)[1].split(
            "## 入口索引", 1
        )[0]
        freshness_linked = set(
            re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", freshness)
        )
        freshness_rows: set[str] = set()
        for line in freshness.splitlines():
            if not line.startswith("| ["):
                continue
            cells = [cell.strip() for cell in line.split("|")]
            self.assertGreaterEqual(len(cells), 5)
            self.assertRegex(
                cells[3],
                r"`\d{4}-\d{2}-\d{2}`",
                f"freshness row lacks a date: {line}",
            )
            freshness_rows.update(
                re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", cells[1])
            )
        self.assertEqual(freshness_rows, freshness_linked)
        for path in sorted(DOCS.rglob("*.md")):
            relative = path.relative_to(DOCS).as_posix()
            if relative == "README.md":
                continue
            self.assertIn(relative, linked, relative)
            self.assertIn(relative, freshness_linked, relative)

    def test_documentation_index_has_no_duplicate_links_per_section(self) -> None:
        text = (DOCS / "README.md").read_text()
        headings = list(re.finditer(r"(?m)^(##+ .+)$", text))
        for index, heading in enumerate(headings):
            end = (
                headings[index + 1].start()
                if index + 1 < len(headings)
                else len(text)
            )
            body = text[heading.end() : end]
            links = re.findall(
                r"\]\(([^)#]+\.md)(?:#[^)]*)?\)",
                body,
            )
            duplicates = sorted(
                link for link, count in Counter(links).items() if count > 1
            )
            self.assertEqual(
                duplicates,
                [],
                f"{heading.group(1)} has duplicate document links",
            )

    def test_authority_documents_do_not_repeat_long_lines(self) -> None:
        for relative in (
            "docs/project-status.md",
            "docs/project-backlog.md",
            "docs/engineering-handoff.md",
            "docs/workstreams.md",
        ):
            lines = [
                line.strip()
                for line in (ROOT / relative).read_text().splitlines()
                if len(line.strip()) >= 100
            ]
            duplicates = sorted(
                line for line, count in Counter(lines).items() if count > 1
            )
            self.assertEqual(
                duplicates,
                [],
                f"{relative} repeats long prose lines",
            )

    def test_project_snapshot_exposes_document_freshness_audit(self) -> None:
        snapshot = project_snapshot.collect()
        audit = snapshot["document_audit"]
        coverage = snapshot["document_coverage"]
        self.assertEqual(audit["total"], len(snapshot["documents"]))
        self.assertEqual(
            sum(audit["categories"].values()),
            audit["total"],
        )
        self.assertEqual(
            audit["current"] + audit["historical"],
            audit["total"],
        )
        self.assertEqual(
            coverage["total"],
            snapshot["code_inventory"]["documented_markdown_files"],
        )
        self.assertEqual(
            sum(coverage["categories"].values()),
            coverage["total"],
        )
        self.assertEqual(
            coverage["categories"]["authority"],
            audit["total"],
        )
        self.assertEqual(coverage["categories"]["navigation"], 1)
        self.assertEqual(
            coverage["older_delegated"],
            sorted(
                coverage["older_delegated"],
                key=lambda row: (row["reviewed"], row["page"]),
            ),
        )
        for row in coverage["older_delegated"]:
            self.assertLess(row["reviewed"], snapshot["fact_date"])
            self.assertNotIn(
                row["category"],
                {"authority", "record"},
                "authority pages are tracked by older_current instead",
            )
        rendered = project_snapshot.render_markdown(snapshot)
        self.assertIn("## 文档与测试", rendered)
        self.assertIn("文档职责分布", rendered)
        self.assertIn("全量文档盘点", rendered)
        if coverage["older_delegated"]:
            self.assertIn("带显式旧复核日期的委派文档", rendered)
        else:
            self.assertIn("没有带显式旧复核日期的委派文档", rendered)
        if audit["older_current"]:
            self.assertIn("复核日期早于当前事实日期的非历史页", rendered)
        else:
            self.assertIn(
                "所有非历史页的最近复核日期均与当前事实日期一致",
                rendered,
            )

    def test_project_snapshot_separates_catalog_and_fact_dates(self) -> None:
        snapshot = project_snapshot.collect()
        self.assertRegex(snapshot["catalog_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(snapshot["fact_date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertGreaterEqual(
            snapshot["fact_date"],
            snapshot["latest_evidence_date"],
            "the project fact date must cover the newest committed evidence",
        )
        self.assertGreaterEqual(
            snapshot["fact_date"],
            snapshot["catalog_date"],
            "the project fact date must cover the device catalog",
        )
        for relative in (
            "docs/README.md",
            "docs/project-status.md",
            "docs/project-backlog.md",
            "docs/validation-ledger.md",
            "docs/engineering-handoff.md",
        ):
            reviewed = project_snapshot.document_date(ROOT / relative)
            self.assertLessEqual(
                reviewed,
                snapshot["fact_date"],
                f"{relative} is dated after the generated project fact date",
            )
        rendered = project_snapshot.render_markdown(snapshot)
        self.assertIn(
            f"设备目录日期：`{snapshot['catalog_date']}`",
            rendered,
        )
        self.assertIn(
            f"当前事实复核：`{snapshot['fact_date']}`",
            rendered,
        )

    def test_project_snapshot_line_count_is_not_self_referential(self) -> None:
        snapshot = project_snapshot.collect()
        excluded = snapshot["code_inventory"]["documented_markdown_lines_exclude"]
        self.assertEqual(excluded, ["docs/project-snapshot.md"])
        expected_lines = sum(
            len(path.read_text(errors="replace").splitlines())
            for path in project_snapshot.document_paths()
            if path != DOCS / "project-snapshot.md"
        )
        self.assertEqual(
            snapshot["code_inventory"]["documented_markdown_lines"],
            expected_lines,
        )

    def test_project_snapshot_ignores_untracked_runtime_docs(self) -> None:
        paths = {
            path.relative_to(ROOT).as_posix()
            for path in project_snapshot.document_paths()
        }
        self.assertIn("platform/README.md", paths)
        self.assertIn(
            "records/2026-10-22-peripheral-simulation-hardening/README.md",
            paths,
        )
        self.assertNotIn(".pytest_cache/README.md", paths)
        self.assertNotIn(
            "platform/tests/node_modules/playwright/README.md",
            paths,
        )
        self.assertNotIn("upstream/esp-emulator/README.md", paths)

    def test_project_snapshot_preserves_trailing_inline_code(self) -> None:
        tasks = {
            task["id"]: task
            for task in project_snapshot.parse_backlog_tasks()
        }
        self.assertIn(
            "物理 PSRAM/cache timing",
            tasks["CORE2-02"]["next"],
        )

    def test_project_snapshot_is_current(self) -> None:
        snapshot = project_snapshot.collect()
        rendered = project_snapshot.render_markdown(snapshot)
        checked_in = (DOCS / "project-snapshot.md").read_text()
        self.assertEqual(
            rendered,
            checked_in,
            "docs/project-snapshot.md is stale; run "
            "`python3 platform/tools/project_snapshot.py --write`",
        )
        self.assertIn(
            f"设备登记：`{snapshot['devices_total']}` 台",
            checked_in,
        )
        self.assertIn("## Backlog Task 板", checked_in)
        self.assertIn("## 代码与文档规模", checked_in)
        self.assertIn("`CORE2-02`", checked_in)
        core2 = next(
            device
            for device in snapshot["devices"]
            if device["id"] == "core2"
        )
        self.assertGreater(len(core2["blockers"]), 1)
        for blocker in core2["blockers"]:
            self.assertIn(blocker, checked_in)

    def test_relative_markdown_links_exist(self) -> None:
        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "platform" / "README.md",
            ROOT / "devices" / "README.md",
            *sorted((ROOT / "devices").rglob("README.md")),
            *sorted((ROOT / "devices").rglob("README.extra.md")),
            *sorted(DOCS.rglob("*.md")),
            *sorted((ROOT / "tests").rglob("README.md")),
            *sorted((ROOT / "patches").rglob("README.md")),
        ]
        pattern = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")
        for path in paths:
            for match in pattern.finditer(path.read_text(errors="replace")):
                raw = match.group(1).strip().split()[0].strip("<>")
                if not raw or raw.startswith(("#", "http://", "https://", "mailto:")):
                    continue
                target = raw.split("#", 1)[0]
                if not target or any(char in target for char in "{}$"):
                    continue
                self.assertTrue(
                    (path.parent / target).resolve().exists(),
                    f"{path.relative_to(ROOT)} -> {raw}",
                )

    def test_executable_test_and_patch_directories_have_readmes(self) -> None:
        for lane in ("uiflow2", "network", "firmware"):
            root = ROOT / "tests" / lane
            for directory in sorted(path for path in root.iterdir() if path.is_dir()):
                if directory.name.startswith((".", "__")):
                    continue
                executable = any(
                    path.is_file()
                    for pattern in ("run_*.py", "test_*.py")
                    for path in directory.glob(pattern)
                )
                if executable:
                    self.assertTrue(
                        (directory / "README.md").is_file(),
                        f"{directory.relative_to(ROOT)} has an executable test "
                        "but no README.md",
                    )

        for directory in sorted(
            path for path in (ROOT / "patches").iterdir() if path.is_dir()
        ):
            if any(directory.glob("*.patch")):
                self.assertTrue(
                    (directory / "README.md").is_file(),
                    f"{directory.relative_to(ROOT)} has patches but no README.md",
                )

    def test_obsolete_current_status_claims_are_absent(self) -> None:
        active = "\n".join(
            path.read_text(errors="replace")
            for path in (
                ROOT / "README.md",
                ROOT / "AGENTS.md",
                ROOT / "platform" / "README.md",
                ROOT / "tests" / "uiflow2" / "README.md",
                ROOT / "tests" / "network" / "core2_openmac_wifi" / "README.md",
                ROOT / "tests" / "network" / "egress_allowlist" / "README.md",
                ROOT / "tests" / "network" / "idf_dhcp_renewal" / "README.md",
                ROOT / "tests" / "network" / "core2_openeth" / "README.md",
                ROOT / "tests" / "network" / "worker_cross_netns" / "README.md",
                ROOT / "tests" / "uiflow2" / "sticks3_peripherals" / "README.md",
                ROOT / "tests" / "README.md",
                ROOT / "tests" / "network" / "README.md",
                ROOT / "patches" / "README.md",
                ROOT / "patches" / "qemu-core2-openmac-wifi" / "README.md",
                ROOT / "patches" / "qemu-core2-ble-controller" / "README.md",
                ROOT / "patches" / "qemu-multi-board-uiflow2" / "README.md",
                ROOT / "patches" / "qemu-esp32c6-uiflow2-adapters" / "README.md",
                *sorted(DOCS.glob("*.md")),
                *sorted(DOCS.glob("*.yaml")),
            )
        )
        catalog = json.loads(
            (
                ROOT
                / "platform/tests/fixtures/stale_doc_claims.json"
            ).read_text()
        )
        self.assertEqual(catalog["schema_version"], 1)
        self.assertTrue(catalog["purpose"])
        self.assertTrue(catalog["authorities"])
        self.assertIn("docs/project-status.md", catalog["authorities"])
        self.assertIn("docs/project-backlog.md", catalog["authorities"])
        self.assertIn("docs/validation-ledger.md", catalog["authorities"])
        self.assertIn("docs/runtime-model-gap-register.md", catalog["authorities"])
        for authority in catalog["authorities"]:
            self.assertTrue((ROOT / authority).is_file(), authority)
        self.assertTrue(catalog["claims"])
        claim_ids = [claim["id"] for claim in catalog["claims"]]
        claim_texts = [claim["text"] for claim in catalog["claims"]]
        self.assertEqual(len(claim_ids), len(set(claim_ids)))
        self.assertEqual(len(claim_texts), len(set(claim_texts)))
        for claim in catalog["claims"]:
            self.assertRegex(claim["id"], r"^STALE-\d{3}$")
            self.assertTrue(claim["text"].strip())
            self.assertTrue(claim["reason"].strip())
            self.assertNotIn(claim["text"], active)

    def test_agents_does_not_duplicate_mutable_project_counts(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text()
        for pattern in (
            r"\b\d+\s+unified profiles\b",
            r"\b\d+\s+(?:public\s+)?samples\b",
            r"\b\d+/\d+\s+(?:PASS|cases?)\b",
        ):
            self.assertIsNone(
                re.search(pattern, agents, re.IGNORECASE),
                f"AGENTS.md must link mutable counts instead of copying them: {pattern}",
            )
        for authority in (
            "docs/project-status.md",
            "docs/project-backlog.md",
            "docs/validation-ledger.md",
            "docs/runtime-model-gap-register.md",
            "docs/project-snapshot.md",
        ):
            self.assertIn(authority, agents)


if __name__ == "__main__":
    unittest.main(verbosity=2)
