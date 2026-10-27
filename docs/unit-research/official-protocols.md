# 外部 Unit 官方协议研究

核对日期：`2026-10-26`。

本页覆盖视觉资产目录的全部 27 款 Unit。视觉资产的 `modeled` 只说明外观；本批
机器契约在 [`platform/units/catalog.json`](../../platform/units/catalog.json)，
主机端口在 [`host-ports.json`](../../platform/units/host-ports.json)。研究文件不改变
`platform/peripherals/catalog.json` 的现有板载外设结论。

本页保留实现前的协议研究范围，不维护当前运行状态。最初契约曾将
`model_status` 记为 `planned`、`runtime.status` 记为 `unsupported`；后续实现和
验证已推进，当前准入以 `platform/units/runtime-profiles.json` 和
[项目当前状态](../project-status.md)为准。`confirmed-contract` 只表示已有官方
产品和驱动依据，不能独自授予寄存器实现完整、虚拟设备 PASS 或真机 PASS。

## 取证与字段约定

先通过 m5stack-assistant 的 `knowledge_search` 查询每个产品，再读取官方产品网页
和 `m5stack/uiflow-micropython` 源码。部分 MCP 查询发生 30 秒超时；随后用官方网页
和 GitHub 原文继续核对。未把无关检索结果当产品证据。驱动来源 URL、读取日期和
SHA-256 写入机器契约；产品页链接出的 datasheet/原理图若没有逐页阅读，明确标记为
`linked-by-verified-product-page`，不会据此声称已经核对其全部内容。

- 接口严格用 `yellow`、`white`、`red`、`black` 颜色命名。官方网页的颜色表与部分
  原理图 J1 的数字编号表现不同，本批不从颜色推断连接器 pin 1/2。
- UIFlow GPIO `port` tuple 通常是 `(white, yellow)`；`port[0]` 不能直接理解为
  Grove 黄色线。I2C 使用显式 SDA/SCL GPIO，不能复用 GPIO tuple 次序推断。
- `inputs` 是外部世界/测试 fixture 状态，需要经过 SoC 控制器和设备模型送入 guest。
  `outputs` 是 guest 驱动外设后的只读观测。它们都不是直接覆盖 guest Python API
  返回值的接口。
- 每项状态用 object 描述 `type`、`unit`、`minimum/maximum`（已确认时）、`default`
  和 `readOnly`。所有 default 均是合成的 UI/测试初值，未声称为实物出厂默认值。
- 红线 `5V` 是所引官方 PinMap 的供电标签；它不表示 GPIO 逻辑电平是 5V。未确认的
  电平阈值、供电控制和最大电流继续保留未知。
- `runtime.qom_path_template` 为 `/machine/units/{attachment_id}`；`properties` 显式
  记录属性与读写方向。实际已实现支持清单以 runtime backend 的能力发现为准。

## 主机物理口路由

下表只列与当前主模型 `visual_port=grove` 对应的首个确认口。可选 base/dock 的 B/C
口单独保留为条件口、`visual_port=null`，不自动显示成主机自带插座。引脚已确认不
代表 QEMU 已路由到该 GPIO、ADC、UART 或 I2C bus。

| 主机 | 明确 port_id | Yellow | White | 电源 | 官方来源 |
| --- | --- | --- | --- | --- | --- |
| `sticks3` | `custom` | G9 | G10 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/StickS3) |
| `cores3` | `port-a` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/CoreS3) |
| `stopwatch` | `port-a` | G10 | G11 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/StopWatch) |
| `cardputer-adv` | `custom` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/Cardputer-ADV) |
| `cardputer-zero` | 未确认 | 未确认 | 未确认 | 未确认 | [原始产品入口](https://docs.m5stack.com/en/core/CardputerZero) |
| `papermono` | 未确认 | 未确认 | 未确认 | 未确认 | [原始产品入口](https://docs.m5stack.com/en/core/PaperMono) |
| `core2` | `port-a` | G32 | G33 | red 5V / black GND | [PinMap](https://docs.m5stack.com/zh_CN/core/Core2_v1.1) |
| `papercolor` | `port-a` | G4 | G5 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/PaperColor) |
| `nanoc6` | `custom` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/NanoC6) |
| `stackchan` | `port-a` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/StackChan) |
| `tab5` | `port-a` | G53 | G54 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/Tab5) |
| `atoms3r` | `custom` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/AtomS3R) |
| `nesso-n1` | `port-a` | G5 | G4 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/Arduino_Nesso_N1) |
| `stamplc` | `port-a` | G2 | G1 | red 5V / black GND | [PinMap](https://docs.m5stack.com/en/core/StamPLC) |

Core2 Port B 的 white=GPIO36 只能输入。Core2/CoreS3/StackChan 的非主口，及 StamPLC
Port C，只有官方 GPIO 表的路由已确认；本次没有把附件配置当成当前视觉模型的实体口。
PaperMono 的现行产品页和所选外壳未给出外部 Grove 口映射；CardputerZero 的原始官方
产品 URL 返回 404，且它属于独立 Linux ARM64 后端，两个目标都不臆造 GPIO。

## 27 款协议总览

| Unit / SKU | 芯片或器件 | 总线 / 地址 | 主要方向与状态 |
| --- | --- | --- | --- |
| ENV III / `U001-C` | SHT30, QMP6988 | `i2c` 0x44, 0x70 | 输入 `temperature-c`, `humidity-pct`, `pressure-pa`；输出 — |
| PIR / `U004` | AS312, HT7533 | `gpio`  | 输入 `motion`；输出 — |
| Ultrasonic-I2C / `U098-B1` | RCWL-9620 | `i2c` 0x57 | 输入 `distance-mm`；输出 — |
| RGB LED / `U003` | SK6812 x3 | `gpio-rmt`  | 输入 —；输出 `led-rgb` |
| Angle / `U005` | 10k ohm potentiometer | `adc`  | 输入 `voltage-mv`；输出 — |
| Color / `U009` | TCS3472 family (schematic TCS34725FN) | `i2c` 0x29 | 输入 `clear-raw`, `red-raw`, `green-raw`, `blue-raw`；输出 — |
| ToF / `U010` | VL53L0X | `i2c` 0x29 | 输入 `distance-mm`；输出 — |
| Light / `U021` | photoresistor, LM393, 10k ohm adjustable resistor | `gpio-adc`  | 输入 `analog-mv`, `digital-level`；输出 — |
| Relay / `U023` | HK4100F-DC5V-SHG | `gpio`  | 输入 —；输出 `output-level` |
| Joystick v1.1 / `U024-C` | ATmega8A | `i2c` 0x52 | 输入 `x-raw`, `y-raw`, `button-raw`；输出 — |
| Dual Button / `U025` | two momentary switches | `gpio`  | 输入 `red-pressed`, `blue-pressed`；输出 — |
| Button / `U027` | momentary switch and resistor divider | `gpio`  | 输入 `pressed`；输出 — |
| NCIR / `U028` | MLX90614ESF-BAA | `i2c` 0x5A | 输入 `ambient-c`, `object-c`；输出 — |
| Heart Rate / `U029` | MAX30100 | `i2c` 0x57 | 输入 `ir-sample`, `red-sample`；输出 — |
| Encoder / `U135` | STM32F030F4P6, 30-position encoder, SK6812 x2 | `i2c` 0x40 | 输入 `counter`, `pressed`；输出 `led-rgb` |
| Thermal / `U016` | MLX90640 | `i2c` 0x33 | 输入 `pixel-temperature-c`；输出 — |
| Mini TVOC/eCO2 / `U088` | SGP30 | `i2c` 0x58 | 输入 `eco2-ppm`, `tvoc-ppb`；输出 — |
| IR / `U002` | IRM-3638T, 940nm IR LED, SS8050 | `gpio-rmt`  | 输入 `rx-pulses-us`；输出 `tx-pulses-us` |
| HUB / `U006` | 无主动芯片（无源并联） | `passive-hub`  | 输入 —；输出 — |
| RFID2 / `U031-B` | WS1850S (product), MFRC522 (linked schematic; inconsistent identity) | `i2c` 0x28 | 输入 `card-present`, `uid-hex`；输出 — |
| RS485 / `U034` | MAX485 / SP485EEN | `uart-rs485`  | 输入 `rx-hex`；输出 `tx-hex` |
| Buzzer / `U132` | passive buzzer, NPN driver | `gpio-pwm`  | 输入 —；输出 `frequency-hz`, `duty-pct` |
| Fan / `U063` | N20 DC motor | `gpio-pwm`  | 输入 —；输出 `duty-pct`, `frequency-hz` |
| Unit Limit / `U145` | mechanical lever switch | `gpio`  | 输入 `pressed`；输出 — |
| CardKB v1.1 / `U035-B` | ATmega8A | `i2c` 0x5F | 输入 50 键 `keys` 矩阵与兼容 `keycode`；输出官方修饰键状态机的 `led-rgb` |
| Unit Key / `U144` | mechanical blue switch, SK6812 x1 | `gpio-rmt`  | 输入 `pressed`；输出 `led-rgb` |
| Unit 8Encoder / `U153` | STM32F030C8T6, WS2812C-2020 x9 | `i2c` 0x41 | 输入 `counters`, `pressed`, `switch-on`；输出 `led-rgb` |

## 首批贯通边界

- Button：输入 `pressed`，白线在释放时高、按下时低；必须进入真实 GPIO 输入路径。
- Relay：只读 `output-level`；来自 guest 对黄色线的输出，不能由浏览器直接改成 ON。
- ENV III：输入 `temperature-c` / `humidity-pct` / `pressure-pa`；SHT30 命令、CRC 和
  QMP6988 OTP/补偿必须由 guest 原驱动消费。UIFlow `ENVUnit.read_pressure()` 的
  hPa 与注入属性 Pa 不能混用。

### QMP6988 离线校准参考

[`qmp6988_reference.py`](../../platform/units/qmp6988_reference.py) 只为 C 模型提供寄存器
编码/反算参考，不是 runtime adapter。它选择合法编码域内的**合成** OTP：
`b00=20000`、`a0=640`，其余 OTP=0；并不代表从真机读取的工厂校准，也不建立物理精度。
完整 25 字节为 `4e200000000000000000000000000000000002800000000000`。
25°C / 101325Pa 的 `0xF7` 六字节为 `a49d387202ab`。

用本次下载、未修改的官方 `QMP6988` 类读取离线寄存器 fixture，覆盖 7 个温度 × 6 个
压力的 42 个组合；最大量化误差为 `6.43e-6°C`、`0.01725Pa`。这是离线公式/字节契约
检查，未运行 firmware、QEMU 或 Device Service。来源哈希、范围和独立检查说明保存在
[`env-iii-qmp6988.json`](../../platform/units/fixtures/env-iii-qmp6988.json)。

## 各款原文与驱动路径

### ENV III (`env-iii`, `U001-C`)

SHT30 uses 16-bit commands and six-byte T/RH responses with CRC8 per 16-bit word (poly 0x31, init 0xFF). QMP6988 requires chip identity, 25-byte calibration, configuration, status and compensated 24-bit pressure/temperature samples. ENVUnit pressure API returns hPa; the injected pressure-pa state uses Pa.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- chip: `SHT30`；commands: measure-driver=0x2C10, status=0xF32D, reset=0x30A2, clear-status=0x3041, heater-on=0x306D, heater-off=0x3066；response: `T[15:8],T[7:0],CRC,RH[15:8],RH[7:0],CRC`；warning: `Current driver comment mentions 0x2C06 but executable MEASURE_CMD is 0x2C10.`
- chip: `QMP6988`；chip_id: `0xD1 -> 0x5C`；calibration: `0xA0, 25 bytes`；reset: `0xE0 <- 0xE6`；iir: `0xF1`；status: `0xF3 bit3 measuring`；control: `0xF4`；io_setup: `0xF5`；samples: `0xF7, pressure[3] then temperature[3], each unsigned 24-bit minus 2^23`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `temperature-c` | `number` | degC -40..120 |
| 外部输入 | `humidity-pct` | `number` | %RH 0..100 |
| 外部输入 | `pressure-pa` | `number` | Pa 30000..110000 |

未关闭边界：

- QMP6988 raw bytes must be consistent with calibration and compensation; do not substitute host-calculated API values.
- Fixture humidity permits the protocol range 0..100%RH; product accuracy specification is 10..90%RH.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/envIII)（2026-10-26）。
- [驱动 `env.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/env.py)，SHA-256 `a93c1b9fa822c2d707edd16205e68cf842160594993a4061044976fe96e2cce5`。
- [驱动 `sht30.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/sht30.py)，SHA-256 `7c8842ee297b2b50c888f2f28ab976e4cc1b1867078a4ffea5a9a68eae9db36d`。
- [驱动 `qmp6988.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/qmp6988.py)，SHA-256 `48ea71495622173423fb296c846d6fcf371c6fa0646d92f764822519388b8d7d`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/enviii/QMP6988%20Datasheet.pdf), [datasheet/原理图 2](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/SHT3x_Datasheet_digital.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### PIR (`pir`, `U004`)

White wire outputs high on motion detection, with a fixed 2-second retriggerable hold described by the product. UIFlow reads the white GPIO and registers rising/falling interrupts.

接线：red=5V (power)；black=GND (ground)；yellow=NC (none)；white=motion (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `motion` | `boolean` |  |

未关闭边界：

- A raw GPIO override is not a validated model of AS312 hold/retrigger timing.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/PIR)（2026-10-26）。
- [驱动 `pir.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/pir.py)，SHA-256 `0fa5fb6b512f682fb7adaabf0b09a9b3f76dea265f4406eea2bb8a23518a17e0`。

### Ultrasonic-I2C (`ultrasonic-i2c`, `U098-B1`)

Write command byte 0x01 to 0x57, wait 120 ms in the official driver, then read three bytes as a big-endian 24-bit distance value. Driver divides the raw value by 1000 for millimeters and optionally by a further 10 for centimeters.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- command: `0x01`；read_bytes: `3`；encoding: `BE uint24, 1000 raw units per mm`；driver_wait_ms: `120`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `distance-mm` | `number` | mm 20..4500 |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/ULTRASONIC%20I2C)（2026-10-26）。
- [驱动 `ultrasonic_i2c.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/ultrasonic_i2c.py)，SHA-256 `3c686309a6492d999f1d36cb9ed7ee9446822dfaaa13a6414632c87480616166`。

### RGB LED (`rgb`, `U003`)

Three daisy-chained addressable SK6812 RGB LEDs on the yellow data wire. The official RGBUnit delegates to SK6812; a model must decode the guest pulse stream instead of accepting a host-side color as guest output. Verified SK6812 driver has ORDER=(1,0,2,3), bpp=3 and timing=1: the RGB variant transmits GRB byte order.

接线：red=5V (power)；black=GND (ground)；yellow=LED data in (host-to-unit)；white=NC in product PinMap (none)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 只读输出 | `led-rgb` | `array` |  array[3..3] |

未关闭边界：

- The schematic exposes a chain DOUT on one connector while the current product PinMap labels white NC; preserve connector-specific uncertainty.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/rgb)（2026-10-26）。
- [驱动 `rgb.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/rgb.py)，SHA-256 `68b3a4424e4d0d6233578b33941fce5652ce2c5df41614804a6b23a903be040c`。
- [驱动 `sk6812.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/neopixel/sk6812.py)，SHA-256 `a03925be7ed5c61c644d3a176990a53c21dbb5bad4b2e854200ee4a0725ecb39`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/760/U003-UNIT_RGB-SCHE.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Angle (`angle`, `U005`)

White wire analog output is specified as 0..2500mV. Official AngleUnit uses the host ADC with 11dB attenuation; read_u16 is host ADC scaling rather than an I2C value.

接线：red=5V (power)；black=GND (ground)；yellow=NC (none)；white=analog output (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `voltage-mv` | `number` | mV 0..2500 |

未关闭边界：

- Mechanical angle-to-voltage transfer and SoC-specific ADC conversion/attenuation need a controller model.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/angle)（2026-10-26）。
- [驱动 `angle.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/angle.py)，SHA-256 `b9934370de61335e21e1db00792c6ea03366120439e552b2656fc963f37fe2dd`。

### Color (`color`, `U009`)

I2C register command bit 0x80; enable/power, integration time and gain precede little-endian 16-bit clear/red/green/blue readings. Raw channel values are the injection contract; lux or color-temperature conversion is performed by the guest driver.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- command_bit: `0x80`；enable: `0x00`；integration_time: `0x01`；gain: `0x0F`；identity: `0x12; driver accepts 0x4D/0x44/0x10`；status: `0x13`；channels: `C=0x14,R=0x16,G=0x18,B=0x1A; little-endian 16-bit`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `clear-raw` | `integer` | raw16 0..65535 |
| 外部输入 | `red-raw` | `integer` | raw16 0..65535 |
| 外部输入 | `green-raw` | `integer` | raw16 0..65535 |
| 外部输入 | `blue-raw` | `integer` | raw16 0..65535 |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/color)（2026-10-26）。
- [驱动 `color.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/color.py)，SHA-256 `89d9e703e6bc3ae551471ff4e50d6dbf548b17c0fb46e7b5e5f316050fbe61e5`。
- [驱动 `tcs3472.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/tcs3472.py)，SHA-256 `3cd3159545ec13665654c69745c6c4723b56656266b392f34120d0b120ab3f13`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/TCS3472_en.pdf), [datasheet/原理图 2](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/707/U009-UNIT_COLOR-SCHE.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### ToF (`tof`, `U010`)

The official driver performs the VL53L0X register initialization, SPAD configuration, reference calibration and ranging sequences at 0x29. Returning only a range number without the initialization/status path does not satisfy this protocol.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `distance-mm` | `number` | mm 30..2000 |

未关闭边界：

- Full driver initialization, data-ready/interrupt status, timeout and invalid-range semantics still require implementation.
- Product states usual maximum 120cm; 200cm requires Long Range mode and suitable environment.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/tof)（2026-10-26）。
- [驱动 `tof.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/tof.py)，SHA-256 `2e9907956107284934968603a138e7cdfb13ea3cf8162fb9694a7e4bbdaa664b`。
- [驱动 `vl53l0x.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/vl53l0x.py)，SHA-256 `a4e64aa62a0976d21845f7793d9b77d5d264a80b2d5d79edd5ed1fc76bd3e715`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/hat/VL53L0X_en.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Light (`light`, `U021`)

White wire is the analog output sampled through host ADC; yellow wire is the comparator digital output. The threshold is mechanically adjustable. Official driver exposes ADC raw/voltage-derived resistance and digital level, not a calibrated lux reading.

接线：red=5V (power)；black=GND (ground)；yellow=comparator digital output (unit-to-host)；white=analog output (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `analog-mv` | `number` | mV 0..未确认 |
| 外部输入 | `digital-level` | `boolean` |  |

未关闭边界：

- Exact analog rail/maximum and comparator polarity/threshold transfer are not established by the verified product text; do not invent lux calibration.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/light)（2026-10-26）。
- [驱动 `light.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/light.py)，SHA-256 `10142264cbc699c55c49ae5e0acd5c35855b361eb114a1fa12c02a7698d4768d`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/709/U201-UNIT_LIGHT_SCHE.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Relay (`relay`, `U023`)

GPIO high energizes relay; GPIO low releases it. DIN is the yellow wire. The unit has no protocol address; relay contact state is derived from the guest-driven GPIO.

接线：red=5V (power)；black=GND (ground)；yellow=DIN (host-to-unit)；white=NC (none)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 只读输出 | `output-level` | `boolean` |  |

未关闭边界：

- Electrical contact timing, load switching and physical isolation require separate hardware evidence.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/relay)（2026-10-26）。
- [驱动 `relay.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/relay.py)，SHA-256 `a3100b40bc7c77827b0fc6190964d54241e6be6c1fdd62d59b4192db3410118e`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/4relay/Datasheet-Realy-HK4100F-DC5V-SHG(1).pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Joystick v1.1 (`joystick-v11`, `U024-C`)

At 0x52, read three bytes from register 0x52: X raw, Y raw, button raw. X/Y range is 0..255. Guest get_x/get_y subtract 128 (with optional swap); preserve raw button byte until pressed polarity is explicitly verified.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- register: `0x52`；length: `3`；encoding: `X:uint8,Y:uint8,button:uint8`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `x-raw` | `integer` | raw8 0..255 |
| 外部输入 | `y-raw` | `integer` | raw8 0..255 |
| 外部输入 | `button-raw` | `integer` | raw 0..1 |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/joystick_1.1)（2026-10-26）。
- [驱动 `joystick.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/joystick.py)，SHA-256 `323da58ebb98d737ed8647567aabb36f0adafd66d1e8dcd5cdf895eeb599caed`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/799/U024-C_UNIT_JOYSTICK_SCHE.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Dual Button (`dual-button`, `U025`)

Two independent active-low button signals. Official product PinMap maps yellow to red button and white to blue button. UIFlow tuple is white then yellow; do not infer color names from the tuple order.

接线：red=5V (power)；black=GND (ground)；yellow=red button (unit-to-host)；white=blue button (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `red-pressed` | `boolean` |  |
| 外部输入 | `blue-pressed` | `boolean` |  |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/dual_button)（2026-10-26）。
- [驱动 `dual_button.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/dual_button.py)，SHA-256 `a734f1ae2bbd594f6d501ab9ee2dd8df170865fa0b3bbb91d6c1fa4da63626ac`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/578/Sch_UNIT_DualButton_v1.1.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Button (`button`, `U027`)

Active-low button output on the white wire; released high and pressed low. UIFlow ButtonUnit aliases LIMITUnit and configures port[0] with pull-up and active_low=True.

接线：red=5V (power)；black=GND (ground)；yellow=NC (none)；white=button (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `pressed` | `boolean` |  |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/button)（2026-10-26）。
- [驱动 `button.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/button.py)，SHA-256 `4b1634a4d4390850f1a20348dfdd8630e05c59f7fd7a4fc746963f6df1edcf92`。
- [驱动 `limit.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/limit.py)，SHA-256 `1cfeac648f99cb79b9e559a98a4771745cbda477ca2f604833afa7fe78d48a1f`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/804/U027_UNIT_BUTTON_SCHE.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### NCIR (`ncir`, `U028`)

SMBus/I2C memory reads at 0x5A. The official driver reads two little-endian bytes from ambient register 0x06 or object register 0x07 and converts raw*0.02 - 273.15 degrees Celsius.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- ambient: `0x06`；object: `0x07`；encoding: `little-endian uint16 Kelvin in 0.02K units`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `ambient-c` | `number` | degC -40..125 |
| 外部输入 | `object-c` | `number` | degC -70..380 |

未关闭边界：

- Official Python path reads two bytes without PEC; full SMBus PEC/EEPROM support is a separate requirement.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/ncir)（2026-10-26）。
- [驱动 `ncir.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/ncir.py)，SHA-256 `41909ef574150b5cffd4c9a33d73afd3c5eb75b89a4c0d8c660603b313b3a2c1`。
- [驱动 `mlx90614.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/mlx90614.py)，SHA-256 `c766bd2c05d7c13f3d48034569923d4562604be176d608966045a40862087403`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/hat/MLX90614-Datasheet-Melexis_en.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Heart Rate (`heart`, `U029`)

The official Python wrapper delegates sensor mode/current/sample-rate and update processing to cdriver.MAX30100; the external model must provide optical raw sample FIFO and register behavior. Heart rate and SpO2 are guest algorithms, not direct host-faked sensor registers.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- interrupt_status: `0x00`；interrupt_enable: `0x01`；fifo_write: `0x02`；fifo_overflow: `0x03`；fifo_read: `0x04`；fifo_data: `0x05`；mode: `0x06`；spo2_config: `0x07`；led_config: `0x09`；temperature: `0x16/0x17`；revision: `0xFE`；part_id: `0xFF`；fifo_encoding: `read FIFO 0x05, four bytes IR_MSB,IR_LSB,RED_MSB,RED_LSB as confirmed by max30100_read_fifo()`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `ir-sample` | `integer` | raw16 0..65535 |
| 外部输入 | `red-sample` | `integer` | raw16 0..65535 |

未关闭边界：

- FIFO timing, overflow, read-pointer and interrupt behavior still need execution coverage; raw sample byte format has been confirmed in max30100.c.
- Raw optical fixtures do not establish biological, clinical or physical optical accuracy.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/heart)（2026-10-26）。
- [驱动 `heart.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/heart.py)，SHA-256 `15249bf0e931f5d33dae61ac5a7899a2862faa4e86698249f909228e8272dbbe`。
- [驱动 `registers.h`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/cmodules/cdriver/max30100/registers.h)，SHA-256 `80e55b7f273feb633dbc3126c0f5895493c3d4a797816a00fa1c37b6202a8d0d`。
- [驱动 `driver_max30100.c`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/cmodules/cdriver/max30100/driver_max30100.c)，SHA-256 `1e5b009fb313811ac8d59e7d127f98c06e2a7e907f448e26802d71f26e061c1c`。
- [驱动 `max30100.c`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/cmodules/cdriver/max30100/max30100.c)，SHA-256 `eed901c774a04b09cbd9738308d2b0c6b502a66e267ba0880e16efdea64dddc1`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/MAX30100.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Encoder (`encoder`, `U135`)

I2C 0x40 uses a register pointer then reads/writes. Counter at 0x10 is signed 16-bit little-endian; button at 0x20 is active low; RGB writes at 0x30 contain LED index followed by three RGB bytes.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- counter: `0x10, int16 LE`；button: `0x20, byte0=0 pressed`；rgb: `0x30: index,R,G,B`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `counter` | `integer` | count -32768..32767 |
| 外部输入 | `pressed` | `boolean` |  |
| 只读输出 | `led-rgb` | `array` |  array[2..2] |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/encoder)（2026-10-26）。
- [驱动 `encoder.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/encoder.py)，SHA-256 `703a35a0f57e400fc33b41f4b14574844bca9bd11238ad501e4bcf9cb519b255`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/801/Unit-Encoder_Protocol.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Thermal (`thermal`, `U016`)

16-bit-addressed I2C words. Official driver loads factory EEPROM calibration from 0x2400, configures 0x800D, polls status 0x8000, and reads a frame block at 0x0400 with 832 words before calculating 32x24 temperatures.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- eeprom: `0x2400`；status: `0x8000`；control: `0x800D`；frame: `0x0400, 832 words including metadata`；encoding: `16-bit register address and words; driver compensation required`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 初期提案（未采用） | `pixel-temperature-c` | `array` |  array[768..768] |

当前实现以 `platform/units/catalog.json` 和 runtime profile 为准：输入为
EEPROM、两半帧的原始十六进制数据及 `control-word`，`raw-fixture-ready`
表示原始 fixture 是否就绪。768 个温度值由 guest 内的官方驱动读取 I2C
原始帧并补偿计算；没有主机直接写温度数组的接口。Web 标量 rail 只显示
控制寄存器和模型就绪状态，不显示温度图或平均温度。

未关闭边界：

- 公开原始样本与合成变体的 guest 数值验证不构成物理热场、光学或温度校准验证。

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/thermal)（2026-10-26）。
- [驱动 `thermal.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/thermal.py)，SHA-256 `401cb4dd53dbffe1d9277bf0bdaee3e25e602c12c92369a99856c91dd6825abb`。
- [驱动 `mlx90640.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/mlx90640.py)，SHA-256 `467d252e6dcfa9283b388ac20fe56c68bba79efe72f4d351742710af7b8e1e21`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/708/U016-UNIT_THERMAL-SCHE.pdf), [datasheet/原理图 2](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/hat/MLX90640-Datasheet-Melexis_en.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Mini TVOC/eCO2 (`tvoc`, `U088`)

16-bit SGP30 commands at 0x58; responses contain big-endian 16-bit words with CRC8. Official driver initializes IAQ and performs eCO2/TVOC measurement, baseline, feature-set and humidity-compensation operations.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- iaq_init: `0x2003`；measure_iaq: `0x2008`；get_baseline: `0x2015`；set_baseline: `0x201E`；humidity: `0x2061`；test: `0x2032`；feature: `0x202F`；raw: `0x2050`；serial: `0x3682`；encoding: `big-endian words + CRC8 per word`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `eco2-ppm` | `integer` | ppm 400..60000 |
| 外部输入 | `tvoc-ppb` | `integer` | ppb 0..60000 |

未关闭边界：

- eCO2 is a gas-derived estimate, not direct CO2 measurement; baseline and warm-up/timing semantics need separate coverage.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/tvoc)（2026-10-26）。
- [驱动 `tvoc.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/tvoc.py)，SHA-256 `ce7f512456a9fceb08e0ccb20e7c53075b84a0a6a760b529339938f959bf6d27`。
- [驱动 `sgp30.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/sgp30.py)，SHA-256 `885c494b1c28f459880e670df743560a944a2f31350a8c4a966e174e94e2e368`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/Sensirion_Gas_Sensors_SGP30_Datasheet.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### IR (`ir`, `U002`)

Independent yellow TX and white demodulated RX. Product specifies 38kHz receiver, 940nm emission and NEC support. A valid runtime path encodes/decodes carrier/envelope pulses through the SoC GPIO/RMT controller.

接线：red=5V (power)；black=GND (ground)；yellow=IR_TX (host-to-unit)；white=IR_RX (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `rx-pulses-us` | `array` | us array[0..未设] |
| 只读输出 | `tx-pulses-us` | `array` | us array[0..未设] |

未关闭边界：

- Protocol fixture pulse polarity, repeat frames and carrier timing must be covered by controller-level tests; no RF/optical reach claim.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/ir)（2026-10-26）。
- [驱动 `ir.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/ir.py)，SHA-256 `b342ff962ffe119e0f1e4d072182a6ea1b251d9dd52dcea8980e386b04ce3896`。

### HUB (`hub`, `U006`)

Passive four-wire parallel wiring expands one input connection into three shared connectors. It is not an addressable I2C multiplexer, has no register map, and cannot resolve duplicate addresses.

接线：red=5V (power)；black=GND (ground)；yellow=shared yellow bus (bidirectional)；white=shared white bus (bidirectional)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 拓扑 | 无主动可寻址状态 | 无 | 直接并联总线 |

未关闭边界：

- Topology, duplicate I2C address, GPIO drive contention and aggregate power must be checked by the attachment layer.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/hub)（2026-10-26）。

### RFID2 (`rfid2`, `U031-B`)

Product declares WS1850S and I2C address 0x28 with compatibility to the earlier RC522 Unit. Official UIFlow wrapper uses MFRC522 driver initialization, REQA/WUPA, anti-collision/select/authentication and card block operations.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- command: `0x01`；com_irq: `0x04`；error: `0x06`；fifo_data: `0x09`；fifo_level: `0x0A`；bit_framing: `0x0D`；tx_control: `0x14`；crc_result: `0x21/0x22`；transfer: `official pcd_read/write_register use raw 8-bit register addresses over I2C; no SPI-shift transformation`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `card-present` | `boolean` |  |
| 外部输入 | `uid-hex` | `string` |  |

未关闭边界：

- Product WS1850S identity conflicts with the linked schematic MFRC522 label; preserve the distinction.
- Do not map a UID directly to a Python read_card_uid return; FIFO/command/IRQ/card protocol execution is required.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/rfid2)（2026-10-26）。
- [驱动 `rfid.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/rfid.py)，SHA-256 `c71fb96399e009134fe213b2df3938eeb5fde88d08bf4c8ccfacd826aa39479e`。
- [驱动 `__init__.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/mfrc522/__init__.py)，SHA-256 `6462fa8be5d2d192bfdc428701dd619b719299daa1e4a82b16164a7099280974`。
- [驱动 `reg.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/mfrc522/reg.py)，SHA-256 `04cf1608635abef89423e7120e9e3b3bac8b49473267da5a4b0a133317b9a436`。
- [驱动 `cmd.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/mfrc522/cmd.py)，SHA-256 `10f1970913fda99ada4ac3ca08725a4fa5e64b25ae554936da29ac2bd3120bac`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/841/U031-B-Sch_Unit-RFID_v1.3.pdf), [datasheet/原理图 2](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/rfid2/WS1850S%20QFN-32.PDF), [datasheet/原理图 3](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/module/MFRC522_en.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### RS485 (`rs485`, `U034`)

TTL/UART to differential RS485 transceiver. Official driver sends host UART TX over yellow and receives on white (UIFlow tuple white,yellow); default init helper is 9600 8N1. Unit protocol bytes depend on the connected peer; no generic fixed Modbus address is implied.

接线：red=5V (power)；black=GND (ground)；yellow=Unit UART_RX / host TX (host-to-unit)；white=Unit UART_TX / host RX (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `rx-hex` | `string` |  |
| 只读输出 | `tx-hex` | `string` |  |

未关闭边界：

- Product lists external DC12V input and red wire 5V; exact power direction/regulation and automatic direction-control timing need schematic confirmation.
- Electrical differential voltage, bus termination and collision behavior are not inferred from UART bytes.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/rs485)（2026-10-26）。
- [驱动 `rs485.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/rs485.py)，SHA-256 `c388ef8e7e43f25e4f3ae05b646949dc1f7fbcb70d395884c1ca6e997dca2432`。
- 产品页另有 [datasheet/原理图 1](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/hat/SP485EEN_en.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Buzzer (`buzzer`, `U132`)

Yellow wire accepts a PWM square wave. Official product recommends 4kHz at half duty and explicitly forbids a sustained DC high. Official BuzzerUnit delegates to Haptic at 4000Hz.

接线：red=5V (power)；black=GND (ground)；yellow=PWM signal (host-to-unit)；white=NC (none)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 只读输出 | `frequency-hz` | `number` | Hz 0..未确认 |
| 只读输出 | `duty-pct` | `number` | % 0..100 |

未关闭边界：

- A frequency/duty observer does not establish acoustic sound pressure or spectral fidelity.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/buzzer)（2026-10-26）。
- [驱动 `buzzer.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/buzzer.py)，SHA-256 `a64cd1e918c92b97f3b0cd8c2e451416d0abfda7cd83aaef18883869f2e5c0c3`。

### Fan (`fan`, `U063`)

Yellow wire drives a single-direction motor through GPIO/PWM. Official driver initializes 250Hz and maps requested speed 1..100 to duty 70..1023 (zero disables). This is control duty, not a calibrated RPM model.

接线：red=5V (power)；black=GND (ground)；yellow=DIN/PWM (host-to-unit)；white=NC (none)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 只读输出 | `duty-pct` | `number` | % 0..100 |
| 只读输出 | `frequency-hz` | `number` | Hz 0..未确认 |

未关闭边界：

- The verified product text does not identify the motor-driver transistor/IC; no L9110 identity is guessed.
- No-load 8800RPM is a product specification, not a linear PWM-to-RPM transfer function.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/Unit_Fan)（2026-10-26）。
- [驱动 `fan.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/fan.py)，SHA-256 `eff2225e312ef341eecd26afadb2094a10ad080c17e1d7b722bcb131daa5ac02`。

### Unit Limit (`limit`, `U145`)

White wire active-low digital limit output: released 3.3V, pressed 0V according to the product. Driver provides active-low Button semantics and optional edge counting.

接线：red=5V (power)；black=GND (ground)；yellow=NC (none)；white=digital output (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `pressed` | `boolean` |  |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/Unit_Limit)（2026-10-26）。
- [驱动 `limit.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/limit.py)，SHA-256 `1cfeac648f99cb79b9e559a98a4771745cbda477ca2f604833afa7fe78d48a1f`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/600/SCH_unitLimit_V1.0.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### CardKB v1.1 (`cardkb`, `U035-B`)

CardKB v1.1 uses I2C address 0x5F and a key-code byte stream. Product documents 50 keys, shift/sym/fn transformations and one status RGB LED. The current shared driver also supports newer report-mode devices; that v2 path is not inherited by this v1.1 product.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- legacy_v1_1: `readfrom(0x5F,1): 0 means no key; nonzero is a key code`；newer_shared_driver: `The current driver also probes 0xF1 and supports v2 report mode; v2 is not asserted for U035-B.`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `keycode` | `integer` | raw8 0..255 |

未关闭边界：

- Keyboard matrix, modifier-lock behavior and consume-on-read/empty semantics require matching v1.1 firmware evidence; do not inherit new CardKB v2 report registers.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/Unit_CardKB_v1.1)（2026-10-26）。
- [驱动 `cardkb.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/cardkb.py)，SHA-256 `8ef7fb3c6d8fcb20e621427d42fe3756352792bcbe23165a36b444d40566a377`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/806/Unit_CardKB_v1_1_User_Manual_EN.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Unit Key (`key`, `U144`)

White wire is the active-low key input; yellow wire drives one SK6812 RGB LED. Official KeyUnit combines hardware.Button(active_low=True) with SK6812 on the second UIFlow tuple element.

接线：red=5V (power)；black=GND (ground)；yellow=LED data (host-to-unit)；white=button (unit-to-host)。

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `pressed` | `boolean` |  |
| 只读输出 | `led-rgb` | `integer` | rgb24 0..16777215 |

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/key)（2026-10-26）。
- [驱动 `key.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/key.py)，SHA-256 `fde43cccc637b8075585d61502bd5afcb14fc3dd5309e29b714055c99841b921`。
- [驱动 `sk6812.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/driver/neopixel/sk6812.py)，SHA-256 `a03925be7ed5c61c644d3a176990a53c21dbb5bad4b2e854200ee4a0725ecb39`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/599/SCH_unitKey_V1.0.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

### Unit 8Encoder (`8encoder`, `U153`)

Eight encoder channels and nine RGB outputs (eight encoder LEDs plus switch LED). Counter and increment registers are signed 32-bit little-endian; buttons are active low. A global toggle and firmware/address registers are exposed.

接线：yellow=SDA (bidirectional)；white=SCL (bidirectional)；red=5V (power)；black=GND (ground)。

确认的寄存器/命令：

- counter: `0x00..0x1F, int32 LE per channel`；increment: `0x20..0x3F, int32 LE`；reset: `0x40..0x47`；button: `0x50..0x57, 0=pressed`；switch: `0x60`；rgb: `0x70..0x8A, 3 RGB bytes per LED, 9 total`；firmware: `0xFE`；address: `0xFF`

状态契约：

| 方向 | 属性 | 类型 | 单位/范围 |
| --- | --- | --- | --- |
| 外部输入 | `counters` | `array` |  array[8..8] |
| 外部输入 | `pressed` | `array` |  array[8..8] |
| 外部输入 | `switch-on` | `boolean` |  |
| 只读输出 | `led-rgb` | `array` |  array[9..9] |

未关闭边界：

- Increment clear-on-read, wraparound, reset and address-change persistence need internal firmware confirmation.

官方证据：

- [产品页与 PinMap](https://docs.m5stack.com/en/unit/Unit_8Encoder)（2026-10-26）。
- [驱动 `encoder8.py`](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/encoder8.py)，SHA-256 `38bf8e2d7e5cea08aed605cda075d614f1275a2010898358426c53059d649e72`。
- 产品页另有 [datasheet/原理图 1](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/607/SCH_UNIT_8Encoder_V1.01.pdf), [datasheet/原理图 2](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/datasheet/unit/Unit%208Encoder/STM32F030C8T6.pdf)，本次仅确认链接存在于产品页，未声称逐页核验。

## 后续验收

1. 接入按明确 `device_id + port_id + attachment id` 绑定，防止重复 pin、同址设备和输出
   电平冲突。HUB 直接并联，不能被当作 PAHUB/I2C mux。
2. 先验证 GPIO/RMT/PWM/ADC/UART/I2C controller 和 board wiring，再实现 Unit 的
   寄存器/FIFO/命令与状态。资料完整但缺 controller 后端时保持 `planned/partial`。
3. 相同 firmware SHA、host profile 和 Unit 组合必须有设备本地驱动数据面测试。正式
   功能测试走 Device Service 可见 session，取证后 stop 保留历史。
4. 发布结论绑定 firmware/模型/工具哈希、输入、串口、应用帧和相关原始总线/PCM/网络
   证据。虚拟设备功能证据不外推为电气、功耗、声学、光学、机械或真实传感器精度。
