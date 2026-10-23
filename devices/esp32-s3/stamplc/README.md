# StamPLC

- SKU：`K141`
- 分组：`ESP32-S3`
- 外壳：`工业控制器`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001222`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 72 × 80 × 33.4 mm |
| 重量 | 138.9 g |
| 显示 | 135×240 ips，1.14"，ST7789V2，无触摸 |
| 控制 | KEY1, KEY2, KEY3 |
| 外设 | temperature:lm75, power-monitor:ina226, rtc:rx8130ce, buzzer:i2s-delta-sigma, can:twai, rs485:uart2-half-duplex, digital-input:aw9523x8, relay-output:aw9523x4 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-23)
- 详情：官方 UIFlow2 v2.5.3 在同一 QEMU guest 内通过 240x135 显示、按键/RGB、继电器/光耦输入、INA226、LM75、RX8130、TWAI CAN、PWR-485、蜂鸣器 PCM、WiFi DHCP/HTTP 以及 UART1 HCI BLE；StamPLC 6/6 外设矩阵通过。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
