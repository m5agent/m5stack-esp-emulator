# Cardputer-ADV

- SKU：`K132-Adv`
- 分组：`ESP32-S3`
- 外壳：`掌上键盘机`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000000936`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 84 × 54 × 19.6 mm |
| 重量 | 81 g |
| 显示 | 240×135 ips，1.14"，ST7789V2，无触摸 |
| 控制 | 56-key keyboard |
| 外设 | imu:bmi270, audio:es8311, microphone, speaker, sd:spi, nfc:st25r3916-spi, subghz:cc1101 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-keyboard-peripherals-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 渲染 240x135 UI，TCA8418 键盘事件后计数重绘；SPI2 上的 microSD、ST25R3916 NFC Cap 和 CC1101 Sub-GHz Cap 均完成数据面闭环。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
