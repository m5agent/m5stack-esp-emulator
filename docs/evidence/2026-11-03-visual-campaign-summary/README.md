# 视觉主机与 Unit 接入战役最终汇总（2026-11-03）

本页收口两条工作流：**视觉库存里剩余仅视觉主机的逐型号接入**与**Unit
协议/数据面接入**。它是汇总入口，不替代各次 evidence、当前状态页或验证台账；
动态设备/Unit 计数以 `docs/project-snapshot.md` 与 catalog/profile 为准。

- 当前设备登记：**33 台**（Device Service 可创建 32 台）。
- 视觉库存：**38 款主机、184 款 Unit**；仍有 **5 款主机仅视觉**
  （全部为 boundary-only/composition-only，见下）。
- Unit catalog：**160 条**（159 个 unit 产品 + `servo8-hat` HAT 口径差）；
  **129 implemented/partial + 31 planned**；另有 **25 款 c 类明确边界**不登记。
  184 个 unit 产品 = 159 登记产品 + 25 c 类边界，**184/184 全覆盖**。

> 原计划写“150 款未登记 Unit 目标”；收口时登记到 **160**，因为 a/b 类研究
> 把 18 款可登记产品纳入 catalog，并新增 25 款 c 类边界；这不是把 c 类强登。

## 1. 视觉主机：13 款目标收口

用户目标是让视觉库存里“有外壳、无运行登记”的主机尽可能获得独立虚拟运行
身份。最终 **9 个独立 host** 完成同 guest 原厂固件路径接入，其余按 **5 项
边界决策**处理（其中 3 个是已接入控制器的套件组合件，不新增 host）。

| # | 主机 | 接入结果 | 证据 |
| --- | --- | --- | --- |
| 1 | AtomS3U（`atoms3u`） | 官方 UIFlow2 启动、GPIO41 按键、GPIO35 WS2812 RMT；IR/PDM/Grove Unit 未覆盖 | [atoms3u-host](../2026-11-02-atoms3u-host/README.md) |
| 2 | Atom VoiceS3R（`atom-echos3r`） | 官方启动、128×128 面板、Speaker/I2S1 DMA 非静音 PCM；功放使能/IR/麦克风/Grove Unit 未覆盖 | [atom-echos3r-host](../2026-11-02-atom-echos3r-host/README.md) |
| 3 | AtomS3R-CAM（`atoms3r-cam`） | 启动、板级 id 144、显示初始化、软件 SCCB/DVP 相机数据面；多帧流/IR/光学未覆盖 | [atoms3r-cam-geometry](../2026-11-02-atoms3r-cam-geometry/README.md)、[camera SCCB](../2026-11-02-atoms3r-cam-sccb/README.md) |
| 4 | AtomS3R-M12（`atoms3r-m12`） | 共享官方 UIFlow2 CAM-M12 镜像；OV3660 0x3c 识别、QQVGA/QVGA/VGA/HD 帧与 5 帧流；MJPEG/UVC/IR/光学未覆盖 | [atoms3r-m12-host](../2026-11-02-atoms3r-m12-host/README.md) |
| 5 | AtomU（`atomu`） | 官方 UIFlow2 启动、板级 id 130、GPIO27 SK6812 RMT、QMP GPIO39 按键、Grove I2C 扫描；PDM/IR/Grove Unit 未覆盖 | [atomu-host](../2026-11-02-atomu-host/README.md) |
| 6 | Atom Echo（`atom-echo`） | 官方启动、板级 id 142、SK6812、按键、Grove I2C、NS4168 I2S1 PCM、SPM1423 PDM RX；模拟声学/IR/Grove Unit 未覆盖 | [atom-echo-host](../2026-11-02-atom-echo-host/README.md) |
| 7 | Basic v2.7（`basic-v27`） | classic ESP32 启动、板级 id 1、ILI9342C 320×240、A/B/C 注入、IP5306 0x75 寄存器、I2S0 DAC PCM；PMIC 电芯/电气/microSD/背光/Grove Unit 未覆盖 | [basic-v27-host](../2026-11-02-basic-v27-host/README.md) |
| 8 | M5Stick（`m5stick`） | 官方 EasyLoader FactoryTest 启动、SH1107 初始化流/GDDRAM；**工厂固件 legacy I2C FIFO 路径未完成，MPU 探测/按键/最终 UI blocked**；同 machine generic fixture 另证 MPU9250/IP5306/按键 | [m5stick-host](../2026-11-02-m5stick-host/README.md) |
| 9 | M5StickT2（`stickt2`） | FLIR Lepton VoSPI/CCI、ST7789 135×240、编码器 QOM、自建 bare-metal probe 3 帧热帧；官方 demo 热成像/UI 路径未完成 | [stickt2-host](../2026-11-02-stickt2-host/README.md) |

### 边界决策（5 项，不新增 host）

| 对象 | 决策 | 原因 |
| --- | --- | --- |
| AtomS3R-Ext（C126-Ext） | **boundary-only** | 无 Ext 专属官方固件/board profile；无屏 + Proto 扩展板与 AtomS3R 不同，不能用 AtomS3R 固件/身份冒充 |
| AtomS3R-AI Chatbot（K147） | **composition-only** | AtomS3R + Atomic Voice Base A149 组合件；官方只有控制器应用固件，无独立 host alias |
| AtomS3R-CAM AI Chatbot（K147-CAM） | **composition-only** | AtomS3R-CAM + A149 组合件；无独立 host alias，复用控制器 + base 数据面 |
| AtomS3R-M12 Volcengine Kit（D062-M12） | **composition-only** | AtomS3R-M12 + A149；Volcengine 固件是应用/测试固件，不构成新 host |
| StickV（K027） | **boundary-only** | K210/RV64GC + OV7740/MaixPy，非 ESP32 后端；M5Burner/UIFlow2/GitHub 无该板固件 |

完整判定口径、M5Burner/GitHub/board 检索结果与“准确该板固件”规则见
[主机边界决策](../../plans/2026-11-02-host-boundary-decisions.md)。M5Stick 的工厂
固件路径仍是 **blocked/partial**，不因“host 已登记”写成完整 PASS。

## 2. Unit：150 目标 → 160 登记、184/184 全覆盖

10 个研究批（每批 12 款）与对应实现/证据 PR：

| 批 | 研究 PR | 实现 PR | 证据 PR | 结果 |
| --- | --- | --- | --- | --- |
| 1 | #83 | #85 | #86 | 12 款研究；A/B/C 类建模与首批 guest 证据 |
| 2 | #99 | #100 / #101 | #102 / #105 | 12 款；batch2a/2b 双段实现与证据 |
| 3 | #104 | #106 / #107 | #110 | 12 款；3A/3B + 3C 实现，寄存器证据 |
| 4 | #108 | #109 / #111 | #115 | 12 款；4A/4B + 4C 实现与证据 |
| 5 | #112 | #113 / #116 | #121 | 12 款；5A/5B 实现与 8 款 guest 证据 |
| 6 | #118 | #119 / #124 | #125 / #131 | 12 款；6A/6B 实现，分两段证据 |
| 7 | #123 | #126 / #129 | #137 | 12 款；7A/7B 实现，8 款 guest 证据 |
| 8 | #128 | #130 / #134 | #144 | 12 款；8A/8B 实现，12 款 guest 证据 |
| 9 | #133 | #135 / #139 | —（无 guest 证据） | 12 款；9A/9B 仅 planned 契约/字节层 |
| 10 | #140 | #142 | #146 | 收口批 43 款分类；18 款登记，6 款 guest 证据 |

配套 patch 链与 recon PR 不在本表重复，见
[`patches/qemu-m5stack-peripherals/README.md`](../../../patches/qemu-m5stack-peripherals/README.md)
与验证台账。各批 evidence 页入口：

- 1：[unit-batch1](../2026-11-02-unit-batch1/README.md) / [bclass](../2026-11-02-unit-bclass/README.md) / [cclass](../2026-11-02-unit-cclass/README.md)
- 2：[unit-batch2](../2026-11-02-unit-batch2/README.md) / [batch2b](../2026-11-02-unit-batch2b/README.md)
- 3：[unit-batch3](../2026-11-02-unit-batch3/README.md)
- 4：[unit-batch4](../2026-11-02-unit-batch4/README.md)
- 5：[unit-batch5](../2026-11-02-unit-batch5/README.md)
- 6：[unit-batch6](../2026-11-02-unit-batch6/README.md) / [batch6b](../2026-11-03-unit-batch6b/README.md)
- 7：[unit-batch7](../2026-11-03-unit-batch7/README.md)
- 8：[unit-batch8](../2026-11-03-unit-batch8/README.md)
- 9：研究页 [batch9-protocols](../../unit-research/2026-11-03-batch9-protocols.md) / 实现状态 [batch9-impl](../../unit-research/2026-11-03-batch9-impl-status.md)（无 guest 证据）
- 10：[unit-batch10](../2026-11-03-unit-batch10/README.md) / 研究页 [batch10-protocols](../../unit-research/2026-11-03-batch10-protocols.md)

### 2.1 证据发现的真实模型 bug（不掩盖）

| 发现 | 修复/影响 |
| --- | --- |
| BH1750 命令掩码被误当连续测量位 | `0120` 修正 dlight 命令判定，否则 guest 读数模式错误 |
| MCP4725 fast-mode 写事务处理 | `0127` 修正，DAC 快写路径可被 guest 驱动验证 |
| AMeter EEPROM 记录跨距/布局 | `0128` 按官方记录跨距修正；`0129` 修正 batch2b 写偏移 |
| Vmeter 默认配置/量程 | `0133` 修正默认配置，guest 读到官方默认而非模型自定值 |
| batch5：op90 digital-level、RTC 停止时钟写回、TMOS 状态/页、KMeter fixture 同步 | `0141` 四个模型 bug |
| batch6 首批：mini-scales readfrom_mem 指针相位/button-pressed 别名、mini-imu 量程同步 | `0144` 三个模型 bug |
| batch6 剩余：Thermal2 fixture 槽位、UWB/DMX/Finger idle arming、FPC1020A 多帧注入 | `0147` |
| batch7：UART 应答器 TX 捕获后未 arm idle、ASR650x RX 路由未命中 | `0150`；否则 CATM/LoRaWAN 每条 AT 超时、注入字节进不了 guest RX |
| batch8：LCD read-after-command 事务跨写/读两段 | `0153`；否则官方 LCDUnit init 读回 0 |
| batch10：BMI270 INTERNAL_STATUS 未置 init-complete、TEMP 0x22 读法/端序不符 | `0154`；否则 generic BMI270 驱动初始化超时、温度读错 |

这些是**模型 fixture/语义 bug**，修复后仍只绑定对应 guest/QOM 证据；不能
外推为物理传感器/执行器 PASS。

## 3. DEFER / BLOCKED / planned-only 清单（31 planned）

### 3.1 DEFER / BLOCKED（7）

| Unit | 状态 | 原因 |
| --- | --- | --- |
| `unit-id` U124 | BLOCKED | guest `IDUnit` 找到 0x35，但冻结 ATECC608B 驱动每条命令前 wake 写 I2C 地址 0x00，绑定 0x35 的从机收不到；不伪造 revision/serial/random |
| `mini-bps-v11` U090-B | DEFER | QMP6988 页面/I2C 索引 0x56 vs 冻结驱动 0x70（env-iii 也用 0x70），地址无法确证；不猜地址、不建模型 |
| `mini-pdm` U089 | DEFER | 无 public Unit PDM 驱动；SPM1423 PDM RX 是板级 I2S，不是 Unit attachment；不伪造 PCM |
| `mini-can` U179 | BLOCKED | Unit runtime 无 CAN attachment/帧 lane，session 被 `contract is incomplete` 拒绝 |
| `lorawan-us915` U184-US915 | BLOCKED | 冻结 `unit/lorawan.py` 继承 ASR650x `LoRaWAN_470`，产品为 STM32WLE5/RAK3172；guest 命令被拒绝 |
| `can` U085 | BLOCKED | 0145 仅有 CanBusClient QOM 观测/inject-hex；guest TWAI/CAN 帧方向、过滤、位定时、外部收发器/仲裁未建模 |
| `mini-imu-pro` U171 | planned | BMI270 init burst accepted 不执行、BMM150 简化 aux；无 guest 证据，运动/磁力物理 NOT RUN |

### 3.2 已有模型但无 guest 证据（7，planned）

`glass`、`rf433t`、`rf433r`、`lorawan-as923`、`lorawan-eu868`、
`audioplayer`、`fingerprint2`：QOM offline smoke/planned 实现存在，但没有
同 guest Device Service evidence，不能升 implemented；RF/显示/音频/指纹/蜂窝
语义 NOT RUN。

### 3.3 planned-only driver-gap（17）

`cardkb2`（I2C 地址/UART 帧未知、PORT.CUSTOM G26/G25）、
`8servos2-i2c`（0x25-0x34、内部固件寄存器表不可读）、
`bmm350`（0x14、无 driver/寄存器表）、`ina226-10a`（0x41、无 datasheet 寄存器表）、
`ina226-1a`（0x41、同上）、`rollercan`（0x64+CAN、内部协议未公开）、
`roller485`/`roller485-lite`（RS485/I2C 0x64 电机、协议外部）、
`rollercan-lite`（CAN/I2C 0x64）、`byteswitch`（0x46、开关表不可读）、
`bytebutton`（0x47、按键表不可读）、`step16`（0x48、位置/配置表不可读）、
`timerpwr`（0x56、RTC/INA3221/定时电源表不可读）、`mq`（0x11、MQ-5/加热表不完整）、
`8servos2-chain`（UART Chain、帧表外部）、`cat1-cn`（ML307R AT/URC 外部）、
`chainbus`（Chain UART/扩展表外部）。
全部只登记 planned 契约 + blocker，**不建 QEMU 模型、不猜寄存器**。

## 4. 边界与不可继承结论

- **virtual-device validation ≠ hardware validation**：本页所有 PASS 都是
  QEMU/Device Service 虚拟设备结果，不是光学、声学、机械、电气、RF 测量。
- **PORT.B/C 替换**：核心 host 只准入 cores3 PORT.A；puzzle(PORT.B)、
  asr/lorawan/catm/8servos2-chain 等 PORT.C 的 session 使用 cores3 PORT.A
  harness，report 记录 `official_port`/`runtime_port_substitution`，不能把
  harness 当作产品 PinMap 等价。
- 地址冲突仍显式保留：0x50（dcssr/acssr）、0x68（BMI270/mini-imu 系）、
  0x14（BMM350/dof9/dof10/bmm350）、0x76（SPA06/BMP280/env 系）、
  0x46/0x47/0x48/0x56/0x11/0x64 等；一总线一 Unit。
- 光学/SSR 电气/隔离/电机 FOC/键程/传感精度/RF/蜂窝/GNSS/音频/语音/电池/
  热等语义全部 **NOT RUN**；RF 类（catm/catm-gnss/lorawan/cat1-cn）只到
  UART 字节层。
- 浏览器准入、WASM、native、hardware 各自独立；本页不把 native PASS 拼接
  为浏览器或硬件 PASS。
- c 类 25 款（camera/vision 14、controller/PoE 4、passive 7）只写边界，
  不登记；见 [batch10 protocol §5](../../unit-research/2026-11-03-batch10-protocols.md)。

## 5. 相关入口

- 当前能力与边界：[项目当前状态](../../project-status.md)
- 未完成/DEFER：[项目 Backlog](../../project-backlog.md)
- 动态计数：[项目快照](../../project-snapshot.md)
- 历史验证：[验证证据台账](../../validation-ledger.md)
- 视觉主机计划：[剩余视觉主机与 Unit 计划](../../plans/2026-11-02-remaining-visual-hosts-and-units.md)、
  [classic 主机](../../plans/2026-11-02-classic-hosts.md)、
  [主机边界决策](../../plans/2026-11-02-host-boundary-decisions.md)
- Unit 研究/契约：`docs/unit-research/2026-11-02-batch1..7`、
  `docs/unit-research/2026-11-03-batch8..10`
