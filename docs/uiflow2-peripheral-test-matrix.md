# UIFlow2 外设 API 测试矩阵

日期：`2026-10-21`

本矩阵验证的是 QEMU 中的完整控制器/总线路径，而不是在 Python 测试代码里伪造
API 返回值。当前结果只代表仿真验收，不是实机验收。

## 本轮结果

| 设备 | 闭环能力 | UIFlow2 API | 结果 |
| --- | --- | --- | --- |
| StickS3 | BMI270 三轴加速度/角速度 | `Imu.getAccel()` / `getGyro()` | PASS |
| StickS3 | A/B/PWR 按键 | `BtnA` / `BtnB` / `BtnPWR` | PASS |
| StickS3 | M5PM1 电池、电压、充电 | `Power.*` | PASS |
| AtomS3R | BMI270 三轴加速度/角速度 | `Imu.getAccel()` / `getGyro()` | PASS |
| AtomS3R | BMM150 三轴磁力计 | `Imu.getMag()` | PASS |
| AtomS3R | 用户按键 | `BtnA` | PASS |
| CoreS3 | BMI270 + BMM150 | `Imu.getAccel/getGyro/getMag()` | PASS |
| CoreS3 | FT6336、PWR、AXP2101、BM8563 | Touch / Button / Power / RTC | PASS |
| CoreS3 | LTR553 环境光 | `M5.Als` | PASS |
| CoreS3 | GC0308 初始化、LCD_CAM 采集、GDMA 帧、拍照 | `camera.init()` / `camera.snapshot()` | PASS |
| StopWatch | BMI270、CST820、M5PM1、RX8130、A/B/PWR | IMU / Touch / Power / RTC / Button | PASS |
| StamPLC | PI4IOE 继电器/输入、RGB、INA226 | StamPLC / INA226Unit | PASS |
| PaperMono | BMI270、M5PM1、RX8130、FT6336、按键、SDMMC | IMU / Power / RTC / Touch / Button / SDCard | PASS |
| StickS3 | RMT0 NEC 38 kHz 红外发送 | `hardware.IR.tx()` | PASS |
| StickS3 | RMT4 NEC 红外接收与回调 | `hardware.IR.rx_cb()` | PASS |
| PaperMono | ST25R3916 I2C NFC 检测、读页、写页回读 | `hardware.NFC` | PASS |
| PaperMono | SX1262 868 MHz 配置、TX、RX 回环 | `lora.SX1262` | PASS |
| StackChan | ST25R3916 I2C NFC 检测、读页、写页回读 | `hardware.NFC` | PASS |
| StackChan | Si12T 三点身体触摸 | `driver.si12t.Si12T` | PASS |
| StackChan | M5IOE1 12 路 NeoPixel RGB 写入/回读 | `driver.m5ioe1.RGB` | PASS |
| StackChan | SCS 总线双舵机 PING、扭矩、位置写入/回读 | `driver.scs_servo.Scscl` | PASS |
| StopWatch | M5IOE1 PWM1 振动马达开关与占空比 | `Power.setVibration()` | PASS |
| AtomS3R | LP5562 三通道 RGB PWM 写入/回读 | I2C `0x30` | PASS |
| StickS3 | ES8311/AW8737A 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| StickS3 | ES8311 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| StopWatch | ES8311/AW8737A 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| StopWatch | ES8311 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| CoreS3 | AW88298 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| CoreS3 | ES7210 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| StackChan | AW88298 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| StackChan | ES7210 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| Cardputer-ADV | ES8311/NS4150B 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| Cardputer-ADV | ES8311 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| Cardputer-ADV | SPI microSD 初始化、512B 写入/回读、原始镜像校验 | `machine.SDCard(slot=3)` | PASS |
| PaperMono | PDM 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| PaperColor | ES8311/AW8737A 扬声器 I2S TX、GDMA、PCM 抓取 | `Speaker.tone()` | PASS |
| PaperColor | ES7210 麦克风 I2S RX、GDMA、PCM 注入 | `Mic.record()` | PASS |
| PaperColor | SPI microSD 初始化、512B 写入/回读、原始镜像校验 | `machine.SDCard(slot=2)` | PASS |
| PaperColor | SHT4X 温度/湿度命令、转换和 CRC8 | `hardware.SHT4X` | PASS |
| Core2 | NS4168 扬声器、ESP32 I2S1 linked-list DMA、AXP2101 ALDO3 使能 | `Speaker.tone()` | PASS |
| Core2 | SPM1423 PDM 麦克风、ESP32 I2S0 linked-list DMA | `Mic.record()` | PASS |
| Core2 | INA3221 ID、总线电压和分流电压寄存器 | ESP32 I2C0 | PASS |

汇总：

```text
PASS    36
```

本轮所有矩阵用例均完成“注入 -> 控制器/总线 -> 芯片模型 -> UIFlow2 API ->
屏幕/帧输出”的闭环。

## 关键修复

### ESP32-S3 I2C FIFO 与重复起始

ESP-IDF 会以 32 位访问一次写入地址和数据。此前模型只消费首个字节，导致
BMI270 软复位后的配置上传被截断。模型现在正确处理 FIFO RAM 字节序，并在
RESTART 前结束上一次 QEMU I2C 事务，StickS3、AtomS3R 和 CoreS3 的 BMI270
初始化因此全部闭环。

### BMM150 Sensor Hub

BMM150 原始数据、轴向转换和 QOM 注入已经闭环。测试输入为
`30 / -20 / 45 uT`，AtomS3R 经板级轴变换后显示 `-30 / -19.5 / -90 uT`，
与 M5Unified 的固定轴映射一致。

### LTR553 ALS

CoreS3 的 LTR553 在 I2C `0x23` 上返回 part ID `0x92` 和 manufacturer ID
`0x05`；四字节 ALS 通道数据由 QOM `light-level` 注入，`M5.Als` 从
`0x88..0x8B` 读取并正确回传环境光值。

### INA226

模型改为真实寄存器语义：

- `0x01` shunt voltage
- `0x02` bus voltage
- `0x03` power
- `0x04` current
- `0x05` calibration
- `0xFE` manufacturer ID `0x5449`
- `0xFF` die ID `0x2260`

`bus-voltage-mv`、`current-ma`、`shunt-ohms` 可通过 QOM 动态注入。StamPLC
目标值 `12.00 V / 0.500 A` 已正确回读。

### GC0308 / ESP32-S3 LCD_CAM / GDMA

新增 LCD_CAM 模型，按 `esp32-camera` 使用的 VSYNC 中断、GDMA RX 描述符和
半缓冲事件交付 RGB565 帧。`camera.snapshot()` 返回
`320x240 / 153600 bytes`，并能通过 `M5.Display.show()` 显示。

高带宽帧可通过宿主文件注入：

```bash
M5SW_CAMERA_FRAME=/path/frame-320x240-rgb565.raw \
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py ...
```

### ESP32-S3 RMT / NEC 红外

此前 SoC 中的 RMT 是 unimplemented。现在补了 RMT APB 配置寄存器、
`RMTMEM` 硬件符号内存、通道状态和 `TX_END/RX_END` 中断：

- TX：UIFlow2 `hardware.IR.tx()` 编码到 RMT0，QEMU 从 RMTMEM 读取 34 个
  NEC 符号，解码回地址 `0x56`、命令 `0xA3`；
- RX：宿主把 34 个 NEC 符号写入 RMT4 硬件内存并触发 RX_END，
  `hardware.IR.rx_cb()` 收到 `address=0x56 / data=0xA3`，UI 成功标记变绿。

相关文件：

```bash
M5SW_RMT_TX_FILE=/tmp/ir.rmt
M5SW_RMT_RX_FILE=/tmp/nec-56-a3.rmt
```

NEC 捕获/注入格式为小端 `rmt_symbol_word_t` 序列。

### ST25R3916 I2C NFC

PaperMono 与 StackChan 的 NFC 使用 ST25R3916 I2C 模式（地址 `0x50`）。模型
实现命令/寄存器/FIFO 协议和 ISO14443A 标签交互，而不是在 Python 中伪造
`detect()`：

- REQA/WUPA 返回 ATQA；
- anticollision 返回 UID + BCC；
- SELECT 返回 SAK；
- GET_VERSION 识别 Type 2/NTAG；
- Type 2 READ 从标签页返回数据和 CRC 占位；
- WRITE_PAGE 更新标签页，随后 READ 回读一致。

两台设备均检测到 UID `DEADBEEF`，PaperMono 写入/回读 page 8 的 `TEST`，
StackChan 写入/回读 page 12 的 `CHAN`。

### PaperMono SX1262 LoRa

PaperMono 使用独立 SPI3 控制器连接 SX1262。模型实现命令状态、参数、寄存器、
TX/RX FIFO、IRQ、RSSI/SNR 和本地 TX 到 RX 的回环数据面。测试通过 native
`lora.SX1262` 完成：

- `SET_STANDBY`、TCXO、DIO2 RF switch 和 IRQ 配置；
- 868 MHz、SF7、125 kHz、CR 4/5 调制配置；
- `WRITE_BUFFER("M5LORA")` 与 `SET_TX`；
- `SET_RX`、`GET_IRQ_STATUS`、`GET_RX_BUFFER_STATUS` 和 `READ_BUFFER`；
- UI 回读 `packet=b'M5LORA' / status=ok`。

测试适配层保持 CS 连续，并把单次 SPI 传输切成不超过 4 字节。这个适配绕过
了当前仿真中尚未闭环的 IDF `spi_device_acquire_bus()` 大于 4 字节事务路径；
数据仍经过真实 GP-SPI 寄存器、GDMA 和 SX1262 模型，不是在 Python 中直接构造
LoRa 返回值。

### StackChan Si12T 身体触摸

Si12T 在 `0x68` 上完成寄存器配置，QOM `touch-bits` 注入后，
`get_touch_status()` 解码出 `[2, 0, 0]`，屏幕绘制成功标记。

### StackChan M5IOE1 RGB

官方 M5IOE1 NeoPixel 驱动通过 I2C 配置 12 颗 RGB，写入红色后从 LED RAM
读回 RGB565 `0xF800`，验证的是扩展器寄存器数据面。

### StackChan SCS 舵机

UIFlow2 通过 UART1（TX GPIO6、RX GPIO7、1 Mbps）使用官方
`driver.scs_servo.Scscl`。QEMU 的 SCSCL 模型从真实 UART TX 字节流解析
`PING`、`WRITE` 和 `READ` 帧，并校验帧尾 checksum：

- ID 1/2 PING 分别返回自身 ID；
- torque enable 写入寄存器 40；
- X/Y 目标位置写入 `500/300`；
- present position 从寄存器 56 回读 `500/300`；
- UI 显示 `status=ok`。

为使该路径可通过，ESP32-S3 系统时钟模型同时补齐了 UART0/1/2 的
`PERIP_CLK_EN` 和 `PERIP_RST_EN` 复位值及读写语义。

### I2S/GDMA 音频数据面

QEMU 的 I2S 模型现在区分 TX/RX，并按真实 GDMA 循环描述的语义逐缓冲区完成：

- TX：ES8311/AW88298/AW8737A 配置完成后，扬声器驱动写入 I2S DMA；
  模型逐个描述符产生 `OUT_EOF`，宿主将实际 PCM 写到
  `M5SW_I2S_PCM_FILE`；
- RX：宿主通过 `M5SW_I2S_RX_PCM_FILE` 注入 16-bit PCM，模型写入 I2S RX
  的 GDMA 描述符并产生 `IN_SUC_EOF`，UIFlow2 `Mic.record()` 可以读到真实
  非静音数据；
- 设备覆盖 StickS3、StopWatch、CoreS3、StackChan、Cardputer-ADV 和
  PaperColor；PaperMono 的 PDM RX 路径走同一 I2S/GDMA 数据面。

StickS3 扬声器抓取的 64 KiB PCM 有 18410 个非零样本，峰峰值 2881；
CoreS3 扬声器抓取峰峰值 11523，均来自固件实际 I2S 写入而不是 Python 伪造。

### SPI microSD

GP-SPI 从设备模型实现了 SD SPI 命令状态机：

- CMD0/8/9/10/13/16/17/24/51/55/58/59；
- ACMD41、ACMD13、ACMD51；
- R1/R2/R3/R7、数据 token、CRC16 和 512 字节单块读写；
- `M5SW_SPI_SD_IMAGE` 指定原始 SD 镜像，写入后主机可直接校验扇区内容。

Cardputer-ADV 使用 `SCK=G40 / MOSI=G14 / MISO=G39 / CS=G12`，PaperColor
使用 `SCK=G15 / MOSI=G13 / MISO=G14 / CS=G47`，两者都通过
`machine.SDCard` 完成写入和回读，未在 Python 侧伪造块数据。

### PaperColor SHT4X

SHT4X 通过 ESP32-S3 I2C 完成测量命令、温度/湿度转换和两段 CRC8 校验；
官方 `hardware.SHT4X.measure()` 返回默认注入的 `25 °C / 50 %RH` 范围值。

### Core2 v1.1 NS4168 与 SPM1423

Core2 固件 SKU 为 `K010-V11`，官方原理图对应 AXP2101 + INA3221，而不是旧版
Core2 的 AXP192。板级模型已改为 AXP2101，扬声器使用 ESP32 I2S1，麦克风
使用 I2S0 PDM RX。

QEMU 直接读取 IDF 生成的 `lldesc_t` 描述符链：

- TX：逐个消费 guest DMA 描述符，触发 `OUT_EOF`，宿主抓到 32768 字节 PCM，
  非零样本 16356，峰峰值 46091；
- RX：向 guest RX 描述符写入确定性 PCM，触发 `IN_SUC_EOF`，官方
  `Mic.record()` 录到非静音数据；
- NS4168 功放使能由 AXP2101 ALDO3 控制，QOM 断言
  `/machine/axp2101 speaker-enabled=true` 通过。

### Core2 v1.1 INA3221

INA3221 在 ESP32 I2C0 的 `0x40/0x41` 地址上提供三通道电源监控。测试注入
CH1 `4800 mV / 240 mA`，固件通过真实 I2C 传输读取：

- die ID `0x3220`；
- bus voltage raw `600`，对应 `4800 mV / 8 mV`；
- shunt voltage raw `60`，对应 `240 mA × 10 mΩ / 40 uV`。

### StopWatch 振动马达

`Power.setVibration(128)` 写入 M5IOE1 PWM1 的 12 位占空比和 enable 位，
模型回读 duty `2055`；再次调用 `setVibration(0)` 后 enable 清零。

### AtomS3R LP5562

LP5562 在 I2C `0x30` 上完成 enable/mode 配置，独立写入 R/G/B PWM
`0x80/0x40/0x20` 后逐寄存器回读一致。

## 运行

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

源码：

- `tests/uiflow2/sticks3_peripherals/`
- `tests/uiflow2/atoms3r_peripherals/`
- `tests/uiflow2/cores3_peripherals/`
- `tests/uiflow2/cores3_camera/`
- `tests/uiflow2/stamplc_peripherals/`
- `tests/uiflow2/stopwatch_peripherals/`
- `tests/uiflow2/sticks3_ir/`
- `tests/uiflow2/sticks3_ir_rx/`
- `tests/uiflow2/papermono_nfc/`
- `tests/uiflow2/papermono_lora/`
- `tests/uiflow2/papermono_spi_probe/`
- `tests/uiflow2/stackchan_nfc/`
- `tests/uiflow2/stackchan_touch/`
- `tests/uiflow2/stackchan_rgb/`
- `tests/uiflow2/stackchan_servo/`
- `tests/uiflow2/stopwatch_vibration/`
- `tests/uiflow2/atoms3r_lp5562/`
- `tests/uiflow2/sticks3_audio/`
- `tests/uiflow2/sticks3_mic/`
- `tests/uiflow2/cores3_audio/`
- `tests/uiflow2/cores3_mic/`
- `tests/uiflow2/stackchan_audio/`
- `tests/uiflow2/stackchan_mic/`
- `tests/uiflow2/stopwatch_audio/`
- `tests/uiflow2/stopwatch_mic/`
- `tests/uiflow2/cardputer_adv_audio/`
- `tests/uiflow2/cardputer_adv_mic/`
- `tests/uiflow2/cardputer_adv_sd/`
- `tests/uiflow2/papermono_mic/`
- `tests/uiflow2/papercolor_audio/`
- `tests/uiflow2/papercolor_mic/`
- `tests/uiflow2/papercolor_sd/`
- `tests/uiflow2/papercolor_sht4x/`
- `tests/uiflow2/core2_audio/`
- `tests/uiflow2/core2_mic/`
- `tests/uiflow2/core2_power_monitor/`

## 屏幕证据

### StickS3

![StickS3 peripheral probe](images/sticks3-peripheral-test.png)

### AtomS3R

![AtomS3R peripheral probe](images/atoms3r-peripheral-test.png)

### CoreS3

![CoreS3 peripheral probe](images/cores3-peripheral-test.png)

### CoreS3 camera

![CoreS3 camera probe](images/cores3-camera-probe.png)

### StamPLC

![StamPLC peripheral probe](images/stamplc-peripheral-test.png)

### StopWatch

![StopWatch peripheral probe](images/stopwatch-peripheral-test.png)

### PaperMono

![PaperMono peripheral probe](images/papermono-peripheral-test.png)

### StickS3 IR TX

![StickS3 IR TX probe](images/sticks3-ir-tx-test.png)

### StickS3 IR RX

![StickS3 IR RX probe](images/sticks3-ir-rx-test.png)

### PaperMono NFC

![PaperMono NFC probe](images/papermono-nfc-test.png)

### PaperMono SX1262 LoRa

![PaperMono LoRa probe](images/papermono-lora-test.png)

### StackChan NFC

![StackChan NFC probe](images/stackchan-nfc-test.png)

### StackChan Si12T touch

![StackChan Si12T touch probe](images/stackchan-touch-test.png)

### StackChan RGB

![StackChan RGB probe](images/stackchan-rgb-test.png)

### StackChan SCS servo

![StackChan SCS servo probe](images/stackchan-servo-test.png)

### StopWatch vibration

![StopWatch vibration probe](images/stopwatch-vibration-test.png)

### AtomS3R LP5562

![AtomS3R LP5562 probe](images/atoms3r-lp5562-test.png)

### Audio and SD data planes

![StickS3 audio](images/sticks3-audio-test.png)

![StickS3 microphone](images/sticks3-mic-test.png)

![CoreS3 audio](images/cores3-audio-test.png)

![CoreS3 microphone](images/cores3-mic-test.png)

![StopWatch audio](images/stopwatch-audio-test.png)

![StopWatch microphone](images/stopwatch-mic-test.png)

![Cardputer-ADV audio](images/cardputer-adv-audio-test.png)

![Cardputer-ADV microphone](images/cardputer-adv-mic-test.png)

![Cardputer-ADV SD](images/cardputer-adv-sd-test.png)

![PaperColor audio](images/papercolor-audio-test.png)

![PaperColor microphone](images/papercolor-mic-test.png)

![PaperColor SD](images/papercolor-sd-test.png)

![PaperColor SHT4X](images/papercolor-sht4x-test.png)

![PaperMono PDM microphone](images/papermono-pdm-mic-test.png)

![StackChan audio](images/stackchan-audio-test.png)

![StackChan microphone](images/stackchan-mic-test.png)

![Core2 audio](images/core2-audio-test.png)

![Core2 microphone](images/core2-mic-test.png)

![Core2 INA3221](images/core2-ina3221-test.png)

## 尚未闭环

- ESP32-C6 RMT/IR 路径（StickS3 的 ESP32-S3 RMT 已闭环）；
- ST25R3916 SPI/NFCCap 路径；
- USB Host 虚拟端点；
- Tab5 SC2356/MIPI-CSI、ES8388 音频和 ST7123 完整数据面；
- CAN/RS485、蜂鸣器等尚未完成闭环的路径；
- 所有项目的真机复测。

这些项目已在 `platform/peripherals/catalog.json` 中逐器件登记，CI 会阻止新增
设备只做显示/触摸而漏掉传感器、总线或执行器。
