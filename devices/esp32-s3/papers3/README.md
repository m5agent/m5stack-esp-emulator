# PaperS3

- SKU：`C139`
- 分组：`ESP32-S3`
- 外壳：`电子纸`
- 运行时：`boot-capable`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.4 / `1897200000000000284`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-S3R8 |
| 架构 | xtensa-lx7 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 67.7 × 121.5 × 7.7 mm |
| 重量 | 89 g |
| 显示 | 540×960 e-paper，4.7"，ET047TC1，触摸 |
| 控制 | GT911 touchscreen, PWR |
| 外设 | imu:bmi270, rtc:bm8563, battery:adc, buzzer, storage:sd |

## 模拟状态

boot-capable：对应 QEMU 后端可启动固件并查看串口，板级显示/外设仍在收口。

- 验证：`native-et047tc1-touch-pass` (2026-11-09)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- BMI270 is attached on the internal I2C bus; board-local accel/gyro injection and readback were not exercised.
- The factory clock reads the attached RTC; time injection and an independent device-local write/read/tick oracle were not exercised.
- The GPIO3 battery-divider ADC data path and voltage injection are not modeled.
- C139 PMS150G power-button, latch and wake behavior are not modeled.
- The factory touch toggles its icon; GPIO21 electrical buzzer drive and audio capture are not modeled.
- The factory demo reaches the empty-slot SPI path; a mounted image, card-detect transitions and sector transfers were not validated.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
