# Unit 第十批协议研究（收口批）：剩余全部 43 款分类与 planned 契约

日期：`2026-11-03`。范围：`products.json` unit 类别中**尚未登记且未研究**的全部
剩余产品，共 **43 款**。本批是 Unit 收口研究：a/b 类写官方证据与 planned
catalog 草稿；c 类只写“不可接入”边界结论，不登记。完成并落地 a/b 后，184 款
unit 产品应全部有 catalog 登记或明确的边界结论。

固定输入：

- 官方产品目录：`platform/web/vendor/m5stack-models/catalog/products.json`
  （222 products，其中 `category=unit` 184 款）。
- 已登记 Unit：`platform/units/catalog.json` 142 款（其中 `servo8-hat` 为 HAT
  口径差，不是 184 个 unit 产品之一）。
- 已研究文档：`docs/unit-research/2026-11-02-batch1..9-protocols.md`（108 款）。
- 官方 UIFlow2 源码：`/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/uiflow-micropython-public`
  （HEAD `528edd8`）。
- QEMU 只读参考：`/Users/m5agent/Documents/ChatGPT/.m5-qemu-src/qemu`（HEAD
  `75f1d24`）+ canonical 链 `0120-0151`。
- 官方页面在 `2026-11-03` 重新抓取核对（引用见 §7）。

## 0. 收口口径

- 184 个 unit 产品 − 已登记产品 141（142 含 `servo8-hat`）= **43 个剩余**。
- 分类：
  - **a 可实现/可登记（7 款）**：有官方驱动，或页面给出完整接口/地址/帧格式，
    可直接登记 planned 并可实现最小数据面。
  - **b driver-gap 可登记（11 款）**：无官方 Unit 驱动且内部固件/寄存器/帧格式
    未公开，但产品实体、总线/地址元数据明确；只登记 planned 契约 + blocker，
    **不建模型、不猜寄存器**。
  - **c 明确不可接入（25 款）**：camera/Linux/controller/PoE 模块或 passive
    转接/无产品实体；不属于 Unit 数据面 attachment，只写边界结论，不登记。
- 预计总登记数：**142 + 18 = 160**（a 7 + b 11）；c 25 款不登记但全部有边界
  结论。产品覆盖：159 个产品 id 登记 + 25 个 c = 184。

| 分类 | 数量 | 处理 |
| --- | --- | --- |
| a 可实现/可登记 | 7 | 写协议证据 + planned 草稿 |
| b driver-gap 可登记 | 11 | 写页面/地址元数据 + planned 草稿 + blocker |
| c 明确不可接入 | 25 | 只写边界结论，不写草稿、不登记 |
| **合计** | **43** | **预计登记 160** |

## 1. 方法

- 只信官方页面 + 冻结驱动源码；地址/寄存器/帧格式必须有页面或 `file:line`
  出处；缺失时显式 driver-gap/unresolved，不按名字猜。
- a 类最小实现优先复用现有框架（ACSSR I2C、BMI270/BMP280 复合 I2C、UART
  fixture responder、RMT LED 捕获）；b 类只写 planned 契约。
- c 类不论证驱动/寄存器，只说明为什么不属于 Unit 数据面。
- 本批不运行 QEMU、不改 catalog/runtime/测试；草稿全部 planned。

## 2. 总线/复用总览

| 总线/接口 | a/b 单元 | QEMU 复用/缺口 |
| --- | --- | --- |
| I2C | dcssr 0x50、ina226-1a 0x41、dof6 0x68/0x69、dof9 0x68+BMM350 0x14、dof10 0x68+0x14+SPA06 0x76、byteswitch 0x46、bytebutton 0x47、step16 0x48、timerpwr 0x56、mq 0x11、roller485/lite/rollercan-lite 0x64 | 复用 `unit/acssr.py`（DCSSR）、`US_BMI270`/BMP280（mini-imu-pro）、ACSSR I2C slave；BMM350/INA3221/INA226/SPA06 无现成模型 |
| UART | asr 115200、8servos2-chain Chain、cat1-cn 115200、chainbus 115200 | 0145/0151 UART fixture responder（TX 捕获 + idle 应答）；ASR 帧格式完整可解析，其余只字节层 |
| RMT/GPIO | puzzle PORT.B 单线 64×WS2812E | 复用 neohex/hex 37-LED RMT 捕获框架，扩到 64 灯 |
| RS485/CAN | roller485/roller485-lite（RS485）、rollercan-lite（CAN） | 无 Unit 模型；协议表外部文档，planned only |

## 3. a 类：可实现/可登记（7 款）

### 3.1 `dcssr` — Unit DCSSR（U140）

- 官方页面：https://docs.m5stack.com/en/unit/DCSSR%20Unit（U140，5V，PORT.A
  黄=SDA 白=SCL；I2C @0x50；另有 RS485 Modbus 模式 0x04）。
- 官方驱动：`unit/acssr.py:15` `ACSSRI2CUnit(i2c, address=0x50)`；`:84`
  `ACSSRModbusUnit(bus, address=0x04)`；`unit/__init__.py:9` 把 `DCSSRUnit`
  映射到 `acssr`，`:156` `DCSSRUnit = ACSSRUnit`。I2C 寄存器：0x00 开关
  （读/写 1B）、0x10 RGB（3B）、0xFE firmware version、0x20 set address。
- API/数据面：`on()/off()/value()/fill_color(rgb)/get_firmware_version()/
  set_address()`；guest 写 0x00 与 0x10，读 0xFE。
- Fixture/注入：QOM `state`（0/1）、`led-rgb`、`firmware-version`、
  `i2c-address`；建议 fixture SSR 开关状态 + RGB。
- QEMU 复用：新增 `CONTROL_DCSSR` I2C slave 0x50（或复用 ACSSR/relay 开关
  寄存器 + RGB 寄存器）；Modbus 模式不在 Unit attachment 内，仅写 blocker。
- 可断言：guest `on/off/value` 与 QOM state 一致；`fill_color` 写 RGB；
  `get_firmware_version` 读 fixture；**SSR 10A/DC24-220V/隔离/开关寿命/
  接触火花/热 NOT RUN**。
- 风险/冲突：0x50 与 ncir2? 需查既有地址（0x50 与 `nfc`? `cardkb` 0x5F 不冲突；
  QEMU 按实际总线检查）；Modbus 模式与 I2C 模式互斥。
- 复杂度：中低。

### 3.2 `ina226-1a` — Unit INA226-1A（U200-1A）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_INA226-1A（U200-1A，5V，
  PORT.A；**I2C @0x41**；0-30V、±1A、80mΩ shunt、隔离/自恢复保险）。
- 官方驱动：**无 Unit INA226 driver**；标准 TI INA226 寄存器（config 0x00、
  shunt 0x01、bus 0x02、power 0x03、current 0x04、calibration 0x05、
  mask 0x06、alert 0x07）来自 datasheet，需固定 SHA。
- Fixture/注入：`bus-voltage-v`、`current-a`、`shunt-voltage-mv`；QOM
  `bus-voltage-v`、`current-a`、`power-w`、`i2c-address`、`calibration`.
- QEMU 复用：与 batch9 planned `ina226-10a` 同一 INA226 模型，只改 shunt
  （80mΩ）与 ±1A 量程参数；0x41 同地址，二选一。
- 可断言：guest 按 driver 公式读 bus/current/power；**隔离/精度/保险/热/
  ±1A 物理 NOT RUN**。
- 风险/冲突：0x41 与 ina226-10a 同地址；shunt 不同，不能共享校准常量。
- 复杂度：中低。

### 3.3 `dof6` — Unit DoF6（U228）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_DoF6（U228，5V，PORT.A；
  **BMI270 I2C @0x68/0x69（板上开关）**，±2/4/8/16g，
  ±125/250/500/1000/2000dps，16-bit）。
- 官方驱动：**无 Unit DoF driver**；BMI270 芯片寄存器/初始化 blob 已在
  batch7 `mini-imu-pro` 0145 中实现（init burst 接受但不执行、accel/gyro/temp
  fixture；`US_BMI270`），可复用为 planned 实现基础。
- Fixture/注入：`acceleration-x/y/z`、`gyroscope-x/y/z`、`temperature-c`、
  `whoami`；QOM 同名 properties。
- QEMU 复用：新增/复用 `US_BMI270` 单从机 0x68/0x69，去掉 BMM150/BMP280
  子设备；范围配置/motion 未建模。
- 可断言：guest 读 accel/gyro/temp 与 fixture 一致；**真实运动/振动/量程
  切换/init blob/中断 NOT RUN**。
- 风险/冲突：0x68 与 mini-imu/mini-imu-pro/doF9/doF10 冲突；0x69 需板上
  开关，默认 0x68。
- 复杂度：中。

### 3.4 `dof9` — Unit DoF9（U229）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_DoF9（U229，5V，PORT.A；
  **BMI270 0x68/0x69 + BMM350 0x14**；九轴，磁力 ±2000µT/0.1µT）。
- 官方驱动：无 DoF driver；BMI270 可复用 `US_BMI270`；**BMM350 无驱动/
  寄存器表**（batch9 已登记 bmm350 planned），需 datasheet 才能实现。
- Fixture/注入：accel/gyro/temp + `magnetic-x/y/z`、heading（需校准公式）。
- QEMU 复用：`US_BMI270` + 新增 `US_BMM350` I2C register file（0x14）；
  0x14 需与板级 BMM150 0x10 区分。
- 可断言：guest 读九轴 fixture；**磁力/heading/校准/OTP/温度稳定性 NOT RUN**。
- 风险/冲突：0x68 与 mini-imu 系冲突；0x14 与 bmm350 同地址。
- 复杂度：中。

### 3.5 `dof10` — Unit DoF10（U230）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_DoF10（U230，5V，PORT.A；
  **BMI270 0x68/0x69 + BMM350 0x14 + SPA06-003 0x76**；气压 300-1100hPa，
  温度 -40~85°C）。
- 官方驱动：无 DoF driver；BMI270 复用 `US_BMI270`，BMM350/SPA06-003
  无 Unit 驱动/寄存器表（BMP280 0x76 模型不能直接替代 SPA06 气压/温度
  校准）。
- Fixture/注入：accel/gyro/temp + magnetic + `pressure-pa`/`temperature-c`。
- QEMU 复用：BMI270 + BMM350 + 新增 `US_SPA06` I2C register file 0x76；
  与 env/bps/env-ii/env-iv 的 0x76 冲突。
- 可断言：guest 读九轴+气压 fixture；**气压/温度校准/相对高度/物理 NOT RUN**。
- 风险/冲突：0x76 与 env 系冲突；0x68 与 mini-imu 系冲突；0x14 同 bmm350。
- 复杂度：中高。

### 3.6 `asr` — Unit ASR（U194）

- 官方页面：https://docs.m5stack.com/en/unit/Unit_ASR（U194，5V，PORT.C
  黄=UART_RX 白=UART_TX；CI-03T 离线语音，**UART 115200 8N1**；42 条预置
  命令，最多 300 条）。
- 官方驱动：**public UIFlow2 无 unit/asr.py**；页面 Protocol 给出完整帧：
  识别结果 `AA 55 <ID> 55 AA`，命令表含 0x01-0x4A 等（方向/操作/数字/确认/
  音量/版本），语音反馈 `AA 55 <ID> 55 AA <reply>`。
- Fixture/注入：QOM `tx-hex`（guest 发命令）、`rx-frames-hex`/`frames-injected`
  （fixture 识别结果注入）；建议 `command-id`、`reply-code`。
- QEMU 复用：0145/0151 UART fixture responder，扩展为按 AA55 帧解析/注入
  （a 类中唯一有完整帧格式的）；**离线语音识别/麦克风/扬声器/AEC/声学
  NOT RUN**。
- 可断言：guest 发命令帧字节、fixture 识别帧回读；**识别率/声学 NOT RUN**。
- 风险/冲突：PORT.C UART 与所有 UART Unit 冲突；CI-03T 自定义固件命令表
  可改，0x?? 需以预置固件版本为准。
- 复杂度：中。

### 3.7 `puzzle` — Unit Puzzle（U193）

- 官方页面：https://docs.m5stack.com/en/unit/Unit-Puzzle（U193，5V，PORT.B
  黄=LED Signal 白=NC；**8×8=64 颗 WS2812E-1313** 单线级联，两个 Grove
  口 IN/OUT）。
- 官方驱动：**public UIFlow2 无 unit/puzzle.py**；接口为单线 RMT/GPIO
  bitstream，LED 排列/级联方向由页面图给出；WS2812E 与 WS2812C 时序需
  resolution。
- Fixture/注入：guest 写 64 灯帧；QOM `led-rgb`（64×24bit）、`led-frames`、
  `incomplete-frames`、`output-transitions`.
- QEMU 复用：复用 batch5/7 `neohex`/`hex` 的 RMT LED 捕获，`leds=64`；
  PORT.B 未准入时用 cores3 PORT.A harness 并记录替换。
- 可断言：guest fill 后 QOM 64 灯颜色/帧数；**LED 光学/亮度/热/级联
  IN/OUT 方向 NOT RUN**。
- 风险/冲突：PORT.B 与其它 B Unit 冲突；WS2812E vs WS2812C 时序/字节序
  unresolved；64 灯功率/亮度限制（页面建议 10%）NOT RUN。
- 复杂度：中低。

## 4. b 类：driver-gap 可登记（11 款）

这些产品只登记 planned 契约 + blocker；**不建 QEMU 模型、不猜寄存器**。

### 4.1 `roller485` / `roller485-lite`（U182 / U182-Lite）

- 页面：https://docs.m5stack.com/en/unit/Unit_Roller485 ；
  https://docs.m5stack.com/en/unit/Unit-Roller485%20Lite
- STM32G431 + DRV8311 + D3504 200KV + TLI5012；**RS485/I2C 0x64**；
  0.66" OLED 64×48、2×WS2812、按键；Lite 无滑环/顶部 LEGO。
- 驱动：public 无 Unit Roller485 驱动；页面指向 Internal Firmware/
  Communication Protocols 外部文档，无寄存器/帧表；FAQ 仅给位置值
  123.4°×100 的 4 字节发送顺序。
- Planned 契约：`mode`/`target-speed`/`target-position`/`actual-*`/
  `current`/`encoder`/`fault`；QEMU 无模型。**电机/FOC/编码器/OLED/RGB/
  滑环/6-16V/负载/热 NOT RUN**。
- 地址冲突：0x64 与 rollercan/rollercan-lite 同地址；RS485 与 I2C 模式互斥。

### 4.2 `rollercan-lite`（U188-Lite）

- 页面：https://docs.m5stack.com/en/unit/Unit-RollerCAN%20Lite
- 同 RollerCAN 家族（STM32G431/DRV8311/D3504/TLI5012）；**CAN/I2C 0x64**；
  无滑环。public 无 driver、协议外部；QEMU 只能 planned I2C 0x64 契约，
  CAN 走 0145 有限 CanBusClient 观测。**电机/物理 NOT RUN**；0x64 冲突。

### 4.3 `byteswitch`（U191）

- 页面：https://docs.m5stack.com/en/unit/Unit%20ByteSwitch（U191，5V，
  PORT.A；STM32G031，8 个 DPDT 拨动开关 + 9×WS2812C，**I2C @0x46**，
  双 Grove 级联）。
- 驱动：public 无 Unit ByteSwitch 驱动；页面 Internal Firmware/Protocol
  表文本不可读（图片/乱码），无寄存器/键值表。
- Planned 契约：`switch-states`（8 bool）、`led-rgb`（9×24bit）、
  `queued-events`；QOM 无模型。**开关机械/光学/级联 NOT RUN**；0x46 冲突。

### 4.4 `bytebutton`（U192）

- 页面：https://docs.m5stack.com/en/unit/Unit%20ByteButton（U192，5V，
  PORT.A；8 按键 + 9×WS2812C，**I2C @0x47**）。
- 驱动：public 无 driver；Protocol 表在文本抓取中严重乱码，无键值/寄存器表。
- Planned 契约：`button-states`（8 bool）、`led-rgb`（9×24bit）、
  `queued-events`；无模型。**按键机械/RGB/级联 NOT RUN**；0x47 冲突。

### 4.5 `step16`（U198）

- 页面：https://docs.m5stack.com/en/unit/Unit_Step16（U198，5V，PORT.A；
  STM32G031，16 位 BCD 旋钮 + 7 段显示 + RGB，**I2C @0x48**，地址范围
  0x08-0x77 可配，掉电保存）。
- 驱动：public 无 driver；Protocol 表不可读，仅页面描述编码/显示/方向/
  RGB/地址可配。
- Planned 契约：`position`（0-15）、`direction`、`led-rgb`、`i2c-address`；
  无模型。**旋钮机械/7 段显示/编码抖动 NOT RUN**；0x48 冲突。

### 4.6 `timerpwr`（U189）

- 页面：https://docs.m5stack.com/en/unit/Unit-TimerPWR（U189，5V，PORT.A；
  STM32G031 + RTC + 升压 + INA3221，**I2C @0x56**；0.66" OLED 64×48、
  双按键、Type-C 充电、1.25-2P 电池）。
- 驱动：public 无 driver；Protocol 表未给出 I2C 命令/定时参数寄存器。
- Planned 契约：`power-state`、`schedule-on`/`schedule-off`、`battery-mv`、
  `input-current-ma`、`output-current-ma`；无模型。**电池/充电/升压/RTC/
  定时切换/OLED/热/安全 NOT RUN**；0x56 冲突。

### 4.7 `mq`（U199）

- 页面：https://docs.m5stack.com/en/unit/Unit_MQ（U199，5V，PORT.A；
  STM32G030 + MQ-5，**I2C @0x11** 可配；可读内部参考电压/传感器电压/
  12-bit/8-bit ADC/firmware/热敏温度；连续/间歇加热模式）。
- 驱动：public 无 driver；页面 Protocol 表/加热时序图未给出完整寄存器表。
- Planned 契约：`sensor-mv`、`reference-mv`、`adc12`、`adc8`、
  `temperature-c`、`firmware-version`、`heating-mode`；无模型。
  **气体浓度/预热/加热/热学 NOT RUN**；0x11 冲突。

### 4.8 `8servos2-chain`（U223）

- 页面：https://docs.m5stack.com/en/unit/Unit_8Servos2-Chain（U223，
  DC9-24V/5V；STM32G031；8 通道 servo/digital/ADC/RGB/PWM；**UART Chain
  系列级联协议**，双 Grove IN/OUT；INA199 电流检测）。
- 驱动：public 无 driver；页面指向 Internal Firmware/Protocol 外部文档，
  无 Chain 帧/寄存器表。
- Planned 契约：`channel-modes`、`servo-angles`、`adc-values`、
  `rgb-leds`、`current-ma`；无模型。**servo/ADC/PWM/9-24V/INA199/
  级联 NOT RUN**；UART 与其它 Unit 冲突。

### 4.9 `cat1-cn`（U204）

- 页面：https://docs.m5stack.com/en/unit/Unit_Cat1-CN（U204，5V，PORT.C
  黄=UART_RX 白=UART_TX；ML307R-DL LTE Cat.1，B1/B3/B5/B8/B34/B38/B39/
  B40/B41；**UART 115200 8N1 AT**；TCP/SSL/HTTP/MQTT，最大 6 socket）。
- 驱动：public 无 Unit Cat1 driver；页面 Protocol 为外部 AT 手册，未给
  完整 URC/命令顺序。
- Planned 契约：`responses-hex`、`tx-hex`、`frames-sent`、
  `frames-injected`；QEMU 可复用 UART fixture responder（仅字节层）。
  **蜂窝 RF/SIM/网络/运营商认证/TLS/MQTT NOT RUN**；PORT.C 冲突。

### 4.10 `chainbus`（U212）

- 页面：https://docs.m5stack.com/en/unit/Unit_ChainBus（U212，5V；
  STM32G031；2×UART Chain IN/OUT + 1×多功能扩展 I2C/GPIO/ADC/NVIC；
  **UART 115200 8N1**；RGB 状态灯）。
- 驱动：public 无 driver；页面 Protocol 指出 Chain UART + 扩展口功能，
  但无完整帧/寄存器表。
- Planned 契约：`chain-uid`、`version`、`link-devices`、`heartbeat`、
  `i2c-address`、`gpio-levels`、`adc-values`；无模型。
  **Chain 拓扑/心跳/协议转换/GPIO/ADC/NVIC NOT RUN**；UART 冲突。
- 判定：虽为总线转换器，但提供 UART/I2C/GPIO/ADC 数据面且为 Unit 实体，
  归 b 而非 c；不建模型。

## 5. c 类：明确不可接入（25 款，不登记）

以下产品只写边界结论，不进入 catalog/profile，不写草稿。原因：不是
Grove/Unit 数据面 attachment，或没有可注入/可观测的 Unit 控制接口。

### 5.1 Camera/vision 模块（14 款）

| Unit | SKU | 边界理由 |
| --- | --- | --- |
| `cams3-5mp` | U174-B | ESP32-S3 5MP camera board：CSI/DVP/JPEG/ISP 与相机传感器，不是 Unit 外设 attachment；无官方 Unit 驱动/寄存器表 |
| `poe-cam-w-v11` | U121-B-V11 | PoE camera（OV2640/WiFi），图像/网络设备，非 Unit 数据面 |
| `poe-cam-w` | U121-B | 同上原始 OV2640 版本 |
| `unitv-ov7740` | U078-C | UnitV Linux/vision camera（OV7740），USB/MIPI/CSI 图像栈，不是 Unit |
| `unitv-m12` | U078-V-M12 | UnitV M12 lens camera，同上 |
| `unitv2` | U078-D | UnitV2 Linux AI camera，Linux/ISP/USB，不是 Unit 数据面 |
| `unitv2-usb` | U078-USB | UnitV2 USB camera 形态，同上 |
| `unitv2-m12` | U078-M12 | UnitV2 M12 lens，同上 |
| `timercamera-f` | U082-F | TimerCamera-F ESP32 camera，图像/电池/定时，不是 Unit |
| `timercamera-x` | U082-X | TimerCamera-X，同上 |
| `timercamera` | U082 | TimerCamera 裸板，同上 |
| `m5camera-x` | U038 | M5Camera-X ESP32 camera，同上 |
| `m5camera` | U017 | M5Camera 原始版本，同上 |
| `esp32cam` | U007 | ESP32CAM 原始版本，同上 |

共同边界：这些是完整 camera/controller 板，图像数据走 DVP/CSI/ISP/JPEG
或 USB/Linux 栈，不是 Grove Unit 的 I2C/UART/GPIO/RMT 数据面；本仓库的
Unit 模型框架无法在不伪造图像栈的情况下登记，且没有官方 Unit driver。
官方页面/产品目录证据：`products.json` 对应 `officialDocs`，页面均描述
camera/vision 产品而非 Unit 外设。

### 5.2 Controller / PoE / gateway 模块（4 款）

| Unit | SKU | 边界理由 |
| --- | --- | --- |
| `poesp32` | U138 | PoE ESP32 控制器/网络模块，需 PoE/以太网/控制器角色，不是 Unit 外设 |
| `c6l` | U202 | ESP32-C6 控制器/LTE? 开发模块（带天线），属于主控板而非 Unit 数据面 |
| `gateway-h2` | U195 | ESP32-H2 gateway/Thread 模块，属于网络网关控制器 |
| `poe-p4` | U213 | ESP32-P4 PoE 控制器模块，属于主控/PoE 板卡 |

共同边界：这些是 controller/gateway/PoE 模块，提供主控/网络角色而非
Grove Unit 数据面；没有 Unit driver，也不应以 Unit attachment 建模。

### 5.3 Passive / 转接 / 无产品实体（7 款）

| Unit | SKU | 边界理由 |
| --- | --- | --- |
| `rca` | U155 | RCA 音视频被动转接，无地址/数据面 |
| `unit-396` | U020 | HY2.0-4P→HT3.96 被动端子转接（页面明确为 converter），无地址/数据面 |
| `typec-to-grove` | U151 | Type-C→Grove 被动转接，无地址/数据面 |
| `grove-to-grove` | U148 | Grove 延长/转接，无地址/数据面 |
| `proto` | U022 | Proto 原型板，无固定外设数据面 |
| `mini-proto` | U064 | Mini Proto 原型板，无固定外设数据面 |
| `m5-bit` | A051 | M5Bit 被动/bit 转接，无地址/数据面 |

共同边界：passive 转接/原型板没有可控/可读的 Unit 寄存器或帧格式；
登记为 Unit 会伪造不存在的接口。官方页面/产品目录证据：`products.json`
对应条目与官方页面描述（如 unit-396 明确 “HY2.0-4P to HT3.96 converter”）。

## 6. 预计总登记数与收口

- 当前 catalog：142（141 个 unit 产品 + `servo8-hat`）。
- 本批 a+b：**18 款**（a 7 + b 11）→ 预计总登记 **160**。
- c：25 款不登记，但有明确边界结论。
- 产品覆盖：159 个 unit 产品登记 + 25 个 c = **184/184**。
- 收口后剩余产品数 = 0；之后只需按 a 类优先级实现数据面，b 类按需补
  驱动/协议后再升级。

## 7. 引用与抓取记录

| 页面 | URL | 用途 |
| --- | --- | --- |
| DCSSR | https://docs.m5stack.com/en/unit/DCSSR%20Unit | I2C 0x50/Modbus 0x04、10A/24-220V |
| INA226-1A | https://docs.m5stack.com/en/unit/Unit_INA226-1A | 0x41、±1A/80mΩ |
| DoF6 | https://docs.m5stack.com/en/unit/Unit_DoF6 | BMI270 0x68/0x69、量程 |
| DoF9 | https://docs.m5stack.com/en/unit/Unit_DoF9 | BMI270+BMM350 0x14 |
| DoF10 | https://docs.m5stack.com/en/unit/Unit_DoF10 | BMI270+BMM350+SPA06 0x76 |
| ASR | https://docs.m5stack.com/en/unit/Unit_ASR | CI-03T、115200、AA55 命令表 |
| Puzzle | https://docs.m5stack.com/en/unit/Unit-Puzzle | 64×WS2812E、PORT.B 单线 |
| Roller485 | https://docs.m5stack.com/en/unit/Unit_Roller485 | RS485/I2C 0x64 电机 |
| Roller485-Lite | https://docs.m5stack.com/en/unit/Unit-Roller485%20Lite | Lite 差异 |
| RollerCAN-Lite | https://docs.m5stack.com/en/unit/Unit-RollerCAN%20Lite | CAN/I2C 0x64 |
| ByteSwitch | https://docs.m5stack.com/en/unit/Unit%20ByteSwitch | 0x46、8 开关+9 RGB |
| ByteButton | https://docs.m5stack.com/en/unit/Unit%20ByteButton | 0x47、8 按键+9 RGB |
| Step16 | https://docs.m5stack.com/en/unit/Unit_Step16 | 0x48、16 位 BCD |
| TimerPWR | https://docs.m5stack.com/en/unit/Unit-TimerPWR | 0x56、INA3221/RTC |
| MQ | https://docs.m5stack.com/en/unit/Unit_MQ | 0x11、MQ-5/ADC/加热 |
| 8Servos2-Chain | https://docs.m5stack.com/en/unit/Unit_8Servos2-Chain | Chain UART/8 通道 |
| Cat1-CN | https://docs.m5stack.com/en/unit/Unit_Cat1-CN | ML307R-DL/115200 AT |
| ChainBus | https://docs.m5stack.com/en/unit/Unit_ChainBus | Chain UART/扩展 I/O |
| c 类 | `products.json` 对应 `officialDocs` | camera/controller/passive 产品页面描述 |

冻结驱动证据：`unit/acssr.py:15/84/156`、`unit/__init__.py:9/156`；
`mini-imu-pro` 0145 的 `US_BMI270`（BMM350 仍无驱动/寄存器表）；
batch8/9 的 UART fixture responder 与 RMT LED 捕获作为 a 类复用建议。

以上是研究结论，不构成实现/证据承诺；a 类实现前仍需按 batch1-8 gate 采集
guest/Device Service 证据，b 类需先补驱动或内部固件协议，c 类不进入
Unit 运行时。
