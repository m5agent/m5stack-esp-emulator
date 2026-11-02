# Unit 第二批（12 款）官方协议研究报告

日期：`2026-11-02`。归属团队任务 `task-18`，工作树
`esp-emulator-unit-research2`，分支 `m5agent/unit-research-batch2`（基于
`origin/main` `3030576e`）。

本页是**实现前**的协议研究，不是运行时或硬件 PASS。本报告没有运行 QEMU、固件或
Device Service，没有修改 `platform/units/catalog.json`、`runtime-profiles.json`、
QEMU 源码或测试；配套的 catalog 草稿单独放在
[`2026-11-02-batch2-catalog-draft.json`](2026-11-02-batch2-catalog-draft.json)。
第一批 12 款（`ssr`/`vibrator`/`earth`/`hall`/`reflective-ir`/`dlight`/`accel`/
`4relay`/`weight-i2c`/`ncir2`/`extio2`/`hbridge`）已在本批开始前登记，本批不再
重复。

## 0. 结论摘要

从未登记的 Unit 中选 12 款。筛选口径：官方 UIFlow2 源码里有**可执行驱动**，协议
能落到现有三个 QEMU Unit 模型分支（`m5_unit_gpio.c` / `m5_unit_i2c_sensors.c` /
`m5_unit_i2c_controls.c`）或同一寄存器机框架的低成本扩展；排除需要新控制器拓扑
（CAN/USB/摄像头/SPI 显示/蜂窝/LoRa）或需要新传感器补偿算法的型号。本批 **10 款 I2C（其中 `env`/`ameter` 为双从机/双地址）、1 款 ADC+GPIO、
1 款 ADC+RMT(SK6812)**，没有引入新 SoC 控制器拓扑。

| # | Unit id | SKU | 名称 | 总线 / 地址 | 复杂度 | 建议归属 QEMU 文件 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `joystick` | U024 | Unit Joystick | `i2c` / `0x52` | A 低 | `m5_unit_i2c_controls.c`（直接复用 `CONTROL_JOYSTICK`） |
| 2 | `dac` | U012 | Unit DAC | `i2c` / `0x60` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_DAC`） |
| 3 | `watering` | U101 | Unit Watering | `gpio-adc` / — | A 低 | `m5_unit_gpio.c`（新增 pump 输出观测分支） |
| 4 | `fader` | U123 | Unit Fader | `gpio-adc + rmt` / — | B 中低 | `m5_unit_gpio.c`（ADC + SK6812 两分支合一） |
| 5 | `bps` | U090 | Unit Mini BPS | `i2c` / `0x76`（QMP6988 变体争议） | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_BMP280`） |
| 6 | `env` | U001 | Unit ENV | `i2c` / `0x5C` + `0x76` | C 中 | `m5_unit_i2c_sensors.c`（新增 `US_DHT12` + 双从机接入） |
| 7 | `adc-v11` | U013-V11 | Unit ADC v1.1 | `i2c` / `0x48` | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_ADS1110`） |
| 8 | `extencoder` | U161 | Unit ExtEncoder | `i2c` / `0x59` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_EXTENCODER`） |
| 9 | `ain4-20ma` | U162 | Unit AIN4-20mA | `i2c` / `0x55` | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_AIN420`） |
| 10 | `acssr` | U139 | Unit ACSSR | `i2c` / `0x50` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_ACSSR`） |
| 11 | `ameter` | U086 | Unit AMeter | `i2c` / `0x48` + `0x51` | C 中 | `m5_unit_i2c_sensors.c`（ADS1115 + EEPROM 双地址） |
| 12 | `gesture` | U127 | Unit Gesture | `i2c` / `0x73` | C 中 | `m5_unit_i2c_sensors.c`（新增 `US_PAJ7620`） |

复杂度定义：

- **A 低**：只注册 id 并复用现有数据面分支，预计 QEMU 侧改动 `< 15` 行，不需要新的
  寄存器状态或控制器行为。
- **B 中低**：新增一个 kind / 分支，但直接复用现有寄存器指针、快照、QOM 属性框架；
  读/写字节语义是确定性的。
- **C 中**：新增完整寄存器文件或多从机/多 bank 状态（DHT12+BMP280 双从机、
  ADS1115+EEPROM 双地址、PAJ7620 219 项初始化 + bank 切换），但仍在同一个 I2C
  slave 框架内，不涉及新的 SoC 控制器拓扑。

未登记差集口径（可复算）：`platform/web/vendor/m5stack-models/catalog/products.json`
的 `category=="unit"` 共 **184** 款；`platform/units/catalog.json` 登记 **46** 款，其中
`servo8-hat` 在 vendor 目录里属于 HAT 条目、不在 unit 类别；故未登记 = 184 − 45 =
**139** 款。任务描述写的 138 与本次精确差集差 1 款（与第一批报告的 151 vs 150 同类
口径差异），不影响选型。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

- 官方 UIFlow2 源码快照：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git 远端 `https://github.com/rodrigob/uiflow_micropython.git`，HEAD
  `528edd8a06d2556c8e753c8e4978179bbb12b5ba`，`m5stack/version.txt` 为 `V2.1.5`）。
  本页所有 `m5stack/libs/...:行号` 都**锚定这个快照**。
- 官方 GitHub master 交叉核对：2026-11-02 用
  `https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/...`
  逐文件下载比对本批 12 个 unit 驱动及其 8 个依赖驱动（共 20 个文件）。15 个逐字节
  相同；5 个不同（明细见 §6）。
- 官方产品页：2026-11-02 直接抓取 12 个 `officialDocs` 页面，SKU、PinMap、芯片名
  与部分协议表从页面原文核对；页面链接的 datasheet/协议 PDF **未逐页阅读**，按仓库
  既有方法标记为 `linked-by-verified-product-page`。
- 官方 I2C 地址总表 `https://docs.m5stack.com/en/product_i2c_addr`（2026-11-02）
  用于交叉核对芯片与 7-bit 地址。该总表比部分产品页更新，个别型号出现
  **产品页/总表/驱动三方不一致**，一律写进 §5 的 `unresolved`，不按名字猜协议。
- 现有 QEMU 模型参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu/hw/m5stopwatch/`
  （只读快照，行号以该 worktree 当前状态为准；本报告未修改）。

### 1.2 逐款证据等级

| 等级 | 含义 | 本批型号 |
| --- | --- | --- |
| E1 | 官方 PinMap + 可执行驱动逐行完整语义（寄存器/命令/编码），无需 PDF 即能确定实现所需的通信语义 | `joystick` `dac` `watering` `fader` |
| E2 | 官方 PinMap + 可执行驱动逐行完整语义，但**官方协议文档/数据手册只确认链接存在、未读**，或存在必须显式标注的未决字段 | `bps` `env` `adc-v11` `extencoder` `ain4-20ma` `acssr` `ameter` `gesture` |
| E3 | 只能读到 API/字段名，关键语义 unknown | 本批没有整款 E3；单字段 unresolved 见 §5 |

本报告禁止按产品名推断协议：每个型号都至少能落到一个官方驱动文件的具体行，或者
明确写进 §5 的 `unresolved`。

### 1.3 主机侧约定（本批全部适用）

- UIFlow GPIO `port` 元组为 `(white, yellow)`：`port[0]` 对应 Grove 白线，`port[1]`
  对应黄线。本批的寄存器/引脚结论都按这个顺序复算，未从颜色名称反推。
- I2C 地址一律写 **7-bit**（`0x52` 等）；驱动里的 `readfrom_mem(addr, reg, n)` 是
  “写寄存器指针 + 重复起始读 n 字节”的语义，模型必须按真实总线字节序列实现。
- 所有主机输入默认值都是**合成测试 fixture**，不是实测硬件默认值；产品页的精度、
  量程、电气参数不进入模型断言。
- 虚拟数据面 PASS 与硬件测量是两类结论；本页不产生任何一类 PASS。

## 2. 与现有 QEMU Unit 模型的复用映射

以下是 `/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu/hw/m5stopwatch/`
下现有模型的接入点（只读参考，本报告未修改）。行号以该 worktree 当前快照为准。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c` | `UNIT_RELAY` 输出观测/复位边界 `:160-200`；QOM `output-transitions` `:364`、`output-level` `:369-373`；id 分派 `:466-470`（`relay`/`ssr`/`2relay`）；`m5_unit_extra_realize` `:507` | `acssr` 的继电器观测语义参考 |
| `m5_unit_gpio.c` | 支持 id 列表 `:606-613`；ADC 采样钩子 `m5_unit_adc_sample` `:742`、PWM 观察 `:763`、UART TX 捕获 `:850`/RX 注入 `:890-897`；QOM 数字输入 `:626-658`、ADC 属性 `:945-951`、RMT 脉冲 `:955-959`、RGB 帧 `:961-969`；realize 分支 `:919`（flashlight）、`:926`（pir）、`:937`（双键）、`:945-951`（angle/light/earth/reflective-ir）、`:953-957`（fan/buzzer/vibrator）、`:961-969`（rgb/key） | `watering` `fader` |
| `m5_unit_i2c_sensors.c` | kind 枚举 `:22-24`；`add_number` `:117`；采样/时序更新 `:273-350`；`sensor_send` `:410`；`sensor_recv` `:572`；支持 id `:650-657`；realize `:660+`（`color`/`tof`/`ncir`/`heart`/`tvoc`/`ultrasonic-i2c`/`thermal`/`dlight`/`accel`） | `bps` `env` `adc-v11` `ain4-20ma` `ameter` `gesture` |
| `m5_unit_i2c_controls.c` | kind 枚举 `:35-40`；寄存器快照 `:797-850`；`control_send` `:879`；`control_recv` `:997`；支持 id `:1053-1059`；realize `:1063+`；地址占用检查先例 `:576-589`、`:949-951`、`:979-981` | `joystick` `dac` `extencoder` `acssr` |

复用原则（避免把模型写成 host 侧假值）：

- GPIO/ADC/PWM/RMT 型号必须继续走 `esp32_gpio_set_input`、
  `esp32_gpio_pad_observer`、`m5_unit_adc_sample`、`m5_unit_pwm_observe` 这些
  **控制器级**钩子；不新增直接改 guest 返回值的属性。
- I2C 型号必须在 `I2CSlaveClass.send/recv` 里实现真实总线字节语义（寄存器指针、
  自动递增、快照、读清），QOM 属性只做注入/观测。
- 双从机/双地址型号（`env`、`ameter`、`bps` 的变体）必须显式建模两个地址的
  slave 实例和地址占用检查，禁止用“同一 slave 猜地址”绕过。

## 3. 地址与总线冲突

本批新增型号与已登记型号的默认 7-bit 地址冲突（同一条被动 HUB/同一 bus 不能共存）：

| 地址 | 本批型号 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x52` | `joystick` U024 | `joystick-v11` U024-C（同地址，读 `0x52` 3 字节） | 产品页协议表；`unit/joystick.py:9,19`；`units/catalog.json` joystick-v11 |
| `0x50` | `acssr` U139 | `nfc` U049（ST25R3916，`0x50`） | 产品页 I2C 0x50；官方 I2C 总表；`units/catalog.json` nfc |
| `0x70` | `bps`（QMP6988 回退分支） | `env-iii` U001-C（QMP6988，`0x70`） | `unit/bps.py:12-13,20`；官方 I2C 总表 |
| `0x48` | `adc-v11`、`ameter`(ADS1115) | 两者互相冲突；无已登记冲突 | 产品页 + 官方 I2C 总表 |
| `0x51` | `ameter`(EEPROM) | 无已登记冲突（`bm8563`/`rx8130` 等 RTC 在整机总线，不在 Unit 端口默认端点） | 产品页；官方 I2C 总表 |
| `0x5C`、`0x76` | `env`（DHT12 + BMP280） | 无；但 `bps` 也占 `0x76` → `env` 与 `bps` 同 bus 冲突 | 产品页；`driver/dht12.py:27`；`driver/bmp280.py:29` |
| `0x59` | `extencoder` U161 | 无；地址可编程 | 官方 I2C 总表 `Programmable address`；`unit/extencoder.py:98` |
| `0x55` | `ain4-20ma` U162 | 无；地址可编程 | 官方 I2C 总表 `Programmable address`；`unit/ain4_20ma.py:113` |
| `0x60` | `dac` U012 | 无 | 产品页；`driver/mcp4725.py:11` |
| `0x73` | `gesture` U127 | 无 | 产品页；`driver/paj7620.py:9` |

实现建议：`joystick` 与 `joystick-v11`、`acssr` 与 `nfc`、`env` 与 `bps` 必须按
“单 bus 只挂一个”建模并写进 fixture 校验；双地址 unit（`env`/`ameter`）必须两个
地址都做占用检查，不能只查主地址。不要为了凑多 Unit 放宽地址冲突检查（现有
`m5_unit_i2c_controls.c` 已有同 bus 地址占用检查的先例，见 `:576-589` JOYSTICK2 分支）。

## 4. 各款协议详情

### 4.1 `joystick` — Unit Joystick（U024）

**官方**：[Unit Joystick](https://docs.m5stack.com/en/unit/joystick)（2026-11-02 读取）；
SKU `U024`；协议类型 I2C、地址 `0x52`；X/Y 输出 0–255、Z 按键 0/1。官方 I2C 总表
只列出 `Unit Joystick v1.1`（U024-C，MEGA8A `0x52`），未列出原版 U024 的芯片 →
芯片身份 `unresolved`（视觉库存名称为 “MEGA328P original”，仅作线索）。
**驱动**：`m5stack/libs/unit/joystick.py`（51 行，快照与 master 逐字节相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址/扫描 | `unit/joystick.py:9-12` | 默认 `0x52`，`scan()` 不含则抛 `UnitError` |
| 读取 | `:18-19` | `readfrom_mem_into(0x52, 0x52, 3)` → 从寄存器 `0x52` 读 3 字节 |
| X/Y 原始 | `:21-27` | `buffer[0]`=X raw，`buffer[1]`=Y raw，uint8 |
| X/Y 映射 | `:29-41` | `x = raw - 128`；`swap_x` 时 `-(raw-127)`；Y 同理 |
| 按键 | `:49-51` | `bool(buffer[2])` |
| 方向交换 | `:43-47` | 纯软件标志，不产生总线事务 |

**官方 API**：`get_x_raw()`、`get_y_raw()`、`get_x()`、`get_y()`、
`get_button_status()`、`swap_x()`、`swap_y()`（`unit/joystick.py:21,25,29,36,43,46,49`）。

**主机输入**：`x-raw`（0..255）、`y-raw`（0..255）、`button-raw`（0..255）。

**QEMU 建议**：**直接复用** `CONTROL_JOYSTICK`。现有
`m5_unit_i2c_controls.c:1073-1076` 已为 `joystick-v11` 建立 `0x52` + 3 字节
`joystick[]` 快照（`:809` 拷贝到 `read_snapshot[0x52..0x54]`），`:954` 对
JOYSTICK 写事务返回 ACK；QOM 已有 `x-raw`/`y-raw`/`button-raw`。只需在支持 id
列表 `:1053-1059` 增加 `"joystick"` 并在 realize 分支把 id 映射到
`CONTROL_JOYSTICK`（或直接把 `"joystick"` 当 `joystick-v11` 的别名），不需要新
kind。与 `joystick-v11` 的地址冲突按 §3 处理。

**可断言数据面标志**：`x-raw`/`y-raw`/`button-raw`（host 注入后 guest
`get_x_raw()`/`get_y_raw()`/`get_button_status()` 读回）；`transactions`、
`read-bytes`（每次读取 +3）、`written-bytes`（扫描/读指针写 +1）；无输出型
transition。

**风险/未确认**：原版 U024 的 MCU/固件身份官方总表未列（`unresolved`）；按键字节
的极性只有 `bool()` 语义，是否 active-low 未验证（沿用 joystick-v11 的“保留 raw
byte 直到极性显式确认”策略）；机械行程与电位器线性度不建模。

### 4.2 `dac` — Unit DAC（U012）

**官方**：[Unit DAC](https://docs.m5stack.com/en/unit/dac)（2026-11-02）；SKU
`U012`；MCP4725 12-bit DAC，I2C `0x60`，0–3.3V 输出，带 EEPROM；官方 I2C 总表
`MCP4725 (0x60)`。
**驱动**：`m5stack/libs/unit/dac.py`（4 行别名，快照=master）+
`m5stack/libs/driver/mcp4725.py`（126 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（逐行）**：

| 命令 | 证据 | 语义 |
| --- | --- | --- |
| Fast-mode 写 | `driver/mcp4725.py:46-55` | 2 字节：`[0b0000_0000 | (val>>8)&0x0F, val&0xFF]`，只更新 DAC，不写 EEPROM |
| 读 | `:57-63` | `readfrom_into(addr, 3)`；DAC 值 = `(buf[1]<<4) | (buf[2]>>4)`，12-bit |
| EEPROM 写 | `:114-126` | 3 字节：`[0x60|(val>>8), (val>>4)&0xFF, (val<<4)&0xFF]`，随后等待 EEPROM 完成（`:121-126` 轮询读） |
| 缩放 | `:65-112` | 16-bit/raw/voltage/normalized 互转；`_max_value=int(4095*(vout/vdd))` |

**官方 API**：`get_value()`/`set_value()`、`get_raw_value()`/`set_raw_value()`、
`get_voltage()`/`set_voltage()`、`get_normalized_value()`/`set_normalized_value()`、
`save_to_eeprom()`（`driver/mcp4725.py:65-126`）。

**主机输入**：`dac-raw`（0..4095）。

**QEMU 建议**：在 `m5_unit_i2c_controls.c` 新增 `CONTROL_DAC`（枚举 `:35-40`、
realize `:1063+`、`control_recv` `:997`、`control_send` `:879`）。这是一个
“无寄存器指针”的裸命令设备，不能照搬 `pointer` 分支：写事务按首字节区分
fast-mode（首字节 bit7..5=0）与 EEPROM 命令（首字节 `0x60` 区）；读事务必须
返回 **3 字节** `[status, val>>4, (val&0x0F)<<4]`（驱动忽略 `buf[0]`，但长度必须为
3）。QOM：`dac-raw`（可写 fixture）、`dac-voltage-v`（只读）、`eeprom-value`
（只读观测）。EEPROM 写入只更新模型状态，是否跨 guest 复位保留写进 blocker。

**可断言数据面标志**：`dac-raw`（host 注入 0..4095 后 guest `get_raw_value()`
读回同值）；`transactions`、`written-bytes`（fast-mode=2/EEPROM=3）、`read-bytes`
（每次读 3）；`eeprom-writes` 计数。

**风险/未确认**：EEPROM 写入时序/耐久/掉电保持不建模（驱动 `:121-126` 的轮询
语义只要求读回成功）；读回 `buf[0]` 的 POR/EEPROM 状态位驱动未使用，模型可用
固定值但必须在注释写明；VDD/VOUT 缩放系数来自驱动默认（vdd=5.0、vout=3.3），
产品页只给 0–3.3V。

### 4.3 `watering` — Unit Watering（U101）

**官方**：[Unit Watering](https://docs.m5stack.com/en/unit/watering)（2026-11-02）；
SKU `U101`；集成 5W 水泵 + 电容式土壤湿度测量板。
**驱动**：`m5stack/libs/unit/watering.py`（94 行，快照=master）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`PUMP_EN`、
White=`Analog Output`。即黄线=水泵使能（host→unit），白线=湿度模拟输出
（unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 水泵引脚 | `unit/watering.py:44-46` | `Pin(port[1])`（黄线）→ `Pin.OUT` |
| ADC | `:46` | `ADC(Pin(port[0]))`（白线），`ATTN_11DB` |
| 电压 | `:48-56` | `read_uv()/1e6` 伏 |
| 原始值 | `:58-66` | `read_u16()` 0..65535 |
| 开/关 | `:68-84` | `on()→value(1)`、`off()→value(0)` |
| 通用写 | `:86-93` | `set_pump(state)` → `value(state)` |

**官方 API**：`get_voltage()`、`get_raw()`、`on()`、`off()`、`set_pump()`。

**主机输入**：`analog-mv`（0..3300 建议，模型不限制）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"watering"`（支持列表 `:606-613`）+ realize
分支。白线走现有 ADC 注入 `m5_unit_adc_sample` `:742`、QOM `analog-mv` +
`adc-samples`（`angle`/`light` 分支 `:945-951` 的写法）；黄线需要**观测 guest 输出**
而不是像 `light` 那样设置输入：复用 `UNIT_RELAY` 的 pad observer 思路
（`m5_unit_runtime.c:160-200`，`Esp32GpioPadObserver`）或 `m5_unit_gpio.c` 中
AW3641 的 observer（`:560`），QOM `pump-level`（bool）+ `pump-transitions`。
不能把 `digital-level` 当输出用（现有 `bool_set` 是设置输入 `:658-660`）。

**可断言数据面标志**：`analog-mv`/`adc-samples`（host fixture → guest `get_raw()`
= 按 11DB 衰减换算的 u16，误差边界写进测试）；`pump-level`/`pump-transitions`
（guest `on()` 后 true，`off()` 后 false）；`transactions`/`read-bytes`/
`written-bytes` 全 0（证明没有伪装 I2C）。

**风险/未确认**：水泵电气/扬程/流量与土壤湿度物理曲线**不建模**（写进 blocker）；
PUMP_EN 高有效来自驱动 `value(1)=on()`，产品页只写 `PUMP_EN` 极性；
ADC 11DB 衰减的满量程/校准未在页面确认（`unresolved`）；`PRODUCT` 页无协议表。

### 4.4 `fader` — Unit Fader（U123）

**官方**：[Unit Fader](https://docs.m5stack.com/en/unit/fader)（2026-11-02）；SKU
`U123`；35mm 10kΩ 滑动电位器 + 14× SK6812 可编程 RGB；输出 0–3.3V（5V 供电时）。
**驱动**：`m5stack/libs/unit/fader.py`（348 行，快照=master）+ 基类
`driver/neopixel/sk6812.py`（29 行）与 `driver/neopixel/__init__.py`（95 行）。
后两者快照与 master **不同**（见 §6）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`RGB`、
White=`Analog Input`。黄线=SK6812 数据（host→unit），白线=电位器模拟输出
（unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 构造 | `unit/fader.py:294-301` | `SK6812(port[1], 14)`；`ADC(port[0])` `ATTN_11DB`；默认亮度 10 |
| 电压 | `:304-313` | `read_uv()/1e6` |
| 原始值 | `:315-324` | `read_u16()` |
| 调色板 | `:35-292` | 256 项 `_PALETTE_HEX`，按 `get_raw()` 线性映射索引 |
| 更新颜色 | `:326-335` | `index=_map(raw,0,0xFFFF,0,255)` → `fill_color(palette[index])` |
| 更新亮度 | `:337-345` | 白色 + `set_brightness(_map(raw,...,0,0xFF))` |
| SK6812 字节序 | `driver/neopixel/sk6812.py:12` | `ORDER=(1,0,2,3)` → bpp=3 时实际发送 G,R,B |
| 800kHz 时序 | `driver/neopixel/__init__.py:20-23` | 1 → `(400,850,800,450)` ns；0 → `(800,1700,1600,900)` ns |
| 帧写 | `driver/neopixel/__init__.py:49` | `write()` 由 RMT/bitbang 打出整帧 |

**官方 API**：`get_voltage()`、`get_raw()`、`update_color()`、
`update_brightness()`（以及继承的 `fill_color()`/`set_brightness()`）。

**主机输入**：`analog-mv`（0..3300）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"fader"`（支持列表 `:606-613`）+ realize
分支，同时启用两个端点：白线 ADC（`m5_unit_adc_sample` `:742`、QOM
`analog-mv`+`adc-samples`，照 `angle` 分支 `:945-951`）；黄线 RMT RGB（照
`rgb` 分支 `:961-969`，`g->leds` 需设为 **14**——当前 `:963-966` 用
`unit->onboard_led_count ? ... : 3`，必须给 fader 显式 14）。请检查
`m5_unit_runtime.c` 的 unit 配置是否允许同一 attachment 同时有 ADC 和 RMT 两个
端点（现有型号要么 ADC 要么 RMT）；若框架只允许一个端点，需要在
`M5_UNIT_CONFIG` 层增加“同一 Unit 两个总线端点”的能力，并保持 controller-level
钩子。

**可断言数据面标志**：`analog-mv`/`adc-samples`（guest `get_raw()` 随 fixture
变化）；`led-rgb`（14×3 字节，G,R,B 顺序）/`led-frames`/`incomplete-frames`
（guest `update_color()` 后帧数增加，颜色对应 palette 索引）；`transactions`/
`read-bytes`/`written-bytes` 全 0。

**风险/未确认**：14 灯 SK6812 的 RMT 帧时序只按驱动常量（400/850/800/450ns）
建模，**不**证明真实 SK6812 容差；`set_brightness` 的 master 版本会在 buffer 上
做缩放（`driver/neopixel/__init__.py` master 新增 `min(255, buf/br)`），而快照
不缩放——实现时必须二选一并锚定 SHA（见 §6），否则 `fill_color()+set_brightness`
后的帧字节不同；调色板/机械手感/电位器线性度不建模。

### 4.5 `bps` — Unit Mini BPS（U090）

**官方**：[Unit Mini BPS](https://docs.m5stack.com/en/unit/bps)（2026-11-02）；
SKU `U090`；BMP280（Bosch），I2C `0x76`，300–1100 hPa，±0.12 hPa，-40..+85°C。
官方 I2C 总表另有 `Unit Mini BPS v1.1`（U090-B，QMP6988 `0x56`）；产品页只写
BMP280。
**驱动**：`m5stack/libs/unit/bps.py`（34 行，快照=master）+ `driver/bmp280.py`
（244 行，快照=master）+ `driver/qmp6988.py`（262 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/bps.py:12-13` | BMP280 `0x76`；QMP6988 回退 `0x70` |
| 探测 | `:17-25` | 取 `i2c.scan()[0]`：若等于 `0x76` 用 BMP280，否则用 QMP6988（**顺序依赖**，见风险） |
| 温度/气压 | `:27-32` | `measure()[0]` °C；`measure()[1]/100` hPa |
| 高度 | `:33-34` | `44330*(1-(p/101325)^(1/5.255))`，海平面气压固定 101325 Pa |
| BMP280 身份 | `driver/bmp280.py:31-32` | `0xD0` 读回 `0x58` |
| BMP280 配置 | `:34-56` | reset `0xE0`←`0xB6`；status `0xF3`；control `0xF4`；config `0xF5`；data `0xF7` 6B；calibration `0x88` 24B |
| BMP280 测量 | `:156-166,198-244` | reset→按 osrs 等待→读 6 字节 → 用 24B 校准做补偿 |
| QMP6988 | `driver/qmp6988.py:11-43,88-262` | `0x70`，chip id `0xD1`=`0x5C`，cal `0xA0` 25B，data `0xF7` 6B，status `0xF3` bit3 |

**官方 API**：`get_temperature()`、`get_pressure()`、`get_altitude()`。

**主机输入**：`temperature-c`、`pressure-pa`。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_BMP280`（枚举 `:22-24`、`add_number`
`:117`、`sensor_send`/`sensor_recv` `:410/:572`、支持 id `:650-657`、realize
`:660+`）。寄存器文件需要：chip id `0xD0`=`0x58`、reset `0xE0`（写 `0xB6` 复位
状态）、status `0xF3`、control `0xF4`/config `0xF5` 可写状态、calibration `0x88`
24 字节固定系数 fixture、data `0xF7` 6 字节。**关键点**：guest 端补偿算法在
Python 里，模型必须返回与 `temperature-c`/`pressure-pa` 一致的**原始 ADC 计数**
（用同一组校准系数反算 20-bit raw），否则 guest 换算值与 fixture 不一致；校准
系数取固定合成的合法值（不要用真实器件标定值），并把“补偿公式以驱动实现为准”
写进注释。QMP6988 变体（U090-B `0x56`/ENV-III `0x70`）建议作为独立 kind 或在
catalog 标记 `unresolved`，不要在一个模型里猜芯片。

**可断言数据面标志**：`transactions`（reset/control/config/calibration 读写的
字节轨迹）；guest `get_temperature()`/`get_pressure()` 与 fixture 在量化误差内
一致；`pressure-pa` 与 `get_altitude()` 的海平面假设一致（不宣称真实高度）。

**风险/未确认**：产品页只有 BMP280，驱动支持 QMP6988 回退且用 `scan()[0]` 顺序
判断（同 bus 上若有其它设备会误判）→ `unresolved`；官方总表 `U090-B` 是
**QMP6988 `0x56`**，与驱动回退地址 `0x70` 不一致；24B/25B 校准系数与补偿公式
需在实现时逐行对照 datasheet（Datasheet 仅链接未读）；海平面气压 101325 Pa 是
驱动假设，不是测量。

### 4.6 `env` — Unit ENV（U001）

**官方**：[Unit ENV](https://docs.m5stack.com/en/unit/env)（2026-11-02，EOL 页）；
SKU `U001`；DHT12 `0x5C` + BMP280 `0x76`；量程 -20..60°C / 20..95%RH /
300..1100 hPa。产品页 Spec 表写温度 ±0.2°C，Comparison 表写 ±0.5°C（
`unresolved`，模型不采用精度数字）。官方 I2C 总表未列 EOL 的 U001，只列
ENV-II/III/IV。
**驱动**：`unit/env.py`（55 行，快照=master）+ `driver/dht12.py`（51 行，快照=master）
+ `driver/bmp280.py`（同 4.5）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 型号常量 | `unit/env.py:22-25` | `ENV_I..ENV_IV`，构造时必须显式传 `type` |
| ENV-I 组合 | `:33-35` | `DHT12` + `BMP280` |
| 读温/湿/压 | `:48-55` | 温度/湿度取 DHT12；气压取 BMP280 `/100` |
| DHT12 地址 | `driver/dht12.py:27` | `0x5C` |
| DHT12 数据 | `:29,44-50` | 从 `0x00` 读 5 字节：湿度整数/十分位、温度整数（bit7 符号）/十分位、校验 |
| DHT12 校验 | `:45-47` | `(b0+b1+b2+b3)&0xFF == b4`，否则抛异常 |

**官方 API**：`read_temperature()`、`read_humidity()`、`read_pressure()`。

**主机输入**：`temperature-c`、`humidity-pct`、`pressure-pa`。

**QEMU 建议**：新增 `US_DHT12`（sensors 文件同一框架：枚举、`add_number`、`send`/
`recv`、支持 id、realize）+ 复用 `US_BMP280`。**框架缺口**：现有
`m5_unit_i2c_sensors.c` 每个 Unit 只创建一个 I2C slave；ENV-I 需要同一 Unit
attachment 下 **两个 slave**（`0x5C`、`0x76`），建议在 `m5_unit_runtime.c` 的
unit 配置里允许一个 unit 挂多个子 slave（或给 `m5_unit_sensor_realize` 增加
multi-address 分支），同时做两个地址的占用检查。DHT12 模型：5 字节数据由
`temperature-c`/`humidity-pct` 量化编码，**必须生成合法校验和**；BMP280 按 4.5
的原始计数策略。

**可断言数据面标志**：两个地址的 `transactions`/`read-bytes`（`0x5C` 每次读 5B，
`0x76` 有 reset/config/calibration/data 轨迹）；guest 读出的温/湿/压与 fixture
一致；DHT12 校验错误路径可用故意破坏 fixture 做负例（负例不要写成 PASS）。

**风险/未确认**：`ENVUnit` 必须显式传 `type`，驱动不会自动识别 → catalog 只声明
ENV-I，不能声称兼容 II/III/IV；产品页精度自相矛盾；DHT12 的上电转换/校验语义
只来自驱动；BMP280 校准见 4.5；双 slave 框架扩展是本批唯一需要改
`m5_unit_runtime` 结构的项。

### 4.7 `adc-v11` — Unit ADC v1.1（U013-V11）

**官方**：[Unit ADC v1.1](https://docs.m5stack.com/en/unit/Unit-ADC_V1.1)（2026-11-02）；
SKU `U013-V11`；I2C `0x48`；16-bit；PGA 1/2/4/8；转换率产品页描述 15/30/60/240
SPS，而 Comparison 表写 8/16/32/128 SPS、且 “ADC Solution” 写 **ADS1100**，与本页
描述/官方 I2C 总表（`ADS1110 (0x48)`）矛盾；参考电压描述写内部 2.048V，规格表写
“VDD reference voltage” → 均为 `unresolved`。
**驱动**：`unit/adc_v11.py`（38 行，**快照与 master 不同**）+ `driver/ads1110.py`
（96 行，快照与 master 语义相同但注释/文档字符串不同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `driver/ads1110.py:10` | `0x48` |
| 配置字节 | `:12-28,83-91` | 单字节写：bit7 ST/DRDY（`0x80` 启动）、bit4 SC（`0x10` 单次）、bit3:2 DR1:DR0（240/60/30/15 SPS）、bit1:0 GAIN（1/2/4/8） |
| 读数据 | `:93-96` | `readfrom_into(addr,2)`，`>h` 大端有符号 16-bit |
| 电压 | `unit/adc_v11.py:29-38` | `raw*2.048/2**(mini_code-1)/gain/divider`，`divider=100/610` |
| 快照 bug | `unit/adc_v11.py:30` | 快照写 `data = self.get_adc_raw_value`（未调用方法）；master 已改为 `get_adc_raw_value()` |

**官方 API**：`get_voltage()`、`get_adc_raw_value`（基类）、`set_gain()`、
`set_sample_rate()`、`set_mode()`、`start_single_conversion()`。

**主机输入**：`voltage-mv`（0..12000 建议，按 0–12V 输入）。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_ADS1110`：状态为 1 字节 config
（`sensor_send` `:410` 捕获写）、读 `sensor_recv` `:572` 返回 2 字节大端有符号；
采样值由 `voltage-mv` fixture 经 `raw = v/1000 /2.048 * gain * 2**(mini_code-1) *
divider` 反算。`add_number` 建 `voltage-mv`（可写）/`adc-raw`（只读）/
`config-word`（只读）。必须按 **ADS1110** 语义实现（官方总表），并在模型注释写
“ADS1100 兼容性未验证”。

**可断言数据面标志**：`config-word`（guest set_gain/set_mode/set_sample_rate 后的
配置字节）；`adc-raw`（host voltage-mv → guest `get_adc_raw_value` 读回，量化误差
内）；guest `get_voltage()` 与 `voltage-mv` 一致。

**风险/未确认**：产品页自相矛盾（ADS1100 vs ADS1110、8/16/32/128 vs 15/30/60/240
SPS、内部 2.048V vs VDD ref）→ `unresolved`，实现以官方 I2C 总表 ADS1110 为准；
`divider=100/610` 无产品页出处（驱动实现）；快照驱动 bug 要求实现/测试锚定
master 修正版本或显式写补丁；输入 0–12V 与 PGA 档位/分压的换算需在实现时验证。

### 4.8 `extencoder` — Unit ExtEncoder（U161）

**官方**：[Unit ExtEncoder](https://docs.m5stack.com/en/unit/ExtEncoder%20Unit)（2026-11-02）；
SKU `U161`；STM32F030F4P6 主控；AB/ABZ 输入；I2C `0x59`（可编程）；官方 I2C
总表 `STM32F030 (0x59) Programmable address`。产品页 “Internal Firmware/Protocol”
节渲染损坏（表格字节重复），无法作为寄存器表证据 → 以驱动为准并标 `unresolved`。
**驱动**：`m5stack/libs/unit/extencoder.py`（118 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `unit/extencoder.py:10,41` | 旋转计数 `i32 LE`（4B） |
| `0x10` | `:11,84` | 米值 `i32 LE`（4B） |
| `0x20` | `:12` | 米值 ASCII 字符串（本驱动无读取方法，`unresolved`） |
| `0x30` | `:13,51` | 写 `[1]` 复位计数 |
| `0x40` | `:14,59-65` | 周长 `u32 LE` 读/写 |
| `0x50` | `:15,68-74` | 脉冲数 `u32 LE` 读/写 |
| `0x60` | `:16,88-95` | 零脉冲值 `u32 LE` 读/写 |
| `0x70` | `:17,77-81` | 零模式 1B 读/写 |
| `0xFE` | `:18,103` | 固件版本 1B |
| `0xFF` | `:19,98` | I2C 地址写 |

**驱动语义**：基值快照 `:26-28`；`get_rotary_value = reset + raw - base`
（`:37-43`）；`get_rotary_increments` 与 `get_rotary_status` 每次读 `0x00`
（`:31-48`）；`_read_bytes` = **先写 1 字节寄存器指针，再 `readfrom_into`**
（`:112-118`），`_write_bytes` = 写 `[reg, data...]`（`:106-110`）。

**官方 API**：`get_rotary_value()`、`get_rotary_increments()`、
`get_rotary_status()`、`reset_rotary_value()`、`set_rotary_value()`、
`get/set_perimeter()`、`get/set_pulse()`、`get/set_zero_mode()`、
`get_meter_value()`、`get/set_zero_pulse_value()`、`set_address()`、
`get_firmware_version()`。

**主机输入**：`counter`（i32）、`perimeter`（u32）、`pulse`（u32）、
`zero-pulse`（u32）、`zero-mode`（0..255）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_EXTENCODER`（枚举
`:35-40`、realize `:1063+`、寄存器快照 `:797-850` 的数组直接可用、
`control_send` `:879`/`control_recv` `:997`）。现有 `CONTROL_ENCODER` 分支
（`:1092-1098`）是最近似的模板，但 EXTENCODER 的多个 4B LE 读写寄存器更适合
“`regs[256]` + 每次读从 `read_snapshot` 取”的通用实现。QOM：`counter`（可写
fixture）、`increments`、`perimeter`、`pulse`、`zero-pulse`、`zero-mode`、
`reset-writes`、`fw-version`、`i2c-address`。地址写 `0xFF` 必须做同 bus 占用检查
（`:949-951` 的先例）。

**可断言数据面标志**：`transactions`/`read-bytes`（读 4B 寄存器 +4，读 1B +1，
指针写 +1）；host 注入 `counter` 后 guest `get_rotary_value()` 一致；
`increments` 随注入变化；`reset-writes` 计数（guest `reset_rotary_value()` 写
`0x30`）；`perimeter`/`pulse` 4B LE 读回。

**风险/未确认**：产品页协议表损坏 → 完整寄存器语义只有驱动出处；`0x20` ASCII
米值格式未知；`0x30` 复位是否清零硬件计数还是只清驱动基值需在实现时二选一
（驱动没更新 `_base_value`，语义可疑）；12-bit 采样精度不建模。

### 4.9 `ain4-20ma` — Unit AIN4-20mA（U162）

**官方**：[Unit AIN4-20mA](https://docs.m5stack.com/en/unit/AIN4-20mA%20Unit)
（2026-11-02）；SKU `U162`；I2C `0x55`（可编程）；隔离 HCNR200 + 运放
SGM321YC5/TR；官方 I2C 总表 `STM32F030 (0x55) Programmable address`，产品页
规格表写 `STM32G030F6P6` → **主控型号冲突 `unresolved`**；产品页协议节把
Firmware Version 与 I2C Address 都印成 `0xF0`，驱动用 `0xFE`/`0xFF` → 冲突。
**驱动**：`m5stack/libs/unit/ain4_20ma.py`（117 行，**快照与 master 不同**）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行 + 产品页交叉）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `unit/ain4_20ma.py:14,41` | 原始 ADC `u16 LE`（产品页标 12-bit；方法名含 raw16，`unresolved`） |
| `0x20` | `:15,54` | 电流 `u16 LE`，值 = mA×100 |
| `0x30` | `:16,65-71` | 校准电流 `u16 LE` R/W，写入 = mA×100（驱动限制 4–20mA） |
| `0xFE` | `:17,90` | 固件版本 1B（产品页印 `0xF0`，冲突） |
| `0xFF` | `:18,99,113` | I2C 地址 R/W（产品页印 `0xF0`，冲突） |

**官方 API**：`get_adc_raw_value()`、`get_current_value()`、
`set_cal_current()`、`get_firmware_version()`、`get_i2c_address()`、
`set_i2c_address()`（另有 `get_adc_raw16_value()`、`get_4_20ma_current_value()`、
`get_device_spec()` 只在快照版本存在，master 已删——见 §6）。

**主机输入**：`current-ma`（4..20）、`adc-raw`（0..65535）、`cal-ma`。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_AIN420`：`sensor_send` 捕获
`0x30` 2B LE 校准写与 `0xFF` 地址写；`sensor_recv` 按指针返回
`0x00`/`0x20`/`0x30`/`0xFE`/`0xFF`。`current-ma` fixture 同时驱动 `0x20`
（×100）与 `0x00`（按线性 4–20mA→12-bit 反算），两者必须自洽。
`add_number`：`current-ma`、`adc-raw`、`cal-ma`、`fw-version`。

**可断言数据面标志**：`transactions`、`read-bytes`（2B/1B）、`written-bytes`
（校准写 2B、地址写 1B、指针写）；guest `get_current_value()` ≈ fixture
`current-ma`（÷100 量化）；`get_firmware_version()`/`get_i2c_address()` 与模型
状态一致；地址改写在同 bus 上的占用检查。

**风险/未确认**：产品页协议表 `0xF0` 与驱动 `0xFE`/`0xFF` 冲突；12-bit vs
`get_adc_raw16_value` 命名冲突；主控 STM32F030 vs STM32G030F6P6 冲突；校准
是否影响 `0x20` 编码（产品页只说写校准值）→ `unresolved`；最大 10Hz 采样周期
只作页面信息，不建模。

### 4.10 `acssr` — Unit ACSSR（U139）

**官方**：[Unit ACSSR](https://docs.m5stack.com/en/unit/acssr)（2026-11-02）；SKU
`U139`；ESP32C3 主控 + 单相固态继电器 + SK6812 RGB；I2C `0x50`（可编程，I2C
模式）；另有 Button/Modbus（RS485 115200 8N1，默认 ID `0x0004`）模式；页面
明确 3.3V 逻辑电平。产品页无 I2C 寄存器协议表（随附 “Communication protocol
manual” PDF 未读）→ 以驱动为准并标 `unresolved`。
**驱动**：`m5stack/libs/unit/acssr.py`（156 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。
ESP32-C3 内部：G0=SCL、G1=SDA、G2=RGB、G3=BTN、G4=RELAY、G5/G6=RS485。

**I2C 寄存器（I2C 模式分支，驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` | `unit/acssr.py:17-21,53-65` | 继电器电平写 `1`/`0`；读回 1B |
| `0x10` | `:67-68` | RGB 3B 大端（`rgb.to_bytes(3,"big")`） |
| `0x20` | `:73-75` | 写新 I2C 地址，随后 `time.sleep(5)` |
| `0xFE` | `:71` | 固件版本 1B |

**驱动语义**：`ACSSRUnit.__new__` 按 bus 类型选择 I2C/Modbus 分支
（`:149-156`）；Modbus 分支用 `write_single_coil(0x0000)` / `read_coils` /
`write_single_register`（`:86-145`），本报告不把 Modbus 纳入 I2C 模型。

**官方 API**：`on()`、`off()`、`value()`/`__call__()`、`fill_color(rgb)`、
`get_firmware_version()`、`set_address()`。

**主机输入**：`relay-level`（bool，fixture 可选）、`led-rgb`（0x000000..0xFFFFFF）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_ACSSR`（枚举、
realize、`control_send`/`control_recv`）：`0x00` 写入更新 `relay-level`，
读回同值；`0x10` 写 3B 更新 `led-rgb`；`0x20` 写地址（同 bus 占用检查，写后
策略需明确是否立即迁移 slave 地址）；`0xFE` 返回固定 `fw-version` fixture。
QOM：`relay-level`（只读观测）、`relay-transitions`、`led-rgb`、`fw-version`。
继电器观测语义可参考 `UNIT_RELAY`（`m5_unit_runtime.c:160-200`），但本型号是
I2C 写入而非 GPIO pad，**不要**复用 `output-level` 的 GPIO 注入路径。

**可断言数据面标志**：`transactions`/`written-bytes`（on=2、off=2、颜色=4、
地址=2）；`relay-level`/`relay-transitions`（guest `on()`/`off()`）；`led-rgb`
（guest `fill_color(0x123456)` 后读回）；`fw-version`；`set_address()` 的 5s
睡眠在 QEMU 虚拟时间下不阻塞语义，但测试要显式等待。

**风险/未确认**：产品页无寄存器协议表（协议 PDF 未读）→ 寄存器语义只有驱动
出处；AC 负载 24–480V、10A、过零/漏电流/寿命等电气行为**不建模**，且安全边界
必须在 blocker 写明；Modbus/Button 模式与模式切换不在 I2C 模型范围；`set_address`
的 5 秒等待与地址迁移语义 `unresolved`；SK6812 由 C3 本地驱动，模型只观测 RGB
状态，不模拟灯珠时序。

### 4.11 `ameter` — Unit AMeter（U086）

**官方**：[Unit AMeter](https://docs.m5stack.com/en/unit/Ameter%20Unit)（2026-11-02）；
SKU `U086`；ADS1115 16-bit ADC（`0x48`）+ EEPROM（`0x51`，出厂校准参数，页面
明确“Please do not write to the EEPROM”）；±4A，CA-IS3020S 隔离，4A 保险丝；
官方 I2C 总表 `EEPROM (0x51)`、`ADS1115 (0x48)`。
**驱动**：`m5stack/libs/unit/ameter.py`（228 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/协议（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| ADC 地址 | `unit/ameter.py:12` | `0x48` |
| EEPROM 地址 | `:13` | `0x51` |
| 转换寄存器 | `:15` | `0x00`，读 2B 大端有符号（`:187-190`） |
| 配置寄存器 | `:16` | `0x01` R/W 16-bit 大端 |
| PGA/速率常量 | `:19-42` | PGA 6144..256 mV，速率 8..860 SPS |
| 单次转换 | `:171-177` | 置 config bit15=1（OS）启动 |
| 忙判断 | `:179-186` | config bit15=1 表示转换完成 |
| 电流换算 | `:152-156` | `resolution * calibration_factor * conversion * (-1)` |
| 分辨率表 | `:56-61` | `MV_x / 0.05`（VOLTAGE_DIVIDER_COEFFICIENT=0.05，`:46`） |
| 校准记录 | `:198-212` | EEPROM 地址 208/216/224/232/240/248（按 gain，`:48-70`），8B 记录：gain、expect BE16、real BE16、前 5 字节 XOR 到 byte5 |
| 读校准 | `:214-228` | 8B 读 + XOR 校验，失败回 (1,1) |

**官方 API**：`get_current()`、`get_adc_raw()`、`set_gain()`/`get_gain()`、
`set_data_rate()`/`get_data_rate()`、`set_operation_mode()`/`get_operation_mode()`、
`conversion()`、`save_calibration()`、`read_calibration()`。

**主机输入**：`current-a`（-4..4）、`adc-raw`（i16）、`calibration-factor`（默认
1.0，可写以绕过 EEPROM 记录）。

**QEMU 建议**：这是**双从机**型号（ADS1115 `0x48` + EEPROM `0x51`），与 `env`
一样需要 framework 支持一个 Unit 挂多个 I2C slave。ADS1115 部分按现有
`US_*` 寄存器框架实现：config 16-bit R/W（PGA/rate/mode/OS 位状态），转换寄存器
由 `current-a` fixture 反算（`current = 0.05*mv?`；实现时用驱动公式反解 raw 计数）。
EEPROM 部分：`0x51` 的 256B 寄存器文件，出厂校准记录用**合成 fixture**（gain、
expect、real、XOR）填充；默认**只读**（写请求返回 NACK 或写入被忽略并记录
`eeprom-writes` 计数），与产品页“不要写 EEPROM”一致；是否允许测试写入作为显式
fixture 开关写进 blocker。QOM：`current-a`、`adc-raw`、`calibration-factor`、
`config-word`、`eeprom-hex`。

**可断言数据面标志**：两个地址的 `transactions`/`read-bytes`（config 读 2B、
conversion 读 2B、EEPROM 读 8B）；guest `get_adc_raw()` 与 fixture 一致；
`get_current()` 与 `current-a` 在量化/校准误差内一致；`get_gain()`/`get_data_rate()`
与 config 写一致；EEPROM 写尝试计数（默认必须为 0）。

**风险/未确认**：EEPROM 出厂校准记录布局与 XOR 校验只有驱动出处（页面只给出
地址与“工厂校准”说明）；无真实出厂系数 → fixture 是合成的，不能宣称 1% 精度；
`MEASURING_DIR=-1` 的符号方向与接线（IN+/IN-）不建模；隔离电源/保险丝/热行为
不建模；`save_calibration()` 在生产中应禁用（页面警告），模型默认只读策略需实现
时确认。

### 4.12 `gesture` — Unit Gesture（U127）

**官方**：[Unit Gesture](https://docs.m5stack.com/en/unit/Gesture)（2026-11-02）；
SKU `U127`；PAJ7620U2 3D 手势传感器；I2C `0x73`；9 种手势（上/下/左/右/前/后/
顺/逆时针/挥动）；有效距离 5–15cm，120/240Hz。产品页无寄存器表（PAJ7620U2
datasheet 仅链接未读）→ `unresolved`。
**驱动**：`m5stack/libs/unit/gesture.py`（37 行，快照=master）+
`driver/paj7620.py`（522 行，快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/命令（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `driver/paj7620.py:9` | `0x73` |
| Part ID | `:10,16-18,357-373` | bank0 `0x00` 读 4B，`(b[1]<<8|b[0])` 必须 = `0x7620` |
| Bank 选择 | `:13,473-481` | 写 `0xEF` = 0/1 |
| 初始化数组 | `:126-346` | **219 项** `[reg,val]`，`begin()` 逐项 `writeto_mem`（`:370-371`） |
| 手势 flags | `:22-23,406-424` | bank0 `0x44` 先读 4B，再读 `0x43` 4B；低位即手势位 |
| 手势位定义 | `:88-113` | Right `1<<0`、Left `1<<1`、Up `1<<2`、Down `1<<3`、Forward `1<<4`、Backward `1<<5`、Clockwise `1<<6`、AntiClockwise `1<<7`、Wave `1<<8` |
| 低速率组合 | `:424-472` | 非 high-rate 时读 `0x43` 合并、`0x44` 判 Wave |
| 读写助手 | `:491-513` | `writeto_mem` / `readfrom_mem`，读失败返回 4×`0x00` |

**官方 API**：`get_hand_gestures()`（`unit/gesture.py:31-33`）→
`get_gesture()`（`driver/paj7620.py:406-471`）；`begin()`、`scan()`、
`gesture_description()`、`set_gesture_highrate()`。

**主机输入**：`gesture`（0..9 或位掩码）、`gesture-flags`（raw 16-bit）。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_PAJ7620`：必须能接受
**219 次 bank 初始化写**（寄存器文件按 `0xEF` bank 索引或直接接受任意写）、
`0x00` 读 4B 返回 `[0x20,0x76,version,0]`（满足 part id 校验）、
`0x43`/`0x44` 读 4B 由 `gesture`/`gesture-flags` fixture 生成
（bit 位定义见上表）。`add_number("gesture")` + `add_number("gesture-flags")`；
`transactions`/`written-bytes` 用来断言 219 次初始化写确实发生。

**可断言数据面标志**：`written-bytes`（begin 的 219 次写 + bank 切换）；guest
`get_hand_gestures()` 返回 fixture 对应手势（例如 `gesture=2` → Left）；
`gesture-flags` 位掩码可做多手势负例；读 `0x44` 的 4B 长度与指针语义。

**风险/未确认**：产品页无寄存器文档、datasheet 未读 → 初始化数组/寄存器语义
只有驱动出处；`_gesture_high_rate` 与 `_gesture_highrate` 属性名不一致
（`driver/paj7620.py:125` vs `:351`、`:441-456`），低速率分支存在既有 bug，
实现/测试应走 high-rate 默认路径并标 `unresolved`；手势物理/光学/距离不建模；
模型对 219 项寄存器写只需接受，不要求复现芯片行为（但要保留 bank 状态以免后续
读回不一致）。

## 5. 未确认项汇总（unresolved）

1. `joystick`：原版 U024 的 MCU/芯片身份未出现在官方 I2C 总表（视觉名称
   “MEGA328P original” 仅线索）；按键字节极性未验证。
2. `dac`：EEPROM 写入时序/掉电保持不建模；读回首字节的 POR/EEPROM 状态位驱动
   未使用，模型取值需注释；VDD/VOUT 缩放系数来自驱动默认。
3. `watering`：PUMP_EN 极性只有驱动 `value(1)=on()` 出处；11DB 衰减满量程/校准
   未在产品页确认；土壤湿度/水泵物理不建模。
4. `fader`：SK6812 时序容差、`set_brightness` 的 master/快照差异（见 §6）、
   电位器线性度/机械手感不建模；同一 Unit 双端点（ADC+RMT）需要框架支持。
5. `bps`：产品页只写 BMP280，驱动支持 QMP6988 回退且用 `scan()[0]` 顺序判断；
   官方总表 `U090-B` 是 QMP6988 `0x56`，与驱动 `0x70` 不一致；24B/25B 校准系数
   fixture 为合成值；海平面气压 101325 Pa 是驱动假设。
6. `env`：`ENVUnit` 必须显式传 `type`（不自动识别）→ 只声明 ENV-I；产品页温度
   精度 ±0.2 vs ±0.5 自相矛盾；DHT12 校验/上电语义只有驱动出处；双从机
   （`0x5C`+`0x76`）需要 `m5_unit_runtime` 框架扩展。
7. `adc-v11`：产品页 ADS1100 vs ADS1110、8/16/32/128 vs 15/30/60/240 SPS、
   内部 2.048V vs VDD reference 三处矛盾（实现以官方 I2C 总表 ADS1110 为准）；
   `divider=100/610` 只有驱动出处；快照驱动 `get_voltage()` 漏调用
   `get_adc_raw_value()`（master 已修）→ 实现/测试必须锚定修正版本。
8. `extencoder`：产品页协议表渲染损坏，寄存器语义只有驱动出处；`0x20` ASCII
   米值格式未知；`0x30` 复位语义（硬件计数 vs 驱动基值）可疑；12-bit 采样精度
   不建模。
9. `ain4-20ma`：产品页协议表 `0xF0` vs 驱动 `0xFE`/`0xFF`；12-bit raw 与
   `get_adc_raw16_value` 命名冲突；主控 STM32F030 vs STM32G030F6P6；校准是否
   影响 `0x20` 编码未确认。
10. `acssr`：产品页无 I2C 寄存器协议表（协议 PDF 未读）；AC 负载电气/过零/
    漏电流/寿命不建模且安全边界必须写进 blocker；Modbus/Button 模式与模式切换
    不在 I2C 模型范围；`set_address()` 的 5s 等待/地址迁移语义未确认。
11. `ameter`：EEPROM 出厂校准记录布局与 XOR 校验只有驱动出处；无真实出厂系数
    → fixture 合成、不能宣称 1% 精度；符号方向/隔离/保险丝不建模；
    `save_calibration()` 生产禁用，模型默认只读策略需实现时确认；双地址
    （`0x48`+`0x51`）需要框架扩展。
12. `gesture`：产品页无寄存器表、datasheet 未读 → 219 项初始化与 flags 语义只有
    驱动出处；`_gesture_high_rate` 属性名 bug 使低速率分支不可信，只走
    high-rate；手势物理/光学/距离不建模。

## 6. 驱动版本交叉核对（快照 vs 官方 master）

快照 HEAD `528edd8a06d2556c8e753c8e4978179bbb12b5ba`（`m5stack/version.txt` =
`V2.1.5`）。2026-11-02 逐文件下载 master 原文比对，20 个文件中 15 个逐字节相同，
5 个不同：

| 文件 | 快照 SHA-256（前 16） | master SHA-256（前 16） | 差异语义 |
| --- | --- | --- | --- |
| `unit/adc_v11.py` | `1e8a2901369bac7b` | `b21f1956ee7c...` | master 修复 `get_voltage()` 漏调用：快照 `data = self.get_adc_raw_value`（方法对象），master `data = self.get_adc_raw_value()`；其余为文档字符串 |
| `unit/ain4_20ma.py` | `e8adc070b6839c10` | `970d5f50ba22...` | master 删除 `get_adc_raw16_value()`/`get_4_20ma_current_value()`/`get_device_spec()` 别名，属性 `_i2c_addr`→`_address`，校准写改用 `to_bytes(2,"little")`（总线字节相同）；文档字符串扩充 |
| `driver/ads1110.py` | `e3de0e5f58b05af9` | `f813e3c7e0ef...` | 仅注释/文档字符串差异（AST 语义一致） |
| `driver/neopixel/sk6812.py` | `b316cbebf49a5a45` | `a03925be7ed5...` | 仅 `set_screen` 类型注解 `int`→`list` |
| `driver/neopixel/__init__.py` | `f1995e9fa025330b` | `d97ffc1bd3cc...` | master 新增 `pin.init(pin.OUT, value=0)` 与 `set_brightness()` 先按旧亮度反缩放 buffer 的语义，**会改变”先 fill_color 再 set_brightness”后的帧字节** |

其余 15 个文件（`unit/joystick.py`、`extencoder.py`、`acssr.py`、`dac.py`、
`ameter.py`、`bps.py`、`env.py`、`gesture.py`、`fader.py`、`watering.py`、
`driver/mcp4725.py`、`dht12.py`、`bmp280.py`、`qmp6988.py`、`paj7620.py`）
逐字节相同。

实现建议：catalog 草稿的 `evidence[].sha256` 同时记录**快照哈希**；若实现者使用
master 版本，必须在实现 PR 里显式写明并锚定 master 哈希。`adc-v11` 必须使用
修复后的 `get_voltage()` 语义（或对快照打补丁），不要复刻快照 bug。

## 7. 落地顺序建议

1. `joystick`（A）：零新 kind，直接证明 `CONTROL_JOYSTICK` 可复用；与
   `joystick-v11` 做地址冲突负例。
2. `watering`（A）：先验证 GPIO 模型的“输出观测 + ADC 输入”双端点分支。
3. `dac`（B）：验证 controls 框架能处理非寄存器指针的裸命令设备与 3 字节读。
4. `bps`（B）：验证 sensors 框架的 chip-id/校准块/原始计数补偿策略。
5. `fader`（B）：验证同一 Unit 的 ADC+RMT 双端点与 14 灯 SK6812 帧。
6. `extencoder`（B）/`ain4-20ma`（B）/`acssr`（B）：复用 controls/sensors 框架，
   各自补 4B LE 寄存器、2B LE 寄存器、I2C 继电器语义。
7. `adc-v11`（B）：补单字节配置 + 2B 大端读，锚定 master 修正版。
8. `env`（C）/`ameter`（C）：先完成 `m5_unit_runtime` 的多从机接入，再做双地址
   数据面与占用检查。
9. `gesture`（C）：最后做，需 219 项初始化写 + bank 状态 + 手势 fixture。

## 8. 官方来源清单（本批引用）

**产品页（2026-11-02 读取）**：

- <https://docs.m5stack.com/en/unit/joystick>
- <https://docs.m5stack.com/en/unit/dac>
- <https://docs.m5stack.com/en/unit/watering>
- <https://docs.m5stack.com/en/unit/fader>
- <https://docs.m5stack.com/en/unit/bps>
- <https://docs.m5stack.com/en/unit/env>
- <https://docs.m5stack.com/en/unit/Unit-ADC_V1.1>
- <https://docs.m5stack.com/en/unit/ExtEncoder%20Unit>
- <https://docs.m5stack.com/en/unit/AIN4-20mA%20Unit>
- <https://docs.m5stack.com/en/unit/acssr>
- <https://docs.m5stack.com/en/unit/Ameter%20Unit>
- <https://docs.m5stack.com/en/unit/Gesture>
- 官方 I2C 地址总表：<https://docs.m5stack.com/en/product_i2c_addr>

**官方驱动（快照路径，`m5stack/libs/` 下）**：

- `unit/joystick.py`、`unit/dac.py`、`unit/watering.py`、`unit/fader.py`、
  `unit/bps.py`、`unit/env.py`、`unit/adc_v11.py`、`unit/extencoder.py`、
  `unit/ain4_20ma.py`、`unit/acssr.py`、`unit/ameter.py`、`unit/gesture.py`
- `driver/mcp4725.py`、`driver/bmp280.py`、`driver/qmp6988.py`、`driver/dht12.py`、
  `driver/ads1110.py`、`driver/paj7620.py`、`driver/neopixel/sk6812.py`、
  `driver/neopixel/__init__.py`

**链接但未读的 datasheet/协议文档**：各产品页 Datasheets 节列出的
MCP4725/BMP280/QMP6988/DHT12/ADS1110/PAJ7620U2/ST25R3916 等 PDF，以及
ExtEncoder/AIN4-20mA/ACSSR 的协议手册。按仓库既有方法，这些只作为实现参考链接，
不声称内容已独立复核。

## 9. 复现方式

```bash
# 固定源码快照
cd /Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public
git rev-parse HEAD   # 528edd8a06d2556c8e753c8e4978179bbb12b5ba
cat m5stack/version.txt   # V2.1.5

# 快照 vs master 逐文件哈希
for f in unit/joystick.py driver/mcp4725.py ...; do
  sha256sum "m5stack/libs/$f"
  curl -sfL "https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/$f" | sha256sum
done
```

本报告未运行任何 QEMU/固件/Device Service；不产生运行时 PASS。

## 10. catalog 草稿说明

`2026-11-02-batch2-catalog-draft.json` 的 12 条记录：

- 字段对齐 `platform/units/catalog.json` 现有条目
  （`id/name/sku/visual_asset/official_docs/checked_at/chips/interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/blocker/input_semantics/output_semantics/limitations`）；
- 全部 `model_status: "planned"`，`runtime.status: "unsupported"`，不改变任何
  runtime-profile 或测试；
- `address_7bit` 用**7-bit**；双地址型号（`env`/`ameter`）列出两个地址；
- `evidence[].sha256` 记录快照哈希，`sha256_matches_snapshot_528edd8` 标记是否与
  快照一致，`sha256_master` 在差异文件中额外记录 master 哈希；
- 所有 `inputs.*.default` 都是合成测试 fixture，不是实测值；`blocker` 写明实现
  前置条件与硬件边界。
