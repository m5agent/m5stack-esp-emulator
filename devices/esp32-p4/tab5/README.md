# Tab5

- SKU：`C145 / K145`
- 分组：`ESP32-P4`
- 外壳：`平板终端`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002379`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-P4NRW32 |
| 架构 | riscv32 |
| Flash | 16 MB |
| PSRAM | 32 MB |
| 机身尺寸 | 128 × 80 × 12 mm |
| 重量 | 120.9 g |
| 显示 | 1280×720 ips，5"，ST7121 / ST7123，触摸 |
| 控制 | Touch, Reset/Boot |
| 外设 | camera:sc2356, imu:bmi270, rtc:rx8130ce, audio, microphone, speaker, usb-host, rs485 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-pass` (2026-10-21)
- 详情：UIFlow2 P4 firmware boots with the C6 ESP-Hosted bridge, renders a physical 1280x720 landscape frame through the real M5GFX drawing path, and redraws after touch. The image is esptool-written to 16 MiB virtual flash and byte-for-byte verified before boot.



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
