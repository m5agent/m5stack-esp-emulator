# ESP32-C6 UIFlow2 虚拟主机补丁

Last reviewed: `2026-11-13`

该补丁应用在公开的 Espressif QEMU ESP32-C6 提交
`febae182e132e4055529be423a818225ebddaa3a` 上，新增：

- C6 启动所需的 SARADC 一次性采样完成握手；
- C6 SPI flash 的 command-aware address width：16 MiB 读路径使用 4-byte
  address，legacy `0x02` Page Program/`0x20` Sector Erase 固定使用
  3-byte address，显式 4-byte opcode 保持不变；同时支持 DIOR/QIOR mode
  byte 和 SPI2 register window；
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

`0008-c6-aes-gdma-wiring.patch` 将共享 ESP AES 数据面接到 C6 的
AES MMIO、GDMA request 6 和 IRQ source 73；不再让原版 Bruce 永久等待
未接线的 `AES_STATE`。Nesso/NanoC6 的 NIST CBC、4096 字节 DMA 与中断
回归见 [AES 用例](../../tests/firmware/esp32c6_aes/README.md)。这不等于
Bruce 的 LittleFS 或 issue #216 全部固件通过。

`0009-c6-qio-flash-header.patch` 按 C6 SPI1 的实际 Flash 型号补齐
SSI QIO mode/dummy header：16 MiB ISSI 使用 3 字节，其他支持的
Winbond/GigaDevice 型号使用 5 字节。它保留 guest 寄存器和 SPI2 数据面；
读写对照使用 [C6 Flash 探针](../../tests/firmware/esp32c6_flash_qio/README.md)。

`0010-c6-sx1262-hardware-spi.patch` 将 Nesso 的硬件 SPI2 和 GPIO SPI
接入同一个 SX1262 状态，保留接收 FIFO 字节，并将 SPI2 `UPDATE` 与
SPI1 Flash 特殊命令分开。芯片支持连续寄存器读写、只读版本标识和
packet-type 状态；[SPI 探针](../../tests/firmware/esp32c6_sx1262_spi/README.md)
及原版 Meshtastic 的命令流覆盖该路径。原版 Meshtastic 越过无线初始化后
仍触发 TG0 watchdog，不能据此宣称整份应用通过；这也不建立 RF 验证。

`0011-c6-isolated-wifi-presence.patch` 保留无宿主网络时的 WiFi/PHY
硬件寄存器与计时器；未配置 backend 时不注入 AP、响应或 RX 数据。
同 BIN 的有/无 NIC 控制器对照见
[radio controller 探针](../../tests/firmware/esp32c6_radio_controllers/README.md)。
原版 Meshtastic 可越过此前静止计时器的等待，后续 BLE 加密控制器缺口
仍独立保留。

`0012-c6-ble-aes-dma.patch` 为 `r_ble_hw_encrypt_block` 实际使用的
`0x600a9400` 独立控制器执行 AES-128 ECB 单块 DMA。NIST 向量及同一原版
Meshtastic 的 NimBLE 同步/GATT 注册有独立证据；后续 TG0 watchdog 仍在，
并不意味着 native BLE、RF 或完整应用通过。

`0013-c6-lpperi-rng.patch` 提供实际 LPPERI RNG 寄存器和 clock gate，
数据来自 QEMU guest-random；寄存器/API 功能验证不等于熵质量或硬件安全验证。

`0014-c6-nesso-panel-madctl.patch` 在固定物理裁剪之前执行 ST7789
MADCTL 地址交换/镜像，并公开显示方向元数据。Device Service 可据此返回
逻辑显示帧；触摸坐标仍保留物理玻璃空间契约。

`0015-c6-spi2-data-length.patch` 将 HP SPI2 的 18-bit `MS_DLEN` 与
SPI1 的 10-bit Flash 长度字段分开，保留 FIFO 字节并约束 DMA 缓冲区。
没有绑定的 TX DMA 通道或空描述符不能退回 FIFO，也不能伪造传输完成。
[显示探针](../../tests/firmware/esp32c6_panel_madctl/README.md) 分别验证
四种旋转与 352 字节 DMA；当前 DMA helper 仍是单描述符、4096 字节上限，
该探针不建立硬件自动 CS、链式 DMA 或超大传输的覆盖。

`0016-c6-spi2-chip-select-routing.patch` 将 SPI2 CS0..5 经 C6 GPIO
输出矩阵路由到实际板级引脚，并处理 CS disable、polarity、KEEP_ACTIVE
及 GPIO 输出使能/反相。屏幕只在 GPIO17 低、无线电 GPIO23 高时接收数据；
双 CS 未选中时不能把传输误送屏幕。显示探针分别覆盖未选中负控、radio
隔离和 ESP-IDF 自动 CS0/GPIO17 整帧填色；不宣称电气时序覆盖。

## 当前开放边界

`0021-c6-efuse-unprovisioned-defaults.patch` 隔离无 backing 时继承的 C3
默认字段，保留 C3 与显式 C6 backing。原 Bruce 的 0019 前后差分及
[实际 C 负/正控制](../../tests/firmware/esp32c6_efuse_defaults/README.md)
已记录；修正后 combined runtime 原 BIN 验收仍为 **NOT RUN**。

`0020-c6-usb-serial-jtag-endpoints.patch` 为固定 CDC IN/OUT 端点提供
64 字节 FIFO、真实 chardev 收发、背压及 C6 IRQ48 接线。独立
[HWCDC 与 UIFlow2 USB REPL 用例](../../tests/firmware/esp32c6_usb_serial_jtag/README.md)
不继承 USB 枚举、EP0、USB OTG、JTAG 或物理电气覆盖。

`0018-c6-wifi-tsf-counter.patch` 补齐原 WiFi HAL 使用的四个 TSF
计数器、门控、64 位加载与一致性快照。`0019-c6-efuse-lp-subregion.patch`
修正被宽 LP 区域遮蔽的 eFuse MMIO 映射；NanoC6 的会话身份经实际
eFuse backing/controller 和 guest API 读取。对应
[同 BIN 控制与原版边界](../../tests/firmware/esp32c6_tsf_identity/README.md)
不授予 802.15.4 数据面、RF 或 Honeypot 完整网络就绪。

该补丁让基线 UIFlow2 和多个公开固件运行，但没有覆盖全部 C6 运行时语义。
当前仍开放的模型缺口是 Zigbee/802.15.4 控制器未建模。C6
`LP_SW_HPSYS` 后 chip id `13/12` 已定位为 16 MiB Flash legacy 写擦命令被
全局 4-byte 模式误解析，以及 C6 reset 后旧 PMP range 未清除；对应修复已由
Device Service 重跑关闭 `RUNTIME-01`。后续 Meshtastic 的 radio、PHY、
AES、RNG 与显示故障已分层记录；早先 PC=0 或晚期黑帧不能替代最新同 BIN
的启动、输入与定时观察结果。Launcher 的跨任务 SPI 锁失败、RFID 的
未建模 PN532Killer 外设仍有独立边界，不能概括为 issue #216 全部通过：
[运行时模型缺口登记](../../docs/runtime-model-gap-register.md)。

## 可重复构建

C6 使用独立的公开基点和 `riscv32-softmmu` 目标；Xtensa 的
`bootstrap-unit-runtime.py` 不包含这条补丁线。安装本机 QEMU 构建依赖后运行：

```sh
python3 scripts/bootstrap-c6-runtime.py --source-dir .work/c6-runtime-source --jobs 4
```

该脚本固定源码提交和补丁顺序，保存每个修改文件及最终二进制的 SHA256，
并拒绝覆盖无归属或被修改的源码树。`--prepare-only` 只准备源码；
`PKG_CONFIG_PATH` 可指向已有的私有依赖目录。静态 libgcrypt 构建可通过
`--extra-ldflags="<prefix>/lib/libgcrypt.a <prefix>/lib/libgpg-error.a"`
显式提供依赖。脚本不会安装全局软件包。

`0007-wifi-context.patch` 是已有 peripherals `0025` 的上下文移植；
它只调整 C6 board 的空行上下文，WiFi 控制器实现不变。构建成功不表示
社区固件运行通过；运行验证必须使用 Device Service 会话。

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
git apply /path/to/0006-espressif-riscv-reset-pmp.patch
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
- C6 16 MiB Flash：Meshtastic 的 core dump Page Program 保持在
  `0x300000/0x900000...`，offset 0 的 C6 secondary bootloader 头不再被
  覆盖；`LP_SW_HPSYS` 后重复 boot 不再报 `Invalid chip id`。
- C6 reset/PMP：第二次 ROM boot 可将 LP-RAM trampoline 写入
  `0x50002000`，不再命中上一轮遗留的 read-only PMP range。
- Core2 与 S3 设备的补丁分别位于 `qemu-multi-board-uiflow2/`；本补丁不改变它们的验收边界。

## 0017: PCR MWDT source and gate

`0017-c6-mwdt-pcr-clock.patch` connects each C6 PCR MWDT clock mux/gate to its
TIMG input and preserves source-cycle progress when retiming. It also treats
C6 divider reset as a one-shot write trigger. Other TIMG clock paths retain
their existing selection. The canonical bootstrap replays this after 0016.
See [the guest and actual-C controls](../../tests/firmware/esp32c6_mwdt_clock/README.md)
for exact native runtime/firmware identities, original RFID failure separation,
and the pending full-matrix boundary.

## 0024: ordinary GPIO source 30

`0024-c6-gpio-interrupt-delivery.patch` adds C6 raw GPIO pending, per-pin CPU
routing, edge/level capture, W1TS/W1TC, IRQ reset and the machine connection to
existing interrupt-matrix source 30. Only the C6 subclass opts into this model.
NMI source 31, wakeup/filter timing, BMI270 IRQ generation and FT6336 trigger
pulses are outside the change. The actual-C before/after sanitizer controls
pass; the rebuilt runtime and guest ISR/Pin.irq probes are **NOT RUN**. See the
[fixed-source and guest workflow](../../tests/firmware/esp32c6_gpio_irq/README.md).
