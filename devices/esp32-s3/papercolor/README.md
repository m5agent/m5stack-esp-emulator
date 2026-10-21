# PaperColor

- SKU：`C151`
- 分组：`ESP32-S3`
- 外壳：`电子纸`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002033`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 70.8 × 103.9 × 8.5 mm |
| 重量 | 73.3 g |
| 显示 | 400×600 e-paper-color，4"，E Ink Spectra 6，无触摸 |
| 控制 | KEY1, KEY2, KEY3, PWR |
| 外设 | sht40, rtc:rx8130ce, audio:es8311, microphone, speaker, rgb-led |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-key-pass` (2026-10-20)
- 详情：官方 UIFlow2 v2.5.3 渲染 400x600 六色电子纸 UI，GPIO 按键后刷新；由统一设备矩阵验证。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
