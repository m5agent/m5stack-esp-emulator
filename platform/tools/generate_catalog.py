#!/usr/bin/env python3
"""Generate per-device descriptors and the static catalog from catalog.source.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "devices" / "catalog.source.json"
CATALOG = ROOT / "devices" / "catalog.json"

STATUS_LABEL = {
    "reference-ready": "reference-ready：真实固件、画面和输入已打通",
    "headless-ready": "headless-ready：真实固件、板级外设和串口/数据面已打通（无显示/画面契约）",
    "boot-capable": "boot-capable：对应 QEMU 后端可启动固件并查看串口，板级显示/外设仍在收口",
    "backend-required": (
        "backend-required：UIFlow2 不适用，由独立设备后端和外设证据验收；"
        "该标签表示固件族分类，不等同于整体完成度"
    ),
}

PRESET_LABEL = {
    "watch-round": "圆屏手表",
    "stick": "竖条棒状",
    "core": "核心主控",
    "cardputer": "掌上键盘机",
    "paper": "电子纸",
    "tab": "平板终端",
    "atom": "微型方块",
    "robot": "机器人",
    "industrial": "工业控制器",
    "console-only": "无屏控制台",
}


def human_bytes(value: int | None) -> str:
    if value is None:
        return "未确认"
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):g} MB"
    if value >= 1024:
        return f"{value / 1024:g} KB"
    return f"{value} B"


def dimensions_text(dimensions: list[float] | None) -> str:
    if not dimensions:
        return "官方未确认"
    return " × ".join(f"{value:g}" for value in dimensions) + " mm"


def display_text(display: dict | None) -> str:
    if not display:
        return "无板载显示屏"
    diagonal = f"{display['diagonal_in']:g}\"" if display.get("diagonal_in") else "尺寸未确认"
    effective = ""
    if display.get("effective_mm"):
        effective = "，有效区 " + " × ".join(f"{value:g}" for value in display["effective_mm"]) + " mm"
    return (
        f"{display['width']}×{display['height']} {display['type']}，"
        f"{diagonal}，{display.get('driver', '驱动未确认')}，"
        f"{'触摸' if display.get('touch') else '无触摸'}{effective}"
    )


def write_device(device: dict, groups: dict[str, dict]) -> dict:
    group = groups[device["group"]]
    out_dir = ROOT / "devices" / group["path"] / device["id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    full = dict(device)
    full["group_label"] = group["label"]
    full["path"] = f"devices/{group['path']}/{device['id']}"
    full["status_label"] = STATUS_LABEL.get(device["runtime"]["status"], device["runtime"]["status"])
    (out_dir / "device.json").write_text(json.dumps(full, ensure_ascii=False, indent=2) + "\n")

    firmware = {
        "schema_version": 1,
        "device_id": device["id"],
        "uiflow2": device.get("uiflow2"),
        "runtime": device.get("runtime"),
        "cache_path": f"platform/.cache/firmware/{device['id']}/uiflow2.bin",
    }
    (out_dir / "firmware.json").write_text(json.dumps(firmware, ensure_ascii=False, indent=2) + "\n")

    hardware = device["hardware"]
    controls = ", ".join(item.get("label", item["id"]) for item in hardware.get("controls", [])) or "无"
    sensors = ", ".join(hardware.get("sensors", [])) or "无"
    uiflow = device.get("uiflow2") or {}
    firmware_text = "不适用"
    if uiflow.get("firmware"):
        fw = uiflow["firmware"]
        firmware_text = f"{fw['version']} / `{fw['firmware_id']}`"
    readme = f"""# {device['name']}

- SKU：`{device.get('sku', '未确认')}`
- 分组：`{group['label']}`
- 外壳：`{PRESET_LABEL.get(device['shell']['preset'], device['shell']['preset'])}`
- 运行时：`{device['runtime']['status']}`
- 外设仿真：`{device['runtime'].get('peripheral_status', 'simulated')}`
- UIFlow2：`{'支持' if uiflow.get('supported') else '不支持'}`，m5ui：`{'支持' if uiflow.get('m5ui') else '不支持'}`
- UIFlow2 固件：{firmware_text}

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | {hardware.get('soc', '未确认')} |
| 架构 | {hardware.get('architecture', '未确认')} |
| Flash | {human_bytes(hardware.get('flash_bytes'))} |
| PSRAM | {human_bytes(hardware.get('psram_bytes'))} |
| 机身尺寸 | {dimensions_text(hardware.get('dimensions_mm'))} |
| 重量 | {f"{hardware.get('weight_g'):g} g" if hardware.get('weight_g') is not None else '官方未确认'} |
| 显示 | {display_text(hardware.get('display'))} |
| 控制 | {controls} |
| 外设 | {sensors} |

## 模拟状态

{STATUS_LABEL.get(device['runtime']['status'], device['runtime']['status'])}。

{validation_readme(device['runtime'])}

{device['runtime'].get('reason', '')}

{blockers_readme(device['runtime'])}

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
"""
    extra_path = (
        SOURCE.parent / group["path"] / device["id"] / "README.extra.md"
    )
    if extra_path.is_file():
        readme += "\n" + extra_path.read_text().rstrip() + "\n"
    (out_dir / "README.md").write_text(readme)

    page = device["runtime"].get("page") or f"/platform/web/device.html?device={group['path']}/{device['id']}"
    (out_dir / "index.html").write_text(
        "<!doctype html><meta charset=\"utf-8\">"
        f"<meta http-equiv=\"refresh\" content=\"0;url={page}\">"
        f"<a href=\"{page}\">{device['name']} simulator</a>\n"
    )

    return {
        "id": device["id"],
        "name": device["name"],
        "sku": device.get("sku"),
        "group": device["group"],
        "group_label": group["label"],
        "category": device["category"],
        "path": f"{group['path']}/{device['id']}",
        "shell": device["shell"]["preset"],
        "display": hardware.get("display"),
        "runtime": device["runtime"],
        "uiflow2": device.get("uiflow2"),
    }


def validation_readme(runtime: dict) -> str:
    validation = runtime.get("validation")
    if not validation:
        return ""
    return (
        f"- 验证：`{validation.get('status', 'unknown')}` "
        f"({validation.get('date', 'date unknown')})\n"
        f"- 详情：{validation.get('detail', '')}"
    )


def blockers_readme(runtime: dict) -> str:
    blockers = runtime.get("blockers") or []
    if not blockers:
        return ""
    rows = "\n".join(f"- {blocker}" for blocker in blockers)
    return f"## 未完成的板级数据面\n\n{rows}"


def main() -> None:
    source = json.loads(SOURCE.read_text())
    groups = {group["id"]: group for group in source["groups"]}
    ids = [device["id"] for device in source["devices"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate device id")

    entries = []
    for device in source["devices"]:
        if device["group"] not in groups:
            raise SystemExit(f"unknown group: {device['group']}")
        entries.append(write_device(device, groups))

    catalog = {
        "schema_version": source["schema_version"],
        "generated_at": source["generated_at"],
        "groups": source["groups"],
        "devices": sorted(entries, key=lambda item: (item["group"], item["name"])),
    }
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"generated {len(entries)} devices -> {CATALOG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
