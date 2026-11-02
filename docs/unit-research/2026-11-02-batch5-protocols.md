# Unit 第五批协议研究：12 款未登记 Unit 的驱动证据、复用建议与 unresolved

日期：`2026-11-02`。范围：`products.json` unit 类别中**尚未登记**的 12 款候选
Unit 的官方页面、官方 UIFlow2 驱动逐行证据、QEMU 复用/新增建议、可断言数据面与
风险。本文件只做研究，不修改 catalog/runtime，不运行 QEMU；catalog 草稿见
`2026-11-02-batch5-catalog-draft.json`，全部 `planned`。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 76 款（70 implemented + 6 planned）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..4-protocols.md`（48 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （git HEAD `528edd8`，即 batch1-4 引用的冻结/快照驱动树）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD `75f1d24`）。
- 官方页面在 `2026-11-02` 重新抓取核对（引用见 §8）。

## 0. 结论摘要

本批从剩余**未研究**的 Unit 中选 12 款，覆盖 6 款 I2C、3 款 GPIO/RMT、3 款 UART，
全部可在现有 QEMU 控制器拓扑（SoC I2C、GPIO ADC、RMT、UART）上落地；其中 4 款
可直接复用已实现模型，2 款只需新增寄存器文件，1 款需要新的 UART 应答器模型，
1 款（PaHub）需要多总线/嵌套 hub 框架扩展。

| # | Unit id | SKU | 总线/地址 | 复杂度 | 推荐优先级 |
| --- | --- | --- | --- | --- | --- |
| 4.1 | `pahub-v20` | U040-B | I2C mux `0x70`（0x70–0x77） | 高（多总线） | 中 |
| 4.2 | `pbhub-v11` | U041-B | I2C `0x61` + 6 通道命令空间 | 低（复用 0131） | **高** |
| 4.3 | `8angle` | U154 | I2C `0x43` | 中低（寄存器组） | **高** |
| 4.4 | `kmeter-iso-v11` | U133-V11 | I2C `0x66` | 低 | 中 |
| 4.5 | `rtc` | U126 | I2C `0x51`（PCF8563） | 中（时钟语义） | 中 |
| 4.6 | `tmos-pir` | U185 | I2C `0x5A`（STHS34PF80） | 中 | 中 |
| 4.7 | `rgb-led-10cm` | A035 | RMT/GPIO（15×SK6812） | 低（复用 fader RMT） | **高** |
| 4.8 | `neohex` | A045-B | RMT/GPIO（37×WS2812C） | 低中（无 unit 驱动） | 中 |
| 4.9 | `op90` | U057 | GPIO 数字输入（白线） | 低（复用 limit/pir） | **高** |
| 4.10 | `lora-e220-433` | U170-433 | UART（PORT.C，9600/115200 冲突） | 高（UART 应答器） | 中 |
| 4.11 | `zigbee` | U110 | UART（PORT.C，38400） | 高（UART 帧） | 中 |
| 4.12 | `nbiot2` | U111-B | UART（PORT.C，115200） | 高（AT 应答器） | 中 |

未研究集合的推导：`products.json` 的 184 款 `category=unit` 产品中，75 款与
`platform/units/catalog.json` 的 76 个 id 精确重合（`servo8-hat` 属 HAT 口径差：
catalog 收录但 products unit 列表无对应产品），因此**未登记产品 = 184 − 75 = 109**。
其中 batch4 已研究但尚未登记/实现的 6 款（`weight`/`bldc-driver`/`ac-measure`/
`dds`/`gps`/`uhf-rfid`）不应重复研究，本批实际从未研究的 **103 款**中选 12 款。
其余未选产品按“无官方驱动/无数据面（passive、camera/Linux 模块、SPI 显示等）”
或“控制器框架尚未覆盖（多通道 UART hub、CAN/SPI、摄像头）”留待后续批次；
本批不把它们写成 planned。

**最推荐的 5 款**（按“可复用框架 + 可断言数据面 + 冲突可控”排序）：

1. `pbhub-v11`（U041-B）— 0131 `CONTROL_PBHUB` 直接复用，单 0x61 命令空间，
   新增 fw v1/v2 fixture 与 SKU id 即可；与已实现 pbhub 同族，证据成本最低。
2. `op90`（U057）— 与已实现 `limit`/`pir` 的 GPIO 数字输入模型同构（白线、
   上拉、active-low），无需新 kind；只用 PORT.B。
3. `rgb-led-10cm`（A035）— 与已实现 fader/rgb 的 RMT 捕获路径同构，15 灯；
   只需按 SKU 配 LED 数并复用 `m5_unit_rmt_tx_routed`。
4. `8angle`（U154）— 与 `scales`/`extencoder` 的 4B/寄存器组同族，8 路 ADC +
   8+1 RGB + 开关；寄存器全部来自官方驱动，0x43 无冲突。
5. `pahub-v20`（U040-B）— 唯一“多总线/同地址设备共存”代表；实现成本高，但
   能补齐 hub/mux 框架缺口，建议在单总线 unit 模型稳定后做。

主要 unresolved/冲突：

- `pahub-v20`：单字节通道 bitmask 只能通过现有 **单 bus attachment** 观测到
  mask 本身；嵌套 hub/下游同地址设备需要新的多 bus 扩展。`0x70` 与已登记
  `env-iii`（QMP6988 0x70）冲突；`0x71–0x77` 未占用。
- `pbhub-v11`：与已登记 `pbhub`（U041）**同 id 空间/不同产品版本**；`0x61` 仍与
  `pbhub` 冲突，通道基址 `0x40/0x50/0x60/0x70/0x80/0xA0` 与 `encoder`/`scroll`
  （0x40）、`nfc`/`acssr`（0x50）、`dac`（0x60）、`env-iii`（0x70）等冲突；
  固件 v1/v2 决定 SK6812 与 IAP 支持，v2 协议表未逐行落地。
- `rtc`：`0x51` 与 `ameter` 的校准 EEPROM 0x51 冲突；时钟必须由 QEMU 虚拟时钟
  推进才有意义，纯静态寄存器只能验证读写/告警配置，时间运行语义 NOT RUN。
- `tmos-pir`：`0x5A` 与已登记 `ncir`/`ncir2` 冲突；存在 embedded-function 页
  机制（0x08/0x09/0x11）与多种 gain/ODR/中断语义，光学/热学 NOT RUN。
- `lora-e220-433`：官方页面规格写 UART **115200**，驱动构造器写 **9600**；
  两者冲突 unresolved。DIP M0/M1 工作模式、RF/天线/433MHz 物理 NOT RUN。
- `zigbee`：UART 帧（0xFA 起始/校验和）与 0xED P2P 帧来自驱动；RF/Mesh/
  路由/加密/NOT RUN；页面 UART 38400 与驱动一致。
- `nbiot2`：SIM7028 AT 应答器可模拟，但 NB-IoT 网络/SIM/运营商认证/HTTP/TLS
  全部 NOT RUN；AT 固件版本未钉 SHA。
- `neohex`：public 源中**没有 unit/neohex 驱动**，只能锚定通用
  `driver/neopixel` + 官方页面（37×WS2812C，PORT.B yellow=信号）；具体
  WS2812 vs SK6812 类/字节序 unresolved，建议后续证据用通用 NeoPixel 路径并
  记录驱动缺口。
- 页面/驱动版本：本地 UIFlow 源码是 HEAD `528edd8`（batch1-4 的快照树），
  **master 与快照的差异未在本批逐字节复核**（无网络 master 抓取），版本敏感项
  （PbHub v1/v2、SHT/SCD4x、UART AT 固件）在各自小节标 unresolved。

## 1. 证据方法与分级

### 1.1 证据源与固定版本

| 来源 | 固定版本/日期 | 用途 |
| --- | --- | --- |
| `products.json` | 仓库当前 `platform/web/vendor/m5stack-models/catalog/products.json`（`updated=2026-11-01`） | 产品 id/SKU/官方 docs URL/参考图 |
| 官方 UIFlow2 源码 | `.work/uiflow-micropython-public` git HEAD `528edd8` | `m5stack/libs/unit/*.py` 与 `driver/*.py` 逐行协议 |
| 官方产品页面 | `2026-11-02` 抓取（12 页，见 §8） | PinMap、规格、分辨率/通道数、协议表说明 |
| 已登记契约 | `platform/units/catalog.json`（76 款）、`host-ports.json`（23 主机） | 地址/端口冲突与复用 |
| 只读 QEMU | `.m5-qemu-src/qemu` HEAD `75f1d24`（canonical native layer 0109+0110–0119；未含 0120+ 补丁） | 复用接入点定位（本地工作树含 0120–0135） |

### 1.2 逐款证据等级

- **driver-confirmed**：寄存器/地址/命令表可从官方驱动逐行引用，且有官方页面
  或官方 I2C 地址表佐证（`pahub-v20`、`pbhub-v11`、`8angle`、`kmeter-iso-v11`、
  `rtc`、`tmos-pir`、`rgb-led-10cm`、`op90`、`lora-e220-433`、`zigbee`、
  `nbiot2`）。
- **driver-gap**：没有 unit 层驱动，只有通用驱动/页面（`neohex`：`driver/neopixel`）。
- **conflict/unresolved**：页面与驱动数字不一致或版本语义未定（`lora` 波特率、
  `pbhub-v11` 固件 v1/v2、`pahub` 6 vs PCA9548A 8 通道、`neohex` 字节序）。

### 1.3 主机侧约定（本批全部适用）

- 本批不运行 QEMU、不修改 `platform/units/*`；所有候选写入 catalog 草稿，
  `model_status=planned`、`runtime.status="unsupported"`。
- GPIO/RMT 类沿用 `host-ports.json` 的端口约定：UIFlow GPIO port tuple 惯例
  `(white, yellow)`；UART 单元驱动构造器为 `UART(id, tx=port[1], rx=port[0])`，
  即 **yellow=host TX/unit RX，white=host RX/unit TX**，与已登记 `rs485`/`midi`
  契约一致。
- I2C 类统一 `yellow=SDA, white=SCL`（详见各款 PinMap）。

## 2. 与现有 QEMU 模型的复用映射

以下是本地工作树 `hw/m5stopwatch/`（canonical + 0120…0135）的接入点，仅只读
参考；本批未修改 QEMU。

| 模型文件 | 现有关键接入点 | 本批用途 |
| --- | --- | --- |
| `m5_unit_runtime.c` | `m5_unit_i2c_attach()`、`sensor_attach_one`、GPIO/RMT/UART 端口创建与 `m5_unit_gpio_supported()` 列表 | 所有 I2C 单元；GPIO/RMT/UART 单元挂在 UNIT_GPIO 分支 |
| `m5_unit_i2c_sensors.c` | `UnitSensorKind` 枚举、`sensor_send/recv`、`add_number/add_fixture_int`、`sensor_attach_one`、0126 双从机 | `kmeter-iso-v11`、`rtc`、`tmos-pir`；`8angle` 也可作为 sensor 寄存器文件 |
| `m5_unit_i2c_controls.c` | `CONTROL_*` 枚举、`snapshot_registers`、`control_send/recv`、`CONTROL_PBHUB`（0131）、`add_control_int_fixture` | `pbhub-v11`（复用 PBHUB）、`pahub-v20`（mux 控制）、`8angle`（寄存器组） |
| `m5_unit_gpio.c` | `m5_unit_adc_sample`、`m5_unit_rmt_tx_routed`、`esp32_gpio_set_input`、GPIO/RMT/ADC/rs485-UART 分支、pad observer | `op90`（数字输入）、`rgb-led-10cm`/`neohex`（RMT 捕获） |
| 0120–0135 已实现模型 | `pbhub`、`fader`、`rgb`、`scales`、`extencoder`、`limit`/`pir`、`rs485` UART | 上述复用基线 |

复用原则（与 batch1-4 相同）：GPIO/ADC 走 `esp32_gpio_set_input`/`m5_unit_adc_sample`，
RMT 走 `m5_unit_rmt_tx_routed`，I2C 在 `I2CSlaveClass.send/recv` 内实现真实字节
语义；QOM 只做注入/观测。

## 3. 地址与总线冲突

本批候选与已登记 76 款（`catalog.json`）的 7-bit 地址冲突：

| 地址 | 本批候选 | 已登记/同批冲突 | 依据 |
| --- | --- | --- | --- |
| `0x70` | `pahub-v20` 默认地址（0x70–0x77） | `env-iii`（QMP6988 0x70） | 官方页面；`unit/pahub.py:21` |
| `0x71–0x77` | `pahub-v20` 可改地址 | 未占用 | 官方页面 A0–A2 表 |
| `0x61` | `pbhub-v11` | `pbhub`（U041） | 官方页面；`unit/pbhub.py:14` |
| `0x40/0x50/0x60/0x70/0x80/0xA0` | `pbhub-v11` 6 通道基址 | `encoder`/`scroll`(0x40)、`nfc`/`acssr`(0x50)、`dac`(0x60)、`env-iii`(0x70) | `unit/pbhub.py:12`；batch3 §3 |
| `0x43` | `8angle` | 未占用 | 官方页面；`unit/angle8.py:11` |
| `0x66` | `kmeter-iso-v11` | 未占用 | 官方页面；`unit/kmeter_iso.py:10` |
| `0x51` | `rtc`（PCF8563/HYM8563） | `ameter` 校准 EEPROM 0x51 | `unit/rtc8563.py:38`；`driver/pcf8563.py:33` |
| `0x5A` | `tmos-pir` | `ncir`/`ncir2`（0x5A） | 官方页面；`driver/sths34pf80.py:20` |

总线/端口级冲突：

- **UART**：`lora-e220-433`/`zigbee`/`nbiot2` 都是 **PORT.C**（页面 PinMap：
  yellow=UART_RX，white=UART_TX）。`host-ports.json` 中带 PORT.C 的主机为
  `cores3`、`core2`、`stackchan`、`stamplc`；`atoms3r`/`sticks3`/`stopwatch` 只有
  A/custom，不能按官方 PORT.C 接线直接回放。UART 控制器与已登记 `rs485`/
  `rs485-iso`/`midi` 共用 UART 路由，需按主机选择空闲 UART 编号（UART1/UART2），
  同一 UART 上不能并存两个 Unit。
- **GPIO/RMT**：`rgb-led-10cm`/`neohex`/`op90` 都是 **PORT.B**（yellow/white 的
  具体信号见各款）。带 PORT.B 的主机为 `cores3`、`core2`、`stackchan`。
  `stopwatch`/`atoms3r`/`sticks3` 无 PORT.B，只能改接线或不在这些主机回放；
  研究 doc 与后续 evidence 必须显式记录。
- **I2C 共享**：`pahub-v20` 的用途正是“同地址设备共存”，但当前 Unit 框架
  每个 attachment 只有一条 bus；在实现多 bus 前，pahub 只能作为“mask 寄存器
  + 通道选择”观测，不能真正转发下游设备事务（见 §4.1）。
- `pbhub-v11` 与已登记 `pbhub` 的 id 冲突需要新 id（本批草稿用 `pbhub-v11`），
  且不能与 `pbhub` 同时挂同一 bus。

## 4. 各款协议详情

### 4.1 `pahub-v20` — Unit PaHub v2.0（U040-B）

**官方**：[Unit PaHub v2.0](https://docs.m5stack.com/en/unit/pahub2)（2026-11-02）；
SKU `U040-B`；PCA9548AP I2C 多通道开关；I2C `@0x70`（A0–A2 焊盘可改
0x70–0x77）；6 通道扩展；允许同一地址的 slave 共存（分时轮询）；嵌套支持。
**驱动**：`unit/pahub.py`（113 行，git `528edd8`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**命令/寄存器语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 通道常量 | `unit/pahub.py:14-19` | `PAHUB_CHN0..5 = 0..5`（仅 6 通道） |
| 默认地址 | `:21` | `PAHUB_DEFAULT_ADDR = 0x70` |
| 构造 | `:27-33` | 保存 i2c/address/channel；无验证/扫描 |
| 选通 | `:36-39` | `readfrom(addr,1)[0] \| (1<<channel)` 后 `writeto(addr,buf)`；读-改-写 1 字节 bitmask |
| 释放 | `:41-44` | `readfrom(addr,1)[0] & ~(1<<channel)` 后写回 |
| 透传 | `:49-113` | scan/start/stop/readinto/write/readfrom/writevto/readfrom_mem/writeto_mem 全部 `select_channel→操作→release_channel` |
| deinit | `:46-47` | 释放当前通道 |

**官方 API**：`select_channel()/release_channel()/deinit()/scan()/start()/stop()/
readfrom()/writeto()/readfrom_into()/writevto()/readfrom_mem()/writeto_mem()`
（即把任意 I2C 操作包进通道选择）。

**主机输入**：`channel`（0..5）、`channel-mask`（只读，1 字节 bitmask）、每通道
下游设备 fixture（由 hub attachment 内部暴露）。若实现多 bus：每通道一组
`device_id/address` fixture；不建议把下游设备当独立 Unit 挂同一 bus。

**QEMU 建议**：现有 `m5_unit_i2c_attach()` 只支持一个 attachment 一条 bus，无法
表达“通道→下游 bus”。两种落地：
1. **仅 mux 数据面**（低成本）：新增 `CONTROL_PAHUB`，在 0x70 上实现 1 字节
   mask 寄存器（读回 OR/AND 语义），QOM `channel-mask`/`channel`；下游事务
   不转发，作为 composition-only 记录。
2. **完整嵌套 hub**（高成本）：在 QEMU I2C 模型上为 0x70 生成 6 条下游
   `I2CBus`，每次写 mask 后把后续事务转发到选中的下游 bus；需要 runtime
   多 bus attach 扩展与同地址占用检查（当前框架缺口）。
   建议先做 1，等 batch6 再评估 2；catalog 草稿的 `required_data_plane` 按方案 1
   描述，并明确“下游转发/嵌套 NOT modeled”。

**可断言数据面**：mask 写入/读回（读-改-写序列）、select/release 顺序、通道号
越界（驱动把 channel 原样使用，无 clamp，需 fixture 校验）、0x70 地址占用冲突。
**风险/未确认**：PCA9548A 实为 8 通道而 unit/驱动只暴露 6；A0–A2 焊盘改址未
建模；同一/不同地址设备嵌套、轮询时序、hot-plug、总线电容/电气 NOT RUN；
`0x70` 与 `env-iii` 冲突（一 bus 一个）；官方页面“1–6 expansion”与 8 通道芯片
差异 unresolved。

### 4.2 `pbhub-v11` — Unit PbHub v1.1（U041-B）

**官方**：[Unit PbHub v1.1](https://docs.m5stack.com/en/unit/pbhub_1.1)（2026-11-02）；
SKU `U041-B`；6×PORT.B 扩展、GPIO/PWM/Servo/ADC/RGB；STM32F030F4P6；
I2C `@0x61`（寄存器写可改）；固件 v1/v2（v2 增加 SK6812 支持与 I2C IAP）。
**驱动**：`unit/pbhub.py`（202 行，git `528edd8`）；与 batch3 §4.9 的
`pbhub`（U041）为同一驱动的不同产品版本。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/命令语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 通道基址 | `unit/pbhub.py:12` | `[0x40,0x50,0x60,0x70,0x80,0xA0]`（通道 5 = 0xA0） |
| hub 地址 | `:14` | `PBHUB_ADDR = 0x61`（页面 0x61 可改） |
| 状态寄存器 | `:15-16` | 0xFE 固件版本 / 0xFF I2C 地址 |
| 数字读 IO0/IO1 | `:29-39` | 指针 = `hub_addr[n] \| (0x04 if pos==0 else 0x05)`；`read_reg` 两次事务（写指针→读 1B） |
| 数字写 IO0/IO1 | `:41-51` | 指针 = `hub_addr[n] \| (0x00 if pos==0 else 0x01)`；1B 写 |
| PWM 读 | `:53-64` | 0x02/0x03 读 1B，`map(0..255→0..100)` |
| PWM 写 | `:66-77` | 0x02/0x03 写 1B，`map(0..100→0..255)` |
| 模拟读 | `:79-89` | 0x46 读 2B `struct.unpack("<h")`（页面 10-bit 0–5V） |
| RGB 数量 | `:91-98` | 0x48 写 2B LE `length` |
| 单灯颜色 | `:100-109` | 0x49：2B LE led + 3B `color_grb`（GRB 交换） |
| 区间颜色 | `:111-123` | 0x4A：begin(2B LE)+count(2B LE)+color_grb(3B) |
| 亮度 | `:125-132` | 0x4B 写 1B（0–100 → 0–255） |
| 舵机角度 | `:134-144` | 0x42/0x43 写 1B（角度→0–255 映射，需按驱动行核对） |
| 舵机脉冲 | `:146-156` | 0x43? 2B（驱动逐行） |
| 状态读 | `:158-164` | 0xFE/0xFF 读 1B |
| 地址迁移 | `:166-183` | 写 0xFF；含同总线冲突检查（驱动层） |
| 读写原语 | `:185-196` | 写 `writeto_mem`；读先 `writeto` 指针再独立 `readfrom_into`（两次事务） |

**官方 API**：`digital_read/write`、`pwm_read/write`、`analog_read`、
`set_rgb_led_num`、`set_rgb_color_pos`、`set_rgb_color`、`set_rgb_brightness`、
`set_servo_angle`、`set_servo_pulse`、`read_status`、`set_i2c_address`、`deinit`。

**主机输入**：6 通道 `digital-inputs`/`analog-inputs`/`rgb-frames`、
`fw-version`（v1/v2 fixture）、地址迁移 fixture。

**QEMU 建议**：复用 batch3 `0131 CONTROL_PBHUB`（单 0x61 命令空间、通道
`base|offset`、GRB、0x4A 区间颜色、0x4B 亮度、0xFF 迁移、0xFA RGB mode），
新增 unit id `pbhub-v11` 与 `fw-version`（v1/v2）fixture；v2 的 SK6812/IAP
差异先作为 unresolved，不伪造 IAP 升级路径。无需新 kind。

**可断言数据面**：每通道 digital/pwm/analog 读回与写入轨迹、RGB 单灯/区间/
亮度、舵机角度/脉冲写值、0xFE/0xFF、地址迁移冲突、通道 5 基址 0xA0。
**风险/未确认**：固件 v1/v2 协议差异（SK6812、IAP 命令未逐行核对）；页面
Protocol 表为图片/PDF 形式，本报告以驱动逐行为准；MCU 身份（本页写
STM32F030F4P6，官方 I2C 总表/旧 U041 写 MEGA328）仍 unresolved；RGB 字节序/
颜色空间、servo 机械角度、嵌套 hub 不支持；`0x61` 与 `pbhub`、通道地址与
已登记 Unit 冲突（一 bus 一个）。

### 4.3 `8angle` — Unit 8Angle（U154）

**官方**：[Unit 8Angle](https://docs.m5stack.com/en/unit/8Angle)（2026-11-02）；
SKU `U154`；8 个可调电位器 + 拨动开关 + 8+1 个 SK6812-3535 RGB；STM32F030F4P6；
I2C `@0x43`；PORT.A。
**驱动**：`unit/angle8.py`（137 行，git `528edd8`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00–0x0F` | `unit/angle8.py:15-16,47-54` | 8 通道 ADC12 原始值，每通道 2B **小端 signed**（`<h`） |
| `0x10–0x17` | `:17-18,56-61` | 8 通道 ADC8 原始值，每通道 1B |
| `0x20` | `:19,63-64` | 拨动开关状态 1B（bool） |
| `0x30–0x53` | `:20-21,65-78` | 9 个 RGB：每通道 4B `[R,G,B,bright]`（bright 0–100） |
| `0xFE` | `:22` | 固件版本 |
| `0xFF` | `:23` | I2C 地址 |

**驱动语义**：`get_adc12_raw(channel)` 用 `readfrommem(reg,2)`（先写指针再读）；
`get_adc8_raw` 读 1B；`get_switch_status` 读 0x20；`set_led_rgb(channel,rgb,bright)`
写 4B；`set_led_rgb_from` 逐灯；`set_angle_sync_bright` 用 ADC12→亮度映射；
`readfrommem` 为“写 1B 指针 + 独立读 N 字节”两次事务；`set_i2c_address` 写 0xFF
并延时 200ms。

**官方 API**：`get_adc12_raw/get_adc8_raw/get_switch_status/set_led_rgb/
set_led_rgb_from/set_angle_sync_bright/get_device_spec/set_i2c_address`。

**主机输入**：`adc12[8]`（0–4095）、`adc8[8]`、`switch` bool、`rgb[9][4]`、
`fw-version`、地址迁移 fixture。

**QEMU 建议**：新增 `CONTROL_ANGLE8`（或复用 scales/extencoder 的 256B
`read_snapshot` 寄存器组）：`read_snapshot` 填 ADC12 LE16×8 / ADC8×8 /
switch / RGB 4B×9 / fw / addr；写路径接受 0x30–0x53 RGB 与 0xFF 地址迁移
（含同总线冲突检查）；QOM 暴露 `adc12`/`adc8`/`switch`/`rgb-frames`/
`fw-version`/`i2c-address`。

**可断言数据面**：guest ADC12/ADC8 与 fixture 一致（含小端符号）、switch、
RGB 写→QOM 读回、地址迁移、指针+独立读事务计数。
**风险/未确认**：电位器机械行程/线性度/零点、SK6812 光学、ADC 参考/滤波、
`set_angle_sync_bright` 的映射语义；`0x43` 无已登记冲突。

### 4.4 `kmeter-iso-v11` — Unit KMeter-ISO v1.1（U133-V11）

**官方**：[Unit KMeter-ISO](https://docs.m5stack.com/en/unit/KMeterISO%20Unit)
（2026-11-02）；SKU `U133-V11`；K 型热电偶 + STM32F030 + MAX31855KASA
（14-bit，0.25°C）+ CA-IS3641HW 隔离；I2C `@0x66`；PORT.A；±2°C。
**驱动**：`unit/kmeter_iso.py`（95 行，git `528edd8`）。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（驱动逐行）**：

| 寄存器 | 证据 | 语义 |
| --- | --- | --- |
| `0x00` / `0x04` | `:10-11,39-42` | 热电偶温度 °C / °F：4B **小端 int32**，值/100 |
| `0x10` / `0x14` | `:12-13,44-47` | 内部（冷端）温度 °C / °F，同样 /100 |
| `0x20` | `:14,49-52` | 就绪：`read 1B`，0=ready（驱动 `return False if status else True`） |
| `0x30` / `0x40` | `:15-16,54-66` | 温度十进制字符串（1B 整数部分 + 8B 小数部分 ASCII） |
| `0x50` / `0x60` | `:17-18,68-80` | 内部温度的整数+字符串形式 |
| `0xFE` / `0xFF` | `:19-20,82-95` | 固件版本 / I2C 地址（写 0xFF 改址，0x08–0x77 校验） |

**驱动语义**：`int_convert` 用 `struct.unpack("<i", value)`；温度 `/100` 保留
两位；字符串读取为两次 `readfrom_mem`（1B+8B，先 decode 再 float）；改址写 1B。

**官方 API**：`get_thermocouple_temperature()`、`get_internal_temperature()`、
`is_ready()`、`get_thermocouple_temperature_string()`、
`get_internal_temperature_string()`、`get_device_info()`、`set_i2c_address()`。

**主机输入**：`thermocouple-c`/`internal-c`（fixture，0.01°C 量化）、
`ready` bool、`fw-version`、字符串形式的可观测 fixture。

**QEMU 建议**：新增 `US_KMETER`（sensor 寄存器文件）：从 fixture 反算 LE int32
（`round(c*100)`）写入 0x00/0x04/0x10/0x14；0x20 由 `ready` fixture 控制；
0x30/0x40/0x50/0x60 生成对应 ASCII；0xFE/0xFF 身份/迁移。或复用
`CONTROL_*` 寄存器组（若把温度当控制类），推荐 sensor 分支（纯观测）。

**可断言数据面**：guest 热电偶/内部温度与 fixture 在 0.01°C 内一致、ready
门控、字符串路径一致、fw/地址、改址冲突。
**风险/未确认**：MAX31855 故障位（开路/短路/低电压）与 fault 语义、热电偶
物理/冷端补偿/±2°C、隔离/电源、10Hz/SPI 内部（对 host 不可见）NOT RUN；
`0x66` 无已登记冲突。

### 4.5 `rtc` — Unit RTC（U126）

**官方**：[Unit RTC](https://docs.m5stack.com/en/unit/UNIT%20RTC)（2026-11-02）；
SKU `U126`；HYM8563（PCF8563 兼容）；I2C `@0x51`（≤400kbps）；PORT.A；
纽扣电池备份、世纪位。
**驱动**：`unit/rtc8563.py`（308 行）+ `driver/pcf8563.py`（256 行），git `528edd8`。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器表（`driver/pcf8563.py:33-72`）**：

| 寄存器 | 语义 |
| --- | --- |
| `0x00` CS1 | TEST1/STOP/TESTC（STOP 停振） |
| `0x01` CS2 | TI_TP/AF/TF/AIE/TIE（告警/定时器标志与使能） |
| `0x02–0x08` | 秒/分/时/日/星期/月(+世纪位)/年，BCD |
| `0x09–0x0C` | 闹钟分/时/日/星期（0x80=disable） |
| `0x0E–0x0F` | 定时器控制/计数值（4.096kHz/64Hz/1Hz/1/60Hz） |

**驱动语义**：`_dec2bcd/_bcd2dec`（`:75-84`）；`datetime()` 读写 7B
（`:95-170`）；`alarm()`（`:171-243`）、`alarm_active()`（`:244-256`）；
unit 层 `RTC8563Unit` 提供 `get_date_time/set_date_time/datetime/write_now/
set_internet_time/set_clk_out_frequency/check_if_alarm_on/turn_off_alarm/
clear_alarm_flag/set_daily_alarm/set_timer_mode/get_timer_value/
check_if_timer_on/turn_off_timer/clear_timer_flag`。

**官方 API**：见上（unit 层封装）。

**主机输入**：`datetime`（BCD 7 字节 fixture）、`alarm` 配置、`timer` 配置、
`running`（STOP 位）、`century`；时间推进 fixture（可选）。

**QEMU 建议**：新增 `US_RTC8563`：寄存器文件 + BCD 编解码；时钟推进由 QEMU
虚拟时钟驱动（`qemu_clock_get_ns`，1Hz）或由 host fixture 固定时间；告警/
定时器用虚拟定时器与标志位；QOM：`datetime`/`running`/`alarm`/`timer`/
`flags`/`i2c-address`。**不建议**用 host 侧 Python 直接写 guest 返回值。

**可断言数据面**：BCD 读写回环、世纪位、STOP/告警/定时器标志与使能、
alarm 设置/清除、地址 0x51。
**风险/未确认**：晶振精度/电池备份/掉电保持、时间时区（unit 层 internet_time
依赖网络）、alarm IRQ 语义、世纪位/闰年 NOT RUN；时钟“运行”在 QEMU 中需
明确虚拟时间基准；`0x51` 与已登记 `ameter` 校准 EEPROM 冲突。

### 4.6 `tmos-pir` — Unit TMOS PIR（U185）

**官方**：[Unit TMOS PIR](https://docs.m5stack.com/en/unit/Unit_TMOS_PIR)
（2026-11-02）；SKU `U185`；STHS34PF80；I2C `@0x5A`；PORT.A；80° FOV、
2m、0.25–30Hz ODR、5–20µm、±0.3°C。
**驱动**：`unit/tmos.py`（5 行别名）+ `driver/sths34pf80.py`（820 行），
git `528edd8`。

**接线（官方 PinMap，PORT.A）**：Black=`GND`、Red=`5V`、Yellow=`SDA`、White=`SCL`。

**寄存器/命令表（`driver/sths34pf80.py`）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 地址/ID | `:20-21` | `0x5A`；WHOAMI 0x0F = `0xD3` |
| LPF/AVG | `:23-26` | 0x0C/0x0D/0x10 滤波/平均配置 |
| CTRL0 | `:27` | 0x17（ODR 等，具体位以驱动 `_set_tmos_odr` 为准） |
| SENS_DATA | `:28` | 0x1D 灵敏度数据 |
| CTRL1/2/3 | `:29-31` | 0x20/0x21/0x22 |
| STATUS/FUNC_STATUS | `:32-33` | 0x23/0x25 中断/功能状态 |
| 数据寄存器 | `:34-45` | TOBJECT 0x26/27、TAMBIENT 0x28/29、TOBJ_COMP 0x38/39、TPRESENCE 0x3A/3B、TMOTION 0x3C/3D、TAMB_SHOCK 0x3E/3F |
| embedded 页机制 | `:48-62` | 0x08/0x09 页地址/数据、0x11 PAGE_RW；阈值/迟滞/算法配置在页内 0x20–0x2A |

**驱动语义**：`begin()` 读 WHOAMI 校验 0xD3（`:177`）、`reset()`（`:194`）、
`set_lpf_*`/`set_avg_*`/`set_gain_mode`/`get_tmos_odr`/`set_tmos_sensitivity`
（`:244-343`）、`get_motion_state()/get_presence_state()/get_tamb_shock_state()`
（`:443-452`）、`get_tobject_raw_value()/get_temperature_data()/
get_tambient_raw_value()/get_tobject_compensated_raw_value()/get_tamb_shock_raw()`
（`:453-495`）、`get_presence_value()/get_motion_value()`（`:496-518`）、
阈值/迟滞 getter/setter（`:619-802`）。unit/tmos.py 直接别名
`STHS34PF80 as TMOSUnit`。

**主机输入**：`tobject-c`、`tambient-c`、`presence-raw`/`motion-raw`、
`presence-flag`/`motion-flag`/`shock-flag`、`gain-mode`、`odr`、`sensitivity`。

**QEMU 建议**：新增 `US_STHS34PF80`（sensor 寄存器文件 + embedded 页）：从
fixture 反算 16 位原始值；实现 WHOAMI 校验、CTRL 读写、数据寄存器读回、
状态位、页机制；QOM：`tobject-c`、`tambient-c`、`presence`、`motion`、
`shock`、`gain-mode`、`odr`、`i2c-address`。

**可断言数据面**：WHOAMI=0xD3、CTRL/ODR/gain 写回读、Tobject/Tambient
原始值与 fixture 换算、presence/motion/shock 状态位、embedded 页读写。
**风险/未确认**：IR 光学/5–20µm/FOV/距离/±0.3°C、热模型、gain 饱和与
power-down 复位语义、算法阈值/迟滞/中断时序 NOT RUN；`0x5A` 与 `ncir`/`ncir2`
冲突。

### 4.7 `rgb-led-10cm` — Unit RGB LED 10cm / 15LED（A035）

**官方**：[Unit RGB LED](https://docs.m5stack.com/en/unit/neopixel)（2026-11-02）；
SKU `A035`（本款 10cm/15 LED；同系列 A035-B 29、0.5m 72、1m 144、2m 288）；
SK6812 (3535)；800K/s；PORT.B。
**驱动**：`unit/rgb.py`（10 行）+ `driver/neopixel/__init__.py`（95 行）+
`driver/neopixel/sk6812.py`，git `528edd8`。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`LED Signal`、
White=`NC`。

**协议语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 单元封装 | `unit/rgb.py:8-10` | `RGBUnit(port, number)` → `SK6812(port[1], number)`；number 由 SKU 决定（本款 15） |
| 字节序 | `driver/neopixel/__init__.py:10` | `ORDER=(1,0,2,3)` → 物理缓冲每灯 G,R,B（SK6812 GRB） |
| 时序 | `:12-24` | `timing=1` → 400/850/800/450ns（800kHz） |
| 写帧 | `:49-51` | `bitstream(pin,0,timing,buf)` 一次发送全部缓冲 |
| 亮度 | `driver/neopixel/sk6812.py` + `:78-95` | `set_brightness(0-100)` 对缓冲缩放后重发 |
| 颜色 | `:56-80` | `color_to_rgb` 等 |

**官方 API**：`RGBUnit(port,number)` 继承 SK6812/NeoPixel：
`__setitem__/fill/fill_color/set_color/set_brightness/write/color_to_rgb`。

**主机输入**：每灯 `led-rgb[15]` fixture、`led-frames`、`incomplete-frames`、
`led-count`（SKU）。

**QEMU 建议**：复用已实现 `fader`/`rgb` 的 RMT 捕获
（`m5_unit_rmt_tx_routed`）：UNIT_GPIO 分支 `leds=15`，从 RMT 符号解码 G,R,B
并 QOM 暴露 `led-rgb`（RGB int）、帧计数、incomplete 计数；`unit/rgb.py` 的
port[1]=yellow 与 PORT.B 一致。无需新 kind。

**可断言数据面**：guest 写 15 灯颜色后 QOM 逐灯一致、帧计数、无 incomplete、
亮度缩放行为、SKU LED 数（15 vs 29/72…）配置。
**风险/未确认**：LED 光学/色温/功率、RMT 时序容差、GRB 字节序/亮度缩放对
不同 neopixel 版本敏感（需钉驱动 SHA）、SIG 电平/上电复位；A035 官方页面
（neopixel）与 A093 strip 页面共享 SK6812 但 LED 数不同。

### 4.8 `neohex` — Unit NeoHEX（A045-B）

**官方**：[Unit NeoHEX](https://docs.m5stack.com/en/unit/Unit_NeoHEX)（2026-11-02）；
SKU `A045-B`；37×WS2812C-2020-V1；单总线、可级联；HY2.0-4P：2×输入
（signal/power）+1×输出扩展；PORT.B。
**驱动**：public 源中**无 `unit/neohex.py`**；通用驱动 `driver/neopixel`。
本款属于 **driver-gap**：研究只能锚定通用 NeoPixel/SK6812 路径 + 官方页面。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`LED Signal`、
White=`NC`。

**协议/复用**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| LED 数 | 官方页面 | 37×WS2812C；级联上限 1024 帧 |
| 单总线 | 官方页面 | DATA 单线、800kHz 类似 WS2812 |
| 通用驱动 | `driver/neopixel/__init__.py` | NeoPixel（WS2812）ORDER=(1,0,2,3)，`bitstream` 写；具体单元使用哪一类（SK6812 vs NeoPixel）在 public 源无 unit 文件 → unresolved |
| 级联 | 官方页面 | 2 输入 1 输出，可级联多面板 |

**主机输入**：`led-rgb[37]`、`led-frames`、`incomplete-frames`。

**QEMU 建议**：复用 RMT 捕获，LED 数 37；因无 unit 驱动，证据探针必须显式
使用 `driver.neopixel`（NeoPixel/SK6812）并钉驱动 SHA，记录“官方 UIFlow
Unit 驱动缺失”这个 gap；QOM 同 `rgb-led-10cm`。

**可断言数据面**：37 灯帧捕获、颜色顺序、级联边界（>37 后行为）。
**风险/未确认**：无 unit 驱动（UIFlow 侧可能用 Blockly/硬件资源）、
WS2812 vs SK6812 字节序/时序差异、37 灯功率/光学、级联数据长度上限；
`A045-B` 与旧 `hex` A045 的差异未核对。

### 4.9 `op90` — Unit OP90（U057）

**官方**：[Unit OP90](https://docs.m5stack.com/en/unit/OP.90)（2026-11-02）；
SKU `U057`；90° 非接触光电限位开关（红外发射+接收，遮挡输出动作）；PORT.B。
**驱动**：`unit/op.py`（28 行，git `528edd8`）。

**接线（官方 PinMap，PORT.B）**：Black=`GND`、Red=`5V`、Yellow=`NC`、
White=`Digital Output`（unit→host）。

**驱动语义（逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 类 | `unit/op.py:11` | `OPUnit(Button)` |
| 构造 | `:12-16` | `Pin(port[0]=white, Pin.IN, Pin.PULL_UP)` + `Button(port[0], active_low)` |
| 模式 | `:13-16` | `type=SWITCH`（默认）或 `COUNTER`；COUNTER 时引脚 IRQ 双沿中断计数 |
| 计数 | `:19-27` | `_cb_irq` 状态变化累加，`count_reset()` 清零 |

**官方 API**：`Button` 的 `pressed/value` + `count_reset()`（COUNTER 模式）。

**主机输入**：`digital-level`（white 线，默认高/未遮挡）；`input-events`、
`counter`（IRQ 计数 fixture）。

**QEMU 建议**：**直接复用**已实现 `limit`/`pir` 的 GPIO 数字输入分支：
`esp32_gpio_set_input(white, !pressed)` + `input-events`/`pressed`；`unit/op.py`
port[0]=white 与官方 PinMap 一致；PORT.B-only。无需新 kind。

**可断言数据面**：guest `value()/pressed` 与注入电平一致、双沿计数、
input-events；无 I2C 事务。
**风险/未确认**：光学对准/红外链路/遮挡物尺寸/90° 几何/响应速度 NOT RUN；
active-low 极性（驱动默认）与“Digital Output”电平定义需 fixture 校验；
PORT.B-only（atoms3r/sticks3/stopwatch 无 PORT.B）。

### 4.10 `lora-e220-433` — Unit LoRaE220-433（U170-433）

**官方**：[Unit LoRaE220-433](https://docs.m5stack.com/en/unit/Unit_LoRaE220-433)
（2026-11-02）；SKU `U170-433`；LLCC68/E220-400T22S；433MHz
（410.125–493.125MHz）；22dBm；UART；DIP M0/M1 四模式；PORT.C。
**驱动**：`unit/lora_e220_433.py`（254 行，git `528edd8`）。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`。驱动 `UART(id, tx=port[1], rx=port[0])` → white=host RX/
unit TX，yellow=host TX/unit RX。

**命令/配置帧（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| UART | `:77-90` | `UART(id, tx=port[1], rx=port[0], baudrate=9600, 8N1, rxbuf=1024)` |
| 波特率常量 | `:13-21` | BAUD_1200…115200（REG2 bits7:5） |
| 校验/空速 | `:22-34` | PARITY、AIRRATE 2.4k–62.5k |
| 子包/功率/WOR | `:36-76` | SUBPACKET、RSSI noise、TX 10/13/17/22dBm、channel 0–83、WOR 500–4000ms |
| setup | `:91-116` | 由参数组装 REG2/3/4/5 并 `write_command_format` |
| 写配置 | `:117-137` | 帧 `[0xC0,0x00,0x08, addrH,addrL, reg2,reg3,reg4,reg5, cryptH,cryptL]`（11B），读回等长才成功 |
| 读配置 | `:139-184` | `[0xC1,0x00,0x08]` → 期望 `len(cmd)+8` 字节；解析地址/波特/空速/子包/功率/信道/RSSI/mode/LBT/WOR |
| 接收 | `:186-237` | 轮询/线程读；RSSI 字节在末尾时 `rssi = byte-256` |
| 发送 | `:239-254` | 帧 `target_addr(2B BE) + channel(1B) + payload`，max 200B |
| 透传/定点 | `:245-254` | `send(target_address,target_channel,data)` |

**官方 API**：`setup()`、`read_command_format()`、`send()`、`receive()`、
`receive_none_block()`、`stop_receive()`、`available_data()`。

**主机输入**：`config`（own address/channel/airrate/subpacket/power/WOR/
crypt）、`tx-frame`、`rx-frame`+`rssi`、`mode`（M0/M1）。

**QEMU 建议**：复用已实现 UART 单元路径（`rs485` 的 rx-hex/tx-hex +
`esp32_uart_inject_rx`，见 `m5_unit_gpio.c`）：新增 `US_LORA_E220` 应答器，
按 0xC0/0xC1/透传帧解析、回 11B 配置镜像、注入 receive payload（含可选 RSSI
字节）；QOM：`config`、`tx-frame`、`rx-frame`、`rssi`、`mode`。UART 主机需
PORT.C（cores3/core2/stackchan/stamplc），并占用空闲 UART。

**可断言数据面**：setup 11B 帧逐字节、read config 解析、send 帧 target/channel/
payload、注入 receive 与 RSSI、UART 事务计数。
**风险/未确认**：RF 433MHz/天线/距离/空速/功率/灵敏度 NOT RUN；DIP M0/M1
工作模式（配置/透传/WOR）未建模；**页面规格 UART 115200 vs 驱动 9600 冲突
unresolved**；0xC0/0xC1 固件版本差异、RSSI 字节开关、加密 key 语义；UART 路由
与其他 UART Unit 冲突。

### 4.11 `zigbee` — Unit ZigBee（U110）

**官方**：[Unit ZigBee](https://docs.m5stack.com/en/unit/zigbee)（2026-11-02）；
SKU `U110`；CC2630F128；UART 38400 8N1；2.4GHz、Mesh；PORT.C。
**驱动**：`unit/zigbee.py`（153 行）+ `driver/drf1609h.py`（379 行），git `528edd8`。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`；驱动 `UART(id, 38400, tx=port[1], rx=port[0])`。

**命令/帧语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| UART | `unit/zigbee.py:29-32` | `UART(id,38400,tx=port[1],rx=port[0])` |
| 命令帧 | `driver/drf1609h.py:317-333` | `[cmd, len, data…, checksum]`，checksum=sum(cmd,len,data)&0xFF |
| 响应帧 | `:333-365` | 以 0xFA 起始、`len+4` 总长、`cmd,len,err,data,checksum` |
| 连接 | `:129-137` | `0xFC` + `"\x04\x44\x54\x4b\x52\x46"` → 解析 manufacturer/version |
| 重启 | `:138-144` | `0xFC` + `"\x06\x44\x54\x4b\xaa\xbb"` |
| 模块参数 | `:145-230` | 读写模块参数帧（device type/PAN/channel/transfer mode/ant/encryption/key） |
| 节点参数 | `:241-330` | 查询/读写节点参数、信号强度、加入网络 |
| P2P | `:96-135` | 发送 `[0xED,len,dest_addr(2B BE),data,src_addr(2B BE)]`；broadcast=0xFFFF |

**官方 API**：`connect_command/restart_command/read_module_param_command/
write_module_param_command/query_enddevice_position_command/
query_node_signal_strength/read_node_param_command/write_node_param_command/
restart_node_command/join_network_command/p2p_transmission/broadcast/receive/
set_module_param`。

**主机输入**：`module-params`、`node-params`、`p2p-dest`、`p2p-data`、
`rx-frame` fixture、`rssi`。

**QEMU 建议**：UART 应答器（`US_ZIGBEE_DRF1609H`）：解析 0xFC 命令帧并回
0xFA 响应/参数镜像；处理 0xED P2P 发送与注入接收；QOM：`module-params`、
`node-params`、`tx-frame`、`rx-frame`、`signal`。PORT.C 主机限制同上。

**可断言数据面**：连接/重启/读写参数帧逐字节与 checksum、节点查询、
P2P 帧 dest/data、注入 receive、错误 checksum 路径。
**风险/未确认**：Zigbee Mesh/路由/2.4GHz RF/加密/天线距离/1000 节点 NOT RUN；
DRF1609H 固件版本、参数帧布局（页面 Protocol 为外部文档）、校验/超时语义；
UART 路由冲突；PORT.C-only。

### 4.12 `nbiot2` — Unit NBIoT2（U111-B）

**官方**：[Unit NBIoT2](https://docs.m5stack.com/en/unit/Unit_NBIoT2)（2026-11-02）；
SKU `U111-B`；SIM7028 NB-IoT；UART 115200；AT 命令；PORT.C；SMA 天线。
**驱动**：`unit/nbiot2.py`（27 行）+ `driver/simcom/common.py`（247 行）+
`driver/simcom/sim7028.py`（294 行），git `528edd8`。

**接线（官方 PinMap，PORT.C）**：Black=`GND`、Red=`5V`、Yellow=`UART_RX`、
White=`UART_TX`；驱动 `UART(id, tx=port[1], rx=port[0], 115200, 8N1)`。

**AT/命令语义（驱动逐行）**：

| 项 | 证据 | 语义 |
| --- | --- | --- |
| 初始化 | `unit/nbiot2.py:17-27` | UART 115200 + `SIM7028`；3 次 `AT` 检查；`ATE0` 关回显 |
| AT 执行 | `driver/simcom/common.py:58-130` | `execute_at_command`、`AT`/`ATE`/`CPIN`/`CREG`/`CSQ`/`CGREG`/`CGMM`/`CGATT`/`CGDCONT`/`CGPADDR`/`COPS` |
| 身份 | `sim7028.py:28-52` | `AT+CGSN=1`（IMEI）、`AT+CICCID`、`AT+CGCONTRDP` |
| MQTT | `:53-195` | `AT+CMQTTSTART`、`ACCQ`、`CONNECT`、`DISC`、`REL`、`STOP`、`SUB/SUBTOPIC`、`UNSUB`、`TOPIC`、`PAYLOAD`、`PUB`、`PUB?`、轮询/回调 |
| HTTP | `:219-268` | `AT+HTTPINIT`、`HTTPPARA URL/CONTENT`、`HTTPDATA`、`HTTPACTION`、`HTTPREAD` |

**官方 API**：`get_imei_number/get_ccid_number/get_pdp_context_dynamic_parameters/
mqtt_server_configure/connect/disconnect/subscribe/unsubscribe/publish/
polling_loop/http_request` 等（SIM7028）。

**主机输入**：`at-response` fixture（按命令返回 OK/ERROR/+CMD 数据）、
`imei/ccid`、`mqtt`/`http` 脚本；`modem-ready` bool。

**QEMU 建议**：新增 UART AT 应答器（`US_SIM7028`）：解析 AT 行命令、回
`OK`/`ERROR`/`+CMD:` 响应、支持 `HTTPDATA` 的 `DOWNLOAD` 提示与多行 AT；
QOM：`modem-ready`、`imei`、`ccid`、`at-transcript`、`command-errors`、
`i2c/uart counters`。网络/蜂窝/RF 不建模。

**可断言数据面**：AT 初始化/回显关闭、IMEI/CCID 响应、MQTT 命令序列与
payload 下载、HTTP 动作/读取、错误路径（错误 CRC/超时）。
**风险/未确认**：NB-IoT RF/网络/SIM/运营商认证/TLS/DTLS/CoAP/SSL NOT RUN；
SIM7028 AT 固件版本未钉 SHA、多行 AT/URC 时序、错误码集合；UART 路由与
PORT.C 限制。

## 5. 未确认项汇总（unresolved）

1. `pahub-v20`：PCA9548A 8 通道 vs unit 驱动 6 通道；A0–A2 改址；嵌套 hub/
   同地址设备转发需要多 bus 框架；`0x70` 与 `env-iii` 冲突。
2. `pbhub-v11`：固件 v1/v2（SK6812/IAP）协议差异；页面 Protocol 表未逐行；
   MCU 身份（STM32F030F4P6 vs MEGA328/I2C 总表）仍未定；与 `pbhub`、通道
   基址与已登记 Unit 的冲突。
3. `8angle`：电位器机械/线性度/零点；ADC 参考；`set_angle_sync_bright` 语义。
4. `kmeter-iso-v11`：MAX31855 fault 位；热电偶物理/冷端/隔离；`0x66` 无冲突。
5. `rtc`：时钟运行/晶振/电池备份/时区/闰年；alarm/timer IRQ；`0x51` 与
   `ameter` EEPROM 冲突。
6. `tmos-pir`：IR 光学/热学/gain 饱和/embedded page 阈值时序；`0x5A` 与
   `ncir`/`ncir2` 冲突。
7. `rgb-led-10cm`：LED 光学/功率/时序容差；A035 与 A093/A035-B 等 SKU 的
   LED 数与页面差异；neopixel 版本敏感。
8. `neohex`：**无 unit 驱动**（只有通用 neopixel）；WS2812 vs SK6812 字节序/
   时序；37 灯/级联上限；A045 vs A045-B 差异未核对。
9. `op90`：光学对准/红外链路/遮挡几何/响应；active-low 极性；PORT.B-only。
10. `lora-e220-433`：**页面 UART 115200 vs 驱动 9600 冲突**；DIP M0/M1 模式；
    RF/天线/433MHz 物理；0xC0/0xC1 固件差异；UART PORT.C 路由。
11. `zigbee`：Mesh/路由/RF/加密/天线；DRF1609H 参数帧布局/固件；UART PORT.C。
12. `nbiot2`：NB-IoT 网络/SIM/运营商认证/TLS；SIM7028 AT 固件版本/URC；
    UART PORT.C。
13. 通用：public 源 HEAD `528edd8` 是 batch1-4 的快照树，**master 差异未复核**；
    page/driver 版本敏感项均需在实现时钉 SHA。

## 6. 驱动版本交叉核对

- 本地官方源码树 HEAD `528edd8`（`Enable unicode24 font.`），与 batch1-4
  文档引用的快照 SHA 一致；本批 12 款的驱动文件 SHA-256 见下表，便于实现时
  钉版本。
- 注意：本批未抓取 GitHub master 做逐字节差异；页面规格与驱动不一致处已标
  unresolved（LoRa 波特率、PbHub 固件、neohex 驱动缺失）。

| 驱动文件 | 行数 | SHA-256（前 16） |
| --- | --- | --- |
| `unit/pahub.py` | 113 | `d5c9c5127efcdcb1` |
| `unit/pbhub.py` | 202 | `7838aaa22d1a8e72` |
| `unit/angle8.py` | 137 | `9917a2a2e6c13f9b` |
| `unit/kmeter_iso.py` | 95 | `59adfb9f2db015ea` |
| `unit/rtc8563.py` | 308 | `6a59b47c8d0d6ebe` |
| `unit/tmos.py` | 5 | `9a859456fb49d62d` |
| `unit/rgb.py` | 10 | `68b3a4424e4d0d62` |
| `unit/op.py` | 28 | `dc9f5ce452530694` |
| `unit/lora_e220_433.py` | 254 | `d07379f88f5737d4` |
| `unit/zigbee.py` | 153 | `561e7965a137e5d2` |
| `unit/nbiot2.py` | 27 | `c14696f3787731c2` |
| `driver/pcf8563.py` | 256 | `e56cbf1be0c6aa66` |
| `driver/sths34pf80.py` | 820 | `7b2a5b2603263cc6` |
| `driver/neopixel/__init__.py` | 95 | `f1995e9fa025330b` |
| `driver/neopixel/sk6812.py` | 59 | `b316cbebf49a5a45` |
| `driver/drf1609h.py` | 379 | `a6654fc8e438d195` |
| `driver/simcom/common.py` | 247 | `d126ef03361769ea` |
| `driver/simcom/sim7028.py` | 294 | `5095e2b29b6c73f7` |

## 7. 落地顺序建议

1. **批次 A（低风险，先做）**：`pbhub-v11`、`op90`、`rgb-led-10cm`。
   三者都能直接复用已实现框架（PBHUB control / GPIO digital input /
   RMT capture），每款 1 个 session 即可取得 guest 证据。
2. **批次 B（寄存器文件）**：`8angle`、`kmeter-iso-v11`、`tmos-pir`。
   新增 sensor/control 寄存器组，fixture 注入 + QOM 观测；`0x43`/`0x66` 无
   冲突，`0x5A` 需独立 host（与 ncir/ncir2 冲突）。
3. **批次 C（时钟/多总线）**：`rtc`、`pahub-v20`。
   `rtc` 需要虚拟时钟语义；`pahub` 需要多 bus/嵌套 hub 框架扩展，建议在
   单 bus 模型稳定后做，否则只做 mask 数据面并标 composition-only。
4. **批次 D（UART 应答器）**：`lora-e220-433`、`zigbee`、`nbiot2`。
   三者共享“UART 注入 + 命令应答器”框架，可先实现一个通用 AT/帧应答器；
   PORT.C 只在 cores3/core2/stackchan/stamplc 可用。
5. **driver-gap**：`neohex` 暂无 unit 驱动，建议先确认 UIFlow 官方实际使用
   的 neopixel 类/示例，再决定是否研究与实现，避免把通用驱动当官方单元驱动。

## 8. 官方来源清单

产品页面（2026-11-02 抓取）：

- https://docs.m5stack.com/en/unit/pahub2
- https://docs.m5stack.com/en/unit/pbhub_1.1
- https://docs.m5stack.com/en/unit/8Angle
- https://docs.m5stack.com/en/unit/KMeterISO%20Unit
- https://docs.m5stack.com/en/unit/UNIT%20RTC
- https://docs.m5stack.com/en/unit/Unit_TMOS_PIR
- https://docs.m5stack.com/en/unit/neopixel（A035/A035-B… Unit RGB LED）
- https://docs.m5stack.com/en/unit/Unit_RGB_LED_Strip（A093 系列对照）
- https://docs.m5stack.com/en/unit/Unit_NeoHEX
- https://docs.m5stack.com/en/unit/OP.90
- https://docs.m5stack.com/en/unit/Unit_LoRaE220-433
- https://docs.m5stack.com/en/unit/zigbee
- https://docs.m5stack.com/en/unit/Unit_NBIoT2

官方驱动（`https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/`，
本地固定 SHA 见 §6）：`unit/pahub.py`、`unit/pbhub.py`、`unit/angle8.py`、
`unit/kmeter_iso.py`、`unit/rtc8563.py`、`unit/tmos.py`、`unit/rgb.py`、
`unit/op.py`、`unit/lora_e220_433.py`、`unit/zigbee.py`、`unit/nbiot2.py`、
`driver/pcf8563.py`、`driver/sths34pf80.py`、`driver/neopixel/*`、
`driver/drf1609h.py`、`driver/simcom/*`。

产品目录/地址索引：`platform/web/vendor/m5stack-models/catalog/products.json`；
官方 I2C 地址总表（页面链接）：https://docs.m5stack.com/en/product_i2c_addr 。

## 9. 复现方式

```bash
# 本文档只读、不运行 QEMU；在 worktree 内校验 docs/索引/snapshot：
cd /Users/m5agent/Documents/ChatGPT/esp-emulator-unit5
python3 -m unittest discover -s platform/tests -p 'test_docs_index_contract.py'
python3 platform/tools/project_snapshot.py --check

# 复核驱动 SHA/行号（本地官方源码树，HEAD 528edd8）
cd /Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public/m5stack/libs
sha256sum unit/pahub.py unit/pbhub.py unit/angle8.py unit/kmeter_iso.py \
  unit/rtc8563.py unit/rgb.py unit/op.py unit/lora_e220_433.py unit/zigbee.py \
  unit/nbiot2.py driver/pcf8563.py driver/sths34pf80.py driver/neopixel/__init__.py
```

## 10. catalog 草稿说明

`2026-11-02-batch5-catalog-draft.json` 包含 12 条 **planned** 草稿，字段与
`platform/units/catalog.json` 的既有条目同形（`id/name/sku/visual_asset/
official_docs/checked_at/chips/interface/protocol/inputs/outputs/evidence/
research_status/model_status/runtime/blocker/limitations`）。草稿仅提案：

- `model_status="planned"`、`runtime.status="unsupported"`，
  `runtime.required_data_plane` 描述预期数据面；
- 不写 `simulated`、不写 functional PASS；
- 地址/端口冲突与 unresolved 均写入 `blocker`/`limitations`；
- 合并进 `platform/units/catalog.json` 前需要另行任务（本批只研究，不修改
  catalog/runtime/tests）。
