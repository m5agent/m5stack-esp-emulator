#!/usr/bin/env python3
"""Generate a deterministic project snapshot from checked-in sources."""
from __future__ import annotations

import argparse
import json
import os
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
PROJECT_STATUS = ROOT / "docs/project-status.md"
VALIDATION_LEDGER = ROOT / "docs/validation-ledger.md"
ENGINEERING_HANDOFF = ROOT / "docs/engineering-handoff.md"
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


def document_paths() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(
            part.startswith(".")
            or part in {"node_modules", "upstream"}
            for part in path.relative_to(ROOT).parts
        )
    )


def code_inventory(documents: list[Path]) -> dict:
    tool_files = sorted((ROOT / "platform/tools").glob("*.py"))
    tool_sizes = [
        (path.name, len(path.read_text(errors="replace").splitlines()))
        for path in tool_files
    ]
    executable_tests = [
        path
        for path in (ROOT / "tests").rglob("*.py")
        if path.name.startswith(("run_", "test_"))
    ]
    executable_dirs = {path.parent for path in executable_tests}
    patch_files = sorted((ROOT / "patches").rglob("*.patch"))
    patch_groups = {
        path.parent for path in patch_files if path.parent.parent == ROOT / "patches"
    }
    evidence_files = sorted(
        (ROOT / "tests").rglob("evidence-*.json")
    )
    document_lines = sum(
        len(path.read_text(errors="replace").splitlines())
        for path in documents
        if path != OUTPUT
    )
    return {
        "tool_modules": len(tool_files),
        "tool_lines": sum(lines for _, lines in tool_sizes),
        "largest_tools": [
            {"path": path, "lines": lines}
            for path, lines in sorted(
                tool_sizes, key=lambda item: (-item[1], item[0])
            )[:6]
        ],
        "executable_test_files": len(executable_tests),
        "executable_test_dirs": len(executable_dirs),
        "evidence_files": len(evidence_files),
        "patch_groups": len(patch_groups),
        "patch_files": len(patch_files),
        "documented_markdown_files": len(documents),
        "documented_markdown_lines": document_lines,
        "documented_markdown_lines_exclude": [OUTPUT.relative_to(ROOT).as_posix()],
    }


def latest_evidence_date() -> str:
    dates = []
    for path in (ROOT / "tests").rglob("evidence-*.json"):
        match = re.search(r"evidence-(\d{4}-\d{2}-\d{2})", path.name)
        if match:
            dates.append(match.group(1))
    return max(dates, default="unknown")


def document_date(path: Path) -> str:
    head = "\n".join(path.read_text(errors="replace").splitlines()[:20])
    match = re.search(
        r"(?:Last reviewed|最近核对|日期)[:：]\s*`?(\d{4}-\d{2}-\d{2})",
        head,
    )
    return match.group(1) if match else "unknown"


def current_fact_date(catalog_date: str) -> str:
    """Return the newest fact explicitly covered by a project entry document.

    ``devices/catalog.source.json`` has its own generation date. Treating that
    catalog date as the project-wide fact date made a fresh evidence ledger look
    stale whenever only device metadata was unchanged.
    """
    dates = [
        catalog_date,
        latest_evidence_date(),
        *(
            document_date(path)
            for path in (
                DOC_INDEX,
                PROJECT_STATUS,
                BACKLOG,
                VALIDATION_LEDGER,
                ENGINEERING_HANDOFF,
            )
        ),
    ]
    return max(date for date in dates if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date))


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


def strip_table_code_fence(cell: str) -> str:
    """Remove one Markdown code fence only when it wraps the whole cell."""
    stripped = cell.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] == "`":
        return stripped[1:-1]
    return stripped


def parse_backlog_tasks() -> list[dict[str, str]]:
    text = BACKLOG.read_text()
    section = text.split("## 可执行任务板", 1)[1].split("\n## ", 1)[0]
    tasks = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [
            strip_table_code_fence(cell)
            for cell in line.strip().strip("|").split("|")
        ]
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


def summarize_documents(
    documents: list[dict[str, str]], source_date: str
) -> dict:
    def category(role: str) -> str:
        if "历史" in role:
            return "historical"
        if "Backlog" in role or "待办" in role:
            return "backlog"
        if "契约" in role:
            return "contract"
        if "证据" in role:
            return "evidence"
        if any(token in role for token in ("架构", "实现", "设计", "验证专题")):
            return "implementation"
        if any(token in role for token in ("工作流", "运维", "导航", "交接", "生成事实")):
            return "workflow"
        return "reference"

    category_counts = Counter(category(row["role"]) for row in documents)
    current_rows = [
        row for row in documents if category(row["role"]) != "historical"
    ]
    older_current_rows = [
        {
            "page": row["page"],
            "role": row["role"],
            "reviewed": row["reviewed"],
        }
        for row in current_rows
        if row["reviewed"] != "unknown" and row["reviewed"] < source_date
    ]
    return {
        "total": len(documents),
        "categories": dict(sorted(category_counts.items())),
        "current": len(current_rows),
        "historical": category_counts["historical"],
        "older_current": older_current_rows,
    }


def summarize_document_coverage(
    paths: list[Path],
    documents: list[dict[str, str]],
    source_date: str,
) -> dict:
    registered = {row["page"] for row in documents}
    historical = {
        row["page"] for row in documents if "历史" in row["role"]
    }
    category_counts: Counter[str] = Counter()
    dated_pages = []
    older_delegated = []
    for path in paths:
        relative = path.relative_to(ROOT).as_posix()
        if relative in {"README.md", "AGENTS.md", "THIRD_PARTY_NOTICES.md"}:
            category = "governance"
        elif relative == "docs/README.md":
            category = "navigation"
        elif relative.startswith("docs/") and relative[5:] in registered:
            category = "authority"
        elif relative.startswith("docs/"):
            category = "unregistered_docs"
        elif relative.startswith("devices/"):
            category = "device"
        elif relative.startswith("tests/"):
            category = "test"
        elif relative.startswith("patches/"):
            category = "patch"
        elif "/vendor/" in relative:
            category = "vendor"
        elif relative.startswith("platform/"):
            category = "platform"
        elif relative.startswith("examples/"):
            category = "example"
        elif relative.startswith("records/"):
            category = "record"
        else:
            category = "other"
        category_counts[category] += 1

        reviewed = document_date(path)
        if reviewed != "unknown":
            dated_pages.append(
                {
                    "page": relative,
                    "category": category,
                    "reviewed": reviewed,
                }
            )
        if (
            category not in {"authority", "record"}
            and relative not in {f"docs/{page}" for page in historical}
            and reviewed != "unknown"
            and reviewed < source_date
        ):
            older_delegated.append(
                {
                    "page": relative,
                    "category": category,
                    "reviewed": reviewed,
                }
            )
    return {
        "total": len(paths),
        "categories": dict(sorted(category_counts.items())),
        "dated": len(dated_pages),
        "older_delegated": sorted(
            older_delegated,
            key=lambda row: (row["reviewed"], row["page"]),
        ),
    }


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
    catalog_date = source["generated_at"]
    fact_date = current_fact_date(catalog_date)
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
        "source_dates": sorted(
            {
                str(cross_vendor.get("date") or "unknown"),
                str(core2_firmware.get("date") or "unknown"),
            }
        ),
    }

    group_counts = Counter(device["group"] for device in source_devices)
    backend_counts = Counter(device["backend"] for device in profile_devices)
    peripheral_counts = Counter(device["peripheral_status"] for device in devices)
    service_count = sum(
        device["backend"].startswith("qemu-")
        or device["backend"] == "esp-emulator-native"
        for device in profile_devices
    )
    documents = parse_document_rows()
    all_documents = document_paths()
    return {
        "catalog_date": catalog_date,
        "fact_date": fact_date,
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
        "documents": documents,
        "document_audit": summarize_documents(
            documents, fact_date
        ),
        "document_coverage": summarize_document_coverage(
            all_documents,
            documents,
            fact_date,
        ),
        "platform_tests": platform_test_count(),
        "code_inventory": code_inventory(all_documents),
    }


def render_markdown(snapshot: dict) -> str:
    lines = [
        "<!-- GENERATED FILE: run `python3 platform/tools/project_snapshot.py --write` -->",
        "",
        "# 项目快照（自动生成）",
        "",
        (
            f"设备目录日期：`{snapshot['catalog_date']}`；"
            f"当前事实复核：`{snapshot['fact_date']}`；"
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
        blocker = (
            "; ".join(device["blockers"])
            if device["blockers"]
            else "无登记 blocker"
        )
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
            "历史哈希绑定公开样本基线（来源日期 "
            + "、".join(f"`{date}`" for date in firmware["source_dates"])
            + f"）覆盖 `{firmware['devices']}` 台设备、"
            f"`{firmware['samples']}` 个固件："
            f"`{firmware['pass']}` PASS、`{firmware['partial']}` PARTIAL、"
            f"`{firmware['fail']}` FAIL。PARTIAL 不自动等于固件缺陷；"
            "`runtime_model_gap` 必须保留模型边界。之后刷新、专项 fixture、"
            "安全与导入结果分别回查专题页和验证台账，不把新 evidence 自动并入"
            "这份历史样本计数。"
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
        "## 代码与文档规模",
        "",
        (
            f"- `platform/tools`：`{snapshot['code_inventory']['tool_modules']}` "
            f"个 Python 模块，`{snapshot['code_inventory']['tool_lines']}` 行；"
            "规模最大的模块如下。"
        ),
        "",
        "| 模块 | 行数 |",
        "| --- | ---: |",
    ]
    for module in snapshot["code_inventory"]["largest_tools"]:
        lines.append(f"| `{module['path']}` | {module['lines']} |")

    lines += [
        "",
        (
            f"- `tests/`：`{snapshot['code_inventory']['executable_test_files']}` "
            f"个可执行 Python 测试文件，分布在 "
            f"`{snapshot['code_inventory']['executable_test_dirs']}` 个目录；"
            f"`{snapshot['code_inventory']['evidence_files']}` 个 evidence JSON。"
        ),
        (
            f"- `patches/`：`{snapshot['code_inventory']['patch_groups']}` 个补丁组，"
            f"`{snapshot['code_inventory']['patch_files']}` 个 patch 文件。"
        ),
        (
            f"- 文档：`{snapshot['code_inventory']['documented_markdown_files']}` "
            f"个 Markdown 页面；除本生成页外共 "
            f"`{snapshot['code_inventory']['documented_markdown_lines']}` 行。"
        ),
        "",
        "## 文档与测试",
        "",
        f"- 平台测试：`{snapshot['platform_tests']}` 项。",
        (
            f"- Docs 新鲜度登记：`{snapshot['document_audit']['total']}` 行；"
            f"其中非历史页 `{snapshot['document_audit']['current']}` 行，"
            f"历史固定页 `{snapshot['document_audit']['historical']}` 行。"
        ),
    ]
    category_labels = {
        "backlog": "待办",
        "contract": "契约",
        "evidence": "证据/差异",
        "historical": "历史固定",
        "implementation": "实现/设计",
        "reference": "参考",
        "workflow": "工作流/导航",
    }
    lines.append(
        "- 文档职责分布："
        + "，".join(
            f"{category_labels.get(name, name)} `{count}`"
            for name, count in snapshot["document_audit"]["categories"].items()
        )
        + "。"
    )
    coverage_labels = {
        "authority": "权威/专题页",
        "device": "设备档案",
        "example": "示例",
        "governance": "治理/入口",
        "navigation": "文档导航",
        "other": "其他",
        "patch": "补丁说明",
        "platform": "平台说明",
        "record": "仓内历史记录",
        "test": "测试/用例说明",
        "unregistered_docs": "未登记 docs 页面",
        "vendor": "第三方来源说明",
    }
    lines.append(
        (
            f"- 全量文档盘点：`{snapshot['document_coverage']['total']}` 个 "
            "Markdown 页面；职责分布："
        )
        + "，".join(
            f"{coverage_labels.get(name, name)} `{count}`"
            for name, count in snapshot["document_coverage"][
                "categories"
            ].items()
        )
        + "。"
    )
    older = snapshot["document_audit"]["older_current"]
    if older:
        lines.append(
            "- 复核日期早于当前事实日期的非历史页："
            + "，".join(
                f"[{row['page']}]({row['page']}) `{row['reviewed']}`"
                for row in older
            )
            + "。这不自动表示内容错误；状态页变更时应优先复核。"
        )
    else:
        lines.append("- 所有非历史页的最近复核日期均与当前事实日期一致。")
    older_delegated = snapshot["document_coverage"]["older_delegated"]
    if older_delegated:
        lines.append(
            "- 带显式旧复核日期的委派文档（需按相邻索引和权威页复核）："
        )
        lines.extend(
            f"  - [{row['page']}]"
            f"({os.path.relpath(ROOT / row['page'], ROOT / 'docs')}) "
            f"`{row['reviewed']}`"
            for row in older_delegated
        )
    else:
        lines.append("- 没有带显式旧复核日期的委派文档。")
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
        "- 测试分层和 evidence 规则：[测试总索引](../tests/README.md)。",
        "- QEMU/固件补丁分组：[补丁总索引](../patches/README.md)。",
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
