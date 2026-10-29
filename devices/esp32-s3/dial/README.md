# Dial

- SKU：`K130`
- 分组：`ESP32-S3`
- 外壳：`圆屏手表`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000000879`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 0 B |
| 机身尺寸 | 45 × 45 × 32.3 mm |
| 重量 | 官方未确认 |
| 显示 | 240×240 ips，1.28"，GC9A01，触摸 |
| 控制 | USER, TOUCH, DIAL |
| 外设 | rtc:pcf8563, nfc:ws1850s, buzzer |

## 模拟状态

candidate。

- 验证：`candidate-not-validated` (2026-10-29)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Device-local official-firmware boot, input and peripheral data-plane validation is NOT RUN; results from another board are not inherited.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
