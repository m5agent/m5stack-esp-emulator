# StickC Plus

- SKU：`K016-P`
- 分组：`ESP32 LX6`
- 外壳：`竖条棒状`
- 运行时：`candidate`
- 外设仿真：`partial`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.2 / `1897200000000003037`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-PICO-D4 |
| 架构 | xtensa-lx6 |
| Flash | 4 MB |
| PSRAM | 0 B |
| 机身尺寸 | 官方未确认 |
| 重量 | 官方未确认 |
| 显示 | 135×240 ips，1.14"，ST7789v2，无触摸 |
| 控制 | A, B, PWR |
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, battery:axp192, charger:axp192, ir, led-output:gpio10, buzzer |

## 模拟状态

candidate。

- 验证：`native-selected-behaviors-pass` (2026-10-29)
- 本页只保留设备档案、验证状态和当前边界；逐项能力、运行流水与不可继承边界见 [项目当前状态](../../../docs/project-status.md)、[验证证据台账](../../../docs/validation-ledger.md) 和 [项目 Backlog](../../../docs/project-backlog.md)。
- 复现入口与 evidence 路径见 [代码与验证入口地图](../../../docs/code-map.md)。

## 未完成的板级数据面

- Selected original v2.5.2 display, GPIO37 and MPU6886 behavior passed independently. RTC, other buttons, audio, IR, power and arbitrary browser firmware still require their own selected-path evidence; no SE/Plus2 result is inherited.

## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
