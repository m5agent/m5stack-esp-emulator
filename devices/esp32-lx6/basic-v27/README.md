# Basic v2.7

- SKU：`K001-V27`
- 分组：`ESP32 LX6`
- 外壳：`核心主控`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `1897200000000000786`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-D0WDQ6-V3 |
| 架构 | xtensa-lx6 |
| Flash | 16 MB |
| PSRAM | 0 B |
| 机身尺寸 | 54 × 54 × 17 mm |
| 重量 | 49.4 g |
| 显示 | 320×240 ips，2"，ILI9342C，无触摸 |
| 控制 | A, B, C, PWR |
| 外设 | speaker:dac, battery:ip5306, charger:ip5306, storage:sd-spi |

## 模拟状态

candidate。

- 验证：`native-boot-display-input-pmic-audio-pass` (2026-11-02)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- IP5306 只建模 I2C 寄存器/状态/充电电压电流请求/BOOST 控制；没有电池电芯、电压电流测量或升压电源路径，READ4 默认 0xff 且不伪造电量。microSD、IP5306 KEY 电源键、面板背光 PWM、Grove Unit 运行时协议与物理电气/声学行为未验证。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
