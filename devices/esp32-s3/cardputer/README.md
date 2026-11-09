# Cardputer

- SKU：`K132`
- 分组：`ESP32-S3`
- 外壳：`掌上键盘机`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `1897200000000000718`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3FN8 |
| 架构 | xtensa-lx7 |
| Flash | 8 MB |
| PSRAM | 0 B |
| 机身尺寸 | 84 × 54 × 19.7 mm |
| 重量 | 92.3 g |
| 显示 | 240×135 ips，1.14"，ST7789V2，无触摸 |
| 控制 | 56-key GPIO keyboard, G0 / Boot, EN / Reset, Power switch |
| 外设 | microphone, speaker, sd:spi, ir, battery, rgb-led, charger |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`native-k132-stock-display-keyboard-pass` (2026-11-09)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
