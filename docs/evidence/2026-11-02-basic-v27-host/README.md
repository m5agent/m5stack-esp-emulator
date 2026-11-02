# Basic v2.7（K001-V27）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 Basic v2.7 接入为独立
classic ESP32 原生 QEMU 主机（machine `m5basic`）。本记录只声明虚拟设备
结果：官方固件启动、板级识别、320×240 面板初始化、A/B/C 按键注入、
IP5306 I2C 寄存器数据面、电池 QOM fixture 与 I2S0 DAC 数字 PCM。
物理电气/声学 `NOT RUN`。

## 结果

- 新增机器 `m5basic`（补丁 `0113-basic-v27-board.patch`）：ESP32-D0WDQ6-V3、
  ILI9342C 320×240（VSPI/SPI3，CS G14、DC G27）、A/B/C 按键
  GPIO39/38/37、Grove A 与 IP5306 `0x75` 共用 G21(SDA)/G22(SCL)、
  Speaker 走 I2S0 DAC（GPIO25）、无 PSRAM。microSD 只登记接线，未建模。
- 新增 `m5.ip5306` I2C 从设备模型：按 IP5306 寄存器手册实现复位值、
  reserved bit 写掩码、Charger_CTL0/1/2/3 与 CHG_DIG_CTL0、READ0/READ1、
  READ3 写 1 清零键标志与 READ4 电量桶；无电芯、无充电/升压电源路径、
  无电压电流测量，默认 READ4=`0xff`（显式“无有效读数”），不伪造电量。
- 官方 UIFlow2 `v2.5.4`（`1897200000000000786`，镜像 SHA-256
  `613a802da0f496d339a4120c0322c0c7ec1db3d81474b4329077f8b233d4dccb`，
  分区表 `vfs` = `0x38A000/0x75000`）在同一 guest 内输出：

  ```
  BASIC27_BOOT_FLAG / BASIC27_MAIN_START / BASIC27_M5_BEGIN_OK
  BASIC27_BOARD 1
  BASIC27_DISPLAY 320 240
  BASIC27_DRAW_OK
  BASIC27_BUTTONS 0 0 0
  BASIC27_I2C_SCAN ['0x48', '0x75']
  BASIC27_IP5306_SYS 0xb9
  BASIC27_IP5306_CHG_V 0x2
  BASIC27_IP5306_CHG_I 0x1
  BASIC27_IP5306_READ0 0x8
  BASIC27_IP5306_READ1 0x0
  BASIC27_IP5306_READ4 0xff
  BASIC27_IP5306_BATTERY none
  BASIC27_IP5306_BOOST_OFF 0
  BASIC27_IP5306_BOOST_ON 1
  BASIC27_IP5306_CHG_V_REQ 0x9
  BASIC27_SPEAKER_RUNNING 1
  BASIC27_SPEAKER_STATUS ok
  BASIC27_PROBE_READY
  BASIC27_BUTTON_STATE 1 0 0 / 0 0 0 / 0 1 0 / 0 0 0 / 0 0 1 / 0 0 0
  ```

- 设备矩阵 case `basic-v27`（console 模式）三次独立运行 `PASS`；除串口标记外，
  运行时校验 I2S0 DMA 捕获 PCM `250,368` bytes、`31,913` 非零采样、
  peak-to-peak `23,270`。串口日志中仅 ESP-IDF `i2c.master` 启动日志的虚
  拟时间戳会轻微变化，`BASIC27_*` 标记稳定。`BASIC27_BUTTON_STATE` 由 QMP 键盘事件经
  panel input handler 驱动真实 GPIO 输入寄存器，guest 侧再回读；不是
  host 侧直接写值。
- 帧证据：同一镜像的 UI 模式运行保存 320×240 帧，`449` nonblack 像素、
  `15` 色（AFTER PNG SHA-256 `d1b9d015…`），说明固件确实经 SPI 面板
  数据面写出画面；本记录不把帧内容当作视觉验收。
- IP5306 电量 fixture（QOM 注入数据面）：`--qom-set-boot
  /machine/ip5306 battery-mv 3900` 后 guest 读到 `READ4 0x80`、
  `BASIC27_IP5306_BATTERY cell`、`BASIC27_BATTERY_LEVEL 75`，QOM
  `battery-code=8`；默认无电芯时 QOM `battery-mv=4294967295`、
  `battery-code=255`。默认路径不读取/不输出任何百分比。
- 开关机请求：guest 清除 SYS_CTL0 的 boost enable bit（0x20）再恢复，
  QOM `power-off-requests=1`、`boost-enabled=True`；模型只记录请求，
  不改变 QEMU 电源状态。
- 充电请求：M5.begin() 写 `0x22=0x02`（4.2V+28mV）；probe 通过
  `M5.Power.setChargeVoltage(4350)` 请求 `0x22=0x09`，QOM
  `charge-voltage-mv=4364`；`0x24` 低 5 位=1 → `charge-current-ma=150`。

## 边界

- IP5306 只覆盖 I2C 寄存器契约；没有电芯、充电/升压功率路径、电压电流
  遥测或 KEY 电源键模型。`0x78` 默认 `0xff` 是模型边界，不是真实电量。
- microSD、面板背光 PWM（G32）、LCD reset（G33）、红色电源键（IP5306 KEY）、
  Grove Unit 协议与 USB-C/CDC 未验证；I2S0 DAC 的模拟输出、功放、声学
  未验证。
- guest I2C 扫描中 `0x48` 是 QEMU classic machine 自带的 `tmp105` 便利设备，
  不是 Basic 板载器件；Basic 板级器件只有 `0x75` IP5306。
- 官方合并镜像为 4 MB 变体；设备硬件为 16 MB Flash。QEMU 使用 4 MB
  合并镜像驱动 `gd25q32` 模型，未验证 16 MB 全片或额外 Flash 空间。
- 本结果不转授 Core2（AXP/触摸/PSRAM）、Atom 系列或任意其它经典主机；
  真机、电气、声学、光学与机械均 `NOT RUN`。

## 复现

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000000786 --chip-id 0x0000
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device basic-v27 --flash-transport direct --out-dir /tmp/basic27-matrix
# 电池 fixture 与 QOM/帧证据（非矩阵门禁）：
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/basic-v27/uiflow2.bin --machine m5basic \
  --files-dir tests/uiflow2/basic_v27_console_test \
  --vfs-offset 0x38a000 --vfs-size 0x75000 --flash-size 0x400000 \
  --expected-size 320x240 --efuse-driver none --allow-static-frame --wait 25 \
  --qom-set-boot /machine/ip5306 battery-mv 3900 \
  --serial-expect "BASIC27_BATTERY_LEVEL 75" \
  --qom-expect /machine/ip5306 battery-code 8 \
  --out-dir /tmp/basic27-battery-fixture
```

## 未覆盖

- IP5306 电芯/充放电/升压/电压电流、QOM 以外的人工注入路径；
- microSD、电源键、背光 PWM、Grove Unit、USB-C/CDC；
- 原厂 UIFlow2 启动菜单/网络、任意第三方固件；
- 真机电气/声学/光学/机械与长期稳定性。
