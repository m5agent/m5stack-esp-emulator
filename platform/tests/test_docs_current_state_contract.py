#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import unittest

import project_snapshot

from _docs_contract_support import DocsContractBase, ROOT, DOCS


class DocsCurrentStateContractTests(DocsContractBase):
    def test_engineering_handoff_stays_a_current_navigation_summary(self) -> None:
        handoff = (DOCS / "engineering-handoff.md").read_text()
        for heading in (
            "## 结论",
            "## 最近成果已经并入哪里",
            "## 成熟度怎么看",
            "## 代码怎么读",
            "## 当前工作流",
            "## 接下来做什么",
            "## 文档怎么维护",
            "## 最小验证集",
        ):
            self.assertIn(heading, handoff)
        for authority in (
            "[项目当前状态](project-status.md)",
            "[项目 Backlog](project-backlog.md)",
            "[自动项目快照](project-snapshot.md)",
            "[验证证据台账](validation-ledger.md)",
            "[代码与验证入口地图](code-map.md)",
        ):
            self.assertIn(authority, handoff)
        backlog = (DOCS / "project-backlog.md").read_text()
        task_ids = set(
            re.findall(
                r"^\| `([A-Z][A-Z0-9-]+)` \|",
                backlog,
                re.MULTILINE,
            )
        )
        self.assertTrue(task_ids)
        for task_id in sorted(task_ids):
            self.assertIn(f"`{task_id}`", handoff)
        self.assertIn("物理跨主机", handoff)
        self.assertIn("`NOT RUN`", handoff)
        self.assertIn("不维护动态数量", handoff)
        for mutable_count in (
            r"`\d+`\s*台设备",
            r"`\d+/\d+`\s*(?:用例|检查|PASS)",
            r"`\d+`\s*个 evidence",
            r"平台测试：`\d+`",
        ):
            self.assertIsNone(
                re.search(mutable_count, handoff),
                f"engineering handoff must link generated counts instead of "
                f"copying {mutable_count}",
            )

    def test_current_status_snapshot_matches_contract(self) -> None:
        status = (DOCS / "project-status.md").read_text()
        snapshot = (DOCS / "project-snapshot.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        ledger = (DOCS / "validation-ledger.md").read_text()
        review_date = (DOCS / "README.md").read_text().split("日期：`", 1)[1].split("`", 1)[0]

        for heading in (
            "## 一页结论",
            "## 当前工作与下一门禁",
            "## 能力状态",
            "## 设备矩阵",
            "## 当前风险",
            "## 证据与文档职责",
        ):
            self.assertIn(heading, status)
        self.assertLessEqual(len(status.splitlines()), 450)
        self.assertIn(f"日期：`{review_date}`", status)
        self.assertIn("[项目 Backlog](project-backlog.md)", status)
        self.assertIn("[验证证据台账](validation-ledger.md)", status)
        self.assertIn("[自动项目快照](project-snapshot.md)", status)
        self.assertIn("[代码与验证入口地图](code-map.md)", status)
        self.assertIn("[工作流总台账](workstreams.md)", status)
        self.assertIn("virtual-device validation", status)
        self.assertIn("hardware validation", status)
        self.assertIsNone(
            re.search(r"\b\d+/\d+\s+(?:PASS|cases?|checks?)\b", status),
            "project-status.md must route run counts to validation-ledger.md",
        )

        source = json.loads((ROOT / "devices" / "catalog.source.json").read_text())
        profiles = json.loads(
            (ROOT / "platform" / "qemu" / "profiles.json").read_text()
        )
        device_count = len(source["devices"])
        service_count = sum(
            device["backend"].startswith("qemu-")
            or device["backend"] == "esp-emulator-native"
            for device in profiles["devices"]
        )
        self.assertIn(f"设备登记：`{device_count}` 台", snapshot)
        self.assertIn(f"Device Service 可创建：`{service_count}` 台", snapshot)

        current_tasks = {
            task["id"]: task
            for task in project_snapshot.parse_backlog_tasks()
        }
        for task_id in (
            "RUNTIME-03",
            "NET-04",
            "CORE2-02",
            "FW-01",
            "FW-02",
            "FW-03",
            "HW-01",
        ):
            self.assertIn(task_id, current_tasks)
            self.assertIn(task_id, backlog)
            self.assertIn(task_id, workstreams)
            self.assertIn(task_id, status)

        self.assertIn("qemu-unified", status)
        self.assertIn("core2-native-hci", status)
        self.assertIn("Core2 legacy I2C", status)
        self.assertIn("物理 PSRAM/cache", status)
        self.assertIn("FirmwareManifest", status)
        self.assertIn("Live eFuse", status)
        self.assertIn("partial", status.lower())
        self.assertIn("NOT RUN", status)
        self.assertIn("hardware validation", status)
        self.assertIn("project-backlog.md", status)
        self.assertIn("validation-ledger.md", status)
        self.assertIn("project-snapshot.md", status)
        self.assertIn("code-map.md", status)
        self.assertIn("http://127.0.0.1:8787", (ROOT / "README.md").read_text())
        self.assertIn("docs/engineering-handoff.md", (ROOT / "README.md").read_text())
        self.assertIn("docs/project-status.md", (ROOT / "README.md").read_text())
        self.assertIn("docs/project-backlog.md", (ROOT / "README.md").read_text())
        self.assertIn("docs/validation-ledger.md", (ROOT / "README.md").read_text())
        self.assertIn("docs/code-map.md", (ROOT / "README.md").read_text())
        self.assertIn("docs/workstreams.md", (ROOT / "README.md").read_text())
        self.assertIn("test_docs_index_contract.py", code_map)
        self.assertIn("test_docs_current_state_contract.py", code_map)
        self.assertIn("test_docs_core2_runtime_contract.py", code_map)
        self.assertIn("test_docs_firmware_security_contract.py", code_map)
        self.assertIn("test_docs_network_worker_contract.py", code_map)
        self.assertIn("HCI-3a", ledger)
        self.assertIn("0x0c35", ledger)
        self.assertIn("67/67", ledger)

        for relative in re.findall(r"\]\((\.\./[^)#]+\.json)\)", status):
            self.assertTrue((DOCS / relative).is_file(), relative)

    def test_workstreams_and_platform_tool_inventory_are_current(self) -> None:
        workstreams = (DOCS / "workstreams.md").read_text()
        code_map = (DOCS / "code-map.md").read_text()
        backlog = (DOCS / "project-backlog.md").read_text()
        handoff = (DOCS / "engineering-handoff.md").read_text()
        qemu_matrix = (
            DOCS / "qemu-device-adaptation-matrix.md"
        ).read_text()
        network_plan = (DOCS / "network-simulation-plan.md").read_text()
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
        task_rows = {
            task["id"]: task
            for task in project_snapshot.parse_backlog_tasks()
        }
        for task in task_rows.values():
            self.assertNotIn("已 PASS", task["next"])
            self.assertIsNone(
                re.search(r"\b\d+/\d+\s+PASS\b", task["next"]),
                f"{task['id']} task board must keep evidence history out of Backlog",
            )
        self.assertIsNone(
            re.search(r"\b\d+/\d+\s+PASS\b", workstreams),
            "workstreams.md must route to status/ledger instead of copying counts",
        )
        for relative, text in (
            ("README.md", (ROOT / "README.md").read_text()),
            ("docs/engineering-handoff.md", handoff),
            ("docs/qemu-device-adaptation-matrix.md", qemu_matrix),
            ("docs/network-simulation-plan.md", network_plan),
        ):
            self.assertIsNone(
                re.search(r"\b\d+/\d+\s+PASS\b", text),
                f"{relative} must route volatile run counts to the ledger",
            )
            self.assertTrue(
                "validation-ledger.md" in text
                or "证据台账" in text,
                f"{relative} must route volatile run counts to the ledger",
            )
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
        expected = f"平台测试：`{count}` 项"
        snapshot = (DOCS / "project-snapshot.md").read_text()
        self.assertIn(
            expected,
            snapshot,
            f"docs/project-snapshot.md must document {count} platform tests",
        )
        status = (DOCS / "project-status.md").read_text()
        self.assertIn("[自动项目快照](project-snapshot.md)", status)
        for relative in (
            "README.md",
            "docs/README.md",
            "docs/workstreams.md",
            "docs/project-status.md",
        ):
            self.assertNotIn(
                f"平台套件共 `{count}` 项",
                (ROOT / relative).read_text(),
                f"{relative} must link to project-snapshot.md instead of "
                f"copying {count}",
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
        self.assertGreaterEqual(
            tuple(int(part) for part in openapi_version.group(1).split(".")),
            (1, 31, 0),
        )
        self.assertIn("core2-native-hci", openapi)
        self.assertGreaterEqual(openapi.count("core2-native-hci"), 3)
        self.assertIn("core2-native-vhci", openapi)
        self.assertIn("without a GDB bridge", openapi)
        self.assertIn("allowlist", openapi)
        self.assertIn("allowed_hosts", openapi)
        self.assertIn("allowed_domains", openapi)
        self.assertIn("cname_records:", openapi)
        self.assertIn("network.cname_records", markdown)
        self.assertIn("allowed_endpoints", openapi)
        self.assertIn("controlled", openapi)
        self.assertIn("two simultaneous cold starts", markdown)
        self.assertIn("preallocated while CPU0 is idle", markdown)
        self.assertIn("gates pass `8/8`", markdown)
        self.assertIn("three-instance `3×120s` gates pass `6/6`", markdown)
        self.assertIn("readiness budget within `40–120s`", markdown)
        self.assertIn("passes 121 cycles", markdown)
        self.assertNotIn(
            "The stock Core2 guest passes thirty cycles",
            markdown,
        )
        self.assertIn(
            "generic `features.network` flag remains false",
            markdown,
        )
        self.assertIn("at least /16", openapi)
        self.assertIn("at least /48", openapi)
        self.assertIn("DNS label boundary", openapi)
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
