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

- 验证：`display-touch-audio-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 完成 320x240 首帧、FT5x06 触摸重绘、MPU6886 IMU、NS4168 扬声器 PCM 抓取、SPM1423 PDM 麦克风 PCM 注入和 INA3221 电源监控。板级已修正为 Core2 v1.1 的 AXP2101 + INA3221 硬件；QEMU 暂用 -m 0 规避 PSRAM/cache 稳定性问题。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
