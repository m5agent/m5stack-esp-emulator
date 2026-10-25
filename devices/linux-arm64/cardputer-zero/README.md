# CardputerZero

- SKU：`C154`
- 分组：`Linux ARM64`
- 外壳：`掌上键盘机`
- 运行时：`backend-required`
- 外设仿真：`simulated`
- UIFlow2：`不支持`，m5ui：`不支持`
- UIFlow2 固件：不适用

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | RP3A0 (BCM2837) |
| 架构 | arm64 |
| Flash | 未确认 |
| PSRAM | 未确认 |
| 机身尺寸 | 84 × 54 × 23.1 mm |
| 重量 | 官方未确认 |
| 显示 | 320×170 lcd，1.9"，ST7789v3，无触摸 |
| 控制 | 46-key keyboard |
| 外设 | camera:imx219, imu:bmi270, magnetometer:bmm150, rtc:rx8130ce, audio:es8389, microphone:es8389, speaker:aw8737a, battery:bq27220, charger:ip2315, io-expander:m5ioe1, ethernet:ethernet-sr9900a, usb-host:usb-hub-gl852g, ir, storage:sd |

## 模拟状态

backend-required：UIFlow2 不适用，由独立设备后端和外设证据验收；该标签表示固件族分类，不等同于整体完成度。

- 验证：`linux-display-input-i2c-audio-power-usb-camera-pass` (2026-10-22)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

Raspberry Pi CM0/Linux, not an Espressif/UIFlow2 firmware target

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
