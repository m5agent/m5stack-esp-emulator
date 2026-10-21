# CoreS3

- SKU：`K128`
- 分组：`ESP32-S3`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001950`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 54 × 54 × 15.5 mm |
| 重量 | 37.8 g |
| 显示 | 320×240 ips，2"，ILI9342C / ILI9342E，触摸 |
| 控制 | Touch, PWR |
| 外设 | camera:gc0308, imu:bmi270, magnetometer:bmm150, rtc:bm8563, microphone, speaker |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 渲染 320x240 UI；触摸、PWR、电池/充电和 RTC 通过。BMI270 数值更新、BMM150 磁力计和 camera.snapshot() 帧采集仍待补齐。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
