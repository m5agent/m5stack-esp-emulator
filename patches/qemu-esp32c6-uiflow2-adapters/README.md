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
- ESP32-C6 I2S TX/RX 寄存器前端、C6 独立的 GDMA `IN[3]+OUT[3]` 中断布局、
  循环 OUT 描述符完成、`OUT_EOF` 回调和 GPIO11 1-bit ΔΣ PCM 抓取；
- Nesso N1 的 135x240 ST7789 虚拟屏和 QMP 触摸输入；
- Nesso BMI270 的初始化、数据就绪和 accel/gyro 采样寄存器/QOM 注入；
- USB-Serial-JTAG console 下的 NanoC6 UIFlow2 启动路径。
- NanoC6/Nesso N1 板级装配隔离：`M5SW_C6_BOARD=nanoc6` 时不创建 Nesso
  屏幕、SX1262、板载 I2C 或强制 GPIO 线；
- NanoC6 GPIO9 按键 QOM 注入，以及 GPIO7/GPIO9/GPIO19 电平观测；
- ESP32-C6 GPIO 寄存器写入 trace（`M5SW_GPIO_TRACE=1`）。
- `MODEM_SYSCON_CLK_CONF1` 的可写寄存器模型，保留 PHY 初始化要求的
  `0x7E1FF` clock mask，使公开 C6 固件可以越过 `esp_phy_enable()` 断言。
- 热门用户固件回归所需的 C6 修正：8 个命令寄存器、空 RX FIFO `0xff`、
  SCL reset 寄存器布局、PCR LEDC clock、compact LEDC layout、SPI2/GDMA
  TX/RX、`TRANS_DONE` 中断，以及共享 GDMA 的 OUT FIFO 完成握手。

## 应用

```bash
cd "$QEMU_ROOT/build/qemu-c6"
git apply /path/to/0001-qemu-c6-m5stack-uiflow2-adapters.patch
git apply /path/to/0002-nanoc6-board-isolation-gpio.patch
git apply /path/to/0016-gigadevice-status2-qio.patch
git apply /path/to/0017-issi-status2-qio.patch
git apply /path/to/0003-modem-syscon-clock-bits.patch
git apply /path/to/0004-user-firmware-hot-samples.patch
git apply /path/to/0005-c6-uart-timeout-registers.patch
```

补丁不包含 C6 根目录 `meson.build` 的本地构建绕过。

## 验证边界

- NanoC6：官方 UIFlow2 v2.5.3 可启动自定义 `/boot.py`、`/main.py`，`M5.begin()` 返回板型 140；无显示屏。
- NanoC6：C6 UART `TOUT_CONF`、FIFO reset、阈值寄存器按 C6 布局建模，
  UART1 HCI Reset/LE 命令可经 Bumble 回包并完成 NUS GATT 写与通知。
- Nesso N1：同一 C6 guest 同时完成 ST7789/触摸、PI4IOE、电源遥测、
  BMI270、SX1262 回环、RMT IR、蜂鸣器 PCM 和 UART1 HCI BLE。
- NanoC6：`hardware.IR.tx()` 经 ESP32-C6 RMT 发送 NEC `0x56/0xA3`。
- NanoC6：`hardware.RGB()` 打开 GPIO19 RGBPWR，GPIO20 WS2812 GRB 解码为
  `00ff00`；GPIO9 按下/释放、GPIO7 蓝灯开关均通过 GPIO 寄存器验证。
- Nesso N1：M5GFX 选择 `ArduinoNessoN1`，显示尺寸为 135x240；QMP 触摸和
  按键输入、双 PI4IOE 输出/中断状态、BQ27220 电池遥测、AW32001 充电状态
  、BMI270 加速度/角速度、ESP32-C6 RMT 红外和 SX1262 LoRa 收发均通过
  UIFlow2 API 闭环。
- Nesso N1 GPIO11 蜂鸣器：官方 `Speaker.tone()` 经 C6 I2S TX、AHB GDMA
  循环描述符和 `OUT_EOF` 中断输出；宿主抓到 48128 字节 PCM，非零样本
  12866，峰峰值 65535。
- Core2 与 S3 设备的补丁分别位于 `qemu-multi-board-uiflow2/`；本补丁不改变它们的验收边界。
