# StackChan

- SKU：`K151 / K151-R`
- 分组：`ESP32-S3`
- 外壳：`机器人`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002716`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 54 × 70.5 × 61.5 mm |
| 重量 | 187.2 g |
| 显示 | 320×240 ips，2"，ILI9342C / ILI9342E，触摸 |
| 控制 | Touch, Yaw, Pitch |
| 外设 | camera:gc0308, imu:bmi270, magnetometer:bmm150, rtc:bm8563, light-proximity:ltr553, battery:axp2101, io-expander:aw9523, io-expander:m5ioe1, power-monitor:ina226, audio:es7210, speaker:aw88298, touch:si12t, nfc:st25r3916, ir, rgb-led, servo:yaw-feedback, servo:pitch-feedback |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-peripherals-simulated` (2026-10-22)
- 详情：官方 UIFlow2 v2.5.3 渲染 320x240 UI 并接受触摸；BMI270 加速度与陀螺仪 API、BM8563 RTC、LTR553 环境光/接近、AW9523 输出/输入、INA226 电压/电流/功率、RMT NEC IR TX/RX 均通过 StackChan 板级数据面。全设备 8/8 外设用例通过。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
