# ESP32-C6 UIFlow2 虚拟主机补丁

该补丁应用在 Espressif QEMU 的 ESP32-C6 后端 `febae18` 上，新增：

- C6 启动所需的 SARADC 一次性采样完成握手；
- C6 SPI flash 的 4-byte address、DIOR/QIOR mode byte 和 SPI2 register window；
- C6 功能 GPIO、软件 I2C 探针桥、HP I2C0，以及 PI4IOE/FT5x06/BMI270、
  BQ27220 电量计和 AW32001 充电器模型；
- Nesso N1 的 135x240 ST7789 虚拟屏和 QMP 触摸输入；
- USB-Serial-JTAG console 下的 NanoC6 UIFlow2 启动路径。

## 应用

```bash
cd "$QEMU_ROOT/build/qemu-c6"
git apply /path/to/0001-qemu-c6-m5stack-uiflow2-adapters.patch
```

补丁不包含 C6 根目录 `meson.build` 的本地构建绕过。

## 验证边界

- NanoC6：官方 UIFlow2 v2.5.3 可启动自定义 `/boot.py`、`/main.py`，`M5.begin()` 返回板型 140；无显示屏。
- Nesso N1：M5GFX 选择 `ArduinoNessoN1`，显示尺寸为 135x240；QMP 触摸和
  按键输入、双 PI4IOE 输出/中断状态、BQ27220 电池遥测和 AW32001 充电状态
  均通过 UIFlow2 API 闭环。
- Core2 与 S3 设备的补丁分别位于 `qemu-multi-board-uiflow2/`；本补丁不改变它们的验收边界。
