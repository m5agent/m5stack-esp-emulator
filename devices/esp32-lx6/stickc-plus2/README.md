# StickC Plus2

- SKU：`K016-P2`
- 分组：`ESP32 LX6`
- 外壳：`竖条棒状`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000000742`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-PICO-V3-02 |
| 架构 | xtensa-lx6 |
| Flash | 8 MB |
| PSRAM | 2 MB |
| 机身尺寸 | 48 × 24 × 13.5 mm |
| 重量 | 16.7 g |
| 显示 | 135×240 ips，1.14"，ST7789v2，无触摸 |
| 控制 | A, B, PWR |
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, buzzer, ir, led-output:gpio19, battery:adc38 |

## 模拟状态

candidate。

- 验证：`native-display-buttons-imu-rtc-pass` (2026-10-29)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Device-local display, A/B/PWR, MPU6886 vectors and RTC real-I2C write/read/tick passed. Audio, IR/LED, battery ADC, power hold/wake and broader peripheral behavior remain open.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
