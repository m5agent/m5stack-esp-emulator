#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsConsistencyTests(unittest.TestCase):
    def _platform_test_count(self) -> int:
        suite = unittest.defaultTestLoader.discover(
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
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-transport-pass.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-guest-h2c.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery.json",
            "tests/uiflow2/core2_native_hci/evidence-2026-10-24-c2h-delivery-5x.json",
            "tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json",
            "tests/network/tls_allowlist/README.md",
            "tests/network/tls_allowlist/run_test.py",
            "tests/network/core2_openmac_wifi/README.md",
            "tests/network/egress_allowlist/README.md",
            "tests/network/egress_allowlist/run_test.py",
            "tests/network/idf_dhcp_renewal/README.md",
            "tests/network/idf_dhcp_renewal/run_test.py",
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
            "tests/firmware/evidence-2026-10-23-static-review.json",
            "tests/firmware/evidence-2026-10-24-filesystem-inventory.json",
            "tests/firmware/evidence-2026-10-24-fat-inventory.json",
            "tests/firmware/evidence-2026-10-24-efuse-security.json",
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
        ):
            self.assertNotIn(stale, active)

    def test_current_status_snapshot_matches_contract(self) -> None:
        status = (DOCS / "project-status.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
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
        self.assertIn("2026-10-24 00:11 +08:00", status)
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
        self.assertIn("native-VHCI BLE 5/5", status)
        self.assertIn("同 guest native-VHCI 3/3", status)
        self.assertIn("core2-native-vhci", status)
        self.assertIn("HCI-1", status)
        self.assertIn("HCI-2", status)
        self.assertIn("HCI-3", status)
        self.assertIn("HCI-4", status)
        self.assertIn("HCI-3a", status)
        self.assertIn("HCI-3b", status)
        self.assertIn("`01030c00`", status)
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
        self.assertIn("QEMU patch `0027`", status)
        self.assertIn(
            "DNS/TLS allowlist",
            (DOCS / "network-simulation-plan.md").read_text(),
        )
        self.assertIn(
            "IP/端口 egress",
            status,
        )
        self.assertIn("DHCP renewal", status)
        self.assertIn("## 新鲜度台账", (DOCS / "README.md").read_text())
        self.assertIn("## 可执行任务板", backlog)
        self.assertNotIn("本轮已完成", backlog)
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

    def test_workstreams_and_platform_tool_inventory_are_current(self) -> None:
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()

        for tool in sorted((ROOT / "platform" / "tools").glob("*.py")):
            self.assertIn(
                f"`platform/tools/{tool.name}`",
                code_map,
                f"platform/tools/{tool.name} is missing from docs/code-map.md",
            )

        task_ids = sorted(
            set(re.findall(r"^\| `([A-Z][A-Z0-9-]+)` \|", backlog, re.M))
        )
        self.assertTrue(task_ids)
        for task_id in task_ids:
            self.assertIn(
                f"`{task_id}`",
                workstreams,
                f"backlog task {task_id} is missing from docs/workstreams.md",
            )

    def test_documented_platform_test_count_is_current(self) -> None:
        count = self._platform_test_count()
        expected = f"`{count}` 项"
        for relative in ("README.md", "docs/project-status.md"):
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
            re.M,
        )
        self.assertIsNotNone(markdown_version)
        self.assertIsNotNone(openapi_version)
        self.assertEqual(markdown_version.group(1), openapi_version.group(1))
        self.assertIn("allowlist", openapi)
        self.assertIn("allowed_hosts", openapi)
        self.assertIn("allowed_endpoints", openapi)
        self.assertIn("controlled", openapi)
        self.assertIn("artifact-uploads", openapi)
        self.assertIn("/firmware/import", openapi)

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
