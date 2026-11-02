# Unit 第九批协议研究：12 款剩余 Unit（驱动-gap / 复用尾部）的官方证据与 unresolved

日期：`2026-11-03`。范围：`products.json` unit 类别中**尚未研究**的候选 Unit
里挑 12 款，记录官方页面、冻结 UIFlow2/M5Unified 驱动证据、QEMU 复用/新增
建议、可断言数据面与风险。本批是 batch1-8 之后的**尾部批次**，剩余池里多数
产品没有公开 UIFlow2 Unit 驱动，因此本页显式记录 driver-gap/DEFER，不按名字
猜协议。catalog 草稿见 `2026-11-03-batch9-catalog-draft.json`，全部 `planned`。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 123 款（105 implemented + 18 planned）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..8-protocols.md`（96 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git HEAD `528edd8`）。
- M5Unified 显示组合：`m5stack/components/M5Unified/mpy_m5unified.cpp`
  （`unit_glass` 配置）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD
  `75f1d24`，canonical native layer）与 Unit 模型层 `0120-0145`；本批未修改
  QEMU。
- 官方页面在 `2026-11-03` 重新抓取核对（引用见 §8）。

## 0. 结论摘要

本批从剩余**未研究**的 Unit 中选 12 款，覆盖 **5 款 I2C、4 款 UART、
2 款 GPIO/RF、1 款 I2C/CAN 电机**：

| # | Unit id | SKU | 总线/地址 | 驱动状态 | 复杂度 |
| --- | --- | --- | --- | --- | --- |
| 4.1 | `glass` | U158 | I2C `0x3D`（SSD1309） | 有 `unit/glass.py`（M5Unified 组合） | 中 |
| 4.2 | `cardkb2` | U215 | I2C/UART 双模（PORT.CUSTOM G26/G25） | **无 official UIFlow2 Unit 驱动** | 中高 |
| 4.3 | `8servos2-i2c` | U222 | I2C `0x25`–`0x34`（旋钮地址） | **无 Unit 驱动**（内部固件协议） | 中 |
| 4.4 | `bmm350` | U231 | I2C `0x14`（BMM350） | **无 Unit 驱动** | 中 |
| 4.5 | `ina226-10a` | U200 | I2C `0x41`（INA226） | **无 Unit 驱动** | 中 |
| 4.6 | `lorawan-as923` | U184-AS923 | UART 115200（PORT.C） | `unit/lorawan.py` 仅 ASR650x/470，无 AS923 类 | 中高 |
| 4.7 | `lorawan-eu868` | U184-EU868 | UART 115200（PORT.C） | `unit/lorawan.py` 用 470；驱动有 `LoRaWAN_868` 未用 | 中高 |
| 4.8 | `fingerprint2` | U203 | UART 115200（PORT.C） | **无 Unit 驱动**（A-K323CP） | 中高 |
| 4.9 | `audioplayer` | U197 | UART 9600 8N1（PORT.C） | **无 Unit 驱动**（N9301） | 中 |
| 4.10 | `rf433t` | U114 | GPIO 黄=RF_TX（PORT.B） | **无 Unit 驱动**（ASK bitbang） | 中低 |
| 4.11 | `rf433r` | U113 | GPIO 白=RF_RX（PORT.B） | **无 Unit 驱动**（ASK 接收） | 中低 |
| 4.12 | `rollercan` | U188 | I2C `0x64` + 2×CAN | **无 Unit 驱动**（内部固件） | 中高 |

未研究集合推导：`products.json` 184 款 unit 中，与 catalog 123 个 id 精确
重合 122 款（`servo8-hat` 是 HAT 口径差），未登记 = 184 − 122 = 62；batch1-8
已研究 96 款，其中 batch7 剩余 7 款（hex/mini-pdm/catm/catm-gnss/lorawan-cn470/
can/mini-imu-pro）与 batch8 剩余 7 款（pahub-v21/lcd/oled/mini-oled/glass2/
gps-v11/gps-sma/nbiot-cn/lora-e220-920/lorawan-us915/mini-can/mic 中除已实现
者）已在本批前被研究/实现，不重复；实际从 **55 款未研究**中选 12 款。其余
未选主要是纯 passive/转接（proto/mini-proto/grove-to-grove/typec-to-grove/
m5-bit/rca/unit-396）、摄像头/Linux 模块（unitv*/timerCamera*/m5camera*/
esp32cam/poe-cam*/cams3-5mp/poesp32）、以及仅内部固件/无公开协议的产品
（byteswitch/bytebutton/step16/puzzle/mq/dcssr/timerpwr/doF*/cardkb2?/
rollercan-lite 等）。本批不把未选写成 planned。

**推荐优先级（按“可复用框架 + 可断言数据面 + 冲突可控”）**：

1. `glass`（U158）— 有 `unit/glass.py` + M5Unified 组合；与 batch8 Glass2
   同 SSD1309/0x3D，加 2 按键 + 1 蜂鸣器，显示组合可复用。
2. `rf433t` / `rf433r`（U114/U113）— 纯 GPIO 数字 bitstream，可直接复用
   GPIO 输出观察/输入 fixture；RF 物理 NOT RUN 但数据面可断言。
3. `8servos2-i2c`（U222）— 8 通道多模式 I2C 控制器，0x25–0x34 与 servo8/
   hbridge 等既有地址冲突明确，协议为内部固件/页面表，适合做 planned 契约。
4. `audioplayer`（U197）— 9600 8N1 UART N9301；与 synth/midi 同一 UART
   responder 框架，音频解码 NOT RUN。
5. `fingerprint2`（U203）— 115200 UART A-K323CP；UART 帧 fixture responder
   可复用，生物特征 NOT RUN。

主要 unresolved/driver-gap：

- **本批近一半产品没有公开 UIFlow2 Unit 驱动**：`cardkb2`（UIFlow2 “coming
  soon”）、`8servos2-i2c`、`bmm350`、`ina226-10a`、`fingerprint2`、
  `audioplayer`、`rf433t/r`、`rollercan` 都只有产品页/内部固件/外部手册。
  不得按产品名猜寄存器；实现前必须取得寄存器手册或内部固件。
- `cardkb2`：ESP32-C61，I2C/UART/BLE HID/ESP-NOW 四模式，出厂 I2C；页面
  未给数字 I2C 地址（只给“User Manual & Registers”外部链接），且 Grove
  引脚是 **PORT.CUSTOM G26/G25**，与 cores3 PORT.A/PORT.C 都不同 → 地址与
  attachment 都 unresolved。
- `8servos2-i2c`：I2C 地址由 16 位旋钮 0x25–0x34；8 通道可配 servo/digital/
  ADC/RGB/PWM；页面 Protocol 表未在文本中给出完整寄存器/命令（内部固件），
  driver 缺失；0x25 与已实现 `8servos`（U165）冲突，0x26 与 scales 系冲突。
- `bmm350`：I2C 0x14，±2000µT/0.1µT；页面无寄存器表，冻结树无 BMM350
  driver；Bosch datasheet 寄存器/校准/OTP 需单独钉。
- `ina226-10a`：I2C 0x41，±10A/0–30V，5mΩ shunt；页面无寄存器表，冻结树
  无 INA226 driver；标准 INA226 寄存器（config/shunt/bus/power/current/
  calibration/mask）来自 datasheet 而非本页，需以 datasheet SHA 为准。
- `lorawan-as923/eu868`：产品 STM32WLE5/RAK3172，`unit/lorawan.py` 用
  `driver.asr650x.LoRaWAN_470`；驱动有 `LoRaWAN_868`（EU868）但没有 AS923
  子类，EU868 包装也未使用 868 类 → AT 兼容性/频段配置 unresolved。
- `fingerprint2`：A-K323CP UART 115200，100 用户、7262B/entry、RGB 环；
  无 Unit 驱动；页面 Protocol 未给帧格式（外部手册），与 batch6 `finger`
  FPC1020A 不是同一芯片，不能复用其帧/版本门。
- `audioplayer`：N9301 UART 9600 8N1，MP3/WAV、microSD；无 Unit 驱动；
  页面 Protocol 未给命令表，需外部手册；音频/3.5mm 输出 NOT RUN。
- `rf433t`/`rf433r`：SYN115/SYN531R ASK 433.92MHz；RF 物理/天线/距离/
  10dBm/-109dBm NOT RUN；只能断言 GPIO bitstream 观察/输入 fixture。
- `rollercan`：STM32G431 + DRV8311 + D3504 电机，I2C 0x64 + 2×CAN，页面
  指向内部固件/协议文档；无 Unit 驱动；FOC/电机/编码器/OLED/RGB NOT RUN。
- `glass`：I2C 0x3D，SSD1309，2 按键+蜂鸣器；`unit/glass.py` 只把屏加入
  M5Unified 外部显示组合，页面 Protocol 表在文本抓取中不可读；0x3D 与
  LCD/OLED/MiniOLED 冲突。

## 1. 方法与纪律

- 只信官方页面 + 冻结驱动源码 + M5Unified 组合源码；寄存器/地址/命令必须
  有 `file:line` 或页面/手册出处；缺失时显式 driver-gap/unresolved。
- 不运行 QEMU；QEMU 建议只描述控制器/模型复用位置，不代表已实现。
- 每款给出 fixture/注入、可断言数据面、QEMU 复用/新增建议、风险与冲突。
- catalog 草稿只写 `planned`，不升级 runtime/profile，不产生 evidence。

## 2. 总线与控制器复用

| 总线 | 本批 Unit | QEMU 复用 | 新增/缺口 |
| --- | --- | --- | --- |
| I2C | glass、cardkb2、8servos2-i2c、bmm350、ina226-10a、rollercan | Unit I2C slave 框架（0123/0130/0139-0145）；`unit/glass.py` + M5Unified `unit_glass` 组合 | cardkb2/8servos2/bmm350/ina226/rollercan 均缺 Unit 模型与驱动；需先拿寄存器手册 |
| UART | lorawan-as923、lorawan-eu868、fingerprint2、audioplayer | 0145 的 UART fixture responder（TX 捕获 + idle 响应注入）；batch8 LoRaWAN responder | 无协议解码；A-K323CP/N9301/LoRaWAN 帧格式缺手册 |
| GPIO/RF | rf433t、rf433r | GPIO 数字输出观察/数字输入 fixture；RMT/GPIO 框架 | ASK bitstream 可直接观察，但 RF 物理 NOT RUN |
| I2C/CAN | rollercan | cores3 TWAI/CANBusState（0145 can 路径）+ I2C slave 框架 | 内部固件协议缺手册；I2C 0x64 + CAN 双模需二选一 |

QEMU 事实：

- 0145 已加入 `CanBusClientState`、`inject-hex`、UART fixture responder、
  `US_BMI270`；本批可复用 UART responder 与 CAN 观测（若 rollercan 走 CAN）。
- M5Unified `mpy_m5unified.cpp:232-321` 支持 `unit_glass` 外部显示组合；
  `unit/glass.py:39` 调用 `M5.addDisplay(i2c, address, {"unit_glass": True})`。
- GPIO 数字输入/输出/RMT 通道可用于 rf433t/r 的 bitstream 观察，但 RF
  发射/接收、天线、调制/解调物理不在模型内。

## 3. 地址/端口冲突与优先级建议

- **I2C 0x3D/0x3C/0x3E**：glass 0x3D 与 batch8 lcd/oled/mini-oled/glass2
  冲突；同一总线只能挂一个显示。
- **0x25–0x34**：8servos2-i2c 旋钮地址与 `8servos` U165（0x25）、
  scales/weight-i2c/4relay（0x26）、joystick 等冲突。
- **0x14**：bmm350 与 batch6/7 的 mini-imu-pro BMM150 aux（0x10）不同，
  0x14 本身空闲但需与板级传感器区分。
- **0x41**：ina226-10a 与 ina226-1a 同地址 0x41，二选一。
- **0x64**：rollercan 与 batch5/6 的 hbridge? 0x20 不冲突；与其它 0x64
  设备（若有）需检查；页面未列冲突。
- **PORT.C**：lorawan-as923/eu868、fingerprint2/audioplayer 与所有 UART
  Unit 共享，一次一个；`cardkb2` 的 PORT.CUSTOM G26/G25 不在现有 host-port
  准入，attachment unresolved；rf433t/r 占 PORT.B 黄/白两线，二选一。
- 建议实现顺序：`glass` → `rf433t`/`rf433r` → `audioplayer` →
  `fingerprint2` → `8servos2-i2c` → `bmm350` → `ina226-10a` →
  `rollercan` → `cardkb2` → `lorawan-as923`/`eu868`；无驱动者先补手册。

## 4. 逐款协议研究

### 4.1 `glass` — Unit Glass（U158）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Glass（U158，5V，PORT.A
  黄=SDA 白=SCL）。STM32F030F4P6 + SSD1309，1.51" 透明 OLED 128×64
  （透明区 128×56），**I2C @0x3D**，2 个输入按键 + 1 个蜂鸣器。
- 官方驱动：`unit/glass.py:11-39` `GlassUnit(i2c, address=0x3D,
  freq=400000)` → `M5.addDisplay(i2c, 0x3D, {"unit_glass": True})`；
  M5Unified `mpy_m5unified.cpp:232-321` 配置 `external_display.unit_glass`
  并实例化 `M5UnitGLASS` 组合。页面“Internal Firmware / Protocol”表在
  文本抓取中不可读（图片/表格乱码），只能锚定驱动组合与页面规格。
- 协议/数据面：SSD1309 命令/像素流由 M5Unified 外部屏驱动发出；2 按键 +
  蜂鸣器是 STM32 内部固件行为，页面无按键/蜂鸣器寄存器表。
- Fixture/注入：无 host sensor fixture；guest 绘制产生命令流；QOM 建议
  `command-hex`、`panel-framebuffer`、`button-states`、`buzzer-hex`、
  `i2c-address`。
- QEMU 复用：batch8 `glass2` 的显示组合 lane；新增 `unit_glass` 组合键与
  2 按键/蜂鸣器 fixture（若实现内部固件命令表，需先取得其协议）。
- 可断言：guest addDisplay 成功、命令流/面板 framebuffer 摘要、0x3D；
  按键/蜂鸣器仅在内部固件协议补全后可断言。
- 风险/冲突：0x3D 与 LCD/OLED/MiniOLED/Glass2 冲突；页面 Protocol 文本
  不可读；透明 OLED 光学/亮度/按键/蜂鸣器物理 NOT RUN。
- 复杂度：中。

### 4.2 `cardkb2` — Unit CardKB2（U215）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_CardKB2（U215，5V，
  PORT.CUSTOM：黄=SDA/UART_RX/G26，白=SCL/UART_TX/G25）。ESP32-C61HF4，
  42 键 + RGB 状态灯 + Reset/Boot，I2C/UART/BLE HID/ESP-NOW 四模式，
  出厂 I2C；UIFlow2 页面标 **coming soon**（无 official Unit 驱动）。
- 官方协议：页面“Unit CardKB2 User Manual & Registers”外部链接（页面未
  直接给数字 I2C 地址/寄存器表）；只能确认四模式切换（Fn+Sym+1..4）与
  出厂 I2C。**I2C 地址 unresolved**，UART 波特率页面仅给 USB 日志
  115200，Grove UART 模式未写。
- Fixture/注入：I2C 模式需先取得手册的键值/状态寄存器；UART 模式需帧
  格式；当前只能 planned 契约（keys/led-rgb/mode）。
- QEMU 复用：I2C 可复用 cardkb 单字节/矩阵框架，但地址/寄存器未知；UART
  可复用 fixture responder；PORT.CUSTOM 不在 cores3 host-port 准入，需
  新 attachment 或映射到 PORT.A/PORT.C 并记录替换。
- 可断言：模式切换（若走 UART/按键序列）、键值 fixture、RGB；全部要求
  先补手册。
- 风险/冲突：无 official UIFlow2 driver；I2C 地址/UART 波特率/帧格式
  unresolved；PORT.CUSTOM G26/G25 与标准 Grove PORT.A/PORT.C 不同；
  Wi-Fi/BLE HID/ESP-NOW RF 与键盘机械/固件行为 NOT RUN。
- 复杂度：中高。

### 4.3 `8servos2-i2c` — Unit 8Servos2-I2C（U222）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_8Servos2-I2C（U222，
  DC9-24V 或 5V，Grove：黄=SDA 白=SCL）。STM32G031G8U6，8 路可配
  servo/digital-in/out/ADC/RGB/PWM；INA199 电流检测；16 位旋钮地址
  **0x25–0x34**。
- 官方驱动：**public UIFlow2 无 8Servos2 Unit 驱动**；页面“Internal
  Firmware / Protocol”表未在文本抓取中给出完整寄存器/命令（内部固件）。
  可参考已登记 `servos8.py`（U165 8Servos，0x25）但两者不是同一 SKU/
  固件，不能直接复用寄存器。
- Fixture/注入：8 通道模式/角度/脉冲/ADC/RGB/PWM 的 fixture 需手册；
  QOM 建议 `channel-modes`、`servo-angles`、`adc-values`、`rgb-leds`、
  `pwm-duty`、`current-ma`。
- QEMU 复用：若拿到寄存器表，复用 `unit/servos8` 的 8 通道掩码/角度框架
  + I2C control slave；地址 0x25–0x34；下游不是总线，无 mux。
- 可断言：地址旋钮映射、8 通道模式/角度/ADC/RGB fixture；servo 机械/
  电流/电源 NOT RUN。
- 风险/冲突：无 Unit 驱动/协议表；0x25 与 `8servos` U165 冲突、0x26 与
  scales 系冲突；DC9-24V/3A/INA199 电气/热 NOT RUN。
- 复杂度：中。

### 4.4 `bmm350` — Unit BMM350（U231）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_BMM350（U231，5V，
  PORT.A）。BMM350 三轴 TMR 磁力计，**I2C @0x14**，±2000µT、约 0.1µT
  分辨率、100/400kHz；无加速度/陀螺/气压。
- 官方驱动：**public UIFlow2 无 BMM350 Unit/driver**；页面无寄存器表。
  Bosch BMM350 的 CHIP_ID/OTP 校准/数据寄存器需 datasheet 另钉；不能
  用 BMM150 或 mini-imu-pro aux 模型直接代替。
- Fixture/注入：`magnetic-x/y/z` fixture；QOM 建议 `whoami`、
  `magnetic-*`、`heading-deg`、`i2c-address`、`transactions`。
- QEMU 复用：新增 `US_BMM350` I2C register file；若只做 planned 契约可
  暂不实现（driver-gap）。
- 可断言：chip-id/磁力 fixture/heading（若驱动公式可得）；磁力物理/
  TMR/温度稳定性/校准 NOT RUN。
- 风险/冲突：无 driver/寄存器表；0x14 本身空闲但需与板级 BMM150（0x10）
  区分；heading 校准/精度 NOT RUN。
- 复杂度：中。

### 4.5 `ina226-10a` — Unit INA226-10A（U200）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_INA226-10A（U200，5V，
  PORT.A）。INA226 隔离电流/电压监控，**I2C @0x41**，0–30V、±10A
  双向、5mΩ shunt、完整电气隔离/自恢复保险。
- 官方驱动：**public UIFlow2 无 INA226 Unit 驱动**；页面无寄存器表。
  标准 INA226 寄存器（config 0x00、shunt 0x01、bus 0x02、power 0x03、
  current 0x04、calibration 0x05、mask 0x06、alert 0x07 等）来自 TI
  datasheet，需固定 datasheet SHA 后才能实现，不能凭产品页猜。
- Fixture/注入：`bus-voltage-v`、`shunt-voltage-mv`、`current-a`、
  `power-w`、`calibration`；QOM 建议上述 + `i2c-address`。
- QEMU 复用：新增 `US_INA226` I2C register file（标准 16-bit registers）；
  隔离/电源/报警 NOT RUN。
- 可断言：guest 读 bus/current/power 与 fixture 一致（按 datasheet 公式）；
  隔离/±10A/30V/保险/精度 NOT RUN。
- 风险/冲突：无 driver/寄存器表；0x41 与 ina226-1a 同地址（二选一）；
  隔离/保险/热 NOT RUN。
- 复杂度：中。

### 4.6 `lorawan-as923` — Unit LoRaWAN-AS923（U184-AS923）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_LoRaWAN-AS923
  （U184-AS923，5V，PORT.C 黄=UART_RX 白=UART_TX）。STM32WLE5/RAK3172，
  LoRaWAN 1.0.3 Class A/B/C，AS923（923–925MHz），OTAA/ABP/P2P，
  **UART 115200 AT**。
- 官方驱动：`unit/lorawan.py:13-22` `LoRaWANUnit(LoRaWAN_470)` 使用
  `driver/asr650x.py:14` ASR650x 平台；驱动类 `LoRaWAN_915`（US915）、
  `LoRaWAN_868`（EU868），**没有 AS923 子类**；产品 STM32WLE5 与
  ASR650x 驱动错配 unresolved。
- AT 命令（参考 `driver/asr650x.py`）：`AT+CGSN?`、`AT+CDEVADDR?/=`、
  `AT+CDEVEUI?/=`、`AT+CAPPEUI?/=`、`AT+CAPPKEY?/=`、
  `AT+CJOINMODE?/=`、`AT+CFREQBANDMASK?/=`、`AT+CWORKMODE?/=`、
  `AT+CCLASS?/=` 等；AS923 band mask 具体值 unresolved。
- Fixture/注入：`responses-hex`；QOM `tx-hex`/`frames-sent`/
  `frames-injected`/`join-status`（若解析）。
- QEMU 复用：0145 LoRaWAN responder；不新增 stack/RF。
- 可断言：AT 字节/fixture 响应；Join/OTAA/ABP、AS923 RF/占空比/认证
  NOT RUN。
- 风险/冲突：STM32WLE5 vs ASR650x、无 AS923 类、AT/命令响应格式
  unresolved；PORT.C 与所有 UART Unit 冲突。
- 复杂度：中高。

### 4.7 `lorawan-eu868` — Unit LoRaWAN-EU868（U184-EU868）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_LoRaWAN-EU868
  （U184-EU868，5V，PORT.C）。STM32WLE5/RAK3172，LoRaWAN 1.0.3
  Class A/B/C，EU868（863–870MHz），OTAA/ABP/P2P，UART 115200 AT；
  外置 2.8dBi 天线。
- 官方驱动：同 4.6；驱动**有** `LoRaWAN_868`（`driver/asr650x.py:918`）
  但 `unit/lorawan.py` 仍继承 `LoRaWAN_470`，未使用 EU868 类；
  产品 STM32WLE5 vs ASR650x 错配 unresolved。
- Fixture/注入/QOM/可断言：同 4.6；EU868 band mask/占空比/认证 NOT RUN。
- 风险/冲突：同 4.6；EU868 类存在但包装未用是明确的集成 unresolved。
- 复杂度：中高。

### 4.8 `fingerprint2` — Unit Fingerprint2（U203）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Fingerprint2
  （U203，5V，PORT.C 黄=UART_RX 白=UART_TX）。STM32G031G8U6 +
  A-K323CP 电容指纹，100 用户、508dpi、80×208、7262B/entry，
  **UART 115200 8N1**，RGB 环。
- 官方驱动：**public UIFlow2 无 Fingerprint2 Unit 驱动**；页面
  “Internal Firmware / Protocol”未给帧/命令表（外部手册）。它与 batch6
  `finger` U008 的 FPC1020A 不是同一芯片/帧协议，不能复用其
  0xF5 帧/版本门。
- Fixture/注入：`response-frames`（按命令的 fixture 响应，需手册）；
  QOM 建议 `tx-hex`/`rx-hex`/`user-count`/`match-result`/`version`。
- QEMU 复用：0145 UART responder；帧格式缺失时只能字节观察。
- 可断言：UART TX/RX fixture 字节；指纹采集/匹配/100 用户/RGB 环 NOT RUN。
- 风险/冲突：无 driver/帧格式；生物特征安全边界；PORT.C 冲突。
- 复杂度：中高。

### 4.9 `audioplayer` — Unit AudioPlayer（U197）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_AudioPlayer
  （U197，5V，PORT.C 黄=UART_RX 白=UART_TX）。N9301 MP3/WAV 解码 +
  microSD（FAT16/32，≤32GB）+ 3.5mm stereo jack；**UART 9600 8N1**。
- 官方驱动：**public UIFlow2 无 AudioPlayer Unit 驱动**；页面
  “Internal Firmware / Protocol”未给命令表（外部手册）。
- Fixture/注入：`responses-hex`；QOM `tx-hex`/`frames-sent`/
  `frames-injected`；命令/状态需手册。
- QEMU 复用：0145 UART responder；音频解码/3.5mm/存储 NOT RUN。
- 可断言：UART 字节/fixture；MP3/WAV 解码、microSD、音频输出 NOT RUN。
- 风险/冲突：无 driver/命令表；PORT.C 冲突；3.5mm 音频物理 NOT RUN。
- 复杂度：中。

### 4.10 `rf433t` — Unit RF433T（U114）

- 官方页面：https://docs.m5stack.com/en/unit/rf433_t（U114，5V，PORT.B
  黄=RF_TX，白=NC）。SYN115 ASK 发射器，433.92MHz，10kbps，10dBm，
  PCB 天线，稳定 10m。
- 官方驱动：**public UIFlow2 无 Unit 驱动**；UIFlow 示例用 GPIO bitbang
  发送 ASK 数据。页面只给 RF 规格与 SYN115 datasheet 链接；没有宿主
  GPIO 时序/编码表。
- Fixture/注入：guest 对 RF_TX 的 bitstream 观察；QOM 建议 `tx-level`/
  `edge-count`/`last-edge-ns`/`tx-bitstream`。
- QEMU 复用：GPIO 数字输出/RMT 观察框架；ASK/433.92MHz/天线/RF 物理
  NOT RUN。
- 可断言：guest bitbang 的 GPIO 边沿/电平序列；RF 发射/距离/功率 NOT RUN。
- 风险/冲突：无 Unit 驱动/编码协议；PORT.B 与 rf433r/其它 Unit 冲突；
  SYN115 外部电阻/功率控制 NOT RUN。
- 复杂度：中低。

### 4.11 `rf433r` — Unit RF433R（U113）

- 官方页面：https://docs.m5stack.com/en/unit/rf433_r（U113，5V，PORT.B
  黄=NC，白=RF_RX）。SYN531R ASK 接收器，433.92MHz，1kbps，
  -109dBm，PCB 天线，10m。
- 官方驱动：**public UIFlow2 无 Unit 驱动**；UIFlow 示例用 GPIO 数字
  输入采样 RF_RX。
- Fixture/注入：RF_RX 数字输入 fixture（bitstream/边沿）；QOM 建议
  `rx-level`/`edge-count`/`rx-bitstream`。
- QEMU 复用：GPIO 数字输入/边沿观察；ASK 解调/RF/天线/距离 NOT RUN。
- 可断言：guest 采样到的数字 bitstream 与 fixture 一致；RF 接收物理
  NOT RUN。
- 风险/冲突：无 Unit 驱动/编码协议；PORT.B 与 rf433t 冲突。
- 复杂度：中低。

### 4.12 `rollercan` — Unit RollerCAN（U188）

- 官方页面：https://docs.m5stack.com/en/unit/Unit-RollerCAN（U188，5V
  或 6–16V，Grove：黄=SDA 白=SCL）。STM32G431CBU6 + DRV8311 +
  D3504 200KV 电机 + TLI5012 编码器；**2×CAN（XT30）+ 2×I2C（0x64）**，
  0.66" OLED、2×WS2812、按键、滑环。
- 官方驱动：**public UIFlow2 无 Unit 驱动**；页面“Internal Firmware /
  Communication Protocols”为外部开源文档；I2C 0x64 寄存器/CAN 帧格式
  未在页面给出。
- Fixture/注入：若走 I2C，需内部固件寄存器表（模式/目标速度/位置/
  电流/编码器/状态）；若走 CAN，需 CAN 帧 ID/DLC/字节序。QOM 建议
  `mode`/`target-speed`/`actual-speed`/`target-position`/`actual-position`/
  `current`/`encoder`/`fault`。
- QEMU 复用：I2C slave 框架或 0145 CANBusClient；二选一（页面 I2C 0x64
  与 CAN 双模）；电机/FOC/编码器/OLED/RGB/滑环 NOT RUN。
- 可断言：寄存器/CAN 字节 fixture；电机物理/闭环/负载/噪声/热 NOT RUN。
- 风险/冲突：无 driver/寄存器表；I2C 0x64 与其它 0x64 设备需检查；CAN
  attachment 仍是 0145 的有限观测；DC6–16V/电机安全 NOT RUN。
- 复杂度：中高。

## 5. catalog 草稿

`2026-11-03-batch9-catalog-draft.json` 含 12 条 `planned` 草稿，字段与
batch1-8 一致：`id/name/sku/visual_asset/official_docs/checked_at/chips/
interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/
blocker/limitations`。`runtime.status` 全部 `planned`，`model_status` 全部
`planned`；不写 evidence/PASS，不升级 profile。

草稿要点：

- 12 款里仅 `glass` 有官方 Unit 驱动组合，`lorawan-*` 有（错配的）
  `unit/lorawan.py`；其余显式 `driver-gap`，保留外部手册/内部固件
  unresolved，不按名字猜寄存器。
- `cardkb2` 的 I2C 地址/UART 帧、`8servos2-i2c` 寄存器、`bmm350`/
  `ina226` 寄存器、`fingerprint2`/`audioplayer` 帧、`rollercan` 协议
  全部 unknown；QEMU 只能先做 GPIO/UART 字节观察或 planned 契约。
- `rf433t/r` 只做 GPIO bitstream 观察，RF 物理/天线/功率 NOT RUN。
- 所有显示/光学/声学/生物特征/电机/RF 语义写 `NOT RUN`，不写 simulated。

## 6. unresolved 汇总

| Unit | unresolved | 影响 |
| --- | --- | --- |
| `glass` | 页面 Protocol 文本不可读；2 按键/蜂鸣器内部固件无表；0x3D 冲突 | 只能做 M5Unified 显示组合 lane |
| `cardkb2` | 无 Unit 驱动、I2C 地址未知、Grove UART 帧未知、PORT.CUSTOM G26/G25 | attachment/地址/帧全部 blocked |
| `8servos2-i2c` | 无 Unit 驱动、内部固件协议表缺失；0x25 与 8servos 冲突 | 只能 planned 契约 |
| `bmm350` | 无 driver/寄存器表；BMM350 datasheet/OTP 未钉 | 只能 planned 契约 |
| `ina226-10a` | 无 driver/寄存器表；标准 INA226 寄存器需 datasheet SHA | 只能 planned 契约 |
| `lorawan-as923/eu868` | STM32WLE5 vs ASR650x；AS923 无驱动类；EU868 类未用 | AT/RF blocked |
| `fingerprint2` | 无 Unit 驱动/帧格式；与 finger U008 不同芯片 | 只能 UART 字节观察 |
| `audioplayer` | 无 Unit 驱动/命令表 | 只能 UART 字节观察 |
| `rf433t/r` | 无 Unit 驱动/编码协议；RF 物理 NOT RUN | 只能 GPIO bitstream |
| `rollercan` | 无 Unit 驱动/内部固件协议；I2C 0x64/CAN 帧未知 | 只能 planned 契约 |
| 多个 | 0x3D/0x14/0x41/0x64/0x25-0x34/PORT.B/C/CUSTOM 复用 | 一总线一 Unit |

## 7. 引用与复现

- 官方产品页（均于 2026-11-03 抓取）：`Unit_Glass`、`Unit_CardKB2`、
  `Unit_8Servos2-I2C`、`Unit_BMM350`、`Unit_INA226-10A`、
  `Unit_LoRaWAN-AS923`、`Unit_LoRaWAN-EU868`、`Unit_Fingerprint2`、
  `Unit_AudioPlayer`、`rf433_t`、`rf433_r`、`Unit-RollerCAN`。
- 驱动源码（冻结树 HEAD `528edd8`）：`unit/glass.py`、`unit/lorawan.py`、
  `driver/asr650x.py`；M5Unified `components/M5Unified/mpy_m5unified.cpp`。
- QEMU 只读坐标：canonical `hw/m5stopwatch/m5_unit_gpio.c`、
  `hw/m5stopwatch/m5_unit_i2c_sensors.c`、`hw/net/can/esp32s3_twai.c`；
  Unit 模型层 `patches/qemu-m5stack-peripherals/0120-0145`。
- 未运行 QEMU、未改 catalog/runtime/测试；raw 证据不涉及。

## 8. 抓取记录

| 页面 | URL | 用途 |
| --- | --- | --- |
| Glass | https://docs.m5stack.com/en/unit/Unit_Glass | SSD1309、0x3D、按键/蜂鸣器 |
| CardKB2 | https://docs.m5stack.com/en/unit/Unit_CardKB2 | ESP32-C61、四模式、PORT.CUSTOM |
| 8Servos2-I2C | https://docs.m5stack.com/en/unit/Unit_8Servos2-I2C | 0x25–0x34、8 通道多模式 |
| BMM350 | https://docs.m5stack.com/en/unit/Unit_BMM350 | 0x14、±2000µT |
| INA226-10A | https://docs.m5stack.com/en/unit/Unit_INA226-10A | 0x41、±10A/30V |
| LoRaWAN-AS923 | https://docs.m5stack.com/en/unit/Unit_LoRaWAN-AS923 | STM32WLE5、AS923、115200 |
| LoRaWAN-EU868 | https://docs.m5stack.com/en/unit/Unit_LoRaWAN-EU868 | STM32WLE5、EU868、115200 |
| Fingerprint2 | https://docs.m5stack.com/en/unit/Unit_Fingerprint2 | A-K323CP、115200、100 用户 |
| AudioPlayer | https://docs.m5stack.com/en/unit/Unit_AudioPlayer | N9301、9600、MP3/WAV |
| RF433T | https://docs.m5stack.com/en/unit/rf433_t | SYN115、433.92MHz、RF_TX |
| RF433R | https://docs.m5stack.com/en/unit/rf433_r | SYN531R、433.92MHz、RF_RX |
| RollerCAN | https://docs.m5stack.com/en/unit/Unit-RollerCAN | 0x64/CAN、电机/编码器 |

以上为研究结论，不构成实现/证据承诺；本批 driver-gap 较多，下一批实现前
必须先取得各产品“Internal Firmware / Protocol”文档或 datasheet，并重新
核对驱动树 HEAD 与地址/端口。

## 9. 首批 3 款实现状态（补丁 0149）

日期：`2026-11-02`。实现任务 `task-55`，分支 `m5agent/units19`（base `origin/main ed92aa6e`，
catalog 123 款）。

**补丁与 base**

- 补丁：`patches/qemu-m5stack-peripherals/0149-unit-batch9a.patch`（sha256 `84aad9a7…`，
  在 canonical 链上 `git apply --check` 通过）。
- canonical 链：`75f1d24` → `0120`-`0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132`
  → `0137` → `0138` → `0139` → `0140` → `0141` → `0142` → `0143` → `0144` → `0145` → `0146`
  → `0147`；本补丁是 `0120` 之后的第 29 层。`0148` 由并行 batch-8 剩余实现任务占用，不属于本链；
  `0150` 为下一个可用号。

**3 款实现与边界**

| Unit | SKU | 状态 | QEMU 模型 | unresolved / NOT RUN |
| --- | --- | --- | --- | --- |
| `glass` | U158 | planned（新命令/framebuffer slave + 静态 fixture） | 新增 `CONTROL_UNIT_GLASS`（I2C 0x3D）：SSD1309 control/command/data 帧（控制字节 0x00 命令流、0x40 GDDRAM 数据）、page/column 寻址、display on/off、contrast、1024B GDDRAM framebuffer 摘要；按键/蜂鸣器为静态 QOM fixture | **页面 Protocol 表不可读 → 内部固件按键/蜂鸣器语义 unresolved（不宣称）；0x3D 与 lcd/oled/mini-oled/glass2 冲突；透明 OLED 光学/亮度/按键/蜂鸣器物理 NOT RUN** |
| `rf433t` | U114 | planned（GPIO 输出观测，driver-gap） | PORT.B 黄=RF_TX：output-level / edge-count / bit-count / bitstream 观测 | **无官方 UIFlow2 Unit 驱动/ASK 编码表；RF 433.92MHz/ASK 调制/PCB 天线/10dBm/10m 距离与 SYN115 功率电阻 NOT RUN；PORT.B 冲突** |
| `rf433r` | U113 | planned（GPIO 输入 fixture，driver-gap） | PORT.B 白=RF_RX：input-level / sample-rate（300-10000Hz）/ samples | **无官方 UIFlow2 Unit 驱动/解码表；RF 433.92MHz/ASK 解调/PCB 天线/-109dBm 灵敏度/10m 距离 NOT RUN；PORT.B 冲突** |

**离线 QOM smoke**（S3 `m5atoms3r`，无 guest 固件）：`glass`/`rf433t`/`rf433r` 各 1 个 attachment，
QMP `qom-list`/`qom-set`/`qom-get` **15/15 PASS**——glass 地址 0x3D、GDDRAM 摘要 8-hex 默认、
button-states/buzzer-hex fixture 读写；rf433t 电平/边沿/bit 计数与 bitstream 属性默认；rf433r
input-level/sample-rate 写入与 samples 计数。smoke 不覆盖 I2C 命令字节语义、按键/蜂鸣器内部固件
行为或 RF 物理；这些仍需 guest/硬件证据。

**计数**：catalog 123 → **126**，runtime-profiles 123 → 126；visual mapping audit 3 条 +
`all-126-products` 标记；计数测试（test_unit_runtime / test_serve_api units / visual mapping /
batch3 A+B、batch7 A/B、batch8 A static marker）与 snapshot 已同步。

**共同边界**：3 款都是控制器可见的事务/寄存器/GPIO 观测模型；没有 guest 与 Device Service
证据前不得升级为 `implemented`/`simulated`/`validated`。
