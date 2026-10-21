# Core2

- SKU：`K010-V11`
- 分组：`ESP32 LX6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
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
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, speaker |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 完成 320x240 首帧和 FT5x06 触摸重绘；QEMU 暂用 -m 0 规避 PSRAM/cache 稳定性问题。测试镜像通过 QEMU ESP32 ROM UART 下载模式和 esptool --no-stub 写入 16 MiB 虚拟 flash，逐字节校验后从同一镜像启动。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
