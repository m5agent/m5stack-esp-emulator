#!/usr/bin/env python3
"""Generate a deterministic project snapshot from checked-in sources."""
from __future__ import annotations

import argparse
import json
import re
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/project-snapshot.md"
SOURCE_DEVICES = ROOT / "devices/catalog.source.json"
PROFILES = ROOT / "platform/qemu/profiles.json"
PERIPHERALS = ROOT / "platform/peripherals/catalog.json"
BACKLOG = ROOT / "docs/project-backlog.md"
RUNTIME_GAPS = ROOT / "docs/runtime-model-gap-register.md"
DOC_INDEX = ROOT / "docs/README.md"
FIRMWARE_EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-24-cross-vendor-runtime-model-gaps.json"
)
CORE2_FIRMWARE_EVIDENCE = (
    ROOT
    / "tests/firmware/"
    "evidence-2026-10-24-core2-public-firmware-model-gaps.json"
)

def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def platform_test_count() -> int:
    suite = unittest.TestLoader().discover(
        str(ROOT / "platform/tests"),
        pattern="test_*.py",
    )
    return suite.countTestCases()


def latest_evidence_date() -> str:
    dates = []
    for path in (ROOT / "tests").rglob("evidence-*.json"):
        match = re.search(r"evidence-(\d{4}-\d{2}-\d{2})", path.name)
        if match:
            dates.append(match.group(1))
    return max(dates, default="unknown")


def parse_runtime_gaps() -> list[dict[str, str]]:
    text = RUNTIME_GAPS.read_text()
    parts = re.split(r"(?m)^### (RUNTIME-\d+)[:：](.*)$", text)
    gaps = []
    for gap_id, title, body in zip(parts[1::3], parts[2::3], parts[3::3]):
        match = re.search(r"\| 状态 \| `([^`]+)`", body)
        gaps.append(
            {
                "id": gap_id,
                "title": title.strip(),
                "status": match.group(1) if match else "UNKNOWN",
            }
        )
    return gaps


def parse_backlog_tasks() -> list[dict[str, str]]:
    text = BACKLOG.read_text()
    section = text.split("## 可执行任务板", 1)[1].split("\n## ", 1)[0]
    tasks = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            continue
        tasks.append(
            {
                "id": cells[0],
                "status": cells[1],
                "next": cells[2],
                "acceptance": cells[3],
            }
        )
    return tasks


def parse_document_rows() -> list[dict[str, str]]:
    text = DOC_INDEX.read_text()
    section = text.split("## 新鲜度台账", 1)[1].split("\n## ", 1)[0]
    rows = []
    link_re = re.compile(r"\]\(([^)#]+\.md)")
    for line in section.splitlines():
        if not line.startswith("| ["):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        links = link_re.findall(line)
        date_match = re.search(r"`(\d{4}-\d{2}-\d{2})`", cells[2])
        rows.append(
            {
                "page": links[0] if links else cells[0],
                "role": cells[1],
                "reviewed": date_match.group(1) if date_match else "unknown",
            }
        )
    return rows


def peripheral_state(entry: dict) -> str:
    if entry.get("peripheral_status"):
        return entry["peripheral_status"]
    statuses = [
        component.get("status")
        for component in entry.get("components", [])
        if component.get("status")
    ]
    return "partial" if any(status != "simulated" for status in statuses) else "simulated"


def collect() -> dict:
    source = load_json(SOURCE_DEVICES)
    profiles = load_json(PROFILES)
    peripheral = load_json(PERIPHERALS)
    source_devices = source["devices"]
    profile_devices = profiles["devices"]
    source_by_id = {device["id"]: device for device in source_devices}
    cross_vendor = load_json(FIRMWARE_EVIDENCE)
    core2_firmware = load_json(CORE2_FIRMWARE_EVIDENCE)

    devices = []
    for profile in sorted(
        profile_devices,
        key=lambda row: (row.get("priority", 999), row["id"]),
    ):
        device_id = profile["id"]
        source_entry = source_by_id[device_id]
        peripheral_entry = peripheral["devices"][device_id]
        validation = profile.get("validation", {})
        devices.append(
            {
                "id": device_id,
                "name": source_entry.get("name", device_id),
                "group": source_entry.get("group", "unknown"),
                "soc": source_entry["hardware"].get("soc", profile.get("soc", "")),
                "backend": profile["backend"],
                "qemu_status": profile["qemu_status"],
                "peripheral_status": peripheral_state(peripheral_entry),
                "validation_date": validation.get("date", "unknown"),
                "validation_status": validation.get("status", "unknown"),
                "blockers": profile.get("blockers", []),
            }
        )

    cross_samples = cross_vendor["samples"]
    core2_samples = core2_firmware["samples"]
    cross_status = Counter(sample["status"] for sample in cross_samples)
    core2_status = Counter(sample["status"] for sample in core2_samples)
    firmware_devices = {
        sample["device_id"] for sample in cross_samples if sample.get("device_id")
    }
    if core2_samples:
        firmware_devices.add(core2_firmware.get("device_id", "core2"))
    firmware = {
        "devices": len(firmware_devices),
        "samples": len(cross_samples) + len(core2_samples),
        "pass": cross_status["PASS"] + core2_status["PASS"],
        "partial": cross_status["PARTIAL"] + core2_status["PARTIAL"],
        "fail": cross_status["FAIL"] + core2_status["FAIL"],
    }

    group_counts = Counter(device["group"] for device in source_devices)
    backend_counts = Counter(device["backend"] for device in profile_devices)
    peripheral_counts = Counter(device["peripheral_status"] for device in devices)
    service_count = sum(
        device["backend"].startswith("qemu-")
        or device["backend"] == "esp-emulator-native"
        for device in profile_devices
    )
    return {
        "source_date": source["generated_at"],
        "latest_evidence_date": latest_evidence_date(),
        "devices_total": len(source_devices),
        "devices_by_group": dict(sorted(group_counts.items())),
        "backends": dict(sorted(backend_counts.items())),
        "service_devices": service_count,
        "peripheral_status": dict(sorted(peripheral_counts.items())),
        "devices": devices,
        "firmware_review": firmware,
        "runtime_gaps": parse_runtime_gaps(),
        "backlog": parse_backlog_tasks(),
        "documents": parse_document_rows(),
        "platform_tests": platform_test_count(),
    }


def render_markdown(snapshot: dict) -> str:
    lines = [
        "<!-- GENERATED FILE: run `python3 platform/tools/project_snapshot.py --write` -->",
        "",
        "# 项目快照（自动生成）",
        "",
        (
            f"来源日期：`{snapshot['source_date']}`；"
            f"最新 evidence 日期：`{snapshot['latest_evidence_date']}`。"
        ),
        "",
        (
            "本页只汇总机器可读源和已提交 evidence，避免在多个文档手写同一组"
            "动态事实。实现结论、风险说明和验证层级仍以"
            "[项目当前状态](project-status.md)、"
            "[验证证据台账](validation-ledger.md)"
            "和 [项目 Backlog](project-backlog.md) 为准。"
        ),
        "",
        "## 设备与后端",
        "",
        (
            f"- 设备登记：`{snapshot['devices_total']}` 台；"
            f"Device Service 可创建：`{snapshot['service_devices']}` 台。"
        ),
        "- 设备分组："
        + "，".join(
            f"`{group}` {count}"
            for group, count in snapshot["devices_by_group"].items()
        )
        + "。",
        "- 外设状态："
        + "，".join(
            f"`{status}` {count}"
            for status, count in snapshot["peripheral_status"].items()
        )
        + "。",
        "",
        "| 设备 | SoC | 后端 | 外设 | 最近验证 | 当前边界 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for device in snapshot["devices"]:
        blocker = device["blockers"][0] if device["blockers"] else "无登记 blocker"
        lines.append(
            f"| {device['name']} (`{device['id']}`) | {device['soc']} | "
            f"`{device['backend']}` | `{device['peripheral_status']}` | "
            f"`{device['validation_date']}` / `{device['validation_status']}` | "
            f"{blocker} |"
        )

    firmware = snapshot["firmware_review"]
    lines += [
        "",
        "## 通用固件审查",
        "",
        (
            f"公开样本快照覆盖 `{firmware['devices']}` 台设备、"
            f"`{firmware['samples']}` 个固件："
            f"`{firmware['pass']}` PASS、`{firmware['partial']}` PARTIAL、"
            f"`{firmware['fail']}` FAIL。PARTIAL 不自动等于固件缺陷；"
            "`runtime_model_gap` 必须保留模型边界。"
        ),
        "",
        "## 运行时模型缺口",
        "",
        "| ID | 状态 | 缺口 |",
        "| --- | --- | --- |",
    ]
    for gap in snapshot["runtime_gaps"]:
        lines.append(
            f"| `{gap['id']}` | `{gap['status']}` | {gap['title']} |"
        )

    lines += [
        "",
        "## Backlog Task 板",
        "",
        "| Task | 当前状态 | 下一项最小交付 |",
        "| --- | --- | --- |",
    ]
    for task in snapshot["backlog"]:
        lines.append(
            f"| `{task['id']}` | {task['status']} | {task['next']} |"
        )

    lines += [
        "",
        "## 文档与测试",
        "",
        f"- 平台测试：`{snapshot['platform_tests']}` 项。",
        f"- Docs 新鲜度登记：`{len(snapshot['documents'])}` 行。",
    ]
    lines.append(
        "- 代码边界和大型模块的维护建议由"
        "[代码与验证入口地图](code-map.md)维护。"
    )

    lines += [
        "",
        "## 维护入口",
        "",
        (
            "- 当前能力、风险和真机边界："
            "[项目当前状态](project-status.md)。"
        ),
        (
            "- 未完成 Task、依赖和验收："
            "[项目 Backlog](project-backlog.md)。"
        ),
        (
            "- 带日期的验证结果和 evidence："
            "[验证证据台账](validation-ledger.md)。"
        ),
        (
            "- 代码、测试和证据路径："
            "[代码与验证入口地图](code-map.md)。"
        ),
        "- 文档职责和新鲜度：[文档导航](README.md)。",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    snapshot = collect()
    rendered = render_markdown(snapshot)
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    if args.write:
        OUTPUT.write_text(rendered)
        print(f"wrote {OUTPUT.relative_to(ROOT)}")
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != rendered:
            raise SystemExit(
                "PROJECT_SNAPSHOT_STALE: "
                "run python3 platform/tools/project_snapshot.py --write"
            )
        print("PROJECT_SNAPSHOT_OK")
    if not any((args.json, args.write, args.check)):
        print(rendered)


if __name__ == "__main__":
    main()
