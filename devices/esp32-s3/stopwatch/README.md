# StopWatch

- SKU：`C152`
- 分组：`ESP32-S3`
- 外壳：`圆屏手表`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002172`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 52 × 52 × 15.5 mm |
| 重量 | 39 g |
| 显示 | 466×466 amoled，1.75"，CO5300，触摸 |
| 控制 | A, B, PWR, Touch |
| 外设 | imu:bmi270, rtc:rx8130ce, audio:es8311, microphone, speaker, vibration, battery |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`uiflow2-ui-touch-pass` (2026-10-20)
- 详情：官方 UIFlow2 v2.5.3 渲染 466x466 圆屏 UI，QMP 触摸后画面重绘；统一矩阵与 StopWatch 专项测试均通过。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
