# CardputerZero

- SKU：`C154`
- 分组：`Linux ARM64`
- 外壳：`掌上键盘机`
- 运行时：`backend-required`
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
| 显示 | 320×170 lcd，1.9"，SPI LCD，无触摸 |
| 控制 | 46-key keyboard |
| 外设 | camera:imx219, imu:bmi270, magnetometer:bmm150, rtc:rx8130ce, audio:es8389, microphone, speaker, ethernet, usb-host |

## 模拟状态

backend-required：需要新的 CPU/系统后端。

- 验证：`not-run` (2026-10-20)
- 详情：当前仅完成设备档案与外壳；固件启动适配待执行。

Raspberry Pi CM0/Linux, not an Espressif firmware target

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
