# PaperColor

- SKU：`C151`
- 分组：`ESP32-S3`
- 外壳：`电子纸`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002033`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 70.8 × 103.9 × 8.5 mm |
| 重量 | 73.3 g |
| 显示 | 400×600 e-paper-color，4"，E Ink Spectra 6，无触摸 |
| 控制 | KEY1, KEY2, KEY3, PWR |
| 外设 | temperature-humidity:sht40, rtc:rx8130ce, audio:es7210, microphone:es7210, speaker:aw8737a, rgb-led:ws2812-rmt, ir, storage:sd-spi |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-23)
- 详情：官方 UIFlow2 v2.5.3 在同一 QEMU guest 内通过 400x600 六色电子纸、按键、M5PM1、SHT4X、ES8311/ES7210 音频、SPI microSD、RMT RGB/IR、WiFi DHCP/HTTP 和 UART1 HCI BLE。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
