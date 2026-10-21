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

汇总：

```text
PASS    5
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

## 尚未闭环

- 音频 I2S/PDM 的 PCM 注入与扬声器 PCM 抓取；
- IR 原始脉冲注入/捕获；
- SX1262 LoRa、ST25R3916 NFC 完整包级协议；
- SD 卡块设备矩阵、USB Host 虚拟端点；
- Tab5 SC2356/MIPI-CSI、ES8388 音频和 ST7123 完整数据面；
- 所有项目的真机复测。

这些项目已在 `platform/peripherals/catalog.json` 中逐器件登记，CI 会阻止新增
设备只做显示/触摸而漏掉传感器、总线或执行器。
