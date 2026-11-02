# Unit 第八批协议研究：12 款剩余 Unit 的驱动证据、复用建议与 unresolved

日期：`2026-11-03`。范围：`products.json` unit 类别中**尚未研究**的候选 Unit
里挑 12 款，记录官方页面、官方 UIFlow2/M5Unified 驱动证据、QEMU 复用/新增
建议、可断言数据面与风险。本文件只做研究，不修改 catalog/runtime，不运行
QEMU；catalog 草稿见 `2026-11-03-batch8-catalog-draft.json`，全部 `planned`。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 111 款（100 implemented + 11 planned）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..7-protocols.md`（84 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git HEAD `528edd8`，batch1-8 共用的冻结驱动树）。
- M5Unified 显示组合：`m5stack/components/M5Unified/mpy_m5unified.cpp`（Unit
  OLED/LCD/MiniOLED/Glass/Glass2 通过 `M5.addDisplay()` 进入组合配置）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD
  `75f1d24`，canonical native layer）与已合入的 Unit 模型层
  `patches/qemu-m5stack-peripherals/0120-0144`；本批未修改 QEMU。
- 官方页面在 `2026-11-03` 重新抓取核对（引用见 §8）。

## 0. 结论摘要

本批从剩余**未研究**的 Unit 中选 12 款，覆盖 **5 款 I2C、5 款 UART、
2 款 GPIO/RMT/ADC/CAN**：

| # | Unit id | SKU | 总线/地址 | 复杂度 | 推荐优先级 |
| --- | --- | --- | --- | --- | --- |
| 4.1 | `pahub-v21` | U040-B-V21 | I2C `0x70`-`0x77`（PCA9548AP） | 低（复用 pahub 模型） | **高** |
| 4.2 | `lcd` | U120 | I2C `0x3E`（页面）/驱动 `0x3D`，ST7789V2 | 中（命令协议） | **高** |
| 4.3 | `oled` | U119 | I2C `0x3C`（页面）/驱动 `0x3D`，SH1107 | 中（显示组合） | 中 |
| 4.4 | `mini-oled` | U166 | I2C `0x3C`（页面）/驱动 `0x3D`，SSD1315 | 中（显示组合） | 中 |
| 4.5 | `glass2` | U158-B | I2C `0x3C`/`0x3D`，SSD1309 | 中（显示组合） | 中 |
| 4.6 | `gps-v11` | U032-V11 | UART 115200（页面）/驱动 9600，AT6668 | 中低（NMEA） | **高** |
| 4.7 | `gps-sma` | U190 | UART 115200（页面）/驱动 9600，AT6668 | 中低（NMEA） | **高** |
| 4.8 | `nbiot-cn` | U112 | UART 115200（SIM7020C） | 中（AT 应答器） | 中 |
| 4.9 | `lora-e220-920` | U170 | UART 9600（驱动，E220-900T22S JP） | 中（0xC0/C1 配置） | 中 |
| 4.10 | `lorawan-us915` | U184-US915 | UART 115200（STM32WLE5 页面） | 中高（AT/驱动错配） | 中 |
| 4.11 | `mini-can` | U179 | PORT.C CAN_TX/RX（TJA1051，1Mbps） | 中（CAN/TWAI） | 中 |
| 4.12 | `mic` | U096 | PORT.B 黄=数字比较器/白=模拟（ADC） | 中（无 Unit 驱动） | 中 |

未研究集合推导：`products.json` 184 款 unit 中，与 catalog 111 个 id 精确重合
110 款（`servo8-hat` 是 catalog-only HAT 口径差），未登记 = 184 − 110 = 74。
batch1-7 已研究 84 款，其中 7 款仍未登记（`can`/`catm`/`catm-gnss`/`hex`/
`lorawan-cn470`/`mini-imu-pro`/`mini-pdm`），batch6 已研究未登记 6 款已进入
catalog planned；扣除已研究未登记后，本批从 **67 款未研究**中选 12 款。其余
未选主要是摄像头/Linux 模块（unitv*/timerCamera*/cams3*/poe-cam/M5Camera/
ESP32CAM）、纯 passive/接口转接（proto/mini-proto/grove-to-grove/
typec-to-grove/m5-bit/rca）、以及无公开 Unit 驱动或仅 MCU 固件的
（mq/dcssr/step16/puzzle/byteswitch/bytebutton/8servos2/dof*/bmm350/
ina226/rf433*/asr/audioplayer/fingerprint2/cardkb2/timerpwr/chainbus 等）。
本批不把它们写成 planned。

**最推荐的 5 款**（按“可复用框架 + 可断言数据面 + 冲突可控”排序）：

1. `pahub-v21`（U040-B-V21）— 与 batch5 `pahub-v20`/`pahub` 同 PCA9548A
   1-byte mask 语义，只多 DIP 地址 0x70–0x77；复用已实现的 `CONTROL_PAHUB`。
2. `gps-v11`（U032-V11）— 与已实现 `gps` 同 unit/gps.py NMEA 解码；AT6668
   只扩星座/更新率，UART RX fixture 可复用 batch4 GPS 模式。
3. `lcd`（U120）— 页面给出完整 I2C 命令表（READ_ID/READ_BUFCOUNT/FILLRECT/
   CASET/RASET/WRITE_RAW/RLE/CHANGE_ADDR），是显示类里数据面最可断言的款；
   QEMU 可做 I2C 命令 slave + framebuffer/bufcount。
4. `gps-sma`（U190）— 与 GPS v1.1 同 AT6668/NMEA，仅外部有源天线不同；
   共享 GPS responder，只记录天线/灵敏度边界。
5. `mini-can`（U179）— 与 batch7 `can` 同 m5can/TWAI 路径，非隔离 TJA1051
   只差电气；QEMU cores3 已有 `esp32s3.twai` + `m5_can_bus_create`。

主要 unresolved/冲突：

- **显示地址三连冲突**：OLED U119 页面 `0x3C` vs 驱动默认 `0x3D`；MiniOLED
  U166 页面 `0x3C` vs 驱动 `0x3D`；LCD U120 页面 `0x3E` vs 驱动 `0x3D`。
  三者还互相冲突（同总线只能挂一个），Glass2 默认 `0x3C` 可焊 `0x3D`，
  页面产品对比表却写“固定 0x3D”，与描述/规格矛盾。
- **GPS 波特率冲突**：GPS v1.1 与 GPS SMA 页面都写默认 **115200 8N1**，冻结
  `unit/gps.py:30/39` 硬编码 **9600**；AT6668 模块可能支持自动波特率或页面
  按新固件写，必须实测/证据钉，不能假设。
- **LoRaWAN-US915 驱动/产品错配**：产品是 STM32WLE5（RAK3172）LoRaWAN 1.0.3，
  `unit/lorawan.py:13` 却继承 `driver.asr650x.LoRaWAN_470`（ASR6501）；驱动内
  有 `LoRaWAN_915` 类但 Unit 包装未使用。AT 命令/响应兼容性未验证。
- `lora-e220-920`：产品 E220-900T22S(JP)/LLCC68 920MHz，驱动
  `unit/lora_e220_jp.py` 用 9600 波特率与 0xC0/C1 配置帧；页面未写波特率，
  433/920 两个驱动的寄存器位定义不同，不能把 batch5 433 结果转授 920。
- `nbiot-cn`：SIM7020C 与 batch5 `nbiot2`（SIM7028）AT 集相近但不同；固件/
  URC/入网顺序 unresolved，CN 频段与运营商认证 NOT RUN。
- `mini-can`：CAN 帧不经 UART；Unit attachment/CAN 帧注入仍是 batch7 的
  unresolved 项；非隔离 TJA1051 与隔离 CA-IS3050G 的电气/终端差异 NOT RUN。
- `mic`：**public UIFlow2 无 Unit MIC 驱动**；只有模拟/数字两路输出，guest 需
  直接 `machine.ADC`/`Pin`。模拟声学、阈值电位器/比较器、灵敏度与频率响应
  NOT RUN；只能断言 ADC fixture 与比较器 GPIO 电平。
- `pahub-v21`：下游 bus 转发/嵌套 hub 与 batch5 一样 **NOT modeled**；A0-A2
  DIP 地址 0x70–0x77 与 pahub-v20/pahub/env-iii 冲突。

## 1. 方法与纪律

- 只信官方页面 + 冻结驱动源码 + M5Unified 组合源码；寄存器/地址/命令必须有
  `file:line` 或页面命令表出处；页面与驱动冲突时两边都记录并标 unresolved。
- 不运行 QEMU；QEMU 建议只描述控制器/模型复用位置，不代表已实现。
- 每款都给出 fixture/注入、可断言数据面、QEMU 复用/新增建议、风险与冲突。
- catalog 草稿只写 `planned`，不升级 runtime/profile，不产生 evidence。

## 2. 总线与控制器复用

| 总线 | 本批 Unit | QEMU 复用 | 新增 |
| --- | --- | --- | --- |
| I2C | pahub-v21、lcd、oled、mini-oled、glass2 | `0123/0125/0130/0139-0141` 的 Unit I2C slave 框架；batch5 `CONTROL_PAHUB`；M5Unified external display 组合 | pahub 地址 0x70–0x77；LCD I2C 命令/framebuffer slave；OLED/MiniOLED/Glass2 显示命令/面板模型或组合 lane |
| UART | gps-v11、gps-sma、nbiot-cn、lora-e220-920、lorawan-us915 | `0139` `lora-e220-433`/`nbiot2` UART TX 捕获 + idle-gap fixture 注入；batch4 `gps` NMEA 模式 | AT6668 NMEA/波特率 fixture；SIM7020 AT 表；JP 920 0xC0/C1 配置；LoRaWAN 915 AT/驱动错配 |
| GPIO/RMT/ADC/CAN | mini-can、mic | canonical `hw/net/can/esp32s3_twai.c`/`esp32_twai.c` + cores3 `m5_can_bus_create`；`hw/m5stopwatch/esp32s3_sens.c` ESP32-S3 SENS/SAR-ADC 兼容模型；GPIO matrix 数字输入 | CAN attachment/frame fixture；ADC channel fixture + comparator GPIO input；MIC 无 Unit 驱动 |

QEMU 控制器事实（canonical `75f1d24`）：

- `hw/net/can/esp32s3_twai.c` 实现 `esp32s3.twai`（SJA1000/CanBusState），
  `hw/xtensa/esp32s3.c:501-514` 已在 cores3 realize 并连接
  `m5_can_bus_create()`；`hw/net/can/esp32_twai.c` 为 ESP32 版本。batch7 `can`
  研究已给出 Unit attachment/CAN 帧注入建议，Mini CAN 只差非隔离收发器。
- `hw/m5stopwatch/esp32s3_sens.c` 是 ESP32-S3 SENS/SAR-ADC 兼容模型，提供中性
  ADC 采样（不承诺校准精度）；MIC 的数字比较器走 GPIO 输入，模拟输出走 SAR-ADC
  通道 fixture。
- 显示类：M5Unified `mpy_m5unified.cpp:206-320` 通过
  `M5.addDisplay(i2c, addr, {"unit_oled"/"unit_lcd"/"unit_mini_oled"/
  "unit_glass2"})` 把外部屏纳入组合；LCD 的 ESP32-PICO 内部固件另有完整 I2C
  命令协议（页面 §4.2），OLED/MiniOLED/Glass2 是 SSD1309/SH1107/SSD1315 命令流。

## 3. 地址/端口冲突与优先级建议

- **I2C 显示地址**：0x3C/0x3D/0x3E 被 OLED、MiniOLED、Glass2、LCD 与
  M5Unified 内置面板共享；同总线只能挂一个，必须按 SKU/驱动地址逐款核对。
- **0x70-0x77**：PaHub v2.1 DIP 可选地址，与 PaHub v2.0/PaHub/env-iii 冲突；
  下游设备只能经 mask 通道访问，QEMU 当前一 attachment 一 bus。
- **UART PORT.C**：gps-v11/gps-sma/nbiot-cn/lora-e220-920/lorawan-us915 与
  已登记 gps/catm/lora/zigbee/nbiot2/rs485-iso/midi 等共享；一次一个。
- **GPIO/CAN PORT.C**：Mini CAN 的 CAN_TX/RX 与 UART Unit 复用同一 pins，
  但走 TWAI 而非 UART，需要 CAN attachment lane；不能映射成 UART responder。
- **PORT.B**：MIC 黄=数字/白=模拟两线，与 RMT/UART/GPIO Unit 冲突；同端口
  只能一个。

建议实现顺序：`pahub-v21` → `gps-v11` → `gps-sma` → `lcd` → `mini-can` →
`oled` → `mini-oled` → `glass2` → `nbiot-cn` → `lora-e220-920` →
`lorawan-us915` → `mic`。

## 4. 逐款协议研究

### 4.1 `pahub-v21` — Unit PaHub v2.1（U040-B-V21）

- 官方页面：https://docs.m5stack.com/en/unit/Unit-PaHub%20v2.1（U040-B-V21，
  5V，PORT.A 黄=SDA 白=SCL）。PCA9548AP，**I2C 0x70–0x77（默认 0x70）**，
  DIP 地址真值表见页面；6 个扩展 Grove 端口，可级联。
- 官方驱动：`unit/pahub.py:21` `PAHUB_DEFAULT_ADDR=0x70`；`:24-46`
  `PAHUBUnit`：`select_channel(channel)` 读 1B mask → OR `(1<<channel)` → 写回；
  `release_channel` 同理 AND 取反；`:48-` `scan/start/stop/readinto/write/
  readfrom/writeto` 等代理方法在每次访问前后 select/release。
- 与 batch5 `pahub-v20` 的关系：同 PCA9548A 1-byte mask 语义；v21 增加 DIP
  地址 0x70–0x77（v2.0 固定 0x70），协议不变。
- Fixture/注入：无需 host fixture；guest select/release 产生 mask；QOM
  `channel-mask`/`channel-writes`/`i2c-address`。
- QEMU 复用：`0139-unit-batch5b.patch` 的 `CONTROL_PAHUB`（0x70，1-byte mask
  read/write）直接复用；新增地址范围/DIP fixture（0x70–0x77），仍不建模下游。
- 可断言：mask 序列、writes≥N、i2c-address；下游 bus/嵌套 hub NOT modeled。
- 风险/冲突：0x70–0x77 与 pahub-v20/pahub/env-iii 冲突；A0-A2 DIP、PCA9548A
  8 vs 6 通道曝光、电气 NOT RUN。
- 复杂度：低；推荐优先级：高。

### 4.2 `lcd` — Unit LCD（U120）

- 官方页面：https://docs.m5stack.com/en/unit/lcd（U120，5V，PORT.A 黄=SDA
  白=SCL）。1.14" 135×240 ST7789V2 + 内置 ESP32-PICO 控制核；**I2C @0x3E**
  （页面规格/描述），最高 400kHz，初始 7-bit 0x3E，可用 CHANGE_ADDR 修改。
- 官方驱动：`unit/lcd.py:11-40` `LCDUnit(i2c, address=0x3D, freq=400000)` →
  `M5.addDisplay(i2c, address, {"unit_lcd": True})`；实际绘制/命令由 M5Unified
  external display 路径（`mpy_m5unified.cpp:232` 附近）执行。**驱动默认
  0x3D 与页面 0x3E 冲突**。
- I2C 命令协议（页面 Protocol，关键项）：`READ_ID 0x04 → [0x77,0x89,major,
  minor]`；`READ_BUFCOUNT 0x09 → remaining buffer`；`FILLRECT 0x68`（Xl,Yt,
  Xr,Yb 4B）及 `FILLRECT_8/16/24/32 0x69/0x6A/0x6B/0x6C`；`DRAWPIXEL
  0x60..0x64`；`CASET 0x2A`/`RASET 0x2B`；`WRITE_RAW_8/16/24/32
  0x41/0x42/0x43/0x44`（变长，直到 STOP）；`WRITE_RLE_* 0x49..0x4D`；
  `SET_COLOR_* 0x51..0x54`；`BRIGHTNESS 0x22`；`ROTATE 0x36`；`SET_POWER
  0x38`；`SET_SLEEP 0x39`；`COPYRECT 0x23`；`RAM_FILL 0x50`；
  `CHANGE_ADDR 0xA0`（新地址+反码+0xA0）；NOP 0x00/未定义命令忽略到 STOP。
- Fixture/注入：无 host sensor fixture；guest 通过 `display.fill()/print()`
  产生命令流；QOM 建议 `command-hex`、`framebuffer`、`read-id`、
  `bufcount`、`i2c-address`。
- QEMU 复用：新增 `CONTROL_UNIT_LCD` I2C slave：解析命令表、READ_ID/
  READ_BUFCOUNT、FILLRECT/CASET/RASET/WRITE_RAW 更新 framebuffer 与 bufcount；
  复用 `m5_unit_i2c_controls.c` pointer/transaction 框架。M5Unified 的
  external display 组合需要 guest 能识别 `unit_lcd` 并走该命令流。
- 可断言：guest `M5.addDisplay` 成功、READ_ID=0x77/0x89 版本、fill 后
  framebuffer rect/颜色、bufcount 递减、ROTATE/BRIGHTNESS 写；显示组合
  （framebuffer 最终上屏）与真实 ST7789V2 光学 NOT RUN。
- 风险/冲突：页面 0x3E vs 驱动 0x3D；0x3C/0x3D 与 OLED/MiniOLED/Glass2
  冲突；ESP32-PICO 内部固件版本/升级、buffer 溢出策略、RGB666 物理色 NOT RUN。
- 复杂度：中；推荐优先级：高。

### 4.3 `oled` — Unit OLED（U119）

- 官方页面：https://docs.m5stack.com/en/unit/oled（U119，5V，PORT.A 黄=SDA
  白=SCL）。1.3" 128×64 SH1107，黑/白；页面 **I2C @0x3C**。
- 官方驱动：`unit/oled.py:11-38` `OLEDUnit(i2c, address=0x3D, freq=400000)` →
  `M5.addDisplay(i2c, address, {"unit_oled": True})`；驱动默认 **0x3D** 与页面
  0x3C 冲突。SH1107 命令由 M5Unified 外部屏驱动（`driver/sh1107.py` 提供
  controller 常量，`M5.addDisplay` 走组合配置）。
- 协议要点（SH1107，`driver/sh1107.py:12-32`）：SET_CONTRAST 0x81、
  SET_ENTIRE_ON 0xA4、SET_NORM_INV 0xA6、SET_DISP 0xAE、SET_MEM_MODE 0x20、
  SET_PAGE_ADDR 0xB0、SET_COL_LO/HI 0x00/0x10、SET_DISP_START_LINE 0xDC、
  SEG_REMAP 0xA0、MUX 0xA8、COM 0xC0、OFFSET 0xD3、CLK_DIV 0xD5、
  PRECHARGE 0xD9、VCOM 0xDB；128×64 用 page mode=False。
- Fixture/注入：无 host fixture；guest 绘制产生 I2C 命令/像素流。QOM 建议
  `command-hex`、`panel-framebuffer`、`i2c-address`。
- QEMU 复用：显示组合/命令 slave；无 Unit 数据面 QOM 时只能记录命令流。
  与 LCD 不同，OLED 没有页面级完整寄存器表，M5Unified 外部屏组合是主要入口。
- 可断言：guest addDisplay 成功、命令流包含 DISP/COL/PAGE/像素、i2c 地址。
- 风险/冲突：0x3C vs 驱动 0x3D；与 MiniOLED/Glass2/LCD 冲突；OLED 面板光学/
  亮度/寿命 NOT RUN；Unit 无独立 QOM 状态 → 显示组合 lane 局限。
- 复杂度：中；推荐优先级：中。

### 4.4 `mini-oled` — Unit Mini OLED（U166）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Mini_OLED（U166，PORT.A
  黄=SDA 白=SCL）。0.42" 72×40 单色白，SSD1315，**I2C @0x3C**。
- 官方驱动：`unit/minioled.py:11-38` `MiniOLEDUnit(i2c, address=0x3D,
  freq=400000)` → `M5.addDisplay(i2c, address, {"unit_mini_oled": True})`；
  驱动 0x3D vs 页面 0x3C 冲突。
- 协议：SSD1315 OLED 命令流（M5Unified 外部屏组合；72×40 单色）；无页面
  寄存器表，命令/像素由组合驱动发出。
- Fixture/注入/QOM：同 OLED；建议 command-hex/framebuffer/i2c-address。
- QEMU 复用：显示组合 lane；若做 I2C slave，只需命令/像素记录。
- 可断言：guest addDisplay、命令流、面板尺寸 72×40。
- 风险/冲突：0x3C vs 0x3D；与 OLED/Glass2/LCD 冲突；SSD1315 光学 NOT RUN。
- 复杂度：中；推荐优先级：中。

### 4.5 `glass2` — Unit Glass2（U158-B）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_Glass2（U158-B，5V，
  PORT.A 黄=SDA 白=SCL）。1.51" 透明 OLED 128×64 SSD1309；默认 **0x3C**，
  可焊 0x3D；页面产品对比表却写“固定 0x3D”，与描述/规格矛盾（unresolved）。
- 官方驱动：`unit/glass2.py:11-41` `Glass2Unit(i2c, address=0x3C,
  freq=400000)` → `M5.addDisplay(i2c, address, {"unit_glass2": True})`；
  驱动默认 0x3C，与对比表冲突、与描述一致。
- 协议：SSD1309 命令流（128×64 单色，透明区 128×56）；两个 Grove 口互通。
- Fixture/注入/QOM：同 OLED；建议 command-hex/framebuffer/i2c-address。
- QEMU 复用：显示组合 lane；0x3C/0x3D 两地址需按配置选择。
- 可断言：guest addDisplay、命令流、透明区尺寸。
- 风险/冲突：页面自相矛盾（0x3C 默认/可改 vs 对比表固定 0x3D）；与
  OLED/MiniOLED/LCD 冲突；透明 OLED 光学/亮度 NOT RUN。
- 复杂度：中；推荐优先级：中。

### 4.6 `gps-v11` — Unit GPS v1.1（U032-V11）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_GPS_v1.1（U032-V11，5V，
  PORT.C 黄=UART_RX 白=UART_TX）。AT6668/ATGM336H-6N，多星座
  GPS/QZSS/BD2/BD3/GAL/GLO，**UART 默认 115200 8N1**，NMEA0183 4.1，
  50 通道，更新率最高 10Hz。
- 官方驱动：`unit/gps.py:14-42` `GPSUnit(id, port)`：UART `port[1]=tx,
  port[0]=rx`，`uart.init(9600, ...)`（`:30`/`:39`）——**冻结驱动 9600 与页面
  115200 冲突**；`decode_gga`/`decode_rmc`/`decode_vtg`（`:44-101`）解析
  `$GNGGA/$GNRMC/$GNVTG`，字段含 UTC、经纬、fix quality、卫星数、海拔、
  速度/航向；`_monitor` 逐行累积 NMEA。
- Fixture/注入：`nmea-lines`（`$GNGGA,...`/`$GNRMC,...`/`$GNVTG,...` fixture，
  按 9600 或 115200 用证据钉）；QOM 输出 `latitude/longitude/altitude-m/
  speed-kph/course-deg/fix-mode/satellites/nmea-hex`。
- QEMU 复用：batch4 `gps` 已实现的 UART RX/NMEA 模式 + 0139 UART TX/RX
  responder；AT6668 只改 talker/星座/更新率，NMEA 语法兼容。波特率必须由
  证据选择 9600 vs 115200。
- 可断言：guest `latitude/longitude/altitude/speed_kph/course/satellite_num`
  与 fixture 一致；NMEA 行字节；fix quality。
- 风险/冲突：页面 115200 vs 驱动 9600 unresolved；GNSS 天线/多频/灵敏度/
  定位精度/冷启动时间 NOT RUN；PORT.C 与其它 UART Unit 冲突。
- 复杂度：中低；推荐优先级：高。

### 4.7 `gps-sma` — Unit GPS SMA（U190）

- 官方页面：https://docs.m5stack.com/en/unit/Unit-GPS%20SMA（U190，5V，
  PORT.C 黄=UART_RX 白=UART_TX）。AT6668/ATGM336H，多星座，**UART 默认
  115200 8N1**，NMEA0183 4.1；外置有源 SMA 天线（30dBi，1555–1580MHz）。
- 官方驱动：与 GPS v1.1 共用 `unit/gps.py`（同一 GPSUnit/9600 硬编码）；
  `decode_gga/rmc/vtg` 相同。页面明确 GPS SMA 与 GPS v1.1 同芯片，仅天线
  形态不同。
- Fixture/注入：同 4.6（NMEA fixture）；QOM 输出同。
- QEMU 复用：同 4.6；外置天线差异不进入数字模型，只做边界记录。
- 可断言：同 4.6；额外记录“外置有源天线”产品字段。
- 风险/冲突：页面 115200 vs 驱动 9600；GPS SMA 与 v1.1 结果可互相参考但
  不转授；GNSS RF/天线增益/定位 NOT RUN；PORT.C 冲突。
- 复杂度：中低；推荐优先级：高。

### 4.8 `nbiot-cn` — Unit NBIoT-CN（U112）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_NBIoT-CN（U112，5V，
  PORT.C 黄=UART_RX 白=UART_TX）。SIM7020C，Cat-NB CN B1/B3/B5/B8，
  **UART 115200bps**，AT 控制，SMA 外置天线；TCP/UDP/LWM2M/CoAP/MQTT/
  HTTP/HTTPS/TLS/DTLS/DNS/NTP/PING 等。
- 官方驱动：`unit/nbiot.py:17-26` `NBIOTUnit(SIM7020)`：UART 115200，
  `check_modem_is_ready()`（`driver/simcom/common.py:58-62`，AT→OK，repeat），
  `set_command_echo_mode(0)`（`:64-68`，ATE0）；SIM7020 驱动
  `driver/simcom/sim7020.py`：`AT+CGSN`、`AT+CCID`、`AT+CGACT`/`AT+CGACT?`、
  `AT+CGCONTRDP`、`AT+CMQNEW/CMQCON/CMQSUB/CMQPUB`、`AT+CHTTPCREATE/...` 等。
- Fixture/注入：`responses-hex`（`;` 分隔 AT 响应 chunk，UART idle-gap 注入，
  复刻 batch5 nbiot2）；QOM `tx-hex`/`responses-hex`/`frames-sent`/
  `frames-injected`。
- QEMU 复用：`0139-unit-batch5b.patch` 的 UART TX/RX responder + SIM7028
  nbiot2 命令表；新增 SIM7020 差异（CMQ*/CHTTP* 命令名/响应）与 CN 频段。
- 可断言：guest 构造成功（AT/ATE0）、`get_imei_number`/`get_ccid_number`/
  `get_network_ip` 等 fixture 值；QOM tx-hex 含 AT/ATE0/CMQ* 字节。
- 风险/冲突：SIM7020C AT 固件/URC/入网顺序 unresolved；NB-IoT RF/网络/SIM/
  运营商认证/TLS/MQTT NOT RUN；PORT.C 与其它 UART Unit 冲突。
- 复杂度：中；推荐优先级：中。

### 4.9 `lora-e220-920` — Unit LoRaE220-920（U170）

- 官方页面：https://docs.m5stack.com/en/unit/LoRaE220-JP%20Unit（U170，5V，
  PORT.C 黄=UART_RX 白=UART_TX）。E220-900T22S(JP)/LLCC68，920.6–928.0MHz，
  最大 13dBm，4 种 DIP 工作模式（Transmit/Receive、WOR Transmit、WOR
  Receive、Configuration）；串口通信，P2P/广播/WOR/载波监听。
- 官方驱动：`unit/lora_e220_jp.py:12` `LoRaE220JPUnit`；
  `:79-92` 构造 UART（`port[1]=tx, port[0]=rx`，`init(9600, ...)`）；
  `:94-175` `setup(own_address, own_channel, encryption_key, air_data_rate,
  subpacket_size, rssi_ambient_noise_flag, transmitting_power, rssi_byte_flag,
  transmission_method_type, lbt_flag, wor_cycle)` 组 0xC0 配置帧并等长回显；
  `:196-220` `receive(timeout)`；`:222-240` `send(target_address,
  target_channel, data)` 组 `>HB + payload` 发送帧。
- Fixture/注入：`responses-hex`（发送后 idle-gap 注入 RX bytes）；QOM
  `tx-hex`/`config-hex`/`frames-sent`/`frames-injected`（同 batch5 lora）。
- QEMU 复用：0139 `lora-e220-433` 的 UART TX 捕获 + 0xC0/C1 配置/回显 +
  idle fixture；920 仅改频段/功率/信道/寄存器位，需新 SKU 参数，不能把 433
  证据转授 920。
- 可断言：guest `setup` 返回 True（等长回显）、config bytes、
  `send` 帧 tx-hex、注入 fixture 的 `receive`。
- 风险/冲突：页面未写波特率（驱动 9600）；920MHz RF/天线/距离/功率/
  Telec 认证 NOT RUN；PORT.C 与其它 UART Unit 冲突。
- 复杂度：中；推荐优先级：中。

### 4.10 `lorawan-us915` — Unit LoRaWAN-US915（U184-US915）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_LoRaWAN-US915
  （U184-US915，5V，PORT.C 黄=UART_RX 白=UART_TX）。STM32WLE5/RAK3172，
  LoRaWAN 1.0.3 Class A/B/C，US915 902–928MHz，OTAA/ABP/P2P，
  **UART 默认 115200**，AT 控制。
- 官方驱动：`unit/lorawan.py:13-22` `LoRaWANUnit(LoRaWAN_470)`：
  `super(LoRaWAN_470, self).__init__(tx=port[1], rx=port[0])`；实际实现是
  `driver/asr650x.py:14` `LoRaWAN_Asr650x`（ASR6501 平台，115200 AT）；
  驱动内已有 `LoRaWAN_915`（`:906`）/`LoRaWAN_868`（`:918`）子类，但 Unit
  包装未使用。**产品 STM32WLE5/RAK3172 vs ASR650x 驱动错配 unresolved**。
- 典型 AT：`AT+CGSN?`、`AT+CDEVADDR?/=`、`AT+CDEVEUI?/=`、`AT+CAPPEUI?/=`、
  `AT+CAPPKEY?/=`、`AT+CAPPSKEY?/=`、`AT+CNWKSKEY?/=`、`AT+CJOINMODE?/=`、
  `AT+CFREQBANDMASK?/=`、`AT+CULDLMODE?/=`、`AT+CWORKMODE?/=`、
  `AT+CCLASS?/=` 及 join/send（行号见 `driver/asr650x.py` 各方法）。
- Fixture/注入：`responses-hex`（AT 响应 chunk）；QOM `tx-hex`/
  `join-status`/`dev-addr`/`dev-eui`/`app-eui`/`frames-*`。
- QEMU 复用：batch7 `lorawan-cn470` 的 UART responder；新增 US915 频段
  配置/channel mask；驱动/产品错配必须用真实响应证据钉。
- 可断言：guest 配置/读取 DevAddr/DevEUI/AppEUI/AppKey；join 请求字节；
  join-status fixture；只做 AT/字节层。
- 风险/冲突：STM32WLE5 vs ASR650x 驱动错配；OTAA/ABP、Join/Accept、US915
  频段/占空比/FCC 认证、RF/天线 NOT RUN；PORT.C 冲突。
- 复杂度：中高；推荐优先级：中。

### 4.11 `mini-can` — Unit Mini CAN（U179）

- 官方页面：https://docs.m5stack.com/en/unit/Unit-Mini%20CAN（U179，5V，
  PORT.C 黄=CAN_TX 白=CAN_RX）。TJA1051T/3 非隔离 CAN 收发器，
  ISO11898-2:2016 / SAE J2284，最高 1Mbit/s，HT3.96 9–24V 或 Grove 5V，
  DC-DC 输入；板载 120Ω 可拆。
- 官方驱动：`unit/can.py:8-34` `CANUnit(CAN)`（`from m5can import CAN`）；
  `:35` `MiniCANUnit = CANUnit`；timing_table 25k/50k/100k/125k/250k/500k/
  800k/1M → (prescaler,sjw,bs1,bs2,triple_sampling)；`super().__init__(0,
  mode, port[1], port[0], ...)`。
- C 模块：`m5stack/cmodules/m5can/modcan.c`：`init(mode, prescaler, *, sjw,
  bs1, bs2, triple_sampling)`、`send/recv/any/state/info/setfilter/
  clearfilter`；CAN_NORMAL/NO_ACKNOWLEDGE/LISTEN_ONLY；标准 11-bit/扩展
  29-bit 帧（同 batch7 can）。
- Fixture/注入：`rx-frames`（host 注入 CAN 帧）；QOM `tx-frames`/
  `rx-frames`/`frames-sent`/`frames-received`/`can-state`。
- QEMU 复用：canonical `esp32s3.twai` + cores3 `m5_can_bus_create()`（见
  batch7 can）；非隔离 TJA1051 与隔离 CA-IS3050G 只差电气，CAN 帧数据面相同。
- 可断言：guest send → QOM/host CAN bus 收到同 id/data；host 注入 → guest
  recv；BTR/波特率表；标准/扩展帧、RTR、过滤器。
- 风险/冲突：CAN attachment/QOM frame fixture 仍是 unresolved；非隔离/终端/
  差分电平/总线仲裁/错误帧/真实负载 NOT RUN；PORT.C 与 UART Unit 复用 pins。
- 复杂度：中；推荐优先级：中。

### 4.12 `mic` — Unit MIC（U096）

- 官方页面：https://docs.m5stack.com/en/unit/mic（U096，5V，PORT.B
  **黄=Digital Output、白=Analog Output**）。MAX4466 麦克风前置放大 +
  LM393 比较器 + 10K 阈值电位器；模拟/数字两路输出；灵敏度 52dB、
  SNR 40dB；全向 electret。
- 官方驱动：**public UIFlow2 无 Unit MIC 驱动**（`unit/` 下无 mic.py）；
  UIFlow 示例直接 `machine.ADC` 采样白线模拟输出、`Pin` 读黄线比较器。
  这是本批的显式 **unit-driver-gap**。
- 协议/数据面：无寄存器；白线是连续模拟电压（声音波形/包络），黄线是
  LM393 比较器数字输出（阈值由电位器设定，声音过阈翻转）。主机侧
  ESP32-S3 SAR-ADC 采样白线；黄线走 GPIO 数字输入。
- Fixture/注入：`analog-mv`（0–3300mV 采样 fixture）、`comparator-level`
  （黄线数字电平 fixture）；QOM 建议 `analog-mv`/`digital-level`/
  `samples`/`sample-rate`。
- QEMU 复用：canonical `hw/m5stopwatch/esp32s3_sens.c` ESP32-S3 SENS/SAR-ADC
  兼容模型（中性 ADC 采样）+ GPIO matrix 数字输入；新增 Unit-level ADC
  channel fixture/comparator input，无需 I2C/UART 模型。
- 可断言：guest `machine.ADC` 读回 fixture mV（量化范围内）、`Pin.value()`
  随 comparator fixture 变化；QOM samples；声学/麦克风物理 NOT RUN。
- 风险/冲突：无官方 Unit 驱动（只能走 machine.ADC/Pin）；模拟/数字两线
  与 PORT.B 其它 Unit 冲突；52dB/SNR/频率响应/阈值电位器/声学 NOT RUN；
  ADC 校准/噪声不建模。
- 复杂度：中；推荐优先级：中。

## 5. catalog 草稿

`2026-11-03-batch8-catalog-draft.json` 含 12 条 `planned` 草稿，字段与
batch1-7 一致：`id/name/sku/visual_asset/official_docs/checked_at/chips/
interface/protocol/inputs/outputs/evidence/research_status/model_status/runtime/
blocker/limitations`。`runtime.status` 全部 `planned`，`model_status` 全部
`planned`；不写 evidence/PASS，不升级 profile。

草稿要点：

- I2C 地址冲突写成 `blocker`/`limitations`，不替产品选地址（OLED/MiniOLED/
  Glass2/LCD 的 0x3C/0x3D/0x3E）。
- 显示类（lcd/oled/mini-oled/glass2）标 `display-composition`：LCD 有页面级
  完整命令表可做 I2C slave；其余三款依赖 M5Unified external display 组合，
  Unit 数据面 QOM 有限。
- GPS v1.1/SMA 标页面 115200 vs 驱动 9600 `unresolved`；LoRaWAN-US915 标
  STM32WLE5 vs ASR650x 驱动错配；lora-e220-920 标 920MHz 不可转授 433。
- mini-can 标 CAN attachment/frame injection unresolved；mic 标
  `no-official-unit-driver`，数据面只能 machine.ADC/Pin。
- 所有 RF/光学/声学/显示物理语义写 `NOT RUN`，不写 simulated。

## 6. unresolved 汇总

| Unit | unresolved | 影响 |
| --- | --- | --- |
| `lcd` | 页面 0x3E vs 驱动 0x3D；内部 ESP32-PICO 固件版本/命令缓冲 | 地址/实现需证据 |
| `oled` | 页面 0x3C vs 驱动 0x3D；显示组合无 Unit QOM | 地址/显示 lane |
| `mini-oled` | 页面 0x3C vs 驱动 0x3D；SSD1315 命令 | 地址/显示 lane |
| `glass2` | 描述默认 0x3C/可焊 0x3D vs 对比表“固定 0x3D”；驱动 0x3C | 地址二义 |
| `gps-v11`/`gps-sma` | 页面 115200 vs 驱动 9600 | 波特率必须实测 |
| `nbiot-cn` | SIM7020C AT 固件/URC/入网顺序 | 只能 fixture AT |
| `lora-e220-920` | 驱动 9600/920 配置位；页面未写波特率 | 不能沿用 433 结果 |
| `lorawan-us915` | STM32WLE5/RAK3172 vs ASR650x 驱动 | AT 兼容性未验证 |
| `mini-can` | CAN attachment/帧注入；非隔离电气 | 需新 attachment lane |
| `mic` | 无 Unit 驱动；ADC/comparator 物理 | 只能 machine.ADC/Pin |
| `pahub-v21` | 下游 bus/嵌套 hub 不建模；0x70–0x77 冲突 | 只断言 mask |
| 多个 | 0x3C/0x3D/0x3E、0x70–0x77、PORT.B/C 复用 | 一总线一 Unit |

## 7. 引用与复现

- 官方产品页（均于 2026-11-03 抓取）：`Unit-PaHub v2.1`、`Unit_GPS_v1.1`、
  `Unit-GPS SMA`、`Unit_NBIoT-CN`、`LoRaE220-JP Unit`、`Unit_LoRaWAN-US915`、
  `oled`、`lcd`、`Unit_Mini_OLED`、`Unit_Glass2`、`Unit-Mini CAN`、`mic`；
  官方 I2C 地址索引 `product_i2c_addr`。
- 驱动源码（冻结树 HEAD `528edd8`）：`unit/pahub.py`、`unit/lcd.py`、
  `unit/oled.py`、`unit/minioled.py`、`unit/glass2.py`、`unit/gps.py`、
  `unit/nbiot.py`、`unit/lora_e220_jp.py`、`unit/lorawan.py`、`unit/can.py`；
  `driver/sh1107.py`、`driver/asr650x.py`、`driver/simcom/sim7020.py`、
  `driver/simcom/common.py`、`m5stack/cmodules/m5can/modcan.c`；
  M5Unified `components/M5Unified/mpy_m5unified.cpp` external display 组合。
- QEMU 只读坐标：`hw/net/can/esp32s3_twai.c`、`hw/net/can/esp32_twai.c`、
  `hw/xtensa/esp32s3.c:501-514`、`hw/m5stopwatch/esp32s3_sens.c`；
  Unit 模型层参考 `patches/qemu-m5stack-peripherals/0123/0125/0130/0139-0144`。
- 未运行 QEMU、未改 catalog/runtime/测试；raw 证据不涉及。

## 8. 抓取记录

| 页面 | URL | 用途 |
| --- | --- | --- |
| PaHub v2.1 | https://docs.m5stack.com/en/unit/Unit-PaHub%20v2.1 | PCA9548AP、0x70–0x77 |
| GPS v1.1 | https://docs.m5stack.com/en/unit/Unit_GPS_v1.1 | AT6668、115200、NMEA |
| GPS SMA | https://docs.m5stack.com/en/unit/Unit-GPS%20SMA | AT6668、外置天线 |
| NBIoT-CN | https://docs.m5stack.com/en/unit/Unit_NBIoT-CN | SIM7020C、115200 |
| LoRaE220-920 | https://docs.m5stack.com/en/unit/LoRaE220-JP%20Unit | E220-900T22S JP、920MHz |
| LoRaWAN-US915 | https://docs.m5stack.com/en/unit/Unit_LoRaWAN-US915 | STM32WLE5、115200 |
| OLED | https://docs.m5stack.com/en/unit/oled | SH1107、0x3C |
| LCD | https://docs.m5stack.com/en/unit/lcd | ST7789V2、0x3E、命令表 |
| Mini OLED | https://docs.m5stack.com/en/unit/Unit_Mini_OLED | SSD1315、0x3C |
| Glass2 | https://docs.m5stack.com/en/unit/Unit_Glass2 | SSD1309、0x3C/0x3D |
| Mini CAN | https://docs.m5stack.com/en/unit/Unit-Mini%20CAN | TJA1051、1Mbps |
| MIC | https://docs.m5stack.com/en/unit/mic | 模拟/数字输出、无 Unit 驱动 |
| I2C index | https://docs.m5stack.com/en/product_i2c_addr | 各芯片 7-bit 地址 |

以上为研究结论，不构成实现/证据承诺；下一批实现前需重新核对驱动树 HEAD
与产品页地址，特别是显示地址（0x3C/0x3D/0x3E）与 GPS 波特率（9600/115200）。

## 9. 首批 5 款实现状态（补丁 0146）

日期：`2026-11-02`。实现任务 `task-50`，分支 `m5agent/units16`（base `origin/main 0578b162`，catalog
111 款）。

**补丁与 base**

- 补丁：`patches/qemu-m5stack-peripherals/0146-unit-batch8a.patch`（sha256 `5b7d6ee1…`，
  在 canonical 链上 `git apply --check` 通过）。
- canonical 链：`75f1d24` → `0120`-`0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132`
  → `0137` → `0138` → `0139` → `0140` → `0141` → `0142` → `0143` → `0144`；本补丁是 `0120`
  之后的第 26 层。`0145` 由并行 batch-7 剩余实现任务占用，不属于本链；`0147` 为下一个可用号。

**5 款实现与边界**

| Unit | SKU | 状态 | QEMU 模型 | unresolved / NOT RUN |
| --- | --- | --- | --- | --- |
| `pahub-v21` | U040-B-V21 | planned（复用 + DIP fixture） | 复用 `CONTROL_PAHUB`（PCA9548A mask-only）；`dip-address` fixture 建模 0x70-0x77，`channel-mask`/`channel-writes` 读回 | **0x70-0x77 与 pahub/pahub-v20/env-iii 冲突；下游 bus 转发/嵌套 hub、A0-A2 DIP 电气、8-vs-6 通道曝光 NOT RUN** |
| `gps-v11` | U032-V11 | planned（复用 GPS NMEA 路径） | 复用 batch4 `gps` UART RX 注入/NMEA 行路径；`nmea-lines`/`baud` fixture、`injected-lines`/`tx-hex` 观测 | **页面 115200 vs 冻结驱动 9600 unresolved（baud fixture 记录、不选边）；GNSS RF/天线/多星座/精度/冷启动 NOT RUN；PORT.C 共享** |
| `gps-sma` | U190 | planned（同 AT6668 路径） | 同 `gps-v11`（外置有源 SMA 天线只写产品边界，不进数字模型） | **同 115200/9600 unresolved；天线增益/RF/精度 NOT RUN；与 v1.1 结果不得互相转授** |
| `lcd` | U120 | planned（新增命令/framebuffer slave） | 新增 `CONTROL_UNIT_LCD`：READ_ID 0x04→0x77/0x89/版本、READ_BUFCOUNT 0x09、FILLRECT 0x68-0x6C、CASET 0x2A/RASET 0x2B、WRITE_RAW 0x41-0x44、WRITE_RLE 0x49-0x4D、DRAWPIXEL、SET_COLOR、BRIGHTNESS/ROTATE/POWER/SLEEP、CHANGE_ADDR 0xA0 + 135x240 RGB565 framebuffer/bufcount | **页面 0x3E vs 驱动 0x3D unresolved（按驱动 0x3D 建模）；0x3C/0x3D/0x3E 与 OLED/MiniOLED/Glass2 冲突；M5Unified external display 上屏组合、ST7789V2 光学/背光/RGB666、ESP32-PICO 固件 NOT RUN** |
| `mini-can` | U179 | **blocked/DEFER（未实现）** | 无 QEMU 模型：CAN 帧走 m5can/TWAI，Unit attachment/CAN 帧注入在 Unit 运行时未建模（同 batch7 `can` gap），不伪造帧 | **CAN attachment/TWAI frame fixture unresolved；TJA1051 非隔离电气、120Ω 终端、差分电平、仲裁/错误帧、真实负载 NOT RUN** |

**离线 QOM smoke**（S3 `m5atoms3r`，无 guest 固件）：`pahub-v21`/`lcd`/`gps-v11`/`gps-sma` 各 1 个
attachment，QMP `qom-list`/`qom-set`/`qom-get` **20/20 PASS**——pahub DIP 0x70→0x71 地址联动、
channel mask 默认值；GPS baud/nmea-lines 读写与 injected/tx 观测；LCD read-id `77890100`、
bufcount=64800、brightness/power/地址默认与命令/像素计数器属性。smoke 不覆盖 I2C 命令字节语义
（FILLRECT/WRITE_RAW 帧）、guest NMEA 解码或 CAN 帧；这些仍需 guest 证据。

**计数**：catalog 111 → **116**，runtime-profiles 111 → 116；visual mapping audit 5 条 +
`all-116-products` 标记；计数测试（test_unit_runtime / test_serve_api units / visual mapping /
batch3 A+B、batch7 A static marker）与 snapshot 已同步。

**共同边界**：4 款是控制器可见的事务/寄存器模型（`lcd` 为新增最小命令 slave），`mini-can` 明确
blocked；复用模型的既有 NOT RUN 边界不因新 SKU 别名升级。没有 guest 与 Device Service 证据前
不得把任何一款升级为 `implemented`/`simulated`/`validated`。

## 10. 剩余 7 款实现状态（补丁 0148，2026-11-03）

batch8 剩余 7 款（`oled`/`mini-oled`/`glass2`/`nbiot-cn`/`lora-e220-920`/
`lorawan-us915`/`mic`）已由
[`0148-unit-batch8b.patch`](../../patches/qemu-m5stack-peripherals/0148-unit-batch8b.patch)
接入 QEMU 数据面。**base 是 28 层 canonical 链 `81d3065`**（canonical `75f1d24`
+ `0120`-`0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132`
→ `0137` → `0138` → `0139` → `0140` → `0141` → `0142` → `0143` → `0144` →
`0145` → `0146` → `0147`），实现 commit 见补丁 body。**尚未采集 guest/Device
Service 证据**，catalog 7 条与 runtime-profiles 7 条保持 `planned`、hosts 为空；
离线 QOM smoke（S3 board、无 guest 固件）19/19 PASS，只验证属性注册、fixture
读写、范围/只读拒绝与响应器默认值，不构成功能 PASS。

| Unit | 0148 模型 | QOM fixtures/观测 | 显式 blocker/unresolved |
| --- | --- | --- | --- |
| `oled` U119 (0x3D) | 共享 OLED 显示命令 slave（SH1107 128×64）：0x00/0x40 2-wire 控制字节、列/页寻址、1024B framebuffer | contrast/display-on/inverse/start-line、display-controller、commands/data-bytes/pixels-written、framebuffer-crc、last-command-hex | **页面 0x3C vs 驱动 0x3D unresolved（建模驱动地址）；三款显示 Unit 0x3C/0x3D 互斥；M5Unified external display 组合、面板光学/亮度/寿命 NOT RUN** |
| `mini-oled` U166 (0x3D) | 共享 kind（SSD1315 72×40，360B framebuffer） | 同上 | **页面 0x3C vs 驱动 0x3D unresolved；0x3C/0x3D 冲突；SSD1315 小屏光学 NOT RUN** |
| `glass2` U158-B (0x3C) | 共享 kind（SSD1309 128×64） | 同上 | **页面描述默认 0x3C/可焊 0x3D vs 对比表“固定 0x3D”自相矛盾 unresolved（建模驱动 0x3C）；透明区/透过率物理 NOT RUN** |
| `nbiot-cn` U112 (UART) | 共享 UART TX 捕获 + idle-gap fixture responder（不解析 AT） | responses-hex、tx-hex、frames-sent/injected | **SIM7020C AT 固件/URC/入网顺序 unresolved；CN 频段/运营商认证/RF/SIM/TLS/MQTT NOT RUN；PORT.C 冲突** |
| `lora-e220-920` U170 (UART) | 复用 0xC0/C1 配置帧回显 + responder；**920 SKU 独立参数，不转授 433 证据** | responses-hex、tx-hex、config-hex、frames-* | **页面未写波特率（驱动 9600）；920 寄存器位与 433 不同；920MHz RF/天线/距离/Telec 认证 NOT RUN；PORT.C 冲突** |
| `lorawan-us915` U184-US915 (UART) | 最小 AT fixture responder（不解析 AT/Join） | responses-hex、tx-hex、frames-* | **产品 STM32WLE5/RAK3172 vs 冻结 ASR650x 驱动错配 unresolved；US915 join/OTAA/ABP/占空比/FCC/RF NOT RUN；PORT.C 冲突** |
| `mic` U096 (GPIO/ADC) | 白线 SAR-ADC `analog-mv` fixture；黄线 LM393 `comparator-level` GPIO 数字输入 | analog-mv、comparator-level、digital-level、adc-samples | **public UIFlow2 无 Unit MIC 驱动（显式 driver-gap，guest 只能 machine.ADC/Pin）；声学/阈值电位器/灵敏度/SNR/频率响应 NOT RUN；PORT.B 冲突** |

离线 QOM smoke（S3 `m5atoms3r`，无 guest）覆盖 7 个 attachment：3 款显示的
controller/地址默认、fixture 读写与范围拒绝；3 款 UART 的 responses-hex 读写与
frames 默认、lora-e220-920 的 config-hex 默认；mic 的 analog-mv/comparator 联动
与范围拒绝。smoke **不**覆盖 I2C 命令/数据字节语义（显示命令流、framebuffer
写）、UART AT 字节语义或 guest ADC/Pin 路径；这些仍需 guest 证据。

**计数**：catalog 123 → **130**、runtime-profiles 123 → 130；visual mapping
audit 7 条 + `all-130-products` 标记；计数测试与 snapshot 已同步。
