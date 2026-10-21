# QEMU 多机型 UIFlow2 补丁

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

## 应用顺序

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/qemu-stopwatch-uiflow2-boot/0001-qemu-uiflow2-stopwatch-boot.patch
git apply /path/to/qemu-multi-board-uiflow2/0001-qemu-m5stack-multiboard-uiflow2.patch
```

## 已验收

- StickS3：官方 UIFlow2 v2.5.3，135x240 首帧，A 键使计数 `0 -> 1`；
- AtomS3R：官方 UIFlow2 v2.5.3，128x128 首帧，GPIO41 使计数 `0 -> 1`；
- CoreS3：官方 UIFlow2 v2.5.3，320x240 首帧，触摸使计数 `0 -> 1`；
- Cardputer-ADV：官方 UIFlow2 v2.5.3，240x135 首帧，TCA8418 按键使计数 `0 -> 1`；
- StamPLC：UIFlow2 v2.5.3，240x135 首帧，PI4IOE 前面板 A 键使计数 `0 -> 1`；
- StackChan：官方 UIFlow2 v2.5.3，320x240 首帧，FT5x06 触摸使计数 `0 -> 1`；
- PaperColor/PaperMono：官方 UIFlow2 v2.5.3，电子纸首帧和输入重绘通过；
- Core2：官方 UIFlow2 已进入 `main.py`，完成 320x240 首帧和触摸重绘；QEMU 暂用 `-m 0` 规避 PSRAM/cache 稳定性问题；
- StopWatch：原有 466x466 圆屏触摸回归继续通过。

补丁不包含 `build/qemu/meson.build` 的本地 slirp 构建修复。
