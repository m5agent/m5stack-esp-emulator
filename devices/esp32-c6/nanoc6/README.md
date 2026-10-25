# NanoC6

- SKU：`C122`
- 分组：`ESP32-C6`
- 外壳：`无屏控制台`
- 运行时：`headless-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001159`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-C6FH4 |
| 架构 | riscv32 |
| Flash | 4 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 23.5 × 12 × 9.5 mm |
| 重量 | 2.7 g |
| 显示 | 无板载显示屏 |
| 控制 | GPIO9 |
| 外设 | rgb-led, led-output:blue, ir |

## 模拟状态

headless-ready：真实固件、板级外设和串口/数据面已打通（无显示/画面契约）。

- 验证：`board-peripherals-wifi-ble-pass` (2026-10-24)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
