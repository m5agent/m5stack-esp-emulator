# AtomU

- SKU：`K117`
- 分组：`ESP32 LX6`
- 外壳：`微型方块`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / official GitHub release / `sha256:affa252d21f223bb…`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-PICO-D4 |
| 架构 | xtensa-lx6 |
| Flash | 4 MB |
| PSRAM | 0 B |
| 机身尺寸 | 53 × 20 × 10.3 mm |
| 重量 | 8.6 g |
| 显示 | 无板载显示屏 |
| 控制 | USER |
| 外设 | rgb-led, ir, microphone:spm1423 |

## 模拟状态

candidate。

- 验证：`native-boot-board-rgb-button-grove-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Device-local console evidence covers ROM boot, board id 130, RMT SK6812 output, QMP key-driven button and Grove I2C scan only. SPM1423 PDM microphone capture, IR G12, Grove Unit protocols and physical behavior remain unvalidated.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
