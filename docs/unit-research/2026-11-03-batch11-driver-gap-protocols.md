# Unit 第十一批：driver-gap 17 款官方协议网络研究

日期：`2026-11-03`。范围：batch10 标记为 driver-gap `planned` 且此前"无官方驱动/无公开协议"的
17 款 Unit：`cardkb2`/`8servos2-i2c`/`8servos2-chain`/`bmm350`/`ina226-10a`/`ina226-1a`/
`rollercan`/`rollercan-lite`/`roller485`/`roller485-lite`/`byteswitch`/`bytebutton`/`step16`/
`timerpwr`/`mq`/`cat1-cn`/`chainbus`。

本批**只做网络检索与文档研究**：不改 `platform/units/catalog.json`、不改模型/测试/profile，
不运行 QEMU，所有 a/b 结论仍按 `planned` 契约对待。产出为本文档 +
`2026-11-03-batch11-driver-gap-catalog-draft.json`（仅作将来补 `protocol` 字段的草稿）。

固定输入：

- 本 worktree：`/Users/m5agent/Documents/ChatGPT/esp-emulator-unitdoc`（分支
  `m5agent/unit-doc-research`，base `origin/main` `36e5e11a`）。
- 冻结 UIFlow2 快照：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （V2.1.5，HEAD `528edd8`）——**确认没有**这 17 款的 Unit 驱动（`m5stack/libs/unit/` 117 个文件）。
- 上游 UIFlow2：`m5stack/uiflow-micropython` **master** `f20d5a00e8c9106aae1d944f3d6f1128839f59cb`
  （2026-11-02 提交，`master` 分支）——**已新增绝大多数驱动**，见 §1。
- 官方文档站：`https://docs.m5stack.com`；所有引用页面/PDF 于 `2026-11-03` 抓取（HTTP 200）。
- 官方 GitHub 仓库：`M5Unit-*` / `M5Chain-*` / `M5UnitUnified` 的 `main`/`master` 分支，
  浅克隆 HEAD SHA 见 §8；协议 PDF/Markdown 直接来自这些仓库与 `m5stack-doc.oss-cn-shenzhen.aliyuncs.com`。
- 厂商 datasheet：TI INA226（SBOS547C，2026-08 修订）、Bosch BMM350
  （BST-BMM350-DS001-27）、OneMO ML307R AT 命令手册（V1.8.1，2024-02-02）。

## 0. 结论摘要

**核心结论：17/17 款都存在可核对的官方公开协议证据，此前 "无公开协议/无驱动" 的结论应被纠正，
但本批不建模型、不登记，仅把协议依据转成可实现契约草稿。**

| 分类 | 数量 | 型号 |
| --- | --- | --- |
| a 有公开协议、可建最小数据面模型 | **15** | `8servos2-i2c`、`8servos2-chain`、`bmm350`、`ina226-10a`、`ina226-1a`、`roller485`、`roller485-lite`、`rollercan`、`rollercan-lite`、`byteswitch`、`bytebutton`、`step16`、`timerpwr`、`mq`、`chainbus` |
| b 部分可建（列出可建子集与缺口） | **2** | `cardkb2`（I2C legacy + UART 可建；V2 report 寄存器/固件版本、BLE HID/ESP-NOW 不可建）、`cat1-cn`（AT 字节层/命令-响应可建；蜂窝 RF/SIM/PDP/网络/云不可建） |
| c 仍无公开协议 | **0** | —（此前 17 款全部升级为 a/b） |

关键证据来源（逐款 URL 与 file:line 见 §4/§5/§8）：

1. **上游 UIFlow2 master 已有 17/17 款驱动**（`unit/` 或 `chain/` 包）：
   `ina226.py`（含 `type="1A"/"10A"`）、`bmm350.py`、`step16.py`、`timerpwr.py`、`mq.py`、
   `roller485.py`、`rollercan.py`、`servos8_v2.py`（I2C）、`chain/servos8_v2.py`（Chain）、
   `cardkb.py`（含 CardKB2 多模式）、`cat1.py`、`bytebutton.py`（`ByteSwitchUnit` 复用同一驱动）、
   `chain/unit_bus.py`（ChainBus）、`chain/chain.py`（Chain 链路层）。
   冻结快照 `528edd8` 没有这些文件，说明 blocker 是**快照落后**而不是厂商没有公开实现。
   （`cardkb2`/`cat1-cn` 因另有协议缺口仍归 b 类，但驱动源码同样存在。）
2. **官方协议文档已公开**：`docs.m5stack.com` 的 `/en/protocol/<SKU>/<bus>` 协议页（本批命中
   `U222/I2C`、`U223/UART`），以及每个 Unit 产品页 "Datasheet" 区链接的官方协议 PDF（Roller485/
   RollerCAN 的 I2C+RS485/CAN、ByteSwitch、ByteButton、Step16、TimerPWR、MQ、ChainBus、
   CardKB2 User Manual）和 GitHub `M5Unit-*-Internal-FW` 仓库中的协议 `.md`/`.xlsx`/`.pdf`。
3. **厂商 datasheet 提供寄存器表**：TI INA226 `Table 7-1`（p.22）完整寄存器集；
   Bosch BMM350 `Table 8`（p.26–28）寄存器图 + §9.2.3 I2C 读需要丢弃前 2 个 dummy 字节；
   OneMO ML307R `AT Commands Reference Guide 4G Series V1.8.1`（191 页，105 条 AT 命令）。

## 1. 与 batch9/batch10 结论的差异（为什么可以纠正）

| 此前 blocker（batch9/batch10） | 本批证据 | 结论 |
| --- | --- | --- |
| CardKB2 "I2C 地址未知、寄存器/帧格式在外部手册" | 官方 User Manual PDF：I2C `0x5F` 原始键值读、`0xF1` 版本；UART `AA 03 KEYID STATE CRC` 115200 8N1；上游 `cardkb.py` 还实现 v2 report（`0x00`–`0x03` 8 字节报告） | 升级 **b**（legacy I2C/UART 可建；v2 report 未写入官方手册、BLE HID/ESP-NOW 不可建） |
| 8Servos2-I2C "Internal Firmware/Protocol 表不可读" | `docs.m5stack.com/en/protocol/U222/I2C` 完整 V2.0 协议页 + 官方 PDF `protocol/V2/...EN_V2.0.pdf` + 上游 `unit/servos8_v2.py` 寄存器常量 | **a** |
| 8Servos2-Chain "Chain 协议外部文档、无帧表" | `docs.m5stack.com/en/protocol/U223/UART` 完整帧/命令表（0x10–0xFE，含 CRC/设备类型 0x000C）+ 上游 `chain/servos8_v2.py` | **a** |
| BMM350 "无寄存器表，只能 datasheet" | Bosch 官方 datasheet `Table 8` + 上游 `driver/bmm350.py` 驱动寄存器常量（0x00/0x04/0x05/0x06/0x31/0x50/0x52/0x53/0x55/0x7E） | **a** |
| INA226 "无 Unit driver，datasheet 未钉" | TI datasheet `SBOS547C Table 7-1` + 上游 `unit/ina226.py` 的 1A/10A 参数与校准值 | **a** |
| Roller485/CAN 家族 "内部固件/通信协议外部且 unresolved" | 官方 Docs 协议 PDF + `M5Unit-Roller485-Internal-FW` / `M5Unit-RollerCAN-Internal-FW` 仓库内最新协议 Markdown（I2C 寄存器总览、RS485/CAN 帧格式、CRC、参数索引表）+ 上游驱动 | **a**（4 款） |
| ByteSwitch/ByteButton "页面 Protocol 表不可读" | 官方协议 PDF `Byte_Switch_protocol.pdf` / `Byte_Button Protocol.pdf`（完整 0x00–0xFF 寄存器表）+ 上游共享驱动 + Internal-FW 源码 | **a**（2 款） |
| Step16/TimerPWR/MQ "页面无完整寄存器表" | 官方协议 PDF（Step16 V1、TimerPWR V1、MQ V1 EN）+ `M5Unit-*-Internal-FW` 的 PDF/xlsx + 上游驱动寄存器常量 | **a**（3 款） |
| ChainBus "Chain/扩展寄存器表不可读" | 官方 `M5Stack-Unit-ChainBus-Protocol-EN.pdf`（I2C/GPIO/ADC/中断/设备类型 0x0006 完整命令）+ 上游 `chain/unit_bus.py` + `chain/chain.py` | **a** |
| Cat1-CN "AT/URC 命令集外部 unresolved" | 官方页直链 OneMO `AT_Commands_Reference_Guide_4G_Series_V1.8.1.pdf`、`ML307R_Communication_Process_Example_V1.0.1.pdf` + 上游 `unit/cat1.py`/`driver/simcom/ml307r.py` | **b**（AT 命令面可建，蜂窝/网络不可建） |

## 2. 方法与证据口径

- 只信"官方产品页 + 官方协议 PDF/Markdown + 官方驱动源码 + 厂商 datasheet"；页面/驱动/协议
  文档互相冲突时，以**协议文档 + 驱动源码交叉验证**为准，冲突显式写 unresolved。
- 网络内容按**不可信数据**处理：只提取产品/协议事实，不执行页内任何指令；不下载/运行固件
  二进制（本批未下载 hex/bin）。
- 驱动引用固定到上游 commit `f20d5a00...`，避免浮动 `master`；协议 Markdown 引用固定到各
  Internal-FW 仓库克隆 HEAD（§8），PDF 引用固定到文档站 OSS URL。
- 只登记"寄存器/命令/帧格式"；**没有证据的字段不写**（例如 Motor FOC 内部实现、传感器
  物理量换算曲线未公开的部分标 unresolved）。
- 分类口径：
  - a = 官方公开了完整到"可写 QEMU 从机/应答器数据面"的寄存器或帧格式，且上游驱动可作
    guest 侧断言参照；
  - b = 只有控制面/子集公开，或关键模式依赖未公开固件版本/物理栈（RF、BLE、网络）；
  - c = 找不到任何可核对协议（本批为 0）。

## 3. 总线/地址/冲突总览

| 型号 | SKU | 总线 | 地址/波特率 | 官方协议文档 | 上游驱动（master `f20d5a0`） |
| --- | --- | --- | --- | --- | --- |
| byteswitch | U191 | I2C | `0x46` | `Byte_Switch_protocol.pdf` | `unit/bytebutton.py`（`ByteSwitchUnit`） |
| bytebutton | U192 | I2C | `0x47` | `Byte_Button Protocol.pdf` | `unit/bytebutton.py`（`ByteButtonUnit`） |
| step16 | U198 | I2C | `0x48`（可配 0x08–0x77） | `Unit-Step16_Protocol.pdf` | `unit/step16.py` |
| timerpwr | U189 | I2C | `0x56` | `U189_UnitTimerPwr_I2C_Protocol_V1_20241018.pdf` | `unit/timerpwr.py` |
| mq | U199 | I2C | `0x11`（可配 0x08–0x77） | `MQ_I2C_Protocol_EN.pdf` + xlsx | `unit/mq.py` |
| 8servos2-i2c | U222 | I2C | `0x25` 基址 + 旋钮 0–15 → `0x25`–`0x34` | `/en/protocol/U222/I2C` + V2.0 PDF | `unit/servos8_v2.py` |
| 8servos2-chain | U223 | UART Chain | 115200 8N1 | `/en/protocol/U223/UART` | `chain/servos8_v2.py` |
| chainbus | U212 | UART Chain | 115200 8N1，设备类型 `0x0006` | `M5Stack-Unit-ChainBus-Protocol-EN.pdf` | `chain/unit_bus.py` + `chain/chain.py` |
| cardkb2 | U215 | I2C / UART | `0x5F` / 115200 8N1 | `Unit_CardKB2_User_Manual_EN.pdf` | `unit/cardkb.py` |
| bmm350 | U231 | I2C | `0x14` | Bosch `BST-BMM350-DS001-27` | `unit/bmm350.py` + `driver/bmm350.py` |
| ina226-10a | U200 | I2C | `0x41` | TI `SBOS547C` | `unit/ina226.py`（`type="10A"`） |
| ina226-1a | U200-1A | I2C | `0x41` | TI `SBOS547C` | `unit/ina226.py`（`type="1A"`） |
| rollercan | U188 | I2C / CAN | `0x64` / CAN 扩展帧，默认 1 Mbps | `Unit-RollerCAN-{I2C,CAN}-Protocol-EN.pdf` + `protocol/*.md` | `unit/rollercan.py` |
| rollercan-lite | U188-Lite | I2C / CAN | 同上（官方页链接同一组协议 PDF） | 同上 | `unit/rollercan.py` |
| roller485 | U182 | I2C / RS485 | `0x64` / RS485 115200 8N1 | `Unit-Roller485-{I2C,RS485}-Protocol-EN.pdf` + `protocol/*.md` | `unit/roller485.py` |
| roller485-lite | U182-Lite | I2C / RS485 | 同上 | 同上 | `unit/roller485.py` |
| cat1-cn | U204 | UART AT | 115200 8N1（可至 460800） | ML307R AT 手册 V1.8.1 + 通信流程示例 V1.0.1 | `unit/cat1.py` + `driver/simcom/ml307r.py` |

**地址冲突（实现期必须检查）：**

- **I2C `0x64` 四款互斥**：`roller485`/`roller485-lite`/`rollercan`/`rollercan-lite` 默认都
  `0x64`；同一总线同地址只能挂一个，且 I2C 模式与 RS485/CAN 模式互斥（见协议文档）。
- **I2C `0x41` 两款**：`ina226-10a`（5 mΩ、±10A）与 `ina226-1a`（80 mΩ、±1A）同地址，
  校准常量不同；QEMU 若要按 SKU 区分，需按模型 attachment 参数化 `shunt/cal/量程`。
- `0x48`/`0x56`/`0x11` 可被改地址并写 Flash；`0x46`/`0x47`/`0x25–0x34`/`0x5F`/`0x14` 与现有
  Unit 地址表的冲突按实际总线实例检查（`0x14` 与 DoF9/DoF10 板上 BMM350 同地址但通常不同总线）。
- UART：`8servos2-chain`/`chainbus` 共用 Chain 总线和设备 Index；`cat1-cn`/`cardkb2` 也占
  UART；PORT.C 等 UART attachment 冲突沿用既有规则（一条总线一个 UART Unit）。
- CAN：`rollercan`/`rollercan-lite` 依赖 0145 `CanBusClient` 观测能力；CAN 电气/位定时/过滤
  NOT RUN（沿用既有 `can`/`mini-can` 边界）。
- RS485：`roller485`/`roller485-lite` 半双工 8N1，CRC-8/MAXIM；当前仓库无通用 RS485 控制器
  attachment，需先按 0145 UART 字节层或新 attachment 方案评估。

## 4. a 类逐款（15 款）

> 通用抓取日期：`2026-11-03`。每条"官方页面"= 产品页（SKU/接口/地址），"协议 PDF/MD"= 官方协议文档，
> "驱动"= 上游 UIFlow2 master 固定 commit 下的源码。所有 QEMU 建议都只是**沿用既有框架的方案**，
> 不代表已实现、更没有 guest 证据。

### 4.1 `byteswitch`（U191，I2C `0x46`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit%20ByteSwitch（U191，5V，PORT.A，
  STM32G031，8 路 DPDT 拨动开关 + 9×WS2812C）；协议 PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/820/Byte_Switch_protocol.pdf（V1，2024-06-19）。
- 寄存器表（PDF 与驱动 `unit/bytebutton.py:5-23` 一致，单位 B）：
  - `0x00` R：8 路开关位图，bit0–bit7 = switch0–7（每 bit 1=…，实际电平以固件为准）。
  - `0x60`–`0x67` R：每路开关单独 1 字节（PDF 标 `SwitchX: 0~1`）。
  - `0x10`–`0x18` W/R：LED0–LED8 亮度（0–255）；`0x19` W/R：LED 显示模式（0=user，1=sys）。
  - `0x20`–`0x4F` W/R：user RGB888，9 灯 × 4 字节步长（B/G/R + 保留），
    `reg = 0x20 + (n//4)*0x10 + (n%4)*4`（`unit/bytebutton.py:16,125-158`）。
  - `0x50`–`0x58` W/R：user RGB233（bit7:6=R，bit5:3=G，bit2:0=B）。
  - `0x70`–`0x8F` W/R：sys RGB888（switch=0 / 按下态）；`0x90`–`0xAF` W/R：sys RGB888
    （switch=1 / 未按下态）。
  - `0xF0` W：写 1 保存到 Flash；`0xF1` W：IRQ enable（使能后 PA13 变 IRQ，读 `0x00` 清中断）；
    `0xFE` R：固件版本；`0xFF` R/W：I2C 地址（1–127）。
- 驱动：`unit/bytebutton.py:4` `class ByteUnit`、`:5` `BYTESWITCH_I2C_ADDRESS=0x46`、
  `:348` `class ByteSwitchUnit`、`:341` `class ByteButtonUnit`；上游别名
  `unit/__init__.py:23` `"ByteSwitchUnit": "bytebutton"`。
- QEMU 数据面建议：新增一个 `CONTROL_BYTEUNIT` I2C 从机（或两实例参数化），实现
  `0x00`/`0x60` 读状态、`0x10-0x19` LED、`0x20-0xAF` RGB、`0xF0/0xF1/0xFE/0xFF` 系统寄存器；
  ByteSwitch 与 ByteButton 共用一个模型、按 attachment 属性区分 0x46/0x47 与状态极性。
- Fixture/注入：QOM `switch-bitmap`（或 `switch0..7`）、`led-brightness[9]`、`user-rgb[9]`、
  `sys-rgb[9]`、`led-mode`、`irq-enable`、`firmware-version`。
- 可断言量：guest 读 `0x00` 位图/`0x60` 单通道 == fixture；写亮度/RGB 后 QOM 回读一致；
  `get_firmware_version`、`get_switch_state`（驱动 `==0` 为按下/闭合，注意极性）可断言。
- Unresolved：开关机械/拨动电气、WS2812 光学、级联双 Grove 行为、IRQ 引脚电气 NOT RUN；
  `0x00` 位图"1"的物理含义（PDF 未写，按驱动 `get_switch_state` 反推为 0=闭合）需真机/示波器确认。

### 4.2 `bytebutton`（U192，I2C `0x47`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit%20ByteButton（U192，8 按键 + 9×WS2812C，
  STM32G031）；协议 PDF
  https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteButton/Byte_Button%20Protocol.pdf
  （V1，2024-06-19）。
- 寄存器表：与 `byteswitch` 完全同构（`0x00` 位图、`0x60` 单通道、`0x10-0x19` LED、
  `0x20-0x4F` user RGB888、`0x50` RGB233、`0x70/0x90` sys RGB888、`0xF0/0xF1/0xFE/0xFF`）；
  差异只有默认地址 `0x47` 与按键语义（`ByteButtonUnit` 驱动 `unit/bytebutton.py:341`）。
- 驱动：同上；`unit/__init__.py:22` `"ByteButtonUnit": "bytebutton"`。
- QEMU 数据面建议：与 `byteswitch` 共用模型，`attachment` 参数 `variant=bytebutton` 默认 0x47。
- Fixture/注入：`button-bitmap`、`button0..7`、LED/RGB/IRQ/FW 同名属性；按键按下=0（驱动
  `get_button_state` 返回 `read == 0`）。
- 可断言量：位图/单键读、LED RGB 写回读、IRQ 使能读回、FW 版本。
- Unresolved：按键机械/光学、9 灯 WS2812 与串接方向、IRQ 电气 NOT RUN。

### 4.3 `step16`（U198，I2C `0x48`，可配 0x08–0x77）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_Step16（U198，16 位 BCD 旋钮 + 7 段显示 +
  1×WS2812，STM32G031，100 ms 更新）；协议 PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1160/Unit-Step16_Protocol.pdf（V1，2025-07-04）；
  仓库内同文 https://github.com/m5stack/M5Unit-Step16-Internal-FW/blob/f38479ae964f/protocol/M5Unit-Step16-I2C-Protocol-EN_V1.0.pdf 。
- 寄存器表（PDF 与 `unit/step16.py:30-41` 一致）：
  - `0x00` R：编码器当前值 0–15（有符号增量语义）；
  - `0x10` W/R：LED 配置 0x00=常灭、0xFE=常亮、0–0xFD=无变化 N 秒后睡眠；默认 0xFE；
  - `0x20` W/R：LED 亮度 0–100（默认 50）；
  - `0x30` W/R：旋转方向 0=逆时针增、1=顺时针增（默认 1）；
  - `0x40` W/R：RGB 电源 0/1（默认 1）；`0x41` W/R：RGB 亮度 0–255；
  - `0x50/0x51/0x52` W/R：RGB R/G/B（0–255）；
  - `0xF0` W：写 1 保存 LED 配置、写 2 保存 RGB 配置；
  - `0xFE` R：固件版本；`0xFF` W/R：I2C 地址 0x08–0x77（立即生效并写 Flash）。
- 驱动：`unit/step16.py:12` `class Step16Unit`、`:30-41` 寄存器常量、`:67` 读编码器、
  `:141` 写 LED 模式、`:184` 亮度、`:223/260/297` RGB、`:346/365` 保存/地址、`:403` FW。
- QEMU 数据面建议：`CONTROL_STEP16` I2C 从机，寄存器文件 + 旋钮 position fixture（0–15）；
  `0xF0` 写触发 Flash 持久化标志（无需真实 NVS，只需读回一致）。
- Fixture/注入：QOM `position`（0–15）、`led-config`、`led-brightness`、`direction`、
  `rgb`(24bit)、`rgb-brightness`、`rgb-power`、`i2c-address`、`firmware-version`。
- 可断言量：`get_encoder_value` 读 fixture、`set/get_led_mode`、亮度、方向、RGB 写回读、
  `get_firmware_version`、地址写后重扫描。
- Unresolved：BCD 旋钮机械/弹跳、7 段显示光学、睡眠定时语义（N 秒）没有时间轴测试；
  协议 PDF 的表格列有错位（`0xF0/0xFE/0xFF` 同列），以驱动常量为准。

### 4.4 `timerpwr`（U189，I2C `0x56`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit-TimerPWR（U189，STM32G031 + RTC +
  INA3221 + LGS4056H + 升压，0.66" OLED，双按键）；协议 PDF
  https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit-TimerPWR/U189_UnitTimerPwr_I2C_Protocol_V1_20241018.pdf
  （V1，2024-03-11）。
- 寄存器表（PDF + `unit/timerpwr.py:28-56`）：
  - `0x00` W/R：Grove 5V 输出使能（bit? 见驱动：`_GROVE_OUTPUT_REG=0x00`，写 1/0）；
    `0x01` W/R：OLED 背光（驱动 `_OLED_BACKLIGHT_REG=0x01`）；
  - `0x10` R：按键 A/B 状态（`_BUTTON_STATUS_REG+btn`，driver 读 0/1）；
  - `0x20` W/R：Wake trigger（bit0 timer，bit1 button）；`0x21` W/R：Sleep trigger（同 bit 定义）；
  - `0x30` W/R：定时开机 H/M/S（3 字节，驱动 `struct.pack(">BBB")`）；
  - `0x40` W：Sleep command（写 1 睡眠）；`0x41` W/R：Cycle 1=start / 0=stop（驱动 `_CYCLE_REG=0x41`）；
  - `0x60` R：USB V（4B LE，raw/100 V）+ USB I（4B LE，raw/100 mA）+ Grove V + Grove I（偏移
    `0x60/0x64/0x68/0x6C`，驱动 `:42-47`、`:150-211`）；
  - `0x70` R：电池 V（4B LE，raw×10 = mV）+ 电池 I（偏移 `0x70/0x74`）；
  - `0x80` W/R：定时关机 H/M/S；
  - `0x90` R：充电状态（0 未充电，1 充电中）；
  - `0xF0` W：写 1 保存参数到 Flash；`0xFE` R 固件版本；`0xFF` R/W I2C 地址。
- 驱动：`unit/timerpwr.py:12` class、`:28-56` 寄存器常量、`:150-211` V/I 解码、
  `:313/372/401/430` sleep/定时 API、`:487/504` cycle、`:506/525` trigger。
- QEMU 数据面建议：`CONTROL_TIMERPWR` I2C 从机；V/I 四通道用 fixture（`usb-v/i`、
  `grove-v/i`、`battery-v/i`）按 LE32 编码；RTC/定时开关只做状态机（power-state），不模拟
  真实电池/升压/充电曲线。
- Fixture/注入：`power-state`、`grove-output`、`oled-backlight`、`battery-mv`、`usb-v/i`、
  `grove-v/i`、`charging`、`schedule-on/off`、`trigger-bits`、`cycle`。
- 可断言量：guest `get_battery_voltage`/`get_usb_voltage` 等与 fixture 一致；写定时时间回读；
  `sleep_once/sleep_cycle` 触发 QOM 状态迁移；充电状态位。
- Unresolved：真实 RTC 长时间定时、电池充放电、DC-DC 升压负载、OLED/按键、热/安全 NOT RUN；
  PDF 表格列错位（`0xF0/0xFE/0xFF` 同列），以驱动常量为准。

### 4.5 `mq`（U199，I2C `0x11`，可配 0x08–0x77）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_MQ（U199，STM32G030 + MQ-5）；
  协议 PDF https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1168/MQ_I2C_Protocol_EN.pdf
  （V1，2025-05-08）；同文 xlsx
  https://github.com/m5stack/M5Unit-MQ-Internal-FW/blob/31744153440f/protocol/M5Unit-MQ-I2C-Protocl-ZH_V1.0.xlsx 。
- 寄存器表（PDF + `unit/mq.py:33-44`）：
  - `0x00` W/R：MQ 工作状态 0=关闭、1=持续加热、2=引脚电平切换；
  - `0x01` W/R：LED 状态 0/1（驱动 `MQ_LED_CFG_REG=0x01`）；
  - `0x10` W/R：高电平时间（30–255 s，默认 30）；`0x11` W/R：低电平时间（5–255 s，默认 5）；
  - `0x20` R：MQ ADC 8 位；`0x30` R：MQ ADC 12 位（2B LE，0–4095）；
  - `0x40` R：Valid Tags（**PDF：0=有效、1=无效**）；
  - `0x50` R：内部 NTC ADC 8 位；`0x60` R：NTC ADC 12 位（2B LE）；
  - `0x70` R：NTC 电阻（2B LE，单位 Ω）；
  - `0x80`–`0x85` R：内部参考电压（2B LE，mV）、MQ 电压（2B LE，mV）、NTC 电压（2B LE，mV）；
  - `0xFE` R：固件版本；`0xFF` R/W：I2C 地址 0x08–0x77（写后 20 ms 延时）。
- 驱动：`unit/mq.py:12` class、`:33-44` 常量、`:76/94` 工作状态、`:140/155` 加热时间、
  `:177/196` ADC/valid、`:245` 电压通道、`:302` 改地址。
- QEMU 数据面建议：`CONTROL_MQ` I2C 从机；`sensor-mv`/`ref-mv`/`ntc-mv` fixture 映射到
  ADC raw；加热模式/时间只做状态机。
- Fixture/注入：QOM `mq-mode`、`led`、`heat-high`、`heat-low`、`sensor-mv`、`ref-mv`、
  `ntc-ohm`、`adc12`、`valid-tags`、`firmware-version`、`i2c-address`。
- 可断言量：ADC8/ADC12、参考电压、NTC 电阻/电压与 fixture 换算一致；模式/加热时间写回读；
  FW 版本/地址。
- Unresolved：MQ-5 气体浓度曲线、预热 20 s 物理、加热温度/热学 NOT RUN；
  **Valid Tags 极性冲突**：PDF 说 0=有效，而上游驱动 `get_valid_tags` 返回 `read == 1`，
  需以固件版本/真机确认（QEMU 先按 PDF 语义并提供 fixture 覆盖两种）。

### 4.6 `8servos2-i2c`（U222，I2C `0x25`–`0x34`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_8Servos2-I2C（U222，STM32G031G8U6 +
  INA199，16 档旋钮选地址）；官方协议页
  https://docs.m5stack.com/en/protocol/U222/I2C（"Firmware V2.0"）；协议 PDF
  https://github.com/m5stack/M5Unit-8Servos2-I2C-Internal-FW/blob/44bdc24af921/protocol/V2/M5Unit-8Servos2-I2C-Protocol-EN_V2.0.pdf
  （页面写 STM32F030F4P6，与产品页/内部固件 README 的 STM32G031G8 冲突，见 unresolved）。
- 寄存器表（PDF V2.0 + `unit/servos8_v2.py:15-30`；页内地址写 `0x25` 基址 + 旋钮位置 0–15）：
  - `0x00` W/R：每通道模式（0 INPUT、1 OUTPUT、2 ADC、3 SERVOS、4 RGB、5 PWM）；
  - `0x10` W/R：上下拉（0 无、1 上拉、2 下拉）；
  - `0x20` R：输入电平（1 高/0 低）；
  - `0x30` W/R：输出电平；
  - `0x40` R：ADC 12 位，每通道 2 字节（0–4095）；
  - `0x50` W/R：舵机角度 0–180（每通道 1 字节）；
  - `0x60` W/R：RGB 配置（bit5=刷新、bit4:0=灯数）；
  - `0x70` W/R：PWM 占空比 0–100；
  - `0x80`–`0xBF` W/R：RGB 缓冲 16×4 字节（B/G/R + 保留，`reg = 0x80 + i*4`）；
  - `0xD0` W/R：TIM2/TIM3 频率（2B LE each，1–65535；舵机需 50 Hz）；
  - `0xE0`–`0xEB` R：12 字节 UID；
  - `0xF0` W/R：系统遥测（4×u16 LE：参考电压、Grove 电压、DC 电压 mV、系统电流 mA）
    + I2C offset/刷新 + 固件版本/地址等复合寄存器；
  - `0xFE` R：固件版本；`0xFF` R/W：当前 I2C 地址。
- 驱动：`unit/servos8_v2.py:15-30` 常量、`:57-65` 模式、`:102-131` 模式读写、`:265-285`
  ADC/舵机、`:324-405` RGB、`:494-540` 定时器、`:543-654` 遥测/UID/FW/地址。
- QEMU 数据面建议：`CONTROL_SERVOS8V2` I2C 从机，寄存器文件 + 8 通道 fixture；
  地址按旋钮位置参数化（attachment `rotary=0..15`）。
- Fixture/注入：QOM `channel-modes[8]`、`gpio-inputs[8]`、`adc[8]`、`servo-angles[8]`、
  `rgb-buffer[16]`、`pwm[8]`、`timer-freq[2]`、`uid[12]`、`sys`(ref/grove/dc/current)、
  `rotation-address`、`firmware-version`。
- 可断言量：模式写回读、输入/输出电平、ADC、舵机角度、PWM、RGB 缓冲、定时器频率、
  遥测 u16、UID、FW/地址。
- Unresolved：舵机/WS2812/PWM 电气与波形、INA199 电流精度、9–24V 供电、I2C 级联、
  MCU 型号冲突（STM32F030F4P6 vs STM32G031G8）NOT RUN；`0xF0` 复合寄存器子字段偏移以
  内部固件代码为准（协议页文字与该 PDF 排列不完全一致）。

### 4.7 `8servos2-chain`（U223，UART Chain 115200 8N1）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_8Servos2-Chain（U223，STM32G031 +
  INA199，8 通道 servo/digital/ADC/RGB/PWM，双 Grove Chain IN/OUT，DC9-24V）；官方协议页
  https://docs.m5stack.com/en/protocol/U223/UART（"UART Control Protocol V1"）；内部固件
  https://github.com/m5stack/M5Chain-Series-Internal-FW/tree/main/Unit-8Servos-Chain 。
- 帧格式（U223 协议页）：`AA 55 <len_lo> <len_hi> <index> <cmd> <data...> <crc> 55 AA`；
  `len` = 从 Index 到 CRC 的字节数（含 Index/CRC，不含头/尾/len 自身），低字节在前；
  CRC = `(index + cmd + data...) & 0xFF`；应答帧同构，`cmd` 回显；`Operation_status`
  0 失败/1 成功。
- 命令表（U223 页完整 0x10–0xFE，摘关键）：
  `0x10/0x11` 设模式（单/多）、`0x12/0x13` 读模式、`0x30/0x31/0x32/0x33` 上下拉、
  `0x34/0x35` 输入电平、`0x40/0x41/0x42/0x43` 输出电平、`0x50/0x51` ADC（8×u16 LE）、
  `0x60/0x61/0x62/0x63` 舵机角度（0–180）、`0x70–0x77` RGB 配置/缓冲（16 色）、
  `0x80–0x83` PWM 占空比（0–100）、`0x90–0x93` TIM2/TIM3 频率（1–65535，默认 50Hz）、
  `0xA0/0xA1/0xA2/0xA3` 参考/Grove/DC 电压与系统电流（u16 LE，mV/mA）、
  `0xF8` UID（4B/12B）、`0xF9` bootloader、`0xFA` firmware、`0xFB` 设备类型（=**0x000C**）、
  `0xFC` 枚举请求、`0xFD` 心跳、`0xFE` 枚举数量。
- 驱动：`chain/servos8_v2.py:31-58` 命令常量与 `DEVICE_TYPE=0x000C`；`chain/chain.py:13-44`
  链路层；上游 `chain/__init__.py:16` `Servos8V2Chain`。
- QEMU 数据面建议：复用 0145/0151 UART fixture responder，升级为 **Chain 帧解析/构造**
  （CRC、Index、命令表），而不是只做字节层；8 通道数据用 QOM fixture。
- Fixture/注入：`channel-modes`、`gpio-inputs`、`adc[8]`、`servo-angles[8]`、`rgb-buffer[16]`、
  `pwm[8]`、`timer-freq`、`ref/grove/dc/current`、`device-type=0x000C`、`index`。
- 可断言量：guest 发出的 AA55 帧字节（cmd/index/CRC）逐字节匹配；读命令返回 fixture；
  设备类型/UID/FW 应答。
- Unresolved：舵机/PWM/WS2812 波形、Chain 多设备枚举/拓扑、9–24V/INA199 NOT RUN。

### 4.8 `chainbus`（U212，UART Chain 115200 8N1，设备类型 `0x0006`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_ChainBus（U212，STM32G031，2×Chain
  UART IN/OUT + 顶部 I2C/GPIO/ADC/NVIC 扩展口 + WS2812）；协议 PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1201/M5Stack-Unit-ChainBus-Protocol-EN.pdf
  （V1，2025-11-13）；内部固件
  https://github.com/m5stack/M5Chain-Series-Internal-FW/tree/main/Unit-ChainBus 。
- 帧格式：与 U223 相同的 Chain 帧（`AA 55 len index cmd data crc 55 AA`；CRC 从 Index 到
  CRC 前所有字节求和低 8 位；最大 256 字节）；设备类型 = **0x0006**。
- 命令表（PDF 完整，摘关键）：
  `0x10` I2C 初始化（speed 0=100kHz/1=400kHz）、`0x11` I2C 读、`0x12` I2C 写、
  `0x13` 指定寄存器读、`0x14` 指定寄存器写、`0x15` 扫描 I2C 地址；
  `0x20/0x21` 设/读 RGB（1 灯）、`0x22/0x23` RGB 亮度；
  `0x30/0x31/0x32` GPIO 输出模式/电平/回读，`0x40/0x41` GPIO 输入模式/电平，
  `0x50` 外部中断模式、`0xE0` 中断主动上报；`0x60/0x61` ADC 配置/读取（0–4095，3.3V 参考）；
  `0x70` 工作状态查询（0 无、1 输出、2 输入、3 NVIC、4 ADC、5 I2C）；
  `0xF8` UID、`0xF9/0xFA/0xFB` 版本/设备类型、`0xFC` 枚举、`0xFD` 心跳、`0xFE` 设备数量。
  GPIO 编号为 **1/2**（不是 0–3）。
- 驱动：`chain/unit_bus.py:10` `class BusChainUnit`、`:32-54` 命令常量、`:118-623` 各命令；
  `chain/chain.py:13-44` 链路层/设备类型；上游 `chain/__init__.py:8,19`。
- QEMU 数据面建议：作为 **Chain 总线转换器节点** 建模：UART 侧响应 Chain 命令；扩展口
  行为在 QOM 内做成 loopback/fixture（I2C 转发可直连到宿主 I2C 从机表、GPIO/ADC 用 fixture），
  避免伪造真实外设。
- Fixture/注入：`chain-uid`、`version`、`link-devices`（枚举）、`heartbeat`、`gpio-levels`、
  `adc[2]`、`i2c-scan-result`、`work-status`、`rgb`。
- 可断言量：I2C init/read/write/scan 命令帧与返回；GPIO/ADC 读写；工作状态；枚举/心跳；
  设备类型 0x0006。
- Unresolved：作为"协议转换器"的实时转发时延、真实 I2C 下游设备、GPIO 电气、NVIC 中断时序
  NOT RUN；多级 Chain 拓扑未建模。

### 4.9 `rollercan`（U188）/ `rollercan-lite`（U188-Lite）I2C `0x64` + CAN

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit-RollerCAN ；
  https://docs.m5stack.com/en/unit/Unit-RollerCAN%20Lite ；官方协议 PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/779/Unit-RollerCAN-I2C-Protocol-EN.pdf ；
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/779/Unit-RollerCAN-CAN-Protocol-EN.pdf ；
  最新权威 Markdown（内部固件仓库，V3.1，2026-08-24）：
  https://github.com/m5stack/M5Unit-RollerCAN-Internal-FW/blob/20039c84b122/protocol/M5Stack-Unit-RollerCAN-I2C-Protocol.md ；
  https://github.com/m5stack/M5Unit-RollerCAN-Internal-FW/blob/20039c84b122/protocol/M5Stack-Unit-RollerCAN-CAN-Protocol.md 。
- I2C 寄存器总览（V3.1；地址 `0x00`–`0xFF`，8-bit 寄存器地址，多字节小端；产品设备 ID `0x02`）：
  `0x00` 电机输出、`0x01` 控制模式（1 速度/2 位置/3 电流/4 编码器）、`0x0A` 位置超范围保护、
  `0x0B` 解除堵转、`0x0C` 系统状态（0 待机/1 运行/2 错误）、`0x0D` 错误位（bit0 过压、
  bit1 堵转、bit2 超范围）、`0x0E` 按键切换模式、`0x0F` 堵转保护、`0x10` CAN ID、
  `0x11` CAN 波特率档位（0=1M/1=500k/2=125k）、`0x12` RGB 亮度、`0x20-0x23` 位置环最大电流
  （X100 mA）、`0x30-0x33` RGB(B/G/R+mode)、`0x34-0x37` 输入电压（X100 V）、
  `0x38-0x3B` MCU 温度、`0x3C-0x3F` 编码器计数、`0x40-0x43` 速度目标（X100 rpm）、
  `0x50-0x53` 速度环最大电流、`0x60-0x63` 实际速度、`0x70-0x7B` 速度 PID、
  `0x80-0x83` 旧格式目标位置（0.01°）、`0x88-0x8D` 扩展目标位置（圈数+圈内角度，0.01°）、
  `0x90-0x9D` 实际位置、`0xA0-0xAB` 位置 PID、`0xB0-0xB3` 电流目标、`0xC0-0xC3` 实际电流、
  `0xE0-0xEB` STM32 UID、`0xF0` 保存参数（写 1）、`0xF1-0xF3` 编码器校准、
  `0xF4` 产品设备 ID（=0x02）、`0xFE` 固件版本（=3）、`0xFF` I2C 地址（0x08–0x77）。
- CAN 协议（V3.1，CAN 2.0 Classic，29-bit 扩展帧，8 字节固定数据，默认 1 Mbps，无应用层 CRC）：
  ID 位段 = `bit28-24 cmd_id | bit23-16 cmd_para | bit15-8 option | bit7-0 node`；
  发现 `0x00`、状态 `0x02`（Data: speed int16 rpm、position int16 deg、current int16 mA、
  voltage int16 V）、使能 `0x03`、停止 `0x04`、设 ID `0x07`、解除堵转 `0x09`、保存 `0x0A`、
  设波特率 `0x0B`、堵转/位置保护开关 `0x0C-0x0F`；
  单参数读写 `0x11`（读）/`0x12`（写）/`0x13`（按 I2C 地址读）/`0x14`（按 I2C 地址写），
  参数索引 `0x7002` 保存 Flash、`0x7003` 解除保护、`0x7004` 电机开关、`0x7005` 模式、
  `0x7006` 电流目标、`0x700A` 速度目标、`0x7016` 位置目标、`0x7017/0x7018` 电流上限、
  `0x7020-0x7025` PID、`0x7030-0x7035` 回读、`0x7050-0x7052` RGB、`0x7060-0x7072` 识别/校准；
  原始 I2C 转发 `0x15`/`0x16`；扩展位置 `0x17`/`0x18`。
- 驱动：`unit/rollercan.py:17` `_ROLLERCAN_I2C_ADDR=0x64`、`:18` `_ROLLERCAN_CAN_ADDR=0xA8`、
  `:20-63` 寄存器/CAN 命令映射、`:520` `RollerI2C`、`:554` `RollerCAN`、`:719` `RollerCANToI2CBus`；
  上游别名 `unit/__init__.py:121` `"RollerCANUnit": "rollercan"`。
  lite 官方页直接链接同一组协议 PDF（无滑环/顶部结构差异），协议层按同族处理。
- QEMU 数据面建议：I2C 侧先做 `CONTROL_ROLLERCAN` 寄存器文件（含产品 ID/FW/错误位/编码器/
  位置/速度 fixture）；CAN 侧若做，复用 0145 `CanBusClient` 的观测/注入（不要伪造 FOC），
  CAN ID 解析按上述位段。
- Fixture/注入：QOM `motor-output`、`mode`、`speed-rpm`、`position-deg`（圈数+0.01°）、
  `current-ma`、`vin-v`、`mcu-temp-c`、`encoder-count`、`error-bits`、`system-state`、
  `rgb`、`can-id`、`can-bps`、`device-id=0x02`、`firmware-version=3`、`i2c-address`。
- 可断言量：guest 读状态/速度/位置/电流/电压与 fixture 一致；模式/目标/PID 写回读；
  错误位/解除堵转状态迁移；设备 ID/FW/地址；CAN 帧 ID+8B 数据字节。
- Unresolved：FOC 电机/编码器物理、温升/电流环、6–16V 供电、OLED/RGB/滑环/按键 NOT RUN；
  lite 与标准版电流/机械差异未逐项核对；CAN 电气/位定时/过滤 NOT RUN。

### 4.10 `roller485`（U182）/ `roller485-lite`（U182-Lite）I2C `0x64` + RS485

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_Roller485 ；
  https://docs.m5stack.com/en/unit/Unit-Roller485%20Lite ；官方协议 PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/776/Unit-Roller485-I2C-Protocol-EN.pdf ；
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/776/Unit-Roller485-RS485-Protocol-EN.pdf ；
  最新权威 Markdown（V2.2/V2.3，2026-09-02）：
  https://github.com/m5stack/M5Unit-Roller485-Internal-FW/blob/7216b24a264e/protocol/M5Stack-Unit-Roller485-I2C-Protocol.md ；
  https://github.com/m5stack/M5Unit-Roller485-Internal-FW/blob/7216b24a264e/protocol/M5Stack-Unit-Roller485-RS485-Protocol.md 。
- I2C 寄存器总览（V2.2；默认 `0x64`，范围 0x08–0x77，小端，产品设备 ID `0x01`）：
  与 RollerCAN 家族近似的 `0x00-0x0F`（输出/模式/保护/状态/错误/按键/堵转）、
  `0x10-0x12`（RS485 ID / 波特率档位 0=115200、1=19200、2=9600 / RGB 亮度）、
  `0x20-0x23` 位置环最大电流、`0x30-0x33` RGB(B/G/R+mode)、`0x34-0x37` VIN、
  `0x38-0x3B` MCU 温度、`0x3C-0x3F` 编码器计数、`0x40-0x43` 速度目标、`0x50-0x53` 速度环
  最大电流、`0x60-0x63` 实际速度、`0x70-0x7B` 速度 PID、`0x80-0x83` 旧格式位置、
  `0x88-0x8D` 扩展位置、`0x90-0x9D` 实际位置、`0xA0-0xAB` 位置 PID、`0xB0-0xB3` 电流目标、
  `0xC0-0xC3` 实际电流、`0xE0-0xEB` UID、`0xF0` 保存、`0xF1-0xF3` 编码器校准、
  `0xF4` 产品 ID（=0x01）、`0xFE` FW（=3）、`0xFF` 地址。
- RS485 协议（V2.3）：半双工 115200/19200/9600 8N1，默认电机 ID `0x00`；
  普通控制请求 15 字节 `Cmd MotorID Data0..11 CRC8`（无帧头），响应 17 字节
  `AA 55 RespCmd MotorID Data0..11 CRC8`；短查询请求 `Cmd MotorID Option CRC8`（4B），
  普通回读响应 20 字节；I2C 转发 `0x60/0x61/0x62/0x63`（响应 `0x70/0x71/0x72/0x73`）；
  CRC8 = CRC-8/MAXIM（初值 0，多项式 0x8C，反射），从 Cmd 起覆盖 MotorID+数据。
- 驱动：`unit/roller485.py:17` `_ROLLER485_I2C_ADDR=0x64`、`:18` `_ROLLER485_RS485_ADDR=0x00`、
  `:21-24` I2C 转发命令、`:26-62` 寄存器/RS485 映射表、`:508` `class Roller485`、
  `:535` `create_frame`、`:649` `_crc8`、`:806` `Roller485Unit`；上游别名
  `unit/__init__.py:120` `"Roller485Unit": "roller485"`。
- QEMU 数据面建议：同 `rollercan`，I2C 寄存器文件 + fixture；RS485 侧用 UART fixture
  responder 按 15/17 字节帧 + CRC8 实现（可断言帧字节）。
- Fixture/注入：同 `rollercan` 的 QOM 属性，加 `rs485-id`、`rs485-bps`。
- 可断言量：I2C 寄存器读写、RS485 请求帧字节/CRC、响应帧结构、状态/速度/位置/电流/电压、
  设备 ID/FW/地址。
- Unresolved：电机/FOC/编码器物理、6–16V/过压/堵转/温升、滑环/OLED/RGB、RS485 电气/终端
  电阻 NOT RUN；lite 与标准版硬件差异未逐项核对。

### 4.11 `bmm350`（U231，I2C `0x14`）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_BMM350（U231，BMM350 三轴 TMR 磁力计，
  ±2000 µT，0.1 µT 分辨率，100/400 kHz）；Bosch datasheet
  https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmm350-ds001.pdf
  （BST-BMM350-DS001-27；产品页镜像
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1289/bst-bmm350-ds001.pdf）。
- 寄存器表（datasheet Table 8，p.26–28；驱动 `driver/bmm350.py:12-23` 一致）：
  `0x00` CHIP_ID（=0x33）、`0x04` PMU_AGGR（ODR/平均）、`0x05` PMU_AXIS、`0x06` PMU_CMD、
  `0x31`–`0x3C` 数据区（X/Y/Z 各 3 字节小端 24-bit + TEMP 3 字节：MAG_X_XLSB 0x31、
  MAG_X_LSB 0x32、MAG_X_MSB 0x33、Y 0x34–0x36、Z 0x37–0x39、TEMP 0x3A–0x3C）、
  `0x50` OTP_CMD、`0x52` OTP_DATA_MSB、`0x53` OTP_DATA_LSB、`0x55` OTP_STATUS、
  `0x7E` CMD（soft reset 写 0xB6）。
- **关键 I2C 行为**：datasheet §9.2.3（p.46）+ `Figure 7`：读寄存器时先送 **2 个 dummy 字节**，
  n 字节读取实际读 n+2 字节并丢弃前 2 字节；上游驱动 `driver/bmm350.py:62-67` 正是
  `readfrom_mem(addr, reg, size+2)[2:]`（QEMU 从机必须复现该偏移，否则驱动读错位）。
- 驱动：`driver/bmm350.py:12` 地址、`:14-23` 寄存器、`:38-57` 初始化序列（0x7E=0xB6 复位、
  读 CHIP_ID==0x33、OTP 读取、PMU 配置）、`:117-119` MAG 12 字节读；`unit/bmm350.py:14`
  `class BMM350Unit`、`:31-40` 初始化参数、`:113-152` get_mag/get_temperature/get_heading；
  上游别名 `unit/__init__.py:18` `"BMM350Unit": "bmm350"`。
- QEMU 数据面建议：`CONTROL_BMM350` I2C 从机（0x14），**读事务返回 2 个 dummy 字节再给数据**；
  实现 WHO_AM_I=0x33、PMU 命令接受、MAG/TEMP 数据寄存器由 fixture 驱动、OTP 读返回固定校准字。
- Fixture/注入：QOM `mag-x/y/z-ut`（或 raw 24-bit）、`temperature-c`、`odr-hz`、`chip-id`、
  `otp-words`、`axis-mapping`、`calibration-offsets/scales`。
- 可断言量：guest `get_mag_raw`/`get_mag`/`get_temperature` 与 fixture 一致（含 24-bit 符号扩展
  与 datasheet 灵敏度系数）；CHIP_ID 校验路径；OTP 读取序列；ODR/axis 写回读。
- Unresolved：磁场/航向物理、OTP 校准曲线精度、温度补偿、±2000 µT 量程/噪声 NOT RUN；
  驱动内 `0.007069979`/`0.007174964` 等灵敏度常数与 datasheet 表值的逐项核对留待实现时复核。

### 4.12 `ina226-10a`（U200，I2C `0x41`，5 mΩ）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_INA226-10A（U200，隔离，0–30V，±10A，
  5 mΩ shunt，自恢复保险）；TI datasheet
  https://www.ti.com/lit/ds/symlink/ina226.pdf（SBOS547C，JUNE 2011–REVISED AUGUST 2026），
  产品页镜像 https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1171/INA226.pdf。
- 寄存器表（datasheet **Table 7-1**，p.22；全部 16-bit big-endian）：
  `00h` Configuration（R/W，POR 0x4127；bit15 RST、bit11:9 AVG、bit8:6 VBUSCT、bit5:3 VSHCT、
  bit2:0 MODE=111 continuous shunt+bus）、`01h` Shunt Voltage（R，LSB 2.5 µV，±81.92 mV 满量程）、
  `02h` Bus Voltage（R，LSB 1.25 mV，0–40.96V）、`03h` Power（R）、`04h` Current（R）、
  `05h` Calibration（R/W）、`06h` Mask/Enable（R/W）、`07h` Alert Limit（R/W）、
  `FEh` Manufacturer ID（=0x5449）、`FFh` Die ID（=0x2260/0x2261）。
  `Table 7-2/7-3/7-4` 给出 AVG/VBUSCT/VSHUNTCT/MODE 位字段。
- 驱动：`unit/ina226.py:8` `class INA226Unit(INA226)`、`:30-43` `type="10A"` → `shunt=0.005`、
  `cal=0x0C80`，配置 AVG=16、VBUSCT/VSHUNTCT=8244 µs、MODE=continuous；`driver/ina226.py:33-42`
  寄存器、`:117-140` calibrate（`current_lsb=0.00512/(cal*R)`、`power_lsb=25*current_lsb`）、
  `:142-231` 读函数（shunt 2.5 µV/LSB、bus 1.25 mV/LSB、current/power 用校准 LSB）；
  上游别名 `unit/__init__.py:123` `"INA226Unit": "ina226"`。
- QEMU 数据面建议：`CONTROL_INA226` I2C 从机（0x41），实现 8 个标准寄存器 + ID；
  `bus-voltage`/`current`/`shunt` fixture 按校准公式反算 raw；配置寄存器保存/回读。
- Fixture/注入：QOM `bus-voltage-v`、`current-a`、`shunt-voltage-mv`、`calibration`、
  `configuration`、`mask-enable`、`alert-limit`、`manufacturer-id=0x5449`、`die-id=0x2260`。
- 可断言量：guest 按驱动公式读 bus/current/power 与 fixture 一致（`current_lsb` 由 cal 决定）；
  config/cal 写回读；ID 寄存器；alert/mask 写回读。
- Unresolved：隔离/±10A/5 mΩ/精度/温漂/自恢复保险 NOT RUN；与 `ina226-1a` 同地址需二选一。

### 4.13 `ina226-1a`（U200-1A，I2C `0x41`，80 mΩ）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_INA226-1A（U200-1A，隔离，0–30V，±1A，
  80 mΩ shunt）；同一 TI datasheet `SBOS547C Table 7-1`。
- 寄存器表：与 `ina226-10a` 完全相同（标准 INA226 8 寄存器 + 0xFE/0xFF ID）。
- 驱动：`unit/ina226.py:31-34` `type="1A"` → `shunt=0.08`、`cal=0x0800`（注意同文件注释
  `# 10A: 0x0C80, 1A:0x811` 与代码 `0x0800` 不一致，代码为准）；其余同 4.12。
- QEMU 数据面建议：**同一个 INA226 模型按 attachment 参数化**（`shunt-ohm`、`cal`、`max-current`），
  不复制两份寄存器逻辑；与 10A 版本不能同时挂同一 0x41 总线。
- Fixture/注入：同 4.12，把量程 fixture 改成 ±1A/80 mΩ 校准。
- 可断言量：同 4.12；另可断言 1A 量程下 raw→A 的换算（cal=0x0800 → current_lsb=3.125e-5 A）。
- Unresolved：同 4.12；1A/80 mΩ 量程与校准值需在实现时以 TI 公式+驱动常量复核（驱动注释冲突）。

## 5. b 类逐款（2 款，列出可建子集与缺口）

### 5.1 `cardkb2`（U215，I2C `0x5F` / UART 115200 8N1）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_CardKB2（U215，ESP32-C61HF4，42 键，
  四模式 I2C/UART/ESP-NOW/BLE HID，Grove PORT.CUSTOM G26/G25）；官方 User Manual PDF
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1225/Unit_CardKB2_User_Manual_EN.pdf
  （抓取 2026-11-03）；出厂固件源码
  https://github.com/m5stack/M5Unit-CardKB2-UserDemo/blob/282e4bc28363/src/main/bsp/bsp_i2c.c 。
- **可建子集 a'（legacy 协议，官方手册直述）**：
  - I2C `0x5F`：直接读 1 字节 = 按键 ASCII 值（无键返回 0x00）；先写 `0xF1` 再读 = 固件版本
    （`bsp_i2c.c:52-53,135-140`）；`0xF0` 写 1 = 产测模式触发（生产用，不建模）。
  - UART 115200 8N1：帧 `AA <DATA_LEN=0x03> <KEY_ID> <KEY_STATE> <checksum>`；
    KEY_ID = row×11+col（0–43），KEY_STATE 0x01 按下/0x02 释放，
    checksum=(DATA_LEN+KEY_ID+KEY_STATE)&0xFF（User Manual §IV，示例 `AA 03 00 01 04`）。
  - 键码映射：Normal/CapsLock/Symbol 三张表（User Manual Table 3–5，ASCII 值）。
  - 驱动：`unit/cardkb.py:436` `class CardKBI2C`、`:461-466` 寄存器、`:479-512` legacy 读路径；
    `:538` `class CardKBUART`、`:200-206` UART/V2 帧常量。
- **驱动实现的 v2 report（官方手册未写，留 unresolved）**：I2C `0x00` status、`0x01` sequence、
  `0x02` report_len（=0x08）、`0x03` report（8 字节：modifier + reserved + 6 keycode）；
  UART `AA 08 <8B report> checksum`。来源为上游驱动 `unit/cardkb.py:200-290,461-512`，
  **没有官方手册/firmware 版本对应**，不写进 a-class 基线。
- 可建数据面：I2C 从机（0x5F，raw key/0xF1 version）+ UART 帧 responder（AA03 帧/校验）。
- Fixture/注入：QOM `key-queue`（ASCII/KEY_ID 序列）、`key-state`、`firmware-version`、
  `mode`（i2c/uart/espnow/blehid 只读枚举，QEMU 只支持 i2c/uart）。
- 可断言量：guest 读键字节/版本；UART 发送/接收帧字节与校验；键码表映射。
- **缺口（为什么 b）**：① v2 report 寄存器/固件版本无法与官方手册对齐；② BLE HID 依赖
  BLE 协议栈与配对，ESP-NOW 依赖 WiFi 2.4G 广播（channel 0，MAC ffffffffffff），
  QEMU Unit 数据面都不是可注入的 I2C/UART；③ CardKB2 的 Grove 是 PORT.CUSTOM G26/G25，
  未在 host-ports 准入，需 cores3 PORT.A harness 替代并记录。
- Unresolved：v2 report 对应的固件版本、按键保持重复（300 ms 后 50 ms 间隔）、
  ESP-NOW/BLE HID **NOT RUN**、PORT.CUSTOM 端口准入。

### 5.2 `cat1-cn`（U204，UART AT 115200 8N1）

- 证据：产品页 https://docs.m5stack.com/en/unit/Unit_Cat1-CN（U204，ML307R-DL LTE Cat.1，
  B1/B3/B5/B8/B34/B38/B39/B40/B41，TCP/UDP/HTTP/SSL/MQTT，最多 6 socket，Nano-SIM）；
  官方 AT 手册
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/AT_Commands_Reference_Guide_4G_Series_V1.8.1.pdf
  （191 页，105 条 AT 命令，2024-02-02）；通信流程示例
  https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/ML307R_Communication_Process_Example_V1.0.1.pdf 。
- **可建子集 a'（AT 字节层命令-响应/URC）**：
  - 基础：`AT`、`ATE0`、`AT+CPIN?`（SIM 就绪）、`AT+CREG?/AT+CEREG?`（注册）、`AT+CSQ`、
    `AT+CGATT?`、`AT+CGDCONT`、`AT+CGSN`/`AT+CIMI`（IMEI/IMSI）、`AT+CGMM`/`AT+CGMI`；
  - PDP/拨号：`AT+MIPCALL=1,1`、`AT+MIPCALL?`、`AT+CGPADDR`、`AT+CGCONTRDP`；
  - Socket：`AT+MIPOPEN=<fd>,<type>,<ip>,<port>`、`AT+MIPSEND=<fd>,<len>` 后跟数据、
    `AT+MIPRD=<fd>,<len>`、`AT+MIPCLOSE=<fd>`、`AT+MDNSGIP`（DNS）。
  - URC：`+MIPOPEN: <fd>,<result>`、`+MIPCLOSE:`、`+MIPRD:`、`+RECEIVE`/`+CIPRXGET` 等
    （以 ML307R 手册命令章节为准；具体 URC 名称逐条核对后写入实现任务）。
  - 驱动：`unit/cat1.py:18` `class Cat1Unit(ML307R, Modem)`（115200 8N1，`check_modem_is_ready`/
    `set_command_echo_mode(0)`）；`driver/simcom/ml307r.py:573-604` MIPCALL、`:127-135` MIPOPEN、
    `:194-215` MIPSEND、`:318-362` MIPRD、`:666-676` MDNSGIP、`:705-724` IMEI/CGMM；
    `driver/simcom/common.py:64-134` 基础 AT 表（AT/ATE/CPIN/CREG/CSQ/CGATT/CGDCONT/CGPADDR/COPS）。
- 可建数据面：UART AT fixture responder（识别命令 → 返回固定/脚本化响应 + URC 注入），
  socket 数据传输可接到宿主 loopback/TCP fixture（仅字节层），不模拟蜂窝。
- Fixture/注入：QOM `responses-hex`、`tx-hex`/`frames-sent`、`frames-injected`、
  `sim-state`（ready/absent）、`network-state`（registered/roaming）、`signal-csq`、
  `socket-table`、`urc-script`。
- 可断言量：guest 发出的 AT 命令字节序列、命令→响应与 URC 注入、MIPOPEN/MIPSEND/MIPRD 帧
  字节和 fd 语义。
- **缺口（为什么 b）**：蜂窝 RF/频段/天线、SIM 文件系统与鉴权、运营商网络注册/PDP 真实性、
  TLS/HTTP/MQTT 协议栈语义、实际 TCP/UDP 链路质量与时延都**不可在 QEMU Unit 数据面建模**；
  只能做 AT 控制面 + 字节层 socket 转发，且网络侧必须标注诊断性 fixture。
- Unresolved：ML307R 各 URC 精确格式/超时（需按手册逐条核对）、信号/小区信息真实性、
  双 SIM/射频认证、`AT+MIPRD` 分片语义、加密与证书 NOT RUN。

## 6. 分类汇总与证据强度

| # | Unit | SKU | 分类 | 协议文档 | 上游驱动 | 可建数据面 | 主要 unresolved |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | byteswitch | U191 | a | 协议 PDF | `unit/bytebutton.py` | I2C 0x46 寄存器文件 | 开关机械/IRQ 极性 |
| 2 | bytebutton | U192 | a | 协议 PDF | `unit/bytebutton.py` | I2C 0x47 寄存器文件 | 按键机械/9 灯光学 |
| 3 | step16 | U198 | a | 协议 PDF | `unit/step16.py` | I2C 0x48 寄存器文件 | 旋钮/7 段显示/睡眠定时 |
| 4 | timerpwr | U189 | a | 协议 PDF | `unit/timerpwr.py` | I2C 0x56 寄存器+电源状态机 | 电池/充电/升压/RTC |
| 5 | mq | U199 | a | 协议 PDF+xlsx | `unit/mq.py` | I2C 0x11 寄存器文件 | 气体/加热/Valid 极性 |
| 6 | 8servos2-i2c | U222 | a | 协议页+PDF | `unit/servos8_v2.py` | I2C 0x25–0x34 寄存器文件 | 舵机/PWM 波形/MCU 型号 |
| 7 | 8servos2-chain | U223 | a | 协议页 | `chain/servos8_v2.py` | UART Chain 帧 responder | 舵机/多设备拓扑 |
| 8 | chainbus | U212 | a | 协议 PDF | `chain/unit_bus.py` | UART Chain 帧 + 扩展口 fixture | 实时转发/GPIO 电气/NVIC |
| 9 | rollercan | U188 | a | I2C/CAN 协议 MD | `unit/rollercan.py` | I2C 0x64 寄存器 + CAN 帧 | FOC/电机物理/CAN 电气 |
| 10 | rollercan-lite | U188-Lite | a | 同上 | 同上 | 同上 | lite 硬件差异 |
| 11 | roller485 | U182 | a | I2C/RS485 协议 MD | `unit/roller485.py` | I2C 0x64 + RS485 帧 | FOC/电机物理/RS485 电气 |
| 12 | roller485-lite | U182-Lite | a | 同上 | 同上 | 同上 | lite 硬件差异 |
| 13 | bmm350 | U231 | a | Bosch DS Table 8 | `unit/bmm350.py` | I2C 0x14（2 dummy 字节） | 磁力/OTP 精度 |
| 14 | ina226-10a | U200 | a | TI DS Table 7-1 | `unit/ina226.py` | I2C 0x41 8 寄存器 | 隔离/精度/10A |
| 15 | ina226-1a | U200-1A | a | TI DS Table 7-1 | `unit/ina226.py` | I2C 0x41 8 寄存器（参数化） | 隔离/精度/1A |
| 16 | cardkb2 | U215 | b | User Manual | `unit/cardkb.py` | I2C 0x5F/UART 帧（legacy） | v2 report/BLE/ESP-NOW/PORT.CUSTOM |
| 17 | cat1-cn | U204 | b | ML307R AT 手册 | `unit/cat1.py` | UART AT 字节层 | RF/SIM/PDP/网络/TLS |

## 7. 推荐实现顺序（前 5 款 + 全序）

排序依据：协议完整度 × 数据面简单度 × 可断言度 × 可复用现有框架；**不是**硬件重要性。

**最可能先解锁的前 5 款：**

1. **`byteswitch` + `bytebutton`（U191/U192，一个共享模型解锁 2 款）**：官方 PDF 完整寄存器表、
   上游共享驱动 `unit/bytebutton.py`（`ByteUnit`/`ByteSwitchUnit`/`ByteButtonUnit`），
   I2C 从机仅需 0x00/0x60 状态 + 0x10-0x19 LED + 0x20-0xAF RGB + 系统寄存器；
   可断言二进制位图/RGB 写回读，且两个 SKU 只差地址与极性。**复杂度低。**
   关键寄存器摘录：`0x00` 状态位图、`0x60` 单通道、`0x10+` 亮度、`0x20/0x70/0x90` RGB888
   （B/G/R + 保留，4 字节步长）、`0xF0` 保存、`0xF1` IRQ、`0xFE` FW、`0xFF` 地址。
2. **`step16`（U198）**：官方协议 PDF + `unit/step16.py:30-41` 寄存器常量；单字节寄存器
   0x00/0x10/0x20/0x30/0x40/0x41/0x50-0x52/0xF0/0xFE/0xFF，旋钮 position fixture 简单，
   可断言编码器值/亮度/RGB/地址。**复杂度低。**
3. **`timerpwr`（U189）**：官方协议 PDF + `unit/timerpwr.py:28-56`；寄存器 0x00-0x90 +
   0xF0/0xFE/0xFF，V/I 4 通道 LE32 解码有明确单位（V/mA，raw/100）；电源状态机可断言
   `power-state`/定时读写/充电位。**复杂度中低。**
4. **`mq`（U199）**：官方协议 PDF + xlsx + `unit/mq.py:33-44`；0x00-0xFF 寄存器表完整，
   ADC/电压/加热时间均明确；可断言 ADC8/12、电压通道、模式写回读。**复杂度低**（除 Valid 极性）。
   关键寄存器摘录：`0x00` 状态、`0x01` LED、`0x10/0x11` 高低电平时间（30–255/5–255 s）、
   `0x20` ADC8、`0x30` ADC12(LE)、`0x40` valid、`0x50/0x60` NTC ADC、`0x70` NTC Ω、
   `0x80` ref/MQ/NTC mV、`0xFE` FW、`0xFF` 地址。
5. **`8servos2-i2c`（U222）**：官方协议页 + V2.0 PDF + `unit/servos8_v2.py:15-30`；
   8 通道模式/ADC/舵机/PWM/RGB 寄存器组 + 0xD0 timer + 0xE0 UID + 0xF0 遥测；
   可复用 I2C 寄存器文件框架，地址随旋钮参数化。**复杂度中低。**

**全序（建议批次）：**

| 批次 | 型号 | 理由 |
| --- | --- | --- |
| P1 | byteswitch、bytebutton、step16、mq | 单字节/低复杂度 I2C 寄存器文件，可共享框架 |
| P1' | timerpwr | 加电源状态机，仍为单 I2C 从机 |
| P2 | 8servos2-i2c、bmm350、ina226-10a/ina226-1a | 需要 2 dummy 字节（BMM350）、校准换算（INA226）、8 通道（8Servos2） |
| P3 | chainbus、8servos2-chain | 共用 Chain 帧 responder（AA55/CRC/命令表），需先扩 0145/0151 UART responder |
| P4 | roller485/roller485-lite、rollercan/rollercan-lite | 4 款共享 2 套寄存器/帧协议；I2C 先做，RS485/CAN 需先解决 attachment |
| P5 | cardkb2（b）、cat1-cn（b） | 需固件版本对齐（cardkb2）/网络与 RF 边界（cat1-cn）后再评估 |

**前置依赖（实现前必须补）：**

- I2C 从机多地址/可改地址（0x48/0x56/0x11/0x25–0x34/0x5F/0xFF 写地址）需现有 I2C slave
  框架支持动态地址与多实例；地址冲突（0x64×4、0x41×2）需在 attachment 层 fail-closed。
- BMM350 的 **2 dummy 字节读语义** 必须由 QEMU I2C 从机实现（否则驱动读错位）。
- Chain 帧 responder 需要从"字节层 fixture"升级为"帧级 CRC/命令解析"（0145/0151 扩展）。
- RS485/CAN 没有通用 Unit attachment：`roller485` 需 UART+方向控制，`rollercan` 需 CAN
  控制器/`CanBusClient`；两者先做 I2C 子集更稳妥。
- cardkb2 的 Grove 是 PORT.CUSTOM G26/G25，需 host-port 准入或 cores3 harness 替代记录。

## 8. 引用与抓取记录

**官方产品页（全部 `2026-11-03` 抓取，HTTP 200；SKU/接口/地址引用自页面）：**

| Unit | 产品页 URL |
| --- | --- |
| cardkb2 | https://docs.m5stack.com/en/unit/Unit_CardKB2 |
| 8servos2-i2c | https://docs.m5stack.com/en/unit/Unit_8Servos2-I2C |
| 8servos2-chain | https://docs.m5stack.com/en/unit/Unit_8Servos2-Chain |
| bmm350 | https://docs.m5stack.com/en/unit/Unit_BMM350 |
| ina226-10a | https://docs.m5stack.com/en/unit/Unit_INA226-10A |
| ina226-1a | https://docs.m5stack.com/en/unit/Unit_INA226-1A |
| rollercan / rollercan-lite | https://docs.m5stack.com/en/unit/Unit-RollerCAN / https://docs.m5stack.com/en/unit/Unit-RollerCAN%20Lite |
| roller485 / roller485-lite | https://docs.m5stack.com/en/unit/Unit_Roller485 / https://docs.m5stack.com/en/unit/Unit-Roller485%20Lite |
| byteswitch | https://docs.m5stack.com/en/unit/Unit%20ByteSwitch |
| bytebutton | https://docs.m5stack.com/en/unit/Unit%20ByteButton |
| step16 | https://docs.m5stack.com/en/unit/Unit_Step16 |
| timerpwr | https://docs.m5stack.com/en/unit/Unit-TimerPWR |
| mq | https://docs.m5stack.com/en/unit/Unit_MQ |
| cat1-cn | https://docs.m5stack.com/en/unit/Unit_Cat1-CN |
| chainbus | https://docs.m5stack.com/en/unit/Unit_ChainBus |

**官方协议文档页（docs.m5stack.com，`2026-11-03`）：**

| 文档 | URL | 内容 |
| --- | --- | --- |
| U222 8Servos2-I2C | https://docs.m5stack.com/en/protocol/U222/I2C | 硬件接口/寄存器总览/读写事务/I2C 模式 |
| U223 8Servos2-Chain | https://docs.m5stack.com/en/protocol/U223/UART | 帧格式/CRC/0x10–0xFE 命令表/设备类型 0x000C |

**官方协议 PDF（产品页 "Datasheet" 链接或 Internal-FW 仓库，`2026-11-03` 下载）：**

| 文档 | URL | 版本/日期 |
| --- | --- | --- |
| ByteSwitch I2C | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/820/Byte_Switch_protocol.pdf | V1 2024-06-19 |
| ByteButton I2C | https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteButton/Byte_Button%20Protocol.pdf | V1 2024-06-19 |
| Step16 I2C | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1160/Unit-Step16_Protocol.pdf | V1 2025-07-04 |
| TimerPWR I2C | https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit-TimerPWR/U189_UnitTimerPwr_I2C_Protocol_V1_20241018.pdf | V1 2024-03-11 |
| MQ I2C | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1168/MQ_I2C_Protocol_EN.pdf | V1 2025-05-08 |
| ChainBus | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1201/M5Stack-Unit-ChainBus-Protocol-EN.pdf | V1 2025-11-13 |
| CardKB2 User Manual | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1225/Unit_CardKB2_User_Manual_EN.pdf | — |
| Roller485 I2C/RS485 | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/776/Unit-Roller485-I2C-Protocol-EN.pdf ；https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/776/Unit-Roller485-RS485-Protocol-EN.pdf | — |
| RollerCAN I2C/CAN | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/779/Unit-RollerCAN-I2C-Protocol-EN.pdf ；https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/779/Unit-RollerCAN-CAN-Protocol-EN.pdf | — |
| ML307R AT 手册 | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/AT_Commands_Reference_Guide_4G_Series_V1.8.1.pdf | V1.8.1 2024-02-02 |
| ML307R 通信流程 | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/ML307R_Communication_Process_Example_V1.0.1.pdf | V1.0.1 2024-01-12 |

**厂商 datasheet（`2026-11-03` 下载并解析文本）：**

| 器件 | URL | 表/章节 |
| --- | --- | --- |
| TI INA226 | https://www.ti.com/lit/ds/symlink/ina226.pdf | SBOS547C；Table 7-1 寄存器集（p.22）、Table 7-2 config、7-3 AVG、7-4 VBUSCT |
| Bosch BMM350 | https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bmm350-ds001.pdf | BST-BMM350-DS001-27；Table 8 寄存器图（p.26–28）、§9.2.3 dummy bytes（p.46） |
| OneMO ML307R | https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1189/AT_Commands_Reference_Guide_4G_Series_V1.8.1.pdf | 105 条 AT 命令；MIPOPEN/MIPSEND/MIPRD/MIPCALL 章节 |

**上游驱动（`m5stack/uiflow-micropython` master `f20d5a00e8c9106aae1d944f3d6f1128839f59cb`，2026-11-02）：**

固定 SHA 的 raw 根：`https://raw.githubusercontent.com/m5stack/uiflow-micropython/f20d5a00e8c9106aae1d944f3d6f1128839f59cb/m5stack/libs/`

| 文件 | 关键行 |
| --- | --- |
| `unit/ina226.py` | `:8` class、`:30-43` 1A/10A 参数与校准 |
| `driver/ina226.py` | `:33-42` 寄存器、`:117-231` 校准/读数 |
| `unit/bmm350.py` | `:14` class、`:31-40` 初始化 |
| `driver/bmm350.py` | `:12-23` 地址/寄存器、`:38-57` 初始化、`:117-119` 数据读 |
| `unit/step16.py` | `:30-41` 寄存器、`:51-403` API |
| `unit/timerpwr.py` | `:28-56` 寄存器、`:150-211` V/I、`:313-542` 定时/触发 |
| `unit/mq.py` | `:33-44` 寄存器、`:76-302` API |
| `unit/bytebutton.py` | `:4-23` ByteUnit/寄存器、`:341` ByteButtonUnit、`:348` ByteSwitchUnit |
| `unit/servos8_v2.py` | `:15-30` 寄存器、`:57-65` 模式、`:543-654` 遥测/UID |
| `unit/roller485.py` | `:17-62` 地址/寄存器、`:508` Roller485、`:649` CRC8 |
| `unit/rollercan.py` | `:17-63` 地址/寄存器/CAN 命令、`:554` RollerCAN |
| `unit/cardkb.py` | `:200-206` 帧常量、`:436` CardKBI2C、`:461-466` 寄存器、`:538` CardKBUART |
| `unit/cat1.py` | `:18` class |
| `driver/simcom/ml307r.py` | `:127-362` MIPOPEN/MIPSEND/MIPRD、`:573-676` MIPCALL/DNS |
| `driver/simcom/common.py` | `:64-134` 基础 AT 命令表 |
| `chain/chain.py` | `:13-44` 命令/状态码/设备类型、`:79` CRC、`:87` 打包、`:454` ChainBus |
| `chain/unit_bus.py` | `:10` BusChainUnit、`:32-54` CMD_BUS_* |
| `chain/servos8_v2.py` | `:31-58` 命令/设备类型/模式 |
| `unit/__init__.py` | `:18` BMM350Unit、`:22` ByteButtonUnit、`:23` ByteSwitchUnit、`:24` CardKBUnit、`:25` Cat1Unit、`:94` MQUnit、`:120` Roller485Unit、`:121` RollerCANUnit、`:123` INA226Unit、`:131` Servos8V2Unit、`:133` Step16Unit、`:137` TimerPWRUnit |
| `chain/__init__.py` | `:8` ChainBus、`:16` Servos8V2Chain、`:19` BusChainUnit |

**官方 GitHub 仓库克隆 HEAD（`2026-11-03`）：**

| 仓库 | HEAD |
| --- | --- |
| m5stack/M5Unit-Roller485-Internal-FW | `7216b24a264e` |
| m5stack/M5Unit-RollerCAN-Internal-FW | `20039c84b122` |
| m5stack/M5Unit-ByteSwitch-Internal-FW | `ecc1b0c1dd71` |
| m5stack/M5Unit-ByteButton-Internal-FW | `0ad1bc9bd5b5` |
| m5stack/M5Unit-Step16-Internal-FW | `f38479ae964f` |
| m5stack/M5Unit-MQ-Internal-FW | `31744153440f` |
| m5stack/M5Unit-TimerPWR-Internal-FW | `b35b91e63b8f` |
| m5stack/M5Unit-8Servos2-I2C-Internal-FW | `44bdc24af921` |
| m5stack/M5Unit-CardKB2-UserDemo | `282e4bc28363` |
| m5stack/M5Chain | `277dcfe84a57` |
| m5stack/M5Chain-Series-Internal-FW | `421e922663bb` |
| m5stack/M5UnitUnified | `68a8fa74959a` |
| m5stack/M5Unit-Roller | `90c84dd21a8e` |
| m5stack/M5Unit-MQ / Step16 / TimerPWR / ByteButton / 8Servos2-I2C | `97dc4378f31b` / `1b2c77317267` / `b9ed9b020f5d` / `160e4543606d` / `2f02c0b58f42` |
| m5stack/M5Unit-CatM / M5Unit-CAN | `9d847aed9d02` / `7fb3bbc12d82` |

> 说明：`M5UnitUnified` 当前 `main` 已拆分为"核心库 + 各 Unit 独立仓库"（`M5Unit-*`），本批
> 未在 `M5UnitUnified` 内找到 17 款的 Unit 驱动源文件；因此 INA226/BMM350/CardKB2 的
> 芯片级寄存器以 TI/Bosch datasheet 与 UIFlow2 `driver/` 为准。

## 9. 结论边界

1. 本批只证明"**有公开、可核对的协议文档**"，不证明"已实现/已 PASS"；所有 17 款仍为
   `planned`，无 QEMU 模型、无 guest 证据。
2. 协议表用于**数据面寄存器/帧实现**，不用于声明物理能力：电机/FOC、传感器物理量、
   RF/蜂窝、SIM/网络、光学/机械/热学都必须保持 NOT RUN。
3. 上游 master 驱动是**软件参考**，不是硬件证明；冻结快照 `528edd8` 与 master `f20d5a0`
   的差异说明"驱动在快照之后合入"，若后续要跑 guest 断言，必须先固定 firmware SHA 与
   UIFlow2 版本（不能把 master 驱动结论继承到 V2.1.5 固件）。
4. 地址冲突（0x64×4、0x41×2、UART/Chain 共用）应在 attachment 层 fail-closed 处理；
   `0x64` 四款与 `0x41` 两款在同一总线不能同时 attach。
5. b 类 2 款（`cardkb2`、`cat1-cn`）的缺口已逐条列出；在缺口关闭前不应把它们写成 a 类，
   也不应把 BLE/ESP-NOW/蜂窝网络写成"可模拟"。
6. 若将来落地模型：先按 §7 顺序、先 I2C 寄存器文件后帧协议，复用现有 I2C slave /
   UART fixture responder / RMT 捕获框架；BMM350 必须实现 2 dummy 字节，Chain 必须实现
   CRC 帧级解析，RS485/CAN 需要新的 attachment 决策。
