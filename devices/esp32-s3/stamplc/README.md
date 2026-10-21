# StamPLC

- SKU：`K141`
- 分组：`ESP32-S3`
- 外壳：`工业控制器`
- 运行时：`reference-ready`
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
| 外设 | temperature:lm75, power-monitor:ina226, rtc:rx8130ce, buzzer, can, rs485, digital-input:8, relay-output:4 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-key-pass` (2026-10-20)
- 详情：官方 UIFlow2 v2.5.3 渲染 240x135 UI，PI4IOE 前面板按键后计数重绘；由统一设备矩阵验证。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
