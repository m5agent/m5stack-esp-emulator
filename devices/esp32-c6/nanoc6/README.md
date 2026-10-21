# NanoC6

- SKU：`C122`
- 分组：`ESP32-C6`
- 外壳：`无屏控制台`
- 运行时：`boot-capable`
- UIFlow2：`支持`，m5ui：`不支持`
- UIFlow2 固件：v2.5.3 / `1897200000000001159`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-C6FH4 |
| 架构 | riscv32 |
| Flash | 4 MB |
| PSRAM | 未确认 |
| 机身尺寸 | 23.5 × 12 × 9.5 mm |
| 重量 | 2.7 g |
| 显示 | 无板载显示屏 |
| 控制 | GPIO9 |
| 外设 | rgb-led, ir |

## 模拟状态

boot-capable：对应 QEMU 后端可启动固件并查看串口，板级显示/外设仍在收口。

- 验证：`console-pass` (2026-10-20)
- 详情：官方 UIFlow2 v2.5.3 在 ESP32-C6 QEMU USB-Serial-JTAG 控制台运行替换后的 boot.py/main.py，M5.begin() 返回板型 140；无显示屏。



## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
