# Unit 第七批协议研究：12 款未登记 Unit 的驱动证据、复用建议与 unresolved

日期：`2026-11-02`。范围：`products.json` unit 类别中**尚未研究**的候选 Unit
里挑 12 款，记录官方页面、官方 UIFlow2 驱动逐行证据、QEMU 复用/新增建议、
可断言数据面与风险。本文件只做研究，不修改 catalog/runtime，不运行 QEMU；
catalog 草稿见 `2026-11-02-batch7-catalog-draft.json`，全部 `planned`。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 100 款（94 implemented + 6 planned）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..6-protocols.md`（72 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git HEAD `528edd8`，batch1-7 共用的冻结驱动树）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD `75f1d24`，
  canonical native layer）与已合入的 Unit 模型层 `patches/qemu-m5stack-peripherals/`
  （0120–0141）；本批未修改 QEMU。
- 官方页面在 `2026-11-02` 重新抓取核对（引用见 §8）。

## 0. 结论摘要

本批从剩余**未研究**的 Unit 中选 12 款，覆盖 **6 款 I2C、2 款 GPIO/RMT/PDM、
3 款 UART、1 款 CAN**：

| # | Unit id | SKU | 总线/地址 | 复杂度 | 推荐优先级 |
| --- | --- | --- | --- | --- | --- |
| 4.1 | `env-ii` | U001-B | I2C SHT30 `0x44` + BMP280 `0x76` | 低（复用 env BMP280） | **高** |
| 4.2 | `mini-bps-v11` | U090-B | I2C QMP6988（页面 `0x56` / 驱动 `0x70`，unresolved） | 低（复用 bps） | **高** |
| 4.3 | `mini-imu-pro` | U171 | I2C BMI270 `0x68` + BMM150 `0x10`（aux）+ BMP280 `0x76` | 中高（复合传感器） | 中 |
| 4.4 | `hbridge-v11` | U160-V11 | I2C STM32F030 `0x20` | 低（复用 hbridge + 新电流寄存器） | **高** |
| 4.5 | `cardkb-original` | U035 | I2C MEGA8A/MEGA328P `0x5F` | 低（复用 cardkb 模型） | **高** |
| 4.6 | `mini-tof-90` | U196 | I2C VL53L0X `0x29` | 低（复用 tof/tof4m） | **高** |
| 4.7 | `hex` | A045 | GPIO/RMT 37×SK6812（PORT.B 黄线数据） | 低（复用 neohex RMT） | 中 |
| 4.8 | `mini-pdm` | U089 | GPIO/PDM SPM1423（PORT.B 数据/时钟） | 中（无 Unit 驱动；复用 QEMU PDM RX） | 中 |
| 4.9 | `catm` | U128 | UART SIM7080G 115200（PORT.C） | 中（AT 应答器） | 中 |
| 4.10 | `catm-gnss` | U137 | UART SIM7080G+GNSS 115200（PORT.C） | 中高（AT+GNSS） | 中 |
| 4.11 | `lorawan-cn470` | U184-CN470 | UART STM32WLE5 LoRaWAN 115200（PORT.C） | 中高（AT/LoRaWAN） | 中 |
| 4.12 | `can` | U085 | CAN/TWAI（PORT.C 黄 TX / 白 RX） | 中高（C 模块 + TWAI） | 中 |

未研究集合推导：`products.json` 的 184 款 `category=unit` 产品中，99 款 id 与
`platform/units/catalog.json` 的 100 个 id 精确重合（`servo8-hat` 属 HAT 口径差，
catalog 收录但 products unit 列表无对应产品），因此未登记产品 = 184 − 99 = 85。
其中 batch6 已研究但尚未登记的 6 款（`dmx`/`finger`/`qrcode`/`thermal2`/
`unit-id`/`uwb`）不应重复；本批实际从**未研究的 79 款**中选 12 款。其余未选
产品按“passive/无数据面（`proto`/`grove-to-grove`/`m5-bit`/`rca` 等）、
摄像头/Linux 模块（`unitv*`/`timerCamera*`/`cams3*`）、纯显示（`oled`/`lcd`/
`mini-oled`/`unit-396`/`glass*`）、无官方 Unit 驱动（`mq`/`dcssr`/`mic`/
`audioplayer`/`asr` 等）”留待后续批次；本批不把它们写成 planned。

**最推荐的 5 款**（按“可复用框架 + 可断言数据面 + 冲突可控”排序）：

1. `mini-tof-90`（U196）— 与已实现 `tof`/`tof4m` 的 VL53L0X `0x29` 寄存器文件
   完全同族；90° 只是光学安装方向，协议零差异，证据成本最低。
2. `hbridge-v11`（U160-V11）— `hbridge` 模型（0x20）已存在，v1.1 只新增
   `0x30` float 电流寄存器；复用现有 I2C 控制框架即可断言 direction/PWM/电流。
3. `cardkb-original`（U035）— `cardkb` 控制模型已存在且同为 `0x5F` 单字节读；
   original 只是 MEGA8A/MEGA328P 版本差异，按键字节协议不变。
4. `env-ii`（U001-B）— SHT30 `0x44` + BMP280 `0x76`；BMP280 校准/补偿与
   `env`/`bps` 已有模型相同，只需加 SHT30 从地址与 ENV_II 分支。
5. `mini-bps-v11`（U090-B）— QMP6988 寄存器文件与 `bps`/`env-iii` 共享；但页面
   `0x56` 与驱动 `0x70` 的地址冲突必须先由证据钉死（见 4.2）。

主要 unresolved/冲突：

- `mini-bps-v11`：产品页与官方 I2C 索引写 **QMP6988 @0x56**，但冻结驱动
  `unit/bps.py:13`/`driver/qmp6988.py:11` 用 **0x70**，且官方索引中 ENV-III 的
  QMP6988 也是 0x70。0x56 是否只是页面笔误、或 QMP6988 支持双地址，需要实测
  扫描/读 chip-id 才能定；0x70 同时被 env-iii/pahub 占用。
- `mini-imu-pro`：三颗芯片复合（BMI270 0x68、BMM150 0x10 经 BMI270 aux、
  BMP280 0x76）；BMM150 不是独立 Grove 地址，必须走 BMI270 aux 事务；0x76
  与 env/bps/env-iv 系列冲突，0x68 与 mini-imu（U095）冲突（本批未选）。
- `hex`：public UIFlow2 **无 `unit/hex.py`**；只能走 generic
  `driver/neopixel/sk6812.SK6812`，且 SK6812 与 batch5 `neohex` 的 WS2812C
  不是同一 LED IC；37 灯数目相同但 byte order/时序容差不同。
- `mini-pdm`：public UIFlow2 **无 Unit 驱动**；PDM 麦克风由 `machine.I2S`
  或低层 PDM 读取，产品页只给 CLK/DAT 引脚。QEMU 已有 ESP32 SPM1423 PDM RX
  与 ESP32-S3 I2S RX front-end（AtomU/Atom Echo 先例），但“Unit 驱动/音量/声学”
  都没有可冻结的 guest API。
- `can`：`unit/can.py` 只是 `m5can` C 模块的薄封装；CAN 帧不经过 UART。QEMU
  cores3 已实例化 ESP32-S3 TWAI + `m5_can_bus_create()` CAN bus，但当前
  host-port/Unit attachment 框架是 I2C/GPIO/UART 视角，CAN 需要新的 attachment
  能力与帧注入接口，unresolved。
- `lorawan-cn470`：产品是 STM32WLE5（页面），驱动却是
  `driver/asr650x.LoRaWAN_470`（ASR6501 的 AT 集）；两者 AT 命令集是否兼容
  未验证。OTAA/ABP 密钥、Join/Accept、CN470 频段/占空比、RF 全部 NOT RUN。
- `catm`/`catm-gnss`：同一 SIM7080G，AT 响应/URC、GNSS 与蜂窝不能并发（页面
  FAQ）；Port.C 与其它 UART Unit 串行复用；GNSS COG 字段页面明确“不是行进方向”。
- `env-ii`/`mini-bps-v11`/`mini-imu-pro`/`mini-tof-90` 的 0x44/0x76/0x56/0x70/
  0x68/0x29 都与既有 Unit 有地址重叠，必须坚持“一总线一 Unit”或 PAHUB 隔离。

## 1. 方法与纪律

- 只信官方页面 + 冻结驱动源码；寄存器/地址必须有 `file:line` 出处；页面与
  驱动冲突时两边都记录并标 unresolved，不替产品做选择。
- 不运行 QEMU；QEMU 建议只描述控制器/模型复用位置，不代表已实现。
- 每款都给出 fixture/注入、可断言数据面、QEMU 复用/新增建议、风险与冲突。
- catalog 草稿只写 `planned`，不升级 runtime/profile，不产生 evidence。

## 2. 总线与控制器复用

| 总线 | 本批 Unit | QEMU 复用 | 新增 |
| --- | --- | --- | --- |
| I2C | env-ii、mini-bps-v11、mini-imu-pro、hbridge-v11、cardkb-original、mini-tof-90 | `m5_unit_i2c_sensors.c`/`m5_unit_i2c_controls.c` 的 I2C slave + 寄存器 pointer/快照框架；batch1-2 已实现 ENV/BPS/HBridge/CardKB/ToF 寄存器文件 | env-ii 的 SHT30 从地址、QMP6988 0x56 分支、IMU-Pro 复合 aux 事务、HBridge 0x30 float current |
| GPIO/RMT/PDM | hex、mini-pdm | 0139 `neohex` RMT capture；canonical `hw/m5stopwatch/m5_i2s.c` ESP32-S3 I2S RX + ESP32 PDM RX（AtomU/Echo SPM1423） | `hex` 的 37×SK6812 SKU 参数；mini-pdm 的 Unit 级 PDM fixture/attachment（当前只有板级麦克风路径） |
| UART | catm、catm-gnss、lorawan-cn470 | 0139 `lora-e220-433`/`nbiot2` 的 UART TX 捕获 + idle-gap fixture 注入 + `data-ready`/`responses-hex` | SIM7080 AT 命令表/URC、GNSS NMEA/CGNSINF 解析夹具、LoRaWAN AT 集 |
| CAN | can | canonical `hw/net/can/esp32s3_twai.c` + `hw/net/can/esp32_twai.c`；cores3 board 已 `m5_can_bus_create()` 并连接 TWAI → CANBusState | Unit attachment/CAN 帧 QOM fixture、host 注入与 TX 捕获 |

QEMU 控制器事实（canonical `75f1d24`）：

- `hw/net/can/esp32s3_twai.c` 实现 `esp32s3.twai`，复用 SJA1000 寄存器语义；
  `hw/xtensa/esp32s3.c:501-514` 已在 cores3 realize TWAI 并连接
  `m5_can_bus_create()` 创建的 `CanBusState`。`hw/net/can/esp32_twai.c` 同时
  提供 ESP32（非 S3）版本。
- `hw/m5stopwatch/m5_i2s.c` 提供 ESP32-S3 I2S RX DMA 和 `rx_pcm` 注入；
  `hw/m5stopwatch/m5_i2s_esp32.c`、`hw/xtensa/esp32.c`（AtomU K117 / Atom Echo
  C008-C）已包含 SPM1423 PDM 麦克风路径。Mini PDM 的 SPM1423 与其同型号，
  可复用 PCM 注入而不是新增音频模型。
- 已有 Unit 模型来自 `patches/qemu-m5stack-peripherals/0120-0141`；本批不修改。

## 3. 端口/地址冲突与优先级建议

- **PORT.C 串行复用**：catm、catm-gnss、lorawan-cn470、nbiot2、lora-e220-433、
  rs485-iso、midi 等共享 PORT.C 的 GPIO 17/18；一次只能挂一个 UART Unit。
- **PORT.B GPIO/RMT 复用**：hex、mini-pdm、neohex、rgb-led-10cm、op90、
  synth 等共享 PORT.B 的 GPIO 9/8；hex（数据线）与 mini-pdm（DATA/CLK 两线）
  互斥，RMT/PDM 也不能与 UART/GPIO 同时占用同一 pin。
- **I2C 地址**：
  - `0x29`：tof（U010，planned/unsupported）、tof4m（U172，implemented）、
    color、mini-tof-90 → 四方冲突。
  - `0x44`：env-ii SHT30、env-iii、env-iv、paper/hat SHT30 → 同总线一 Unit。
  - `0x5F`：cardkb（U035-B planned/unsupported）与 cardkb-original（U035）→
    同地址两版本，必须按 SKU 选一个。
  - `0x68`：mini-imu-pro BMI270、mini-imu（U095）、板级 BMI270（部分主机）。
  - `0x70`：env-iii QMP6988 与驱动默认 QMP6988、pahub-v20/pahub 系列。
  - `0x76`：env/bps/env-ii/env-iv BMP280 系。
  - `0x56`：官方索引的 mini-bps-v11 QMP6988；与驱动 `0x70` unresolved。
- 建议实现顺序：`mini-tof-90` → `hbridge-v11` → `cardkb-original` → `env-ii`
  → `mini-bps-v11`（先解决 0x56/0x70）→ `hex` → `catm` → `catm-gnss` →
  `lorawan-cn470` → `mini-imu-pro` → `mini-pdm` → `can`。

## 4. 逐款协议研究

### 4.1 `env-ii` — Unit ENV-II（U001-B）

- 官方页面：https://docs.m5stack.com/en/unit/envII（SKU U001-B，5V，PORT.A，
  黄=SDA 白=SCL）。SHT30 `0x44` + BMP280 `0x76`。
- 官方驱动：`unit/env.py:13-60`；`ENV_II=2` 分支 `:17-18` 用
  `SHT30(i2c)` + `BMP280(i2c)`。API：`read_temperature()` / `read_humidity()` /
  `read_pressure()`（`:60-72`）。
- SHT30：`driver/sht30.py:8` 地址 0x44；`:33` MEASURE 命令 `0x2C10`
  （高重复性，无时钟拉伸）；`:34` STATUS `0xF32D`；`:35` RESET `0x30A2`；
  `:37` heater `0x306D`/`:38` disable `0x3066`；测量响应 6B（T_MSB,T_LSB,T_CRC,
  H_MSB,H_LSB,H_CRC），CRC-8 poly 0x31。换算：T=-45+175*raw/65535，
  RH=100*raw/65535（`:124-160`）。
- BMP280：`driver/bmp280.py:29` 地址 0x76；`:31-32` CHIP_ID 0xD0=0x58；
  `:52` DATA 0xF7 6B；`:53` CALIBRATION 0x88 24B；`:38-44` CONTROL 0xF4；
  `:46-50` CONFIG 0xF5；`:58-60` 启动/采样 timing；`bmp280_refresh`/补偿在
  `driver/bmp280.py`（与 batch1-2 已实现 env/bps 共用）。
- Fixture/注入：`temperature-c`、`humidity-pct`、`pressure-pa`（session-initial
  unit-input）；输出 QOM 同名字段 + `transactions`。
- QEMU 复用：`0125-unit-batch2.patch` + `0126-unit-batch2b.patch` 的 BMP280
  寄存器文件/校准模型；`0130-unit-batch3ab.patch` 的 env 分支。新增 SHT30
  从地址（0x44）和 ENV_II 复合读取（每次 read 会触发 SHT30/BMP280 两组事务）。
- 可断言：guest 读回 fixture 的 T/RH/P 值（容差 ±0.01/±0.1）、BMP280 chip-id、
  SHT30 CRC 正确；I2C 事务 ≥3；QOM fixture 不回写 guest。
- 风险/冲突：0x44/0x76 与 env、env-iv、paper/hat SHT30、bps 冲突；SHT30
  heater/时钟拉伸未用；真实温湿度/气压物理 NOT RUN。
- 复杂度：低。推荐优先级：高。

### 4.2 `mini-bps-v11` — Unit Mini BPS v1.1（U090-B）

- 官方页面：https://docs.m5stack.com/en/unit/BPS(QMP6988)（U090-B，5V，
  PORT.A，黄=SDA 白=SCL）；页面写 **I2C @0x56**，传感器 QMP6988。
- 官方驱动：`unit/bps.py:12-13` `_BMP280_I2C_ADDR=0x76`、
  `_QMP6988_I2C_ADDR=0x70`；`:16-27` 扫描 `i2c.scan()[0]` 决定 BMP280 还是
  QMP6988；`:29-40` `get_temperature/pressure/altitude`。
- QMP6988：`driver/qmp6988.py:11` `I2C_DEFAULT_ADDR=0x70`；`:13-14` CHIP_ID
  0xD1=0x5C；`:16-17` RESET 0xE0=0xE6；`:19-20` IIR 0xF1；`:23-25` STATUS 0xF3；
  `:27-33` CONTROL 0xF4；`:35-37` IO_SETUP 0xF5；`:39-43` DATA 0xF7 6B、
  CALIBRATION 0xA0 25B。BMP280 走 `driver/bmp280.py`（见 4.1）。
- **unresolved 地址冲突**：产品页 + 官方 I2C 索引写 QMP6988 `0x56`；驱动默认
  `0x70`，且官方索引中 ENV-III 的 QMP6988 是 `0x70`。同一芯片两个地址可能来自
  QMP6988 的地址选择脚/页面笔误；实现前必须用 `i2c.scan()` + CHIP_ID 0x5C
  在 0x56/0x70 两个地址上验证，不能只信一边。
- Fixture/注入：`temperature-c`、`pressure-pa`；QOM 输出同名字段 + `transactions`。
- QEMU 复用：`0125-unit-batch2.patch` 的 `bps` 模型（BMP280/QMP 双分支）+
  `bmp280_refresh`；新增 QMP 0x56 地址分支/双地址探测。0x70 已有 pahub/env-iii
  占用，需一总线一 Unit 或 PAHUB。
- 可断言：guest 温度/气压/高度（高度按驱动 44330 公式反算）、QMP CHIP_ID、
  QOM fixture；0x56 vs 0x70 的扫描结果必须如实记录。
- 风险/冲突：0x56 与 0x70 二选一 unresolved；0x76 BMP280 变体与 env/bps 冲突；
  气压物理/高度基准 NOT RUN。
- 复杂度：低（若地址确认）；推荐优先级：高。

### 4.3 `mini-imu-pro` — Unit Mini IMU-Pro（U171）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Mini_IMU-Pro（U171，5V，
  PORT.A，黄=SDA 白=SCL）。BMI270 `0x68`（DIP 可改）、BMM150 `0x10`、
  BMP280 `0x76`；官方 I2C 索引把 BMM150 列在 `BMI270_SCL/SDA BUS 2`，
  即 BMM150 接在 BMI270 的 auxiliary bus 上，不是 Grove 直连。
- 官方驱动：`unit/imu_pro.py:16` BMI270_ADDR=0x68；`:25-56` `IMUProUnit` 继承
  `BMI270_BMM150, BMP280`，构造要求 0x68 在 scan；API `get_accelerometer()`
  `get_gyroscope()` `get_magnetometer()` `get_compass()` `get_attitude()`
  `get_temperature()` `get_pressure()`（`:76-141`）。
- BMI270/BMM150：`driver/bmi270_bmm150.py:15-16` PRIMARY 0x68/SECONDARY 0x69；
  `:19-44` DATA 0x0C、AUX_X 0x04、AUX_CONF 0x44、AUX_RD 0x4D、AUX_WR 0x4E、
  INIT_ADDR_0/1 0x5B/0x5C、CMD 0x7E；`:516-...` BMI270 类：`:557` init burst
  `CMD=0xB0`、`:577-579` soft reset 0xB6、`:582-607` ODR/range、
  `:602-608` aux sensor init（BMM150 0x10）。BMM150 数据经 aux 寄存器读取
  （`:798-818` magnet_raw/magnet）。
- Fixture/注入：`acceleration-x/y/z`、`gyroscope-x/y/z`、`magnetic-x/y/z`、
  `temperature-c`、`pressure-pa`；QOM 输出 `transactions`/`i2c-address`。
- QEMU 复用：cores3 板级已有 BMI270 0x69（内部总线）模型可参考寄存器 init
  blob；但 Unit 0x68 + aux BMM150 0x10 需要新的复合 I2C slave（主地址 0x68，
  aux 窗口 0x04/0x4D/0x4E），BMP280 复用 4.1 的模型。实现成本高于单芯片。
- 可断言：guest accel/gyro/mag 的 fixture 值与姿态角（math 在 guest 计算）、
  BMP280 温度/气压、QOM transactions；aux 事务计数。
- 风险/冲突：0x76 与 env/bps 冲突；0x68 与 mini-imu（U095）冲突；BMI270
  init blob 必须被 guest 接受；BMM150 aux 事务顺序/页面切换复杂；磁力/姿态
  物理与安装方向 NOT RUN。
- 复杂度：中高；推荐优先级：中。

### 4.4 `hbridge-v11` — Unit HBridge v1.1（U160-V11）

- 官方页面：https://docs.m5stack.com/en/unit/HBridge%20v1.1%20Unit
  （U160-V11，5V，PORT.A，黄=SDA 白=SCL）；STM32F030F4P6，RZ7899，
  INA199 电流采集；I2C `0x20`（0x20–0x2F 可改）。
- 官方驱动：`unit/hbridge.py:10` HBRIDGE_ADDR=0x20；`:13-19` 寄存器：
  DIRECTION 0x00、PWM8 0x01、PWM16 0x02（LE 2B）、PWMFREQ 0x04（LE 2B）、
  ADC8 0x10、ADC16 0x20（LE 2B）、VIN_CURRENT 0x30（float32 LE）、
  I2C_ADDR 0xFF、FW_VER 0xFE。API：`set_direction(0/1/2)`、
  `set_8bit_pwm`、`set_16bit_pwm`、`set_percentage_pwm`、`set_pwm_freq`、
  `get_adc_value(raw/res)`、`get_vin_current()`（v1.1 新增，`:120-127`）、
  `get_device_status(0xFE/0xFF)`。
- 与已实现 `hbridge`（U160）的关系：v1.1 增加电流检测与保护，寄存器文件
  向后兼容；`0x30` float 电流是唯一新数据面。
- Fixture/注入：`adc-mv`、`vin-current-a`；QOM 输出 `direction`、
  `pwm-duty-pct`、`pwm-frequency-hz`、`transactions`。
- QEMU 复用：`0123-unit-i2c-batch3.patch`/`0125-unit-batch2.patch` 的 hbridge
  模型（direction/PWM/freq/ADC/status 已实现）；新增 0x30 float LE 快照与
  `get_vin_current` 断言。0x20 已被 hbridge U160 占用，一总线一 Unit。
- 可断言：guest 写 direction/PWM/freq 后 QOM 回读一致；guest 读 ADC/电流
  fixture；16-bit LE 顺序；0xFE/0xFF 读回。
- 风险/冲突：0x20 与 hbridge U160 同地址；电机驱动/RZ7899/INA199/过流保护/
  真实负载电流 NOT RUN；float 字节序需证据。
- 复杂度：低；推荐优先级：高。

### 4.5 `cardkb-original` — Unit CardKB (original MEGA328P U035)（U035）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_CardKB（U035，5V，PORT.A，
  黄=SDA 白=SCL，I2C `0x5F`，50 键 + 1 RGB LED）。页面 Protocol 表：
  地址 0x5F，读 1 字节 `keyboard_value_reg[0]`。
- 官方索引/版本：官方 I2C 索引把 Unit CardKB U035 标为 **MEGA8A @0x5F**；
  catalog 已登记 `cardkb` 是 U035-B（v1.1）且 runtime `unsupported`。本款是
  **U035 original（MEGA328P，页面产品名）**，同地址不同 MCU 版本。
- 官方驱动：`unit/cardkb.py:24-76` `CardKBUnit` 地址 0x5F；`get_key()` 读 1B、
  非 0 压队；`get_string`/`is_pressed`/`set_callback`/`tick`；`KeyCode`
  常量（`:9-22`）含 0x00 unknown、0x08 BS、0x09 TAB、0x0D ENTER、0x1B ESC、
  0x20 SPACE、0x7F DEL、方向键 180–183）。
- Fixture/注入：`key-events`（按序注入的键值数组，含 0 表示无键）；QOM 输出
  `last-key`、`key-events`、`transactions`。
- QEMU 复用：`0035-unit-i2c-controls.patch:688/714` 已有 cardkb 控制模型
  （`CONTROL_CARDKB`，单字节读）；original 版本可直接复用，仅需按 SKU 记录
  MEGA8A/MEGA328P 差异。原始版本 KeyCode 是否与 v1.1 完全一致需证据。
- 可断言：guest `get_key()` 序列等于注入序列；组合键（Shift/Sym/Fn）由
  guest 驱动/固件处理，QEMU 只注入最终键值；QOM key-events 计数。
- 风险/冲突：0x5F 与已登记 `cardkb`（U035-B）同地址；original 与 v1.1 的
  MCU/键值差异 unresolved；键盘矩阵/RGB LED/机械手感 NOT RUN。
- 复杂度：低；推荐优先级：高。

### 4.6 `mini-tof-90` — Unit Mini ToF-90°（U196）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Mini_ToF-90（U196，5V，
  PORT.A，黄=SDA 白=SCL）；VL53L0X，I2C `0x29`，3–200 cm，25° FoV，
  940nm VCSEL，测量 8–23ms；页面明确 90° 只是激光模块安装方向。
- 官方驱动：`unit/tof.py:5` 直接 `from driver.vl53l0x import VL53L0X as ToFUnit`；
  VL53L0X 构造 `/driver/vl53l0x.py:112-123`（地址 41=0x29）；
  `get_range()` `:503`、`get_data_ready()` `:514`、`read_range()` `:541`、
  `start_continuous()` `:582`、`stop_continuous()` `:602`。
- 寄存器（`driver/vl53l0x.py:19-40`）：SYSRANGE_START 0x00、SYSTEM_SEQUENCE_CONFIG
  0x01、SYSTEM_INTERRUPT_CLEAR 0x0B、RESULT_INTERRUPT_STATUS 0x13、
  RESULT_RANGE_STATUS 0x14、I2C_SLAVE_DEVICE_ADDRESS 0x8A、MSRC_CONFIG 0x60 等；
  `range` 值 = RESULT_RANGE_STATUS 后 16-bit / 4? 以驱动为准。
- Fixture/注入：`distance-mm`、`data-ready`；QOM 输出 `timing-budget-ms`、
  `range-status`、`i2c-address`、`clear-writes`、`transactions`（与 tof4m 契约一致）。
- QEMU 复用：`0125-unit-batch2.patch` 的 `US_TOF`（tof U010）与
  `0134/0136` 的 tof4m（VL53L1X，0x29）寄存器文件；Mini ToF-90 是 VL53L0X，
  直接复用 `US_TOF`，只需按 SKU 配 90° 说明/量程，无需新寄存器。
- 可断言：guest `get_range()`/`get_data_ready()` 读回 fixture；QOM 清中断写、
  range status、timing budget；90° 安装不影响协议。
- 风险/冲突：0x29 与 tof（U010，planned/unsupported）、tof4m（U172，
  implemented）、color（U009，0x29）四方冲突；激光光学/测距精度/940nm NOT RUN；
  VL53L0X 初始化 blob 与 tof4m 的 VL53L1X 不可混用。
- 复杂度：低；推荐优先级：高。

### 4.7 `hex` — Unit HEX（A045）

- 官方页面：https://docs.m5stack.com/en/unit/hex（A045，5V，PORT.B，
  黄=LED Signal，白=NC）；37 颗 SK6812 RGB LED，串联输出可级联，16.7M 色。
- 官方驱动：**public UIFlow2 无 `unit/hex.py`**（`m5stack/libs/unit/` 下无 hex）；
  可执行参考只有 generic `driver/neopixel/sk6812.py:10` `SK6812`（继承
  `driver/neopixel/__init__.py` NeoPixel），`set_screen`/`fill_color`/`write`，
  ORDER 为 GRB（`:12`），默认 bpp=3；`unit/rgb.py` 只服务 RGBUnit 的 SKU。
- Fixture/注入：无 host 注入（RMT 是输出）；QOM 输出 `led-rgb`（37×u24）、
  `led-frames`、`incomplete-frames`、`output-transitions`（同 neohex 契约）。
- QEMU 复用：`0139-unit-batch5b.patch` 的 `neohex` GPIO/RMT capture（37 灯、
  黄线数据、led-rgb/led-frames）；新增 Unit id `hex` 与 SKU 参数，区分
  SK6812 vs WS2812C 的 bit timing/byte order。PORT.B 黄线 GPIO 9（cores3）。
- 可断言：guest `SK6812.fill_color(0x112233)`/`set_screen` 后 QOM 37 灯全同色、
  帧数≥1、incomplete=0；级联输出/输入端口可记录但不转发。
- 风险/冲突：**unit 驱动 gap**；SK6812 37 灯与 `neohex` A045-B 的 WS2812C
  37 灯外形/协议相近但 IC 不同；PORT.B 与 neohex/rgb-led-10cm/op90 等冲突；
  LED 光学/功耗/级联时序 NOT RUN。
- 复杂度：低；推荐优先级：中。

### 4.8 `mini-pdm` — Unit Mini PDM（U089）

- 官方页面：https://docs.m5stack.com/en/unit/pdm（U089，5V，PORT.B，
  黄=Data、白=Clock）；SPM1423 PDM MEMS 麦克风，-22dBFS@94dB SPL，
  SNR 61.4dB，THD 1%，600µA。
- 官方驱动：**public UIFlow2 无 Unit PDM 驱动/API**；只有产品页与
  `machine.I2S`/PDM 低层路径（MicroPython ESP32 端口支持 PDM RX）。页面
  没有寄存器表（PDM 是数字音频流，不是 I2C/UART）。
- Fixture/注入：`pcm-frame`（PCM 采样 hex fixture，例如 16-bit mono 1kHz
  正弦）；QOM 输出 `pcm-frame`、`sample-rate`、`frames`、`clock-hz`。
- QEMU 复用：canonical 已实现 **ESP32-S3 I2S RX DMA front-end**
  （`hw/m5stopwatch/m5_i2s.c`：`rx_pcm`/`rx_dma`/`i2s_rx_timer` 注入）与
  **ESP32 SPM1423 PDM RX 板级路径**（`hw/m5stopwatch/m5_i2s_esp32.c`、
  `hw/xtensa/esp32.c` AtomU K117 / Atom Echo C008-C）。Mini PDM 与 AtomU/Echo
  同型号 SPM1423，可复用 PCM 注入；需要新增 Unit attachment + I2S/PDM
  pinmux（PORT.B DATA/CLK）配置，而不是新音频模型。
- 可断言：guest 用 I2S PDM RX 读回 fixture PCM（按 sample rate/帧数）、
  QOM pcm-frame 一致；音频编解码/声学灵敏度/SNR 不做物理断言。
- 风险/冲突：无 official Unit 驱动，guest API 只能走 `machine.I2S`，与
  “Unit 驱动”证据口径不同；PORT.B 两线占用与 hex/RMT/UART 冲突；
  声学/音频 NOT RUN；PDM clock pinmux 未验证。
- 复杂度：中；推荐优先级：中。

### 4.9 `catm` — Unit CatM（U128）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_CatM（U128，5V，PORT.C，
  UART 115200 8N1）；SIM7080G，Cat-M/NB-IoT 双模，SMA 天线，
  AT 控制，支持 TCP/UDP/HTTP/HTTPS/TLS/DTLS/MQTT/CoAP/LWM2M 等。
- 官方驱动：`unit/catm.py:17-26` `CATMUnit(SIM7080)`：UART 115200，
  `check_modem_is_ready()`（`driver/simcom/common.py:58-62`，`AT`→`OK`，
  repeat 重试），`set_command_echo_mode(0)`（`:64-68`，`ATE0`）。
  SIM7080 驱动 `driver/simcom/sim7080.py:12-16` 继承 Modem；
  `:26-31` `AT+CMNB?`（`+CMNB:`）；`:32-36` `AT+GSN`；`:38-42` `AT+CCID`；
  `:44-48` `AT+CMNB=`；`:50-67` `AT+CNACT?`/`AT+CNACT=`；`:69+`
  `AT+SMCONF=...`/`AT+SMCONN` 等 MQTT。
- Fixture/注入：`responses-hex`（`;` 分隔的 AT 响应 chunk，由 UART idle-gap
  注入，复刻 batch5 nbiot2/lora 的 responder）；QOM 输出 `tx-hex`、
  `responses-hex`、`frames-sent`、`frames-injected`。
- QEMU 复用：`0139-unit-batch5b.patch` 的 UART TX 捕获 + idle fixture 注入
  （`at_timer`/`at_idle_cb`）直接复用；新增 SIM7080 AT 响应夹具与
  `AT+CMNB?`/`AT+CNACT?` 等命令断言。PORT.C 黄=RX 白=TX（cores3 GPIO 17/18）。
- 可断言：guest 构造成功（AT/ATE0）、`get_mode_selection`/`get_imei_number`/
  `get_network_ip` 等返回 fixture 值；QOM tx-hex 含 `41540d0a`、`415445300d0a`、
  `AT+CMNB?` 等；只做字节/AT 解析断言。
- 风险/冲突：SIM7080 AT 固件版本/URC 时序未钉；Cat-M/NB-IoT RF、SIM、
  运营商认证、TCP/TLS/MQTT 网络全部 NOT RUN；PORT.C 与其它 UART Unit 互斥；
  页面 FAQ：SIM7080 不能同时蜂窝 + GNSS。
- 复杂度：中；推荐优先级：中。

### 4.10 `catm-gnss` — Unit CatM GNSS（U137）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_CatM_GNSS（U137，5V/9-24V，
  PORT.C，UART 115200 8N1）；SIM7080G，Cat-M/NB-IoT + GPS/GLONASS/BeiDou/
  Galileo，双 SMA 天线。
- 官方驱动：`unit/catm_gnss.py:17-26` `CATMGNSSUnit(SIM7080)`，与 catm 相同
  构造（AT 就绪 + ATE0）。GNSS API 在 `driver/simcom/sim7080.py`：
  `:312-350` `AT+CGNSPWR?`/`AT+CGNSPWR=`；`:352-395` `gnss_nmea_output_polling`
  `AT+CGNSINF`（`+CGNSINF:` 行，NMEA 输出轮询）；`:396-427`
  `get_gnss_position(unit, format)`；`:428+` `AT+CGNSCOLD/WARM/HOT` 启动。
- Fixture/注入：`responses-hex`（AT/GNSS 响应 chunk：`OK`、`+CGNSPWR: 1`、
  `+CGNSINF: ...` 等）；QOM 输出 `tx-hex`、`responses-hex`、
  `latitude`/`longitude`/`altitude`/`speed`/`course`/`fix-mode`、
  `frames-sent`/`frames-injected`。
- QEMU 复用：与 catm 共用 UART responder；新增 GNSS 行解析夹具；
  不新增 RF 模型，GNSS 定位为 fixture 数值。
- 可断言：guest `get_check_gnss_power()`、`get_gnss_position()` 返回 fixture；
  `AT+CGNSINF` tx 字节；fix/经纬度/海拔/速度解析一致。
- 风险/冲突：GNSS 天线/RF/卫星几何/定位精度 NOT RUN；页面 FAQ 明确
  `AT+CGNSINF` 的 COG 字段不是行进方向；蜂窝 + GNSS 不能并发；
  PORT.C 与 catm/其它 UART 冲突。
- 复杂度：中高；推荐优先级：中。

### 4.11 `lorawan-cn470` — Unit LoRaWAN-CN470（U184-CN470）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_LoRaWAN-CN470（U184-CN470，
  5V，PORT.C，UART 115200，AT）；STM32WLE5 + LoRaWAN 1.0.3 CN470
  （470–510MHz），Class A/B/C，OTAA/ABP，支持 P2P；灵敏度 -137dBm。
- 官方驱动：`unit/lorawan.py:13-22` `LoRaWANUnit(LoRaWAN_470)`，
  `super(LoRaWAN_470, self).__init__(tx=port[1], rx=port[0])`；实际实现是
  `driver/asr650x.py:14` `LoRaWAN_Asr650x` / `:744` `LoRaWAN_470`（ASR6501 平台）。
  典型 AT：`AT+CGSN?`、`AT+CDEVADDR?/=`、`AT+CDEVEUI?/=`、`AT+CAPPEUI?/=`、
  `AT+CAPPKEY?/=`、`AT+CAPPSKEY?/=`、`AT+CNWKSKEY?/=`、`AT+CJOINMODE?/=`、
  `AT+CFREQBANDMASK?/=`、`AT+CULDLMODE?/=`、`AT+CWORKMODE?/=`、
  `AT+CCLASS?/=` 及 join/send（行号见 `driver/asr650x.py` 各方法）。
- **unresolved 驱动/产品错配**：产品是 STM32WLE5，驱动类叫 ASR650x；
  两者 AT 命令是否完全兼容未验证（可能为兼容 AT 集，也可能固件返回不同
  格式）。必须用证据确认 `AT+CGSN?`/`AT+CDEVADDR?` 等响应，不能假定。
- Fixture/注入：`responses-hex`（AT 响应 chunk）；QOM 输出 `tx-hex`、
  `join-status`、`frames-sent`、`frames-injected`、`dev-addr`/`dev-eui`/
  `app-eui`（从 fixture 解析）。
- QEMU 复用：UART responder（同 catm）；新增 LoRaWAN AT 命令表/响应夹具；
  不新增 LoRa RF/协议栈模型。
- 可断言：guest 设置/读取 DevAddr/DevEUI/AppEUI/AppKey 等后 QOM tx-hex 字节；
  join 请求/响应状态；AT 解析值；只做字节/AT 层。
- 风险/冲突：驱动/产品错配 unresolved；OTAA/ABP 密钥、Join/Accept、
  CN470 频段/占空比、RF/天线/距离全部 NOT RUN；PORT.C 与 catm 等冲突；
  LoRaWAN 认证/安全不建模。
- 复杂度：中高；推荐优先级：中。

### 4.12 `can` — Unit CAN（U085）

- 官方页面：https://docs.m5stack.com/en/unit/can（U085，5V，PORT.C，
  黄=CAN_TX 白=CAN_RX）；隔离 CAN 收发器 CA-IS3050G（1000V 隔离），
  ISO11898-2，最高 1Mbps，110 节点，120Ω 终端。
- 官方驱动：`unit/can.py:8-34` `CANUnit(CAN)`，`from m5can import CAN`；
  `:10-25` timing_table：25k/50k/100k/125k/250k/500k/800k/1M →
  (prescaler,sjw,bs1,bs2,triple_sampling)；构造
  `super().__init__(0, mode, port[1], port[0], ...)`；
  `MiniCANUnit = CANUnit`。
- C 模块：`m5stack/cmodules/m5can/modcan.c`：`init(mode, prescaler, *, sjw,
  bs1, bs2, triple_sampling)`（`:109-215`）、`send(id, data, *, extframe, rtr)`
  `:313`、`recv`/`any`/`state`/`info`/`setfilter`/`clearfilter`
  （`:436-470`）、CAN_NORMAL/NO_ACKNOWLEDGE/LISTEN_ONLY（`:476-490`）；
  SJA1000/TWAI 语义。
- Fixture/注入：`rx-frames`（CAN 帧 fixture：标准/扩展 id + data hex；
  由 host 注入 CAN bus）；QOM 输出 `tx-frames`、`rx-frames`、`frames-sent`、
  `frames-received`、`can-state`。
- QEMU 复用：canonical `hw/net/can/esp32s3_twai.c`（`esp32s3.twai`，SJA1000
  寄存器）+ `hw/net/can/esp32_twai.c`；cores3 board
  `hw/xtensa/esp32s3.c:501-514` 已 realize TWAI 并连接 `m5_can_bus_create()`
  的 `CanBusState`。建议：给 Unit attachment 暴露 CAN bus 句柄，host 通过
  QMP/service 注入 `CanBusState` 帧并捕获 guest TX；不需要新控制器。
- 可断言：guest `CANUnit.send(0x123, b"...")` → QOM `tx-frames`/host CAN bus
  收到相同 id/data；host 注入帧 → guest `recv()` 返回相同帧；波特率 timing
  表映射到 TWAI BTR；标准/扩展 id、RTR、过滤器。
- 风险/冲突：`m5can` 是 C 模块，无 Python 驱动协议；CAN 帧不经过 UART，
  PORT.C 的 UART host-port 语义不适用，需要新的 CAN attachment/权限模型
  unresolved；隔离/终端/差分电平/总线仲裁/错误帧/真实 CAN 负载 NOT RUN；
  与 UART Unit 共享 PORT.C 引脚，互斥。
- 复杂度：中高；推荐优先级：中。

## 5. catalog 草稿

`2026-11-02-batch7-catalog-draft.json` 含 12 条 `planned` 草稿，字段与
batch1-6 一致：`id/name/sku/visual_asset/official_docs/checked_at/chips/
interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/
blocker/limitations`。`runtime.status` 全部 `planned`，`model_status` 全部
`planned`；不写 evidence/PASS，不升级 profile。

草稿要点：

- 每个 I2C 条目 `interface.address_7bit` 记录 7-bit 地址数组；地址冲突写在
  `blocker`/`limitations`，不替产品选地址（尤其 `mini-bps-v11`）。
- `hex` 明确 `unit-driver-gap`（无 `unit/hex.py`，generic SK6812 路径）。
- `mini-pdm` 明确 `no-official-unit-driver`，数据面依赖 `machine.I2S` PDM RX。
- `can` 的 `interface.bus` 用 `gpio`/`can` 语义（引脚 TX/RX），不伪装成 UART；
  runtime properties 用 CAN 帧数组/计数。
- 所有 RF/光学/声学/热/电气/机械语义写 `NOT RUN`，不写 simulated。

## 6. unresolved 汇总

| Unit | unresolved | 影响 |
| --- | --- | --- |
| `mini-bps-v11` | QMP6988 地址页面/索引 `0x56` vs 驱动 `0x70` | 无法确定 slave 地址；需 scan + CHIP_ID |
| `mini-imu-pro` | BMI270 init blob/BMM150 aux 事务；0x76/0x68 冲突 | 复合传感器实现成本高 |
| `hex` | public 源无 unit 驱动；SK6812 vs WS2812C 时序 | 只能 generic 路径，guest API 证据口径需说明 |
| `mini-pdm` | public 源无 Unit 驱动；PDM pinmux/clock | guest API 不存在，需 I2S 直读 |
| `can` | C 模块 + 新 attachment/CAN 帧接口；PORT.C 复用 | 需 host-port 能力扩展，不能走 UART responder |
| `lorawan-cn470` | STM32WLE5 产品 vs ASR650x 驱动 AT 集 | 响应格式/命令兼容性未验证 |
| `catm`/`catm-gnss` | SIM7080 AT 固件/URC；蜂窝+GNSS 互斥 | 只能字节/AT 夹具，网络 NOT RUN |
| 多个 I2C | 0x29/0x44/0x5F/0x68/0x70/0x76 地址重叠 | 必须一总线一 Unit 或 PAHUB |

## 7. 引用与复现

- 官方产品页（均于 2026-11-02 抓取）：
  `envII`、`BPS(QMP6988)`、`Unit_Mini_IMU-Pro`、`HBridge v1.1 Unit`、
  `Unit_CardKB`、`Unit_Mini_ToF-90`、`hex`、`pdm`、`Unit_CatM`、
  `Unit_CatM_GNSS`、`Unit_LoRaWAN-CN470`、`can`；
  官方 I2C 地址索引 `product_i2c_addr`。
- 驱动源码（冻结树 HEAD `528edd8`）：`unit/env.py`、`unit/bps.py`、
  `unit/imu_pro.py`、`unit/hbridge.py`、`unit/cardkb.py`、`unit/tof.py`、
  `unit/catm.py`、`unit/catm_gnss.py`、`unit/lorawan.py`、`unit/can.py`；
  `driver/sht30.py`、`driver/bmp280.py`、`driver/qmp6988.py`、
  `driver/bmi270_bmm150.py`、`driver/vl53l0x.py`、`driver/neopixel/*`、
  `driver/simcom/sim7080.py`、`driver/simcom/common.py`、`driver/asr650x.py`、
  `cmodules/m5can/modcan.c`。
- QEMU 只读坐标：`hw/net/can/esp32s3_twai.c`、`hw/net/can/esp32_twai.c`、
  `hw/xtensa/esp32s3.c:501-514`、`hw/m5stopwatch/m5_i2s.c`、
  `hw/m5stopwatch/m5_i2s_esp32.c`；Unit 模型层参考
  `patches/qemu-m5stack-peripherals/0123/0125/0126/0130/0134/0136/0139-0141`。
- 未运行 QEMU、未改 catalog/runtime/测试；raw 证据不涉及。

## 8. 抓取记录

| 页面 | URL | 用途 |
| --- | --- | --- |
| ENV-II | https://docs.m5stack.com/en/unit/envII | SHT30 0x44/BMP280 0x76 |
| Mini BPS v1.1 | https://docs.m5stack.com/en/unit/BPS(QMP6988) | QMP6988、页面 0x56 |
| Mini IMU-Pro | https://docs.m5stack.com/en/unit/Unit_Mini_IMU-Pro | BMI270/BMM150/BMP280 |
| HBridge v1.1 | https://docs.m5stack.com/en/unit/HBridge%20v1.1%20Unit | 0x20、电流检测 |
| CardKB | https://docs.m5stack.com/en/unit/Unit_CardKB | 0x5F、单字节读 |
| Mini ToF-90 | https://docs.m5stack.com/en/unit/Unit_Mini_ToF-90 | VL53L0X 0x29 |
| HEX | https://docs.m5stack.com/en/unit/hex | 37×SK6812、PORT.B |
| Mini PDM | https://docs.m5stack.com/en/unit/pdm | SPM1423 CLK/DAT |
| CatM | https://docs.m5stack.com/en/unit/Unit_CatM | SIM7080G 115200 |
| CatM GNSS | https://docs.m5stack.com/en/unit/Unit_CatM_GNSS | GNSS AT/COG 说明 |
| LoRaWAN-CN470 | https://docs.m5stack.com/en/unit/Unit_LoRaWAN-CN470 | STM32WLE5、LoRaWAN |
| CAN | https://docs.m5stack.com/en/unit/can | CA-IS3050G、1Mbps |
| I2C index | https://docs.m5stack.com/en/product_i2c_addr | 各芯片 7-bit 地址 |

以上为研究结论，不构成实现/证据承诺；下一批实现前需重新核对驱动树 HEAD
与产品页地址，特别是 `mini-bps-v11` 的 0x56/0x70 与 `lorawan-cn470` 的
驱动/产品错配。
