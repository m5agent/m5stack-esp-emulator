# StickS3

- SKU：`K150`
- 分组：`ESP32-S3`
- 外壳：`竖条棒状`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001693`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3-PICO-1-N8R8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 48 × 24 × 15 mm |
| 重量 | 20 g |
| 显示 | 135×240 ips，1.14"，ST7789P3，无触摸，有效区 14.864 × 24.912 mm |
| 控制 | A, B, PWR |
| 外设 | imu:bmi270, audio:es8311, microphone, speaker, ir |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-button-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 渲染 135x240 UI；A/B/P 按键、电池/充电、BMI270 加速度计和陀螺仪数据闭环通过。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
