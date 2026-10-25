# PaperMono

- SKU：`C153`
- 分组：`ESP32-S3`
- 外壳：`电子纸`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `2089633464953118721`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 62 × 101 × 8 mm |
| 重量 | 72.4 g |
| 显示 | 480×800 e-paper-mono，3.97"，SSD1677，触摸 |
| 控制 | KEY1, KEY2, PWR, Touch |
| 外设 | imu:bmi270, rtc:rx8130ce, battery:m5pm1, io-expander:m5ioe1, charger:ip2315, microphone:pdm, nfc:st25r3916, lora:sx1262, buzzer, rgb-led, storage:sd |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-peripherals-wifi-ble-pass` (2026-10-23)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
