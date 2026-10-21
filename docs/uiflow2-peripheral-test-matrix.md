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
| CoreS3 | LTR553 环境光 | `M5.Als` | PARTIAL |
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
| StopWatch | M5IOE1 PWM1 振动马达开关与占空比 | `Power.setVibration()` | PASS |
| AtomS3R | LP5562 三通道 RGB PWM 写入/回读 | I2C `0x30` | PASS |

汇总：

```text
PASS    15
PARTIAL 1
```

唯一的 `PARTIAL` 是 CoreS3 的 LTR553：芯片 ID 和寄存器读取路径已存在，但
当前 UIFlow2 `M5.Als` 板上初始化路径仍返回 0。其余本轮覆盖项均完成
“注入 -> 控制器/总线 -> 芯片模型 -> UIFlow2 API -> 屏幕/帧输出”的闭环。

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
- `tests/uiflow2/stopwatch_vibration/`
- `tests/uiflow2/atoms3r_lp5562/`

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

### StopWatch vibration

![StopWatch vibration probe](images/stopwatch-vibration-test.png)

### AtomS3R LP5562

![AtomS3R LP5562 probe](images/atoms3r-lp5562-test.png)

## 尚未闭环

- 音频 I2S/PDM 的 PCM 注入与扬声器 PCM 抓取；
- ESP32-C6 RMT/IR 路径（StickS3 的 ESP32-S3 RMT 已闭环）；
- ST25R3916 SPI/NFCCap 路径；
- MicroPython/IDF 大于 4 字节 SPI 的总线锁路径；
- Cardputer/PaperColor 的 SPI SD 路径、USB Host 虚拟端点；
- Tab5 SC2356/MIPI-CSI、ES8388 音频和 ST7123 完整数据面；
- 所有项目的真机复测。

这些项目已在 `platform/peripherals/catalog.json` 中逐器件登记，CI 会阻止新增
设备只做显示/触摸而漏掉传感器、总线或执行器。
