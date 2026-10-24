#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path

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
            "docs/unified-device-runtime.md",
            "docs/device-service-api.md",
            "docs/device-service.openapi.yaml",
            "docs/code-map.md",
            "docs/firmware-manifest.md",
            "docs/network-simulation-plan.md",
            "docs/network-lane.md",
            "docs/core2-native-hci-backend.md",
            "platform/README.md",
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
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-oversize-att-mtu.json",
            "tests/uiflow2/core2_native_hci/run_full.py",
            "tests/uiflow2/core2_native_hci/run_service_5x.py",
            "patches/qemu-core2-native-hci/0003-esp32-native-hci-api-transaction.patch",
            "patches/qemu-core2-native-hci/0004-xtensa-ccount-tb-yield.patch",
            "patches/qemu-core2-native-hci/0005-esp32-native-hci-guest-call-sregs.patch",
            "tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json",
            "tests/network/tls_allowlist/README.md",
            "tests/network/tls_allowlist/run_test.py",
            "tests/network/core2_openmac_wifi/README.md",
            "tests/network/core2_openmac_wifi/evidence-2026-10-24-deterministic-5x.json",
            "tests/network/egress_allowlist/README.md",
            "tests/network/egress_allowlist/run_test.py",
            "tests/network/idf_dhcp_renewal/README.md",
            "tests/network/idf_dhcp_renewal/run_test.py",
            "platform/tools/network_fabric.py",
            "platform/tools/worker_registry.py",
            "platform/tools/worker_directory.py",
            "platform/tools/worker_queue.py",
            "platform/tools/worker_auth.py",
            "platform/tools/worker_agent.py",
            "platform/tests/test_network_fabric.py",
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
            "tests/uiflow2/evidence-2026-10-23-zero-retry-matrix.json",
            "tests/uiflow2/evidence-2026-10-24-gdma-external-memory-matrix.json",
            "tests/uiflow2/evidence-2026-10-24-dual-guest-fabric-matrix.json",
            "tests/firmware/evidence-2026-10-23-static-review.json",
            "tests/firmware/evidence-2026-10-24-filesystem-inventory.json",
            "tests/firmware/evidence-2026-10-24-fat-inventory.json",
            "tests/firmware/evidence-2026-10-24-spiffs-inventory.json",
            "tests/firmware/evidence-2026-10-24-efuse-security.json",
            "tests/firmware/evidence-2026-10-24-license-policy.json",
            "tests/firmware/evidence-2026-10-24-streaming-artifact-upload.json",
            "tests/firmware/evidence-2026-10-24-webburner-ui.json",
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
                ROOT / "patches" / "qemu-core2-openmac-wifi" / "README.md",
                ROOT / "patches" / "qemu-core2-ble-controller" / "README.md",
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
        ):
            self.assertNotIn(stale, active)

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
            "profile=core2-native-vhci",
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
            (ROOT / "README.md").read_text(),
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
        self.assertIn("hci4-halted-gate-5x.json", status)
        self.assertIn("CORE2-02", backlog)
        self.assertIn("extended-run", backlog)
        self.assertIn("CORE2-02", workstreams)
        self.assertIn("extended-run", workstreams)
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
        for document in (status, workstreams, code_map):
            self.assertIn("HLI", document)
            self.assertIn("HCI-3b", document)
            self.assertIn("5/5", document)
        self.assertIn("HCI-4", status)
        self.assertIn("core2-native-hci", status)
        self.assertIn("HCI-4", workstreams)
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
        for relative in (
            "README.md",
            "docs/README.md",
            "docs/project-status.md",
            "docs/workstreams.md",
        ):
            document = (ROOT / relative).read_text()
            self.assertIn(
                expected, document,
                f"{relative} must document {count} platform tests",
            )
            self.assertIn("跳过", document, relative)

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
