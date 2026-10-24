#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

import project_snapshot

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsConsistencyTests(unittest.TestCase):
    def _platform_test_count(self) -> int:
        suite = unittest.TestLoader().discover(
            str(ROOT / "platform" / "tests"),
            pattern="test_*.py",
        )
        return suite.countTestCases()

    def test_required_contract_documents_exist(self) -> None:
        for relative in (
            "README.md",
            "AGENTS.md",
            "docs/README.md",
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
            "platform/README.md",
            "platform/tests/test_ble_probe.py",
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
            "tests/uiflow2/core2_native_hci/run_full.py",
            "tests/uiflow2/core2_native_hci/run_service_5x.py",
            "patches/qemu-core2-native-hci/0003-esp32-native-hci-api-transaction.patch",
            "patches/qemu-core2-native-hci/0004-xtensa-ccount-tb-yield.patch",
            "patches/qemu-core2-native-hci/0005-esp32-native-hci-guest-call-sregs.patch",
            "patches/qemu-core2-native-hci/0006-esp32-native-hci-observability.patch",
            "patches/qemu-esp32c6-uiflow2-adapters/0006-espressif-riscv-reset-pmp.patch",
            "tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json",
            "tests/network/tls_allowlist/README.md",
            "tests/network/tls_allowlist/run_test.py",
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
            "platform/tools/network_fabric.py",
            "platform/tools/transport_security.py",
            "platform/tools/worker_registry.py",
            "platform/tools/worker_directory.py",
            "platform/tools/worker_queue.py",
            "platform/tools/worker_auth.py",
            "platform/tools/worker_agent.py",
            "platform/tests/test_network_fabric.py",
            "platform/tests/test_transport_security.py",
            "platform/tests/test_worker_registry.py",
            "platform/tests/test_worker_directory.py",
            "platform/tests/test_worker_queue.py",
            "platform/tests/test_worker_auth.py",
            "platform/tests/test_worker_agent.py",
            "tests/network/lab_fabric/README.md",
            "tests/network/lab_fabric/run_test.py",
            "tests/network/lab_fabric/check_fabric.py",
            "tests/network/lab_fabric/role_a/boot.py",
            "tests/network/lab_fabric/role_a/main.py",
            "tests/network/lab_fabric/role_b/boot.py",
            "tests/network/lab_fabric/role_b/main.py",
            "tests/network/lab_fabric/evidence-2026-10-24-two-guest-pass.json",
            "patches/qemu-m5stack-peripherals/0028-esp32-wifi-dual-guest-fabric.patch",
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
            "tests/network/worker_reattach/README.md",
            "tests/network/worker_reattach/evidence-2026-10-24-reattach-pass.json",
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
            "tests/firmware/evidence-2026-10-24-efuse-security.json",
            "tests/firmware/evidence-2026-10-24-license-policy.json",
            "tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json",
            "tests/firmware/evidence-2026-10-24-webburner-ui.json",
            "tests/firmware/evidence-2026-10-24-public-manifest-web-conformance.json",
            "tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json",
            "tests/firmware/evidence-2026-10-24-c6-soft-reset-flash-addressing.json",
            "tests/firmware/evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json",
            "tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json",
            "tests/firmware/c6_zigbee_thread_sim/README.md",
            "tests/firmware/c6_zigbee_thread_sim/run_feasibility.py",
            "tests/firmware/README.md",
            "platform/web/firmware.html",
            "platform/web/firmware.css",
            "platform/web/firmware.js",
            "platform/web/firmware-upload.js",
            "platform/web/sha256.js",
            "platform/tests/test_firmware_upload.mjs",
            "platform/tests/test_sha256.mjs",
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
        self.assertIn("`CORE2-02`", checked_in)

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
        self.assertEqual(evidence["observations"]["chip_id_value"], "0x4a")
        self.assertTrue(evidence["observations"]["successful_axp_start"])
        self.assertFalse(
            evidence["observations"][
                "subsequent_axp_bus_transaction_observed"
            ]
        )
        self.assertEqual(
            evidence["classification"]["code"],
            "i2c_driver_or_bus_handoff_gap",
        )
        register = (DOCS / "runtime-model-gap-register.md").read_text()
        self.assertIn("chip id `0x4a`", register)
        self.assertIn("bus ownership", register)

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
                ROOT / "tests" / "uiflow2" / "sticks3_peripherals" / "README.md",
                ROOT / "patches" / "qemu-core2-openmac-wifi" / "README.md",
                ROOT / "patches" / "qemu-core2-ble-controller" / "README.md",
                ROOT / "patches" / "qemu-multi-board-uiflow2" / "README.md",
                ROOT / "patches" / "qemu-esp32c6-uiflow2-adapters" / "README.md",
                *sorted(DOCS.glob("*.md")),
            )
        )
        for stale in (
            "网络模拟尚未接入统一设备服务",
            "CoreS3's stock UIFlow2 board initialization still needs separate",
            "same-instance board + WiFi model only if later required",
            "network simulation has not yet been integrated",
            "network namespaces and packet capture",
            "current full matrix  NOT RUN after 7823bef",
            "发布级“当前全矩阵”仍为 `NOT RUN`",
            "连续 3/3 首轮 PASS",
            "cache/WDT startup instability remains a known simulation-only blocker",
            "原生 BT controller 外部 peer/GATT 仍为 NOT RUN",
            "native-controller peer/GATT remains `NOT RUN`",
            "GDB bridge 仍未进入 Device Service",
            "Device Service integration of the bridge",
            "Service production bridge",
            "single-lease integration remains",
            "GDB-based runners are not yet exposed as a Device Service runtime",
            "not yet part of this unified lease",
            "retries by default five times",
            "cache startup panic is still intermittent",
            "DNS, external internet access and BLE are not covered",
            "the ST7789 panel first frame is still black",
            "It does not yet validate the first frame",
            "TLS fixture 在当前 S3 QEMU 上停在",
            "currently stalls while creating",
            "TLS/Host allowlist fixture is wired but blocked",
            "Linux namespace TLS remains `NOT RUN`",
            "Linux namespace TLS、可控 resolver",
            "继续补可控 resolver",
            "网络模拟暂不开放",
            "DNS requests, external internet access and BLE remain `NOT RUN`",
            "QOM injection runs without pausing the guest to avoid the known Core2 cache/watchdog failure",
            "PSRAM/cache stability remains",
            "It does not yet prove over-the-air advertising, external discovery",
            "FAT inventory is not implemented",
            "SPIFFS/FAT 解包",
            "FAT/SPIFFS 返回可验证清单",
            "This is not a generic destination-IP/port allowlist",
            "通用 destination allowlist",
            "still not prove arbitrary destination IP/port",
            "DHCP renewal remains `NOT RUN`",
            "DHCP renewal has not been validated",
            "仍不是任意 公网目标 IP/端口 allowlist",
            "generic allowlisted egress and object-backed",
            "文件系统提取、敏感资产/权限审批",
            "243/243",
            "guest VHCI 未接入",
            "`243` 项",
            "`7f8343d",
            "6.8k 行",
            "6840 行",
            "6843 行",
            "WebBurner UI 未接线",
            "WebBurner UI 接线仍开放",
            "WebBurner UI 尚未调用 chunk API",
            "双设备 fabric、自托管 QEMU worker、外部 IPv6",
            "自托管 QEMU worker、双设备 fabric 和外部 IPv6 仍待补",
            "`NET-03` 双设备 fabric",
            "external IPv6 egress 和双设备 lab fabric 仍开放",
            "external IPv6/CIDR/domain-set allowlisting and multi-device lab fabric",
            "下一步是 `NET-03` 双设备 fabric",
            "two-device lab fabric and external",
            "现网 Agent Review API 已具备",
            "| `HCI-3a` C2H callback | `PASS` |",
            "SPIFFS 仍 `UNSUPPORTED`",
            "SPIFFS 目前只做分区识别",
            "SPIFFS inventory is not implemented",
            "SPIFFS 解包",
            "HLI 尚未投递真实 controller event",
            "but no real HCI event or ACL packet was delivered",
            "同 guest 重连已通过",
            "repeated in-guest reconnect PASS",
            "same-guest disconnect lifecycle fails before re-advertising",
            "The stock Core2 guest currently returns aggregate `FAIL`",
            "stock guest reproduces without the test-only re-advertise call",
            "more than two reconnect cycles",
            "more than two connection cycles",
            "证书/worker 凭据热轮换",
            "Certificate and worker credential hot rotation",
            "certificate and worker credential hot rotation",
            "Certificates and keys are loaded at process start; hot rotation is not implemented",
            "hot rotation is not implemented",
            "零中断 request draining",
            "Existing requests are not drained",
            "request draining remain open",
            "凭据重叠/客户端批量迁移",
            "credential overlap/client-fleet migration",
            "超过十轮连接",
            "more than ten reconnect cycles",
            "keeps the Core2 WiFi path `PARTIAL`",
            "accelerometer/gyroscope values: PARTIAL",
            "暂用 `-m 0` 规避 PSRAM/cache 稳定性问题",
            "Both gaps are still `OPEN`",
            "两个 `runtime_model_gap` 仍为 `OPEN`",
            "C6 LP_SW_HPSYS software reset can lose the expected chip id (RUNTIME-01)",
            "`RUNTIME-01` 复位/eFuse/寄存器语义",
            "| `CORE2-02` 30-cycle extension | `NOT RUN` |",
            "| `CORE2-02` 60-cycle extension | `NOT RUN` |",
            "| `CORE2-02` 120-cycle extension | `NOT RUN` |",
            "3 个独立 lease、每个 30 轮的下一门禁",
            "Automated discovery and migration of a client fleet is still",
            "Automated client-fleet migration, production",
            "自动化客户端批量迁移、跨主机 QEMU executor",
        ):
            self.assertNotIn(stale, active)

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
        self.assertEqual(register.count("| 状态 | `OPEN` |"), 3)
        self.assertEqual(
            register.count(
                "| 状态 | `FIXED`（virtual-device validation） |"
            ),
            1,
        )
        self.assertIn("RUNTIME-01", register)
        self.assertIn("RUNTIME-02", register)
        self.assertIn("RUNTIME-03", register)
        self.assertIn("RUNTIME-04", register)
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
        for text in (status, backlog, workstreams, firmware_matrix):
            self.assertIn("RUNTIME-01", text)
            self.assertIn("RUNTIME-02", text)
            self.assertIn("RUNTIME-03", text)
            self.assertIn("RUNTIME-04", text)
        self.assertIn(
            "runtime-model-gap-register.md",
            status,
        )
        self.assertIn(
            "historical snapshot classified both samples",
            firmware_matrix,
        )
        self.assertIn(
            "不把“已分类”算成该任务完成",
            backlog,
        )

    def test_core2_reconnect_evidence_is_reconciled(self):
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        adaptation_matrix = (
            DOCS / "qemu-device-adaptation-matrix.md"
        ).read_text()
        core2_backend = (DOCS / "core2-native-hci-backend.md").read_text()
        runtime_contract = (DOCS / "unified-device-runtime.md").read_text()
        project_snapshot = (DOCS / "project-snapshot.md").read_text()
        catalog_source = json.loads(
            (ROOT / "devices/catalog.source.json").read_text()
        )
        generated_catalog = json.loads(
            (ROOT / "devices/catalog.json").read_text()
        )
        qemu_profiles = json.loads(
            (ROOT / "platform/qemu/profiles.json").read_text()
        )
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

        self.assertIn("3/3 PASS", status)
        self.assertIn("20/30/60/120", project_snapshot)
        self.assertIn("one Device Service lease", runtime_contract)
        self.assertIn("one guest instance", runtime_contract)
        self.assertIn("3 个独立 lease 各 120 轮", backlog)
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

        self.assertIn("MAX_BLE_RECONNECT_CYCLES = 120", limits)
        self.assertIn("MAX_BLE_HOLD_SECONDS = 7200", limits)
        self.assertIn(
            "MAX_BLE_LINGER_SECONDS = MAX_BLE_HOLD_SECONDS + 60",
            limits,
        )
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", service)
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", peer)
        self.assertIn("MAX_BLE_RECONNECT_CYCLES", runner)
        self.assertIn('"ble_reconnect_cycles": 120', service_tests)
        reconnect_schema = openapi.split(
            "ble_reconnect_cycles:",
            1,
        )[1].split("ble_reconnect_delay_seconds:", 1)[0]
        self.assertIn("maximum: 120", reconnect_schema)
        linger_schema = openapi.split(
            "ble_linger_seconds:",
            1,
        )[1].split("ble_reconnect_cycles:", 1)[0]
        self.assertIn("maximum: 7260", linger_schema)

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

        core2_source = next(
            device for device in catalog_source["devices"]
            if device["id"] == "core2"
        )
        source_detail = core2_source["runtime"]["validation"]["detail"]
        self.assertIn("分别完成 20、30、60、120 轮", source_detail)
        self.assertIn("3377/3377", source_detail)
        self.assertNotIn("更多轮次", source_detail)

        core2_profile = next(
            device for device in qemu_profiles["devices"]
            if device["id"] == "core2"
        )
        profile_detail = core2_profile["validation"]["detail"]
        self.assertIn("at 20, 30, 60 and 120 cycles", profile_detail)
        self.assertIn("3377/3377", profile_detail)
        self.assertNotIn("More than sixty", profile_detail)
        self.assertTrue(
            any(
                "more than one hundred twenty reconnect cycles" in blocker
                for blocker in core2_profile["blockers"]
            )
        )

        core2_generated = next(
            device for device in generated_catalog["devices"]
            if device["id"] == "core2"
        )
        self.assertEqual(
            core2_generated["runtime"]["validation"]["detail"],
            source_detail,
        )

    def test_worker_generation_pointer_migration_is_reconciled(self):
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        api = (DOCS / "device-service-api.md").read_text()
        tls_readme = (
            ROOT / "tests/network/worker_tls/README.md"
        ).read_text()
        evidence = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-fleet-credential-migration-pass.json"
            ).read_text()
        )

        self.assertEqual(evidence["status"], "PASS")
        self.assertEqual(len(evidence["fleet"]["workers"]), 2)
        self.assertEqual(
            set(evidence["fleet"]["receipts"]),
            set(evidence["fleet"]["workers"]),
        )
        self.assertIsNone(evidence["rotation"]["worker_reload_signal"])
        self.assertEqual(
            evidence["rotation"]["worker_credential_commit"],
            "atomic-generation-pointer-replacement",
        )
        self.assertTrue(
            all(value == "PASS" for value in evidence["checks"].values())
        )

        for text in (status, backlog, workstreams, api, tls_readme):
            self.assertIn("generation", text.lower())
        self.assertIn("secret-free receipt", status)
        self.assertIn("worker 主机自动发现", backlog)
        self.assertIn(
            "--credential-generation-file",
            api,
        )
        self.assertIn(
            "run_fleet_migration_test.py",
            tls_readme,
        )

    def test_current_status_snapshot_matches_contract(self) -> None:
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        source = json.loads((ROOT / "devices" / "catalog.source.json").read_text())
        catalog = json.loads((ROOT / "devices" / "catalog.json").read_text())
        profiles = json.loads(
            (ROOT / "platform" / "qemu" / "profiles.json").read_text()
        )
        review_date = source["generated_at"]
        device_count = len(source["devices"])
        qemu_count = sum(
            device["backend"].startswith("qemu-")
            for device in profiles["devices"]
        )
        service_count = qemu_count + sum(
            device["backend"] == "esp-emulator-native"
            for device in profiles["devices"]
        )
        self.assertIn(f"`{device_count}` 台设备", status)
        self.assertIn(f"`{service_count}` 台设备", status)
        self.assertEqual(catalog["generated_at"], review_date)
        self.assertEqual(qemu_count, 12)
        self.assertIn("`67/67` 用例、`274/274` 检查 PASS", status)
        self.assertIn(
            f"平台套件共 `{self._platform_test_count()}` 项",
            status,
        )
        self.assertIn("项环境相关测试跳过", status)
        self.assertIn("2026-10-24 06:47 +08:00", status)
        self.assertIn("`retry_used=false`", status)
        self.assertIn("`qemu-unified`", (ROOT / "README.md").read_text())
        self.assertIn(
            "runtime=qemu-unified",
            (DOCS / "unified-device-runtime.md").read_text(),
        )
        self.assertIn(
            "docs/code-map.md",
            (ROOT / "README.md").read_text(),
        )
        self.assertIn(
            "docs/workstreams.md",
            (ROOT / "README.md").read_text(),
        )
        self.assertIn(
            "workstreams.md",
            status,
        )
        self.assertIn(
            "## P0 收口",
            status,
        )
        self.assertIn("native-HCI `HCI-1` 至 `HCI-4` PASS", status)
        self.assertIn("core2-native-vhci", status)
        self.assertIn("HCI-1", status)
        self.assertIn("HCI-2", status)
        self.assertIn("HCI-3", status)
        self.assertIn("HCI-4", status)
        self.assertIn("HCI-3a", status)
        self.assertIn("C2H callback | `DIAGNOSTIC PASS`", status)
        self.assertIn("HCI-3b", status)
        self.assertIn("`01030c00`", status)
        self.assertIn("worker heartbeat", status)
        self.assertIn(
            "evidence-2026-10-24-pass.json",
            (ROOT / "tests/network/worker_lifecycle/README.md").read_text(),
        )
        self.assertIn(
            "core2-native-vhci",
            (DOCS / "unified-device-runtime.md").read_text(),
        )
        self.assertIn(
            "core2-native-vhci",
            (DOCS / "network-simulation-plan.md").read_text(),
        )
        self.assertIn(
            "core2-native-vhci",
            (DOCS / "qemu-device-adaptation-matrix.md").read_text(),
        )
        self.assertIn(
            "controlled DNS、TLS/Host allowlist",
            status,
        )
        self.assertIn("controlled DNS", status)
        self.assertIn("QEMU patch `0028`", status)
        self.assertIn(
            "DNS/TLS allowlist",
            (DOCS / "network-simulation-plan.md").read_text(),
        )
        self.assertIn(
            "IP/端口 egress",
            (DOCS / "validation-ledger.md").read_text(),
        )
        self.assertIn("DHCP renewal", status)
        self.assertIn("SPIFFS", status)
        firmware_manifest = (DOCS / "firmware-manifest.md").read_text()
        self.assertIn("SPIFFS 解析器", firmware_manifest)
        self.assertIn("spiffsgen.py", firmware_manifest)
        self.assertIn("LUT", firmware_manifest)
        self.assertIn("8 个声明", firmware_manifest)
        self.assertNotIn("SPIFFS 目前只做分区识别", firmware_manifest)
        spiffs_evidence = json.loads(
            (
                ROOT
                / "tests/firmware/evidence-2026-10-24-spiffs-inventory.json"
            ).read_text()
        )
        self.assertEqual(spiffs_evidence["status"], "PASS")
        self.assertTrue(
            spiffs_evidence["implementation"]["lut_validation"]
        )
        self.assertEqual(
            len(spiffs_evidence["implementation"]["supported_configs"]),
            8,
        )
        canonical = spiffs_evidence["canonical_spiffsgen_fixture"]
        self.assertEqual(canonical["status"], "PASS")
        self.assertTrue(canonical["lut_validated"])
        self.assertEqual(canonical["declared_licenses"], ["MIT"])
        self.assertEqual(canonical["sensitive_path_count"], 1)
        self.assertNotIn(
            "device.key",
            json.dumps(spiffs_evidence),
        )
        self.assertEqual(
            spiffs_evidence["negative_cases"]["lookup_table_mismatch"],
            "INVALID",
        )
        self.assertIn(
            "spiffs-inventory.json",
            code_map,
        )
        license_policy = json.loads(
            (
                ROOT
                / "tests/firmware/evidence-2026-10-24-license-policy.json"
            ).read_text()
        )
        self.assertEqual(license_policy["status"], "PASS")
        self.assertEqual(
            license_policy["cases"]["denied_gpl_3_0_only"],
            "REJECTED",
        )
        self.assertEqual(
            license_policy["cases"]["no_allowlist"],
            "REVIEW_REQUIRED",
        )
        self.assertIn(
            "Not a legal opinion",
            license_policy["limits"],
        )
        self.assertIn(
            "license-policy.json",
            code_map,
        )
        self.assertIn(
            "声明级许可 allowlist/denylist",
            firmware_manifest,
        )
        public_manifest = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-public-manifest-web-conformance.json"
            ).read_text()
        )
        self.assertEqual(public_manifest["status"], "PASS")
        self.assertTrue(all(public_manifest["checks"].values()))
        self.assertEqual(
            public_manifest["runs"]["merged_import"]["artifact_sha256"],
            public_manifest["runs"]["webburner_import"]["artifact_sha256"],
        )
        self.assertEqual(
            public_manifest["runs"]["capability_mismatch"]["status"],
            "REJECTED",
        )
        self.assertEqual(
            public_manifest["runs"]["capability_mismatch"]["issue_code"],
            "unsupported_capability",
        )
        self.assertIn("## 新鲜度台账", (DOCS / "README.md").read_text())
        self.assertIn("## 可执行任务板", backlog)
        self.assertNotIn("本轮已完成", backlog)
        self.assertNotIn("已经完成", backlog)
        self.assertIn("本页不保存完成日志", backlog)
        ledger = (DOCS / "validation-ledger.md").read_text()
        self.assertIn("验证证据台账", ledger)
        self.assertIn("2026-10-24", ledger)
        self.assertIn("HCI-3a", ledger)
        self.assertIn("诊断性单包 C2H", ledger)
        self.assertIn("[验证证据台账](validation-ledger.md)", status)
        self.assertIn(
            "[验证证据台账](docs/validation-ledger.md)",
            (ROOT / "README.md").read_text(),
        )
        ledger_evidence = re.findall(
            r"\]\((\.\./tests/[^)#]+\.json)\)",
            ledger,
        )
        self.assertGreaterEqual(len(ledger_evidence), 10)
        for relative in ledger_evidence:
            json.loads((DOCS / relative).read_text())
        self.assertIn(
            f"日期：`{review_date}`",
            status,
        )
        self.assertIn(
            f"日期：`{review_date}`",
            (DOCS / "firmware-manifest.md").read_text(),
        )
        self.assertIn(
            f"Date: `{review_date}`",
            (DOCS / "unified-device-runtime.md").read_text(),
        )
        self.assertIn(
            f"日期：`{review_date}`",
            (DOCS / "uiflow2-peripheral-test-matrix.md").read_text(),
        )
        core2_profile = next(
            device for device in profiles["devices"] if device["id"] == "core2"
        )
        self.assertIn(
            "physical cache/PSRAM",
            " ".join(core2_profile["blockers"]),
        )
        tls_evidence = json.loads(
            (
                ROOT
                / "tests/network/tls_allowlist/"
                "evidence-2026-10-23-blocked.json"
            ).read_text()
        )
        self.assertEqual(tls_evidence["status"], "FAIL")
        self.assertIn("aes_gdma", tls_evidence["blocker"])
        tls_pass = json.loads(
            (
                ROOT
                / "tests/network/tls_allowlist/"
                "evidence-2026-10-23-pass.json"
            ).read_text()
        )
        self.assertEqual(tls_pass["status"], "PASS")
        self.assertTrue(tls_pass["checks"]["tls_allow_and_deny"])
        self.assertTrue(tls_pass["checks"]["tls_port_observed"])
        tls_namespace = json.loads(
            (
                ROOT
                / "tests/network/tls_allowlist/"
                "evidence-2026-10-24-linux-namespace-pass.json"
            ).read_text()
        )
        self.assertEqual(tls_namespace["status"], "PASS")
        self.assertEqual(tls_namespace["isolation"], "namespace")
        self.assertTrue(tls_namespace["checks"]["private_namespace"])
        self.assertTrue(tls_namespace["checks"]["no_external_route"])
        tls_dns = json.loads(
            (
                ROOT
                / "tests/network/tls_allowlist/"
                "evidence-2026-10-24-controlled-dns-pass.json"
            ).read_text()
        )
        self.assertEqual(tls_dns["status"], "PASS")
        self.assertTrue(tls_dns["checks"]["dns_allow_and_deny"])
        self.assertTrue(tls_dns["checks"]["dns_background_denied"])
        matrix = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-24-gdma-external-memory-matrix.json"
            ).read_text()
        )
        self.assertEqual(matrix["peripheral_matrix"]["cases"], 67)
        self.assertEqual(matrix["peripheral_matrix"]["checks"], 274)
        self.assertFalse(matrix["peripheral_matrix"]["retry_used"])
        latest_matrix = json.loads(
            (
                ROOT
                / "tests/uiflow2/"
                "evidence-2026-10-24-dual-guest-fabric-matrix.json"
            ).read_text()
        )
        self.assertEqual(
            latest_matrix["qemu_patch"]["file"],
            (
                "patches/qemu-m5stack-peripherals/"
                "0028-esp32-wifi-dual-guest-fabric.patch"
            ),
        )
        self.assertEqual(latest_matrix["qemu_patch"]["reverse_check"], "PASS")
        self.assertEqual(latest_matrix["peripheral_matrix"]["cases"], 67)
        self.assertEqual(latest_matrix["peripheral_matrix"]["checks"], 274)
        self.assertEqual(latest_matrix["peripheral_matrix"]["pass"], 67)
        self.assertEqual(latest_matrix["peripheral_matrix"]["fail"], 0)
        self.assertEqual(
            latest_matrix["peripheral_matrix"]["attempts_per_case"],
            1,
        )
        self.assertFalse(latest_matrix["peripheral_matrix"]["retry_used"])
        self.assertEqual(
            latest_matrix["interactive_case_hardening"]["case"],
            "cardputer-adv-keyboard",
        )
        self.assertEqual(
            latest_matrix["interactive_case_hardening"][
                "final_full_matrix"
            ],
            "PASS",
        )
        ci_egress = json.loads(
            (
                ROOT
                / "tests/network/egress_allowlist/"
                "evidence-2026-10-24-github-actions-pass.json"
            ).read_text()
        )
        self.assertEqual(ci_egress["status"], "PASS")
        self.assertTrue(all(ci_egress["checks"].values()))
        radio_loss = json.loads(
            (
                ROOT
                / "tests/network/reconnect_probe/"
                "evidence-2026-10-24-radio-loss-pass.json"
            ).read_text()
        )
        self.assertEqual(radio_loss["status"], "PASS")
        self.assertTrue(all(radio_loss["checks"].values()))
        self.assertEqual(radio_loss["fault"]["target"], "radio")
        reconnect = json.loads(
            (
                ROOT
                / "tests/network/reconnect_probe/"
                "evidence-2026-10-24-radio-loss-recovery-pass.json"
            ).read_text()
        )
        self.assertEqual(reconnect["status"], "PASS")
        self.assertEqual(len(reconnect["checks"]), 16)
        self.assertTrue(all(reconnect["checks"].values()))
        self.assertFalse(reconnect["fault"]["down_value"])
        self.assertTrue(reconnect["fault"]["up_value"])
        self.assertEqual(
            reconnect["packet_capture"]["dhcp"]["transactions"][0][
                "message_sequence"
            ],
            [
                "DISCOVER",
                "OFFER",
                "REQUEST",
                "ACK",
                "DISCOVER",
                "OFFER",
                "REQUEST",
                "ACK",
            ],
        )
        lab_fabric = json.loads(
            (
                ROOT
                / "tests/network/lab_fabric/"
                "evidence-2026-10-24-two-guest-pass.json"
            ).read_text()
        )
        self.assertEqual(lab_fabric["status"], "PASS")
        self.assertEqual(len(lab_fabric["checks"]), 17)
        self.assertTrue(all(lab_fabric["checks"].values()))
        self.assertEqual(
            lab_fabric["fabric"]["mode"],
            "linux-private-qemu-socket-switch",
        )
        self.assertFalse(
            lab_fabric["isolation"]["host_control"]["connected"]
        )
        self.assertFalse(
            lab_fabric["isolation"]["public_web"]["connected"]
        )
        self.assertFalse(
            lab_fabric["isolation"]["metadata"]["connected"]
        )
        self.assertTrue(lab_fabric["checks"]["switch_mac_binding"])
        self.assertEqual(
            lab_fabric["switch"]["client_slot_by_endpoint"],
            {"0": 0, "1": 1},
        )
        self.assertEqual(
            lab_fabric["switch"]["mac_by_client_slot"],
            {
                "0": "02:4d:35:00:00:01",
                "1": "02:4d:35:00:00:02",
            },
        )
        self.assertFalse(any(lab_fabric["switch"]["pending_frames"].values()))
        for capture_name in ("guest_a", "guest_b"):
            flows = lab_fabric["captures"][capture_name]["tcp_flows"]
            self.assertTrue(
                any(
                    flow["source"].startswith("10.230.0.2:")
                    and flow["destination"].startswith("10.230.0.3:19123")
                    for flow in flows
                )
            )
            self.assertTrue(
                any(
                    flow["source"].startswith("10.230.0.3:19123")
                    and flow["destination"].startswith("10.230.0.2:")
                    for flow in flows
                )
            )
        for document in (
            status,
            (DOCS / "network-simulation-plan.md").read_text(),
            (ROOT / "tests/network/lab_fabric/README.md").read_text(),
        ):
            self.assertIn("QEMU socket", document)
        self.assertIn("双 guest", workstreams)
        self.assertIn("TAP/bridge", status)
        worker_lifecycle = json.loads(
            (
                ROOT
                / "tests/network/worker_lifecycle/"
                "evidence-2026-10-24-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_lifecycle["status"], "PASS")
        self.assertEqual(len(worker_lifecycle["checks"]), 17)
        self.assertTrue(all(worker_lifecycle["checks"].values()))
        self.assertEqual(
            worker_lifecycle["worker"]["restarted"]["generation"],
            2,
        )
        self.assertEqual(
            worker_lifecycle["worker"]["restarted"][
                "abandoned_lease_count"
            ],
            1,
        )
        self.assertTrue(
            worker_lifecycle["checks"]["interrupted_session_failed"]
        )
        self.assertTrue(
            worker_lifecycle["checks"]["pcap_result_recorded"]
        )
        worker_queue = json.loads(
            (
                ROOT
                / "tests/network/worker_queue/"
                "evidence-2026-10-24-queue-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_queue["status"], "PASS")
        self.assertEqual(
            worker_queue["scope"],
            "contract-and-http-api",
        )
        self.assertTrue(all(worker_queue["checks"].values()))
        self.assertEqual(
            worker_queue["tests"]["platform_suite"],
            "289/289 PASS",
        )
        self.assertIn(
            "active QEMU process re-attach",
            worker_queue["not_claimed"],
        )
        reattach = json.loads(
            (
                ROOT
                / "tests/network/worker_reattach/"
                "evidence-2026-10-24-reattach-pass.json"
            ).read_text()
        )
        self.assertEqual(reattach["status"], "PASS")
        self.assertEqual(
            reattach["scope"],
            "local-qemu-control-plane",
        )
        self.assertTrue(all(reattach["checks"].values()))
        self.assertEqual(
            reattach["live_service_reattach"]["status"],
            "PASS",
        )
        self.assertTrue(
            reattach["live_service_reattach"][
                "qemu_survived_service_kill"
            ]
        )
        self.assertTrue(
            reattach["live_service_reattach"][
                "restarted_service_reattached"
            ]
        )
        self.assertIn(
            "companion HTTP/BLE helper continuity",
            reattach["not_claimed"],
        )
        executor = json.loads(
            (
                ROOT
                / "tests/network/worker_executor/"
                "evidence-2026-10-24-executor-pass.json"
            ).read_text()
        )
        self.assertEqual(executor["status"], "PASS")
        self.assertEqual(executor["scope"], "same-host-real-qemu-job")
        self.assertTrue(all(executor["checks"].values()))
        self.assertEqual(
            executor["live_execution"]["job_status"],
            "completed",
        )
        self.assertEqual(
            executor["live_execution"]["result_state"],
            "PASS",
        )
        self.assertIn(
            "cross-host execution",
            executor["not_claimed"],
        )
        executor_auth = json.loads(
            (
                ROOT
                / "tests/network/worker_executor/"
                "evidence-2026-10-24-executor-auth-pass.json"
            ).read_text()
        )
        self.assertEqual(executor_auth["status"], "PASS")
        self.assertEqual(
            executor_auth["live_execution"]["unsigned_claim_http"],
            401,
        )
        self.assertEqual(
            executor_auth["live_execution"]["job_status"],
            "completed",
        )
        self.assertTrue(executor_auth["authentication"]["nonce_replay_cache"])
        efuse_security = json.loads(
            (
                ROOT
                / "tests/firmware/evidence-2026-10-24-efuse-security.json"
            ).read_text()
        )
        self.assertEqual(efuse_security["status"], "PASS")
        self.assertTrue(all(efuse_security["checks"].values()))
        self.assertEqual(
            efuse_security["capability_preflight"]["status"],
            "REJECTED",
        )
        upload_evidence = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-streaming-artifact-upload.json"
            ).read_text()
        )
        self.assertEqual(upload_evidence["status"], "PASS")
        self.assertTrue(all(upload_evidence["checks"].values()))
        self.assertTrue(
            upload_evidence["checks"]["failed_append_rollback"]
        )
        self.assertTrue(upload_evidence["checks"]["abandoned_upload_gc"])
        webburner_evidence = json.loads(
            (
                ROOT
                / "tests/firmware/evidence-2026-10-24-webburner-ui.json"
            ).read_text()
        )
        self.assertEqual(webburner_evidence["status"], "PASS")
        self.assertTrue(all(webburner_evidence["checks"].values()))
        self.assertEqual(
            webburner_evidence["large_package_probe"]["chunks"],
            3,
        )
        self.assertTrue(
            webburner_evidence["refresh_recovery"][
                "import_resumed_after_refresh"
            ]
        )
        hci3b = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-diagnostic.json"
            ).read_text()
        )
        self.assertEqual(hci3b["stage"], "HCI-3b")
        self.assertEqual(hci3b["status"], "FAIL")
        self.assertTrue(hci3b["progression"]["ble_connected"])
        self.assertTrue(
            hci3b["progression"]["guest_sent_first_att_response"]
        )
        self.assertFalse(hci3b["progression"]["gatt_service_discovery"])
        safe_point = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-safe-point-audit.json"
            ).read_text()
        )
        self.assertEqual(safe_point["status"], "FAIL")
        self.assertFalse(safe_point["progression"]["ble_connected"])
        self.assertFalse(safe_point["experiment_retained"])
        self.assertEqual(safe_point["qemu_patch_reverse_check"], "PASS")
        controller_entry = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-controller-entry-audit.json"
            ).read_text()
        )
        self.assertEqual(controller_entry["status"], "FAIL")
        self.assertFalse(controller_entry["experiment_retained"])
        self.assertEqual(
            controller_entry["qemu_patch_reverse_check"],
            "PASS",
        )
        api_boundary = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-api-boundary-audit.json"
            ).read_text()
        )
        self.assertEqual(api_boundary["stage"], "HCI-3b")
        self.assertEqual(api_boundary["status"], "FAIL")
        partial = api_boundary["observations"]["api_breakpoint_partial"]
        self.assertTrue(partial["gatt_discovered"])
        self.assertTrue(partial["notification_subscribed"])
        self.assertFalse(partial["guest_received_write"])
        self.assertFalse(api_boundary["findings"]["retained"])
        hli_queue = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-hli-queue-diagnostic.json"
            ).read_text()
        )
        self.assertEqual(hli_queue["stage"], "HCI-3b")
        self.assertEqual(hli_queue["gate_result"], "OPEN")
        self.assertEqual(hli_queue["status"], "DIAGNOSTIC_PASS")
        self.assertFalse(hli_queue["runtime"]["gdb_bridge"])
        self.assertEqual(hli_queue["guest_configuration"]["CONFIG_BTDM_CTRL_HLI"], 1)
        self.assertEqual(
            hli_queue["guest_configuration"]["hli_software_interrupt"],
            29,
        )
        self.assertEqual(hli_queue["injected_work"]["event"], 13)
        self.assertEqual(hli_queue["qom"]["hli_posts"], 1)
        self.assertEqual(hli_queue["qom"]["hli_errors"], 0)
        self.assertEqual(hli_queue["qom"]["hli_queue_depth"], 0)
        self.assertEqual(hli_queue["qom"]["meta_queue_depth"], 0)
        self.assertTrue(hli_queue["observations"]["guest_hli_isr_consumed_work"])
        self.assertFalse(hli_queue["observations"]["real_hci_event_delivered"])
        self.assertFalse(hli_queue["observations"]["complete_hci_gatt_sequence"])
        self.assertFalse(hli_queue["observations"]["hli_consumed_counter_usable"])
        self.assertFalse(hli_queue["experiment_retained"])
        self.assertFalse(hli_queue["reproducible_from_committed_worktree"])
        hli_event = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hli-event-5x.json"
            ).read_text()
        )
        self.assertEqual(hli_event["stage"], "HCI-3b")
        self.assertEqual(hli_event["status"], "PASS")
        self.assertEqual(len(hli_event["runs"]), 5)
        self.assertTrue(
            all(run["status"] == "PASS" for run in hli_event["runs"])
        )
        self.assertTrue(
            all(
                run["reset_command"] == "01030c00"
                and run["next_command"] == "01011000"
                for run in hli_event["runs"]
            )
        )
        self.assertTrue(
            all(
                run["hli_posts"] == 1
                and run["hli_consumed"] == 1
                and run["hli_event_buffers"] == 1
                and run["hli_errors"] == 0
                and run["malformed_packets"] == 0
                and run["dropped_packets"] == 0
                for run in hli_event["runs"]
            )
        )
        self.assertIn(
            "complete HCI command sequence",
            hli_event["not_claimed"],
        )
        notification_fail = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci3b-hli-api-notification-fail.json"
            ).read_text()
        )
        self.assertEqual(notification_fail["stage"], "HCI-3b")
        self.assertEqual(notification_fail["gate_result"], "OPEN")
        self.assertEqual(notification_fail["status"], "FAIL")
        self.assertTrue(
            notification_fail["progression"]["notification_subscribed"]
        )
        self.assertTrue(
            notification_fail["progression"]["nus_write_sent_by_peer"]
        )
        self.assertFalse(
            notification_fail["progression"]["guest_received_write_marker"]
        )
        self.assertFalse(
            notification_fail["progression"]["notification_observed"]
        )
        self.assertEqual(
            notification_fail["counters"]["hli_errors"],
            1,
        )
        self.assertEqual(
            notification_fail["counters"]["hli_c2h_acls"],
            9,
        )
        self.assertIn(
            "BLE_BUMBLE_FAIL notification timeout",
            notification_fail["observed_order"][3],
        )
        self.assertIn(
            "errno=5",
            notification_fail["observed_order"][5],
        )
        self.assertEqual(
            notification_fail["repeat_observations"]["same_build_runs"],
            2,
        )
        self.assertEqual(
            notification_fail["repeat_observations"][
                "notification_timeout"
            ],
            2,
        )
        self.assertTrue(
            notification_fail["experiment"][
                "reproducible_from_committed_worktree"
            ]
        )
        self.assertEqual(
            notification_fail["superseded_by"],
            "evidence-2026-10-24-hli-api-gatt-5x.json",
        )
        gatt_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hli-api-gatt-5x.json"
            ).read_text()
        )
        self.assertEqual(gatt_pass["stage"], "HCI-3b")
        self.assertEqual(gatt_pass["gate_result"], "PASS")
        self.assertEqual(gatt_pass["status"], "PASS")
        self.assertEqual(gatt_pass["att"]["pdu_bytes"], 17)
        self.assertEqual(len(gatt_pass["runs"]), 5)
        self.assertTrue(
            all(run["status"] == "PASS" for run in gatt_pass["runs"])
        )
        self.assertTrue(
            all(
                run["l2cap_mtu_rejects"] == 0
                and run["python_gatts_on_write"] == 1
                and run["python_notify"] == 1
                for run in gatt_pass["runs"]
            )
        )
        self.assertEqual(
            gatt_pass["patch_validation"]["git_apply_check"],
            "PASS",
        )
        hci4 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-service-5x.json"
            ).read_text()
        )
        self.assertEqual(
            hci4["kind"],
            "m5stack-core2-native-hci-service-attempts",
        )
        self.assertEqual(hci4["stage"], "HCI-4")
        self.assertEqual(hci4["gate_result"], "PASS")
        self.assertEqual(hci4["status"], "PASS")
        self.assertEqual(hci4["validation"], "virtual-device validation")
        self.assertEqual(hci4["profile"], "core2-native-hci")
        self.assertEqual(hci4["runtime"], "qemu-unified")
        self.assertEqual(hci4["service_api"], "/api/v1")
        self.assertEqual(hci4["attempts_requested"], 5)
        self.assertEqual(hci4["attempts_passed"], 5)
        self.assertEqual(len(hci4["runs"]), 5)
        self.assertTrue(all(run["status"] == "PASS" for run in hci4["runs"]))
        self.assertTrue(
            all(run["frame_bytes"] > 1000 for run in hci4["runs"])
        )
        self.assertEqual(
            {run["frame_sha256"] for run in hci4["runs"]},
            {
                (
                    "5bfcdf8fc518a36385783a9b5bf09b3fbce9"
                    "d8c07406326955569f6c7db8408b"
                )
            },
        )
        self.assertTrue(all(run["qom_nodes"] == 27 for run in hci4["runs"]))
        self.assertTrue(all(run["pcap_bytes"] > 0 for run in hci4["runs"]))
        checks = hci4["checks_per_attempt"]
        for check in (
            "api_evidence",
            "frame_png",
            "wifi_dhcp_http",
            "public_dns_http",
            "external_nus_gatt",
            "evidence_zip",
            "pcap_file_in_evidence_zip",
            "manifest_session_binding",
        ):
            self.assertEqual(checks[check], "PASS")
        self.assertEqual(checks["qom_nodes"], 27)
        self.assertEqual(
            checks["hci_transport"],
            "ESP32 native HCI device + HLI to Bumble",
        )
        self.assertFalse(hci4["boundary"]["gdb_bridge"])
        self.assertEqual(hci4["boundary"]["isolation"], "trusted-host")
        self.assertIn(
            "bit-exact Espressif BT controller/baseband",
            hci4["boundary"]["not_claimed"],
        )
        extended_fail = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-extended-run-fail.json"
            ).read_text()
        )
        self.assertEqual(
            extended_fail["kind"],
            "m5stack-core2-native-hci-extended-run-failure",
        )
        self.assertEqual(extended_fail["stage"], "CORE2-02")
        self.assertEqual(extended_fail["gate_result"], "FAIL")
        self.assertEqual(extended_fail["status"], "FAIL")
        self.assertEqual(len(extended_fail["observations"]), 3)
        self.assertEqual(
            extended_fail["observations"][0]["configuration"][
                "attempts_completed"
            ],
            4,
        )
        self.assertEqual(
            extended_fail["observations"][1]["failure"]["first_panic"][
                "kind"
            ],
            "IllegalInstruction",
        )
        self.assertEqual(
            extended_fail["observations"][1]["failure"]["first_panic"][
                "symbol"
            ],
            "semphr_give_wrapper",
        )
        self.assertEqual(
            extended_fail["classification"]["result"],
            "not_root_caused",
        )
        self.assertEqual(
            extended_fail["superseded_by"],
            "evidence-2026-10-24-hci4-halted-gate-5x.json",
        )
        halted_gate = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-halted-gate-5x.json"
            ).read_text()
        )
        self.assertEqual(halted_gate["gate_result"], "PASS")
        self.assertEqual(halted_gate["attempts_requested"], 5)
        self.assertEqual(halted_gate["attempts_passed"], 5)
        self.assertEqual(halted_gate["hold_seconds_per_attempt"], 10)
        self.assertTrue(
            all(run["status"] == "PASS" for run in halted_gate["runs"])
        )
        self.assertTrue(
            all(
                run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-posts"]
                == run["native_hci_health"]["hli-consumed"]
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                for run in halted_gate["runs"]
            )
        )
        halted_confirm = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-halted-gate-confirm-5x.json"
            ).read_text()
        )
        self.assertEqual(halted_confirm["status"], "PASS")
        self.assertEqual(halted_confirm["attempts_passed"], 5)
        self.assertEqual(
            halted_confirm["qemu_sha256"],
            halted_gate["qemu_sha256"],
        )
        patch_0005 = (
            ROOT
            / "patches/qemu-core2-native-hci/"
            "0005-esp32-native-hci-guest-call-sregs.patch"
        ).read_bytes()
        self.assertEqual(
            halted_gate["patch_validation"]["sha256"],
            hashlib.sha256(patch_0005).hexdigest(),
        )
        self.assertEqual(
            halted_gate["patch_validation"]["reverse_apply_check"],
            "PASS",
        )
        hold60 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-hold60-3x.json"
            ).read_text()
        )
        self.assertEqual(hold60["gate_result"], "PASS")
        self.assertEqual(hold60["attempts_requested"], 3)
        self.assertEqual(hold60["attempts_passed"], 3)
        self.assertEqual(hold60["hold_seconds_per_attempt"], 60)
        self.assertTrue(all(run["status"] == "PASS" for run in hold60["runs"]))
        self.assertTrue(
            all(
                run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-posts"]
                == run["native_hci_health"]["hli-consumed"]
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                and run["native_hci_health"]["peer-closed"] == 1
                and run["native_hci_health"]["last-error"] == 3
                for run in hold60["runs"]
            )
        )
        hold120 = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-hold120-2x.json"
            ).read_text()
        )
        self.assertEqual(hold120["gate_result"], "PASS")
        self.assertEqual(hold120["attempts_requested"], 2)
        self.assertEqual(hold120["attempts_passed"], 2)
        self.assertEqual(hold120["hold_seconds_per_attempt"], 120)
        self.assertTrue(all(hold120["checks_per_attempt"].values()))
        self.assertTrue(all(run["status"] == "PASS" for run in hold120["runs"]))
        self.assertTrue(
            all(
                run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-posts"]
                == run["native_hci_health"]["hli-consumed"]
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                and run["native_hci_health"]["peer-closed"] == 1
                and run["native_hci_health"]["tx-queue-depth"] == 32
                and run["native_hci_health"]["last-error"] == 2
                for run in hold120["runs"]
            )
        )
        active_hold = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-active-ble-hold120-2x.json"
            ).read_text()
        )
        self.assertEqual(active_hold["status"], "PASS")
        self.assertEqual(active_hold["hold_seconds_per_attempt"], 120)
        self.assertEqual(active_hold["ble_linger_seconds"], 180)
        self.assertEqual(active_hold["attempts_passed"], 2)
        self.assertTrue(
            all(active_hold["checks_per_attempt"].values())
        )
        self.assertTrue(
            all(
                run["native_hci_health"]["peer-closed"] == 0
                and run["native_hci_health"]["tx-queue-depth"] == 0
                and run["native_hci_health"]["last-error"] == 0
                and run["native_hci_health"]["hli-errors"] == 0
                for run in active_hold["runs"]
            )
        )
        reconnect_fail = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-reconnect2-fail.json"
            ).read_text()
        )
        self.assertEqual(reconnect_fail["stage"], "CORE2-02")
        self.assertEqual(reconnect_fail["gate_result"], "FAIL")
        self.assertEqual(reconnect_fail["status"], "FAIL")
        self.assertEqual(
            reconnect_fail["validation"],
            "virtual-device validation",
        )
        self.assertEqual(len(reconnect_fail["variants"]), 3)
        self.assertTrue(
            all(
                variant["requested_reconnect_cycles"] == 2
                and variant["observed"]["cycle_1"] == "PASS"
                and variant["observed"]["cycle_2_advertisement"] == "TIMEOUT"
                and not variant["observed"]["guest_panic"]
                for variant in reconnect_fail["variants"]
            )
        )
        self.assertEqual(
            reconnect_fail["variants"][2]["observed"][
                "serial_error_marker_count"
            ],
            0,
        )
        self.assertEqual(
            reconnect_fail["classification"]["result"],
            "Bumble returned an invalid response for a no-response HCI command",
        )
        self.assertEqual(
            reconnect_fail["root_cause"]["invalid_reply_opcode"],
            "0x0c35",
        )
        reconnect_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect2-3x.json"
            ).read_text()
        )
        self.assertEqual(reconnect_pass["status"], "PASS")
        self.assertEqual(reconnect_pass["ble_reconnect_cycles"], 2)
        self.assertEqual(reconnect_pass["attempts_passed"], 3)
        self.assertTrue(
            all(
                run["status"] == "PASS"
                and run["native_hci_health"]["trace-hs-sched-reset"] == 0
                and run["native_hci_health"]["trace-gap-adv-start"] == 2
                and run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                for run in reconnect_pass["runs"]
            )
        )
        reconnect5_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect5-3x.json"
            ).read_text()
        )
        self.assertEqual(reconnect5_pass["status"], "PASS")
        self.assertEqual(reconnect5_pass["ble_reconnect_cycles"], 5)
        self.assertEqual(reconnect5_pass["attempts_requested"], 3)
        self.assertEqual(reconnect5_pass["attempts_passed"], 3)
        self.assertEqual(
            reconnect5_pass["firmware"]["sha256"],
            reconnect_pass["firmware"]["sha256"],
        )
        self.assertEqual(
            reconnect5_pass["qemu_sha256"],
            reconnect_pass["qemu_sha256"],
        )
        self.assertTrue(
            all(
                run["status"] == "PASS"
                and run["native_hci_health"]["trace-hs-sched-reset"] == 0
                and run["native_hci_health"]["trace-gap-adv-start"] == 5
                and run["native_hci_health"]["hli-posts"] == 157
                and run["native_hci_health"]["hli-consumed"] == 157
                and run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                and run["native_hci_health"]["conn-pool-free"] == 3
                and run["native_hci_health"]["l2cap-pool-free"] == 9
                and run["native_hci_health"]["gatts-pool-free"] == 3
                for run in reconnect5_pass["runs"]
            )
        )
        reconnect10_fail = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect10-timeout-fail.json"
            ).read_text()
        )
        self.assertEqual(reconnect10_fail["status"], "FAIL")
        self.assertEqual(reconnect10_fail["ble_reconnect_cycles"], 10)
        self.assertEqual(reconnect10_fail["observed"]["ble_cycles_passed"], 5)
        self.assertTrue(reconnect10_fail["observed"]["ble_cycle_6_started"])
        self.assertFalse(reconnect10_fail["observed"]["guest_panic"])
        self.assertIn(
            "timed out waiting for external BLE peer completion",
            reconnect10_fail["observed"]["session_error"],
        )
        self.assertEqual(
            reconnect10_fail["superseded_by"],
            "evidence-2026-10-24-hci4-reconnect10-3x.json",
        )
        reconnect10_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect10-3x.json"
            ).read_text()
        )
        self.assertEqual(reconnect10_pass["status"], "PASS")
        self.assertEqual(reconnect10_pass["ble_reconnect_cycles"], 10)
        self.assertEqual(reconnect10_pass["attempts_requested"], 3)
        self.assertEqual(reconnect10_pass["attempts_passed"], 3)
        self.assertEqual(
            reconnect10_pass["firmware"]["sha256"],
            reconnect5_pass["firmware"]["sha256"],
        )
        self.assertEqual(
            reconnect10_pass["qemu_sha256"],
            reconnect5_pass["qemu_sha256"],
        )
        self.assertTrue(
            all(
                run["status"] == "PASS"
                and run["native_hci_health"]["trace-hs-sched-reset"] == 0
                and run["native_hci_health"]["trace-gap-adv-start"] == 10
                and run["native_hci_health"]["hli-posts"] == 297
                and run["native_hci_health"]["hli-consumed"] == 297
                and run["native_hci_health"]["hli-c2h-events"] == 207
                and run["native_hci_health"]["hli-c2h-acls"] == 90
                and run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                and run["native_hci_health"]["conn-pool-free"] == 3
                and run["native_hci_health"]["l2cap-pool-free"] == 9
                and run["native_hci_health"]["gatts-pool-free"] == 3
                for run in reconnect10_pass["runs"]
            )
        )
        reconnect20_pass = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-hci4-reconnect20-3x.json"
            ).read_text()
        )
        self.assertEqual(reconnect20_pass["status"], "PASS")
        self.assertEqual(reconnect20_pass["ble_reconnect_cycles"], 20)
        self.assertEqual(reconnect20_pass["attempts_requested"], 3)
        self.assertEqual(reconnect20_pass["attempts_passed"], 3)
        self.assertEqual(
            reconnect20_pass["elf_sha256"],
            reconnect10_pass["elf_sha256"],
        )
        self.assertEqual(
            reconnect20_pass["qemu_sha256"],
            reconnect10_pass["qemu_sha256"],
        )
        self.assertTrue(
            all(
                run["status"] == "PASS"
                and run["native_hci_health"]["trace-hs-sched-reset"] == 0
                and run["native_hci_health"]["trace-gap-adv-start"] == 20
                and run["native_hci_health"]["hli-posts"] == 577
                and run["native_hci_health"]["hli-consumed"] == 577
                and run["native_hci_health"]["hli-c2h-events"] == 397
                and run["native_hci_health"]["hli-c2h-acls"] == 180
                and run["native_hci_health"]["hli-errors"] == 0
                and run["native_hci_health"]["hli-queue-depth"] == 0
                and run["native_hci_health"]["meta-queue-depth"] == 0
                and run["native_hci_health"]["conn-pool-free"] == 3
                and run["native_hci_health"]["l2cap-pool-free"] == 9
                and run["native_hci_health"]["gatts-pool-free"] == 3
                for run in reconnect20_pass["runs"]
            )
        )
        worker_tls = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-tls-mtls-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls["status"], "PASS")
        self.assertEqual(worker_tls["tls"]["observed_version"], "TLSv1.3")
        self.assertTrue(
            all(value == "PASS" for value in worker_tls["checks"].values())
        )
        self.assertEqual(
            worker_tls["worker_transport"]["unsigned_claim_http"],
            401,
        )
        self.assertEqual(
            worker_tls["worker_transport"]["worker_agent_exit_code"],
            0,
        )
        self.assertIn(
            "cross-host network topology or latency",
            worker_tls["not_claimed"],
        )
        worker_tls_job = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-tls-mtls-qemu-job-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls_job["status"], "PASS")
        self.assertEqual(
            worker_tls_job["checks"]["real_sticks3_qemu_job_over_mtls"],
            "PASS",
        )
        self.assertEqual(
            worker_tls_job["live_job"]["status"],
            "completed",
        )
        self.assertEqual(
            worker_tls_job["live_job"]["result_state"],
            "PASS",
        )
        self.assertEqual(worker_tls_job["live_job"]["attempts"], 1)
        self.assertIn(
            "unified board/network application PASS for the QEMU job",
            worker_tls_job["not_claimed"],
        )
        worker_tls_unified = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-tls-mtls-unified-job-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls_unified["status"], "PASS")
        self.assertEqual(
            worker_tls_unified["checks"][
                "unified_sticks3_markers_over_mtls"
            ],
            "PASS",
        )
        self.assertEqual(
            worker_tls_unified["checks"]["unified_network_evidence_over_mtls"],
            "PASS",
        )
        self.assertGreater(worker_tls_unified["live_job"]["pcap_bytes"], 0)
        self.assertGreater(worker_tls_unified["live_job"]["frame_bytes"], 0)
        worker_tls_rotation = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-security-rotation-job-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls_rotation["status"], "PASS")
        self.assertEqual(
            worker_tls_rotation["scope"],
            "same-host-loopback-sighup-tls-token-rotation",
        )
        self.assertEqual(
            worker_tls_rotation["rotation"]["reload_signal"],
            "SIGHUP",
        )
        self.assertTrue(
            all(
                value == "PASS"
                for value in worker_tls_rotation["checks"].values()
            )
        )
        self.assertEqual(
            worker_tls_rotation["checks"]["old_tls_identity_rejected"],
            "PASS",
        )
        self.assertEqual(
            worker_tls_rotation["checks"]["old_master_token_rejected"],
            "PASS",
        )
        self.assertEqual(
            worker_tls_rotation["live_job"]["status"],
            "completed",
        )
        self.assertEqual(
            worker_tls_rotation["live_job"]["result_state"],
            "PASS",
        )
        self.assertEqual(worker_tls_rotation["live_job"]["attempts"], 1)
        self.assertIn(
            "zero-downtime request draining during rotation",
            worker_tls_rotation["not_claimed"],
        )
        worker_tls_rotation_drain = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-security-rotation-drain-job-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls_rotation_drain["status"], "PASS")
        self.assertEqual(
            worker_tls_rotation_drain["scope"],
            "same-host-loopback-sighup-drained-tls-token-rotation",
        )
        self.assertEqual(
            worker_tls_rotation_drain["rotation"][
                "active_request_drain"
            ],
            "PASS",
        )
        self.assertEqual(
            worker_tls_rotation_drain["checks"][
                "active_request_drained_across_rotation"
            ],
            "PASS",
        )
        self.assertTrue(
            all(
                value == "PASS"
                for value in worker_tls_rotation_drain["checks"].values()
            )
        )
        self.assertEqual(
            worker_tls_rotation_drain["live_job"]["status"],
            "completed",
        )
        self.assertEqual(
            worker_tls_rotation_drain["live_job"]["result_state"],
            "PASS",
        )
        self.assertEqual(
            worker_tls_rotation_drain["live_job"]["attempts"],
            1,
        )
        self.assertIn(
            "credential overlap or zero-downtime client fleet migration",
            worker_tls_rotation_drain["not_claimed"],
        )
        worker_tls_rotation_overlap = json.loads(
            (
                ROOT
                / "tests/network/worker_tls/"
                "evidence-2026-10-24-security-rotation-overlap-job-pass.json"
            ).read_text()
        )
        self.assertEqual(worker_tls_rotation_overlap["status"], "PASS")
        self.assertEqual(
            worker_tls_rotation_overlap["scope"],
            "same-host-loopback-bounded-overlap-final-cutover-with-drain",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["rotation"][
                "client_ca_overlap"
            ],
            "A-and-B",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["rotation"][
                "client_ca_final"
            ],
            "B",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["rotation"][
                "master_token_overlap"
            ],
            "A-and-B",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["rotation"][
                "master_token_final"
            ],
            "B",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["rotation"][
                "client_fleet_migration"
            ],
            "manual-staged",
        )
        self.assertTrue(
            all(
                value == "PASS"
                for value in worker_tls_rotation_overlap["checks"].values()
            )
        )
        for check in (
            "overlap_old_client_certificate_accepted",
            "overlap_old_master_token_accepted",
            "final_old_tls_identity_rejected",
            "final_old_master_token_rejected",
            "active_request_drained_across_rotation",
        ):
            self.assertEqual(
                worker_tls_rotation_overlap["checks"][check],
                "PASS",
            )
        self.assertEqual(
            worker_tls_rotation_overlap["live_job"]["status"],
            "completed",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["live_job"]["result_state"],
            "PASS",
        )
        self.assertEqual(
            worker_tls_rotation_overlap["live_job"]["attempts"],
            1,
        )
        self.assertIn(
            "automated client fleet migration",
            worker_tls_rotation_overlap["not_claimed"],
        )
        self.assertIn("HTTPS/mTLS", status)
        self.assertIn("SIGHUP", status)
        self.assertIn("security-rotation-job-pass.json", status)
        self.assertIn("security-rotation-drain-job-pass.json", status)
        self.assertIn("security-rotation-overlap-job-pass.json", status)
        self.assertIn("真实 QEMU job over mTLS", status)
        self.assertIn("unified StickS3 job over mTLS", status)
        firmware_cross_vendor = json.loads(
            (
                ROOT
                / "tests/firmware/"
                "evidence-2026-10-24-cross-vendor-runtime-model-gaps.json"
            ).read_text()
        )
        self.assertEqual(firmware_cross_vendor["status"], "PARTIAL")
        self.assertEqual(
            firmware_cross_vendor["selection"]["devices"],
            6,
        )
        self.assertEqual(
            firmware_cross_vendor["selection"]["samples"],
            18,
        )
        self.assertEqual(
            firmware_cross_vendor["selection"]["official"],
            8,
        )
        self.assertEqual(
            firmware_cross_vendor["selection"]["community"],
            10,
        )
        self.assertEqual(
            firmware_cross_vendor["summary"]["status_counts"],
            [
                {"status": "PARTIAL", "count": 8},
                {"status": "PASS", "count": 10},
            ],
        )
        self.assertTrue(
            firmware_cross_vendor["summary"]["static_analysis_valid"]
        )
        self.assertEqual(
            firmware_cross_vendor["summary"]["runtime_model_gaps"],
            2,
        )
        self.assertEqual(
            firmware_cross_vendor["revalidation"]["samples"],
            6,
        )
        self.assertEqual(
            {
                gap["code"]
                for sample in firmware_cross_vendor["revalidation"][
                    "runtime_model_gaps"
                ]
                for gap in sample["runtime_model_gaps"]
            },
            {
                "zigbee_runtime_not_modeled",
                "c6_chip_id_lost_after_software_reset",
            },
        )
        self.assertIn(
            "model_gap_classification",
            firmware_cross_vendor["checks"],
        )
        self.assertIn(
            "physical hardware, electrical or RF behavior",
            firmware_cross_vendor["not_claimed"],
        )
        self.assertIn(
            "cross-vendor-runtime-model-gaps.json",
            status,
        )
        wifi_repeat = json.loads(
            (
                ROOT
                / "tests/network/core2_openmac_wifi/"
                "evidence-2026-10-24-deterministic-5x.json"
            ).read_text()
        )
        self.assertEqual(wifi_repeat["status"], "PASS")
        self.assertEqual(wifi_repeat["attempts_passed"], 5)
        self.assertEqual(len(wifi_repeat["attempts"]), 5)
        self.assertTrue(
            all(
                attempt["status"] == "PASS"
                for attempt in wifi_repeat["attempts"]
            )
        )
        self.assertIn("tcg,thread=single", wifi_repeat["runtime_flags"])
        self.assertIn(
            "shift=auto,align=off,sleep=off",
            wifi_repeat["runtime_flags"],
        )
        self.assertIn("CORE2-02", status)
        self.assertIn("extended-run", status)
        self.assertIn("semphr_give_wrapper", status)
        self.assertIn("5×10s", status)
        self.assertIn("60s", status)
        self.assertIn("120s", status)
        self.assertIn("hci4-halted-gate-5x.json", status)
        self.assertIn("hci4-hold60-3x.json", status)
        self.assertIn("hci4-hold120-2x.json", status)
        self.assertIn("CORE2-02", backlog)
        self.assertIn("extended-run", backlog)
        self.assertIn("CORE2-02", workstreams)
        self.assertIn(
            "core2-native-hci",
            (DOCS / "core2-native-hci-backend.md").read_text(),
        )
        self.assertIn("same-guest reconnect", status)
        self.assertIn("二十轮", status)
        self.assertIn("0x0c35", backlog)
        self.assertIn("reconnect2-fail.json", ledger)
        self.assertIn("hci4-reconnect2-3x.json", ledger)
        self.assertIn("hci4-reconnect5-3x.json", ledger)
        self.assertIn("hci4-reconnect10-3x.json", ledger)
        self.assertIn("hci4-reconnect20-3x.json", ledger)
        self.assertIn("hci4-reconnect10-timeout-fail.json", ledger)
        self.assertIn(
            "worker_tls/evidence-2026-10-24-tls-mtls-pass.json",
            ledger,
        )
        self.assertIn(
            "worker_tls/evidence-2026-10-24-tls-mtls-qemu-job-pass.json",
            ledger,
        )
        self.assertIn(
            "worker_tls/evidence-2026-10-24-tls-mtls-unified-job-pass.json",
            ledger,
        )
        self.assertIn(
            "worker_tls/evidence-2026-10-24-security-rotation-job-pass.json",
            ledger,
        )
        self.assertIn(
            "worker_tls/evidence-2026-10-24-security-rotation-drain-job-pass.json",
            ledger,
        )
        self.assertIn(
            "worker_tls/evidence-2026-10-24-security-rotation-overlap-job-pass.json",
            ledger,
        )
        self.assertIn(
            "firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json",
            ledger,
        )
        self.assertIn(
            "ble_reconnect_cycles",
            (DOCS / "device-service-api.md").read_text(),
        )
        oversize = json.loads(
            (
                ROOT
                / "tests/uiflow2/core2_native_hci/"
                "evidence-2026-10-24-oversize-att-mtu.json"
            ).read_text()
        )
        self.assertEqual(oversize["status"], "FAIL")
        self.assertTrue(oversize["expected_failure"])
        self.assertEqual(oversize["input"]["att_pdu_bytes"], 24)
        self.assertEqual(oversize["input"]["default_att_mtu"], 23)
        self.assertEqual(
            oversize["counters"]["trace_l2cap_mtu_reject"],
            1,
        )
        self.assertEqual(
            oversize["superseded_by"],
            "evidence-2026-10-24-hli-api-gatt-5x.json",
        )
        for patch_name, hash_key in (
            (
                "0003-esp32-native-hci-api-transaction.patch",
                "0003_sha256",
            ),
            ("0004-xtensa-ccount-tb-yield.patch", "0004_sha256"),
        ):
            patch_bytes = (
                ROOT / "patches/qemu-core2-native-hci" / patch_name
            ).read_bytes()
            self.assertEqual(
                gatt_pass["patch_validation"][hash_key],
                hashlib.sha256(patch_bytes).hexdigest(),
            )
        self.assertIn(
            "API boundary",
            (DOCS / "core2-native-hci-backend.md").read_text(),
        )
        for document in (status, code_map):
            self.assertIn("HLI", document)
            self.assertIn("HCI-3b", document)
            self.assertIn("5/5", document)
        self.assertIn("HCI-4", status)
        self.assertIn("core2-native-hci", status)
        self.assertIn("core2-native-hci", workstreams)
        self.assertIn("core2-native-hci", backlog)
        self.assertIn("HCI-4", code_map)
        self.assertIn("core2-native-hci", code_map)
        self.assertNotIn("CORE2-01", backlog)
        dns_probe = (
            ROOT / "tests/network/idf_dns_udp/README.md"
        ).read_text()
        self.assertIn("Controlled\nA/NXDOMAIN", dns_probe)
        self.assertNotIn("future dedicated DNS", dns_probe)
        dns_udp = json.loads(
            (
                ROOT
                / "tests/network/idf_dns_udp/"
                "evidence-2026-10-24-dns-udp-pass.json"
            ).read_text()
        )
        self.assertEqual(dns_udp["status"], "PASS")
        self.assertTrue(all(dns_udp["checks"].values()))
        self.assertFalse(dns_udp["runtime"]["dns"]["controlled_resolver"])
        self.assertEqual(
            dns_udp["runtime"]["udp"]["datagrams"],
            ["M5_DNS_UDP_PROBE"],
        )
        wrong_password = json.loads(
            (
                ROOT
                / "tests/network/wrong_password/"
                "evidence-2026-10-24-wrong-password-pass.json"
            ).read_text()
        )
        self.assertEqual(wrong_password["status"], "PASS")
        self.assertEqual(
            wrong_password["scope"],
            "simulation-only-not-hardware-validation",
        )
        self.assertTrue(all(wrong_password["checks"].values()))
        self.assertEqual(len(wrong_password["checks"]), 7)
        self.assertRegex(
            wrong_password["source"]["base_commit"],
            r"^[0-9a-f]{40}$",
        )
        self.assertTrue(
            all(
                set(artifact) == {"role", "bytes", "sha256"}
                for artifact in wrong_password["artifacts"]
            )
        )
        agents = (ROOT / "AGENTS.md").read_text()
        self.assertNotIn(
            "streaming upload and broader cross-firmware compatibility",
            agents,
        )
        device_center = (DOCS / "device-center-adapter.md").read_text()
        self.assertIn("POST /api/v1/sessions", device_center)
        self.assertIn("## 已接入契约", device_center)
        self.assertNotIn("后续进程级执行器", device_center)
        peripheral_matrix = (
            DOCS / "uiflow2-peripheral-test-matrix.md"
        ).read_text()
        self.assertNotIn("未来 CC1101", peripheral_matrix)

    def test_workstreams_and_platform_tool_inventory_are_current(self) -> None:
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        lab_fabric = (
            ROOT / "tests/network/lab_fabric/README.md"
        ).read_text()

        for tool in sorted((ROOT / "platform" / "tools").glob("*.py")):
            self.assertIn(
                f"`platform/tools/{tool.name}`",
                code_map,
                f"platform/tools/{tool.name} is missing from docs/code-map.md",
            )

        self.assertIn("## 代码域", code_map)
        self.assertIn("服务与生命周期", code_map)
        self.assertIn("固件输入与审查", code_map)
        self.assertIn("网络策略与取证", code_map)
        self.assertIn("运行时与设备登记", code_map)
        core2_hci = (DOCS / "core2-native-hci-backend.md").read_text()
        self.assertIn("`HCI-3a` C2H callback | `DIAGNOSTIC PASS`", core2_hci)
        self.assertIn("`HCI-4` stability | `PASS`", core2_hci)
        self.assertIn("core2-native-hci", core2_hci)
        self.assertIn("core2-native-vhci", core2_hci)
        self.assertIn("legacy", core2_hci.lower())
        self.assertIn("platform/tools/worker_directory.py", code_map)
        self.assertIn("platform/tools/worker_queue.py", code_map)
        self.assertIn("platform/tools/worker_auth.py", code_map)
        self.assertIn("platform/tools/worker_agent.py", code_map)
        self.assertIn("platform/tests/test_worker_directory.py", code_map)
        self.assertIn("platform/tests/test_worker_queue.py", code_map)
        self.assertIn("platform/tests/test_worker_auth.py", code_map)
        self.assertIn("platform/tests/test_worker_agent.py", code_map)

        task_ids = sorted(
            set(
                re.findall(
                    r"^\| `([A-Z][A-Z0-9-]+)` \|",
                    backlog,
                    re.MULTILINE,
                )
            )
        )
        self.assertTrue(task_ids)
        for task_id in task_ids:
            self.assertIn(
                f"`{task_id}`",
                workstreams,
                f"backlog task {task_id} is missing from docs/workstreams.md",
            )
        self.assertNotIn("`NET-03`", backlog)
        self.assertIn("QEMU socket L2 switch", lab_fabric)
        self.assertIn("TAP/bridge", lab_fabric)

    def test_documented_platform_test_count_is_current(self) -> None:
        count = self._platform_test_count()
        expected = f"`{count}` 项"
        document = (DOCS / "project-status.md").read_text()
        self.assertIn(
            expected,
            document,
            f"docs/project-status.md must document {count} platform tests",
        )
        self.assertIn("跳过", document)
        for relative in ("README.md", "docs/README.md", "docs/workstreams.md"):
            self.assertNotIn(
                expected,
                (ROOT / relative).read_text(),
                f"{relative} must link to project-status.md instead of copying {count}",
            )

    def test_api_versions_match(self) -> None:
        markdown = (DOCS / "device-service-api.md").read_text()
        openapi = (DOCS / "device-service.openapi.yaml").read_text()
        markdown_version = re.search(
            r"runtime contract `([0-9]+\.[0-9]+\.[0-9]+)`",
            markdown,
        )
        openapi_version = re.search(
            r"^  version: ([0-9]+\.[0-9]+\.[0-9]+)$",
            openapi,
            re.MULTILINE,
        )
        self.assertIsNotNone(markdown_version)
        self.assertIsNotNone(openapi_version)
        self.assertEqual(markdown_version.group(1), openapi_version.group(1))
        self.assertIn("core2-native-hci", openapi)
        self.assertGreaterEqual(openapi.count("core2-native-hci"), 3)
        self.assertIn("core2-native-vhci", openapi)
        self.assertIn("without a GDB bridge", openapi)
        self.assertIn("allowlist", openapi)
        self.assertIn("allowed_hosts", openapi)
        self.assertIn("allowed_endpoints", openapi)
        self.assertIn("controlled", openapi)
        self.assertIn("ble_linger_seconds", openapi)
        self.assertIn("artifact-uploads", openapi)
        self.assertIn("/firmware/import", openapi)
        self.assertIn("/worker/drain", openapi)
        self.assertIn("/workers", openapi)
        self.assertIn("/workers/{worker_id}/heartbeat", openapi)
        self.assertIn("/jobs", openapi)
        self.assertIn("/jobs/claim", openapi)
        self.assertIn("/jobs/{job_id}/heartbeat", openapi)
        self.assertIn("/jobs/{job_id}/result", openapi)
        self.assertIn("WorkerJobList", openapi)
        self.assertIn("idempotency_key", openapi)
        self.assertIn("X-M5-Worker-Signature", openapi)
        self.assertIn("nonce_replay_cache", openapi)
        self.assertIn("reattached_process", openapi)
        self.assertIn("qemu-control-plane", openapi)
        self.assertIn("RemoteWorkerRegistration", openapi)
        self.assertIn("accepting_leases", openapi)
        self.assertIn("Remote worker directory MVP", markdown)
        self.assertIn("Durable remote job queue", markdown)

    def test_webburner_browser_surface_is_wired(self) -> None:
        html = (ROOT / "platform/web/firmware.html").read_text()
        script = (ROOT / "platform/web/firmware.js").read_text()
        uploader = (ROOT / "platform/web/firmware-upload.js").read_text()
        index = (ROOT / "platform/web/index.html").read_text()
        sessions = (ROOT / "platform/web/sessions.html").read_text()

        self.assertIn('id="firmwareFile"', html)
        self.assertIn('id="startBtn"', html)
        self.assertIn('id="cancelBtn"', html)
        self.assertIn('id="createSessionBtn"', html)
        self.assertIn("firmware-upload.js", script)
        self.assertIn("/api/v1/firmware/import", uploader)
        self.assertIn("/api/v1/artifact-uploads", uploader)
        self.assertIn("/platform/web/firmware.html", index)
        self.assertIn("/platform/web/firmware.html", sessions)


if __name__ == "__main__":
    unittest.main(verbosity=2)
