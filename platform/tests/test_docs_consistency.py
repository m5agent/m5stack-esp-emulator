#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"


class DocsConsistencyTests(unittest.TestCase):
    def test_required_contract_documents_exist(self) -> None:
        for relative in (
            "README.md",
            "AGENTS.md",
            "docs/README.md",
            "docs/project-status.md",
            "docs/project-backlog.md",
            "docs/unified-device-runtime.md",
            "docs/device-service-api.md",
            "docs/device-service.openapi.yaml",
            "docs/code-map.md",
            "docs/firmware-manifest.md",
            "docs/network-simulation-plan.md",
            "docs/network-lane.md",
            "platform/README.md",
            "tests/uiflow2/README.md",
            "tests/uiflow2/core2_native_vhci/README.md",
            "tests/uiflow2/core2_native_vhci/evidence-2026-10-23-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci.json",
            "tests/uiflow2/unified_core2/evidence-2026-10-23-native-vhci-service.json",
        ):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_documentation_index_covers_every_document(self) -> None:
        index = (DOCS / "README.md").read_text()
        linked = set(
            re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", index)
        )
        for path in sorted(DOCS.rglob("*.md")):
            relative = path.relative_to(DOCS).as_posix()
            if relative == "README.md":
                continue
            self.assertIn(relative, linked, relative)

    def test_relative_markdown_links_exist(self) -> None:
        paths = [
            ROOT / "README.md",
            ROOT / "AGENTS.md",
            ROOT / "platform" / "README.md",
            ROOT / "devices" / "README.md",
            *sorted((ROOT / "devices").rglob("README.md")),
            *sorted((ROOT / "devices").rglob("README.extra.md")),
            *sorted(DOCS.glob("*.md")),
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
                *sorted(DOCS.glob("*.md")),
            )
        )
        for stale in (
            "网络模拟尚未接入统一设备服务",
            "CoreS3's stock UIFlow2 board initialization still needs separate",
            "same-instance board + WiFi model only if later required",
            "network simulation has not yet been integrated",
            "network namespaces and packet capture",
            "连续 3/3 首轮 PASS",
            "cache/WDT startup instability remains a known simulation-only blocker",
            "原生 BT controller 外部 peer/GATT 仍为 NOT RUN",
            "native-controller peer/GATT remains `NOT RUN`",
            "GDB bridge 仍未进入 Device Service",
            "Device Service integration of the bridge",
            "Service production bridge",
            "single-lease integration remains",
            "网络模拟暂不开放",
        ):
            self.assertNotIn(stale, active)

    def test_current_status_snapshot_matches_contract(self) -> None:
        status = (DOCS / "project-status.md").read_text()
        source = json.loads((ROOT / "devices" / "catalog.source.json").read_text())
        profiles = json.loads(
            (ROOT / "platform" / "qemu" / "profiles.json").read_text()
        )
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
        self.assertEqual(qemu_count, 12)
        self.assertIn("`67/67` 用例、`274/274` 检查 PASS", status)
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
            "## P0 收口",
            status,
        )
        self.assertIn("native-VHCI BLE 5/5", status)
        self.assertIn("同 guest native-VHCI 3/3", status)
        self.assertIn("core2-native-vhci", status)
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

    def test_documented_platform_test_count_is_current(self) -> None:
        suite = unittest.defaultTestLoader.discover(
            str(ROOT / "platform" / "tests"),
            pattern="test_*.py",
        )
        count = suite.countTestCases()
        expected = f"`{count}/{count}` PASS"
        for relative in ("README.md", "docs/project-status.md"):
            self.assertIn(
                expected,
                (ROOT / relative).read_text(),
                f"{relative} must document {count} platform tests",
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
            re.M,
        )
        self.assertIsNotNone(markdown_version)
        self.assertIsNotNone(openapi_version)
        self.assertEqual(markdown_version.group(1), openapi_version.group(1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
