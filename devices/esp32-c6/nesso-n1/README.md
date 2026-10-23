# Arduino Nesso N1

- SKU：`DK001`
- 分组：`ESP32-C6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002638`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-C6 |
| 架构 | riscv32 |
| Flash | 16 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 官方未确认 |
| 重量 | 官方未确认 |
| 显示 | 135×240 ips，1.14"，ST7789，触摸 |
| 控制 | Touch, KEY1, KEY2 |
| 外设 | imu:bmi270, lora, buzzer:i2s-gpio, ir-tx, battery-fuel-gauge:bq27220, charger:aw32001, io-expander:pi4ioe5v6408 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-peripherals-wifi-ble-pass` (2026-10-23)
- 详情：官方 UIFlow2 v2.5.3 在同一 QEMU C6 guest 内通过 135x240 显示、触摸/按键、PI4IOE、BQ27220/AW32001、BMI270、SX1262 LoRa、RMT 红外、I2S 蜂鸣器、QEMU ESP32-C6 WiFi DHCP/HTTP 和 UART1 HCI BLE NUS；独立 runner 与 Device Service 单个 qemu-ble lease 均通过，stock hardware.RGB() 仍为 NOT RUN。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
