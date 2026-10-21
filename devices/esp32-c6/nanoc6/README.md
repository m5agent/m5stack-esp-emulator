# NanoC6

- SKU：`C122`
- 分组：`ESP32-C6`
- 外壳：`无屏控制台`
- 运行时：`boot-capable`
- 外设仿真：`simulated`
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
| 外设 | rgb-led, led-output:blue, ir |

## 模拟状态

boot-capable：对应 QEMU 后端可启动固件并查看串口，板级显示/外设仍在收口。

- 验证：`console-rgb-button-led-ir-pass` (2026-10-22)
- 详情：官方 UIFlow2 v2.5.3 在独立 NanoC6 板级 C6 后端运行，M5.begin() 返回板型 140；hardware.RGB 打开 GPIO19 RGBPWR，GPIO20 RMT WS2812 GRB 数据捕获为 00FF00；GPIO9 经 QOM 注入按下/释放并由 machine.Pin 读取；GPIO7 蓝色 LED 开关状态通过 GPIO 输出寄存器验证；hardware.IR TX 捕获并解码为 NEC 0x56/0xA3。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用
