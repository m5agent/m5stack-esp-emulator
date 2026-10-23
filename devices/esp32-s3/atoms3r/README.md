# AtomS3R

- SKU：`C126`
- 分组：`ESP32-S3`
- 外壳：`微型方块`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001772`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3-PICO-1-N8R8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 24 × 24 × 12.9 mm |
| 重量 | 6.8 g |
| 显示 | 128×128 ips，0.85"，ST7735 / GC9107，无触摸 |
| 控制 | USER |
| 外设 | imu:bmi270, magnetometer:bmm150, rgb-led, ir |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-23)
- 详情：官方 UIFlow2 v2.5.3 在同一 QEMU guest 内通过 128x128 显示、GPIO41 按键、BMI270、BMM150、LP5562 RGB、RMT IR、WiFi DHCP/HTTP 和 UART1 HCI BLE。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
