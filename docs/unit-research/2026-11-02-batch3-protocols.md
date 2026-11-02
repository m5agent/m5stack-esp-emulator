# Unit 第三批（12 款）官方协议研究报告

日期：`2026-11-02`。归属团队任务 `task-24`，工作树
`esp-emulator-units2`，分支 `m5agent/unit-research-batch3`（基于
`origin/main` `7e2dd9e5`，Unit 已登记 58 款）。

本页是**实现前**的协议研究，不是运行时或硬件 PASS。本报告没有运行 QEMU、固件或
Device Service，没有修改 `platform/units/catalog.json`、runtime profile、QEMU
源码或测试；配套的 catalog 草稿单独放在
[`2026-11-02-batch3-catalog-draft.json`](2026-11-02-batch3-catalog-draft.json)。

## 0. 结论摘要

从未登记的 Unit 中选 12 款。筛选口径：官方 UIFlow2 源码里有**可执行驱动**，协议
能落到现有四个已实现框架之一（GPIO/ADC/RMT、I2C controls、I2C sensors、双从机
`m5_unit_i2c_attach`），或能用同一寄存器机框架低成本扩展；排除需要新控制器拓扑
（CAN/USB/摄像头/SPI 显示/蜂窝/LoRa/原生 C DMX/synth）或需要新专用算法的型号。

| # | Unit id | SKU | 名称 | 总线 / 地址 | 复杂度 | 建议归属 QEMU 分支 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `rfid` | U031 | Unit RFID | `i2c` / `0x28` | A 低 | `m5_unit_i2c_controls.c`（复用 `CONTROL_RFID2` 的 MFRC522 兼容命令面） |
| 2 | `vmeter` | U087 | Unit VMeter | `i2c` / `0x49` + `0x53` | B 中低 | `m5_unit_i2c_sensors.c`（复用 0126 双从机 `US_ADS1115`+EEPROM 模式） |
| 3 | `scales` | U108 | Unit Scales | `i2c` / `0x26` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_SCALES` 寄存器组） |
| 4 | `dac2` | U012-B | Unit DAC2 | `i2c` / `0x59` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_DAC2`，GP8413 双通道） |
| 5 | `extio` | U011 | Unit EXT.IO | `i2c` / `0x27` | B 中低 | `m5_unit_i2c_controls.c`（新增 `CONTROL_PCA9554` 4 寄存器扩展器） |
| 6 | `adc` | U013 | Unit ADC | `i2c` / `0x48` | B 中低 | `m5_unit_i2c_sensors.c`（新增 `US_ADS1100`，区别于已有 `US_ADS1110`） |
| 7 | `env-iv` | U001-D | Unit ENV-IV | `i2c` / `0x44` + `0x76` | C 中 | `m5_unit_i2c_sensors.c`（新增 `US_SHT4X` + 复用 `US_BMP280` 双从机） |
| 8 | `co2` | U103 | Unit CO2 | `i2c` / `0x62` | C 中 | `m5_unit_i2c_sensors.c`（新增 `US_SCD40` 命令+CRC 词协议） |
| 9 | `pbhub` | U041 | Unit PbHub | `i2c` / `0x61` + 6 通道地址 | C 中 | `m5_unit_i2c_controls.c`（多地址 hub：`m5_unit_i2c_attach` ×7） |
| 10 | `tube-pressure` | U130 | Unit Tube Pressure | `gpio-adc` / — | A 低 | `m5_unit_gpio.c`（复用 angle/light 的 ADC 输入分支） |
| 11 | `laser-rx` | U065 | Unit Laser RX | `gpio` / — | A 低 | `m5_unit_gpio.c`（复用 PIR/limit 的数字输入分支） |
| 12 | `ultrasonic-io` | U098-B2 | Unit Ultrasonic-IO | `gpio-timing` / — | C 中 | `m5_unit_gpio.c`（新增 trigger 观测 + echo 脉冲响应） |

复杂度定义：

- **A 低**：只注册 id 并复用现有数据面分支，预计 QEMU 侧改动 `< 20` 行，不新增
  寄存器状态或控制器行为。
- **B 中低**：新增一个 kind / 寄存器组，但直接复用现有指针、快照、QOM 属性框架；
  读/写字节语义是确定性的。
- **C 中**：新增完整命令层/多地址模型/时序响应（双从机、SCD4x 命令+CRC、PbHub
  7 地址、echo 脉冲），但仍在现有 SoC 控制器拓扑（I2C/GPIO/ADC）内。

未登记差集口径（可复算）：`platform/web/vendor/m5stack-models/catalog/products.json`
的 `category=="unit"` 共 **184** 款；`platform/units/catalog.json` 登记 **58** 款，
其中 `servo8-hat` 在 vendor 目录里属于 HAT 条目、不在 unit 类别；故未登记 =
184 − 57 = **127** 款。任务描述的“约 126 款”与本次精确差集差 1 款（与 batch1/
batch2 同类口径差异），不影响选型。

本批覆盖 4 个已实现框架：I2C controls 6 款（rfid/scales/dac2/extio/pbhub 与
双从机 vmeter）、I2C sensors 6 款（adc/env-iv/co2 与 vmeter 的 ADS1115 半边）、
GPIO/ADC 3 款（tube-pressure/laser-rx/ultrasonic-io），其中 4 款是本批之前已
实现型号的**同芯片/同协议兄弟**（rfid→rfid2、vmeter→ameter、adc→adc-v11、
env-iv→env/env-iii），可最大化复用与差分验证价值。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

- 官方 UIFlow2 源码快照：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git 远端 `https://github.com/rodrigob/uiflow_micropython.git`，HEAD
  `528edd8a06d2556c8e753c8e4978179bbb12b5ba`，`m5stack/version.txt` 为 `V2.1.5`）。
  本页所有 `m5stack/libs/...:行号` 都**锚定这个快照**。
- 官方 GitHub master 交叉核对：2026-11-02 用
  `https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/...`
  逐文件下载比对本批 12 个 unit 驱动 + 10 个依赖驱动/包（共 22 个文件）。11 个
  逐字节相同；11 个不同，其中 **5 个有语义差异**（`unit/co2.py`、
  `driver/scd40.py`、`driver/sht4x.py`、`driver/ads1100.py`、`unit/pbhub.py`），
  4 个只是常量位置/注解/文档字符串变化（`unit/rfid.py`、`unit/scales.py`、
  `unit/tube_pressure.py`、`unit/laser_rx.py`、`unit/ultrasonic_io.py`、
  `driver/pca9554.py` 中部分为纯注解）。明细见 §6。
- 官方产品页：2026-11-02 直接抓取 12 个 `officialDocs` 页面，SKU、PinMap、芯片名、
  量程/精度和 PbHub 的完整协议表从页面原文核对；页面链接的 datasheet/原理图/
  协议 PDF **未逐页阅读**，标记为 `linked-by-verified-product-page`。
- 官方 I2C 地址总表 `https://docs.m5stack.com/en/product_i2c_addr`（2026-11-02）
  用于交叉核对芯片与 7-bit 地址；若干型号出现产品页/总表/驱动三方不一致，一律
  写进 §5 的 `unresolved`，不按名字猜协议。
- 现有 QEMU 模型参考：`esp-emulator-units2/.work/native-lock-source/qemu/hw/m5stopwatch/`
  （只读快照，HEAD `9dd5e2a` = canonical 75f1d24 + 0120/0121/0122/0123/0125 +
  已实现的 0126；行号以该 worktree 当前状态为准，本报告未修改）。

### 1.2 逐款证据等级

| 等级 | 含义 | 本批型号 |
| --- | --- | --- |
| E1 | 官方 PinMap + 可执行驱动逐行完整语义（寄存器/命令/编码），无需 PDF 即能确定实现所需的通信语义 | `rfid` `tube-pressure` `laser-rx` `scales` |
| E2 | 官方 PinMap + 可执行驱动逐行完整语义，但**官方协议文档/数据手册只确认链接存在、未读**，或存在必须显式标注的未决字段 | `vmeter` `dac2` `extio` `adc` `env-iv` `co2` `pbhub` `ultrasonic-io` |
| E3 | 只能读到 API/字段名，关键语义 unknown | 本批没有整款 E3；单字段 unresolved 见 §5 |

本报告禁止按产品名推断协议：每个型号都至少能落到一个官方驱动文件的具体行，或者
明确写进 §5 的 `unresolved`。

### 1.3 主机侧约定（本批全部适用）

- UIFlow GPIO `port` 元组为 `(white, yellow)`：`port[0]` 对应 Grove 白线，`port[1]`
  对应黄线。本批的引脚结论都按这个顺序复算，未从颜色名称反推。
- I2C 地址一律写 **7-bit**（`0x49` 等）；驱动的 `readfrom_mem(addr, reg, n)` 是
  “写寄存器指针 + 重复起始读 n 字节”的语义；`writeto_mem` 是“写指针 + 数据”。
  PbHub 的 `read_reg` 是**两次独立事务**（先 writeto 指针，再 readfrom_into），
  模型必须区分。
- 所有主机输入默认值都是**合成测试 fixture**，不是实测硬件默认值；产品页的精度、
  量程、电气参数不进入模型断言。
- 虚拟数据面 PASS 与硬件测量是两类结论；本页不产生任何一类 PASS。

## 2. 与现有 QEMU Unit 模型的复用映射

以下是 `esp-emulator-units2/.work/native-lock-source/qemu/hw/m5stopwatch/`
（HEAD `9dd5e2a`）的接入点（只读参考，本报告未修改）。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c` | `m5_unit_i2c_attach()` `:343-350`；`sensor_attach` `:352-363`；`UNIT_ENV_III` 双从机特例 `:409-418`；id 分派 `:470-481`；`m5_unit_extra_supported` `:508-513` | `vmeter`/`env-iv` 双从机、`pbhub` 多地址 |
| `m5_unit_runtime.h` | `UnitKind` `:10`；`m5_unit_i2c_attach` 声明 `:39-40` | 同上 |
| `m5_unit_i2c_sensors.c` | kind 枚举 `:20-26`；`add_number` `:117`；`sensor_send` `:545+`；`sensor_recv` `:934+`；支持 id 列表 `:1150-1158`；`sensor_device` `:1162`；`sensor_attach_one` `:1168-1173`；realize `:1175+`；0126 双从机 env/ameter 分支 `:1177-1192,1255-1272` | `vmeter` `adc` `env-iv` `co2` |
| `m5_unit_i2c_controls.c` | kind 枚举 `:35-42`；`snapshot_registers` `:1189`；`control_send` `:1319`；`control_recv` `:1579`；支持 id `:1711-1717`；realize `:1723+`；0126 `CONTROL_EXTENCODER`/`CONTROL_ACSSR` 分支 `:1795-1823`；地址占用检查先例 `:576-589,949-951,979-981` | `rfid` `scales` `dac2` `extio` `pbhub` |
| `m5_unit_gpio.c` | 支持 id 列表 `:610-615`；QOM `digital-level` get/set `:665,697`；ADC 采样钩子 `m5_unit_adc_sample` `:781`；realize 分支 `:948+`（angle/light/earth ADC `:992-1000`、rgb `:1009-1016`）；pad observer 先例 `:560`（AW3641） | `tube-pressure` `laser-rx` `ultrasonic-io` |

复用原则（避免把模型写成 host 侧假值）：

- GPIO/ADC 型号必须继续走 `esp32_gpio_set_input`、`esp32_gpio_pad_observer`、
  `m5_unit_adc_sample` 这些**控制器级**钩子；不新增直接改 guest 返回值的属性。
- I2C 型号必须在 `I2CSlaveClass.send/recv` 里实现真实总线字节语义（寄存器指针、
  自动递增、快照、命令+CRC 词），QOM 属性只做注入/观测。
- 多地址型号（`pbhub` 7 地址、`vmeter`/`env-iv` 2 地址）必须每个地址都建模为
  独立 slave 并做同总线占用检查。

## 3. 地址与总线冲突

本批新增型号与已登记型号的默认 7-bit 地址冲突（同一条被动 HUB/同一 bus 不能共存）：

| 地址 | 本批型号 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x28` | `rfid` U031 | `rfid2` U031-B（MFRC522 兼容） | 产品页；官方 I2C 总表；`unit/rfid.py:9` |
| `0x26` | `scales` U108 | `4relay` U097、`weight-i2c` U180 | 产品页；官方 I2C 总表；`unit/scales.py:12` |
| `0x59` | `dac2` U012-B | `extencoder` U161（0x59） | 产品页（0x58~0x65 可编程，默认 0x59）；`unit/dac2.py:31` |
| `0x48` | `adc` U013 | `adc-v11` U013-V11、`ameter` U086 | 产品页；官方 I2C 总表；`driver/ads1100.py:14` |
| `0x44` | `env-iv` U001-D | `env-iii` U001-C（SHT30 0x44） | 产品页；官方 I2C 总表；`driver/sht4x.py:16` |
| `0x76` | `env-iv` BMP280 半边 | `bps` U090、`env` U001 | 产品页；`driver/bmp280.py:29` |
| `0x49`/`0x53` | `vmeter` U087 | `0x49` 无；`0x53` 与 `accel` U056 冲突 | 产品页；官方 I2C 总表；`unit/vmeter.py:12-13` |
| `0x27` | `extio` U011 | 无 | 产品页；官方 I2C 总表；`driver/pca9554.py:29` |
| `0x62` | `co2` U103 | 无 | 产品页；官方 I2C 总表；`unit/co2.py:13` |
| `0x61` | `pbhub` U041 | 无（0x61~0x68 可编程） | 产品页；官方 I2C 总表；`unit/pbhub.py:14` |
| `0x40`/`0x50`/`0x60`/`0x70`/`0x80`/`0xA0` | `pbhub` 6 个通道地址 | 与 `encoder`(0x40)、`scroll`(0x40)、`nfc`(0x50)、`acssr`(0x50)、`dac`(0x60)、`env-iii`(0x70) 等多个已登记地址重叠 | 产品页协议表；`unit/pbhub.py:12` |

实现建议：`rfid`/`rfid2`、`scales`/`4relay`/`weight-i2c`、`dac2`/`extencoder`、
`adc`/`adc-v11`/`ameter`、`env-iv`/`env-iii`/`bps`/`env` 都必须按“单 bus 只挂
一个”建模并写进 fixture 校验；`pbhub` 的 6 个通道地址只在 hub attachment 内部
暴露，不能与同总线的独立 Unit 共享地址。

## 4. 各款协议详情

### 4.1 `rfid` — Unit RFID（U031）

**官方**：[Unit RFID](https://docs.m5stack.com/en/unit/rfid)（2026-11-02，EOL 页）；
SKU `U031`；MFRC522 13.56MHz；I2C `0x28`；支持 ISO14443A / MIFARE / NTAG；读卡距离
<20mm。官方 I2C 总表 `MFRC522 (0x28)`。
**驱动**：`m5stack/libs/unit/rfid.py`（56 行，快照=master 语义相同）+
`m5stack/libs/driver/mfrc522/{__init__,reg,cmd,firmware}.py`（1238/154/106/61 行，
四个文件快照与 master **逐字节相同**）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令/寄存器语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/rfid.py:9` | `0x28` |
| 初始化 | `unit/rfid.py:11`；`driver/mfrc522/__init__.py:122-198` | `pcd_init()`：软复位、TMode/TPrescaler/TReload、TxASK、天线使能 |
| 读/写寄存器 | `driver/mfrc522/__init__.py:200-208` | `pcd_write_register`/`pcd_read_register`（地址 + 数据两字节事务） |
| 寄存器表 | `driver/mfrc522/reg.py:10-120` | CommandReg 0x01、ComIrqReg 0x04、ErrorReg 0x06、Status2Reg 0x08、FIFODataReg 0x09、FIFOLevelReg 0x0A、ControlReg 0x0C、BitFramingReg 0x0D、ModeReg 0x11、TxControlReg 0x14、TxASKReg 0x15、CRCResult 0x21/0x22、TModeReg 0x2A、TPrescalerReg 0x2B、TReloadReg 0x2C/0x2D、VersionReg 0x37 |
| PCD 命令 | `driver/mfrc522/cmd.py:9-70` | PCD_IDLE 0x00、PCD_TRANSCEIVE 0x0C、PCD_MFAUTHENT 0x0E、PCD_SOFTRESET 0x0F、PICC_REQA 0x26、PICC_WUPA 0x52、PICC_SEL_CL1 0x93、PICC_AUTHENT1A 0x60、PICC_READ 0x30、PICC_WRITE 0xA0、PICC_HALT 0x50 |
| 寻卡 | `unit/rfid.py:13-19`；`__init__.py:376+` | `picc_request_a` / `picc_wakeup_a` |
| 读 UID | `unit/rfid.py:21-23`；`__init__.py:1184+` | `picc_read_card_serial` → `_uid.uid` |
| 读/写块 | `unit/rfid.py:25-45`；`__init__.py:628-700` | `pcd_authenticate(0x60,...)` + `mifare_read/write` |
| 关闭 | `unit/rfid.py:47-49` | `picc_halt_a()` + `pcd_stop_crypto1()` |

**官方 API**：`is_new_card_present()`、`read_card_uid()`、`read(block)`、
`write(block, buffer)`、`close()`、`wakeup_all()`、`picc_select_card()`。

**主机输入**：`card-present`、`uid-hex`、`card-data-hex`（与已登记 rfid2 profile 一致）。

**QEMU 建议**：**直接复用** `CONTROL_RFID2`（`m5_unit_i2c_controls.c` 已有
MFRC522 兼容命令面、确定性 MIFARE Classic 1KiB 合成卡、UID/扇区/认证状态与
FIFO；realize 分支 `:1723+` 的 RFID2 else 分支 `:1855+`）。只需在支持 id 列表
`:1711-1717` 增加 `"rfid"` 并让 realize 把 id 映射到 `CONTROL_RFID2`（默认
`address=0x28`、`uid_len=4` 与 rfid2 相同），不需要新 kind。与 `rfid2` 的地址
冲突按 §3 处理。

**可断言数据面标志**：`transactions`、`read-bytes`、`written-bytes`、`card-reads`、
`card-writes`、`command-errors`、`fifo-level`、`selected`、`authenticated`；
guest `read_card_uid()` 返回 fixture UID。

**风险/未确认**：RF 场、天线、读卡距离、卡片电气/安全与真实 MIFARE 密钥**不建模**
（沿用 rfid2 的既有边界：卡内容是确定性合成 fixture，不是真实用户卡数据）；
`0x28` 与 rfid2 冲突（一总线一个）；产品页 EOL。

### 4.2 `vmeter` — Unit VMeter（U087）

**官方**：[Unit VMeter](https://docs.m5stack.com/en/unit/vmeter)（2026-11-02）；
SKU `U087`；ADS1115 16-bit ADC（`0x49`）+ EEPROM（`0x53`，出厂校准，页面明确
“Do not write to the EEPROM”）；±36V；CA-IS3020S 隔离；官方 I2C 总表
`EEPROM (0x53)`、`ADS1115 (0x49)`。
**驱动**：`m5stack/libs/unit/vmeter.py`（227 行，快照=master 逐字节相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/协议（驱动逐行，与 ameter 同构）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| ADC 地址 | `unit/vmeter.py:12` | `0x49` |
| EEPROM 地址 | `:13` | `0x53` |
| 分压系数 | `:46` | `VOLTAGE_DIVIDER_COEFFICIENT = 0.015918958` |
| 换算方向 | `:44` | `MEASURING_DIR = -1` |
| 电压换算 | `:151-158` | `resolution * calibration_factor * conversion * -1` |
| 分辨率表 | `:56-61` | `MV_x / 0.015918958` |
| 配置寄存器 | `:105-150` | ADS1115 0x01：PGA bits11:9、rate bits7:5、mode bit8、OS bit15 |
| 转换寄存器 | `:186-188` | 0x00 读 2B 大端有符号 |
| 校准 EEPROM | `:197-227` | 0x53 地址 208/216/224/232/240/248（8B 记录：gain、expect BE16、real BE16、XOR） |
| 单次转换 | `:170-184` | 置 OS=1 后轮询 bit15 完成 |

**官方 API**：`get_voltage()`、`get_adc_raw()`、`set_gain()`/`get_gain()`、
`set_data_rate()`/`get_data_rate()`、`set_operation_mode()`/`get_operation_mode()`、
`conversion()`、`read_calibration()`。

**主机输入**：`voltage-v`（-36..36）；`calibration-factor` 可作显式 fixture（默认 1.0）。

**QEMU 建议**：参数化复用 0126 的 `ameter` 双从机模式（`US_ADS1115` +
`US_AMETER_EEPROM`，见 `m5_unit_i2c_sensors.c:1255-1272` 与 `m5_unit_runtime.c:343`）；
新增 `US_ADS1115_VMETER`（或给 `US_ADS1115` 增加 per-unit 系数/地址参数），
地址 `0x49`+`0x53`，电压 fixture 按 `raw = round(-voltage / (mv_lsb[gain]/0.015918958))`
反算，EEPROM 合成记录 factor=1.0、默认只读。QOM：`voltage-v`、`adc-raw`、
`config-word`、`eeprom-writes`、`i2c-address`。

**可断言数据面标志**：guest `get_voltage()` 与 fixture 在量化误差内一致；
`config-word` 随 gain/rate 写变化；EEPROM 读记录 factor=1.0；写尝试被 NACK 计数。

**风险/未确认**：0x53 与已登记 `accel` U056 冲突（一总线一个）；EEPROM 出厂校准
布局只有驱动出处，无真实系数→fixture 合成、不能宣称 1% 精度；±36V/隔离/保险丝/
方向 NOT RUN；产品页分辨率描述（≤16V 1mV、>16V 7.9mV）与驱动系数关系需实现时
逐行核对。

### 4.3 `scales` — Unit Scales（U108）

**官方**：[Unit Scales](https://docs.m5stack.com/en/unit/UNIT%20Scales)（2026-11-02）；
SKU `U108`；STM32F030F4P6 + HX711 24-bit ADC，0–20kg，I2C `0x26`；SK6812 RGB
指示灯 + 去皮按键；官方 I2C 总表 `STM32F030 (0x26) Programmable address`。
**驱动**：`m5stack/libs/unit/scales.py`（102 行，**快照与 master 不同**：master 把
模块级常量搬进类属性并加文档字符串，值不变）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x20`/`0x21`/`0x22`/`0x23` | `unit/scales.py:15-18` | 按键短按/长按/状态/偏移 |
| `0x25` | `:21` | RGB 同步控制 |
| `0x50`/`0x51`/`0x52` | `:22-24` | RGB 3B（`get_rgb_led` 读 `LED_RED` 起 3B） |
| `0x10` | `:27` | 原始 ADC `int32 BE`（`get_scale_value(0)`） |
| `0x14` | `:28` | 重量 `int32 BE`，驱动 `/100` 得克 |
| `0x18` | `:29` | 偏移 ADC `int32 BE` R/W |
| `0x24` | `:30` | 当前偏移（写 1 触发） |
| `0x30` | `:33` | 校准零点（写 2B 0,0，sleep 200ms） |
| `0x32` | `:34` | 校准负载（写 2B little-endian 克数，sleep 200ms） |
| `0xFE`/`0xFF` | `:37-38` | 固件版本 / I2C 地址 |

**驱动语义**：`get_scale_value(scale)` 读 `RAW_ADC + scale*4` 4 字节（`:71-77`）；
`set_rgb_led` 写 3B 大端（`:65-66`）；`set_i2c_address` 写 `0xFF`（`:95-102`）。

**官方 API**：`get_button_status()`、`set_button_offset()`、`set_rgbled_sync()`、
`get_rgbled_sync()`、`set_rgb_led()`、`get_rgb_led()`、`get_scale_value(scale)`、
`set_raw_offset()`、`set_current_raw_offset()`、`set_calibration_zero()`、
`set_calibration_load()`、`get_device_inform()`、`set_i2c_address()`。

**主机输入**：`weight-g`（-20000..20000）、`adc-raw`（int32）、`button-status`。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_SCALES`（kind 枚举
`:35-42`、`snapshot_registers` `:1189`、`control_send` `:1319`、`control_recv`
`:1579`、realize `:1723+`）。寄存器组：`0x10/0x14/0x18` 4B BE 值、`0x20-0x25`
按键/RGB 控制、`0x30/0x32` 校准写观测、`0x50-0x52` RGB、`0xFE/0xFF` 身份/地址。
QOM：`weight-g`、`weight-raw`、`adc-raw`、`button-status`、`led-rgb`、
`led-sync`、`calibration-writes`、`fw-version`、`i2c-address`。

**可断言数据面标志**：guest `get_scale_value(1)`（重量 `/100`）与 fixture 一致；
`get_scale_value(0)` 读原始 ADC；RGB 写入回读；校准写计数；`0xFF` 地址迁移
（含同总线占用检查）。

**风险/未确认**：0x26 与 `4relay`/`weight-i2c` 冲突（一总线一个）；HX711 采样
时序/称重力学/20kg 量程/去皮物理 NOT RUN；按键长短按语义只来自驱动；master 常量
重命名（值相同）需钉 SHA；产品页 10SPS 输出率不建模。

### 4.4 `dac2` — Unit DAC2（U012-B）

**官方**：[Unit DAC2](https://docs.m5stack.com/en/unit/Unit-DAC2)（2026-11-02）；
SKU `U012-B`；GP8413 15-bit 双通道 DAC；I2C `0x58~0x65`（A2/A1/A0 可选，默认
`0x59`）；0–5V/0–10V；0.2% 输出误差；短路保护；官方 I2C 总表
`GP8413 (0x59)` / `0x58-0x65(default:0x59)`。
**驱动**：`m5stack/libs/unit/dac2.py`（120 行，快照=master 逐字节相同）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/命令语义（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `unit/dac2.py:31` | 默认 `0x59` |
| 量程 | `:25-26,52-66` | 0x01 写 0x00=0–5V；0x11=0–10V |
| 通道 0 | `:68-95` | 0x02 写 2B LE：`int(v/max*0xFFFF)` |
| 通道 1 | `:92-95` | 0x04 写 2B LE |
| 双通道 | `:89-91,97-120` | 0x02 写 4B LE（两个 16-bit 值） |

**官方 API**：`set_dacoutput_voltage_range(range)`、`set_voltage(voltage, channel)`、
`set_voltage_both(v0, v1)`。

**主机输入**：`range`（0/1）、`voltage-0-v`、`voltage-1-v`（0..5/10）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_DAC2`：写事务按首字节
寄存器 + 2B/4B LE 数据；0x01 更新量程；0x02/0x04 更新两通道原始码。
QOM：`range`（只读）、`voltage-0-v`/`voltage-1-v`（由原始码与量程换算，只读）。
**关键未决**：页面写 15-bit 分辨率，但驱动把 `voltage/max*0xFFFF`（16-bit 满码）
写入；芯片实际 15-bit（0..32767）还是驱动使用 16-bit 约定需在实现时对照 GP8413
数据手册，模型应保存 guest 写入的 16-bit 原始码并显式标 `unresolved`。

**可断言数据面标志**：`transactions`/`written-bytes`（0x01=2B、0x02=3B/5B、
0x04=3B）；guest `set_voltage` 后 QOM 原始码/换算电压一致；量程切换后换算变化。

**风险/未确认**：15-bit vs 16-bit 编码 `unresolved`；0x59 与 `extencoder` 冲突
（一总线一个）；模拟输出误差/短路保护/线性度 NOT RUN；地址 0x58~0x65 由硬件
A2/A1/A0 决定，模型只实现默认 0x59。

### 4.5 `extio` — Unit EXT.IO（U011）

**官方**：[Unit EXT.IO](https://docs.m5stack.com/en/unit/extio)（2026-11-02，EOL 页）；
SKU `U011`；PCA9554PW 8 位 I/O 扩展器；I2C `0x27`（A0–A2 焊盘可改）；
2.3–5.5V；开漏/上拉/中断输出；官方 I2C 总表 `PCA9554PW (0x27)`。
**驱动**：`m5stack/libs/unit/extio.py`（4 行别名，快照=master）+
`m5stack/libs/driver/pca9554.py`（146 行，**快照与 master 仅类型注解差异**）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器语义（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| 0x00 | `driver/pca9554.py:24` | 输入端口（读引脚电平） |
| 0x01 | `:25` | 输出端口（写输出锁存） |
| 0x02 | `:26` | 极性反转 |
| 0x03 | `:27` | 配置（1=输入，0=输出） |
| 地址 | `:29` | 默认 `0x27` |
| 读/写 | `:135-146` | `_read_u8`/`_write_u8`：写指针 + 读/写 1 字节 |

**官方 API**：`set_port_mode(mode)`、`set_pin_mode(id, mode)`、
`digit_write_port(value)`、`digit_write(id, value)`、`digit_read_port()`、
`digit_read(id)`、`pin(id, mode, value)`。

**主机输入**：`input-levels`（8 bool）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_PCA9554`：4 个寄存器
（input/output/polarity/config），写支持 0x01/0x02/0x03，读 0x00 返回
`(input_levels ^ polarity) & ~config | (output & config)`（按 PCA9554 语义：
配置为输出的位读输出锁存，输入位读引脚）。QOM：`input-levels`（可写 fixture）、
`output-levels`、`polarity`、`config`、`i2c-address`（固定 0x27 只读，A2/A1/A0
焊盘不建模）。

**可断言数据面标志**：guest `digit_write` 后 QOM 输出锁存一致；`digit_read`
随 input fixture/polarity/config 变化；配置寄存器读回；地址固定 0x27。

**风险/未确认**：中断输出（INT）不建模；A0–A2 焊盘改址不建模（固定 0x27）；
上拉/开漏电气 NOT RUN；产品页 EOL；0x27 无已登记冲突。

### 4.6 `adc` — Unit ADC（U013）

**官方**：[Unit ADC](https://docs.m5stack.com/en/unit/adc)（2026-11-02，EOL 页）；
SKU `U013`；ADS1100 16-bit ADC；I2C `0x48`；PGA 1/2/4/8；8–128 SPS；内部参考；
官方 I2C 总表 `ADS1100 (0x48)`。
**驱动**：`m5stack/libs/unit/adc.py`（5 行别名，快照=master）+
`m5stack/libs/driver/ads1100.py`（111 行，**快照与 master 语义差异**：master
`get_raw_value()` 返回 `_BUFFER[0:2]`，快照返回整个 3 字节 buffer）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `driver/ads1100.py:14` | `0x48` |
| 配置位 | `:16-19` | ST/BSY bit7、SC bit4、DR bits3:2、PGA bits1:0 |
| 速率表 | `:21` | `(128, 32, 16, 8)` SPS |
| 增益表 | `:23` | `(1, 2, 4, 8)` |
| 默认配置 | `:39` | `0x8C` |
| 读转换 | `:44-54` | 写配置 → sleep 0.1s → `readfrom_into` 3B（data hi、data lo、config） |
| 电压换算 | `:56-64` | `(value / (-min_code[rate]*gain)) * 3.3 * 4` |
| 配置写 | `:66-108` | `writeto` 1 字节配置 |

**官方 API**：`get_value()`、`get_voltage()`、`get_raw_value()`、
`get/set_operating_mode()`、`get/set_data_rate()`、`get/set_gain()`。

**主机输入**：`voltage-v`（0..12）。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_ADS1100`（区别于已有
`US_ADS1110`；kind 枚举 `:20-26`、`sensor_send` `:545+`、`sensor_recv`
`:934+`、支持 id `:1150-1158`、realize `:1175+`）。状态为 1 字节 config；
读事务返回 3B `[data_hi, data_lo, config]`（canonical ADS1100 读格式）；raw 由
`voltage-v` 按驱动公式反算。QOM：`voltage-v`、`adc-raw`、`config-word`。

**可断言数据面标志**：`config-word` 随 gain/rate/mode 写变化；guest `get_value()`
读回 3B 与 config 一致；`get_voltage()` 与 fixture 在量化误差内一致。

**风险/未确认**：0x48 与 `adc-v11`/`ameter` 冲突（一总线一个）；ADS1100 vs
ADS1110 是两个不同已登记/本批型号，不能混用寄存器语义（batch2 已记录 adc-v11
页面 ADS1100/ADS1110 冲突）；master/snapshot `get_raw_value` 返回长度差异需要
钉 SHA；参考电压/内部 PGA 精度 NOT RUN；产品页 EOL。

### 4.7 `env-iv` — Unit ENV-IV（U001-D）

**官方**：[Unit ENV-IV](https://docs.m5stack.com/en/unit/Unit_ENV-IV)（2026-11-02，
EOL 页）；SKU `U001-D`；SHT40 `0x44` + BMP280 `0x76`；-40..125°C / 0..100%RH /
300–1100hPa；精度 ±0.2°C、±1.8%RH、±0.12hPa；官方 I2C 总表
`SHT40 (0x44)`、`BMP280 (0x76)`。
**驱动**：`m5stack/libs/unit/env.py`（55 行，快照=master 逐字节相同；`ENV_IV`
常量 `:25`、组合 `:42-45`）+ `driver/sht4x.py`（173 行，**快照与 master 语义
差异**：快照 `self.measure[1]`/`[0]` 缺少调用，master 修复并新增
`get_temperature/get_humidity`）+ `driver/bmp280.py`（快照=master）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（SHT4x 驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址 | `driver/sht4x.py:16` | `0x44` |
| 读序列号 | `:17,77-98` | 0x89 → 6B（2×2B + CRC） |
| 软复位 | `:18,99-101` | 0x94 |
| 测量 | `:120-160` | 写 1 字节命令（Mode 枚举）→ sleep → 读 6B（T 2B+CRC、RH 2B+CRC） |
| CRC | `:163-173` | CRC8 poly 0x31 init 0xFF |
| 解码 | `:145-160` | T=-45+175*raw/65535；RH=-6+125*raw/65535（clamp 0..100） |
| BMP280 | 同 batch2 `driver/bmp280.py` | 0x76：0xD0=0x58、0x88 24B 校准、0xF7 6B 数据 |

**官方 API**：`ENVUnit(i2c, type=ENV_IV)` → `read_temperature()`、
`read_humidity()`、`read_pressure()`（`unit/env.py:48-55`）。

**主机输入**：`temperature-c`（-40..125）、`humidity-pct`（0..100）、
`pressure-pa`（30000..110000）。

**QEMU 建议**：复用 0126 双从机 `m5_unit_i2c_attach` 模式：新增 `US_SHT4X`
（0x44，命令 0x89/0x94/测量命令 + 6B CRC 响应，T/RH 由 fixture 编码并生成合法
CRC）+ 复用 `US_BMP280`（0x76，仅暴露 pressure-pa，温度槽固定合成值）。QOM：
`temperature-c`、`humidity-pct`、`pressure-pa`。实现时二选一：按快照命令层
（测量命令来自 Mode 枚举，见 `driver/sht4x.py` Mode 定义）或 master 修复版
getters，并锚定 SHA；**CRC 必须合法**。

**可断言数据面标志**：guest `read_temperature/humidity/pressure` 与 fixture 在
量化误差内一致；SHT40 事务为写 1 字节命令 + 读 6 字节（CRC 校验通过）；
BMP280 事务轨迹；两地址都计数。

**风险/未确认**：0x44 与已登记 `env-iii`（SHT30 0x44）冲突；0x76 与
`bps`/`env` 冲突；快照 SHT4x getter bug 要求锚定 master 修复版或打补丁；
`ENVUnit` 必须显式 `type=4`；产品页 EOL；SHT40 精度/自热/滤波 NOT RUN。

### 4.8 `co2` — Unit CO2（U103）

**官方**：[Unit CO2](https://docs.m5stack.com/en/unit/co2)（2026-11-02）；SKU
`U103`；Sensirion SCD40；I2C `0x62`；400–2000ppm；±(50ppm+5%)；
-10..60°C、0..95%RH；官方 I2C 总表 `SCD41 (0x62)`（**SCD40 vs SCD41 冲突**，
见 §5）。
**驱动**：`m5stack/libs/unit/co2.py`（345 行，**快照与 master 语义差异**：
快照自带完整命令层；master 改为 `CO2Unit(SCD40)` 子类）+ `driver/scd40.py`
（262 行，**快照与 master 完全不同**：快照是 asyncio 实现，master 是同步命令层）。
两份实现命令常量一致（0x21B1/0xEC05/0xE4B8/…），但 API/时序不同，必须钉 SHA。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令语义（快照 `unit/co2.py` 逐行）**：

| 命令 | 证据 | 语义 |
| --- | --- | --- |
| 0x21B1 / 0x3F86 | `unit/co2.py:20-21` | 启动/停止周期测量 |
| 0x21AC | `:22` | 低功耗周期测量 |
| 0xE4B8 | `:19` | 数据就绪状态（2B + CRC） |
| 0xEC05 | `:23` | 读测量（3×2B + CRC），顺序 CO2、temp、RH |
| 0x219D / 0x2196 | `:33-34` | 单次测量 all / HT |
| 0x3646 / 0x3632 | `:15-16` | reinit / factory reset |
| 0x241D / 0x2318 | `:25-26` | 设置/读温度偏移 |
| 0x2427 / 0x2322 | `:27-28` | 设置/读海拔 |
| 0xE000 | `:29` | 设置环境压力 |
| 0x3682 | `:24` | 序列号 |
| 0x36E0 / 0x36F6 | `:35-36` | 掉电/唤醒 |
| 写命令 | `:304-314` | 2 字节 big-endian |
| 读响应 | `:316-322` | 每 2B 数据 + 1B CRC，CRC8 poly 0x31 init 0xFF（`:324-345`） |
| 测量解码 | `:71-81` | CO2=(b0<<8)|b1；temp=-45+175*raw/65535；RH=100*raw/65535 |
| 数据就绪 | `:82-89,194-204` | 读 0xE4B8 2B+CRC，低 11 bit 非 0 就绪 |

**官方 API**：`set_start_periodic_measurement()`、`set_stop_periodic_measurement()`、
`get_sensor_measurement()`、`is_data_ready()`、`data_isready()`、
`set/get_temperature_offset()`、`set/get_sensor_altitude()`、`set_ambient_pressure()`、
`set_force_calibration()`、`get/set_calibration_enabled()`、
`get_serial_number()`、`set_self_test()`、`set_factory_reset()`、`reinit()`、
`set_single_shot_measurement_all/ht()`、`set_sleep_mode()`、`set_wake_up()`。

**主机输入**：`co2-ppm`（400..2000/5000）、`temperature-c`、`humidity-pct`、
`data-ready`（bool）、`serial-number`。

**QEMU 建议**：`m5_unit_i2c_sensors.c` 新增 `US_SCD40`：命令+CRC 词协议。
状态机：命令写（2B BE）→ 按命令返回响应（数据就绪/测量/序列号/温度偏移等），
每个 2B 数据后必须回 CRC8(poly 0x31, init 0xFF)；测量值由 fixture 编码
（CO2 直接 ppm；T/RH 按公式反算 raw）。周期测量模式下 0xEC05 仅在
`data-ready` fixture 后返回；reinit/reset 更新状态。QOM：`co2-ppm`、
`temperature-c`、`humidity-pct`、`data-ready`、`serial-number`、
`measurement-reads`。

**可断言数据面标志**：每类命令的 written/read 字节轨迹与 CRC 正确；guest
`get_sensor_measurement()` 与 fixture 一致；`is_data_ready()` 受 fixture 门控；
错误 CRC 路径可做负例（模型不应伪造通过）。

**风险/未确认**：SCD40（页面/驱动）vs SCD41（官方 I2C 总表）芯片标识冲突；
快照 async 实现 vs master sync 实现是两套 API，必须锚定一个 SHA；`co2l` U104
（SCD41，量程更大）不在本批；CRC/上电时序/测量周期（5s）与精度 NOT RUN；
0x62 无已登记冲突。

### 4.9 `pbhub` — Unit PbHub（U041）

**官方**：[Unit PbHub](https://docs.m5stack.com/en/unit/Unit_PbHub)（2026-11-02，
EOL 页）；SKU `U041`；6 通道 Grove PORT.B 扩展器；I2C `0x61`（A0–A2 可改
0x61–0x68）；页面描述写 MEGA328、规格表写 **STM32F030F4P6**，官方 I2C 总表写
`MEGA328 (0x61)` → **MCU 身份三方冲突 `unresolved`**。页面 Protocol 表给出
完整 6×12 命令矩阵。
**驱动**：`m5stack/libs/unit/pbhub.py`（202 行，**快照与 master 语义差异**：
master 将 RGB 3B 从直接大端改为 **GRB 交换**（`color_grb`），并新增
`LED_CTRL_REG 0xFA` 的 `set_rgb_mode/get_rgb_mode`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**通道/命令表（页面 Protocol + 驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| hub 地址 | `unit/pbhub.py:14` | `0x61`（0x61–0x68） |
| 通道基址 | `:12` | `[0x40,0x50,0x60,0x70,0x80,0xA0]` |
| 状态寄存器 | `:15-16` | 0xFE 固件 / 0xFF 地址 |
| 数字写 IO0/IO1 | 页面命令 0x40/0x41（+0x10*ch） | 1B |
| 模拟写 IO0/IO1 | 0x42/0x43 | 1B（PWM 0–255） |
| 数字读 IO0/IO1 | 0x44/0x45 | 1B |
| 模拟读 IO0 | 0x46 | 2B LE int16（页面 10-bit ADC 0–5V） |
| RGB 数量 | 0x48 | 2B LE |
| 单灯颜色 | 0x49 | 2B LE 位置 + 3B 颜色（快照大端；master GRB） |
| 区间颜色 | 0x4A | 2B+2B LE + 3B 颜色 |
| 亮度 | 0x4B | 1B |
| 驱动读 | `:189-202` | 先 `writeto` 指针，再独立 `readfrom_into`（两次事务） |
| 驱动写 | `:185-188` | `writeto_mem(addr, reg, data)` |

**官方 API**：`digital_read/write`、`pwm_read/write`、`analog_read`、
`set_rgb_led_num`、`set_rgb_color_pos`、`set_rgb_color`、`set_rgb_brightness`、
`set_servo_angle`、`set_servo_pulse`、`read_status`、`set_i2c_address`。

**主机输入**：6 通道 `digital-inputs`、`analog-inputs`（10-bit 0–1023）、
`rgb-frames`（每通道）。

**QEMU 建议**：`m5_unit_i2c_controls.c` 新增 `CONTROL_PBHUB`，用
`m5_unit_i2c_attach()` 挂 **7 个 slave**：0x61（FW/地址）+6 个通道 address
（0x40/0x50/0x60/0x70/0x80/0xA0）。每通道一个寄存器文件：读命令 0x44/0x45
返回 fixture 数字输入，0x46 返回 2B LE 模拟值；写命令 0x40-0x43 更新输出锁存/
PWM，0x48-0x4B 更新 RGB 帧；0x61 的 0xFE/0xFF 提供身份与地址迁移（含同总线
冲突检查）。QOM：每通道 `digital-inputs`/`analog-inputs`/`digital-outputs`/
`pwm-outputs`/`rgb-frames`，以及 `fw-version`/`i2c-address`。
**关键点**：通道 5 基址是 `0xA0`（不是 0x90），页面与驱动一致；读是两次独立
事务；RGB 字节序需按所选 SHA 决定（快照大端 vs master GRB）。

**可断言数据面标志**：guest 每通道 digital_read/analog_read 与 fixture 一致；
写命令轨迹与输出锁存/PWM/RGB 帧；0x61 地址迁移；channel 地址只能通过 hub
attachment 暴露。

**风险/未确认**：MCU 身份冲突（MEGA328 vs STM32F030F4P6 vs 总表 MEGA328）；
RGB 字节序版本差异 unresolved；hub 不支持嵌套；模拟输入 10-bit/0–5V 映射需在
实现时按页面/驱动核对；通道地址与独立 Unit 地址重叠（§3）；PWM/servo/RGB 电气/
机械 NOT RUN。

### 4.10 `tube-pressure` — Unit Tube Pressure（U130）

**官方**：[Unit Tube Pressure](https://docs.m5stack.com/en/unit/Unit_Tube_Pressure)
（2026-11-02）；SKU `U130`；MCP-H10-B200KPPN 压阻式压力传感器；-100..200kPa；
输出 0.1–3.1V；精度 ±1.5kPa；页面给出公式 `P = K*Vout + B`（K=100，B=-110 等价）。
**驱动**：`m5stack/libs/unit/tube_pressure.py`（39 行，快照=master 语义相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`NC`、
White=`Analog Output`。模拟输出在白线。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| ADC | `unit/tube_pressure.py:13-14` | `ADC(port[0])`（白线），`ATTN_11DB` |
| 压力 | `:16-20` | `(v-0.1)/3.0*300-100` kPa，`round(,2)` |
| 电压 | `:22-24` | `read_uv()/1e6` V |
| 平均原始值 | `:26-39` | 连续读 10 次，去掉 min/max，其余 8 次累加后 `>>3`（16-bit 或 12-bit） |

**官方 API**：`get_pressure()`、`get_voltage()`、`get_analog_value(bits)`。

**主机输入**：`analog-mv`（100..3100）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"tube-pressure"`（支持列表 `:610-615`）
+ realize 分支复用 angle/light 的 ADC 输入（`m5_unit_adc_sample` `:781`、QOM
`analog-mv` + `adc-samples` `:992-1000`）。黄线 NC 不接线。guest 换算压力在
driver 侧完成，模型只提供 mV。

**可断言数据面标志**：guest `get_pressure()` 与 fixture 在量化误差内一致；
`get_voltage()` 一致；`adc-samples` 计数；`transactions/read-bytes/written-bytes`
全 0（无伪装 I2C）。

**风险/未确认**：传感器线性度/温补/±1.5kPa 精度 NOT RUN；页面公式与驱动公式
等价性已复算（100mV-110）；ADC 11DB 校准 unresolved；PORT.B 白线模拟、黄线 NC。

### 4.11 `laser-rx` — Unit Laser RX（U065）

**官方**：[Unit Laser RX](https://docs.m5stack.com/en/unit/laser-rx)（2026-11-02）；
SKU `U065`；ISO103 光电接收管；接收频率 140–205kHz；峰值波长 900nm；配对
LASER.TX。
**驱动**：`m5stack/libs/unit/laser_rx.py`（49 行，快照=master 语义相同）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`NC`、
White=`DOUT`。数字输出在白线。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 模式 | `unit/laser_rx.py:10-11` | `PIN_MODE`（GPIO）/`UART_MODE` |
| GPIO | `:15-18` | `Pin(port[0], Pin.IN, Pin.PULL_UP)`（白线，上拉输入） |
| UART | `:19-22,32-45` | `UART(id, tx=port[1], rx=port[0])`；read/readline/any |
| 电平 | `:47-49` | `value()` 返回 GPIO 电平 |

**官方 API**：`value()`（GPIO 模式）、`read()/readline()/any()`、`init_uart()`。

**主机输入**：`digital-level`（bool，默认高——上拉）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"laser-rx"`（支持列表 `:610-615`）+
realize 分支复用 PIR/limit 的数字输入：`esp32_gpio_set_input(white, !pressed)`
（`bool_set` 先例 `:679-700`），QOM `input-level`/`pressed`（只读观测）。黄线 NC
不接线。UART 模式需要 UART 拓扑，本批先只做 GPIO 模式并标 `unresolved`。

**可断言数据面标志**：guest `value()` 与注入电平一致；`input-events` 计数；
`transactions/read-bytes/written-bytes` 全 0。

**风险/未确认**：光学链路/光束/140–205kHz 接收频率/900nm 灵敏度 NOT RUN；
UART 模式未建模；配对 TX（U066）不在本批；PORT.B 白线 DOUT、黄线 NC。

### 4.12 `ultrasonic-io` — Unit Ultrasonic-IO（U098-B2）

**官方**：[Unit Ultrasonic-IO](https://docs.m5stack.com/en/unit/Unit_Ultrasonic-IO)
（2026-11-02）；SKU `U098-B2`；RCWL-9620 + 16mm 探头；2–450cm；40kHz；±2%；
触发后输出与回波时间对应的脉冲；测量周期 50ms。**页面 PinMap 把 PORT.A 标成
SDA/SCL，但描述/驱动都是 GPIO 触发+回波** → 标签复用冲突，按驱动引脚顺序处理。
**驱动**：`m5stack/libs/unit/ultrasonic_io.py`（53 行，快照=master 语义相同）。

**接线（按驱动端口元组 `(white, yellow)`）**：Black=`GND`、Red=`5V`、
Yellow=`Trigger`（`port[1]`，host→unit）、White=`Echo`（`port[0]`，unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 触发 | `unit/ultrasonic_io.py:19-20` | `Pin(port[1], OUT, pull=None)`，默认低 |
| 回波 | `:22` | `Pin(port[0], IN, pull=None)` |
| 脉冲 | `:24-35` | 拉低 5us → 拉高 10us → 拉低；`machine.time_pulse_us(echo, 1, timeout)` |
| 距离 | `:37-49` | `mm = echo_time*100//582`（声速 343.2m/s，往返除 2）；cm 再 /10 |
| 超时 | `:16` | `echo_timeout_us` 默认 1,000,000us |
| 周期 | `:47` | 每次测量后 `sleep_ms(50)` |

**官方 API**：`tx_pulse_rx_echo()`、`get_target_distance(mode)`。

**主机输入**：`distance-mm`（20..4500）。

**QEMU 建议**：`m5_unit_gpio.c` 新增 id `"ultrasonic-io"` + realize 分支：
黄线通过 `Esp32GpioPadObserver`（先例 `:560` AW3641）观测 guest 触发脉冲
（拉高 ≥10us）；在触发沿后用 QEMU 定时器把白线拉高 `pulse_us = distance_mm*582/100`
（往返时间），再拉低；白线同时接入 `esp32_gpio_set_input`，让
`machine.time_pulse_us` 读到真实脉宽。超时（>4500mm 或 fixture 设 timeout）
保持白线低电平直到 time_pulse_us 超时。QOM：`distance-mm`（可写 fixture）、
`echo-pulse-us`（只读换算）、`trigger-count`、`timeouts`。

**可断言数据面标志**：guest `get_target_distance(1)` 与 fixture 在换算误差内一致；
黄线 trigger 脉冲宽度/次数；`echo-pulse-us` 与 formula 一致；超时路径读 0/异常；
`transactions/read-bytes/written-bytes` 全 0。

**风险/未确认**：页面 PinMap 标 SDA/SCL 与 GPIO 事实冲突 unresolved；RCWL-9620
400ms/50ms 周期、>3.5m 响应延迟、温度补偿 NOT RUN；声学/40kHz/±2% 精度 NOT RUN；
`time_pulse_us` 的 timeout 语义需在实现时与 MicroPython 行为对齐。

## 5. 未确认项汇总（unresolved）

1. `rfid`：RF 场/天线/距离/真实卡片与密钥不建模（沿用 rfid2 边界）；0x28 与
   rfid2 冲突。
2. `vmeter`：EEPROM 出厂校准布局只有驱动出处，无真实系数（fixture 合成、不得
   宣称 1% 精度）；0x53 与 `accel` 冲突；±36V/隔离/保险丝 NOT RUN。
3. `scales`：HX711 采样时序/称重力学/去皮物理 NOT RUN；0x26 三方冲突；master
   常量重命名需钉 SHA；10SPS 输出率不建模。
4. `dac2`：15-bit vs 驱动 16-bit 满码编码 unresolved；0x59 与 `extencoder`
   冲突；模拟输出/短路保护 NOT RUN。
5. `extio`：INT 中断输出、A0–A2 焊盘改址、上下拉/开漏电气不建模；产品页 EOL。
6. `adc`：ADS1100 与 ADS1110 是不同型号（不得混用）；0x48 三方冲突；
   master/snapshot `get_raw_value()` 返回长度差异；精度/参考 NOT RUN。
7. `env-iv`：快照 SHT4x getter bug（`self.measure[0/1]` 缺调用）必须锚定 master
   修复版或打补丁；0x44 与 `env-iii` 冲突、0x76 与 `bps`/`env` 冲突；
   `ENVUnit` 必须显式 type=4；产品页 EOL；精度 NOT RUN。
8. `co2`：SCD40（页面/驱动）vs SCD41（官方 I2C 总表）芯片冲突；快照 async 实现
   vs master sync 实现两套 API 必须钉 SHA；5s 测量周期/CRC/精度 NOT RUN。
9. `pbhub`：MCU 身份三方冲突（页面 MEGA328 vs 规格 STM32F030F4P6 vs 总表
   MEGA328）；RGB 字节序快照大端 vs master GRB；hub 不支持嵌套；通道地址与多个
   独立 Unit 重叠；PWM/servo/RGB 电气/机械 NOT RUN。
10. `tube-pressure`：传感器线性度/温补/±1.5kPa 精度 NOT RUN；ADC 11DB 校准
    unresolved；页面公式与驱动公式已复算等价。
11. `laser-rx`：光学链路/140–205kHz/900nm NOT RUN；UART 模式未建模；配对 TX
    U066 不在本批。
12. `ultrasonic-io`：页面 PinMap 的 SDA/SCL 标签与 GPIO 事实冲突 unresolved；
    声学/温度补偿/±2% 精度与 >3.5m 延迟 NOT RUN；`time_pulse_us` 超时语义需对齐。

## 6. 驱动版本交叉核对（快照 vs 官方 master）

快照 HEAD `528edd8a06d2556c8e753c8e4978179bbb12b5ba`（`m5stack/version.txt` =
`V2.1.5`）。2026-11-02 逐文件下载 master 原文比对，22 个文件中 11 个逐字节相同、
11 个不同：

| 文件 | 快照 SHA-256（前 16） | master SHA-256（前 16） | 差异语义 |
| --- | --- | --- | --- |
| `unit/rfid.py` | `39c888f5ae118623` | `c71fb96399e00913` | 仅文档字符串/格式，AST 语义一致 |
| `unit/scales.py` | `63190d083f132be8` | `7753190c476f158c` | master 把模块级常量搬进类属性并加文档（值不变），语义一致 |
| `unit/co2.py` | `70081fa3bf228d35` | `9ea29cca598b6ca9` | **master 重写**为 `CO2Unit(SCD40)` 子类；快照自带完整命令层。命令常量一致，API/实现不同 |
| `unit/pbhub.py` | `7838aaa22d1a8e72` | `7091b8b03b98cc7f` | **语义不同**：master RGB 3B 改为 GRB 交换，并新增 `LED_CTRL_REG 0xFA` mode get/set |
| `unit/tube_pressure.py` | `0c097234dc4755ab` | `baa5fc1e0ee9cd1c` | AST 语义一致（仅注释/格式） |
| `unit/laser_rx.py` | `118dd190e8111808` | `a4cae3628c97a64b` | AST 语义一致 |
| `unit/ultrasonic_io.py` | `e8557de46fa9f86e` | `ce74eaa97d7b8023` | AST 语义一致 |
| `driver/pca9554.py` | `734e1ad418752ed6` | `51553d653996fe44` | 仅类型注解 + 文档字符串 |
| `driver/ads1100.py` | `b93cb45e509bddbc` | `a0d3a9813a68d081` | **语义不同**：master `get_raw_value()` 返回 `_BUFFER[0:2]`，快照返回完整 3B |
| `driver/sht4x.py` | `bfbfbd6983f51169` | `4c225ce93a7378a1` | **语义不同**：快照 `get_temperature/relative_humidity` 缺 `measure()` 调用（bug），master 修复并新增 `get_temperature/get_humidity` |
| `driver/scd40.py` | `0a8590c580190405` | `168ea241d593ac37` | **完全不同的实现**：快照 asyncio 异步驱动，master 同步命令层 |
| `unit/vmeter.py` | `cace78da627fc96b` | 同 | 逐字节相同 |
| `unit/dac2.py` | `5de7a05bf128010e` | 同 | 逐字节相同 |
| `unit/extio.py` | `d46a3d864988e2e7` | 同 | 逐字节相同 |
| `unit/adc.py` | `2d830058bee7f81b` | 同 | 逐字节相同 |
| `unit/env.py` | `a93c1b9fa822c2d7` | 同 | 逐字节相同 |
| `driver/checksum.py` | `100223c8df7e7c42` | 同 | 逐字节相同 |
| `driver/mfrc522/__init__.py` | `6462fa8be5d2d192` | 同 | 逐字节相同 |
| `driver/mfrc522/reg.py` | `04cf1608635abef8` | 同 | 逐字节相同 |
| `driver/mfrc522/cmd.py` | `10f1970913fda99a` | 同 | 逐字节相同 |
| `driver/mfrc522/firmware.py` | `1a08760b07e2d0d2` | 同 | 逐字节相同 |
| `driver/bmp280.py` | `01cd715d416cad44` | 同 | 逐字节相同 |

实现建议：catalog 草稿的 `evidence[].sha256` 同时记录**快照哈希**；若实现者使用
master 版本，必须在实现 PR 里显式写明并锚定 master 哈希。`env-iv`/`adc`/`pbhub`/
`co2` 必须钉一个 SHA，不能混用两版语义。

## 7. 落地顺序建议

1. `rfid`（A）：零新 kind，直接证明 `CONTROL_RFID2` 可复用；与 `rfid2` 做地址
   冲突负例。
2. `tube-pressure`（A）：验证现有 GPIO ADC 分支可直接复用（纯输入）。
3. `laser-rx`（A）：验证数字输入分支与 `pressed/input-level` 语义。
4. `extio`（B）：验证 controls 框架的 4 寄存器 I/O 扩展器（input/output/
   polarity/config 组合语义）。
5. `dac2`（B）：验证 controls 框架的多字节 LE 写与量程/通道换算（15-bit 未决）。
6. `scales`（B）：验证 4B BE 寄存器 + 校准/RGB 寄存器组（与 weight-i2c 差分）。
7. `vmeter`（B）：复用 0126 双从机 ameter 模式，换地址/分压系数。
8. `adc`（B）：新增 `US_ADS1100`，与 `US_ADS1110` 做差分验证。
9. `env-iv`（C）：新增 `US_SHT4X` 命令+CRC 响应，复用 `US_BMP280` 双从机。
10. `co2`（C）：新增 SCD4x 命令+CRC 状态机（数据就绪门控 + 周期测量）。
11. `pbhub`（C）：多地址 hub（7 slave）+ 每通道寄存器文件；先做静态寄存器
    读写，再做 RGB/模拟输入 fixture。
12. `ultrasonic-io`（C）：最后一款，需要 trigger 观测 + echo 脉冲定时器；
    先做固定 distance fixture，再做超时路径。

## 8. 官方来源清单（本批引用）

**产品页（2026-11-02 读取）**：

- <https://docs.m5stack.com/en/unit/rfid>
- <https://docs.m5stack.com/en/unit/vmeter>
- <https://docs.m5stack.com/en/unit/UNIT%20Scales>
- <https://docs.m5stack.com/en/unit/Unit-DAC2>
- <https://docs.m5stack.com/en/unit/extio>
- <https://docs.m5stack.com/en/unit/adc>
- <https://docs.m5stack.com/en/unit/Unit_ENV-IV>
- <https://docs.m5stack.com/en/unit/co2>
- <https://docs.m5stack.com/en/unit/Unit_PbHub>
- <https://docs.m5stack.com/en/unit/Unit_Tube_Pressure>
- <https://docs.m5stack.com/en/unit/laser-rx>
- <https://docs.m5stack.com/en/unit/Unit_Ultrasonic-IO>
- 官方 I2C 地址总表：<https://docs.m5stack.com/en/product_i2c_addr>

**官方驱动（快照路径，`m5stack/libs/` 下）**：

- `unit/rfid.py`、`unit/vmeter.py`、`unit/scales.py`、`unit/dac2.py`、
  `unit/extio.py`、`unit/adc.py`、`unit/env.py`、`unit/co2.py`、`unit/pbhub.py`、
  `unit/tube_pressure.py`、`unit/laser_rx.py`、`unit/ultrasonic_io.py`
- `driver/mfrc522/{__init__,reg,cmd,firmware}.py`、`driver/pca9554.py`、
  `driver/ads1100.py`、`driver/sht4x.py`、`driver/scd40.py`、`driver/checksum.py`、
  `driver/bmp280.py`

**链接但未读的 datasheet/协议文档**：各产品页 Datasheets 节列出的 MFRC522/
ADS1115/GP8413/PCA9554/ADS1100/SHT40/BMP280/SCD40/MCP-H10-B200KPPN/RCWL-9620/
ISO103 等 PDF。按仓库既有方法，这些只作为实现参考链接，不声称内容已独立复核。

## 9. 复现方式

```bash
cd /Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public
git rev-parse HEAD   # 528edd8a06d2556c8e753c8e4978179bbb12b5ba
cat m5stack/version.txt   # V2.1.5

# 快照 vs master 逐文件哈希
for f in unit/rfid.py driver/mfrc522/__init__.py ...; do
  sha256sum "m5stack/libs/$f"
  curl -sfL "https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/$f" | sha256sum
done
```

本报告未运行任何 QEMU/固件/Device Service；不产生运行时 PASS。

## 10. catalog 草稿说明

`2026-11-02-batch3-catalog-draft.json` 的 12 条记录：

- 字段对齐 `platform/units/catalog.json` 现有条目
  （`id/name/sku/visual_asset/official_docs/checked_at/chips/interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/blocker/input_semantics/output_semantics/limitations`）；
- 全部 `model_status: "planned"`、`runtime.status: "unsupported"`（草稿，不是
  runtime admission）；
- `address_7bit` 用 **7-bit**；双地址型号（`vmeter`/`env-iv`）列出两个地址，
  `pbhub` 列出 hub 地址（通道地址在 protocol 表说明，不放进 `address_7bit`）；
- `evidence[].sha256` 记录快照哈希，`sha256_matches_snapshot_528edd8` 标记是否与
  快照一致，`sha256_master` 在差异文件中额外记录 master 哈希；
- 所有 `inputs.*.default` 都是合成测试 fixture，不是实测值；`blocker` 写明实现
  前置条件与硬件边界。

## 11. 本轮已实现的 A+B 数据面（0130，2026-11-02）

`patches/qemu-m5stack-peripherals/0130-unit-batch3ab.patch` 把 §4.1–4.6/4.10/4.11 的
8 款落到 QEMU 数据面。catalog 仍全部 `planned`，无 guest 证据、无功能 PASS；
离线 QOM smoke 只验证属性注册、fixture 读写/范围拒绝、只读拒绝和地址接线。

| Unit | QEMU 接入点 | 已实现的数据面 | 仍未确认/未建模 |
| --- | --- | --- | --- |
| `rfid` U031 | 复用 `CONTROL_RFID2`（0x28） | MFRC522 命令面、合成 MIFARE 卡、UID/认证/FIFO 观测 | RF 场/天线/读卡距离/真实卡片与密钥；0x28 与 rfid2 冲突 |
| `tube-pressure` U130 | `m5_unit_gpio.c` 单端 ADC | 白线 `analog-mv`/`adc-samples`，只读 `pressure-kpa` 便利换算 | 传感器线性度/温补/±1.5kPa；ADC 11DB 校准 |
| `laser-rx` U065 | `m5_unit_gpio.c` 数字输入 | 白线 DOUT 上拉输入、`digital-level`/`input-level` | UART 模式、光学链路/140–205kHz/900nm |
| `extio` U011 | 新 `CONTROL_PCA9554`（0x27） | input/output/polarity/config 4 寄存器语义、数组 fixture | INT 输出、A0–A2 焊盘改址、上下拉电气 |
| `dac2` U012-B | 新 `CONTROL_DAC2`（0x59） | 0x01 量程、0x02/0x04 LE 通道码、只读 raw/电压观测 | 15-bit vs 16-bit 满码；模拟输出/短路保护；0x59 与 extencoder 冲突 |
| `scales` U108 | 新 `CONTROL_SCALES`（0x26） | 4B BE raw/weight/offset、按钮/LED、校准写计数、0xFF 地址迁移 | HX711 采样/称重力学/去皮物理；0x26 与 4relay/weight-i2c 冲突 |
| `vmeter` U087 | `US_ADS1115_VMETER`+EEPROM（0x49/0x53） | 参数化 ameter 双从机、0.015918958 分压、合成 factor 1.0 校准 | 真实出厂校准/±36V/隔离/保险丝；0x53 与 accel 冲突 |
| `adc` U013 | 新 `US_ADS1100`（0x48） | 1 字节 config、3 字节 data/config 读、voltage-v 反算 | ADS1100 vs ADS1110、master/snapshot `get_raw_value()` 长度差异、精度/参考；0x48 三方冲突 |

上表所有“仍未确认/未建模”项都同步记录在 catalog blocker 与
`platform/web/unit-visual-mappings.js` 的 AUDIT 条目中；A+B 之外的 4 款
（env-iv/co2/pbhub/ultrasonic-io）由并行的 0131 任务负责。
## 11. 后 4 款（C 类）QEMU 实现状态（0131，2026-11-02）

第三批 C 类 4 款（`env-iv`/`co2`/`pbhub`/`ultrasonic-io`）已由
[`0131-unit-batch3c.patch`](../../patches/qemu-m5stack-peripherals/0131-unit-batch3c.patch)
接入 QEMU 数据面；base 为 canonical native layer `75f1d24` + 已合入的
`0120/0121/0122/0123/0125/0126/0127/0128/0129`（`0124` 为 StickT2 预留层，本补丁
不依赖；`0130` 是并行 unit-protocols A+B 层，不属于本补丁 base）。**尚未采集
guest/Device Service 证据**，因此 catalog 4 条与 runtime-profiles 4 条均保持
`planned`、hosts 为空。离线 QOM smoke 只验证属性注册、fixture 读写、范围拒绝、
只读拒绝与双从机结构（23/23 PASS），不构成功能 PASS。

**研究草稿修正**：§4.9 曾把 PbHub 的 6 个通道基址写成了 6 个独立总线地址并建议
`m5_unit_i2c_attach` ×7；实现时按官方驱动逐行复核，`unit/pbhub.py` 的所有
`writeto_mem`/`read_reg` 都发往**单一 hub 地址 0x61**，`channel_base|offset`
是**寄存器字节**而不是总线地址。因此 0131 用单个 `CONTROL_PBHUB`（0x61）实现
256 字节命令空间，`m5_unit_i2c_attach` 只用于 `env-iv` 的双从机。catalog blocker
已按这一修正写入，不再声称 7 个总线地址。

| Unit | 0131 模型 | QOM fixtures/观测 | 仍需 guest 证据 / unresolved 边界 |
| --- | --- | --- | --- |
| `env-iv` U001-D (0x44 + 0x76) | 双从机：`US_SHT4X` 0x44（命令字节 + 6B T/RH 或序列号帧，每 2B 后 CRC8 poly 0x31）+ 复用 `US_BMP280` 0x76（仅 pressure-pa，自身温度槽固定 25C） | 输入 temperature-c(-40..125)/humidity-pct(0..100)/pressure-pa(30000..110000)；观测 serial-number、两地址事务计数 | **快照 driver/sht4x.py getter bug（缺 measure() 调用）→ 必须锚定 master 修正版或打补丁**；0x44 与 env-iii 冲突、0x76 与 bps/env 冲突；ENVUnit 必须显式 type=4；产品页 EOL；精度/自热 NOT RUN |
| `co2` U103 (0x62) | `US_SCD40`：2B BE 命令 + 每 2B 数据 CRC8 词协议；0xE4B8 就绪、0xEC05 测量（9B）、0x241D/0x2318、0x2427/0x2322、0xE000、0x3682、0x3646/0x3632、0x21B1/0x3F86/0x21AC、0x219D/0x2196 等；周期/单次/复位状态转移 | 输入 co2-ppm(400..5000)/temperature-c(-10..60)/humidity-pct(0..95)/data-ready；观测 serial-number/measurement-reads | **SCD40（页面/驱动）vs SCD41（I2C 总表）冲突；快照 asyncio 实现 vs master 同步重写两套 API 必须钉 SHA；两份驱动的温度解码都从 buf[1] 而非 buf[4] 取值（既有 bug）→ guest temperature 不可断言，只有 CO2/湿度可断言**；5s 周期/CRC/精度 NOT RUN |
| `pbhub` U041 (0x61) | `CONTROL_PBHUB`：单一 0x61 命令空间；通道 base 0x40/0x50/0x60/0x70/0x80/0xA0 × offset 0x00..0x0B；数字/模拟/RGB/servo/brightness 写更新每通道状态，0xFA RGB mode、0xFF 地址迁移（0x61..0x68） | 输入 digital-inputs[6]/analog-inputs[6]（0..1023）；观测 digital-outputs/pwm-outputs/rgb-frames[6]/rgb-mode/fw-version/i2c-address | **MCU 身份三方冲突（页面 MEGA328 vs 规格 STM32F030F4P6 vs 总表 MEGA328）；RGB 字节序快照大端 vs master GRB（实现取 master GRB，须写 SHA）；通道命令地址与 encoder/scroll/nfc/acssr/dac/env-iii 重叠只在 hub 命令空间内部暴露；hub 不支持嵌套；PWM/servo/RGB 电气与 10-bit ADC 校准 NOT RUN** |
| `ultrasonic-io` U098-B2 (GPIO) | GPIO id `ultrasonic-io`：黄线 pad observer 观测 trigger 上升/下降沿，下降沿按 distance-mm 生成 `pulse_us=distance_mm*582/100` 白线高脉冲；越界距离不生成回波（guest 收到真实超时）；复位/超时计数 | 输入 distance-mm(20..4500)；观测 echo-pulse-us(=distance*582/100)、trigger-count、timeouts、echo-level | **页面 PinMap 把 PORT.A 标成 SDA/SCL，与 GPIO trigger/echo 事实冲突；MicroPython time_pulse_us 超时语义 unresolved（模型只覆盖有回波/无回波两条路径）；RCWL-9620 >3.5m 延迟、50ms 周期、温度补偿、±2% 精度、40kHz 声学 NOT RUN** |

离线 QOM smoke 复现（无 guest 固件；`m5basic` machine，env-iv/co2/pbhub 共享
32/33 软 I2C 总线，ultrasonic-io 用 yellow=26/white=36）：

```bash
cat > /tmp/unit-smoke-config3.json <<'JSON'
{"schema_version":1,"attachments":[
 {"id":"enviv1","unit_id":"env-iv","pins":{"yellow":32,"white":33}},
 {"id":"co21","unit_id":"co2","pins":{"yellow":32,"white":33}},
 {"id":"pbhub1","unit_id":"pbhub","pins":{"yellow":32,"white":33}},
 {"id":"ultra1","unit_id":"ultrasonic-io","pins":{"yellow":26,"white":36}}]}
JSON
M5_UNIT_CONFIG=/tmp/unit-smoke-config3.json qemu-system-xtensa -M m5basic \
  -L .work/M5StopWatch-QEMU/build/qemu/pc-bios -display none \
  -serial null -serial null -serial null \
  -qmp unix:/tmp/unit-smoke3.sock,server=on,wait=off
# 另一个终端：qom-get/qom-set /machine/units/<id>/<property>
```

23 项检查全部 PASS：env-iv 7（默认值/三个 fixture 写入/范围拒绝/双从机子对象
`sht4x`@0x44 + `bmp280`@0x76）、co2 6、pbhub 6（默认数组/输入写入/范围与长度
拒绝/只读拒绝）、ultrasonic-io 4（默认 distance-mm=1000→echo-pulse-us=5820/
distance 500→2910/越界拒绝）。该 smoke **不**覆盖 I2C `send/recv` 字节语义、
SCD4x 命令/CRC 词、PbHub 通道命令写入与 ultrasonic 触发时序；这些仍需 guest 证据。

**计数说明**：本分支 base `origin/main cde329f5` 的 catalog 为 58 款，加上本批 4 款
后为 **62 款**（catalog 与 runtime-profiles 都是 62）。Lead 描述的“66→70”应指
并行 unit-protocols A+B 8 款（0130）合并后的总数：58+8=66 → 62+8=70。本分支的
计数测试按 worktree 实际值 62 更新；合并后由集成 PR 统一到 70。

共同边界：4 款都是控制器可见的事务/时序模型，不是电气/光学/声学/气体传感器物理
模型；地址冲突（env-iv 0x44/0x76、co2 0x62 无冲突、pbhub 通道命令地址只在 hub
内部）与版本差异必须随 catalog 一起读。没有 guest 与 Device Service 证据前不得
升级为 `implemented`/`simulated`。
