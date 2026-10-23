# Core2

- SKU：`K010-V11`
- 分组：`ESP32 LX6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000003470`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-D0WDQ6-V3 |
| 架构 | xtensa-lx6 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 54 × 54 × 16.5 mm |
| 重量 | 45.1 g |
| 显示 | 320×240 ips，2"，ILI9342C / ILI9342E，触摸 |
| 控制 | Touch, PWR |
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, speaker:ns4168, power-monitor:ina3221 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-23)
- 详情：官方 UIFlow2 v2.5.3 在同一 m5core2 guest 内通过 320x240 显示/触摸、AXP2101、INA3221、MPU6886、PCF8563、NS4168 扬声器、SPM1423 麦克风、OpenMAC WiFi DHCP/HTTP 和 UART1 HCI BLE；QOM 注入不暂停 guest，以规避已知 Core2 cache/watchdog 故障，QEMU 仍使用 -m 0。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
