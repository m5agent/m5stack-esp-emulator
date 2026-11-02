# Unit 第六批协议研究：12 款未登记 Unit 的驱动证据、复用建议与 unresolved

日期：`2026-11-02`。范围：`products.json` unit 类别中**尚未登记**的 12 款候选
Unit 的官方页面、官方 UIFlow2 驱动逐行证据、QEMU 复用/新增建议、可断言数据面与
风险。本文件只做研究，不修改 catalog/runtime，不运行 QEMU；catalog 草稿见
`2026-11-02-batch6-catalog-draft.json`，全部 `planned`。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 87 款（82 implemented + 5 planned）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..5-protocols.md`（60 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git HEAD `528edd8`，batch1-5 引用的冻结/快照驱动树）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD `75f1d24`，
  canonical native layer；本批未修改 QEMU）。
- 官方页面在 `2026-11-02` 重新抓取核对（引用见 §8）。

## 0. 结论摘要

本批从剩余**未研究**的 Unit 中选 12 款，覆盖 6 款 I2C、2 款 GPIO/RMT、4 款 UART，
全部可在现有 QEMU 控制器拓扑（SoC I2C、GPIO、RMT、UART）上落地；其中 4 款可
直接复用已实现模型/框架，4 款只需新增寄存器文件或 UART 应答器，2 款需要新的
MCU 协议模型（Thermal2、Unit ID crypto 扩展），1 款依赖固件 C 模块（DMX）。

| # | Unit id | SKU | 总线/地址 | 复杂度 | 推荐优先级 |
| --- | --- | --- | --- | --- | --- |
| 4.1 | `unit-id` | U124 | I2C `0x35`（ATECC608B） | 中高（crypto 扩展） | 中 |
| 4.2 | `mini-scales` | U177 | I2C `0x26` | 中低（寄存器组） | **高** |
| 4.3 | `thermal2` | U149 | I2C `0x32`（页面写 0x33） | 中高（768 帧缓冲） | 中 |
| 4.4 | `env-pro` | U169 | I2C `0x77`（BME688） | 中 | 中 |
| 4.5 | `mini-imu` | U095 | I2C `0x68`（MPU6886） | 低（复用板级模型） | **高** |
| 4.6 | `qrcode` | U173 | I2C `0x21` / UART | 中 | 中 |
| 4.7 | `rgb-led-strip-50cm` | A093 | RMT（30×SK6812） | 低（复用 fader RMT） | **高** |
| 4.8 | `op180` | U058 | GPIO 数字输入（白线） | 低（复用 limit/pir） | **高** |
| 4.9 | `uwb` | U100 | UART（PORT.C，115200） | 中高（AT 应答器） | 中 |
| 4.10 | `dmx` | U183 | UART/RS485（PORT.C，250kbps） | 中（C 模块） | 中 |
| 4.11 | `synth` | U178 | UART（PORT.C，31250，TX-only） | 低（复用 MIDI TX 捕获） | **高** |
| 4.12 | `finger` | U008 | UART（PORT.C，19200） | 中高（FPC1020A 帧） | 中 |

未研究集合的推导：`products.json` 的 184 款 `category=unit` 产品中，86 款与
`platform/units/catalog.json` 的 87 个 id 精确重合（`servo8-hat` 属 HAT 口径差：
catalog 收录但 products unit 列表无对应产品），因此**未登记产品 = 184 − 86 = 98**。
其中 batch5 已研究但尚未登记的 7 款（`pahub-v20`/`rtc`/`tmos-pir`/`neohex`/
`lora-e220-433`/`zigbee`/`nbiot2`）不应重复研究，本批实际从**未研究的 91 款**中
选 12 款。其余未选产品按“passive/无数据面（`proto`/`grove-to-grove` 等）、
摄像头/Linux 模块（`unitv*`/`timerCamera*`/`cams3*`）、SPI 显示/相机（`lcd`/
`oled`/`glass*`）、无官方 Unit 驱动（`hex`/`m5-bit`/`dcssr`/`mq`/`mic` 等）”
留待后续批次；本批不把它们写成 planned。

**最推荐的 5 款**（按“可复用框架 + 可断言数据面 + 冲突可控”排序）：

1. `mini-scales`（U177）— 与已实现 `scales`/`weight-i2c` 的 0x26 寄存器文件同族，
   只需新增 u32 ADC/float weight/button/RGB/校准/滤波字节布局；证据成本最低。
2. `rgb-led-strip-50cm`（A093）— 与已实现 fader/rgb 的 RMT 捕获同构，30 灯；
   只需按 SKU 配 LED 数并复用 `m5_unit_rmt_tx_routed`。
3. `op180`（U058）— 与已实现 `limit`/`pir` 的 GPIO 数字输入模型同构（白线、
   上拉、active-low），无需新 kind；只用 PORT.B。
4. `synth`（U178）— 与 batch4 `midi` 的 UART MIDI TX 捕获完全同构，且 white=NC
   （只发不收）；只需复用 `midi` 模型/探针的 byte-stream 断言。
5. `mini-imu`（U095）— QEMU 已有板级 MPU6886 模型（0x68），把它包成 Unit 传感器
   或新增寄存器夹具即可；MPU6886 寄存器表与 WHO_AM_I 明确。

主要 unresolved/冲突：

- `thermal2`：产品页规格写 **I2C @0x33**，同页 Protocol 表头写 **Addr:0x32**，
  驱动常量 **0x32**；0x33 已被已登记 `thermal`（U016）占用 → 地址二选一 unresolved。
- `mini-scales`：`0x26` 现被 `4relay`/`weight-i2c`/`scales` 三方占用（本批成
  四方冲突）；页面 FAQ 写 “MiniScales Unit uses I2C OR UART”，而驱动只有 I2C 路径；
  固件 v3/v4（v4 去掉 ADC 绝对变化上限，协议不变）需钉版本。
- `qrcode`：I2C/UART 由侧边开关切换，驱动两套路径；I2C 使用 16-bit 寄存器地址 +
  0x1000 数据窗口，QEMU 目前没有 16-bit 指针的通用 Unit slave 封装（VL53L1X
  是首个同类实现，可复用其两字节地址相位）。
- `env-pro`：BME688 `0x77` 空闲，但 `0x76` 备选地址与 `bps`/`env`/`env-iv` 冲突；
  BME68x 校准系数/加热器/IAQ 语义与 BMP280 不同，不能直接把 env 模型当 BME688。
- `unit-id`：现有 QEMU `m5_atecc608.c` 是 Core2-for-AWS 板级最小模型，只实现
  INFO/READ/IDLE 等少量 opcode；Unit ID 需要 RANDOM/GEN_KEY/SIGN/SHA 等命令的
  夹具响应。真实 key/cert/Trust&GO 生命周期 NOT RUN，绝不放入真实私钥。
- `uwb`：AT 命令/响应来自页面与驱动；UWB 3.5–6.5GHz RF/天线/测距精度 NOT RUN，
  页面明确“不支持自定义信息传输”。
- `dmx`：驱动是纯 Python 封装 + `cdriver.esp_dmx` C 模块，QEMU 只能观测 UART
  字节；DMX512/RS485 差分总线、5kVrms 隔离、XLR-3、120Ω 终端 NOT RUN。
- `synth`：SAM2695 只通过 yellow UART RX 接收 MIDI（white=NC）；音频合成/
  NS4150B 功放/扬声器 NOT RUN，31250 波特率来自驱动（页面未写）。
- `finger`：FPC1020A 驱动启动时校验版本仅接受 `B1.10.00`/`B1.07.00`；生物特征
  采集/匹配/150 用户/安全等级 NOT RUN，UART 帧的 XOR 校验可做数据面。
- `rgb-led-strip-50cm`：页面 PinMap 给的是**灯带侧** VCC/GND/DATA（Red/White/
  Green）线色，不是 Grove 转换线映射；`unit/rgb.py` 用 port[1]（yellow）作数据线，
  适配器对应关系 unresolved；30 vs 60/120/300 LED 变体按 SKU 配置。
- `op180`：与 batch5 `op90` 共用 `unit/op.py`，协议完全相同；差别仅在 180° 光学/
  机械，物理链路/遮挡几何 NOT RUN；PORT.B 当前 runtime 未准入（见 §3）。
- 主机侧：当前 host-ports 注册表只把 `cores3 PORT.A` 作为 main-device 端口准入；
  官方 PORT.B/PORT.C 的 12 款中 6 款（rgb strip/op180/uwb/dmx/synth/finger）需
  在后续实现任务里按 batch4/5 的 harness 方式显式记录端口替换，不能默默声称
  官方连接器已验证。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

| 来源 | 固定版本/日期 | 用途 |
| --- | --- | --- |
| `products.json` | 仓库当前 `platform/web/vendor/m5stack-models/catalog/products.json`（`updated=2026-11-01`） | 产品 id/SKU/官方 docs URL/参考图 |
| 官方 UIFlow2 源码 | `.work/uiflow-micropython-public` git HEAD `528edd8` | `m5stack/libs/unit/*.py` 与 `driver/*.py` 逐行协议 |
| 官方产品页面 | `2026-11-02` 抓取（12 页，见 §8） | PinMap、地址、规格、协议表/AT 命令 |
| 已登记契约 | `platform/units/catalog.json`（87 款）、`host-ports.json` | 地址/端口冲突与复用 |
| QEMU 只读 | `.m5-qemu-src/qemu` HEAD `75f1d24`（canonical native layer） | 复用接入点定位（m5_unit_*、m5_atecc608、板级 mpu6886） |

### 1.2 逐款证据等级

- **driver-confirmed**：寄存器/命令表可从官方驱动逐行引用，且有官方页面或
  官方协议表佐证（`mini-scales`、`env-pro`、`mini-imu`、`qrcode`、`rgb-led-strip-50cm`、
  `op180`、`synth`、`finger`）。
- **driver-confirmed-with-page-conflict**：页面与驱动数字/模式不一致，需显式
  unresolved（`thermal2` 0x32 vs 0x33、`mini-scales` I2C OR UART）。
- **driver-confirmed-but-C-module**：Python 驱动存在，但底层是固件 C 模块
  （`dmx` 的 `cdriver.esp_dmx`），QEMU 只能观测 UART 字节。
- **crypto-boundary**：`unit-id` 有官方驱动与协议表，但真实密钥/证书/Trust&GO
  安全语义 NOT RUN，QEMU 只能给确定性夹具响应。

### 1.3 主机侧约定（本批全部适用）

- 本批不运行 QEMU、不修改 `platform/units/*`；所有候选写入 catalog 草稿，
  `model_status=planned`、`runtime.status="unsupported"`。
- GPIO/RMT 类沿用 `host-ports.json` 的端口约定：UIFlow GPIO port tuple 惯例
  `(white, yellow)`；UART 单元驱动构造器为 `UART(id, tx=port[1], rx=port[0])`，
  即 **yellow=host TX/unit RX，white=host RX/unit TX**。
- I2C 类统一 `yellow=SDA, white=SCL`（详见各款 PinMap）。
- 当前 host-ports 只有 cores3 PORT.A 是 main-device 准入；PORT.B/PORT.C 均为
  accessory/限定配置。因此本批 6 款非 PORT.A 单元的实现/证据任务必须显式记录
  “官方连接器 → 实际 harness 端口”的替换（与 batch4/5 一致）。

## 2. 与现有 QEMU 模型的复用映射

以下是只读 QEMU 树（canonical `75f1d24`；主工作树含 0120+ 补丁但本批未改）的
接入点。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c/.h` | `m5_unit_i2c_attach()`、`m5_unit_sensor_supported()`、`m5_unit_control_supported()`、`m5_unit_gpio_supported()`、`m5_unit_extra_supported` | 12 款 id 注册 |
| `m5_unit_i2c_sensors.c` | `UnitSensorKind`/`US_*`、`add_number/add_fixture_int/add_fixture_bool/add_i64/add_u64/add_i2c_address`、`sensor_send/recv` | `thermal2`/`env-pro`/`mini-imu`/`qrcode`（可作 sensor 或新增 control） |
| `m5_unit_i2c_controls.c` | `CONTROL_*`、`snapshot_registers`、`control_send/recv`、寄存器组与地址迁移 | `mini-scales`（0x26 寄存器组）、`unit-id`（ATECC 命令帧） |
| `m5_unit_gpio.c` | `m5_unit_rmt_tx_routed`、`esp32_gpio_set_input`、UART TX 捕获/RX 注入、`led-rgb`/`tx-hex`/`rx-hex` | `rgb-led-strip-50cm`、`op180`、`uwb`/`dmx`/`synth`/`finger` |
| `m5_atecc608.c` | 板级 ATECC608A 最小模型：wake/idle 令牌、command framing、CRC16 poly 0x8005、config 读、Info | `unit-id` 的 framing/CRC 可复用；需扩 RANDOM/GEN_KEY/SIGN/SHA 的夹具响应 |
| 板级 MPU6886 模型 | `m5sw_i2c_devs`/board model 的 `mpu6886`（0x68），含 accel/gyro/whoami 寄存器 | `mini-imu` 可直接包装为 Unit 传感器 |
| 已实现 `scales`/`weight-i2c` | 0x26 寄存器文件（adc/weight/button/led/校准/写入计数） | `mini-scales`（布局不同，需新 kind 或变体） |
| 已实现 `midi` | UART 31250 MIDI byte-stream TX 捕获 `tx-hex` | `synth`（TX-only，white NC） |
| 已实现 `rs485`/`rs485-iso` | UART TX 捕获 + RX 注入；半双工 RS485 边界 | `dmx`（UART 字节层） |
| 已实现 `limit`/`pir` | 白线数字输入 + input-events | `op180`（PORT.B） |

复用原则：GPIO/ADC 走 `esp32_gpio_set_input`/`m5_unit_adc_sample`，RMT 走
`m5_unit_rmt_tx_routed`，UART 走 `m5_unit_uart_tx`/`esp32_uart_inject_rx`，
I2C 在 `I2CSlaveClass.send/recv` 内实现真实字节语义；QOM 只做注入/观测。

## 3. 地址与总线冲突

| 地址 | 本批候选 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x35` | `unit-id`（ATECC608B） | 未占用 | 官方页面；`unit/id.py:15` |
| `0x26` | `mini-scales` | `4relay`/`weight-i2c`/`scales` | 官方页面；`unit/miniscale.py:14` |
| `0x32`（页面 Protocol）或 `0x33`（页面规格） | `thermal2` | `0x33` 被已登记 `thermal`（U016）占用；`0x32` 未占用 | 官方页面；`unit/thermal2.py:11` |
| `0x77` | `env-pro`（BME688） | 未占用；BME68x 备选 `0x76` 与 `bps`/`env`/`env-iv` 冲突 | 官方页面；`unit/envpro.py:16` |
| `0x68` | `mini-imu`（MPU6886） | 未占用（备选 `0x69` 亦未占用） | 官方页面；`unit/imu.py:15` |
| `0x21` | `qrcode` I2C | 未占用 | 官方页面；`unit/qrcode.py:15` |

总线/端口级冲突：

- **UART PORT.C**：`uwb`/`dmx`/`synth`/`finger` 与已登记 `rs485`/`rs485-iso`/
  `midi`/`gps`/`uhf-rfid` 共用；同一 UART 一次只能接一个 Unit。`synth` 的 white
  线为 NC（TX-only），`dmx` 是差分 RS485（Grove 侧仍按 UART 引脚），`finger`
  19200、`uwb` 115200、`synth` 31250 各自波特率不同。
- **GPIO/RMT**：`rgb-led-strip-50cm` 与 `op180` 官方都在 PORT.B（yellow DATA /
  white Digital Output）；当前 runtime 只准入 cores3 PORT.A → 实现时需显式
  harness 替换并记录。
- **I2C 共享**：`mini-scales` 0x26 四方冲突（`4relay`/`weight-i2c`/`scales`）；
  `thermal2` 页面/驱动地址二义（0x32/0x33，后者与 `thermal` 冲突）；
  `env-pro` 0x77 空闲但兼容地址 0x76 冲突。
- `qrcode` 的 I2C 模式用 16-bit 寄存器指针（0x0000/0x0010/0x0020/0x0030/0x0040/
  0x00F0/0x1000），与现有 8-bit 寄存器组模型不同；UART 模式使用 0x21/0x32
  命令帧，二者不可同时建模（侧边开关物理互斥）。

## 4. 各款协议详情

### 4.1 `unit-id` — Unit ID（U124）

**官方**：[Unit ID](https://docs.m5stack.com/en/unit/id)（2026-11-02）；SKU
`U124`；ATECC608B-TNGTLSU-G；I2C `@0x35`（≤1Mbps）；ECC-P256（ECDH/ECDSA）、
SHA256、AES128-GCM；16 个 key slot；10Kb EEPROM；72-bit 唯一序列号；Trust&GO
预置证书（只支持 Microchip Trust Platform）。
**驱动**：`unit/id.py`（122 行）+ `driver/atecc608b_tngtls/atecc.py`（481 行），
git `528edd8`。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令/帧语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/id.py:15`；`atecc.py:31` | `_I2C_ADDR = 0x35` |
| Wake/Idle/Sleep | `atecc.py:131-147` | wake 向地址 0 写 `0x00` + 1.5ms；idle 向 0x35 写 `0x02`；sleep 写 `0x01` |
| 命令包 | `atecc.py:412-438` | `[0x03, count, opcode, param1, param2_L, param2_H, data..., CRC16_L, CRC16_H]`；CRC16 poly `0x8005`，低字节先 |
| 响应 | `atecc.py:439-462` | `[len+3, data..., CRC16_L, CRC16_H]`，CRC 校验失败抛 RuntimeError |
| Opcode | `atecc.py:35-46,47-55` | COUNTER `0x24`、INFO `0x30`、NONCE `0x16`、RANDOM `0x1B`、SHA `0x47`、LOCK `0x17`、GEN_KEY `0x40`、SIGN `0x41`、WRITE `0x12`（count 表见 47-55） |
| 读写 | `atecc.py:386-411` | zone/address 4 或 32 字节读；控制区/数据区写 |

**官方 API**（`unit/id.py`）：`get_revision_number()`、`get_serial_number()`、
`randint/random/randrange/uniform`、`get_generate_key(slot 0–4, private_key)`、
`get_ecdsa_sign(slot, 32B message)`、`get_verify_ecdsa_sign(message, sign, key)`、
`get_sha256_hash(message, format)`、`set_certificate_signing_request(...)`。

**主机输入**：`serial`（72-bit fixture）、`revision`、`random-bytes`（RANDOM 响应）、
`public-key`/`signature`（fixture）、`sha-digest`（固定消息 fixture）、
`slot` 选择。**不允许**真实私钥/证书进入仓库或 QEMU。

**QEMU 建议**：现有 `m5_atecc608.c` 只有板级最小模型（INFO/READ/IDLE 等），
且不是 Unit attachment。两条路：
1. 抽出 `US_ATECC608B` Unit 模型，复用现有 command framing/CRC/wake/config
   代码结构，补 RANDOM/GEN_KEY/SIGN/SHA 的确定性夹具响应；
2. 在 `m5_unit_i2c_controls.c` 新增 control kind，实现 0x03 命令解析 + 响应缓冲。
推荐 1（crypto 语义清晰、与板级模型解耦）；QOM：`serial`/`revision`/
`random-bytes`/`public-key`/`signature`/`sha-digest`/`transactions`/`i2c-address`。

**可断言数据面**：guest `get_serial_number()` 与 72-bit fixture 一致；revision；
`get_sha256_hash()` 与固定消息 fixture 一致；`randint` 落在边界内；
`get_generate_key`/`get_ecdsa_sign` 返回非空 fixture 长度；QOM 事务计数。
**风险/未确认**：真实 ECDSA/AES/Trust&GO 证书链、key slot 锁定/权限、10Kb
EEPROM 内容、物理安全 NOT RUN；QEMU 不得出现真实私钥；0x35 无已登记冲突。

### 4.2 `mini-scales` — Unit Mini Scales（U177）

**官方**：[Unit Mini Scales](https://docs.m5stack.com/en/unit/Unit-Mini%20Scales)
（2026-11-02）；SKU `U177`；STM32F030F4P6 + HX711 + 5kg 称重传感器；I2C `@0x26`；
SK6812 RGB + 功能按键；固件 v3/v4（v4 去掉 ADC 绝对变化上限，协议仍为 v3）；
FAQ 写 “MiniScales Unit (U177) uses I2C OR UART”。
**驱动**：`unit/miniscale.py`（127 行，git `528edd8`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `:27-30` | ADC 原始值 4B **小端 uint32** |
| `0x10` | `:32-37` | 重量 4B **小端 float（克）**；驱动减 `self.tare` |
| `0x20` | `:39-43` | 按键 1B signed；**0=按下**，驱动 `struct.unpack("b")==0` |
| `0x30` | `:49-57` | RGB 3B `[R,G,B]` 写 |
| `0x40` | `:63-89` | 校准 gap 4B float：`(adc2-adc1)/(g2-g1)` |
| `0x50` | `:59-61` | 写 1 重置/去皮（reset weight to zero） |
| `0x80` | `:91-100` | 低通滤波 enable（0/1）读写 |
| `0x81` | `:102-112` | 平均滤波等级 0–50（int8）读写 |
| `0x82` | `:114-125` | EMA alpha 0–99（int8）读写 |

**官方 API**：`adc`、`weight`、`button` 属性；`tare()`、`set_led(r,g,b)`、
`reset()`、`calibration(w1_g,adc1,w2_g,adc2)`、`set/get_low_pass_filter()`、
`set/get_average_filter_level()`、`set/get_ema_filter_alpha()`。

**主机输入**：`adc-raw`（u32）、`weight-g`（float、克）、`button-pressed`、
`calibration-writes`、`filter` 配置。**QOM 输出**：`adc`/`weight-g`/`button`/
`led-rgb`/`calibration-gap`/`reset-writes`/`lpf`/`avg-level`/`ema-alpha`/
`i2c-address`。

**QEMU 建议**：现有 `scales`/`weight-i2c` 都是 0x26 寄存器文件但布局不同
（batch1 scales 使用 2B/4B 等）；新增 `CONTROL_MINISCALE` 或 `scales` 变体：
`read_snapshot` 填 u32 ADC LE / float weight LE / button / RGB / gap float /
lpf / avg / ema / 地址；写路径更新校准/滤波/复位并计数；QOM 夹具反算。
地址 0x26 四方冲突 → 单 bus 只挂一个。

**可断言数据面**：guest `adc`/`weight` 与夹具一致（float 编码精确）；`tare`
只改 guest 侧偏移；按键 0=按下；RGB 写 QOM 回读；`calibration` gap 写入值与
公式一致；reset/LPF/avg/EMA 读写回；QOM 事务计数。
**风险/未确认**：HX711/5kg 载荷/温漂/线性度 NOT RUN；固件 v3/v4 差异（绝对
ADC 变化上限）需钉版本；页面 FAQ “I2C OR UART” 与驱动仅 I2C 冲突 unresolved；
0x26 与 `4relay`/`weight-i2c`/`scales` 冲突；滤波/校准内部实现只按驱动写入断言。

### 4.3 `thermal2` — Unit Thermal2（U149）

**官方**：[Unit Thermal2](https://docs.m5stack.com/en/unit/Thermal2)（2026-11-02）；
SKU `U149`；MLX90640 32×24、110°×75° FOV、-40..300°C；ESP32-PICO-D4 MCU
（高/低温报警、平均/最大/最小、缓存、蜂鸣器、RGB、按键、复位）；I2C。
**页面冲突**：Specifications 写 `I2C @0x33`，同页 Protocol 表头写
`REG MAP (Addr:0x32)`；驱动常量 `THERMAL_CAM_ADDR=0x32`。
**驱动**：`unit/thermal2.py`（544 行，git `528edd8`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `:13,313-321` | 按键状态 bits0–4；写回清标志 |
| `0x01` | `:14,324-326` | 温度报警状态 bitmask |
| `0x04–0x07` | `:15,328-344` | 设备信息：0x40/0x64、major/minor |
| `0x08–0x09` | `:16,346-352` | I2C 地址 / 取反 |
| `0x0A–0x0C` | `:17-19,354-396` | 功能控制 bits0–2、刷新率、噪声滤波 |
| `0x10–0x15` | `:20-24,398-461` | 温度监视窗口、报警使能、蜂鸣器 freq/duty、RGB |
| `0x20/0x30` | `:25-26,464-477` | 低/高温度阈值（2B LE，`(raw-8192)/128`） |
| `0x22/0x32` | `:27-28,479-490` | 低/高报警蜂鸣器频率 |
| `0x24/0x34` | `:29-30,492-500` | 报警间隔（值×10ms） |
| `0x25/0x35` | `:31-32,502-509` | 低/高报警 LED RGB 3B |
| `0x6E/0x6F` | `:33-34,512-521` | 数据刷新控制（写 0 请求新数据）/子页信息 |
| `0x70/0x72/0x74` | `:35-36,523-536` | 中位/平均/差分温度（2B LE，`(raw-8192)/128`） |
| `0x76+` | `:37,538-542` | 差分温度 x/y 位置 |
| `0x80–0x37F` | `:38,544` | 温度数据数组 768×2B LE（32×24） |

**官方 API**：`get_button_state`、`get_temp_alarm_status`、`get_device_detail`、
`get_i2c_addr`、`get/set_func_ctrl`、`get/set_refresh_rate`、`get/set_noise_filter`、
`get/set_temp_monitor`、`set_temp_alarm_ctrl`、`get/set_buzzer_freq`、
`get/set_buzzer_duty`、`set_rgb_led`、`get/set_temp_threshold`、
`get/set_temp_alarm_buzzer_freq`、`get/set_temp_alarm_interval`、
`get/set_temp_alarm_led`、`get_data_refresh_ctrl`、`get_subpage_info`、
`get_temp_measure`、`get_temp_differential`、`get_temp_data_buffer`。

**主机输入**：`temperature-frame`（768×2B raw 数组或 32×24 °C fixture）、
`median/avg/diff-c`、`button-pressed`、`alarm-status`、`refresh-rate`。
**QOM 输出**：`temperature-frame`、`temp-c`（派生）、`button-pressed`、
`alarm-status`、`refresh-rate`、`config`、`transactions`、`i2c-address`。

**QEMU 建议**：新增 `US_THERMAL2`（sensor/control 寄存器文件）：
0x00–0x7F 配置/阈值/报警，0x80–0x37F 768×2B 温度数组；读夹具按公式反算
raw = `round((temp+64)*128)`（注意驱动读回 `(raw-8192)/128`，两者语义相差
64°C 偏移，必须以驱动/页面表格为准）；写路径更新报警/阈值/蜂鸣器/RGB/
刷新控制并计数。现有 `thermal` 模型是 raw MLX90640 协议，不能直接复用；
可复用其 32×24 帧 fixture 生成器。地址 0x32/0x33 二义，实现前必须钉一个。

**可断言数据面**：guest `get_temp_data_buffer` 长度 768 且与夹具逐项一致；
`get_temp_measure(0/1/2)` 与中位/平均/差分夹具一致；阈值/报警/蜂鸣器/LED
写读回；`get_button_state`/`get_temp_alarm_status`；QOM 事务计数。
**风险/未确认**：页面规格 0x33 vs 协议表/驱动 0x32 unresolved（0x33 与
`thermal` 冲突）；页面寄存器表 OCR 有大量笔误，需以驱动为准；热成像光学/
精度/刷新率/报警状态机 NOT RUN；ESP32 MCU 内部缓存语义未建模。

### 4.4 `env-pro` — Unit ENV-Pro（U169）

**官方**：[Unit ENV-Pro](https://docs.m5stack.com/en/unit/Unit_ENV-Pro)（2026-11-02）；
SKU `U169`；BME688；I2C `@0x77`；T/RH/P/气体（VOC/CO₂ 等效/IAQ）；气体扫描
10.8s、湿度 ±3%RH、气压噪声 0.12Pa、温度 ±0.5°C。
**驱动**：`unit/envpro.py`（56 行）+ `driver/bme68x.py`（884 行），git `528edd8`。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/协议（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/envpro.py:16` | `0x77` |
| Chip ID | `bme68x.py:17,55` | `0xD0` = `0x61` |
| Soft reset | `:16` | `0xE0` 写 `0xB6` |
| Variant | `:15` | `0xF0`（gas low/high） |
| Status/meas status | `:14,27` | `0x73`/`0x1D` |
| Config/ctrl | `:18-22` | `0x75 CONFIG`、`0x74 CTRL_MEAS`、`0x72 CTRL_HUM`、`0x70 CTRL_GAS_0`、`0x71 CTRL_GAS_1` |
| 气体加热 | `:23-26` | `0x6E GAS_WAIT_SHARED`、`0x64 GAS_WAIT_0`、`0x5A RES_HEAT_0`、`0x50 IDAC_HEAT_0` |
| 校准系数 | `:29-30` | `0x8A` / `0xE1` 两段 |
| 模式 | `:39-40` | sleep=0、forced=1 |
| 写/读 | `:865-884` | I2C `readfrom_mem_into`/`writeto_mem`，地址按 8-bit 递增写 |
| 默认 | `:196-201` | 温度 oversample=2、压力=5、湿度=1；`set_gas_heater(320,150)`；forced mode |

**官方 API**：`get_temperature()`、`get_humidity()`、`get_pressure()`、
`get_gas_resistance()`（gas/1000）、`get_altitude()`、
`get/set_over_sampling_rate(TEMPERATURE/PRESSURE/HUMIDITY)`、
`get/set_iir_filter_coefficient()`；底层 BME68X：`set_op_mode/get_op_mode`、
`set_tph/get_tph`、`set_gas_heater`、`_read_calibration`/`_read_field_data`、
`temperature/pressure/humidity/altitude/gas` 属性。

**主机输入**：`temperature-c`、`humidity-pct`、`pressure-pa`、`gas-resistance-ohm`、
`altitude-m`、`chip-id`、`variant`、校准系数 fixture；`op-mode`/oversampling 配置。
**QOM 输出**：上述测量值、`chip-id`、`variant`、`transactions`、`i2c-address`。

**QEMU 建议**：新增 `US_BME68X`：实现 0xD0=0x61、0xF0 variant、0xE0 reset、
0x8A/0xE1 校准系数夹具、0x74 forced mode 测量转换与 0x1D 状态位；温度/
压力/湿度/气体/海拔由夹具反算。可直接复用 BMP280 的校准/换算结构，但不能
把 BMP280 的寄存器表当 BME688。`readfrom_mem_into` 与 `writeto_mem` 语义与
现有 sensor 框架一致。

**可断言数据面**：guest `get_temperature/humidity/pressure/altitude` 与夹具
在驱动量化范围内一致；`get_gas_resistance` 与 gas fixture 一致；chip-id 校验
通过；校准系数读轨迹；QOM 事务计数。
**风险/未确认**：BME688 气体/IAQ/加热器/校准真实性 NOT RUN；气体扫描 10.8s
时序与 heater profile 不建模；`0x77` 空闲但 `0x76` 备选与 `bps`/`env`/`env-iv`
冲突；驱动以 `readfrom_mem` 8-bit 地址读写，需钉 SHA。

### 4.5 `mini-imu` — Unit Mini IMU（U095）

**官方**：[Unit Mini IMU](https://docs.m5stack.com/en/unit/imu)（2026-11-02）；
SKU `U095`；MPU6886 6 轴 + 温度；I2C `@0x68`；加速度 ±2/4/8/16g；陀螺
±250/500/1000/2000dps；16-bit ADC、1KB FIFO。
**驱动**：`unit/imu.py`（123 行）+ `driver/mpu6886.py`（193 行），git `528edd8`。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（`driver/mpu6886.py`）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/imu.py:15` | `0x68` |
| CONFIG/GYRO/ACCEL | `mpu6886.py:12-15` | `0x1A CONFIG`、`0x1B GYRO_CONFIG`、`0x1C ACCEL_CONFIG`、`0x1D ACCEL_CONFIG2` |
| 数据寄存器 | `:16-29` | ACCEL X/Y/Z `0x3B-0x40`、TEMP `0x41/42`、GYRO X/Y/Z `0x43-0x48`，均 16-bit BE |
| 电源/ID | `:30-31` | `0x6B PWR_MGMT_1`、`0x75 WHO_AM_I` |
| 量程 | `:33-46` | ACCEL_FS_SEL 2/4/8/16g；GYRO_FS_SEL 250/500/1000/2000dps |
| API | `:91-131` | `acceleration`、`gyro`、`temperature`、`whoami`、`calibrate` |
| 寄存器辅助 | `:149-193` | `_register_short/three_shorts/char`、`_accel_fs/_gyro_fs` |

**官方 API**（`unit/imu.py`）：`get_accelerometer()`（g）、`get_gyroscope()`
（rad/s）、`get_attitude()`（yaw/pitch/roll）、`set_accel_range()`、
`set_gyro_range()`、`set_accel_unit()`、`set_gyro_unit()`、
`set_gyro_calibrate()`、`set_gyro_offsets()`。

**主机输入**：`accel-x/y/z-g`、`gyro-x/y/z-dps`、`temperature-c`、`whoami`。
**QOM 输出**：`accel-*`/`gyro-*`/`temperature`/`whoami`/`transactions`/`i2c-address`。

**QEMU 建议**：现有板级 MPU6886 模型（`m5sw_i2c_devs`/board model 的
`"mpu6886"`，0x68）已含 accel/gyro/whoami 寄存器与夹具；两条路：
1. 新增 Unit id 时把该模型以 Unit attachment 方式挂载（需允许 Unit 引用板级
   器件或复制其寄存器实现）；
2. 在 `m5_unit_i2c_sensors.c` 新增 `US_MPU6886`，寄存器文件 + 夹具。
推荐 2（与现有 Unit sensor 框架一致）；WHO_AM_I 值与位宽取自驱动。

**可断言数据面**：guest `get_accelerometer` 与夹具换算一致（量程/单位）；
`get_gyroscope` 一致；`get_attitude` 在固定夹具下产生确定性角度；`whoami`；
量程写后比例变化；QOM 事务计数。
**风险/未确认**：真实运动/振动/温度/校准 NOT RUN；MPU6886 内部 DMP/FIFO
未建模；0x68 空闲，`0x69` 备选亦空闲；驱动量程常量映射需按驱动逐行核对。

### 4.6 `qrcode` — Unit QRCode（U173）

**官方**：[Unit QRCode](https://docs.m5stack.com/en/unit/Unit-QRCode)（2026-11-02）；
SKU `U173`；640×480 CMOS + STM32F030；侧边开关切 I2C/UART；I2C `@0x21`；
3 种二维码 + 14 种一维码；触发键/蜂鸣器/补光/瞄准。
**驱动**：`unit/qrcode.py`（174 行，git `528edd8`）。

**接线（官方 PinMap）**：

| 模式 | 端口 | Black | Red | Yellow | White |
| --- | --- | --- | --- | --- | --- |
| I2C | PORT.A | GND | 5V | SDA | SCL |
| UART | PORT.C | GND | 5V | UART_RX | UART_TX |

**I2C 寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x0000` W | `:16` | 触发：0 停止连续解码 / 1 开始连续解码（仅手动模式有效） |
| `0x0010` R/W | `:17` | 数据状态：0 not ready / 1 data good / 2 need read again（读后或写 0 清除） |
| `0x0020` R | `:18` | QR 数据长度 2B **小端** |
| `0x0030` W/R | `:19` | 触发模式：0 自动 / 1 手动 |
| `0x0040` R | `:20` | 触发键状态：0 按下 / 1 未按 |
| `0x00FE` R | `:21` | 固件版本 |
| `0x00FF` W/R | `:22` | I2C 地址 |
| `0x1000–0x11FF` R | `:23` | QR 数据缓冲（驱动按长度读） |

**UART 命令帧**：`QRCODE_TX_CONFIG=[0x21,0x61,0x41,0x00]`、
`QRCODE_TX_CONTROL=[0x32,0x75,0x01]`；响应 `[0x22,0x61,0x41,0x00,0x00]`、
`[0x33,0x75,0x02,0x00,0x00]`（`:25-30`）；`cmd_send_resp`/`wait_resp_cmd`
（`:160-174`）。

**官方 API**：`set_manual_scan(ctrl)`、`get_qrcode_data_status()`、
`clear_qrcode_data_status()`、`get_qrcode_data_length()`、`get_qrcode_data(decode)`、
`get/set_trigger_mode()`、`get_trigger_button_status()`、`get_device_info()`、
`set_device_i2c_address()`、`set_event_cb()`、`event_poll_loop()`。

**主机输入**：`qr-data`（字节/字符串 fixture）、`data-status`、`length`、
`trigger-mode`、`button-pressed`、`firmware-version`、`i2c-address`。
**QOM 输出**：`qr-data`、`data-status`、`length`、`trigger-mode`、`button-pressed`、
`fw-version`、`i2c-address`、`transactions`。

**QEMU 建议**：新增 `CONTROL_QRCODE`（或 sensor 变体）：16-bit 寄存器地址
（2B LE 写指针 + 读），数据窗口 0x200B；实现状态/长度/数据/触发模式/按键/
版本/地址迁移。16-bit 地址相位可复用 batch3 `US_VL53L1X` 的两字节地址实现；
I2C 与 UART 模式互斥（侧边开关），QEMU 只建模 I2C 或按配置二选一。

**可断言数据面**：guest 读状态/长度/QR 数据与 fixture 一致；触发模式/手动
扫描写回；按键状态；固件版本/地址；UART 模式可断言命令字节与响应；QOM 事务。
**风险/未确认**：真实摄像头/QR 解码/扫码光学/补光/蜂鸣 NOT RUN；I2C vs UART
侧边开关物理互斥；16-bit 地址与数据窗口需逐字节核对；0x21 无已登记冲突。

### 4.7 `rgb-led-strip-50cm` — Unit RGB LED Strip 0.5m / 30LED（A093）

**官方**：[Unit RGB LED Strip](https://docs.m5stack.com/en/unit/Unit_RGB_LED_Strip)
（2026-11-02）；SKU `A093`（30 LED/0.5m；同系列 A093-B 60、A093-C 120、
A093-D 300）；SK6812 5050；800K/s；单总线可级联；IP65 防水；灯带侧 PinMap
为 VCC/GND/DATA，线色 Red/White/Green。
**驱动**：`unit/rgb.py`（10 行）+ `driver/neopixel/__init__.py`（95 行）+
`driver/neopixel/sk6812.py`，git `528edd8`。

**接线**：官方页面只给灯带侧 VCC/GND/DATA（Red/White/Green）；Grove 转换线
到主机的 data 线映射未在页面写明。UIFlow 驱动 `RGBUnit(port, number)` 使用
**port[1]（yellow）** 作 SK6812 数据线（`unit/rgb.py:8-10`）。

**协议语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 单元封装 | `unit/rgb.py:8-10` | `RGBUnit(port, number)` → `SK6812(port[1], number)`；A093 应为 30 |
| 字节序 | `driver/neopixel/__init__.py:10` | `ORDER=(1,0,2,3)` → 每灯 G,R,B（SK6812 GRB） |
| 时序 | `:12-24` | 800kHz（400/850/800/450ns） |
| 写帧 | `:49-51` | `bitstream(pin,0,timing,buf)` 一次发送整条灯带 |
| 亮度 | `sk6812.py` + `:78-95` | `set_brightness(0-100)` 缩放后重发 |

**官方 API**：`RGBUnit(port, number)` 继承 SK6812/NeoPixel：
`__setitem__/fill/fill_color/set_color/set_brightness/write/color_to_rgb`。

**主机输入**：`led-rgb[30]` fixture、`brightness`、`led-frames`。
**QOM 输出**：`led-rgb[30]`、`led-frames`、`incomplete-frames`、`led-count`。

**QEMU 建议**：复用已实现 fader/rgb 的 RMT 捕获
（`m5_unit_rmt_tx_routed`）：UNIT_GPIO 分支 `leds=30`，从 RMT 符号解码 G/R/B
并 QOM 暴露 `led-rgb`（RGB int）、帧计数。`unit/rgb.py` 的 port[1]=yellow
与 batch5 A035 的 15 灯路径相同，只是 LED 数/产品不同。

**可断言数据面**：guest 写 30 灯颜色后 QOM 逐灯一致；帧计数/无 incomplete；
亮度缩放；SKU LED 数（30 vs 60/120/300）配置。
**风险/未确认**：页面灯带侧线色（Red/White/Green）与 Grove 转换线映射
unresolved；LED 光学/IP65/功率/时序容差 NOT RUN；30 vs 60/120/300 变体需按
SKU 配置；与 batch5 A035 同协议但不同 SKU（不得把 A035 结果直接转授 A093）。

### 4.8 `op180` — Unit OP180（U058）

**官方**：[Unit OP180](https://docs.m5stack.com/en/unit/OP180)（2026-11-02）；
SKU `U058`；180° 非接触光电限位开关（红外发射/接收对射，遮挡输出动作）；
PORT.B。
**驱动**：`unit/op.py`（28 行，git `528edd8`）——与 batch5 `op90` 同一驱动。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`NC`、
White=`Digital Output`（unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 类 | `unit/op.py:11` | `OPUnit(Button)` |
| 构造 | `:12-16` | `Pin(port[0]=white, Pin.IN, PULL_UP)` + `Button(port[0], active_low)` |
| 模式 | `:13-16` | `type=SWITCH`（默认）或 `COUNTER`；COUNTER 时双沿 IRQ 计数 |
| 计数 | `:19-27` | `_cb_irq` 状态变化累加，`count_reset()` 清零 |

**官方 API**：`Button` 的 `pressed/value` + `count_reset()`（COUNTER 模式）。

**主机输入**：`digital-level`（white 线，默认高/未遮挡）、`input-events`。
**QOM 输出**：`output-level`/`pressed`、`input-events`、`transitions`。

**QEMU 建议**：**直接复用**已实现 `limit`/`pir` 的 GPIO 数字输入分支：
`esp32_gpio_set_input(white, !pressed)` + `input-events`；`unit/op.py`
port[0]=white 与官方 PinMap 一致；PORT.B-only。

**可断言数据面**：guest `value()/pressed` 与注入电平一致、双沿计数、
input-events；无 I2C。
**风险/未确认**：180° 光学对射/遮挡几何/响应速度/机械安装 NOT RUN；
`op90`（batch5）已研究同一驱动，本款只差 180° 光学/机械；PORT.B 当前 runtime
未准入（需 harness 替换并记录）；active-low 极性来自驱动默认。

### 4.9 `uwb` — Unit UWB（U100）

**官方**：[Unit UWB](https://docs.m5stack.com/en/unit/uwb)（2026-11-02）；
SKU `U100`；BU01（DW1000）+ STM32F103；AT 命令；串口 115200；3.5–6.5GHz
UWB；定位精度 10cm；anchor/tag 模式；页面明确**不支持自定义信息传输**。
**驱动**：`unit/uwb.py`（143 行，git `528edd8`）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`；驱动 `UART(id, tx=port[1], rx=port[0])`，115200 8N1。

**AT 命令/响应（页面 + 驱动逐行）**：

| 命令 | 证据 | 响应/语义 |
| --- | --- | --- |
| `AT\r\n` | 页面；`unit/uwb.py:54-62` | 探测，`OK` |
| `AT+switchdis=0/1` | 页面；`:100-104` | 关闭/开启测距（仅 tag 模式有效） |
| `AT+interval=5..50` | 页面；`:85-89` | 测距输出间隔（收集点数） |
| `AT+version?` | 页面；`:64-72` | 厂商/模块/版本，`...OK` |
| `AT+RST` | 页面；`:74-83` | 复位，返回 `device:` 行 |
| `AT+anchor_tag=model,ID` | 页面；`:91-98` | model 1=anchor，0=tag；ID 设置 |
| 连续输出 | `:139-143+` | `TAG ID:`/`UWB_RESULT_HEADER` 距离结果 |

**官方 API**：`get_version()`、`reset()`、`set_range_interval()`、`set_mode()`、
`continuous_output_value()`、`at_cmd_send()`、`update_new_value_loop()`、
`get_distance_measure`、`check_device`、`uart_port_id()`。

**主机输入**：`at-response`（按命令返回的 fixture 行）、`distance-measure`
（4 基站距离 fixture）、`anchor-id`、`tag-id`、`mode`。
**QOM 输出**：`at-transcript`、`tx-hex`、`rx-hex`、`distance[4]`、
`device-id`、`transactions`。

**QEMU 建议**：复用 UART TX 捕获/RX 注入（`rs485`/`gps` 同一路径），新增
`US_UWB` AT 应答器：解析 `AT...\r\n`，按 fixture 回 `OK`/`device:`/版本/
距离行；QOM 暴露 `distance[4]`/`device-id`/`at-transcript`。UWB RF/天线/测距
物理不建模。

**可断言数据面**：guest `get_version()`/`check_device` 通过；AT 命令字节与
QOM tx-hex 一致；注入 AT 响应后 guest 解析；`update_new_value_loop` 距离数组
与 fixture 一致；QOM 事务计数。
**风险/未确认**：UWB 3.5–6.5GHz RF/天线/多径/10cm 精度 NOT RUN；
anchor/tag 网络/基站数上限；页面声明不支持自定义数据；固件版本/AT 响应
格式需钉 SHA；PORT.C 与 `dmx`/`synth`/`finger` 及已登记 UART 单元冲突。

### 4.10 `dmx` — Unit DMX（U183）

**官方**：[Unit DMX](https://docs.m5stack.com/en/unit/Unit-DMX)（2026-11-02）；
SKU `U183`；CA-IS3092W 隔离半双工 RS485 收发器（5kVrms）；XLR-3 母座；
120Ω 终端；DMX512 固定 250kbps（最高 500kbps）；Grove 串口。
**驱动**：`unit/dmx.py`（5 行别名）+ `driver/dmx512.py`（143 行），git `528edd8`。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。

**驱动/协议语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 模式常量 | `driver/dmx512.py:37-38` | `DMX_MASTER=1`、`DMX_SLAVE=2` |
| 构造 | `:54-63` | `UART` 由 `cdriver.esp_dmx.dmx_init(port_id, tx, rx, -1, mode)` 接管 |
| 写通道 | `:80-93` | `write_data(channel 1–512, value 0–255)` → `esp_dmx.dmx_write_data` |
| 读通道 | `:95-105` | Slave 模式 `read_data(channel)` |
| 清缓存 | `:107-111` | `esp_dmx.dmx_clear_buffer` |
| 接收线程 | `:118-143` | `attach_channel` + `receive_none_block` 回调 |
| 收/发停止 | `:145-158` | `stop_receive`/`deinit` |

**官方 API**：`write_data()`、`read_data()`、`clear_buffer()`、`deinit()`、
`attach_channel()`、`detach_channel()`、`receive_none_block()`、`stop_receive()`；
构造 `DMX512(id, port, mode=DMX_MASTER)`。

**主机输入**：`rx-hex`（DMX 帧 fixture）、`tx-channel-data`（channel/value）、
`mode`（master/slave）。
**QOM 输出**：`tx-hex`、`rx-hex`、`channels`（512 字节数组）、
`frames`、`transactions`。

**QEMU 建议**：**只复用 UART 字节层**（`m5_unit_uart_tx`/`esp32_uart_inject_rx`）：
guest 的 C 模块 `cdriver.esp_dmx` 在 UART 上发 DMX 帧；QEMU 捕获 TX 字节并注入
RX。QOM 可另建 512 通道数组，由 tx 帧解析填充（若实现愿意解析 DMX 帧）或仅
观测字节。DMX/RS485 差分电气不建模。

**可断言数据面**：guest `write_data(channel, value)` → QOM tx 字节/通道数组；
Slave 注入 `rx-hex` 后 `read_data` 一致；`attach_channel` 回调触发；QOM 帧计数。
**风险/未确认**：DMX512/RS485 差分总线、5kVrms 隔离、XLR-3、120Ω 终端、
250kbps 时序 NOT RUN；`cdriver.esp_dmx` C 模块内部帧格式/中断行为不可见，
QEMU 只能观测 UART 字节；PORT.C 与 UART 单元冲突；master/slave 模式互斥。

### 4.11 `synth` — Unit Synth（U178）

**官方**：[Unit Synth](https://docs.m5stack.com/en/unit/Unit-Synth)（2026-11-02）；
SKU `U178`；SAM2695 音频合成器 + NS4150B 功放；MIDI 标准协议；8Ω@1W 扬声器；
串口通信。
**驱动**：`unit/synth.py`（603 行，git `528edd8`）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`NC`。即 **TX-only**：主机只向 SAM2695 发 MIDI，不接收。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 构造 | `unit/synth.py:139-148` | `Pin(port[0], IN, PULL_UP)`；`UART(id, tx=port[1], rx=port[0])`；31250 8N1 |
| Note on/off | `:150-168` | MIDI `0x90/0x80 | channel` + pitch/velocity |
| 音色/鼓 | `:169-189` | Control Change/Program Change |
| Pitch bend/range | `:190-215` | `0xE0`/RPN |
| 音量/重置 | `:217-252` | Channel/Master volume、GM reset |
| Reverb/Chorus | `:257-327` | 4-byte SysEx 参数 |
| Pan/EQ/Tuning/Vibrate/TVF/Envelope/Scale/Mod | `:329-565` | 对应 MIDI CC/SysEx |
| 写 UART | `:586-591` | `cmd_write(cmd)` → `_uart.write(bytes(cmd))` |

**官方 API**：`set_note_on/off`、`set_instrument`、`set_drums_instrument`、
`set_pitch_bend`/`set_pitch_bend_range`、`midi_reset`、`set_channel_volume`、
`set_all_notes_off`、`set_master_volume`、`set_reverb`、`set_chorus`、`set_pan`、
`set_equalizer`、`set_tuning`、`set_vibrate`、`set_tvf`、`set_envelope`、
`set_scale_tuning`、`set_mod_wheel`、`set_all_drums`、`cmd_write`、`map`。

**主机输入**：无（TX-only）；`tx-midi-commands` 由 guest 侧调用产生。
**QOM 输出**：`tx-hex`、`written-bytes`、`transactions`。

**QEMU 建议**：复用 batch4 `midi` 的 UART TX 捕获（`tx-hex` +
`written-bytes`）；不同点：`synth` 的 white=NC，**不建模 RX/注入**；UART
31250（与 midi 相同）。QOM `tx-hex` 断言 note on/off/CC/SysEx 字节流即可。

**可断言数据面**：guest `set_note_on/off`、`set_instrument`、`set_reverb` 等
产生的 MIDI 字节流与 QOM `tx-hex` 一致；`written-bytes` 计数；无 I2C 事务。
**风险/未确认**：SAM2695 合成音频/音色/复调/NS4150B 功放/扬声器 NOT RUN；
TX-only（white NC 不得注入 RX）；31250 来自驱动（页面未写）；PORT.C 与
`uwb`/`dmx`/`finger` 冲突。

### 4.12 `finger` — Unit Finger（U008）

**官方**：[Unit Finger](https://docs.m5stack.com/en/unit/finger)（2026-11-02）；
SKU `U008`；FPC1020A 电容式指纹模块；UART 默认 **19200 8N1**（9600–115200）；
150 用户容量；安全等级 0–9（默认 5）；特征值 193B；PORT.C。
**驱动**：`unit/finger.py`（15 行）+ `driver/fpc1020a/fpc1020a/api.py`
（490 行）+ `types.py`，git `528edd8`。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`；驱动 `UART(id, 19200, tx=port[1], rx=port[0])`。

**UART 帧协议（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 帧定界 | `api.py:95-96` | `_START=0xF5`、`_END=0xF5` |
| 发送帧 | `api.py:429-433` | `[0xF5, cmd, data..., checksum(XOR), 0xF5]` |
| 接收帧 | `api.py:447-520` | `0xF5 ... 0xF5`，XOR checksum 校验 |
| Checksum | `api.py:508-520` | 所有字节 XOR |
| ACK 码 | `api.py:98-110` | 0x00 success、0x01 fail、0x04 full、0x05 nouser、0x06 occupied、0x07 exist、0x08 timeout、0x09 resend |
| 版本门 | `api.py:110-120` | 构造时 `get_version()` 仅接受 `B1.10.00`/`B1.07.00`，否则 RuntimeError |
| Command ID | `api.py:24-44` | SLEEP 0x2C、ADD_MODE 0x2D、ADD_1/2/3 0x01/02/03、DELETE_USER 0x04、DELETE_ALL 0x05、GET_USER_CNT 0x09、GET_USER_PERMISSIONS 0x0A、MATCH_1 0x0B、MATCH_N 0x0C、CAPTURE_CHAR 0x23、CAPTURE_RAW 0x24、GET_VERSION 0x26、MATCH_LEVEL 0x28、GET_USER_INFO 0x2B、GET_USER_CHAR 0x31、UPLOAD_USER_INFO 0x41、UPLOAD_CHAR 0x44、GET_UNREGISTERED_ID 0x47 |

**官方 API**：`sleep()`、`get/set_add_mode()`、`add_user(id, permission)`、
`delete_user`、`delete_all_user`、`get_user_count`、`get_user_capacity`、
`compare_id`、`get_version`、`capture_characteristic`、`capture_raw_image`、
`get_user_info`、`get_user_characteristic`、`upload_user_info`、
`upload_characteristic`、`get_unregistered_user_id`、`set_match_level` 等
（具体以驱动 `api.py` 为准）。

**主机输入**：`response-frames`（按命令的 fixture 响应帧）、`user-count`、
`version`、`match-result`、`finger-present`。
**QOM 输出**：`tx-hex`、`rx-hex`、`frames-sent`、`frames-injected`、
`user-count`、`version`、`transactions`。

**QEMU 建议**：复用 UART TX 捕获/RX 注入，新增 `US_FPC1020A` 帧应答器：
检测 0xF5 起止帧、校验 XOR、按 command 回 fixture 帧（版本/用户数/匹配结果）；
QOM 暴露 `tx-hex`/`rx-hex`/`frames-*`/`user-count`/`version`。生物特征采集/
匹配不建模。

**可断言数据面**：guest 构造时 `get_version` 通过（版本 fixture 必须为
B1.10.00/B1.07.00）；`get_user_count`/`compare_id` 与 fixture 一致；
发送帧的 XOR checksum 正确；注入响应帧被 guest 解析；QOM 帧计数。
**风险/未确认**：FPC1020A 指纹采集/匹配/安全等级/150 用户/193B 特征/防伪
NOT RUN；固件版本门（仅两个版本字符串）；UART 19200 与 PORT.C 冲突；
帧长/超时/重发语义需按驱动核对。

## 5. 未确认项汇总（unresolved）

1. `unit-id`：真实 ECDSA/AES/Trust&GO 证书链/密钥槽锁定/10Kb EEPROM NOT RUN；
   QEMU 现有 ATECC 模型只覆盖 framing/CRC/config/Info，需扩 RANDOM/GEN_KEY/
   SIGN/SHA 夹具；不得出现真实私钥。
2. `mini-scales`：0x26 与 `4relay`/`weight-i2c`/`scales` 四方冲突；固件 v3/v4
   （ADC 绝对变化上限）需钉版本；页面 FAQ “I2C OR UART” 与驱动仅 I2C 冲突；
   HX711/5kg/温漂 NOT RUN。
3. `thermal2`：页面规格 **0x33** vs Protocol 表/驱动 **0x32** unresolved
   （0x33 与已登记 `thermal` 冲突）；页面寄存器表 OCR 笔误多，需以驱动为准；
   热成像光学/精度/刷新/报警状态机 NOT RUN。
4. `env-pro`：BME688 气体/IAQ/加热器/校准真实性 NOT RUN；`0x77` 空闲但
   `0x76` 备选与 `bps`/`env`/`env-iv` 冲突；不能把 BMP280 表当 BME688。
5. `mini-imu`：真实运动/振动/温度/DMP/FIFO NOT RUN；板级 MPU6886 模型
   与 Unit attachment 的接入方式未定。
6. `qrcode`：摄像头/QR 解码/扫码光学/补光/蜂鸣 NOT RUN；I2C vs UART 侧边
   开关互斥；16-bit 地址/0x1000 数据窗口需逐字节核对；0x21 无冲突。
7. `rgb-led-strip-50cm`：页面灯带侧线色（Red/White/Green）与 Grove 转换线
   映射 unresolved；30/60/120/300 变体按 SKU；光学/IP65/功率 NOT RUN；
   与 batch5 A035 协议相同但 SKU 不同，不得转授。
8. `op180`：180° 光学/机械/遮挡几何 NOT RUN；与 batch5 op90 共用驱动；
   PORT.B 当前 runtime 未准入。
9. `uwb`：UWB 3.5–6.5GHz RF/天线/测距精度/anchor-tag 网络 NOT RUN；页面
   声明不支持自定义数据；AT 固件版本需钉 SHA；PORT.C 冲突。
10. `dmx`：DMX512/RS485 差分/5kVrms 隔离/XLR-3/120Ω/250kbps NOT RUN；
    `cdriver.esp_dmx` C 模块不可见，QEMU 只能观测 UART 字节；PORT.C 冲突。
11. `synth`：SAM2695 合成/音频/NS4150B/扬声器 NOT RUN；TX-only（white NC）；
    31250 来自驱动；PORT.C 冲突。
12. `finger`：FPC1020A 生物采集/匹配/安全等级/150 用户 NOT RUN；版本门仅
    接受 B1.10.00/B1.07.00；UART 帧长/超时/重发需逐字节核对；PORT.C 冲突。
13. 通用：本地官方源码 HEAD `528edd8`（batch1-5 同一快照），master 差异未
    复核；页面/驱动版本敏感项需在实现时钉 SHA；host-ports 只准入 cores3
    PORT.A，PORT.B/C 需 harness 替换并显式记录。

## 6. 驱动版本交叉核对

- 本地官方源码树 HEAD `528edd8`（`Enable unicode24 font.`），与 batch1-5
  文档引用一致；本批 12 款驱动文件 SHA-256 见下表。
- 本批未抓取 GitHub master 逐字节对比；页面/驱动冲突已显式标 unresolved
  （thermal2 0x32/0x33、mini-scales I2C/UART、qrcode 双模式等）。

| 驱动文件 | 行数 | SHA-256（前 16） |
| --- | --- | --- |
| `unit/id.py` | 122 | `a7053ccdaf2ee50d` |
| `unit/miniscale.py` | 127 | `1dce2237a99df575` |
| `unit/thermal2.py` | 544 | `7c676c88f93454d5` |
| `unit/envpro.py` | 56 | `1f525793ddd86bb9` |
| `unit/imu.py` | 123 | `323a6c96b5db132c` |
| `unit/qrcode.py` | 174 | `13a425acf41568a4` |
| `unit/rgb.py` | 10 | `68b3a4424e4d0d62` |
| `unit/op.py` | 28 | `dc9f5ce452530694` |
| `unit/uwb.py` | 143 | `7e30b06ead09d266` |
| `unit/dmx.py` | 5 | `612b66705ce692a3` |
| `unit/synth.py` | 603 | `18dc58029382b709` |
| `unit/finger.py` | 15 | `d95aa2a0dabe5880` |
| `driver/atecc608b_tngtls/atecc.py` | 481 | `6c4358ef03682f15` |
| `driver/bme68x.py` | 884 | `6131a58eeb525250` |
| `driver/mpu6886.py` | 193 | `10223a4e1a2a8966` |
| `driver/dmx512.py` | 143 | `fc88845a950d5bf5` |
| `driver/fpc1020a/fpc1020a/api.py` | 490 | `2585a50ac820f1b7` |
| `driver/neopixel/__init__.py` | 95 | `f1995e9fa025330b` |
| `driver/neopixel/sk6812.py` | 59 | `b316cbebf49a5a45` |

## 7. 落地顺序建议

1. **批次 A（低风险，先做）**：`mini-scales`、`rgb-led-strip-50cm`、`op180`、
   `synth`。前三款直接复用已实现寄存器组/GPIO/RMT 框架，`synth` 复用 batch4
   MIDI TX 捕获；每款 1 个 session 即可取证。
2. **批次 B（传感器寄存器组）**：`mini-imu`、`env-pro`。`mini-imu` 可复用
   板级 MPU6886 夹具；`env-pro` 需新增 BME68x 校准/forced mode 模型。
3. **批次 C（复杂寄存器/协议）**：`mini-scales` 若 A 未做可并入；`qrcode`
   （16-bit 地址 + 0x1000 数据窗口）、`thermal2`（768×2B 帧缓冲 + 地址二义）。
4. **批次 D（UART 应答器）**：`uwb`、`dmx`、`finger`。三者共享 UART TX/RX
   路径；`dmx` 只能断言 UART 字节（C 模块），`finger` 需 XOR 帧应答器，
   `uwb` 需 AT 应答器。
5. **crypto**：`unit-id` 单独任务；先扩 QEMU ATECC 夹具（RANDOM/GEN_KEY/
   SIGN/SHA），明确不得使用真实密钥/证书。

## 8. 官方来源清单

产品页面（2026-11-02 抓取）：

- https://docs.m5stack.com/en/unit/id
- https://docs.m5stack.com/en/unit/Unit-Mini%20Scales
- https://docs.m5stack.com/en/unit/Thermal2
- https://docs.m5stack.com/en/unit/Unit_ENV-Pro
- https://docs.m5stack.com/en/unit/imu
- https://docs.m5stack.com/en/unit/Unit-QRCode
- https://docs.m5stack.com/en/unit/Unit_RGB_LED_Strip
- https://docs.m5stack.com/en/unit/OP180
- https://docs.m5stack.com/en/unit/uwb
- https://docs.m5stack.com/en/unit/Unit-DMX
- https://docs.m5stack.com/en/unit/Unit-Synth
- https://docs.m5stack.com/en/unit/finger

官方驱动（`https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/`，
本地固定 SHA 见 §6）：`unit/id.py`、`unit/miniscale.py`、`unit/thermal2.py`、
`unit/envpro.py`、`unit/imu.py`、`unit/qrcode.py`、`unit/rgb.py`、`unit/op.py`、
`unit/uwb.py`、`unit/dmx.py`、`unit/synth.py`、`unit/finger.py`、
`driver/atecc608b_tngtls/atecc.py`、`driver/bme68x.py`、`driver/mpu6886.py`、
`driver/dmx512.py`、`driver/fpc1020a/fpc1020a/api.py`、`driver/neopixel/*`。

产品目录/地址索引：`platform/web/vendor/m5stack-models/catalog/products.json`；
官方 I2C 地址总表：https://docs.m5stack.com/en/product_i2c_addr 。

## 9. 复现方式

```bash
# 本文档只读、不运行 QEMU；在 worktree 内校验 docs/索引/snapshot：
cd /Users/m5agent/Documents/ChatGPT/esp-emulator-unit6
python3 -m unittest discover -s platform/tests -p 'test_docs_index_contract.py'
python3 platform/tools/project_snapshot.py --check

# 复核驱动 SHA/行号（本地官方源码树，HEAD 528edd8）
cd /Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public/m5stack/libs
sha256sum unit/id.py unit/miniscale.py unit/thermal2.py unit/envpro.py unit/imu.py \
  unit/qrcode.py unit/rgb.py unit/op.py unit/uwb.py unit/dmx.py unit/synth.py \
  unit/finger.py driver/atecc608b_tngtls/atecc.py driver/bme68x.py \
  driver/mpu6886.py driver/dmx512.py driver/fpc1020a/fpc1020a/api.py
```

## 10. catalog 草稿说明

`2026-11-02-batch6-catalog-draft.json` 包含 12 条 **planned** 草稿，字段与
`platform/units/catalog.json` 的既有条目同形（`id/name/sku/visual_asset/
official_docs/checked_at/chips/interface/protocol/inputs/outputs/evidence/
research_status/model_status/runtime/blocker/limitations`）。草稿仅提案：

- `model_status="planned"`、`runtime.status="unsupported"`，
  `runtime.required_data_plane` 描述预期数据面；
- 不写 `simulated`、不写 functional PASS；
- 地址/端口冲突与 unresolved 均写入 `blocker`/`limitations`；
- 合并进 `platform/units/catalog.json` 前需要另行任务（本批只研究，不修改
  catalog/runtime/tests）。

## 11. 首批 6 款实现状态（补丁 0140，2026-11-02）

batch6 首批 6 款（`mini-scales`/`rgb-led-strip-50cm`/`op180`/`synth`/`mini-imu`/
`env-pro`）已由
[`0140-unit-batch6a.patch`](../../patches/qemu-m5stack-peripherals/0140-unit-batch6a.patch)
接入 QEMU 数据面。**base 是 20 层 canonical 链 `96b68ae`**（canonical `75f1d24`
+ `0120…0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132` →
`0137` → `0138` → `0139`），实现 commit `f177808`。**尚未采集 guest/Device Service
证据**，catalog 6 条与 runtime-profiles 6 条保持 `planned`、hosts 为空；离线 QOM
smoke（S3 board、无 guest 固件）只验证属性注册、fixture 读写、范围/只读拒绝、
30 灯数组与寄存器机默认值（18/18 PASS），不构成功能 PASS。

| Unit | 0140 模型 | QOM fixtures/观测 | 显式 blocker/unresolved |
| --- | --- | --- | --- |
| `mini-scales` U177 (0x26) | `CONTROL_MINISCALE`：u32 LE ADC 0x00、float LE weight 0x10、signed button 0x20（0=按下）、RGB 0x30、校准 gap float 0x40、reset/去皮 0x50、LPF/avg/EMA 0x80/0x81/0x82、fw/地址 | adc-raw、weight-g、button、calibration-gap、reset-writes、calibration-writes、lpf、avg-level、ema-alpha、i2c-address | **HX711/5kg 载荷/温漂/线性度 NOT RUN；v3/v4 固件差异需钉版本；页面“I2C OR UART”与驱动仅 I2C 冲突 unresolved；0x26 与 4relay/weight-i2c/scales 四方冲突** |
| `rgb-led-strip-50cm` A093 (RMT) | GPIO id：黄线 RMT 捕获 30×SK6812 帧 | led-rgb[30]、led-frames、incomplete-frames、output-transitions | **页面只给灯带侧 VCC/GND/DATA 线色，Grove 适配器数据线映射 unresolved；A093 vs A093-B/C/D（60/120/300）变体不建模；LED 光学/IP65/功率/时序容差 NOT RUN；PORT.B 主机限制** |
| `op180` U058 (GPIO) | GPIO id（与 op90 共用事务模型）：白线数字输入 input-level + active-low blocked；黄线 NC | digital-level、blocked、input-events | **180° 光学/对射几何/响应/机械安装 NOT RUN；极性来自共享驱动默认；PORT.B 主机限制；OP90 与 OP180 是不同产品，结果不可互相转授** |
| `synth` U178 (UART) | GPIO id：仅 TX 捕获 31250 MIDI 字节流；white=NC，不建模 RX/注入 | tx-hex、written-bytes、transactions | **SAM2695 音频/音色/复调/NS4150B 功放/扬声器 NOT RUN；TX-only 不得注入 RX；31250 来自驱动（页面未写）；PORT.C 冲突** |
| `mini-imu` U095 (0x68) | `US_MPU6886`：WHO_AM_I=0x19、accel/gyro/temp 数据寄存器由 fixture 按驱动比例因子反算（16384/8192/4096/2048、131/62.5/32.8/16.4）、0x1B/0x1C 量程写、地址迁移 | accel-x/y/z-g、gyro-x/y/z-dps、temperature-c、accel-range、gyro-range、whoami、i2c-address | **真实运动/振动/温度/校准 NOT RUN；DMP/FIFO 不建模；0x68 无已登记冲突（0x69 备选未实现）** |
| `env-pro` U169 (0x77) | `US_BME68X`：CHIP_ID 0x61、variant、软复位 0xB6、CTRL/STATUS/校准寄存器存储、0x1D 起 17B 合成 field data | temperature-c、humidity-pct、pressure-pa、gas-resistance-ohm、data-ready、chip-id、variant、i2c-address | **BME688 气体/IAQ/加热器/10.8s 扫描 NOT RUN；BME68x 补偿逆运算未建模 → guest 温/湿/压解码不可断言，field bytes 为合成；仅实现默认 0x77，备选 0x76 与 bps/env/env-iv 冲突；0x77 无已登记冲突** |

离线 QOM smoke 复现（S3 `m5atoms3r`，无 guest；6 attachment 一次启动）：

```bash
cat > /tmp/unit-smoke-config9.json <<'JSON'
{"schema_version":1,"attachments":[
 {"id":"ms1","unit_id":"mini-scales","pins":{"yellow":15,"white":16}},
 {"id":"strip1","unit_id":"rgb-led-strip-50cm","pins":{"yellow":21,"white":38}},
 {"id":"op1801","unit_id":"op180","pins":{"yellow":9,"white":10}},
 {"id":"synth1","unit_id":"synth","pins":{"yellow":11,"white":12}},
 {"id":"imu1","unit_id":"mini-imu","pins":{"yellow":17,"white":18}},
 {"id":"envpro1","unit_id":"env-pro","pins":{"yellow":5,"white":6}}]}
JSON
M5_UNIT_CONFIG=/tmp/unit-smoke-config9.json qemu-system-xtensa -M m5atoms3r \
  -L .work/M5StopWatch-QEMU/build/qemu/pc-bios -display none \
  -serial null -serial null -serial null \
  -qmp unix:/tmp/unit-smoke9.sock,server=on,wait=off
# 另一个终端：qom-get/qom-set /machine/units/<id>/<property>
```

18 项检查全部 PASS：mini-scales 3（默认/fixture 写入/范围拒绝）、
rgb-led-strip-50cm 2（30 灯/帧计数）、op180 2（默认/遮挡）、synth 2（默认/
无 RX 拒绝）、mini-imu 5（默认/fixture/量程/非法量程拒绝/WHO_AM_I 只读）、
env-pro 4（默认/fixture/范围拒绝/CHIP_ID 只读）。smoke **不**覆盖 I2C
send/recv 字节语义（Mini Scales 寄存器、MPU6886 数据寄存器、BME688 页/校准）、
RMT 30 灯帧、UART TX 捕获；这些仍需 guest 证据。

**计数**：catalog 94 → **100**、runtime-profiles 94 → 100；visual mapping audit
6 条 + `all-100-products`；计数测试与 snapshot 已同步。

## 12. 剩余 6 款实现状态（补丁 0142，2026-11-02）

batch6 剩余 6 款（`unit-id`/`thermal2`/`qrcode`/`uwb`/`dmx`/`finger`）已由
[`0142-unit-batch6b.patch`](../../patches/qemu-m5stack-peripherals/0142-unit-batch6b.patch)
接入 QEMU 数据面。**base 是 22 层 canonical 链 `94b6298`**（canonical `75f1d24`
+ `0120…0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132` →
`0137` → `0138` → `0139` → `0140` → `0141`），实现 commit `eb4ce0c`。**尚未采集
guest/Device Service 证据**，catalog 6 条与 runtime-profiles 6 条保持 `planned`；
离线 QOM smoke（S3 board、无 guest 固件）15/15 PASS，不构成功能 PASS。

| Unit | 0142 模型 | QOM fixtures/观测 | 显式 blocker/unresolved |
| --- | --- | --- | --- |
| `unit-id` U124 (0x35) | `US_ATECC608B`：0x03 命令帧解析、CRC16(poly 0x8005) 响应帧；INFO revision/serial、RANDOM、SHA、GEN_KEY、SIGN、NONCE 返回**固定非秘密测试向量** | revision、transactions、i2c-address | **真实 ECDSA/AES-GCM/Trust&GO 证书链/key slot 锁定/权限/10Kb EEPROM NOT RUN；wake-to-address-0/idle/sleep 未建模；仓库与 QEMU 不含任何真实私钥/证书；0x35 无已登记冲突** |
| `thermal2` U149 (0x32) | `US_THERMAL2`：按键/报警/设备信息/功能/刷新/阈值/蜂鸣器/RGB 寄存器、中位/平均/差分温度、768×2B 温度数组（raw=temp*128+8192，驱动解码） | median-c、average-c、differential-c、button-pressed、alarm-status、refresh-rate、fw-version、i2c-address | **页面 0x33 vs 协议表/驱动 0x32 二义 unresolved（0x33 与已登记 thermal 冲突，只实现 0x32）；热成像光学/精度/刷新/报警状态机 NOT RUN；ESP32 内部缓存语义不建模** |
| `qrcode` U173 (0x21) | `US_QRCODE`：2 字节小端地址窗口、状态/长度/触发模式/按键/固件/地址寄存器、0x1000–0x11FF QR 数据窗口 | data-status、trigger-mode、button-pressed、fw-version、i2c-address | **摄像头/扫码光学/补光/瞄准/解码 NOT RUN；I2C/UART 侧开关物理互斥、只实现 I2C 侧；UART 命令帧未在该 attachment 建模；0x21 无已登记冲突** |
| `uwb` U100 (UART) | GPIO id：UART 捕获 + idle-time fixture 应答器（不解析 AT/UWB 语义） | responses-hex、tx-hex、frames-sent/injected | **UWB 3.5–6.5GHz RF/天线/多径/10cm 精度/基站网络 NOT RUN；页面明确不支持自定义数据传输；AT/固件响应格式需钉 SHA；PORT.C 端口冲突** |
| `dmx` U183 (UART) | GPIO id：仅 UART 字节观测/注入（cdriver.esp_dmx C 模块不可执行，不解析 DMX 帧） | responses-hex、tx-hex、frames-sent/injected | **DMX512/RS485 差分总线/5kVrms 隔离/XLR-3/120Ω/250kbps 时序 NOT RUN；C 模块帧格式/中断不可见；master/slave 互斥未区分；PORT.C 端口冲突** |
| `finger` U008 (UART) | GPIO id：UART 捕获 + idle-time fixture 应答器（不解析 0xF5/XOR 帧语义） | responses-hex、tx-hex、frames-sent/injected | **指纹采集/匹配/安全等级/150 用户/193B 特征/防伪 NOT RUN；版本门 B1.10.00/B1.07.00 需 fixture 满足；XOR/ACK 语义未解码；PORT.C 端口冲突** |

离线 QOM smoke（S3 `m5atoms3r`，无 guest）15 项 PASS：unit-id 2（默认/只读拒绝）、
thermal2 3（默认/fixture/范围拒绝）、qrcode 4（默认/触发模式/状态/非法状态拒绝）、
uwb 2、dmx 2、finger 2（默认/响应 fixture）。smoke **不**覆盖 I2C send/recv 字节
语义（ATECC 命令/CRC、Thermal2 数组、QRCode 地址窗口）、UART 应答器 idle 时序；
这些仍需 guest 证据。

**计数**：catalog 100 → **106**、runtime-profiles 100 → 106；visual mapping audit
6 条 + `all-106-products`；计数测试与 snapshot 已同步。
