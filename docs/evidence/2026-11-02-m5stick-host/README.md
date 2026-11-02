# M5Stick（K016）虚拟主机接入（工厂固件 boot/OLED 限定 + 模型数据面）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 M5Stick（K016）接入为
独立 classic ESP32 原生 QEMU 主机（machine `m5stick`）。本记录区分两条
lane：官方 EasyLoader 工厂固件的**限定** boot/OLED 证据，以及 generic
classic-ESP32 MicroPython fixture 对板级模型的 guest 数据面证据。
物理声学/光学/电气 `NOT RUN`。

## 结果 1：官方工厂固件（限定、blocked）

M5Stick 没有官方 UIFlow1/UIFlow2 构建；唯一官方可执行镜像是 EasyLoader
安装包内的 FactoryTest。提取工具
`tests/uiflow2/m5stick_factory_test/extract_image.py` 固定：

| 产物 | 大小 | SHA-256 |
| --- | --- | --- |
| `EasyLoader_M5Stick_FactoryTest.exe` | 9,463,808 | `99c640b0ed51bd9670f544164f5542cb9c0303f1b6f84a4ee91e33e6c82e69f4` |
| 连续 flash 段（installer `0x527b41`，`0x571e0` B → flash `0x1000`） | 356,832 | `7435e808475e9774361e4232eb009ce71fdcda33651477d9904e49be4884f036` |
| 规范化 4 MB 镜像 | 4,194,304 | `84228dfb6f0dd9b84b63c33f93a53545d8d43658893f432e3eaf4313923bffca` |

> 研究计划 §3.2 原先记录的规范化镜像 SHA `d960e57e…` 只拷贝了
> `0x471E0` 字节，比 app0 的 `image_end=0x481E0`（相对 app 起点）少
> `0x10000` 字节，导致 app 校验失败并在 bootloader 内静默重启。本记录
> 使用修正后的 `0x571E0` 字节提取，app 校验通过并进入应用代码。

确定性 icount 运行（`-accel tcg,thread=single -icount
shift=2,align=off,sleep=off`，无 trace 依赖）真实串口输出：

```
ets Jul 29 2019 12:21:46
rst:0x1 (POWERON_RESET),boot:0x12 (SPI_FAST_FLASH_BOOT)
...
entry 0x400806b8
mpu9250 addr: FF
```

同时 SH1107 模型收到完整 64×128 U8g2 兼容初始化命令流
（`AE DC00 81 2F 20 A0 C0 A8 7F D3 60 D5 51 D9 22 DB 35 B0 DA12 A4 A6`）
以及 4,096 字节 GDDRAM 数据写（含 1,024 字节非零内容）；设备矩阵
`firmware` case 以串口 `mpu9250 addr:` 为 PASS 标记（2/2 次 PASS；其中
一次在 app 稳定前多经历一个 TG1WDT 复位周期，原始 boot-log 字节不同但
标记稳定），表示"进入固件原生 MPU 探测并显式报告未检测到（0xFF）"，
**不**表示工厂固件按键/九轴或最终 UI 帧通过。

**工厂固件阻塞点**：该 2019 时代 legacy ESP-IDF I2C 驱动的 FIFO 数据写入
路径没有到达 classic I2C 控制器模型（模型只观测到配置/命令寄存器写入与
`TRANS_START`），因此 MPU9250 探测失败并输出 `FF`，固件随后停滞在
UI 绘制/按键阶段之前。原厂固件的按键与九轴数据面因此记 `blocked`，没有
用 host 假值绕过。

## 结果 2：板级模型数据面（generic MicroPython fixture）

`m5stick` 没有可注入 VFS 的官方固件，因此用 generic classic-ESP32
UIFlow2 镜像（Atom Lite 构建，SHA-256 `ae47e82c…`）只作为 guest 传输，
在**同一 `m5stick` machine** 上驱动板级模型；这不是本板官方固件，也不
声明 UIFlow2 支持。fixture 镜像 SHA-256
`1475baac988e8acc…`。

真实 guest 串口标记：

```
M5STICK_BOOT_FLAG / M5STICK_PROBE_START
M5STICK_I2C_SCAN ['0x48', '0x68', '0x75']
M5STICK_MPU_WHO 0x71
M5STICK_MPU_ACCEL_HEX 000000001000
M5STICK_IP5306_SYS 0xbe
M5STICK_IP5306_READ4 0xff
M5STICK_BUTTON 1
M5STICK_PROBE_READY
M5STICK_MPU_ACCEL_X 0
M5STICK_MPU_ACCEL_X 8192
M5STICK_BUTTON_STATE 0
M5STICK_BUTTON_STATE 1
```

- QOM `qom-set /machine/mpu9250 accel-x 2.0` 后 guest 通过真实 I2C 控制器
  读回 raw `8192`（0x2000）；默认 Z 轴 1 g 为 `0x1000`。
- QMP `input-send-event` key `a` 经 SH1107 panel input handler 驱动 GPIO35
  输入寄存器，guest 依次报告按下（`0`）与释放（`1`）。
- IP5306 通过真实 guest I2C 读回寄存器契约：`SYS_CTL0=0xbe`（复位值），
  `READ4=0xff`（无电芯，不伪造电量）。

`0x48` 是 QEMU classic machine 自带的 `tmp105` 便利设备，不是 M5Stick
板载器件。

## 边界

- 工厂固件的 MPU9250 探测、按键、最终 UI 帧未通过；SH1107 只证明初始化
  命令/显存写入路径，不证明对比度、电荷泵、光学或机械玻璃。
- MPU9250 只建模 accel/gyro/temperature 与 WHO_AM_I；AK8963 磁力计
  （bypass 0x0C）、DMP、自检未建模。九轴声称不成立，只声明六轴寄存器
  数据面。
- 官方 MPU9250 仅 Gray 版本存在，Black 版本无 IMU；本记录不区分修订，
  也不声明任意实物装配。
- 蜂鸣器 G26、IR G17、蓝色 LED G19 只登记接线，无 GPIO/RMT 数据面；
  IP5306 KEY 电源键、Grove Unit 协议、USB/CH9102 与低功耗路径未验证。
- 真机、声学、光学、电气、机械与长期稳定性 `NOT RUN`；不转授 StickC /
  Atom 系列。

## 复现

```bash
# 从官方 EasyLoader 提取并校验规范化工厂镜像
python3 tests/uiflow2/m5stick_factory_test/extract_image.py
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device m5stick --flash-transport direct --out-dir /tmp/m5stick-matrix

# 板级模型 fixture（generic classic-ESP32 MicroPython 传输，非本板官方固件）
python3 tests/uiflow2/m5stick_model_probe/make_image.py \
  --base platform/.cache/firmware/community/1897200000000002571.bin \
  --out /tmp/m5stick-model-probe.bin
```

原始串口/命令 trace/GDDRAM/帧只保留在 `/tmp` 或 `.work`，不提交二进制。
