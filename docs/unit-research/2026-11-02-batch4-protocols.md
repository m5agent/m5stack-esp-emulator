# Unit 第四批（12 款）官方协议研究报告

日期：`2026-11-02`。归属团队任务 `task-28`，工作树
`esp-emulator-unit4`，分支 `m5agent/unit-research-batch4`（基于
`origin/main` `ab4c6bff`，Unit 已登记 70 款）。

本页是**实现前**的协议研究，不是运行时或硬件 PASS。本报告没有运行 QEMU、固件或
Device Service，没有修改 `platform/units/catalog.json`、runtime profile、QEMU
源码或测试；配套的 catalog 草稿单独放在
[`2026-11-02-batch4-catalog-draft.json`](2026-11-02-batch4-catalog-draft.json)。

## 0. 结论摘要

从未登记的 Unit 中选 12 款。筛选口径：官方 UIFlow2 源码里有**可执行驱动**，协议
能落到已实现框架（GPIO/ADC/RMT 端点、I2C controls/sensors、UART 端点、0126
双从机 attach）之一，或能用同一寄存器机框架低成本扩展；排除需要新控制器拓扑
（CAN/USB/摄像头/DMX 原生 C 驱动/synth I2S/复合视频 DAC/蜂窝/LoRa）或纯显示器
件（M5.addDisplay 原生显示管线）。

| # | Unit id | SKU | 名称 | 总线 / 地址 | 复杂度 | 建议归属 QEMU 分支 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `co2l` | U104 | Unit CO2L | `i2c` / `0x62`（SCD41） | B 中低 | `m5_unit_i2c_sensors.c`（复用 0131 `US_SCD40`，改量程/单次测量） |
| 2 | `rs485-iso` | U094 | Unit RS485-ISO | `uart-rs485` / — | A 低 | `m5_unit_gpio.c`（复用已登记 `rs485` 的 UART 端点） |
| 3 | `laser-tx` | U066 | Unit Laser TX | `gpio` / —（黄线 DIN） | A 低 | `m5_unit_gpio.c`（GPIO 输出观测；UART TX 模式可选） |
| 4 | `neco` | U163 | Unit Neco | `gpio-rmt` / —（DATA + BTN） | B 中低 | `m5_unit_gpio.c`（RMT 帧 + 数字输入；35/70 灯与 25 灯上限需处理） |
| 5 | `midi` | U187 | Unit MIDI | `uart` / —（31250/31520） | B 中低 | `m5_unit_gpio.c`（UART TX 捕获 MIDI 字节流） |
| 6 | `weight` | U030 | Unit Weight | `gpio-timing` / —（CLK+DAT） | C 中 | `m5_unit_gpio.c`（HX711 24-bit 位脉冲协议） |
| 7 | `tof4m` | U172 | Unit ToF4M | `i2c` / `0x29`（VL53L1X） | C 中 | `m5_unit_i2c_sensors.c`（新增 16-bit 寄存器地址 VL53L1X） |
| 8 | `bldc-driver` | U181 | Unit BLDC Driver | `i2c` / `0x65` | C 中 | `m5_unit_i2c_controls.c`（新增完整电机控制寄存器组） |
| 9 | `ac-measure` | U164 | Unit AC Measure | `i2c` / `0x42` | C 中 | `m5_unit_i2c_sensors.c`（新增 AC 测量寄存器组） |
| 10 | `dds` | U105 | Unit DDS | `i2c` / `0x31`（AD9833） | C 中 | `m5_unit_i2c_controls.c`（频率/相位/波形寄存器写入） |
| 11 | `gps` | U032 | Unit GPS | `uart` / 9600 NMEA | C 中 | `m5_unit_gpio.c`（UART RX 注入 NMEA，TX 观测） |
| 12 | `uhf-rfid` | U107 | Unit UHF-RFID | `uart` / 115200 JRD4035 | C 中 | `m5_unit_gpio.c`（UART 命令/响应 + RX fixture 注入） |

复杂度定义：

- **A 低**：只注册 id 并复用现有数据面分支，预计 QEMU 侧改动 `< 20` 行，不新增
  寄存器状态或控制器行为。
- **B 中低**：新增一个 kind / 寄存器组，但直接复用现有指针、快照、QOM 属性框架；
  读/写字节语义是确定性的。
- **C 中**：新增完整命令层/时序响应（16-bit 寄存器地址、HX711 位脉冲、NMEA/AT
  帧解析、AC 测量字符串/字节双视图），但仍在现有 SoC 控制器拓扑（I2C/GPIO/UART）
  内。

未登记差集口径（可复算）：`platform/web/vendor/m5stack-models/catalog/products.json`
的 `category=="unit"` 共 **184** 款；`platform/units/catalog.json` 登记 **70** 款，
其中 `servo8-hat` 在 vendor 目录里属于 HAT 条目、不在 unit 类别；故未登记 =
184 − 69 = **115** 款。任务描述的“约 114 款”与本次精确差集差 1 款（与 batch1/2/3
同类口径差异），不影响选型。

本批多样性：GPIO/RMT 3 款（`laser-tx`/`neco`/`weight`）、UART 4 款
（`rs485-iso`/`midi`/`gps`/`uhf-rfid`）、I2C 5 款（`co2l`/`tof4m`/`bldc-driver`/
`ac-measure`/`dds`）。其中 `co2l` 是已实现 `co2` 的 SCD41 兄弟、`rs485-iso` 是
已实现 `rs485` 的隔离版本、`tof4m` 是已实现 `tof`（VL53L0X）的 VL53L1X 兄弟，
可最大化复用与差分验证价值；本批没有新的双从机/多地址候选（剩余双地址型号没有
官方 UIFlow2 单位驱动）。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

- 官方 UIFlow2 源码快照：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git 远端 `https://github.com/rodrigob/uiflow_micropython.git`，HEAD
  `528edd8a06d2556c8e753c8e4978179bbb12b5ba`，`m5stack/version.txt` 为 `V2.1.5`）。
  本页所有 `m5stack/libs/...:行号` 都**锚定这个快照**。
- 官方 GitHub master 交叉核对：2026-11-02 用
  `https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/...`
  逐文件下载比对本批 14 个 unit 驱动 + 9 个依赖驱动（共 23 个文件）。8 个逐字节
  相同；15 个不同，其中 **7 个有语义差异**（`unit/co2.py`、`unit/co2l.py`、
  `unit/rs485.py`、`unit/ac_measure.py`、`unit/uhf_rfid.py`、`driver/scd40.py`、
  `driver/neopixel/__init__.py`），其余为常量位置/类型注解/文档字符串变化
  （`unit/laser_tx.py`、`unit/neco.py`、`unit/weight.py`、`unit/tof4m.py`、
  `unit/bldc_driver.py`、`driver/jrd4035`、`driver/vl53l1x.py`）。明细见 §6。
- 官方产品页：2026-11-02 直接抓取 12 个 `officialDocs` 页面，SKU、PinMap、芯片名、
  量程/精度、MIDI 波特率描述与 JRD4035 AT 命令说明从页面原文核对；页面链接的
  datasheet/原理图/协议 PDF **未逐页阅读**，标记为 `linked-by-verified-product-page`。
- 官方 I2C 地址总表 `https://docs.m5stack.com/en/product_i2c_addr`（2026-11-02）
  用于交叉核对芯片与 7-bit 地址；若干型号出现产品页/总表/驱动三方不一致，一律
  写进 §5 的 `unresolved`，不按名字猜协议。
- 现有 QEMU 模型参考：`esp-emulator-unit4` worktree 的
  `.work/native-lock-source/qemu` 或 `/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`
  （只读；行号以该快照为准，本报告未修改）。

### 1.2 逐款证据等级

| 等级 | 含义 | 本批型号 |
| --- | --- | --- |
| E1 | 官方 PinMap + 可执行驱动逐行完整语义（寄存器/命令/编码），无需 PDF 即能确定实现所需的通信语义 | `rs485-iso` `laser-tx` `neco` `midi` `weight` |
| E2 | 官方 PinMap + 可执行驱动逐行完整语义，但**官方协议文档/数据手册只确认链接存在、未读**，或存在必须显式标注的未决字段 | `co2l` `tof4m` `bldc-driver` `ac-measure` `dds` `gps` `uhf-rfid` |
| E3 | 只能读到 API/字段名，关键语义 unknown | 本批没有整款 E3；单字段 unresolved 见 §5 |

本报告禁止按产品名推断协议：每个型号都至少能落到一个官方驱动文件的具体行，或者
明确写进 §5 的 `unresolved`。

### 1.3 主机侧约定（本批全部适用）

- UIFlow GPIO `port` 元组为 `(white, yellow)`：`port[0]` 对应 Grove 白线，`port[1]`
  对应黄线。本批的引脚结论都按这个顺序复算，未从颜色名称反推。
- I2C 地址一律写 **7-bit**（`0x62` 等）；VL53L1X 使用 **16-bit 寄存器地址**（大端
  地址 + 数据），与其余 8-bit 寄存器设备不同，模型必须单独实现地址相位。
- UART 型号的 `port[0]` 是 unit→host（host RX），`port[1]` 是 host→unit（host TX）；
  驱动 `UART(id, tx=port[1], rx=port[0])` 的顺序必须按驱动复算。
- 所有主机输入默认值都是**合成测试 fixture**，不是实测硬件默认值；产品页的精度、
  量程、电气参数不进入模型断言。
- 虚拟数据面 PASS 与硬件测量是两类结论；本页不产生任何一类 PASS。

## 2. 与现有 QEMU Unit 模型的复用映射

以下是 `esp-emulator-unit4/.work/native-lock-source/qemu/hw/m5stopwatch/`（只读
参考，本报告未修改；该树包含 batch2b/batch3 C 的 0131 实现）。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c` | `m5_unit_i2c_attach()`；`sensor_attach`；id 分派与 `m5_unit_extra_supported`（sensors/controls/gpio 三张 id 表） | `co2l`/`tof4m`/`bldc-driver`/`ac-measure`/`dds` 注册 |
| `m5_unit_i2c_sensors.c` | `US_SCD40`（0131，命令+CRC 词协议）；`US_*` 寄存器文件框架；`add_number`/`add_fixture_int`/`add_fixture_bool`/`add_i64`/`add_u64`/`add_i2c_address`；`response_word`；`sensor_send`/`sensor_recv` | `co2l` 复用 `US_SCD40`；`tof4m`/`ac-measure` 新增寄存器 kind |
| `m5_unit_i2c_controls.c` | `CONTROL_DAC`/`CONTROL_EXTENCODER`/`CONTROL_ACSSR`/`CONTROL_PBHUB` 框架；`control_send`/`control_recv`/`snapshot_registers`；`add_control_int_fixture`；地址迁移冲突检查 | `bldc-driver`/`dds` 新增控制 kind |
| `m5_unit_gpio.c` | 支持 id 列表；QOM `digital-level`/`pressed`/`input-level`/`adc-samples`；`m5_unit_adc_sample`；RMT 帧捕获（`led-rgb`/`led-frames`，`g->leds` 上限 25）；UART TX 捕获/ RX 注入（`tx-hex`/`rx-hex`）；pad observer（AW3641/ultrasonic 0131） | `rs485-iso`/`laser-tx`/`neco`/`midi`/`gps`/`uhf-rfid`/`weight` |

复用原则（避免把模型写成 host 侧假值）：

- GPIO/ADC/RMT/UART 型号必须继续走 `esp32_gpio_set_input`、
  `esp32_gpio_pad_observer`、`m5_unit_adc_sample`、RMT 捕获与 UART 端点这些
  **控制器级**钩子；不新增直接改 guest 返回值的属性。
- I2C 型号必须在 `I2CSlaveClass.send/recv` 里实现真实总线字节语义（寄存器指针、
  16-bit 地址相位、快照、命令+CRC），QOM 属性只做注入/观测。
- UART 型号必须区分“guest 发往 unit 的 TX 字节”和“unit 发给 guest 的 RX 字节”；
  NMEA/AT/MIDI 响应只能通过真实 guest UART RX 路径注入。

## 3. 地址与总线冲突

本批新增型号与已登记型号的默认地址/引脚冲突（同一条总线/HUB 端口不能共存）：

| 地址/资源 | 本批型号 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x62` | `co2l` U104（SCD41） | `co2` U103（SCD40） | 产品页；官方 I2C 总表；`unit/co2l.py:9,17` |
| `0x29` | `tof4m` U172（VL53L1X） | `tof` U010（VL53L0X）、`color` U009（TCS3472） | 产品页；官方 I2C 总表；`driver/vl53l1x.py:12` |
| `0x65` | `bldc-driver` U181 | 无 | 产品页；官方 I2C 总表；`unit/bldc_driver.py:12` |
| `0x42` | `ac-measure` U164 | 无（0x42 在已登记 Unit 中未占用） | 产品页；官方 I2C 总表；`unit/ac_measure.py:12` |
| `0x31` | `dds` U105 | 无 | 产品页；`unit/dds.py:69` |
| PORT.B 黄/白 | `laser-tx`（DIN/NC）、`neco`（DATA/BTN）、`weight`（CLK/DAT） | 三者物理端口不同实例可共存，但同一 Grove 端口一次只能接一个 | 产品页 PinMap；驱动 `port[]` 顺序 |
| UART PORT.C | `rs485-iso`、`midi`、`gps`、`uhf-rfid` | 同一 UART 端口一次只能接一个；`rs485` 已登记 | 产品页 PinMap；驱动 `UART(id, tx=port[1], rx=port[0])` |

实现建议：`co2l`/`co2`、`tof4m`/`tof`/`color` 必须按“单 bus 只挂一个”建模并写进
fixture 校验；UART 型号必须在 attachment 上显式声明端口占用，不能与同端口其它
Unit 同时创建。

## 4. 各款协议详情

### 4.1 `co2l` — Unit CO2L（U104）

**官方**：[Unit CO2L](https://docs.m5stack.com/en/unit/CO2L)（2026-11-02）；SKU
`U104`；Sensirion **SCD41**；I2C `0x62`；CO2 400–5000ppm，±(40ppm+5%)；
-10..60°C、0..95%RH；支持低功耗单次测量。
**驱动**：`m5stack/libs/unit/co2l.py`（18 行，**快照与 master 语义不同**：master
改为 `CO2LUnit(SCD40)` 子类并使地址常量改名 `CO2L_I2C_ADDR`；快照继承 `CO2Unit`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**协议语义**：完全复用 `unit/co2.py` 的 SCD4x 命令表（2 字节 BE 命令 + 每 2 字节
数据后 CRC8 poly 0x31 init 0xFF），见 batch3 报告 §4.8；SCD41 的差异是量程
400–5000ppm、精度 ±(40ppm+5%)、支持单次测量（0x219D/0x2196）。

**官方 API**：`CO2Unit` 的全部 API（`set_start_periodic_measurement()`、
`get_sensor_measurement()`、`is_data_ready()`、`set/get_temperature_offset()`、
`set/get_sensor_altitude()`、`set_ambient_pressure()`、`set_single_shot_measurement_all/ht()`、
`set_sleep_mode()`、`set_wake_up()` 等，`unit/co2.py`）。

**主机输入**：`co2-ppm`（400..5000，SCD41 量程）、`temperature-c`（-10..60）、
`humidity-pct`（0..95）、`data-ready`（bool）。

**QEMU 建议**：在 `m5_unit_i2c_sensors.c` 的 `US_SCD40` 基础上让 `co2l` 使用同一
kind，仅把 fixture 量程/默认值改为 400..5000 并在 realize 中显式 `unit_id → co2l`
映射；若实现需要区分芯片身份（SCD40 vs SCD41），加只读 QOM `chip-id`（0x40/0x41）
并把来源写进注释。地址 0x62 与已登记 `co2` 冲突，必须单 bus 校验。

**可断言数据面标志**：guest `get_sensor_measurement()` 的 CO2/RH 与 fixture 一致
（temperature 受两份驱动的 buf[1] 解码 bug 影响，不可断言，见 §5）；命令/CRC 词
轨迹；单次测量路径 `set_single_shot_measurement_all()` 后可读。

**风险/未确认**：SCD41 与 SCD40 的芯片身份在 UIFlow2 页面/驱动/官方 I2C 总表之间
存在冲突（总表只写 SCD41 0x62，co2 页面写 SCD40）；快照 vs master 的继承结构不同，
必须钉 SHA；5s 周期/CRC/精度 NOT RUN；0x62 与 co2 冲突；温度解码 bug 见 §5。

### 4.2 `rs485-iso` — Unit RS485-ISO（U094）

**官方**：[Unit RS485-ISO](https://docs.m5stack.com/en/unit/iso485)（2026-11-02）；
SKU `U094`；CA-IS3082W 隔离半双工 RS485；最高 500Kbps；最多 256 节点；
隔离耐压 1000VRMS；fail-safe 接收。
**驱动**：`m5stack/libs/unit/rs485_iso.py`（4 行别名，快照与 master 逐字节相同）
→ `unit/rs485.py` 的 `RS485Unit`（**快照与 master 语义不同**：master 改为
`__new__` 工厂 + `machine` 导入，快照继承 `driver.modbus.master.uSerial`）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。即黄线=unit 的 UART_RX（host TX），白线=unit 的 UART_TX（host RX）。

**协议/驱动语义**：`RS485Unit` 是 `uSerial`（纯 Python Modbus 主站库）的封装：
`write(payload)`、`read(byte=None)`、`readline()`、`any()`、`sendbreak()`、
`flush()`、`txdone()`（`unit/rs485.py:31-80`）；`init(tx_pin, rx_pin, baudrate=9600,
data_bits=8, stop_bits=1, parity=None, ctrl_pin=None)`（`:17-30`）。

**官方 API**：`write/read/readline/any/sendbreak/flush/txdone/init`。

**主机输入**：`rx-hex`（host→unit 的串口字节 fixture，用于模拟对端 Modbus 从站
响应）。

**QEMU 建议**：**直接复用**已登记 `rs485` 的 UART 数据面（`m5_unit_gpio.c` 的
`rs485` 分支：UART TX 捕获 `tx-hex` + RX 注入 `rx-hex`；寄存器模型 `hbridge`/
`rs485` 的既有边界）。只需在 gpio 支持 id 列表加入 `"rs485-iso"` 并让 realize
映射到 `rs485` 分支（地址无、端口 UART），不需要新 kind。与 `rs485` 的端口占用
按“一 UART 端口一个 Unit”处理。

**可断言数据面标志**：guest `write()` 的字节流出现在 QOM `tx-hex`；host 注入
`rx-hex` 后 guest `read()/readline()/any()` 看到相同字节；`transactions`/
`read-bytes`/`written-bytes` 计数；无 I2C 事务。

**风险/未确认**：隔离耐压/ESD/fail-safe/256 节点等电气特性 NOT RUN；快照 `uSerial`
vs master `__new__` 结构差异需钉 SHA；500Kbps 上限不建模；Modbus 从站协议本身由
guest 驱动负责，不由 Unit 模型解释。

### 4.3 `laser-tx` — Unit Laser TX（U066）

**官方**：[Unit Laser TX](https://docs.m5stack.com/en/unit/laser-tx)（2026-11-02）；
SKU `U066`；激光二极管发射；配对 LASER.RX；页面有**人眼安全警告**。
**驱动**：`m5stack/libs/unit/laser_tx.py`（46 行，快照与 master 语义相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`DIN`、White=`NC`。
数字输入在黄线。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 模式 | `unit/laser_tx.py:10-11` | `PIN_MODE`（GPIO）/`UART_MODE` |
| GPIO | `:15-18` | `Pin(port[1], Pin.OUT)`（黄线） |
| UART | `:19-21,29-32` | `UART(id, tx=port[1], rx=port[0])`；`write(payload)` |
| 开/关 | `:34-40` | `on()→value(1)`，`off()→value(0)` |
| 通用写 | `:42-45` | `value(x)→value(int(x))` |

**官方 API**：`on()`、`off()`、`value(x)`、`write(payload)`、`init_uart(...)`。

**主机输入**：`output-level`（bool，fixture）；UART 模式可注入 `tx-hex`。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"laser-tx"`，复用 GPIO 输出 pad observer
（参考 `ssr`/`relay` 的 out-listener 或 `watering` 的 pump 观测）：黄线电平变化
更新 QOM `output-level`/`output-transitions`。UART 模式可复用现有 UART TX 捕获
（`tx-hex`）。白线 NC 不接线。

**可断言数据面标志**：`output-level`/`output-transitions` 随 guest `on()/off()/
value()` 变化；UART 模式 `tx-hex` 与 `write()` 字节一致；`transactions` 为 0。

**风险/未确认**：**激光光功率/波长/人眼安全/调制带宽 NOT RUN**，catalog/README
必须保留“不可直视激光/不可对人或动物”的安全警告，模型不得声称任何光学输出；
UART 模式的具体波特率由 guest 配置，不建模。

### 4.4 `neco` — Unit Neco（U163）

**官方**：[Unit Neco](https://docs.m5stack.com/en/unit/Unit_Neco)（2026-11-02）；
SKU `U163`；35 颗 WS2812C-2020 RGB（产品页），"cat ear" 面板；两个 Grove 口
（可级联/扩展）；一个可交互按键。
**驱动**：`m5stack/libs/unit/neco.py`（60 行，快照与 master 语义相同）+
`driver/neopixel/ws2812.py`（快照=master）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`DATA`、
White=`BTN`。黄线=WS2812 数据（host→unit），白线=按键（unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 构造 | `unit/neco.py:11-17` | `WS2812(port[1], number=70)` + `Button(port[0], active_low=True)` |
| 灯数 | `:11,17` | 驱动默认 **70** 颗；产品页写 **35** 颗 → 冲突 unresolved |
| 区间颜色 | `:19-26` | `set_color_from(begin,end,rgb,delay)` 逐灯写 |
| 渐变 | `:28-41` | `set_color_saturation_from` 计算亮度衰减 |
| 跑马灯 | `:43-50` | `set_color_running_from` 逐灯亮灭 |
| 随机 | `:52-60` | `set_random_color_random_led_from` |
| 按键 | `hardware/button.py` | 白线上拉/低有效按键 |

**官方 API**：`set_color_from()`、`set_color_saturation_from()`、
`set_color_running_from()`、`set_random_color_random_led_from()`，以及继承的
`set_color/set_brightness/fill_color`。

**主机输入**：`button-pressed`（bool，active-low）；观测 `led-rgb`/`led-frames`。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"neco"`：黄线走现有 RMT RGB 捕获
（`led-rgb`/`led-frames`/`incomplete-frames`），但 `g->leds` 需要 **35 或 70**
而现有 realize 有 `unit->onboard_led_count > 25` 的拒绝上限——需要提高/按 unit
配置上限（或把 `onboard_led_count` 设为 35 并调整该检查）。白线走数字输入
（`pressed`/`input-level`，active-low）。两个 Grove 口的级联/pass-through 不在
模型内。

**可断言数据面标志**：guest `set_color_from()` 后 `led-rgb` 帧与 `led-frames` 计数；
`set_random_color_random_led_from()` 的帧非空；guest 读取按键 `button.pressed`
与注入 fixture 一致；`transactions`=0。

**风险/未确认**：驱动默认 70 灯 vs 产品页 35 灯冲突 unresolved；两 Grove 口级联
不建模；WS2812 时序容差/亮度/光学与功耗 NOT RUN；`neopixel` 快照 vs master 的
`set_brightness` 语义差异（见 batch2 §6）仍需钉 SHA。

### 4.5 `midi` — Unit MIDI（U187）

**官方**：[Unit MIDI](https://docs.m5stack.com/en/unit/Unit-MIDI)（2026-11-02）；
SKU `U187`；SAM2695 MIDI 合成芯片；MIDI 1.0/16 通道；Grove UART；左右 MIDI
端口 Bypass/Separate 模式；3.5mm 音频输出与 5-pin DIN。页面写波特率 **31520bps**
（标准 MIDI 是 31250 → 页面/驱动冲突 unresolved）。
**驱动**：`m5stack/libs/unit/midi.py`（242 行，快照=master）+ `driver/sam2695.py`
（614 行，快照=master）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。黄线=host→unit（unit RX / SAM2695），白线=unit→host（host RX）。

**协议语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| UART | `driver/sam2695.py:151-161` | `machine.UART(id, tx=port[1], rx=port[0])`；MIDI 串行 |
| MIDI 命令 | `:9-27` | Note Off 0x80、Note On 0x90、Poly AT 0xA0、CC 0xB0、Program 0xC0、Channel AT 0xD0、Pitch Bend 0xE0、SysEx 0xF0/0xF7、Real-time 0xF8/0xFA/0xFB/0xFC/0xFE/0xFF |
| 音符 API | `:163-181` | `set_note_on(channel,pitch,velocity)`、`set_note_off(channel,pitch)` |
| 乐器 | `:182-212` | `set_instrument(bank,channel,value)`、`set_drums_instrument(...)`、pitch bend |
| 音量/混响/合唱 | `:230-340` | `set_channel_volume`、`set_master_volume`、`set_reverb`、`set_chorus`、`set_pan` |
| EQ/调音/包络 | `:349-530` | `set_equalizer`、`set_tuning`、`set_vibrate`、`set_tvf`、`set_envelope`、`set_scale_tuning`、`set_mod_wheel` |
| 设备命令 | `:577-604` | `set_all_drums`、`cmd_write`（原始 SysEx 字节写） |
| Unit 封装 | `unit/midi.py:237-243` | `MIDIUnit(SAM2695)` + 乐器/音符常量表 |

**官方 API**：上述 `SAM2695` 全部方法（`MIDIUnit` 直接继承）。

**主机输入**：`rx-hex`（MIDI IN 注入，Bypass 模式）；观测 `tx-hex`
（guest→SAM2695 的 MIDI 字节流）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"midi"`，复用现有 UART 端点：
黄线（host→unit）的 guest 写入进 `tx-hex` 捕获（MIDI 命令字节流）；白线
（unit→host）用于 Bypass 模式注入 `rx-hex`。**音频合成不建模**，只断言 MIDI
字节流。无需新寄存器 kind。

**可断言数据面标志**：guest `set_note_on(0,60,127)` 后 `tx-hex` 包含
`90 3C 7F`；`set_note_off` 后 `80 3C xx`；Program Change `C0 xx`；SysEx 帧
`F0..F7`；`transactions`/`read-bytes`/`written-bytes` 与 UART 字节数一致。

**风险/未确认**：页面写 31520bps vs 标准 MIDI 31250 vs 驱动未显式设 baud——
波特率 unresolved，实现时以驱动/固件实际串口配置为准并写 SHA；SAM2695 合成
音频/音色/复调 NOT RUN；Bypass/Separate 硬件切换与左右端口不建模；音频输出
不可断言。

### 4.6 `weight` — Unit Weight（U030）

**官方**：[Unit Weight](https://docs.m5stack.com/en/unit/Unit_Weight)（2026-11-02）；
SKU `U030`；HX711 24-bit ADC（仅 Channel A，PGA 128/64）；10SPS；GPIO 位脉冲
接口（非寄存器）。页面 FAQ 把 Weight 写成 “I2C”（与描述/PinMap/驱动 GPIO 冲突，
unresolved）。
**驱动**：`m5stack/libs/unit/weight.py`（82 行，快照与 master 语义相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`CLK`、
White=`DAT`。即白线=HX711 DOUT（unit→host），黄线=HX711 SCK/CLK（host→unit）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 常量 | `unit/weight.py:12-17` | Channel A gain 128/64、Channel B 32；24 data bits |
| 引脚 | `:22-23` | `Pin(port[0], IN)`＝DAT（白线）、`Pin(port[1], OUT)`＝CLK（黄线） |
| 读原始值 | `:28-52` | 先等 DAT 低（ready，`:56-63` 轮询最多 25×10ms）；循环 24 次：CLK 高→sleep 1us→CLK 低→sleep 1us→读 DAT 位并移位；再发 gain_m 个额外脉冲；`count ^ 0x800000` |
| 去皮/标定 | `:54-60` | `zero_value` 快照与 `_scale` 系数 |
| 通道选择 | `:76-82` | 额外脉冲数=channel（1/3/2） |

**官方 API**：`get_raw_weight`、`get_scale_weight`、`set_tare()`、
`set_calibrate_scale(weight)`、`set_channel(chan)`。

**主机输入**：`weight-g`、`adc-raw`（24-bit signed fixture）、`channel`。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"weight"` + 位脉冲响应模型：黄线用
`esp32_gpio_pad_observer` 统计 guest 的 CLK 脉冲（与 0131 ultrasonic 同模式），
白线由模型按位输出 24-bit 数据（MSB first）+ gain 脉冲；每 25/26/27 个脉冲完成
一次转换并更新读数。QOM：`adc-raw`（可写 24-bit fixture）、`weight-g`、`channel`、
`conversions`、`ready-level`。

**可断言数据面标志**：guest `get_raw_weight` 与 fixture/换算一致；CLK 脉冲数与
转换次数；`get_scale_weight` 随 `set_calibrate_scale`/`set_tare` 变化；
`transactions`=0（无 I2C）。

**风险/未确认**：HX711 时序（10SPS、ready 轮询、1us 半周期）在 QEMU 虚拟时间下
需要按 MicroPython `sleep_us` 语义对齐；页面 FAQ 的 I2C 描述与 PinMap/驱动冲突
unresolved；称重力学/载荷/温度漂移/量程 NOT RUN。

### 4.7 `tof4m` — Unit ToF4M（U172）

**官方**：[Unit ToF4M](https://docs.m5stack.com/en/unit/Unit_ToF4M)（2026-11-02）；
SKU `U172`；VL53L1CX/VL53L1X ToF；I2C `0x29`；4–400cm；27° FoV；mm 级分辨率。
**驱动**：`m5stack/libs/unit/tof4m.py`（5 行别名，快照=master）+
`driver/vl53l1x.py`（281 行，快照与 master **仅文档/格式差异**）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**协议语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `driver/vl53l1x.py:57` | `0x29` |
| 寄存器寻址 | `:267-274` | 16-bit 寄存器地址（大端）+ 数据；`_write_register(addr,data)`/`_read_register(addr,len)` |
| 身份 | `:12-13,174-178` | `MODEL_ID 0x010F`=0xEA、module type 0xCC、mask rev 0x10 |
| 初始化序列 | `:67-170` | 50+ 个 16-bit 寄存器写（含 `0x2D-0x36`、`0x60-0x87` 等），最后设置 timing budget |
| 距离 | `:179-186` | `get_distance`：读 `RESULT__FINAL_CROSSTALK_CORRECTED_RANGE_MM_SD0 0x0096` 2B |
| 就绪 | `:199-204` | `get_data_ready`：读 `0x0031` bit0 |
| 测距启停 | `:187-198` | `0x0087` mode start/stop、`0x0086` interrupt clear |
| Timing budget | `:206-228` | `TB_SHORT_DIST`/`TB_LONG_DIST` 覆盖 15/20/33/50/100/200/500ms，写 `0x005E/0x0061` 等 |
| 距离模式 | `:236-266` | short/long 两套寄存器值（`0x004B`、`0x0060/0x0063`、`0x0078/0x007A` 等） |
| 地址迁移 | `:275-281` | `0x0001` 写新地址 |

**官方 API**：`get_model_info`、`get_distance`、`get_data_ready`、
`set_continuous_start/stop_measurement`、`clear_interrupt`、
`get/set_measurement_timing_budget`、`get/set_distance_mode`、`set_i2c_address`。

**主机输入**：`distance-mm`（40..4000）。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_VL53L1X`：必须实现 **16-bit
寄存器地址相位**（写事务：2B 地址 BE，然后数据；读事务：2B 地址 BE，再重复起始读，
地址字节随读自动递增——模型需按驱动的 `_read_register` 语义核对）。实现 model id
`0x010F`=0xEA/0xCC/0x10、init 序列接受（寄存器文件）、`0x0087` 启停、
`0x0031` 就绪、`0x0096` 距离 2B 由 fixture 反算；timing budget 写只存状态。
QOM：`distance-mm`、`data-ready`、`timing-budget-ms`、`range-status`、
`i2c-address`。

**可断言数据面标志**：guest `get_model_info` 通过身份检查；`get_distance` 与
fixture 一致；`get_data_ready` 受 fixture 门控；init 序列的写寄存器轨迹；
`0x0001` 地址迁移与冲突检查。

**风险/未确认**：产品页写 VL53L1CXV0FY/1，对比表又写 VL53L1X（芯片命名
unresolved）；16-bit 寄存器地址 + 读自动递增语义必须与驱动逐字节核对；4m 量程/
分辨率/激光安全/光学 NOT RUN；0x29 与已登记 `tof`（VL53L0X）、`color`（TCS3472）
冲突。

### 4.8 `bldc-driver` — Unit BLDC Driver（U181）

**官方**：[Unit BLDC Driver](https://docs.m5stack.com/en/unit/Unit_BLDC_Driver)
（2026-11-02）；SKU `U181`；STM32G030F6P6 + DRV11873PWPR；I2C `0x65`；
5V@508mA 输出；失速保护。
**驱动**：`m5stack/libs/unit/bldc_driver.py`（199 行，快照与 master **仅注解/
导入差异**）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `unit/bldc_driver.py:14` | mode（0=open loop / 1=close loop） |
| `0x10` | `:20` | open-loop PWM `int16le`（0..2047） |
| `0x20`/`0x90`/`0xB0` | `:21,24,26` | 回读 RPM float/int/ASCII |
| `0x30`/`0xA0`/`0xC0` | `:25,27,28` | 回读频率 float/int/ASCII |
| `0x40`/`0xD0` | `:29,30` | 设定 RPM float/int |
| `0x50` | `:31` | PID（3 字节 P/I/D） |
| `0x60` | `:15` | 方向 |
| `0x70`/`0x71` | `:16-17` | 电机型号 / 极对数 |
| `0x80` | `:18` | 电机状态 |
| `0xF0` | `:32` | 写 flash 保存 |
| `0xFE`/`0xFF` | `:33-34` | 固件版本 / I2C 地址 |

**官方 API**：`get/set_mode`、`get/set_direction`、`get/set_motor_model`、
`get/set_pole_pairs`、`get_motor_status`、`get/set_open_loop_pwm`、
`get_read_back_rpm_float/int/str`、`get_read_back_freq_float/int/str`、
`get/set_rpm_float`、`get/set_rpm_int`、`get/set_pid_value`、
`save_data_in_flash()`、`get_device_spec(mode)`、`set_i2c_address()`。

**主机输入**：`rpm`（float/int）、`pwm`（0..2047）、`mode`、`direction`、
`pole-pairs`、`pid`。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_BLDC`：寄存器文件 +
派生语义（float/int/ASCII 三视图由同一 RPM/频率 fixture 计算；PID 3 字节；
0xFF 地址迁移；0xF0 flash 写计数）。QOM：`mode`、`direction`、`rpm`、
`rpm-readback`、`frequency-hz`、`pwm`、`pid`、`motor-status`、`flash-writes`、
`fw-version`、`i2c-address`。

**可断言数据面标志**：guest `set_mode/set_direction/set_open_loop_pwm` 后读回；
`get_read_back_rpm_float/int/str` 三视图与 fixture 自洽；PID 读回；地址迁移；
`save_data_in_flash()` 计数；`transactions`/`read/write bytes`。

**风险/未确认**：BLDC 电机电气/转速/失速保护/DRV11873 状态与 5V 输出 NOT RUN；
RPM float 用 `struct.unpack("<f")`，模型必须用真实 IEEE754 编码；页面 STM32G030
vs 官方 I2C 总表 STM32G030 一致（无冲突）；0x65 无已登记冲突；`0xF0` flash 语义
（是否持久化）unresolved。

### 4.9 `ac-measure` — Unit AC Measure（U164）

**官方**：[Unit AC Measure](https://docs.m5stack.com/en/unit/AC%20Measure%20Unit)
（2026-11-02）；SKU `U164`；STM32G030F6P6 + HLW8032 + B0505ST16-W5 隔离 +
EL357 光耦；I2C `0x42`；AC 100–240V@10A 单相测量。
**驱动**：`m5stack/libs/unit/ac_measure.py`（205 行，快照与 master **语义不同**：
master 把模块级常量搬进类属性并加类型注解）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。
AC 端子 HT3.96-4P：L1/PE/L2/N。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00/0x10/0x20/0x30` | `unit/ac_measure.py:13-16` | 电压/电流/有功功率/视在功率 7 字节 ASCII |
| `0x40` | `:17` | 功率因数 4 字节 ASCII |
| `0x50` | `:18` | kWh 11 字节 ASCII |
| `0x60/0x70/0x80/0x90` | `:19-22` | 电压/电流 u16le、有功/视在功率 u32le |
| `0xA0/0xB0` | `:23-24` | 功率因数 u8 / kWh u32le |
| `0xC0/0xD0` | `:25-26` | 电压/电流校准系数 写 |
| `0xE0` | `:27` | 保存系数 |
| `0xFC` | `:28` | data-ready |
| `0xFD` | `:29` | 跳 bootloader |
| `0xFE/0xFF` | `:30-31` | 固件版本 / I2C 地址 |

**官方 API**：`get_voltage/current/active_power/apparent_power/power_factor/kwh`
的 `_str` 与 `_byte` 双视图、`get/set_voltage_coeff`、`get/set_current_coeff`、
`set_save_coeff()`、`get_data_ready()`、`set_jump_bootloader()`、
`get_device_status(mode)`、`set_i2c_address()`。

**主机输入**：`voltage-v`、`current-a`、`active-power-w`、`apparent-power-va`、
`power-factor`、`energy-kwh`、`data-ready`。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_ACMEASURE`：寄存器文件 + 派生
双视图（ASCII 字符串由数值 fixture `g_snprintf` 生成，固定宽度需按驱动读取长度
对齐；byte 视图用 LE 编码）；系数写/保存/数据就绪/固件/地址迁移；0xFD 写只记录
（不真正跳 bootloader）。QOM：数值 fixture 6 项 + `coeff-voltage`/`coeff-current`、
`data-ready`、`fw-version`、`i2c-address`、`save-coeff-writes`。

**可断言数据面标志**：guest `_str` 与 `_byte` 视图与 fixture 自洽；系数写读回；
`get_data_ready()` 受 fixture 门控；`set_save_coeff()` 计数；
`transactions`/`read/write bytes`。

**风险/未确认**：**安全边界：AC 100–240V@10A 是测量输入，不是可切换负载；
模型只模拟寄存器读数，绝不模拟/宣称市电通断、隔离耐压、过流或计量精度**；
HLW8032/隔离/校准系数语义 unresolved；`0xFD` bootloader 跳转不建模（写只记录）；
页面 STM32G030 vs 官方 I2C 总表 STM32F030 冲突 unresolved；`0x42` 无已登记冲突。

### 4.10 `dds` — Unit DDS（U105）

**官方**：[Unit DDS](https://docs.m5stack.com/en/unit/dds)（2026-11-02）；SKU
`U105`；AD9833 波形发生器 + STM32F031G4U6；I2C `0x31`；0–1MHz、28-bit 频率
分辨率、11-bit 相位、0–0.6V 幅度；波形 SINE/TRIANGLE/SQUARE/SAWTOOTH/DC。
**驱动**：`m5stack/libs/unit/dds.py`（298 行，快照=master 逐字节相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/编码（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x10` | `unit/dds.py:60` | DDS_DESC_ADDR（描述，未在 API 中使用） |
| `0x20` | `:61,137-140` | DDS_MODE_ADDR：写 `0x80|wave`（wave 0b001..0b101） |
| `0x21` | `:62,140-175` | DDS_CTRL_ADDR：`0x80` + sleep bits（0x40/0x20/0x10/0x08） |
| `0x30` | `:63,98-120` | DDS_FREQ_ADDR：4B，bit7=0 选 FREQ0/bit7=1 选 FREQ1；频率字=freq*2^28/10MHz |
| `0x34` | `:64,122-136` | DDS_PHASE_ADDR：2B，bit7 选 PHASE0/1；相位字=deg*2048/360 |
| 读回 | 示例 `:…` | `i2c.readfrom_mem(0x31,0x30,6)` 可直接读寄存器 |
| FMCLK | `:66` | 10MHz 参考时钟 |

**官方 API**：`set_freq(index,freq)`、`set_phase(index,phase)`、
`set_freq_phase(...)`、`set_mode(mode)`、`set_ctrl(...)`、
`select_freq_reg(index)`、`select_phase_reg(index)`、
`quick_output(mode,freq,phase)`。

**主机输入**：`waveform`（1..5）、`frequency-hz`（0..1e6）、`phase-deg`（0..360）、
`freq-reg`（0/1）、`phase-reg`（0/1）、`sleep-mode`（0/1/2）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_DDS`：寄存器文件写：
0x20 mode、0x21 ctrl、0x30 4B 双频寄存器、0x34 2B 双相位寄存器；读回寄存器
内容。模型可把频率字反算为 Hz 供 QOM 观测。QOM：`frequency-hz`、
`phase-deg`、`waveform`、`active-freq-reg`、`active-phase-reg`、`sleep-mode`、
`ctrl-word`、`i2c-address`。

**可断言数据面标志**：guest `quick_output(WAVE_SINE,1000,0)` 后 QOM
`frequency-hz`≈1000、`waveform`=1；`set_freq(index=1)` 写 FREQ1 位；`set_ctrl`
sleep 位；寄存器读回与写入一致。

**风险/未确认**：AD9833 实际模拟波形/幅度/相位精度/输出阻抗 NOT RUN；0.6V
幅度与 10MHz mclk 由硬件决定，不建模；`set_ctrl` 的 bit 语义（sleep/复位/
频率/相位选择）只按驱动实现；0x31 无已登记冲突。

### 4.11 `gps` — Unit GPS（U032）

**官方**：[Unit GPS](https://docs.m5stack.com/en/unit/Unit_GPS)（2026-11-02，
EOL 页）；SKU `U032`；AT6558 北斗/GPS + MAX2659 放大；UART 9600 8N1
（1 start/1 stop/no parity）；定位精度 2.5m；更新率 1–10Hz；支持 NMEA GGA/RMC/VTG。
**驱动**：`m5stack/libs/unit/gps.py`（123 行，快照=master）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。黄线=host→unit（unit RX），白线=unit→host（host RX）。

**协议语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| UART | `unit/gps.py:31-33` | `UART(id, tx=port[1], rx=port[0])`，9600 8N1，rxbuf 1024 |
| 轮询 | `:36` | `TimerThread.add_timer(50, PERIODIC, self._monitor)`；50ms 周期读串口 |
| 行解析 | `:103-117` | `_monitor` 累积行，按 `$GNGGA/$GNRMC/$GNVTG` 分派 |
| GGA | `:44-78` | 时间（含时区偏移）、纬度/经度（度分→十进制）、卫星数、定位质量、海拔 |
| RMC | `:86-92` | 日期/速度/航向 |
| VTG | `:93-102` | 速度 km/h、航向 |
| 时区 | `:41-42` | `set_time_zone(value)` 默认 +8 |
| 十进制换算 | `:80-85` | degree/minute → decimal |

**官方 API**：`decode_gga/decode_rmc/decode_vtg`、`set_time_zone`、
`uart_port_id`、`deinit`，以及解析字段（`latitude/longitude/altitude/
satellite_num/pos_quality/speed_knot/speed_kph/course/gps_time/gps_date`）。

**主机输入**：`nmea-lines`（fixture NMEA 句子，按 50ms 注入 guest UART RX）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"gps"`，复用现有 UART 端点：白线
（unit→host）通过 `esp32_uart_inject_rx()` 注入 fixture NMEA 句子（与 rs485
RX 注入同路径），黄线（host→unit）捕获 guest 发送字节（GPS 通常只收不发，
观测 `tx-hex`）。模型按 50ms 节拍注入一行 NMEA（或按 fixture 顺序循环），
QOM：`rx-lines`（fixture 配置）、`tx-hex`、`injected-lines`。

**可断言数据面标志**：guest 解析出的 `latitude/longitude/altitude/satellite_num/
gps_time` 与 fixture NMEA 一致；注入行数；`transactions`/`read-bytes` 计数；
无 I2C。

**风险/未确认**：真实 GNSS 卫星/射频/天线/定位精度 NOT RUN；NMEA checksum
是否被驱动校验（驱动只按逗号切分，不校验 *XX checksum）→ 模型可注入合法
checksum 但 guest 不校验，unresolved；冷/热启动时间、1–10Hz 更新率不建模；
PORT.C 与 midi/uhf-rfid/rs485-iso 共享 UART 端口冲突；页面 EOL。

### 4.12 `uhf-rfid` — Unit UHF-RFID（U107）

**官方**：[Unit UHF-RFID](https://docs.m5stack.com/en/unit/uhf_rfid)（2026-11-02）；
SKU `U107`；JRD-4035 UHF 模块 + 陶瓷天线；840–960MHz；EPC Gen2 / ISO 18000-6C；
UART 115200；内置 AT 命令集；标签缓存 200；读取距离 1m。
**驱动**：`m5stack/libs/unit/uhf_rfid.py`（74 行，**快照与 master 语义不同**：
master 新增 NXP EAS/config word/read-protect 等 API）+ `driver/jrd4035/__init__.py`
（580 行，**快照与 master 仅类型注解/返回类型差异**，另有新增 NXP 命令方法）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。黄线=host→unit，白线=unit→host。

**协议语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| UART | `unit/uhf_rfid.py:17-18` | `machine.UART(id, 115200, tx=port[1], rx=port[0])` |
| 帧格式 | `driver/jrd4035/__init__.py:10-15` | 头 `0xBB`、尾 `0x7E`；帧类型 0x00 命令 / 0x01 响应 / 0x02 通知 |
| 模块信息 | `:55-61` | `0x00/0x01/0x02` 读模块信息 |
| 读参数/功率 | `:65-89` | `0x03` 读参数、`0x22` inventory、`0x27` 连续 inventory、`0x28` 功率 |
| 选择 | `:104-120` | `0x0C` select（target/action/membank/pointer/truncate/mask） |
| 读写/锁 | `:143-190` | read_mem_bank/write_mem_bank/lock/kill/access pwd（命令码见文件） |
| NXP | master 版新增 | EAS alarm / config word / read-protect |
| checksum | 驱动命令构造 | 帧尾校验（驱动负责） |

**官方 API**：`inventory()`、`read_mem_bank()`、`write_mem_bank()`、`select()`、
`set_access_password()`、`set_kill_password()`、`kill()`、`lock_mem_bank()`、
`get/set_impinj_monza_qt_*`，以及驱动底层的 `get_module_info`、
`get/ set_parameter`、`set_power`、`get/set_region`、`get/frequency` 等。

**主机输入**：`responses-hex`（fixture 响应帧，按命令顺序返回）；观测 `tx-hex`。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"uhf-rfid"`，复用 UART 端点：黄线捕获
guest 命令帧到 `tx-hex`；白线按 fixture `responses-hex` 通过
`esp32_uart_inject_rx()` 注入响应帧（帧头/尾/校验由 fixture 提供，模型可校验
或原样注入）。QOM：`rx-frames-hex`、`tx-hex`、`frames-injected`、`frames-sent`。

**可断言数据面标志**：guest `inventory()` 发送的 `0xBB..0x7E` 帧出现在 `tx-hex`；
注入响应后 guest 解析出的 EPC/状态与 fixture 一致；`transactions` 计数；无 I2C。

**风险/未确认**：RF 840–960MHz/天线/Gen2 空口/读取距离 1m/区域限制 NOT RUN；
kill/lock/密码等安全操作只做帧层，绝不宣称真实标签安全；快照 vs master 的
NXP API 差异需钉 SHA；UART 端口与 gps/midi/rs485-iso 冲突；标签缓存 200 不建模。

## 5. 未确认项汇总（unresolved）

1. `co2l`：SCD40 vs SCD41 芯片身份冲突（co2 页面 SCD40、co2l 页面 SCD41、官方
   I2C 总表 SCD41 0x62）；快照 `CO2LUnit(CO2Unit)` vs master `CO2LUnit(SCD40)`
   继承结构不同；5s 周期/CRC/精度 NOT RUN；0x62 与 co2 冲突。
2. `rs485-iso`：隔离耐压/ESD/fail-safe/500Kbps/256 节点 NOT RUN；快照继承
   `uSerial` vs master `__new__` 工厂差异；Modbus 从站语义由 guest 负责。
3. `laser-tx`：**激光光功率/波长/人眼安全/调制带宽 NOT RUN**，安全警告必须保留；
   UART 模式波特率由 guest 配置，不建模。
4. `neco`：驱动默认 70 灯 vs 产品页 35 灯冲突 unresolved；两 Grove 口级联不建模；
   WS2812 时序容差/亮度/光学/功耗 NOT RUN；`neopixel` 快照 vs master
   `set_brightness` 语义差异需钉 SHA。
5. `midi`：页面 31520bps vs 标准 MIDI 31250 vs 驱动未显式设 baud → 波特率
   unresolved；SAM2695 合成音频/音色/复调 NOT RUN；Bypass/Separate 硬件切换不建模。
6. `weight`：HX711 时序（10SPS/ready 轮询/1us 半周期）在 QEMU 虚拟时间下需对齐；
   页面 FAQ 的 I2C 描述与 PinMap/驱动 GPIO 冲突；称重力学/载荷/温漂/量程 NOT RUN。
7. `tof4m`：VL53L1CX vs VL53L1X 芯片命名冲突；16-bit 寄存器地址 + 读自动递增
   语义需逐字节核对；4m 量程/分辨率/激光安全/光学 NOT RUN；0x29 与 tof/color 冲突。
8. `bldc-driver`：BLDC 电机电气/转速/失速保护/DRV11873 状态/5V 输出 NOT RUN；
   `0xF0` flash 持久化语义 unresolved；RPM float 需真实 IEEE754 编码。
9. `ac-measure`：**AC 100–240V@10A 是测量输入，不是可切换负载；模型只模拟
   寄存器读数，绝不宣称市电通断/隔离耐压/过流/计量精度**；HLW8032/隔离/校准
   系数语义 unresolved；`0xFD` bootloader 跳转不建模；STM32G030（页面）vs
   STM32F030（官方总表）冲突 unresolved。
10. `dds`：AD9833 模拟波形/幅度/相位精度/输出阻抗 NOT RUN；`set_ctrl` bit
    语义只按驱动实现；0x31 无已登记冲突。
11. `gps`：真实 GNSS 卫星/射频/天线/定位精度 NOT RUN；NMEA checksum 不被驱动
    校验（unresolved）；冷/热启动与更新率不建模；PORT.C 与 midi/uhf-rfid/rs485-iso
    同端口冲突；页面 EOL。
12. `uhf-rfid`：RF 840–960MHz/天线/Gen2 空口/读取距离/区域限制 NOT RUN；
    kill/lock/密码只做帧层、不宣称真实标签安全；快照 vs master NXP API 差异需钉
    SHA；UART 端口冲突。

## 6. 驱动版本交叉核对（快照 vs 官方 master）

快照 HEAD `528edd8a06d2556c8e753c8e4978179bbb12b5ba`（`m5stack/version.txt` =
`V2.1.5`）。2026-11-02 逐文件下载 master 原文比对，23 个文件中 8 个逐字节相同、
15 个不同：

| 文件 | 快照 SHA-256（前 16） | master SHA-256（前 16） | 差异语义 |
| --- | --- | --- | --- |
| `unit/co2l.py` | `7a5fd59da6bfc2bc` | `3d1537c872451ac5` | **语义不同**：master 改为 `CO2LUnit(SCD40)`，地址常量改名 `CO2L_I2C_ADDR` |
| `unit/co2.py` | `70081fa3bf228d35` | `9ea29cca598b6ca9` | **重写**：master 改为 `CO2Unit(SCD40)` 子类；快照自带完整命令层 |
| `unit/rs485.py` | `4b22eb3966dbc0e7` | `c388ef8e7e43f25e` | **语义不同**：master 改为 `__new__` 工厂 + `machine` 导入 |
| `unit/laser_tx.py` | `1ebd0434ea837c13` | `34ebd6307ccc4eb1` | AST 语义一致（仅文档/格式） |
| `unit/neco.py` | `332c4db12929d68c` | `44481254eb4930fc` | AST 语义一致 |
| `unit/weight.py` | `ff365f871c66aa5f` | `6cfe65908efe6cab` | AST 语义一致 |
| `unit/tof4m.py` | `1734abed4538eb55` | `2cb68a333bc090dd` | 仅新增 `ToF4MUnit = TOF4MUnit` 别名（语义等价） |
| `unit/bldc_driver.py` | `ff93419bb04e4cd0` | `36a94199b6d32020` | 仅导入/类型注解差异 |
| `unit/ac_measure.py` | `31912dd9c5e3680d` | `26c4a1fb361cbd86` | **语义不同**：master 把模块级常量搬进类属性并加类型注解 |
| `unit/uhf_rfid.py` | `81407c62ceca5368` | `c8b13468aca2d6f6` | **语义不同**：master 新增 NXP EAS/config word/read-protect API |
| `driver/scd40.py` | `0a8590c580190405` | `168ea241d593ac37` | **完全不同的实现**：快照 asyncio，master 同步命令层 |
| `driver/neopixel/__init__.py` | `f1995e9fa025330b` | `d97ffc1bd3cce82b` | **语义不同**：master 增加 `pin.init(...,value=0)` 与 `set_brightness` 反缩放 |
| `driver/jrd4035/__init__.py` | `6fa5c043b283e272` | `a3ada7bcd7ae42f3` | 类型注解/返回类型 + 新增 NXP 命令方法 |
| `driver/vl53l1x.py` | `3adf98a041cc12b3` | `738fb31a2bf8b2b7` | AST 语义一致（仅文档/格式） |
| `unit/rs485_iso.py` | `3d9beac7838dfc31` | 同 | 逐字节相同 |
| `unit/midi.py` | `c610921c77a26c23` | 同 | 逐字节相同 |
| `unit/dds.py` | `a556555822d823a7` | 同 | 逐字节相同 |
| `unit/gps.py` | `527921a49640a5d3` | 同 | 逐字节相同 |
| `driver/checksum.py` | `100223c8df7e7c42` | 同 | 逐字节相同 |
| `driver/modbus/master/uSerial.py` | `cdc3b1bf201a6ed6` | 同 | 逐字节相同 |
| `driver/neopixel/ws2812.py` | `65d6bff5a7689eb0` | 同 | 逐字节相同 |
| `driver/sam2695.py` | `335a531c6b844fa3` | 同 | 逐字节相同 |
| `driver/timer_thread.py` | `6bf8e0b67669070d` | 同 | 逐字节相同 |

实现建议：catalog 草稿的 `evidence[].sha256` 同时记录**快照哈希**；若实现者使用
master 版本，必须在实现 PR 里显式写明并锚定 master 哈希。`co2l`/`co2`/
`rs485-iso`/`ac-measure`/`uhf-rfid` 必须钉一个 SHA，不能混用两版语义。

## 7. 落地顺序建议

1. `rs485-iso`（A）：零新 kind，直接证明已登记 `rs485` UART 端点可复用。
2. `laser-tx`（A）：GPIO 输出观测最小改动；安全 blocker 先写进 catalog。
3. `co2l`（B）：复用 0131 `US_SCD40`，只改量程/单次测量/身份；与 co2 做地址冲突负例。
4. `neco`（B）：验证 RMT 帧捕获可突破现有 25 灯上限（需调整 `onboard_led_count` 检查）。
5. `midi`（B）：验证 UART TX 捕获 MIDI 字节流（无需 RX）。
6. `tof4m`（C）：新增 16-bit 寄存器地址 I2C 模型，与 `tof`（VL53L0X）差分。
7. `bldc-driver`（C）：完整电机控制寄存器组（float/int/ASCII 三视图）。
8. `ac-measure`（C）：AC 测量双视图（ASCII/byte）+ 安全 blocker。
9. `dds`（C）：频率/相位/波形寄存器写入与读回。
10. `weight`（C）：HX711 位脉冲时序模型（先做固定 24-bit fixture，再做出皮/标定）。
11. `gps`（C）：UART NMEA 注入 + guest 解析字段断言。
12. `uhf-rfid`（C）：JRD4035 帧命令/响应 fixture（先做 inventory，再做 NXP 扩展）。

## 8. 官方来源清单（本批引用）

**产品页（2026-11-02 读取）**：

- <https://docs.m5stack.com/en/unit/CO2L>
- <https://docs.m5stack.com/en/unit/iso485>
- <https://docs.m5stack.com/en/unit/laser-tx>
- <https://docs.m5stack.com/en/unit/Unit_Neco>
- <https://docs.m5stack.com/en/unit/Unit-MIDI>
- <https://docs.m5stack.com/en/unit/Unit_Weight>
- <https://docs.m5stack.com/en/unit/Unit_ToF4M>
- <https://docs.m5stack.com/en/unit/Unit_BLDC_Driver>
- <https://docs.m5stack.com/en/unit/AC%20Measure%20Unit>
- <https://docs.m5stack.com/en/unit/dds>
- <https://docs.m5stack.com/en/unit/Unit_GPS>
- <https://docs.m5stack.com/en/unit/uhf_rfid>
- 官方 I2C 地址总表：<https://docs.m5stack.com/en/product_i2c_addr>

**官方驱动（快照路径，`m5stack/libs/` 下）**：

- `unit/co2l.py`、`unit/co2.py`、`unit/rs485.py`、`unit/rs485_iso.py`、
  `unit/laser_tx.py`、`unit/neco.py`、`unit/midi.py`、`unit/weight.py`、
  `unit/tof4m.py`、`unit/bldc_driver.py`、`unit/ac_measure.py`、`unit/dds.py`、
  `unit/gps.py`、`unit/uhf_rfid.py`
- `driver/scd40.py`、`driver/checksum.py`、`driver/modbus/master/uSerial.py`、
  `driver/neopixel/ws2812.py`、`driver/neopixel/__init__.py`、
  `driver/sam2695.py`、`driver/jrd4035/__init__.py`、`driver/vl53l1x.py`、
  `driver/timer_thread.py`

**链接但未读的 datasheet/协议文档**：各产品页 Datasheets 节列出的 SCD41/
CA-IS3082W/WS2812C/SAM2695/HX711/VL53L1X/DRV11873PWPR/HLW8032/AD9833/AT6558/
MAX2659/JRD-4035 等 PDF。按仓库既有方法，这些只作为实现参考链接，不声称内容已
独立复核。

## 9. 复现方式

```bash
cd /Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public
git rev-parse HEAD   # 528edd8a06d2556c8e753c8e4978179bbb12b5ba
cat m5stack/version.txt   # V2.1.5

# 快照 vs master 逐文件哈希
for f in unit/co2l.py driver/scd40.py ...; do
  sha256sum "m5stack/libs/$f"
  curl -sfL "https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/$f" | sha256sum
done
```

本报告未运行任何 QEMU/固件/Device Service；不产生运行时 PASS。

## 10. catalog 草稿说明

`2026-11-02-batch4-catalog-draft.json` 的 12 条记录：

- 字段对齐 `platform/units/catalog.json` 现有条目
  （`id/name/sku/visual_asset/official_docs/checked_at/chips/interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/blocker/input_semantics/output_semantics/limitations`）；
- 全部 `model_status: "planned"`、`runtime.status: "unsupported"`（草稿，不是
  runtime admission）；
- `address_7bit` 用 **7-bit**；UART/GPIO 型号地址为空数组；
- `evidence[].sha256` 记录快照哈希，`sha256_matches_snapshot_528edd8` 标记是否与
  快照一致，`sha256_master` 在差异文件中额外记录 master 哈希；
- 所有 `inputs.*.default` 都是合成测试 fixture，不是实测值；`blocker` 写明实现
  前置条件与硬件边界（含激光安全、AC 市电测量、RF/称重等 NOT RUN）。

## 11. A+B 6 款 QEMU 实现状态（补丁 0134，2026-11-02）

第四批 A+B 6 款（`rs485-iso`/`laser-tx`/`co2l`/`neco`/`midi`/`tof4m`）已由
[`0134-unit-batch4ab.patch`](../../patches/qemu-m5stack-peripherals/0134-unit-batch4ab.patch)
接入 QEMU 数据面。**base 是 canonical native layer `75f1d24` + 已合入的
`0120/0121/0122/0123/0124/0125/0126/0127/0128/0129` + `0131`（batch3 C）**；
`0130`（batch3 A+B）与本补丁是并行层，不能顺序 apply，本补丁不依赖 `0130`；
`0132`/`0133` 已被 unit-protocols 的 batch3 证据修复占用，所以本批补丁号用
**0134**。0130/0131 的 reconciliation 留给后续独立任务，不在本任务范围。
**尚未采集 guest/Device Service 证据**，因此 catalog 6 条与 runtime-profiles 6 条
均保持 `planned`、hosts 为空；离线 QOM smoke（S3 board、无 guest 固件）只验证属性
注册、fixture 读写、范围/只读拒绝与结构（21/21 PASS），不构成功能 PASS。

| Unit | 0134 模型 | QOM fixtures/观测 | 仍需 guest 证据 / unresolved 边界 |
| --- | --- | --- | --- |
| `rs485-iso` U094 (UART PORT.C) | 复用已登记 `rs485`（U034）UART 端点：`tx-hex` 捕获 + `rx-hex` 注入；零新 kind | 输入 rx-hex；观测 tx-hex、transactions/read/written-bytes | 隔离耐压/ESD/fail-safe/500Kbps/256 节点 NOT RUN；快照 uSerial 继承 vs master `__new__` 工厂差异须钉 SHA；Modbus 从站语义由 guest 负责；PORT.C 与 midi/gps/uhf-rfid 端口冲突 |
| `laser-tx` U066 (GPIO DIN) | GPIO id `laser-tx`：黄线 pad 输出观测 `output-level` + 单元级 `output-transitions`；UART TX 模式未建模 | 输入 output-level；观测 output-transitions | **激光安全：人眼/光功率/波长/调制带宽 NOT RUN；catalog 保留不可直视/不可对人或动物的警告；不得声称光学输出** |
| `co2l` U104 (0x62 SCD41) | 复用 0131 `US_SCD40`：量程 400..5000、单次测量 0x219D/0x2196、只读 `chip-id`=0x41 身份 fixture | 输入 co2-ppm/temperature-c/humidity-pct/data-ready；观测 serial-number/chip-id/measurement-reads | **SCD40（co2 页面）vs SCD41（co2l 页面/官方总表）冲突；快照 `CO2LUnit(CO2Unit)` vs master `CO2LUnit(SCD40)` 结构不同须钉 SHA；两份驱动温度解码取 buf[1] 而非 buf[4] → guest temperature 不可断言，只有 CO2/湿度可断言；0x62 与 co2 冲突；5s 周期/CRC/精度 NOT RUN** |
| `neco` U163 (RMT+BTN) | GPIO id `neco`：黄线 RMT 捕获 35 灯 WS2812 帧（RGB 缓冲 25→128、realize 上限 128）；白线 active-low 按键 | 输入 button-pressed（QOM `pressed`）；观测 led-rgb(35)/led-frames/incomplete-frames/input-events | **驱动默认 70 灯 vs 产品页 35 灯冲突（模型按 35 实现）；两 Grove 口级联/pass-through 不建模；WS2812 时序/亮度/光学/功耗 NOT RUN；neopixel 快照 vs master `set_brightness` 语义差异须钉 SHA** |
| `midi` U187 (UART) | GPIO id `midi`：黄线捕获 guest→SAM2695 MIDI 字节流（tx-hex），白线可选 MIDI IN 注入（rx-hex）；音频合成不建模 | 输入 rx-hex；观测 tx-hex/transactions/written-bytes | **页面 31520bps vs 标准 31250 vs 驱动未设 baud → 波特率 unresolved；SAM2695 音色/复调/音频 NOT RUN；Bypass/Separate 硬件切换不建模；PORT.C 端口冲突** |
| `tof4m` U172 (0x29 VL53L1X) | 新增 `US_VL53L1X`：16-bit 寄存器地址相位（2B BE 地址 + 数据、读自动递增）、model id 0x010F..0x0111=0xEA/0xCC/0x10、data-ready 0x0031、range status 0x0089、distance 0x0096/0x0097、start/stop 0x0087、interrupt clear 0x0086、地址迁移 0x0001、init 序列寄存器文件、fixture 20ms 就绪节拍 | 输入 distance-mm(40..4000)/data-ready；观测 timing-budget-ms/range-status/clear-writes/i2c-address | **页面 VL53L1CXV0FY/1 vs 对比表 VL53L1X 命名冲突；16-bit 地址/自增语义需逐字节核对；4m/分辨率/激光安全/光学 NOT RUN；0x29 与 tof（VL53L0X）/color（TCS3472）三方冲突** |

离线 QOM smoke 复现（S3 板；`m5atoms3r`，无 guest 固件；6 attachment 共享一次
启动，UART 单元在离线状态下 RX 注入按“无路由”拒绝，属预期）：

```bash
cat > /tmp/unit-smoke-config4.json <<'JSON'
{"schema_version":1,"attachments":[
 {"id":"iso1","unit_id":"rs485-iso","pins":{"yellow":5,"white":6}},
 {"id":"midi1","unit_id":"midi","pins":{"yellow":11,"white":12}},
 {"id":"laser1","unit_id":"laser-tx","pins":{"yellow":7,"white":8}},
 {"id":"neco1","unit_id":"neco","pins":{"yellow":9,"white":10}},
 {"id":"tof1","unit_id":"tof4m","pins":{"yellow":15,"white":16}},
 {"id":"co2l1","unit_id":"co2l","pins":{"yellow":17,"white":18}}]}
JSON
M5_UNIT_CONFIG=/tmp/unit-smoke-config4.json qemu-system-xtensa -M m5atoms3r \
  -L .work/M5StopWatch-QEMU/build/qemu/pc-bios -display none \
  -serial null -serial null -serial null \
  -qmp unix:/tmp/unit-smoke4.sock,server=on,wait=off
# 另一个终端：qom-get/qom-set /machine/units/<id>/<property>
```

21 项检查全部 PASS：rs485-iso 3（属性/空缓冲/未路由 RX 拒绝）、midi 3、laser-tx 2
（默认 output-level=false、只读拒绝）、neco 4（35 灯数组/默认值/按下/释放，
active-low 电平）、co2l 4（默认/chip-id=0x41/量程拒绝/只读拒绝）、tof4m 5
（默认/距离写入/双向越界拒绝/data-ready 写入）。该 smoke **不**覆盖 I2C
`send/recv` 字节语义（SCD4x 命令+CRC、VL53L1X 16-bit 地址/自增）、UART TX 捕获
（离线无 guest UART 路由）、RMT WS2812 帧、GPIO 输出写；这些仍需 guest 证据。

**计数说明**：本分支 base `origin/main 0cd21dab` 的 catalog 为 70 款，加上本批 6 款
后为 **76 款**（catalog 与 runtime-profiles 都是 76）；计数测试、visual mapping
audit（`all-76-products`）与 snapshot 已同步。

共同边界：6 款都是控制器可见的事务/时序模型，不是电气/光学/声学/音频/射频物理
模型；没有 guest 与 Device Service 证据前不得升级为 `implemented`/`simulated`。
