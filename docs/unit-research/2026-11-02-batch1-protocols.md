# Unit 第一批（12 款）官方协议研究报告

日期：`2026-11-02`。归属团队任务 `task-2`，工作树 `esp-emulator-units`，分支
`m5agent/unit-batch1`（基于 `origin/main` `930d7183`）。

本页是**实现前**的协议研究，不是运行时或硬件 PASS。本报告没有运行 QEMU、固件或
Device Service，没有修改 `platform/units/catalog.json`、`runtime-profiles.json`、
QEMU 源码或测试；配套的 catalog 草稿单独放在
[`2026-11-02-batch1-catalog-draft.json`](2026-11-02-batch1-catalog-draft.json)。

## 0. 结论摘要

从 151 款未登记 Unit 中选出 12 款。筛选口径：官方 UIFlow2 源码里有**可执行驱动**，
协议能落到现有三个 QEMU Unit 模型分支（`m5_unit_gpio.c` / `m5_unit_i2c_sensors.c` /
`m5_unit_i2c_controls.c`）之一，或能用同一寄存器机框架低成本扩展；明确排除需要新
控制器拓扑（UART/SPI/CAN/USB/摄像头）或需要新传感器补偿算法的型号。

| # | Unit id | SKU | 名称 | 总线 / 地址 | 复杂度 | 建议归属 QEMU 文件 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `ssr` | U122 | Unit SSR | `gpio` / — | A 低 | `m5_unit_runtime.c`（复用 `UNIT_RELAY`） |
| 2 | `vibrator` | U059 | Unit Vibrator | `gpio-pwm` / — | A 低 | `m5_unit_gpio.c`（复用 PWM 观察分支） |
| 3 | `earth` | U019 | Unit Earth | `gpio-adc` / — | A 低 | `m5_unit_gpio.c`（复用 angle/light 分支） |
| 4 | `hall` | U084 | Unit Hall | `gpio` / — | A 低 | `m5_unit_gpio.c`（复用 PIR 数字输入分支） |
| 5 | `reflective-ir` | U175 | Unit Reflective IR | `gpio-adc` / — | A 低 | `m5_unit_gpio.c`（复用 angle/light 分支） |
| 6 | `dlight` | U136 | Unit DLight | `i2c` / `0x23` | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_DLIGHT`） |
| 7 | `accel` | U056 | Unit Accel | `i2c` / `0x53` | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_ACCEL`） |
| 8 | `4relay` | U097 | Unit 4Relay | `i2c` / `0x26` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_RELAY4`） |
| 9 | `weight-i2c` | U180 | Unit Weight-I2C | `i2c` / `0x26` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_WEIGHT`） |
| 10 | `ncir2` | U150 | Unit NCIR2 | `i2c` / `0x5A` | C 中 | `m5_unit_i2c_controls.c`（新增 `CONTROL_NCIR2`） |
| 11 | `extio2` | U011-B | Unit EXT.IO2 | `i2c` / `0x45` | C 中 | `m5_unit_i2c_controls.c`（新增 `CONTROL_EXTIO2`） |
| 12 | `hbridge` | U160 | Unit HBridge | `i2c` / `0x20` | C 中 | `m5_unit_i2c_controls.c`（新增 `CONTROL_HBRIDGE`） |

复杂度定义：

- **A 低**：只注册 id 并复用现有数据面分支，预计 QEMU 侧改动 `< 15` 行，不需要新的
  寄存器状态。
- **B 中低**：新增一个 kind / 分支，但直接复用现有寄存器指针、快照、QOM 属性框架。
- **C 中**：新增一个完整寄存器文件 kind 与少量派生语义（温度换算、浮点编码、多通道
  模式），但仍在同一个 I2C slave 框架内，不涉及新的 SoC 控制器拓扑。

未登记差集口径（可复算）：`platform/web/vendor/m5stack-models/catalog/products.json`
的 `category=="unit"` 共 **184** 款；`platform/units/catalog.json` 登记 **34** 款，其中
`servo8-hat` 在 vendor 目录里属于 HAT 条目、不在 unit 类别；故未登记 = 184 − 33 =
**151** 款。任务描述写的 150 与本次精确差集差 1 款，属口径差异，不影响选型。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

- 官方 UIFlow2 源码快照：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git 远端 `https://github.com/rodrigob/uiflow_micropython.git`，HEAD
  `528edd8a06d2556c8e753c8e4978179bbb12b5ba`，`version.text` 为 V2.1.5）。
  本页所有 `m5stack/libs/...:行号` 都**锚定这个快照**，可由实现者本地复读。
- 官方 GitHub master 交叉核对：2026-11-02 用
  `https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/...`
  逐文件下载比对。12 个 unit 驱动中 9 个与快照**逐字节相同**；3 个不同：
  `unit/accel.py`、`unit/extio2.py`、`unit/weight_i2c.py`（差异内容见 §6）。
  master 上 `m5stack/uiflow-micropython` 没有快照 commit `528edd8`（该 commit 只在
  镜像远端存在），因此实现时应二选一并把所选版本写进 catalog 的 `sha256`。
- 官方产品页：2026-11-02 直接抓取 12 个 `officialDocs` 页面，PinMap 表、SKU、芯片名
  与 4Relay 的寄存器协议表均从页面 HTML 原文核对；页面链接的 datasheet/原理图/协议
  PDF **未逐页阅读**，按仓库既有方法标记为 `linked-by-verified-product-page`。
- 官方 I2C 地址总表 `https://docs.m5stack.com/en/product_i2c_addr`（2026-11-02）用于
  交叉核对 I2C 地址与可编程地址范围。

### 1.2 逐款证据等级

| 等级 | 含义 | 本批型号 |
| --- | --- | --- |
| E1 | 官方 PinMap + 可执行驱动逐行完整语义（寄存器/命令/编码），无需 PDF 即能确定实现所需的通信语义 | `ssr` `vibrator` `earth` `hall` `4relay` |
| E2 | 官方 PinMap + 可执行驱动逐行完整语义，但**官方协议文档/数据手册只确认链接存在、未读**，或存在必须显式标注的未决字段 | `reflective-ir` `dlight` `accel` `ncir2` `extio2` `weight-i2c` `hbridge` |
| E3 | 只能读到 API/字段名，关键语义 unknown | 本批没有整款 E3；单字段 unresolved 见 §5 |

本报告禁止按产品名推断协议：每个型号都至少能落到一个官方驱动文件的具体行，或者
明确写进 §5 的 `unresolved`。

### 1.3 主机侧约定（本批全部适用）

- UIFlow GPIO `port` 元组为 `(white, yellow)`：`port[0]` 对应 Grove 白线，`port[1]`
  对应黄线。本批的寄存器/引脚结论都按这个顺序复算，未从颜色名称反推。
- Grove 连接器颜色固定为 `black=GND`、`red=5V`、`yellow`/`white` 为信号；I2C 型号统一
  `yellow=SDA`、`white=SCL`。
- 红线 5V 只是官方 PinMap 的供电标签，不能推出 GPIO 逻辑电平。各型号的 `logic_v`
  保持 `null`，`logic_voltage_status` 沿用 catalog 既有文案。
- `inputs` 是外部世界/fixture 状态，经 SoC 控制器送入 guest；`outputs` 是 guest 驱动
  外设后的只读观测。两者都不是直接覆盖 guest Python 返回值的接口。
- 不执行 QEMU/固件；本报告给出的“可断言数据面标志”是**实现验收目标**，不是已验证结果。

## 2. 与现有 QEMU Unit 模型的复用映射

以下是 `/Users/m5agent/Documents/ChatGPT/esp-emulator-shellsim/.work/native-lock-source/qemu/hw/m5stopwatch/`
下现有模型的接入点（只读参考，本报告未修改）。行号以该 worktree 当前快照为准。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c` | `UNIT_RELAY` 输出观测/复位边界 `:160-200`；realize `:367-379`；`M5_UNIT_CONFIG` id 分派 `:465-471`；`m5_unit_extra_realize` 兜底 `:408` | `ssr` 复用 `UNIT_RELAY` |
| `m5_unit_gpio.c` | 支持 id 列表 `:606-613`；ADC 注入 `:737-754`（filter `:747-748`）；PWM 观察 `:756-773`（filter `:767`）；RMT 发送 `:775+`；GPIO realize 分支 `:918`（pir）、`:931`（angle/light）、`:938`（fan/buzzer）、`:948`（rgb/key） | `vibrator` `earth` `hall` `reflective-ir` |
| `m5_unit_i2c_sensors.c` | kind 枚举 `:22-23`；`add_number` 属性框架 `:109`；采样更新 `:207`；写路径 `:345`（pointer 语义 `:393-397`）；读路径 `:462`；支持 id `:531-538`；realize `:540+` | `dlight` `accel` |
| `m5_unit_i2c_controls.c` | kind 枚举 `:34-37`；寄存器快照 `:751`；事件 `:796`；写路径 `:824`；读路径 `:917`；支持 id `:973-980`；realize `:983+` | `4relay` `weight-i2c` `ncir2` `extio2` `hbridge` |

复用原则（避免把模型写成 host 侧假值）：

- GPIO/ADC/PWM 型号必须继续走 `esp32_gpio_set_input`、`m5_unit_adc_sample`、
  `m5_unit_pwm_observe` 这些**控制器级**钩子；不新增直接改 guest 返回值的属性。
- I2C 传感器型号必须在 `I2CSlaveClass.send/recv` 里实现真实总线字节语义（指针、
  自动递增、快照、读清），QOM 属性只做注入/观测。
- 输出型型号只允许观测 guest 驱动的 pad/线上状态或总线写入轨迹。

## 3. 地址与总线冲突

本批新增型号与已登记型号的默认 7-bit 地址冲突（同一条被动 HUB/同一 bus 不能共存）：

| 地址 | 本批型号 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x26` | `4relay` U097、`weight-i2c` U180 | 两者互相冲突 | 官方 I2C 总表；`unit/relay4.py:51`；`unit/weight_i2c.py:11` |
| `0x5A` | `ncir2` U150 | `ncir` U028（MLX90614） | 官方 I2C 总表；`unit/ncir2.py:8` |
| `0x20` | `hbridge` U160 | 无已登记冲突；自身可改 `0x20-0x2F` | 官方 I2C 总表；`unit/hbridge.py:10,36-44` |
| `0x23` | `dlight` U136 | 无 | 官方 I2C 总表；`driver/bh1750.py:11` |
| `0x53` | `accel` U056 | 无 | 官方 I2C 总表；`unit/accel.py:9`、`driver/adxl34x.py:10` |
| `0x45` | `extio2` U011-B | 无；官方标 programmable | 官方 I2C 总表；`unit/extio2.py:24` |

实现建议：`4relay` 与 `weight-i2c` 必须按“单 bus 只挂一个”建模并写进 fixture 校验；
`ncir2` 与 `ncir` 同理。不要为了凑多 Unit 放宽地址冲突检查（现有
`m5_unit_i2c_controls.c` 已有同 bus 地址占用检查的先例，见 `:555-570` JOYSTICK2 分支）。

## 4. 各款协议详情

### 4.1 `ssr` — Unit SSR（U122）

**官方**：[Unit SSR](https://docs.m5stack.com/en/unit/ssr)（2026-11-02 读取）；SKU
`U122`；芯片 `MOC3043M` 光耦 + `BT136S` 可控硅（产品页 Datasheets 列表）。
**驱动**：`m5stack/libs/unit/ssr.py`（快照与 master 逐字节相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`DIN`、
White=`NC`。即控制线在黄线，白线不接。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 控制引脚 | `unit/ssr.py:43` | `Pin(port[1])` → 黄线 |
| 初始化 | `unit/ssr.py:44` | `Pin.OUT, pull=PULL_DOWN, value=0` |
| 开/关 | `unit/ssr.py:46-64` | `on()→value(1)`，`off()→value(0)` |
| 通用写 | `unit/ssr.py:66-76` | `set_state(state)` → `value(state)` |

无寄存器、无地址、无读回：guest 只能驱动 GPIO，不能读继电器状态。

**官方 API**：`on()`、`off()`、`set_state(state)`（`unit/ssr.py:46,56,66`）。

**主机输入**：无（纯输出 Unit）。

**QEMU 建议**：直接复用 `UNIT_RELAY`。`m5_unit_runtime.c:367-379` 已对黄线建立
`output-level` 观测与 `output-transitions`，`:160-200` 已有硬复位边界；只需在
`M5_UNIT_CONFIG` 的 id 分派 `:465-471` 把 `"ssr"` 映射到 `UNIT_RELAY`（并同步
`platform/peripherals` 与 runtime profile 的 id 列表）。不需要新文件。

**可断言数据面标志**：`/machine/units/{id}/output-level`（guest `on()` 后为真）、
`output-transitions`（每次电平变化 +1）、`transactions/read-bytes/written-bytes` 全为
0（证明没有伪装 I2C 数据面）。

**风险/未确认**：交流过零开关、过流保护、耐压/负载与触点寿命**不建模**（与 `relay`
既有边界相同，写进 blocker）。产品页称“only suitable for AC loads”，模型不能因此
拒绝 DC 负载测试；电气结论一律留在硬件域。

### 4.2 `vibrator` — Unit Vibrator（U059）

**官方**：[Unit Vibrator](https://docs.m5stack.com/en/unit/vibrator)（2026-11-02）；
SKU `U059`；`N20` 直流电机 + 金属偏心轮，N 沟道 MOSFET 低边驱动，空载 8800 RPM，
产品页建议 PWM 频率 10 kHz。
**驱动**：`unit/vibrator.py` + `driver/haptic.py`（两者快照与 master 相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`DIN`、White=`NC`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 引脚 | `unit/vibrator.py:8-10` | `VibratorUnit(Haptic)`，`super().__init__(port[1])` → 黄线 |
| PWM 构造 | `driver/haptic.py:20-21` | `PWM(pin, freq=100, duty_u16=0)`（默认 100 Hz） |
| 单次震动 | `driver/haptic.py:25-30` | `once(freq,duty,duration)` 先 set `duty_u16=duty*65535//100`，软定时后回调清零 |
| 持续设置 | `driver/haptic.py:35-41` | `set_freq(freq)`、`set_duty(duty 0-100)`、`turn_off()` |

**官方 API**：`once(freq=10,duty=50,duration=50)`、`set_freq()`、`set_duty()`、
`turn_off()`（`driver/haptic.py:25,35,38,41`）。

**主机输入**：无（纯输出 Unit）。

**QEMU 建议**：复用 `m5_unit_gpio.c` 的 PWM 观察分支。该分支在 realize `:938-940`
添加 `frequency-hz`/`duty-pct` 属性，在 `m5_unit_pwm_observe` `:756-773` 按
LEDC 配置（timer/divider/resolution/enable bit）计算频率与占空比，并要求 guest 的
PWM 输出矩阵路由到该 Unit 黄线（`:767` 的 fan/buzzer 条件）。需要改的只有两处：
`m5_unit_gpio_supported` 列表 `:606-613` 加 `"vibrator"`，以及 `:938`、`:767` 两个
id 条件加 `"vibrator"`。不需要新文件。

**可断言数据面标志**：`frequency-hz`、`duty-pct`、`output-transitions`；注入
`once()` 后应看到 duty 先非 0 再回 0（guest 软定时行为，不要求模型计时）。

**风险/未确认**：
- 产品页建议 10 kHz、驱动默认 100 Hz，二者都合法；模型只观测实际 LEDC 配置，不能
  声称“最佳频率”。
- 振动强度/加速度、机械偏心轮行为、MOSFET 电气特性都不建模。
- 现有 PWM 分支在 `conf` 未使能时把 duty 归 0（`:763`），这是既有策略，与本 Unit
  无关，但验收时要知道。

### 4.3 `earth` — Unit Earth（U019）

**官方**：[Unit Earth](https://docs.m5stack.com/en/unit/earth)（2026-11-02）；SKU
`U019`；土壤湿度探针 + 10K 可调电阻，模拟 + 数字双输出；产品明确“电极不耐腐蚀/
不防水，仅 PoC”。
**驱动**：`unit/earth.py`（快照与 master 相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`Digital Output`、
White=`Analog Output`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 引脚 | `unit/earth.py:8-10` | `ADC(Pin(port[0]=white), atten=ATTN_11DB)`；`Pin(port[1]=yellow, IN)` |
| 模拟读 | `unit/earth.py:39-43` | `read_u16()`（原始）；`read_uv()/1000`（mV） |
| 数字读 | `unit/earth.py:45` | `get_digital_value()` 返回黄线电平 |
| 湿度换算 | `unit/earth.py:22-37` | 只用 `min=2900/max=1630` 两个**驱动常量**做线性/反向插值 |
| 校准 | `unit/earth.py:14-20` | `set_calibrate(min,max)` 只改 Python 侧常量 |

**官方 API**：`get_analog_value()`、`get_voltage_mv()`、`get_digital_value()`、
`humidity()`、`set_calibrate()`（`unit/earth.py:39,42,45,22,14`）。

**主机输入**：`analog-mv`（0..3300，白线 ADC）、`digital-level`（bool，黄线比较器）。

**QEMU 建议**：复用 `m5_unit_gpio.c` 的 `angle/light` 分支——`:931-937` 已实现
“白线 ADC 电压注入 + `adc-samples` 计数”，`light` 子分支还在黄线注入数字电平；
`:737-754` 的 `m5_unit_adc_sample` 会按 `white == pin` 且 id ∈ {angle,light} 返回
ADC 读数。需要改：`:606-613` 加 `"earth"`、`:931` 和 `:747-748` 的 id 条件加
`"earth"`。数据契约与 `light` 完全同构（`analog-mv` + `digital-level`）。

**可断言数据面标志**：`analog-mv` 被 guest `read_u16/read_uv` 消费后
`adc-samples` 递增；`digital-level` 对应 guest `get_digital_value()` 的串口输出。

**风险/未确认**：
- 数字输出的**高/低含义**（湿/干）产品页与驱动都没有声明；`digital-level` 只暴露
  原始电平，不定义“检测到水”。`humidity()` 的 2900/1630 是驱动默认常量，不是校准
  数据，不能作为湿度真值。
- 探针腐蚀、极化、土壤类型影响不建模。

### 4.4 `hall` — Unit Hall（U084）

**官方**：[Unit Hall](https://docs.m5stack.com/en/unit/hall)（2026-11-02）；SKU
`U084`；3× `A3144E` 霍尔开关 + `74HC08D` 逻辑门；产品规格明确 **Output Level:
Low-level active**，“S 极靠近正面或 N 极靠近背面时输出低电平并点亮指示灯”。
**驱动**：`unit/hall_effect.py`（继承 `unit/pir.py`；两者快照与 master 相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`NC`、
White=`Digital Output`。即信号在白线。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 基类/引脚 | `unit/hall_effect.py:5,9-14` → `unit/pir.py:17-20` | `Pin(port[0]=white)`，`IN`，双沿 IRQ |
| 极性常量 | `unit/hall_effect.py:10-11` | `IRQ_ACTIVE=0`、`IRQ_NEGATIVE=1`（低有效，与 PIR 的常量相反） |
| 读状态 | `unit/pir.py:23` | `get_status()` 返回白线原始电平 |

**官方 API**：`get_status()`、`set_callback(handler, trigger)`、`enable_irq()`、
`disable_irq()`，触发常量 `IRQ_ACTIVE`/`IRQ_NEGATIVE`（`unit/pir.py:23,26,29,32`；
`unit/hall_effect.py:10-11`）。

**主机输入**：`magnetic-detected`（bool）。语义：true → 白线拉低；false → 白线拉高。

**QEMU 建议**：在 `m5_unit_gpio.c` 的 PIR 分支（`:918-921`）旁增加一个输入分支：
`esp32_gpio_set_input(unit->white, detected ? 0 : 1)`，QOM 属性 `magnetic-detected`
（读写）+ `input-level`（读）。**不要**照搬 PIR 的 2 秒 `motion_off` 保持计时
（`motion_off` `:628-634`），A3144E 是即时开关，没有产品声明的保持窗口。需要改
`:606-613` 列表 + 新增一个 realize 分支。不需要新文件。

**可断言数据面标志**：`magnetic-detected` 注入后 guest `get_status()` 的串口输出
（true 时读到 0）；guest 注册双沿 IRQ 时，两次注入应触发两次回调。

**风险/未确认**：3 颗 A3144E 与 `74HC08D` 的组合逻辑（AND/OR、三面灵敏度的空间
判据）**没有官方原理图逐页核对**，本模型只暴露单根白线的合成电平，不建模三传感器
空间分布与磁极方向。指示灯不建模。

### 4.5 `reflective-ir` — Unit Reflective IR（U175）

**官方**：[Unit Reflective IR](https://docs.m5stack.com/en/unit/Unit-Reflective%20IR)
（2026-11-02）；SKU `U175`；红外发射+接收，模拟/数字双输出，`LM393` 比较器，出厂
阈值 1.65 V（产品页 Note，写有可调电位器与有效区间说明）。
**驱动**：`unit/reflective_ir.py`（快照与 master 相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`Digital Output`、
White=`Analog Output`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 引脚 | `unit/reflective_ir.py:18-20` | `ADC(Pin(port[0]=white))`；`Pin(port[1]=yellow, IN)` |
| 模拟/数字读 | `unit/reflective_ir.py:23-27` | `get_digital_value()`、`get_analog_value()` |
| IRQ 语义 | `unit/reflective_ir.py:29-41` | 双沿 IRQ，回调参数是 `pin()` 的原始电平；`EVENT_DETECTED=0`、`EVENT_NOT_DETECTED=1` |
| 使能 | `unit/reflective_ir.py:32-36` | `enable_irq/disable_irq` |

**官方 API**：`get_digital_value()`、`get_analog_value()`、`set_callback()`、
`enable_irq()`、`disable_irq()`；事件常量 `EVENT_DETECTED`/`EVENT_NOT_DETECTED`
（`unit/reflective_ir.py:23,26,29,35,15-16`）。

**主机输入**：`analog-mv`（白线 ADC）、`digital-level`（黄线比较器电平）。

**QEMU 建议**：与 `earth` 完全同构，复用 `angle/light` 分支（`:931-937`、`:747-748`、
`:606-613`）。数字事件本身来自 guest 双沿 IRQ，模型不需要生成边沿。

**可断言数据面标志**：`analog-mv` → `adc-samples`；`digital-level` → guest 数字读数/
回调。

**风险/未确认**：产品页只写“Detection status via analog and digital signals”，
**数字输出的高/低与“检测到反射物”的对应关系未在驱动或页面显式声明**（驱动的
`EVENT_DETECTED=0` 只是回调索引，不是比较器极性）；该字段保持 `unresolved`，模型仅
暴露原始电平。比较器阈值 1.65 V 是产品页文本，不是我们读过的 schematic 真值；IR
发射/接收器件型号产品页未给出。

### 4.6 `dlight` — Unit DLight（U136）

**官方**：[Unit DLight](https://docs.m5stack.com/en/unit/DLight%20Unit)（2026-11-02）；
SKU `U136`；`BH1750FVI`，I2C `0x23`，量程 1–65535 lx，16-bit ADC。
**驱动**：`unit/dlight.py`（一行别名）+ `driver/bh1750.py`（两者快照与 master 相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（逐行）**：

| 命令 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` / `0x01` / `0x07` | `driver/bh1750.py:15-17` | power down / power on / reset |
| `0x10` / `0x11` / `0x13` | `:21,24-26` | continuous H-res / H-res2 / L-res |
| `0x20` / `0x21` / `0x23` | `:22,24-26` | one-time H-res / H-res2 / L-res |
| 灵敏度高字节 | `:56-59` | `int(69*sensitivity)` 后写 `(0b01000<<3)|(mt>>5)`，编码域 `0x40..0x5F` |
| 灵敏度低字节 | `:60-61` | `(0b011<<5)|(mt&0b11111)`，编码域 `0x60..0x7F`，随后重发 measurement 命令 |
| 读取 | `:72-74` | 直接 `readfrom_into` 2 字节，`>H` 大端 |
| lux 换算 | `:76-81` | `lux = raw / 1.2 / sensitivity`，H-res2 再 /2 |
| 转换时间 | `:88-92` | H-res 180 ms、L-res 24 ms（按 sensitivity 反比） |

**官方 API**：`get_lux()`、`configure(mode, resolution)`、`get_sensitivity()`、
`set_sensitivity()`，常量 `CONTINUOUSLY`/`ONE_TIME`/`H_RESOLUTION_MODE`/
`H_RESOLUTION_MODE2`/`L_RESOLUTION_MODE`、`Power`（`driver/bh1750.py:43,48,53,56,21-26,14-17`）。
UIFlow 示例：`examples/unit/dlight/dlight_core_example.py:24-32`（I2C0 + `get_lux()`）。

**主机输入**：`illuminance-lx`（number，1..65535）。

**QEMU 建议**：在 `m5_unit_i2c_sensors.c` 新增 `US_DLIGHT`（枚举 `:22-23`、realize
`:540+`、支持列表 `:531-538`、`add_number` `:109`）。写路径：单字节命令（`sensor_send`
`:345` 的通用 pointer 分支不适用，需要专用分支）；读路径：直接返回 2 字节大端
（`sensor_recv` `:462`）。样本由 `illuminance-lx` 反算：`raw = lux*1.2*sensitivity`
（H-res2 再 ×2），并遵守转换/掉电窗口（掉电或转换中读返回旧值/0，策略需在实现时
明确并写注释）。**不要**用 host 侧直接改 `get_lux()`。

**可断言数据面标志**：`transactions`、`read-bytes`、`written-bytes`（命令字节）；
guest `get_lux()` 串口值等于 fixture 的 `illuminance-lx`（允许 ±1 LSB 量化）；
`configure()`/`set_sensitivity()` 后的命令字节轨迹。

**风险/未确认**：BH1750FVI datasheet 仅链接未读；上电默认 MTreg（驱动 sensitivity
默认 1.0 对应的编码是计算值，不是 datasheet 默认值）保持 `unresolved`。产品页宣称
1..65535 lx，但 `lux=raw/1.2` 要求 `raw=lux*1.2`，16-bit raw 在 sensitivity=1 时只能
表达到约 54612 lx，**量程上限与编码一致性未决**（fixture 应限制在可编码范围，或改用
MTreg/sensitivity 重新标定）。驱动的 `_ready()`（`:83-86`）睡眠表达式可疑（可能传入
负值），实现时不要复刻该时序 bug；模型只要求返回最新样本。

### 4.7 `accel` — Unit Accel（U056）

**官方**：[Unit Accel](https://docs.m5stack.com/en/unit/accel)（2026-11-02）；SKU
`U056`；`ADXL345` 三轴加速度计，I2C `0x53`，±2/4/8/16 g，16-bit 二进制补码。
**驱动**：`unit/accel.py` + `driver/adxl34x.py`（`unit/accel.py` 快照与 master **不同**：
master 增加文档与 `enable_*_detection` 包装，寄存器路径不变；`driver/adxl34x.py` 仅
注释/文档差异，见 §6）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器语义（逐行，地址均为 8-bit 寄存器号）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` DEVID | `driver/adxl34x.py:16` | 器件 ID（**驱动从不读**，值见 §5 unresolved） |
| `0x1D..0x2A` | `:17-31` | tap/offset/duration/activity/free-fall 阈值与轴控制 |
| `0x2B` ACT_TAP_STATUS | `:31` | tap 源状态 |
| `0x2C` BW_RATE | `:32` | 数据率（编码 `:54-69`） |
| `0x2D` POWER_CTL | `:33` | init 写 `0x08` 进入 measure（`:112`） |
| `0x2E` INT_ENABLE | `:34` | init 写 0（`:113`），`enable_*` 后按 bit 打开 |
| `0x2F` INT_MAP | `:35` | 中断映射 |
| `0x30` INT_SOURCE | `:36` | 读清中断源（`:369-370`；`events` `:143-184`） |
| `0x31` DATA_FORMAT | `:37` | 量程编码 `:71-74`；`range` setter `:332-350` |
| `0x32..0x37` | `:38-43` | X/Y/Z 各 2 字节小端 int16；`acceleration` 一次读 6 字节（`:119-125`） |
| `0x38/0x39` | `:44-45` | FIFO_CTL/FIFO_STATUS（驱动未使用） |

换算：`raw * 0.004 * 9.80665` m/s²（`:12-14,121-125`）；`raw_x/y/z` 直接暴露 int16
（`:128-140`）。

**官方 API**：`get_accel()`、`get_data_rate()/set_data_rate()`、`get_range()/set_range()`、
`is_tap()`、`is_motion()`、`is_freefall()`（`unit/accel.py:12-36`）；master 版另有
`enable_motion_detection()/enable_freefall_detection()/enable_tap_detection()` 及对应
`disable_*`（master 版行号 51/270/318；V2.1.5 快照里没有这些方法）。

**主机输入**：`accel-x-raw`、`accel-y-raw`、`accel-z-raw`（int16，-32768..32767）。
事件 fixture（`tap`/`motion`/`freefall`，由 `0x30` 读清消费）本批未列入契约，作为
第二阶段可选扩展；第一阶段只验收三轴 raw → 驱动换算。

**QEMU 建议**：在 `m5_unit_i2c_sensors.c` 新增 `US_ACCEL`，直接复用现有
“首字节=寄存器指针、后续读自动递增”的通用机制（`sensor_send` `:393-397` 的
`pointer = data`、`sensor_recv` `:486`/`:500` 的读指针与 `:507` 的通用返回），不需要 per-kind 分支：
- 写：记录 POWER_CTL/INT_ENABLE/DATA_FORMAT/BW_RATE 等寄存器值；对 `0x30` 读清置位。
- 读：`0x32..0x37` 从三个 int16 fixture 拼小端字节；`0x30` 返回当前事件位并在下次
  读时清除（行为对齐 `:369-370`）。
- `add_number`（`:109`）注册三个 raw 输入；换算留给 guest 驱动。

**可断言数据面标志**：guest `get_accel()` 输出 = fixture raw × 0.004 × 9.80665；
`raw_x/raw_y/raw_z` 原样；POWER_CTL 写入轨迹 `0x2D<-0x08`；`events` 读清语义；
`transactions` 计数。

**风险/未确认**：
- `DEVID(0x00)` 的官方值**没有从 datasheet 逐页核实**（驱动不读它），实现时建议把
  它做成 fixture 输入或明确注释 `unresolved`，**不要按型号猜 `0xE5`**。
- `DATA_FORMAT` 量程 bit 的换算是否影响 raw LSB（ADXL345 full-resolution 模式下
  LSB 固定）未核实；模型只需保证写入寄存器 bit 正确，换算按驱动公式即可。
- tap/activity/free-fall 的阈值/时间窗语义只做到寄存器读写与 `INT_SOURCE` 读清，
  不建模真实机械事件检测。

### 4.8 `4relay` — Unit 4Relay（U097）

**官方**：[Unit 4Relay](https://docs.m5stack.com/en/unit/4relay)（2026-11-02）；SKU
`U097`；`STM32F030F4P6`，4 路机械继电器，I2C `0x26`，AC250V/DC28V 10A。产品页
**内嵌完整 Protocol 表**（Mode control `0x10`、RELAY control `0x11`），是本批少有的
“官方页面直接给出寄存器表”的型号。
**驱动**：`unit/relay4.py`（快照与 master 相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器语义（官方页面表 + 驱动逐行）**：

| 寄存器 | 位 | 语义 | 驱动证据 |
| --- | --- | --- | --- |
| `0x10` Mode | bit0 | LED Sync Mode：0=Manual（LED 独立控制），1=Auto（LED 跟随继电器）；bit7..1 页面标 read-only | 页面 Protocol 表；`unit/relay4.py:45,48-49,82` |
| `0x11` Control | driver: bit0..3 | **驱动语义（Python 与 Arduino 一致）**：RELAY1..RELAY4 分别落在 bit0..bit3 | `unit/relay4.py:137,139-160`（`n-1`）；Arduino `Unit_4RELAY.cpp:64-73` |
| `0x11` Control | driver: bit4..7 | **驱动语义**：LED1..LED4 分别落在 bit4..bit7 | `unit/relay4.py:102,104-125`（`n+3`）；Arduino `Unit_4RELAY.cpp:78-86`（`0x10<<number`） |
| `0x11` Control | page: bit3..0 / bit7..4 | **官方页面 Protocol 表写的是反序**：bit3=RELAY1…bit0=RELAY4，bit7=LED1…bit4=LED4 | 产品页 Protocol 表（2026-11-02 抓取） |

> **位序冲突（必须显式记录）**：产品页 4Relay Protocol 表把 RELAY1 写成 bit3、RELAY4
> 写成 bit0、LED1 写成 bit7、LED4 写成 bit4；而官方 Python 驱动
> （`unit/relay4.py:102,137`）与官方 Arduino 库
> （[`Unit_4RELAY.cpp`](https://raw.githubusercontent.com/m5stack/M5Unit-RELAY/master/src/Unit_4RELAY.cpp)
> 的 `relayWrite`/`ledWrite`）都把 RELAY1 落在 bit0、LED1 落在 bit4。两个可执行官方驱动
> 互相一致，因此本批**采用驱动兼容位序**建模，产品页表格作为冲突来源登记，不能混写。
> Arduino 的 `relayAll()` 只写 `0x0f`（`Unit_4RELAY.cpp:49-52`），而 Python
> `set_relay_all(1)` 写 `0xFF`（`unit/relay4.py:162-174`），会额外点亮 LED，这也是
> 驱动差异而非硬件结论。

驱动读-改-写：`get_relay_state`/`set_relay_state` 读 `0x11` 后修改单 bit 再写回
（`:127-160`）；`set_relay_all(1)` 直接写 `0xFF`，会**同时点亮四路 LED**（`:162-174`），
这是官方驱动的可观测副作用，模型应保留。`get_mode/set_mode` 读/写 `0x10`
（`:70-91`）。

**官方 API**：`set_mode(mode)`、`get_mode()`、`set_relay_state(n,state)`、
`get_relay_state(n)`、`set_led_state(n,state)`、`get_led_state(n)`、`set_relay_all(state)`
（`unit/relay4.py:70,84,139,127,104,93,162`）；常量 `ASYNC_MODE=0`/`SYNC_MODE=1`
（`:48-49`）。

**主机输入**：无（纯输出，寄存器可读回）。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_RELAY4`，用现有
“`s->regs` + `snapshot_registers`（`:751`）+ `control_send/control_recv`（`:824/:917`）”
框架：
- 写 `0x10`/`0x11` 落寄存器；`0x11` 写入使 relay/LED 位变化时 `output_changed`
  （`:107`）累加 `output-transitions`。位序按**驱动兼容**：RELAYn→bit(n-1)、LEDn→bit(n+3)；
  不要照产品页表格的反序实现。
- 读返回当前寄存器快照（保证驱动读-改-写正确）。
- 输出的 QOM 观测：`relay-states`(4 bool array)、`led-states`(4 bool)、`mode`。
- Auto 模式语义是产品页声明（LED 跟随 relay）：实现时要么在 `0x11` 写入时按 mode
  推导 LED 位，要么只存寄存器并注明“仅寄存器语义”。建议保留页面语义并在 blocker
  里写清这是页面文本而非实测。

**可断言数据面标志**：写 `0x11` 的字节轨迹；读回 `0x11` = 期望 bit；`mode` 读回；
`output-transitions`；`transactions`。硬复位后的输出边界需与现有 relay 系列一致
（参考 patch `0087-unit-hard-reset-output-boundary` 的边界，但本 Unit 是 I2C 寄存器，
复位策略要在实现时明确定义为寄存器默认值，而非 pad 电平）。

**风险/未确认**：继电器触点寿命/吸合时间/耐压与负载**不建模**；`0x10` bit7..1 的
read-only 保留位被写入时的行为未在页面/驱动说明；Auto 模式的精确时序未验证。
`0x11` 位序存在**产品页表 vs 官方可执行驱动**冲突（见上框），本批按驱动建模。
地址 `0x26` 与 `weight-i2c` 冲突（§3）。

### 4.9 `weight-i2c` — Unit Weight-I2C（U180）

**官方**：[Unit Weight-I2C](https://docs.m5stack.com/en/unit/Unit-Weight%20I2C)
（2026-11-02）；SKU `U180`；`STM32F030F4P6` + `HX711`，24-bit，I2C `0x26`；
产品页 Protocol 段落标注 “v3 初版；v3/v4 移除 ADC 变化绝对值上限、支持负重量，协议
不变”。
**驱动**：`unit/weight_i2c.py`（快照 V2.1.5 与 master **不同**，见 §6）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器语义（逐行）**：

| 寄存器 | 编码 | 语义 | 证据（快照行号） |
| --- | --- | --- | --- |
| `0x00` ADC | `<I`，4 字节小端 | HX711 原始 ADC | `unit/weight_i2c.py:43-47` |
| `0x10` Weight | `<f`，4 字节小端 float | 重量（g，float） | `:49-53` |
| `0x40` GAP | `<f` 写入 | 校准斜率 | `:55-74` |
| `0x50` Offset | 写 `0x01` | 清零/去皮 | `:76-78` |
| `0x60` Weight×100 | `<i`，4 字节小端 | 重量×100 的整数 | `:80-84`（快照直接返回原始整数；master 改为 `/100`，见 §6） |
| `0x70` Weight string | 16 字节、NUL 结尾 ASCII | 重量字符串 | `:86-90` |
| `0x80` Filter IP | 1 字节 | 低通滤波开关 | `:92-101` |
| `0x81` Filter AVG | `<b`，0..50 | 平均滤波级数 | `:103-115` |
| `0x82` Filter EMA | `<b`，0..99 | EMA alpha | `:118-131` |
| `0xFE` FW / `0xFF` Addr | 1 字节 | 固件版本 / I2C 地址 | `:133-147` |

**官方 API**：`get_adc_raw()`、`get_weight_float()`、`get_weight_int()`、
`get_weight_str()`、`set_calibration()`、`set_reset_offset()`、
`set_lowpass_filter()/get_lowpass_filter()`、`set_average_filter_level()/
get_average_filter_level()`、`set_ema_filter_alpha()/get_ema_filter_alpha()`、
`get_device_spec()`、`set_i2c_address()`（`unit/weight_i2c.py:43,49,80,86,55,76,92,98,
103,113,118,129,133,140`）。

**主机输入**：`weight-g`（number，g，可负）、`adc-raw`（integer，HX711 原始值，
可选）。**一致性要求**：`0x10`、`0x60`、`0x70` 必须由同一个 `weight-g` 派生，不能
各自注入——否则 guest 会看到互相矛盾的读数（与 env-iii 的 QMP6988 raw/校准一致性
规则同类）。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_WEIGHT`，复用寄存器快照机制
（`:751`、`:824`、`:917`）：写 `0x40/0x50/0x80/0x81/0x82/0xFF` 落寄存器并记录写轨迹；
写 `0x50` 触发内部 offset 清零策略；读时把 `weight-g` 编码成 float32 LE、×100 int32
LE、ASCII 字符串三份一致字节。`0x00` 用 `adc-raw` fixture（或按 gap 派生，实现时二选
一并写注释）。

**可断言数据面标志**：三类重量寄存器读回的 float/int/string 相互一致；`0x40` 校准
写入轨迹（含负值场景，对应官方 v3/v4 说明）；`0xFE` 返回 fixture 版本；`0xFF` 地址
变更后 guest 重新 scan/读成功。

**风险/未确认**：
- `0x60` 的**语义边界**：快照 V2.1.5 驱动直接返回原始 int，master 驱动 `/100`；
  即该寄存器就是“×100”。实现时以 master 语义为准（`0x60 = round(weight_g*100)`），
  但要在 catalog 里显式记录这个版本差。
- 官方 protocol PDF（`M5Unit-WeightI2C/docs/Unit_Weight_I2C_Protocol.pdf`）只确认
  链接存在、**未读**；`0x00` ADC 与 float 之间的精确量化关系未核实。
- 地址 `0x26` 与 `4relay` 冲突（§3）。
- 秤标定、温漂、HX711 时序不在 I2C 数据面内，不建模。

### 4.10 `ncir2` — Unit NCIR2（U150）

**官方**：[Unit NCIR2](https://docs.m5stack.com/en/unit/NCIR2)（2026-11-02）；SKU
`U150`；`STM32F030F4P6` + `MLX90614`，I2C `0x5A`（可改），-70..380 °C，带蜂鸣器、
RGB、功能键；产品页链接官方 **NCIR-STM32 I2C Protocol PDF**（未读）。
**驱动**：`unit/ncir2.py`（快照与 master 相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器语义（逐行；均为“寄存器指针 + 读 N 字节”访问，`read_from_mem` `:208-215`）**：

| 寄存器 | 长度/编码 | 语义 | 证据 |
| --- | --- | --- | --- |
| `0x00` 温度 | int16 LE /100 | 目标温度 °C | `unit/ncir2.py:47-51` |
| `0x10` 发射率 | uint16 LE /65535 | 0.1..1 可写 | `:53-66` |
| `0x20` / `0x22` 低温/高温阈值 | int16 LE /100 | 报警阈值 | `:68-78` |
| `0x30` / `0x33` 报警 LED | 3 字节 RGB（大端写） | 低/高温报警灯色 | `:80-88` |
| `0x40/0x42/0x44` | uint16 LE / u8 | 低温报警频率/间隔/占空 | `:90-122` |
| `0x45/0x47/0x49` | 同上 | 高温报警频率/间隔/占空 | `:90-122` |
| `0x50/0x52/0x53` | uint16 LE / u8 | 蜂鸣器频率/占空/开关 | `:124-159` |
| `0x60` RGB | 3 字节 | 指示 RGB | `:161-170` |
| `0x70` 按键 | u8，0=按下 | `not read(...)` → pressed 为真 | `:172-177` |
| `0x80` 保存配置 | 写 `0x01` | 保存（驱动 sleep 200 ms） | `:179-183` |
| `0x90` 芯片温度 | int16 LE /100 | 芯片温度 °C | `:185-189` |
| `0xFE` / `0xFF` | u8 | 固件版本 / I2C 地址 | `:191-206` |

**官方 API**：`get_temperature_value`、`get_emissivity_value`/`set_emissivity_value`、
`get/set_temperature_threshold`、`get/set_temp_alarm_led`、高频/低频报警相关
get/set、`get/set_buzzer_*`、`get/set_rgb_led`、`get_button_status`、
`save_config_setting`、`get_chip_temperature`、`get_device_spec`、`set_i2c_address`
（`unit/ncir2.py:48-206`）。

**主机输入**：`object-c`（-70..380，默认 32）、`chip-c`（-40..125，默认 25）、
`button-pressed`（bool，默认 false）。**输出观测**：`rgb-led`（0xRRGGBB）、
`buzzer-on`（bool）。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_NCIR2`（寄存器文件 +
`snapshot_registers` `:751`）：首字节设指针、后续读写自动递增；读 `0x00`/`0x90` 由
fixture 温度编码 int16 LE；读 `0x70` 返回 `pressed?0:1`；写 `0x10/0x20/0x22/0x30/...`
落寄存器并让读回一致；写 `0x60` 触发 `output_changed`（`:107`）；写 `0xFF` 复用
现有 `i2c_slave_set_address` 先例（`:555-570` 的 JOYSTICK2 地址冲突检查）。温度换算
（/100）在 guest 侧完成，模型只给字节。

**可断言数据面标志**：`get_temperature_value` 串口值 = fixture `object-c`（±0.01）；
发射率/threshold 写后读回一致；RGB 写入轨迹与 `rgb-led`；按键读回；`0x80` 写 1
轨迹；`0xFE` fixture 版本。

**风险/未确认**：
- 官方 NCIR-STM32 协议 PDF **未读**；以上语义全部来自可执行驱动，寄存器“内部含义”
  若与 PDF 冲突，以驱动为准并记录差异。
- 报警逻辑（超阈值自动蜂鸣/RGB/保存）在 STM32 内部固件，本模型**只做寄存器回读，
  不模拟自动报警状态机**；这写进 blocker。
- 产品量程 -70..380 °C，但驱动把 `0x00` 按 **signed int16 ×0.01** 读取，编码上限
  +327.67 °C；超过该点的读数无法编码，保持 `unresolved`/饱和策略，fixture 不应注入
  380 °C 后声称“正确回读”。
- 地址 `0x5A` 与已登记 `ncir`（MLX90614）冲突（§3）。
- MLX90614 视场/发射率物理模型不建模。

### 4.11 `extio2` — Unit EXT.IO2（U011-B）

**官方**：[Unit EXT.IO2](https://docs.m5stack.com/en/unit/extio2)（2026-11-02）；
SKU `U011-B`；`STM32F030F4P6`，8 通道 IO 扩展，I2C `0x45`（可改），每通道支持
数字 IO / ADC / SERVO / RGB。产品页链接官方 I2C Protocol **v1** 与 **v3** PDF（v3 增加
PWM 模式与 IAP，未读）。
**驱动**：`unit/extio2.py`（快照 V2.1.5 与 master **不同**，见 §6）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`；
板上另有 2×5 排针 `IO0..IO7`。

**寄存器语义（逐行）**：

| 基准寄存器 | 编码 | 语义 | 证据（快照行号） |
| --- | --- | --- | --- |
| `0x00 + ch` | u8：0=IN/1=OUT/2=ANALOG/3=SERVO/4=NEOPIXEL | 通道模式 | `unit/extio2.py:13,96-101,108-109` |
| `0x10 + ch` | u8 | 数字输出 | `:14,111-112` |
| `0x20 + ch` | u8 | 数字输入读回 | `:15,133-134` |
| `0x30 + ch` | u8 | 8-bit ADC | `:16,136-137` |
| `0x40 + ch*2` | u16 LE | 12-bit ADC | `:17,139-140` |
| `0x50 + ch` | u8 | 舵机角度 | `:18,114-115` |
| `0x60 + ch*2` | u16 LE | 舵机脉宽 | `:19,117-118` |
| `0x70 + ch*3` | 3 字节（R,G,B 顺序由驱动 `write_rgb_led` 写 `r,g,b`） | 24-bit RGB | `:20,120-124` |
| `0xFE` | u8 | 固件版本 | `:21,151-152` |
| `0xFF` | u8 | I2C 地址 | `:22,126-128,154-155` |
| `0x90 + ch` / `0xA0` | u8 | **仅 master 驱动**：PWM duty / PWM freq | master `unit/extio2.py:21-22,314-384` |

**官方 API**：`set_config_mode`、`write_output_pin`、`write_servo_angle`、
`write_servo_pulse`、`write_rgb_led`、`set_address`、`get_config_mode`、
`read_input_pin`、`read_adc8_pin`、`read_adc12_pin`、`read_servo_angle`、
`read_servo_pulse`、`read_rgb_led`、`read_fw_version`、`get_address`、`pin(id,mode,value)`
（`unit/extio2.py:108-157`）；master 额外 `set/get_pwm_duty_cycle`、
`set/get_pwm_frequency`。

**主机输入**：`input-levels`（8×bool，默认 false）、`adc-mv`（8×number，0..3300）、
`fw-version`（integer 0..255，合成 fixture）。**输出观测**：`modes`（8×u8）、
`output-levels`（8×bool）、`servo-angles`（8×u8）、`servo-pulses`（8×u16）、
`rgb-leds`（8×u24）。master v3 的 PWM 寄存器（`0x90/0xA0`）未列入本批 outputs，
如实现再单独补契约。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_EXTIO2`（寄存器文件 +
snapshot）：写 `0x00-0x07`/`0x10-0x17`/`0x50-`/`0x60-`/`0x70-`/`0xFF` 落寄存器并更新
观测属性；读 `0x20-0x27` 取 fixture 输入电平、`0x30-0x37`/`0x40-0x4F` 取 fixture
ADC、`0xFE` 取 fixture 版本。模式与读回值之间不做“自动校验”（ST 固件内部规则未知），
只保证寄存器语义；`0xFF` 地址变更加上同 bus 冲突检查（参考 `:555-570`）。

**可断言数据面标志**：写 `0x00/0x10/0x50/0x60/0x70` 的字节轨迹；读 `0x20/0x30/0x40`
返回 fixture 值；`read_fw_version()` fixture 值；地址变更后原地址不再 ACK。

**风险/未确认**：
- 版本分叉：**快照驱动没有 PWM 寄存器**，master 驱动新增 `0x90/0xA0`；实现前必须
  选版本（建议按官方 Protocol v3 目标 + master 驱动）。
- 官方 Protocol v1/v3 PDF 未读；8/12-bit ADC 的满量程与参考电压、舵机角度/脉宽的
  单位与范围、RGB 字节顺序（驱动写 `r,g,b`，但芯片内部顺序未读 PDF）均保持
  `unresolved`；不要按常识补全。
- `write_rgb_led` 内部把 `value` 拆成 r/g/b 写入 3 字节（`:120-124`），读回
  `_read_u24` 解释为 `buf[0]<<16|buf[1]<<8|buf[2]`（`:193-199`），二者自洽。
- ST 固件 IAP/升级模式不建模。

### 4.12 `hbridge` — Unit HBridge（U160）

**官方**：[Unit HBridge](https://docs.m5stack.com/en/unit/Unit_HBridge)（2026-11-02）；
SKU `U160`；`STM32F030F4P6` + `RZ7899`，I2C `0x20`（DIP 可改 `0x20-0x2F`），
最大 3 A，支持正/反/刹车与 PWM 调速；产品页链接 Internal Firmware 仓库（无独立协议
PDF 链接）。
**驱动**：`unit/hbridge.py`（快照与 master 相同）。驱动含 “support v1.1” 段的
`get_vin_current()`，即同一驱动同时覆盖 U160 与 U160-V11。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`；
另有 `HV/GND/M-/M+` 端子。

**寄存器语义（逐行）**：

| 寄存器 | 编码 | 语义 | 证据 |
| --- | --- | --- | --- |
| `0x00` Direction | u8：0 stop / 1 forward / 2 reverse | 方向（驱动 docstring） | `unit/hbridge.py:12,58-63` |
| `0x01` PWM8 | u8，0..255 | 8-bit 占空 | `:13,65-70` |
| `0x02` PWM16 | u16 LE，0..65535 | 16-bit 占空 | `:14,72-77` |
| `0x04` PWM freq | u16 LE，驱动 clamp 100..10000 | PWM 频率 Hz | `:15,92-98` |
| `0x10` ADC8 | u8 | 8-bit ADC | `:16,100-117` |
| `0x20` ADC16 | u16 LE | 16-bit ADC | `:17,100-117` |
| `0x30` VIN current | float32 LE，4 字节 | 母线电流（v1.1 段） | `:18,120-125` |
| `0xFE` / `0xFF` | u8 | 固件版本 / I2C 地址 | `:19-20,129-135` |

地址范围 `0x20-0x2F` 由 `init_i2c_address()` 校验（`:36-44`）；写地址走 `0xFF`
（与其它 STM32 Unit 同型）。

**官方 API**：`set_direction(dir)`、`set_8bit_pwm(duty)`、`set_16bit_pwm(duty)`、
`set_percentage_pwm(duty,res)`、`set_pwm_freq(freq)`、`get_adc_value(raw,res)`、
`get_vin_current()`（v1.1）、`get_driver_config(reg)`、`get_device_status(mode)`、
`init_i2c_address()`（`unit/hbridge.py:58,65,72,79,92,100,120,46,129,36`）。

**主机输入**：`adc-mv`（number 0..3300，可选 8/16-bit 来源）、`vin-current-a`（number，
v1.1 fixture）。**输出观测**：`direction`（u8）、`pwm-duty-pct`（number）、
`pwm-frequency-hz`（number）。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_HBRIDGE`（寄存器文件 +
snapshot）：写 `0x00/0x01/0x02/0x04/0xFF` 落寄存器并更新观测属性；读
`0x10/0x20` 由 fixture ADC 编码、`0x30` 由 fixture 电流编码 float32、`0xFE`
fixture 版本。不要实现 RZ7899 电气/保护行为。

**可断言数据面标志**：`set_direction`/`set_16bit_pwm`/`set_pwm_freq` 写轨迹；
`get_adc_value()` 读回 fixture；`get_vin_current()` 读回 float fixture；
`direction`/`pwm-duty-pct`/`pwm-frequency-hz` 观测属性；地址变更到 `0x21` 后读成功。

**风险/未确认**：
- 产品页没有独立 I2C protocol PDF；寄存器语义只来自官方驱动。`0x30` 只在 v1.1
  硬件存在，U160（v1.0）读回值保持 `unresolved`（建议返回 0 并注明，或直接拒绝）。
- 方向/刹车时序、RZ7899 死区、过流/过温保护、电机等效负载**不建模**；`set_percentage_pwm`
  的 `res` 参数实现（`:79-90`）写入 `PWM8BIT` 的换算与 docstring 有出入（16-bit 分支
  仍写 8-bit 寄存器），实现时不要复刻此 bug，按显式寄存器语义处理。
- `get_adc_value()` 的换算 `3.3/res*val*11`（`:113-117`）是驱动启发式，不是校准结果。

## 5. 未确认项汇总（unresolved）

| # | 型号 | 未确认项 | 影响 | 建议处理 |
| --- | --- | --- | --- | --- |
| U1 | `hall` | 3×A3144E + 74HC08D 的组合逻辑与空间判据；指示灯不参与协议 | 只能建单线合成电平 | 模型只暴露白线电平，blocker 写明“多传感器逻辑未建” |
| U2 | `earth` | 数字输出高/低与湿/干的对应；`humidity()` 的 2900/1630 是驱动常量 | 不能断言“湿度检测” | `digital-level` 只做原始电平；不把 humidity 真值化 |
| U3 | `reflective-ir` | 数字输出极性与“检测到”的对应；IR 发射/接收器件型号；LM393 阈值电路未读 | 事件语义无法闭环 | 只暴露原始电平；`EVENT_*` 作为 guest 回调索引 |
| U4 | `vibrator` | 产品建议 10 kHz vs 驱动默认 100 Hz 的取舍；振动强度/电机参数 | 频率无“正确值” | 只观测 LEDC 配置，不做频域判断 |
| U5 | `accel` | `DEVID 0x00` 官方值；量程 bit 与 LSB 的关系；tap/free-fall 阈值语义 | 身份寄存器可能应为 fixture | DEVID 设 fixture/注明 unresolved；不做机械事件 |
| U6 | `4relay` | `0x11` 位序产品页表与官方 Python/Arduino 驱动相反；`0x10` 保留位写入行为；Auto 模式时序；触点电气 | 必须选定一条位序 | 采用驱动兼容位序（RELAYn=bit(n-1)、LEDn=bit(n+3)）并记录冲突 |
| U7 | `weight-i2c` | `0x60` 语义版本差（原始 int vs /100）；官方 v3 protocol PDF 未读；ADC↔float 量化 | 读回一致性要求 | 按 master `/100` 实现并记录版本；三类重量寄存器同源派生 |
| U8 | `ncir2` | 官方 NCIR-STM32 PDF 未读；内部自动报警状态机；地址 0x5A 冲突；产品 380 °C 量程 vs signed int16×0.01 编码上限 327.67 °C | 上端温度不可编码 | 只做寄存器回读；fixture 限制在可编码范围并注明 |
| U9 | `extio2` | 官方 v1/v3 PDF 未读；ADC 满量程/参考电压；舵机单位；RGB 内部字节序；快照 vs master 寄存器差 | 派生语义可能错 | 先实现寄存器/字节层，不实现单位换算；固定驱动版本 |
| U10 | `hbridge` | 无独立协议 PDF；v1.0 的 `0x30` 语义；方向/刹车细节；驱动百分比换算 bug | 观测值定义受限 | 寄存器层实现；`0x30` v1.0 返回 unresolved |
| U11 | `dlight` | 产品页 1..65535 lx vs `raw=lux*1.2` 在 16-bit raw 下的编码上限（约 54612 lx）；上电默认 MTreg | 量程上限不可编码 | fixture 限制在可编码范围；上限标 unresolved |

另有跨型号未确认：

- 12 款所链接的 datasheet/原理图/协议 PDF **一律未逐页阅读**，按仓库既有方法只登记
  `linked-by-verified-product-page`，不据此扩展寄存器结论。
- GPIO 型号的电气电平（5V 供电标签 ≠ 3.3V 逻辑）、驱动能力、保护电路都不建模。
- 所有 `default` 都是合成 UI/测试初值，不是实物出厂默认。

## 6. 驱动版本交叉核对（快照 vs 官方 master）

2026-11-02 下载 master 原文比对结果：

| 文件 | 结果 | 差异要点 |
| --- | --- | --- |
| `unit/ssr.py`、`unit/vibrator.py`、`unit/earth.py`、`unit/hall_effect.py`、`unit/reflective_ir.py`、`unit/dlight.py`、`unit/ncir2.py`、`unit/relay4.py`、`unit/hbridge.py` | 与快照**逐字节相同** | — |
| `unit/accel.py` | 不同 | master 增加完整 docstring 与 `enable_*_detection` 包装；寄存器路径不变 |
| `unit/extio2.py` | 不同 | master 新增 PWM 寄存器 `0x90`/`0xA0` 与 `set/get_pwm_*`、`set/get_pwm_frequency` |
| `unit/weight_i2c.py` | 不同 | `0x60`：master `int(raw/100)`，快照直接返回 raw；`0x40` 校准公式去掉 `abs()`；导入改为 `unit.pahub`/`unit.unit_helper` |
| `driver/adxl34x.py` | 不同 | 仅注释/文档，寄存器常量与换算未变 |
| `driver/bh1750.py`、`driver/haptic.py` | 相同 | — |

**实现结论**：先固定 `unit/extio2.py`、`unit/weight_i2c.py`、`unit/accel.py` 的版本
（建议 master），把所选文件的 SHA-256 写进 catalog evidence；本页行号锚定 V2.1.5
快照，若改用 master，需要按上表重新锚定行号（extio2 新增行、weight 单行、accel
docstring 偏移）。

## 7. 落地顺序建议

1. **A 类 5 款先落**（`ssr` → `hall` → `earth` → `reflective-ir` → `vibrator`）：
   全部复用现成 GPIO/PWM/继电器分支，一天内可完成 catalog + QEMU + 设备级用例骨架；
   `ssr` 与 `hall` 适合作为首批“zero-new-data-plane”验收样板。
2. **B 类 4 款次之**（`4relay` → `dlight` → `accel` → `weight-i2c`）：`4relay` 有官方
   页面寄存器表，风险最低；`dlight` 是单命令传感器；`accel` 是标准指针寄存器；
   `weight-i2c` 需要先定 `0x60` 版本语义。
3. **C 类 3 款最后**（`ncir2` → `extio2` → `hbridge`）：都依赖 STM32 寄存器文件
   框架，建议先把 `m5_unit_i2c_controls.c` 的通用寄存器文件做成可复用 helper（现在
   `snapshot_registers` `:751` 与 `control_send` `:824` 已具备雏形），再逐个接。
4. **地址冲突**：`4relay`/`weight-i2c` 与 `ncir2`/`ncir` 在建 fixture 和文档时先声明；
   不要同时挂同一 bus 做 Demo。
5. **实现后再回填** catalog `model_status`/`runtime.status` 与 runtime-profiles；
   本报告与 catalog 草稿只到 `confirmed-contract` + `planned`，不授权任何
   `simulated`/PASS 声明。

### 实现状态（2026-11-02 追加）

A 类 5 款（`ssr`、`vibrator`、`earth`、`hall`、`reflective-ir`）的 QEMU 控制器级
数据面已由
[`0114-unit-gpio-batch1.patch`](../../patches/qemu-m5stack-peripherals/0114-unit-gpio-batch1.patch)
注册（native layer 到 `0109` + `0110/0111/0112` 之上；`0113` 由 Basic v2.7 并行
合入，两者都是 native-only、不进 `sources.lock`/WASM 构建）。catalog 与
runtime profile 仍保持 `planned`/`unsupported`，Device Service 以
`runtime_model_gap` 拒绝挂载；在 guest/Device Service device-local 证据取得前不
升级状态。B/C 类 7 款仍停留在本报告的研究结论。

## 8. 官方来源清单（本批引用）

产品页（均 2026-11-02 读取）：

- SSR `https://docs.m5stack.com/en/unit/ssr`
- Vibrator `https://docs.m5stack.com/en/unit/vibrator`
- Earth `https://docs.m5stack.com/en/unit/earth`
- Hall `https://docs.m5stack.com/en/unit/hall`
- Reflective IR `https://docs.m5stack.com/en/unit/Unit-Reflective%20IR`
- DLight `https://docs.m5stack.com/en/unit/DLight%20Unit`
- Accel `https://docs.m5stack.com/en/unit/accel`
- NCIR2 `https://docs.m5stack.com/en/unit/NCIR2`
- EXT.IO2 `https://docs.m5stack.com/en/unit/extio2`
- 4Relay `https://docs.m5stack.com/en/unit/4relay`
- Weight-I2C `https://docs.m5stack.com/en/unit/Unit-Weight%20I2C`
- HBridge `https://docs.m5stack.com/en/unit/Unit_HBridge`
- I2C 地址总表 `https://docs.m5stack.com/en/product_i2c_addr`

官方驱动（master 原文 URL；`sha256` 为 master 内容哈希，2026-11-02 下载计算；
快照 V2.1.5 与 master 不同的 3 个文件已在 §6 标出）：

| 文件 | SHA-256（master） |
| --- | --- |
| `unit/ssr.py` | `4300fa901b16bd923c5a690dacb86cf09037a6e8a8ff5ebe78a13178799c9181` |
| `unit/vibrator.py` | `7a4b1f1e14be1b1db338aefb874ea4999791581622c28c51025a6f5bef71d4a2` |
| `unit/earth.py` | `d7938ae04194bb4588a8c24c17099a15f909f56f977067d812b312277e3de382` |
| `unit/hall_effect.py` | `1015507e975a48a4be9b5d3c871fb01630f7eec7c17dac9b4d4e11edb255132c` |
| `unit/reflective_ir.py` | `dd0e19937f5badab9e991f95376c070b25c2d35f2cd01354d66867048cb86aa6` |
| `unit/dlight.py` | `a4371a3bd3dd8dcd7dc17b6ae4e85753432354b6b15ceeb01ca85f4ac28a399c` |
| `unit/accel.py` | `0a6bc7746d30bbbcd78d655d3137da23dad56c43bef74806ef8415344e7c1d68` |
| `unit/ncir2.py` | `9acd068c6a70695cd9400ced7aa6eec4249b60bb75f2729d8533990062c8f60c` |
| `unit/extio2.py` | `d1781a00a000813983ffe34fd2a47df0829108f4c0b8653c3a40ffe8cbc4e31d` |
| `unit/relay4.py` | `8a4fee2b141724bf55585d9da0e0fc867d6066b934218c05036eb29f4318ccd7` |
| `unit/weight_i2c.py` | `26c631cea86185192a44cc05c77ef44d5a911aa522413938fa815893805c1ddf` |
| `unit/hbridge.py` | `3835ba81f823b3d29aecc9160ba2e76687048bb358d3e2a87dc461783bec18c7` |
| `driver/bh1750.py` | `3d044da2aeeef464c3e05e0fec1c9158c6ee56b3684b20c3acbfe0b4c0ad5e12` |
| `driver/haptic.py` | `a443d3d947c9821208d3eac4835e0ef8e475c5cc54e0619ef159971b78e70148` |
| `driver/adxl34x.py` | `1aa7d0b796922ff9aabaa68e510463bd94cfbbda44c87dbed6aacae4ca316bb7` |

官方协议/数据手册链接（**仅确认链接存在，未逐页阅读**）：

- SSR：`BT136S` `.../datasheet/unit/ssr/C23427_BT136S.PDF`、`MOC3043` `.../C41809_MOC3043SR2M_2015-01-24.PDF`
- Hall：`A3144E` `.../datasheet/unit/3141Thru3144E_HALL.PDF`
- DLight：`BH1750FVI` `.../datasheet/hat/BH1750FVI.pdf`
- Accel：`ADXL345` `.../datasheet/unit/ADXL345_en.pdf`
- NCIR2：`Sch_UNIT-NCIR2.pdf`、`NCIR-STM32.pdf`、`STM32F030F4P6.PDF`、`MLX90614` datasheet
- EXT.IO2：`Sch_UNIT-EXTIO2.pdf`、`EXTIO2_V1_Protocol.pdf`、`EXTIO2_V3_Protocol.pdf`
- 4Relay：`Sch_UNIT-4RELAY.pdf`（协议表在产品页内嵌，非 PDF；官方 Arduino 库
  `https://github.com/m5stack/M5Unit-RELAY` 的 `Unit_4RELAY.cpp` 已读，用于位序交叉核对）
- Weight-I2C：`SCH_UNIT_WEIGHT_I2C.pdf`、`HX711_en.pdf`、`Unit_Weight_I2C_Protocol.pdf`
- HBridge：`STM32F030F4P6.PDF`、`RZ7899.PDF`、Internal Firmware 仓库
- Earth：`U019_UNIT_EARTH_SCHE.pdf`
- Reflective IR：`SCH_UNIT_Reflective_IR_V1.0.pdf`
- Vibrator：`Unit_Vibrator.pdf`（无 IC datasheet）

## 9. 复现方式

- 未登记差集：对 `platform/web/vendor/m5stack-models/catalog/products.json` 取
  `category=="unit"` 的 id 集合，减去 `platform/units/catalog.json` 的 `units[].id`。
- 驱动哈希：`shasum -a 256 <官方源码根>/m5stack/libs/unit/<file>.py`（快照与 master
  相同的文件两者一致；不同的 3 个文件哈希见上表）。
- 本报告不产生也不要求任何 QEMU/固件运行证据；实现后的验收必须按仓库
  `AGENTS.md` 的 Device Service 路线另做 device-local 证据。

## 10. B 类 QEMU 实现状态（0119，2026-11-02）

本批 B 类 4 款已由
[`0119-unit-i2c-batch2.patch`](../../patches/qemu-m5stack-peripherals/0119-unit-i2c-batch2.patch)
接入 QEMU I2C slave 事务数据面。补丁 base 为 native-only 序列
`0109+0110/0111/0112/0113/0114/0116`（不依赖 `0115`；`0117`/`0118` 是并行层）。
**尚未采集 guest/Device Service 证据**，因此
`platform/units/catalog.json` 的 4 条 `model_status`/`runtime.status` 和
`platform/units/runtime-profiles.json` 的 `status` 均保持 `planned`、hosts 为空；
离线 QOM smoke 只验证属性注册、读写、范围拒绝和只读拒绝，不构成功能 PASS。

| Unit | 0119 事务模型 | QOM fixtures/读数 | 仍需 guest 证据 / 边界 |
| --- | --- | --- | --- |
| `dlight` | BH1750 0x23：单字节命令机（0x00/0x01/0x07、continuous 0x10/0x11/0x13、one-time 0x20/0x21/0x23）、MTreg 0x40/0x60 两字节编码、转换窗口 | 输入 `illuminance-lx`；模型内按 bh1750 驱动公式反算 raw=lux*1.2*sensitivity（H-res2 ×2）并裁剪到 u16，H 180ms/L 24ms ÷ sensitivity 的窗口只由模型自身计时 | 驱动读到的 2 字节 big-endian raw 尚未经 guest I2C 回放；power-on 默认 MTreg、数据手册 timing、照度/光学量值仍未确认 |
| `accel` | ADXL345 0x53：寄存器指针/自增、POWER_CTL(0x2d)/DATA_FORMAT(0x31) 存储、0x32–0x37 六字节合成、INT_SOURCE(0x30) 读清 | 输入 `accel-x-g/y-g/z-g`（±16g，raw=round(g*250) 的 4mg/LSB 换算）与 `int-source`（中断源 bitmask fixture，读 0x30 后清零） | 6 字节 data/INT_SOURCE 的 guest 读路径尚未回放；DEVID(0x00) 保持 reserved 读回 0xff，明确不猜 0xE5；活动/tap/free-fall 检测器与物理加速度未建模 |
| `4relay` | U097 0x26：0x10 mode 读写、0x11 relay+LED 读改写回环，逐通道 QOM 状态 | 输出 `relay-1..4-level`、`led-1..4-level`、`mode`（只读）；编码按两份官方可执行驱动的 `RELAYn=bit(n-1)`/`LEDn=bit(n+3)`，即 RELAY1=bit0/LED1=bit4 | 产品页 Protocol 表的反向位序（RELAY1=bit3/LED1=bit7）已作为冲突登记，未混用；guest 写 0x11/0x10 的读回与继电器触点/负载/切换时序/NOT RUN |
| `weight-i2c` | U180 0x26：0x00 u32 ADC、0x10 f32 grams、0x40 f32 gap（存）、0x50 offset reset（存）、0x60 int32 weight×100、0x70 16B ASCII、0x80/0x81/0x82 滤波（存）、0xFE fw、0xFF 地址 | 输入 `weight-g`（±1e6 g）、`adc-raw`（u32）、`weight-fw`（0–255，默认 3）；读数由 fixture 派生 | 0x60 采用 master 驱动 weight×100 语义，但 protocol-PDF/driver 版本差异仍是 unresolved；0x40/0x50 只存储不加到 weight（校准运算 NOT RUN）；0x70 为合成 `"%.3f"` 格式；默认 0x26 与 4relay 同总线冲突 |

共同边界：4 款都只是控制器可见的事务模型，不是电气/机械/光学/称重模型；
在没有 guest 与 Device Service 证据前不得升级为 `implemented`/`simulated`，
也不得把 QOM fixture 读数当作传感器测量值。下一步验收应按 `AGENTS.md` 的
独立 Device Service 路线逐款 attach、运行官方 UIFlow2 驱动并记录 serial/QOM/
帧/ZIP 证据后再升级 profile。

## 11. C 类 QEMU 实现状态（0122，2026-11-02）

C 类 3 款已由
[`0123-unit-i2c-batch3.patch`](../../patches/qemu-m5stack-peripherals/0123-unit-i2c-batch3.patch)
接入 QEMU I2C 寄存器事务数据面；补丁 base 为 canonical native layer `75f1d24`（`0109+0110…0119`）
+ 已合入的 `0120` 修复（`0121` 是并行预留层，不依赖）。**尚未采集 guest/Device Service
证据**，因此 `platform/units/catalog.json` 3 条 `model_status`/`runtime.status` 与
`platform/units/runtime-profiles.json` 3 条均保持 `planned`、hosts 为空。离线 QOM smoke
只验证属性注册、fixture 读写、范围拒绝和只读拒绝（3/3 PASS），不构成功能 PASS。

| Unit | 0122 事务模型 | QOM fixtures/观测 | 仍需 guest 证据 / unresolved 边界 |
| --- | --- | --- | --- |
| `ncir2` U150 (0x5A) | 0x00/0x90 温度字节由 fixture 编码 int16 LE ×0.01；0x10 发射率、0x20/0x22 阈值、0x30/0x33 报警 LED、0x40–0x53 报警/蜂鸣器参数、0x60 RGB、0x70 按键、0x80 保存、0xFE/0xFF 身份；只读 fixture 寄存器拒写 | 输入 `object-c`/`chip-c`/`button-pressed`；观测 `rgb-led`、`buzzer-on`（寄存器回读） | 零 guest 回放；STM32 报警状态机不建模；NCIR-STM32 PDF 未读；0x5A 与已登记 ncir(MLX90614) 地址冲突；-70..380°C 与 signed int16 ×0.01 编码上限 +327.67°C 的 top-range 语义 unresolved（模型饱和而不声明 380°C 正确回读）；红外光学/发射率物理 NOT RUN |
| `extio2` U011-B (0x45) | 8 通道 0x00 模式/0x10 输出/0x50 舵机角/0x60 舵机脉宽/0x70 RGB 寄存器；0x20 输入、0x30/0x40 ADC 由 fixture 派生；0xFE fw、0xFF 地址；master v3 的 0x90/0xA0 PWM 字节 | 输入 `input-levels`/`adc-mv`/`fw-version`；观测 `modes`/`output-levels`/`servo-angles`/`servo-pulses`/`rgb-leds` | 零 guest 回放；Protocol v1/v3 PDF 未读；8/12-bit ADC 满量程与参考电压、舵机角度/脉宽单位、芯片内部 RGB 字节序均 unresolved；冻结固件驱动是否含 0x90/0xA0 未确认；ST IAP/升级不建模 |
| `hbridge` U160 (0x20) | 0x00 方向、0x01 PWM8、0x02 PWM16、0x04 频率写；0x10 ADC8、0x20 ADC16、0x30 VIN 电流（v1.1）由 fixture 派生；0xFE/0xFF 身份，地址变更加 0x20–0x2F 限制 | 输入 `adc-mv`/`vin-current-a`；观测 `direction`/`pwm-duty-pct`/`pwm-frequency-hz` | 零 guest 回放；无独立 protocol PDF，仅按可执行驱动；0x30 仅 v1.1 硬件有、U160 v1.0 读回语义 unresolved（本模型返回 fixture float）；方向/刹车时序、RZ7899 死区/保护、电机电气行为 NOT RUN；`set_percentage_pwm` 的 16-bit 分支写 8-bit 寄存器是驱动 bug，模型只保留显式寄存器语义 |

共同边界：3 款都只是控制器可见的寄存器事务模型，不是红外/电气/机械/无线模型；
地址冲突（0x5A 与 ncir）、unresolved 寄存器语义与饱和策略必须随 catalog 一起读；
在没有 guest 与 Device Service 证据前不得升级为 `implemented`/`simulated`，也不得把
QOM fixture 读数当作传感器/电机测量值。
