# AtomS3U

- SKU：`K125`
- 分组：`ESP32-S3`
- 外壳：`微型方块`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `2099000000000000005`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 0 B |
| 机身尺寸 | 53 × 20 × 10.3 mm |
| 重量 | 8.5 g |
| 显示 | 无板载显示屏 |
| 控制 | USER |
| 外设 | rgb-led, ir, microphone |

## 模拟状态

candidate。

- 验证：`native-console-boot-rgb-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- IR GPIO12、SPM1423 PDM 麦克风和 Grove Unit 数据面没有同 guest 验证；USB CDC 控制台与物理光学/声学行为未覆盖。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
