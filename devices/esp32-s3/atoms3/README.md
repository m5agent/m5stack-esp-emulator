# AtomS3

- SKU：`C123`
- 分组：`ESP32-S3`
- 外壳：`微型方块`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002444`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 0 B |
| 机身尺寸 | 24 × 24 × 12.9 mm |
| 重量 | 6.9 g |
| 显示 | 128×128 ips，0.85"，GC9107，无触摸 |
| 控制 | USER |
| 外设 | imu:mpu6886, rgb-led, ir |

## 模拟状态

candidate。

- 验证：`native-display-input-imu-rgb-pass` (2026-10-29)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Selected exact-firmware native behavior passed; full peripheral completion, arbitrary firmware, networking and physical equivalence are not established. See device-local evidence and remaining component blockers.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
