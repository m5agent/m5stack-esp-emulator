# QEMU 多机型 UIFlow2 补丁

Last reviewed: `2026-10-25`

> 历史启动补丁：本文保留 2026-10-20 的板级 bring-up 边界。后续网络、
> BLE、Core2 长稳和设备服务能力见
> [项目当前状态](../../docs/project-status.md)与
> [代码与验证入口地图](../../docs/code-map.md)，不要从本页推断当前完整能力。

该补丁建立在 StopWatch UIFlow2 启动补丁之上，新增：

- `m5sticks3`：ST7789P3 135x240、M5PM1、BMI270、A/B 按键；
- `m5atoms3r`：ST7735 128x128、GPIO41 按键；
- `m5cores3`：ILI9342 320x240、AXP2101、AW9523、FT5x06 触摸；
- `m5cardputeradv`：ST7789 240x135、TCA8418 键盘事件；
- `m5stamplc`：ST7789 240x135、PI4IOE 三键；
- `m5stackchan`：ILI9342 320x240、FT5x06 触摸；
- `m5papercolor`：Spectra 6 400x600、GPIO 按键；
- `m5papermono`：SSD1677 480x800、FT5x06 触摸；
- `m5core2`：ESP32 LX6 板级入口、ILI9342/AXP192/FT5x06，完整帧和触摸已通过；
- 通用 SPI 面板模型：DC 相位、CASET/RASET/RAMWR、玻璃方向、触摸输入；
- 可变 GPIO 软件 I2C 引脚、无设备 NACK 完成语义、CoreS3 四线 PSRAM。

这是历史快照补丁，不能与当前的
`patches/qemu-m5stack-peripherals/0003-m5stack-shared-spi-full.patch`
按任意顺序继续叠加：两者都修改 `hw/gpio/esp32_gpio.c` 等共享文件，具有
不同的前像/后像。需要完整运行时请使用上面的 macOS arm64 release；需要源码
重建时先确认目标树，不要把两个历史分支拼成一条补丁序列。

## 历史快照状态

本页原先给出的 `stopwatch -> multiboard` 顺序只在内部中间树成立。使用公开
tag、公开的 zqqf16 v0.1.0 补丁和当前 stopwatch patch 重建时，
multiboard patch 在 `hw/gpio/esp32_gpio.c`、多个 `hw/m5stopwatch/*.c` 和
`hw/xtensa/meson.build` 上失败。因此该顺序不再作为可执行重建指令；
完整运行时使用 release bundle，源码重建需要目标分支的合并快照。

## 已验收

- StickS3：官方 UIFlow2 v2.5.3，135x240 首帧，A 键使计数 `0 -> 1`；
- AtomS3R：官方 UIFlow2 v2.5.3，128x128 首帧，GPIO41 使计数 `0 -> 1`；
- CoreS3：官方 UIFlow2 v2.5.3，320x240 首帧，触摸使计数 `0 -> 1`；
- Cardputer-ADV：官方 UIFlow2 v2.5.3，240x135 首帧，TCA8418 按键使计数 `0 -> 1`；
- StamPLC：UIFlow2 v2.5.3，240x135 首帧，PI4IOE 前面板 A 键使计数 `0 -> 1`；
- StackChan：官方 UIFlow2 v2.5.3，320x240 首帧，FT5x06 触摸使计数 `0 -> 1`；
- PaperColor/PaperMono：官方 UIFlow2 v2.5.3，电子纸首帧和输入重绘通过；
- Core2：官方 UIFlow2 已进入 `main.py`，完成 320x240 首帧和触摸重绘；当时的
  QEMU `-m 0` 启动边界后续已定位为 interrupt-WDT/timer starvation，并通过
  deterministic `tcg,thread=single` + `icount` 稳定；物理 PSRAM/cache 等价性
  仍是独立缺口；
- StopWatch：原有 466x466 圆屏触摸回归继续通过。

补丁不包含 `build/qemu/meson.build` 的本地 slirp 构建修复。
