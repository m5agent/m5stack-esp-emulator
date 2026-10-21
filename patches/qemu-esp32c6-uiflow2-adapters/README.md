# ESP32-C6 UIFlow2 虚拟主机补丁

该补丁应用在 Espressif QEMU 的 ESP32-C6 后端 `febae18` 上，新增：

- C6 启动所需的 SARADC 一次性采样完成握手；
- C6 SPI flash 的 4-byte address、DIOR/QIOR mode byte 和 SPI2 register window；
- C6 功能 GPIO、软件 I2C 探针桥、HP I2C0，以及 PI4IOE/FT5x06/BMI270、
  BQ27220 电量计和 AW32001 充电器模型；
- ESP32-C6 RMT TX/RX 控制器、APB FIFO、硬件符号 RAM、TX_END/RX_END
  中断和 NEC 符号抓取；
- ESP32-C6 SPI2 的 DMA `TRANS_DONE` 状态，以及 Nesso 共享 SPI2 上通过
  GPIO20-23 连接的 SX1262 命令/寄存器/FIFO 和本地 TX-RX 回环模型；
- ESP32-C6 I2S TX/RX 寄存器前端与 GDMA 连接骨架；Nesso GPIO11 蜂鸣器的
  I2S DMA 数据落入仍为全零，因此蜂鸣器保持 planned；
- Nesso N1 的 135x240 ST7789 虚拟屏和 QMP 触摸输入；
- Nesso BMI270 的初始化、数据就绪和 accel/gyro 采样寄存器/QOM 注入；
- USB-Serial-JTAG console 下的 NanoC6 UIFlow2 启动路径。

## 应用

```bash
cd "$QEMU_ROOT/build/qemu-c6"
git apply /path/to/0001-qemu-c6-m5stack-uiflow2-adapters.patch
```

补丁不包含 C6 根目录 `meson.build` 的本地构建绕过。

## 验证边界

- NanoC6：官方 UIFlow2 v2.5.3 可启动自定义 `/boot.py`、`/main.py`，`M5.begin()` 返回板型 140；无显示屏。
- NanoC6：`hardware.IR.tx()` 经 ESP32-C6 RMT 发送 NEC `0x56/0xA3`。
- Nesso N1：M5GFX 选择 `ArduinoNessoN1`，显示尺寸为 135x240；QMP 触摸和
  按键输入、双 PI4IOE 输出/中断状态、BQ27220 电池遥测、AW32001 充电状态
  、BMI270 加速度/角速度、ESP32-C6 RMT 红外和 SX1262 LoRa 收发均通过
  UIFlow2 API 闭环。
- Nesso N1 GPIO11 蜂鸣器：`Speaker.begin()` 和 I2S/GDMA 启动可观测，但
  当前捕获的 DMA 缓冲仍全为零，不能作为完整蜂鸣器闭环。
- Core2 与 S3 设备的补丁分别位于 `qemu-multi-board-uiflow2/`；本补丁不改变它们的验收边界。
