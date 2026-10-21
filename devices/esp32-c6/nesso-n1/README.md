# Arduino Nesso N1

- SKU：`DK001`
- 分组：`ESP32-C6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000002638`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-C6 |
| 架构 | riscv32 |
| Flash | 16 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 官方未确认 |
| 重量 | 官方未确认 |
| 显示 | 135×240 ips，1.14"，ST7789，触摸 |
| 控制 | Touch, KEY1, KEY2 |
| 外设 | imu:bmi270, lora, buzzer:gpio-ledc, ir-tx, battery-fuel-gauge:bq27220, charger:aw32001, io-expander:pi4ioe5v6408 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-touch-power-io-pass` (2026-10-21)
- 详情：官方 UIFlow2 v2.5.3 渲染 135x240 UI；QMP 触摸和按键输入通过，双 PI4IOE5V6408 输出/中断状态、BQ27220 电池遥测和 AW32001 充电状态均完成总线闭环。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
