# 文档导航与新鲜度规则

日期：`2026-11-04`

本页只维护阅读顺序、职责和新鲜度。动态测试计数、设备/Task 计数以及
“非历史页是否落后于当前事实日期”由[自动项目快照](project-snapshot.md)
生成；当前能力结论在[项目当前状态](project-status.md)，带日期的历史快照只在
[验证证据台账](validation-ledger.md)追加。这里不把“测试通过”写成
“全部功能或真机通过”。

项目文档很多，但不是所有页面都描述“当前能力”。本页定义阅读顺序、文档职责
和新鲜度规则，避免把历史排障、计划或单次证据误当成今天的实现状态。

## 五分钟阅读顺序

只想知道“现在做到哪、还差什么”时，不需要从头读所有专题：

1. [工程交接总览](engineering-handoff.md)：当前工作、代码边界和下一步；
2. [项目当前状态](project-status.md)：已经具备的能力与不可继承边界；
3. [项目 Backlog](project-backlog.md)：仍未完成的任务、依赖和验收；
4. [验证证据台账](validation-ledger.md)：上述结论对应的日期化 evidence；
5. 需要改代码时再读[代码与验证入口地图](code-map.md)和相关专题页。

文档按“事实层级”使用，而不是按修改时间判断可信度：

| 层级 | 可以回答什么 | 不能回答什么 |
| --- | --- | --- |
| 当前事实 | `project-status.md` 描述当前能力和边界 | 具体历史轮次、失败 control |
| 待办 | `project-backlog.md` 描述未完成工作和验收 | 已完成能力的完整证据 |
| 生成快照 | `project-snapshot.md` 汇总动态计数和新旧日期 | 人工判断、硬件结论 |
| 契约 | API、Manifest、统一运行时和部署页面定义稳定接口 | 今天某项固件是否 PASS |
| 专题/历史 | 解释某条实现、根因或单次验证 | 不能覆盖当前状态页；即使页首日期较新，也要看 evidence 日期 |

页首“最近核对”表示维护者已确认该页与当前入口不冲突，不表示页内所有底层
矩阵都在当天重跑。页内固件 SHA、轮次、截图和失败 control 只覆盖其 evidence
日期；看到 `PASS`、`current` 或 `latest` 时，必须继续核对它指向的 artifact
和设备/profile。

Unit 历史 raw 归档已从源码交付外置，固定旧提交链接只用于历史审计；普通 CI
不下载归档，具体保留范围与显式验证入口见[证据保留规则](evidence-retention.md)。
Core2 legacy 的最新 status/CAS 诊断见
[RDSR 与锁竞争关联](evidence/2026-10-29-core2-legacy-status-cas/README.md)；
`0088` 的跨核 CAS 调度 A/B 见
[contended-CAS scheduler](evidence/2026-10-29-core2-contended-cas-scheduler/README.md)；
这些是历史排查证据，不单独证明 legacy 启动通过。当前原厂 normal-WDT startup 的限定通过见
[WDT level delivery 后续证据](evidence/2026-10-30-core2-legacy-wdt-level-delivery/README.md)，
setup/REPL、任意应用与物理等价仍需分别验证。

浏览器低帧率、正常时钟候选与逐设备准入按
[WASM 性能与多设备计划](plans/2026-10-29-wasm-performance-devices.md)推进；
2026-11-03 的本地/浏览器同固件性能修复按
[性能修复与对照计划](plans/2026-11-03-emulator-performance.md)执行，
[性能修复与对照证据](evidence/2026-11-03-emulator-performance/README.md)分别记录浏览器与原生结果，
[QEMU 执行优化决策](adr/0001-qemu-browser-hot-block-jit.md)保留单一 QEMU TCI，不引入第二套 JIT 后端。
2026-11-04 的[全19板默认UIFlow与输入验收](evidence/2026-11-04-browser-uiflow-all19-acceptance/README.md)在V6本地独立完成60例，
覆盖编辑器、声明按键/键盘/机身触摸输入与原固定示例；[设计](plans/2026-11-04-uiflow-browser-workbench-design.md)保留范围与路径。
逐板性能、长期稳定性及正式HTTPS仍独立验收，本地功能结果不关闭原策略C根因。
[当前发布包启动调查](evidence/2026-11-04-browser-startup-investigation/README.md)
保留 Atom Matrix / StickC Plus 基线、未采用候选和早启 CDP 诊断，不授予新默认固件或全设备提速。
[host poll 唤醒限定证据](evidence/2026-11-04-wasm-wakeable-poll/README.md)
记录 fresh75、真实 SDK 正向控制及两板原 Flash cold 15/26 项通过；
[后续四组同页对照](evidence/2026-11-04-wasm-wakeable-poll/warm-summary.json)已完成，
75 两组 warm 更慢，纯 cache 暖启动收益与 pthread cancellation 仍未建立；
不授予全型号、新默认镜像或线上提速。
[UIFlow 工作台限定验收](evidence/2026-11-04-browser-uiflow-workbench/README.md)
保留首次 UART signed-array 失败、修复后的 smoke、CoreS3 完整编辑器以及独立组合/布局证据；
[CoreS3 正常钟后续验收](evidence/2026-11-04-browser-uiflow-workbench-wallclock/README.md)
记录同 Flash/WASM 的 exact-SHA 候选 54/54 与单次 `10.971 s` ready。
[StamPLC 工作台复位证据](evidence/2026-11-04-stamplc-workbench-reset/README.md)
保留原多指令策略复位异常与精确策略 54/54；`RUNTIME-07` 根因仍开放。
[输入专项证据](evidence/2026-11-04-browser-input-acceptance/README.md)分开圆屏观察器、PM1 应用配置和 Cardputer IRQ/中断清理；
[Cardputer 复位调查](evidence/2026-11-04-cardputer-workbench-reset/README.md)保留后续越界与诊断边界，`RUNTIME-08` 根因仍开放。
[PaperColor 帧观察器证据](evidence/2026-11-04-papercolor-frame-oracle/README.md)保留 LCD 红色假设的失败；按 Spectra6 调色板与新帧序列独立验收。
[Paper PM1 应用配置](evidence/2026-11-04-paper-pm1-application/README.md)保留缺失 Python helper 的准备失败，分开公开 I2C 配置与原生按键事件结果。
[S3 工作台执行策略](evidence/2026-11-04-s3-workbench-execution-policy/README.md)保留 AtomS3 Lite 首启 PIF，并记录八款精确镜像的独立候选验收；`RUNTIME-09` 根因仍开放。
本地全19的最终范围见新独立记录；上述各历史记录仍只授予当时的限定结果，不改写原FAIL。
原生设备验证与浏览器准入分别绑定执行产物。测量与准入见
[浏览器性能证据](evidence/2026-10-29-wasm-performance-devices/README.md)，
SDK 候选见[LVGL 正常时钟证据](evidence/2026-10-29-browser-lvgl-wallclock/README.md)。
新增六板已按[后续 Xtensa 接入计划](plans/2026-10-29-wasm-remaining-xtensa.md)完成固定示例准入；
编译、文件组合、模型检查与最终单板浏览器准入分开记录，正式部署另验。

模型仓库新增的 21 款主机按[主机模型接入计划](plans/2026-10-29-expanded-host-models.md)
同步；当前视觉库存为 38 主机、184 Unit；设备登记 33 台、5 款视觉主机仅视觉，Unit catalog 160 条（**158 implemented/partial + 2 planned DEFER**）+ 25 c 类边界。
[逐板原厂固件验证](evidence/2026-10-29-expanded-hosts/README.md)记录输入、控制器与显示/LED，
仅模型、候选和通过的功能范围分别标注。
[AtomS3U 主机接入](evidence/2026-11-02-atoms3u-host/README.md)记录独立 `m5atoms3u`
板级的原厂固件启动、GPIO41 按键和 GPIO35 WS2812 RMT 限定通过，
IR、PDM 麦克风与 Grove Unit 数据面仍为未覆盖。
[Atom VoiceS3R 主机接入](evidence/2026-11-02-atom-echos3r-host/README.md)记录独立
`m5atomvoices3r` 的原厂固件启动、128×128 面板初始化和 Speaker/I2S1 DMA
非静音 PCM；功放使能、IR、麦克风与 Grove Unit 仍未覆盖。
[AtomS3R-CAM 主机接入](evidence/2026-11-02-atoms3r-cam-host/README.md)记录独立
`m5atoms3rcam` 的启动、板级识别 144、显示初始化和 GC0308 身份读取；
原厂 camera.init/capture 仍为 ESP_ERR_NOT_SUPPORTED，没有相机帧数据面。
[AtomU 主机接入](evidence/2026-11-02-atomu-host/README.md)记录独立 `m5atomu`
的官方 UIFlow2 启动、板级识别 130、GPIO27 SK6812 RMT、QMP 注入 GPIO39
按键回读与 Grove I2C 控制器扫描；SPM1423 PDM 麦克风、IR G12 与 Grove
Unit 数据面仍未覆盖。该板固件来自固定 SHA 的官方 GitHub release 资产。

[Atom Echo 主机接入](evidence/2026-11-02-atom-echo-host/README.md)记录独立
`m5atomecho` 的官方 UIFlow2 启动、板级识别 142、GPIO27 SK6812 RMT、
QMP 注入 GPIO39 按键回读、Grove I2C 控制器扫描、NS4168 I2S1 非静音
PCM 捕获与 SPM1423 PDM RX 注入路径；官方 C008-C 无板载 ES8311/I2C
codec，probe 如实记录 `ATOMECHO_ES8311 absent`。模拟声学、IR 与 Grove
Unit 仍未覆盖；固件来自固定 SHA 的官方 GitHub release 资产。

[AtomS3R-CAM 相机数据面闭环](evidence/2026-11-02-atoms3r-cam-sccb/README.md)记录软件 SCCB 根因（硬件 I2C hand-off 误关相机桥）与修复，官方 `camera.init()/capture()` 取得 320×240 RGB565 整帧；仅默认 QVGA 单帧、物理光学 NOT RUN。

[AtomS3R-CAM 相机几何与多帧流](evidence/2026-11-02-atoms3r-cam-geometry/README.md)记录非 QVGA 几何跟随（LCD_CAM 按 GC0308 window/subsample 寄存器锁存）与 5 帧流：QQVGA/240×240/QVGA/CIF/VGA 整帧 digest 与宿主重建一致，连续 5 帧互异且无撕裂；物理光学与运行中动态改尺寸 NOT RUN。

[AtomS3R-M12 主机接入](evidence/2026-11-02-atoms3r-m12-host/README.md)记录 OV3660 M12 相机主机：共享官方 UIFlow2 镜像（M5Burner 描述覆盖 AtomS3R-M12）自动探测 0x3c/PID 0x3660，QQVGA/QVGA/VGA/HD 帧与宿主重建一致、5 帧流互异；社区 `AtomS3R-CAM M12 User Demo` 黑盒确认 OV3660 控制面，其 MJPEG/UVC 数据面与物理光学 NOT RUN。

[M5StickT2 热成像主机接入](evidence/2026-11-02-stickt2-host/README.md)记录 classic ESP32 热成像主机：自建 bare-metal 探针经真实 HSPI/GPIO I2C/ST7789 控制器读取 FLIR Lepton 3.0 VoSPI 与 CCI，3 帧 guest FNV-1a digest 与宿主 fixture oracle 一致、0 包错误，面板截图与 encoder QOM 注入通过；官方 `StickT2 User Demo` 只到达 app 启动标记，其热成像/UI 路径与物理 LWIR 光学 NOT RUN。

剩余视觉主机与 Unit 接入的最终状态已收口，汇总见
[剩余主机与 Unit 接入计划](plans/2026-11-02-remaining-visual-hosts-and-units.md)。

剩余 classic/异构主机的接入决策（固件 SHA、镜像格式、QEMU 复用、GO/DEFER/NO-GO）见
[classic 主机可行性研究](plans/2026-11-02-classic-hosts.md)。

剩余仅视觉主机的最终边界决策（implemented / composition-only / boundary-only，含 M5Burner 与官方 GitHub release 检索记录、组合件判定和重开条件）见
[主机边界决策](plans/2026-11-02-host-boundary-decisions.md)。

Unit 第一批 12 款的官方驱动证据、寄存器/命令表与未确认项见
[Unit 第一批协议研究](unit-research/2026-11-02-batch1-protocols.md)；其中 A 类
5 款（`ssr`/`earth`/`hall`/`reflective-ir`/`vibrator`）已通过独立 Device Service
可见会话取得虚拟设备数据面证据，见
[Unit 第一批 A 类虚拟设备证据](evidence/2026-11-02-unit-batch1/README.md)，
B 类 4 款（`dlight`/`accel`/`4relay`/`weight-i2c`）的 I2C 事务数据面证据见
[Unit 第一批 B 类虚拟设备证据](evidence/2026-11-02-unit-bclass/README.md)。

Unit 第二批 12 款（`joystick`/`dac`/`watering`/`fader`/`bps`/`env`/`adc-v11`/`extencoder`/`ain4-20ma`/`acssr`/`ameter`/`gesture`）的官方驱动证据、寄存器/命令表、QEMU 复用建议与 unresolved 见
[Unit 第二批协议研究](unit-research/2026-11-02-batch2-protocols.md)；catalog 草稿见同目录 batch2 JSON，全部 planned。
Unit 第三批 12 款（`rfid`/`vmeter`/`scales`/`dac2`/`extio`/`adc`/`env-iv`/`co2`/`pbhub`/`tube-pressure`/`laser-rx`/`ultrasonic-io`）的官方驱动证据、寄存器/命令表、QEMU 复用建议与 unresolved 见
[Unit 第三批协议研究](unit-research/2026-11-02-batch3-protocols.md)；catalog 草稿见同目录 batch3 JSON，全部 planned。
Unit 第四批 12 款（`co2l`/`rs485-iso`/`laser-tx`/`neco`/`midi`/`weight`/`tof4m`/`bldc-driver`/`ac-measure`/`dds`/`gps`/`uhf-rfid`）的官方驱动证据、GPIO/RMT/UART/I2C 协议表、QEMU 复用建议（`rs485`/`co2`/`tof` 同族复用、HX711 位脉冲、NMEA/AT 帧注入、SHT4x/AC 市电/激光安全边界）与 unresolved 见
[Unit 第四批协议研究](unit-research/2026-11-02-batch4-protocols.md)；catalog 草稿见同目录 batch4 JSON，全部 planned。
Unit 第五批 12 款（`pahub-v20`/`pbhub-v11`/`8angle`/`kmeter-iso-v11`/`rtc`/`tmos-pir`/`rgb-led-10cm`/`neohex`/`op90`/`lora-e220-433`/`zigbee`/`nbiot2`）的官方驱动证据、I2C/GPIO-RMT/UART 协议表、QEMU 复用建议（PaHub 多总线、PbHub v1.1→0131、8Angle 寄存器组、RTC 虚拟时钟、黑白线 GPIO/RMT、UART 应答器）与 unresolved 见
[Unit 第五批协议研究](unit-research/2026-11-02-batch5-protocols.md)；catalog 草稿见同目录 batch5 JSON，全部 planned。
其中首批 5 款（`pbhub-v11`/`op90`/`rgb-led-10cm`/`8angle`/`kmeter-iso-v11`）已由 `0137` 接入 QEMU 数据面，实现状态、QOM fixture、QOM smoke 与 unresolved（PORT.B 主机限制、op90 极性、pbhub v1/v2 差异、8angle/kmeter 寄存器组）见
[Unit 第五批首批实现状态](unit-research/2026-11-02-batch5-impl-status.md)，与协议研究 §4.2/4.3/4.4/4.7/4.9/§5 对应。
Unit 第六批 12 款（`unit-id`/`mini-scales`/`thermal2`/`env-pro`/`mini-imu`/`qrcode`/`rgb-led-strip-50cm`/`op180`/`uwb`/`dmx`/`synth`/`finger`）的官方驱动证据、I2C/GPIO-RMT/UART 协议表、QEMU 复用建议（MiniScales→0x26 寄存器组、A093→fader RMT、OP180→limit/pir GPIO、Synth→midi TX 捕获、MPU6886/ATECC 复用、Thermal2 768×2B 帧、QRCode 16-bit 地址、UWB AT/DMX C 模块/FPC1020A 帧）与 unresolved 见
[Unit 第六批协议研究](unit-research/2026-11-02-batch6-protocols.md)；catalog 草稿见同目录 batch6 JSON，全部 planned。
Unit 第七批 12 款（`env-ii`/`mini-bps-v11`/`mini-imu-pro`/`hbridge-v11`/`cardkb-original`/`mini-tof-90`/`hex`/`mini-pdm`/`catm`/`catm-gnss`/`lorawan-cn470`/`can`）的官方页面/驱动 file:line、6×I2C+2×GPIO-RMT-PDM+3×UART+1×CAN 协议表、QEMU 复用建议（ToF→US_TOF、HBridge→0x20 模型+0x30 电流、CardKB→既有单字节控制、ENV-II SHT30/BMP280 复合、Hex→neohex RMT、Mini PDM→SPM1423 PDM RX、CatM/GNSS/LoRaWAN→UART responder、CAN→esp32s3.twai/CANBusState）与 unresolved（Mini BPS 0x56 vs 驱动 0x70、IMU-Pro aux、LoRaWAN STM32WLE5 vs ASR650x 驱动、CAN attachment）见
[Unit 第七批协议研究](unit-research/2026-11-02-batch7-protocols.md)；catalog 草稿见同目录 batch7 JSON，全部 planned。
Unit 第八批 12 款（`pahub-v21`/`lcd`/`oled`/`mini-oled`/`glass2`/`gps-v11`/`gps-sma`/`nbiot-cn`/`lora-e220-920`/`lorawan-us915`/`mini-can`/`mic`）的官方页面/驱动 file:line、5×I2C+5×UART+2×GPIO-CAN-ADC 协议/命令表、QEMU 复用建议（PaHub→CONTROL_PAHUB、LCD→I2C 命令/framebuffer slave、OLED/MiniOLED/Glass2→M5Unified display 组合、GPS→NMEA responder、NBIoT-CN→SIM7020 AT、LoRaE220-920→0xC0/C1、LoRaWAN-US915→AT responder、Mini CAN→esp32s3.twai/CANBusState、MIC→S3 SENS/SAR-ADC+GPIO）与 unresolved（显示 0x3C/0x3D/0x3E 三方冲突、GPS 页面 115200 vs 驱动 9600、LoRaWAN-US915 STM32WLE5 vs ASR650x 驱动错配、Mini CAN attachment、MIC 无 Unit 驱动）见
[Unit 第八批协议研究](unit-research/2026-11-03-batch8-protocols.md)；catalog 草稿见同目录 batch8 JSON，全部 planned。
Unit 第九批 12 款（`glass`/`cardkb2`/`8servos2-i2c`/`bmm350`/`ina226-10a`/`lorawan-as923`/`lorawan-eu868`/`fingerprint2`/`audioplayer`/`rf433t`/`rf433r`/`rollercan`）的官方页面、驱动-gap/组合证据、5×I2C+4×UART+2×GPIO-RF+1×I2C-CAN 的总线/地址/协议表、QEMU 复用建议与 unresolved（Glass 0x3D 显示组合；CardKB2 PORT.CUSTOM G26/G25+地址未知；8Servos2 0x25-0x34 内部固件；BMM350 0x14/INA226 0x41 寄存器手册缺失；LoRaWAN AS923/EU868 STM32WLE5 vs ASR650x；Fingerprint2 A-K323CP 无 Unit 驱动；AudioPlayer N9301 无命令表；RF433T/R GPIO bitstream；RollerCAN I2C 0x64/CAN 协议未公开）见
[Unit 第九批协议研究](unit-research/2026-11-03-batch9-protocols.md)；catalog 草稿见同目录 batch9 JSON，全部 planned。
Unit 第九批剩余 9 款的实现/契约状态见
[Batch-9 剩余实现状态](unit-research/2026-11-03-batch9-impl-status.md)：lorawan-as923/lorawan-eu868/audioplayer/fingerprint2 复用 0151 UART 字节层 fixture responder（无协议解码、无 guest 证据），
cardkb2/8servos2-i2c/bmm350/ina226-10a/rollercan 仅登记 planned 契约与 blocker（不建模型、不猜寄存器）；catalog/profile 133→142，全部 planned。
Unit 第十批为**收口研究**：剩余全部 43 款未研究 unit 产品分类完毕（a 可实现 7 款：dcssr/ina226-1a/dof6/dof9/dof10/asr/puzzle；b driver-gap 可登记 11 款：roller485/roller485-lite/rollercan-lite/byteswitch/bytebutton/step16/timerpwr/mq/8servos2-chain/cat1-cn/chainbus；c 明确不可接入 25 款：camera/Linux/controller/PoE 模块与 passive 转接），见
[Unit 第十批协议研究](unit-research/2026-11-03-batch10-protocols.md)；a/b 草稿见同目录 batch10 JSON（全部 planned，预计登记 142→160），c 类只写边界结论不登记；落地后 184 款 unit 产品将全部有登记或明确边界结论。
Batch-10 a/b 类 18 款已登记落地（catalog/profile 142→160，全部 planned），实现状态见
[Batch-10 a/b 登记与最小模型状态](unit-research/2026-11-03-batch10-impl-status.md)：dcssr/puzzle/dof6/dof9/dof10/asr 建最小模型（0152），ina226-1a 与 b 类 11 款仅登记 planned 契约；无 guest 证据，离线 QOM smoke 6/6 不是 functional PASS。
Batch-10 a 类 6 款虚拟设备证据见
[Unit 第十批 a 类虚拟设备证据](evidence/2026-11-03-unit-batch10/README.md)：dcssr（官方 DCSSRUnit）、puzzle（generic SK6812 64 灯 driver-gap）、dof6/dof9/dof10（仅 BMI270 子集，BMM350/SPA06 BLOCKED）、asr（raw UART AA55 字节层）各一个 cores3 可见会话全部 PASS；0154 修复 BMI270 init 状态与 0x22 温度别名；物理/光学/SSR/运动/磁力/气压/语音语义 NOT RUN。
Unit 第十二批 c 类 4 款见
[Unit 第十二批 c 类虚拟设备证据](evidence/2026-11-03-unit-batch12c-evidence/README.md)：8servos2-chain/chainbus 的 AA55 Chain 帧、cat1-cn 的 ML307R AT 字节层、mini-imu-pro 的 BMI270+BMP280 子集 4/4 PASS；0160 修复 data-less AA55 帧 length=3 被清缓冲的模型 bug；无 public Unit 驱动者标 driver-gap，物理/蜂窝/级联/运动语义 NOT RUN。
CAN / LoRaWAN lane 解锁与三款虚拟设备证据见
[Unit CAN/LoRaWAN 虚拟设备证据](evidence/2026-11-03-unit-can-lorawan/README.md)：`can`/`mini-can` 在 cores3 real TWAI + `m5-canbus` CanBusClient lane 上各一个可见会话 PASS（guest 发帧 `123#0102030405060708` 被观测、host `456#deadbeef` 经 QOM `inject-hex` 注入并由 guest TWAI 收到；冻结 release `unit/can.py` wrapper 不可用的问题如实记录并用同一官方 `m5can` C 模块取证），`lorawan-us915` 以已文档化 guest-side UART bootstrap 取得冻结 ASR650x 驱动的 AT 字节层 PASS（`AT+CWORKMODE`/`AT+DTRX`，`tx-hex`/frames 计数）；本次 lane 解锁只需 Unit runtime 契约 + probe，**无新增 QEMU 源码补丁**（canonical 35 层链不变）；CAN 电气/仲裁/隔离与 US915 AT 解码/Join/RF/FCC 全部 NOT RUN。
Unit Glass 的 BLOCKED 根因已由 task-75 定位并解锁：官方 M5GFX M5UnitGLASS 使用**自定义 STM32 REG_INDEX 寄存器协议**（0x00 clear/0x10 show/0x90 picture/0xB0 draw/0xC0 buzzer/0xD0 key/0xFE version），不是旧模型假设的 SSD1309 0x00/0x40 控制字节；补丁 0157 实现协议/QOM pages 后官方 GlassUnit guest 重跑 PASS（commands=4366、data-bytes=13144、pages=44），见
[Unit Glass 解锁证据](evidence/2026-11-03-glass-unblock/README.md)。
视觉主机与 Unit 接入战役已收口，最终汇总见
[视觉主机与 Unit 接入战役汇总](evidence/2026-11-03-visual-campaign-summary/README.md)：
9 个独立视觉 host 完成同 guest 原厂固件路径接入，5 项 boundary-only/composition-only；
Unit catalog 160 条（**158 implemented/partial + 2 planned DEFER**）+ 25 款 c 类边界，184/184 覆盖；canonical 41 层链（0120–0161，41/41 replay）。
Unit 第十一批 7 款已有模型 planned 款的 guest 证据见
[Unit 第十一批虚拟设备证据](evidence/2026-11-03-unit-batch11/README.md)：lorawan-as923/eu868（官方驱动字节层）、rf433t/r（machine.Pin bitbang/采样）、audioplayer/fingerprint2（raw UART 字节层）6 款 PASS；
同步；当前视觉库存为 38 主机、184 Unit；设备登记 33 台、5 款视觉主机仅视觉，Unit catalog 160 条（**158 implemented/partial + 2 planned DEFER**）+ 25 c 类边界。
glass 因参考 GlassUnit/M5.addDisplay 未产生模型可见 I2C 事务如实 **BLOCKED**（commands=0/data-bytes=0）；本批未需 0155 模型修复。
Unit catalog 160 条（**158 implemented/partial + 2 planned DEFER**）+ 25 款 c 类边界，184/184 覆盖。
Unit 第十一批为 **driver-gap 17 款官方协议网络研究**：用官方协议文档/上游 UIFlow2 master 驱动/厂商 datasheet 纠正此前“无公开协议”结论，17 款全部升级为 a/b（a 15 款：8servos2-i2c、8servos2-chain、bmm350、ina226-10a、ina226-1a、roller485、roller485-lite、rollercan、rollercan-lite、byteswitch、bytebutton、step16、timerpwr、mq、chainbus；b 2 款：cardkb2、cat1-cn；c 0 款），逐款给出寄存器/帧表、驱动 file:line、QEMU 数据面建议、fixture/可断言量与 unresolved，并给出推荐实现顺序（前 5：byteswitch+bytebutton、step16、timerpwr、mq、8servos2-i2c），见
[Unit 第十一批 driver-gap 协议研究](unit-research/2026-11-03-batch11-driver-gap-protocols.md)；协议字段草稿见同目录 batch11 JSON（全部 planned，未改 catalog/model/test）。

Unit batch-12b 的 10 款 driver-gap Unit 已按 batch-11 官方协议研究建**最小模型层**（reconcile11 后 patch `0159`；最终 canonical 41 层链至 `0161`）：
`bmm350`（0x14，Bosch Table 8，含 datasheet §9.2.3 的 2 dummy 字节读）、
`ina226-10a`/`ina226-1a`（0x41，TI Table 7-1，10A 5mΩ/0x0C80 与 1A 80mΩ/0x0800 参数化）、
`roller485`/`roller485-lite`/`rollercan`/`rollercan-lite`（0x64 I2C 寄存器子集）、
`8servos2-chain`（U223 Chain AA55 帧级 responder，设备类型 0x000C）、
`chainbus`（U212 Chain 帧级 responder，0x0006，I2C 转发 fail-closed）、
`cat1-cn`（ML307R-DL 最小 AT 命令/响应字节 responder）。其中 **7 款 I2C Unit**
（bmm350/ina226×2/roller×4）已由后续 guest 证据任务以 **raw `machine.I2C` 寄存器
探针**（无官方 Unit 驱动，driver-gap）取得 7/7 PASS 并升 profile implemented
+ hosts `cores3`；catalog 全部保持 partial（不升 simulated）。`8servos2-chain`/
`chainbus`/`cat1-cn` 仍保持 planned + hosts 空。RS485/CAN 帧层、FOC 电机物理、
级联拓扑、蜂窝 RF/SIM/网络/TLS 与全部电气语义 NOT RUN。实现状态与复现见
[Unit batch-12b 实现状态](unit-research/2026-11-03-batch12b-impl-status.md)，
guest 证据见
[Unit batch-12b 7 款 I2C guest 证据](evidence/2026-11-03-unit-batch12b-evidence/README.md)
（0x41 两款、0x64 四款地址互斥 → 每款独立 session；先取 ZIP 再 purge=0）。

C 类 3 款（`ncir2`/`extio2`/`hbridge`）的寄存器事务数据面证据见
[Unit 第一批 C 类虚拟设备证据](evidence/2026-11-02-unit-cclass/README.md)。
Unit 第二批前 6 款（`joystick`/`watering`/`fader`/`dac`/`bps`/`adc-v11`）的
GPIO/ADC/RMT 与 I2C 数据面证据见
[Unit 第二批前 6 款虚拟设备证据](evidence/2026-11-02-unit-batch2/README.md)。
Unit 第二批后 6 款（`env`/`ameter`/`extencoder`/`ain4-20ma`/`acssr`/`gesture`）的
双从机 I2C 与寄存器数据面证据见
[Unit 第二批后 6 款虚拟设备证据](evidence/2026-11-02-unit-batch2b/README.md)。
Unit 第三批全部 12 款（A+B 8 款 / C 4 款）的双树并行 QEMU 证据见
[Unit 第三批虚拟设备证据](evidence/2026-11-02-unit-batch3/README.md)；证据发现并修复了
0132/0133/0135 三个模型补丁（PbHub RGB 提交、Ultrasonic echo 断言、SCD40 序列号、
VMeter 默认配置、EXT.IO 读回、Scales RGB 写入）。
Unit 第四批全部 12 款（A+B 6 款 / C 6 款）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第四批虚拟设备证据](evidence/2026-11-02-unit-batch4/README.md)；证据发现并修复了
0138 的 AC Measure 视图/ASCII 偏移与 Weight HX711 pad-observer 断言两个模型 bug，
并在单次会话中验证 rs485-iso/laser-tx/co2l/neco/midi/tof4m/weight/bldc-driver/
ac-measure/dds/gps/uhf-rfid 的 guest 数据面。
Unit 第五批全部 12 款（A 5 款 / B 7 款）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第五批虚拟设备证据](evidence/2026-11-02-unit-batch5/README.md)；证据发现并修复了
0141 的 op90 digital-level 属性、RTC 停止时钟写回、TMOS 状态位/页读取与 KMeter
fixture 同步四个模型 bug，并在单次会话中验证 pbhub-v11/op90/rgb-led-10cm/8angle/
kmeter-iso-v11/pahub-v20/rtc/tmos-pir/neohex/lora-e220-433/zigbee/nbiot2 的 guest 数据面。
Unit 第六批首批 6 款（mini-scales/rgb-led-strip-50cm/op180/synth/mini-imu/env-pro）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第六批首批虚拟设备证据](evidence/2026-11-02-unit-batch6/README.md)；证据发现并修复了
0144 的 mini-scales 指针相位/button-pressed 别名与 mini-imu 量程同步三个模型 bug，并在
单次会话中验证 6 款的 guest 数据面；env-pro 只断言 identity/raw field bytes/QOM fixture，
guest 解码温/湿/压因 BME68x 补偿逆运算未建模而 NOT ASSERTED。
Unit 第六批剩余 6 款（unit-id/thermal2/qrcode/uwb/dmx/finger）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第六批剩余虚拟设备证据](evidence/2026-11-03-unit-batch6b/README.md)；证据发现并修复了
0145 的 Thermal2 fixture 槽位、UWB/DMX/Finger UART 应答器 idle arming 与 FPC1020A 多帧注入三个模型 bug，
thermal2/qrcode/uwb/dmx/finger 5 款 PASS，unit-id 因 ATECC 驱动 wake 写 I2C 地址 0x00 的 harness 限制如实 BLOCKED；
PORT.C 未准入使用 cores3 PORT.A harness；热/光/RF/生物/电气物理语义与 DMX512 电气行为全部 NOT RUN。
Unit 第八批全部 12 款（pahub-v21/gps-v11/gps-sma/lcd/oled/mini-oled/glass2/nbiot-cn/lora-e220-920/mic + mini-can/lorawan-us915）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第八批虚拟设备证据](evidence/2026-11-03-unit-batch8/README.md)；证据发现并修复了
0152 的 Unit LCD read-after-command 事务（冻结驱动 READ_ID 写读分离，原模型清空命令缓冲导致 init 失败），
10 款 PASS（显示三款用 M5.addDisplay 组合、显式地址记录 0x3C/0x3D 差异；GPS 页面 115200 vs 驱动 9600 unresolved；
UART 三款只断言字节层；mic 为 driver-gap 的 machine.ADC/Pin），mini-can 因 Unit runtime 无 CAN attachment lane、lorawan-us915 因 ASR650x 驱动未到达 Unit UART 均如实 BLOCKED；
PORT.B/C 未准入使用 cores3 PORT.A harness；显示光学/GNSS RF/蜂窝 RF/LoRaWAN RF/CAN 电气/声学语义全部 NOT RUN。
Unit ID（ATECC608A）此前因冻结驱动 wake 写 I2C 地址 0x00 而 BLOCKED，现已解锁并取得虚拟设备证据，见
[Unit ID 解锁虚拟设备证据](evidence/2026-11-03-unit-id-unblock/README.md)；补丁 `0156` 实现 wake-to-address-0
broadcast ACK、跨 wake 保留命令帧与冻结驱动精确 CRC，guest INFO revision=0x260 / READ serial fixture /
SHA / GEN_KEY public-key 与 QOM fixture 一致；全部为固定非敏感测试向量，真实密码学/密钥/证书
（ECDSA/AES/Trust&GO、key-slot locking、10Kb EEPROM）NOT RUN。
Unit 第七批 8 款（mini-tof-90/hbridge-v11/cardkb-original/env-ii/hex/catm/catm-gnss/lorawan-cn470）在单一 QEMU 构建上取得虚拟设备证据，见
[Unit 第七批虚拟设备证据](evidence/2026-11-03-unit-batch7/README.md)；证据发现并修复了
0145 batch7 UART 应答器的 TX 捕获后未 arm idle 响应体与 ASR650x RX 注入路由两个模型 bug（0149），
8 款 guest 会话全部 PASS 并升 profile implemented/catalog partial；`can` 因 CAN attachment/帧注入 gap 如实 BLOCKED，
`mini-bps-v11`/`mini-pdm` 保持 DEFER，`mini-imu-pro` 不在本批范围、保持 planned；
PORT.B/C 未准入使用 cores3 PORT.A harness 替换并记录；光学/电机/键程/传感精度/RF/蜂窝语义全部 NOT RUN。

Unit batch12a 7 款 driver-gap Unit（byteswitch/bytebutton/step16/timerpwr/mq/8servos2-i2c/cardkb2）已由 `0157` 接入 QEMU 寄存器文件数据面并登记 planned 契约（无 guest 证据、全部 planned），实现状态与边界见
[Unit batch12a 实现状态](unit-research/2026-11-03-batch12a-impl-status.md)。
Unit batch12a 7 款 driver-gap Unit（byteswitch/bytebutton/step16/timerpwr/mq/8servos2-i2c/cardkb2）已通过 guest **raw machine.I2C 探针**取得虚拟设备证据（无官方 Unit 驱动，driver-gap caveat 已记录），见
[Unit batch12a 虚拟设备证据](evidence/2026-11-03-unit-batch12a-evidence/README.md)；证据发现并修复了 `0160` 的 MQ ADC12 QOM 截断/取整不一致，7 款寄存器读写与 QOM fixture 一致；机械/电气/光学/热学/声学物理与 UART/BLE/ESP-NOW 模式 NOT RUN。

## 首页与维护入口

面向使用者的首页为默认中文 [README](../README.md)，英文入口为 [README.en](../README.en.md)。
维护者先读根 [AGENTS.md](../AGENTS.md)，再按职责查看
[服务工具](../platform/tools/AGENTS.md)、[浏览器/模型](../platform/web/AGENTS.md)、
[设备登记](../devices/AGENTS.md)、[运行时测试](../tests/AGENTS.md)、
[补丁](../patches/AGENTS.md)和[文档维护](AGENTS.md)。指引保存稳定规则，当前能力仍查权威页。

## 按角色继续阅读

1. [工程交接总览](engineering-handoff.md)：用一页理解产品边界、代码阅读顺序、
   当前工作流和下一步；不复制动态计数。
2. [自动项目快照](project-snapshot.md)：从 catalog、profile、evidence 和 Backlog
   自动汇总的设备、样本、缺口与 Task 板。
3. [工作流总台账](workstreams.md)：按工作流串起代码、权威状态入口和 Task ID。
4. [项目当前状态](project-status.md)：现在能做什么、已经验证什么、仍有什么风险。
5. [项目 Backlog](project-backlog.md)：尚未完成的工作、优先级、依赖和验收条件。
6. [代码与验证入口地图](code-map.md)：实现落在哪些模块、测试如何复现、证据在哪里。
7. [验证证据台账](validation-ledger.md)：按日期保存当时的检查项、结论和 evidence。
8. [统一设备运行时契约](unified-device-runtime.md)：Device Service、单 guest、
   board/WiFi/BLE/evidence 的产品验收边界。
9. [运行时模型缺口登记](runtime-model-gap-register.md)：已知“固件已执行但
   模拟器能力不足”的缺口、证据、边界和关闭条件。
10. [公众模拟器计划](plans/2026-10-28-public-simulator.md)与[纯浏览器调研](browser-runtime-feasibility.md)：Pages 入口、浏览器与原生后端的分界和对照实验。

如果页面之间冲突，以当前代码、生成后的 catalog/coverage、最新测试证据和
`project-status.md` 为准；`project-backlog.md` 不描述完成状态，日期较早的
调查页也不自动代表当前结论。

## P0 与模型缺口的权威入口

- 当前能力、已闭合边界和风险只看 [项目当前状态](project-status.md)。
- 未完成 Task ID、依赖和验收只看 [项目 Backlog](project-backlog.md)。
- 某项结论何时、用什么证据验证，只看 [验证证据台账](validation-ledger.md)。
- 具体设备/样本/Task 计数看 [自动项目快照](project-snapshot.md)；它由源文件
  生成，不替代上述人工结论和边界说明。
- 固件行为与模拟器差异不能直接归因时，先查
  [运行时模型缺口登记](runtime-model-gap-register.md)；分类不是修复。

不要在 README、专题页或历史调查中复制第三份 P0 状态表。

## 文档分层

| 类型 | 作用 | 代表页面 |
| --- | --- | --- |
| 当前事实 | 只描述当前实现、验证日期和已知边界 | [项目当前状态](project-status.md) |
| 待办 | 只列未完成工作、依赖和验收条件 | [项目 Backlog](project-backlog.md) |
| 契约 | 定义 API、manifest、运行时和发布门禁 | [Device Service API](device-service-api.md)、[FirmwareManifest](firmware-manifest.md)、[统一运行时](unified-device-runtime.md) |
| 实现地图 | 指到源码、测试、证据和生成物 | [代码与验证入口地图](code-map.md) |
| 验证台账 | 按日期保存当时结论、检查项和 evidence | [验证证据台账](validation-ledger.md) |
| 专题说明 | 深入解释某一类模型、流程或边界 | [网络模拟](network-simulation-plan.md)、[外设架构](peripheral-simulation-architecture.md) |
| 历史证据 | 保留当时的复现、根因或阶段计划 | [StopWatch QEMU 适配](stopwatch-uiflow2-qemu.md)、[多设备设计](plans/2026-10-20-multi-device-emulator-design.md) |

## 新鲜度台账

“最近核对”表示该页结论已经和当前主入口对齐，不表示所有底层矩阵都在同一天
重跑；真正的验证时间以页内 evidence 和 JSON 为准。

自动快照区分三种日期，避免把设备目录的生成时间误当成项目事实日期：

- 设备目录日期：`devices/catalog.source.json` 的 `generated_at`；
- 当前事实复核：机器源日期、最新 evidence 和五个项目入口复核日期中的最大值；
- 最新 evidence 日期：已提交 `tests/**/evidence-YYYY-MM-DD-*.json` 的最大日期。

因此 catalog 未变化但新 evidence 已提交时，快照仍会推进“当前事实复核”，并把
显式复核日期更早的权威页、委派页分别列为待复核项。待复核是审计信号，不是
自动判定内容错误。

证据与计划行的“事实基线”是该日期当时的结果，不是今天的项目状态；后续
证据可以关闭历史 `OPEN`/`PARTIAL`，但不会改写原记录。当前结论始终回到
项目状态、Backlog、运行时缺口登记和验证台账。

| 页面 | 类型 | 最近核对 | 事实基线 |
| --- | --- | --- | --- |
| [性能修复与对照](evidence/2026-11-03-emulator-performance/README.md) | 验证证据 | `2026-11-03` | 历史 native 同固件取帧/动作与 browser R6 完整本地门禁；新部署另行绑定运行时 |
| [性能优化合 main 与 Pages 更新](evidence/2026-11-03-performance-pages-release/README.md) | 部署与虚拟设备证据 | `2026-11-03` | 两 PR 合并、新 producer 路径策略、19 板 20 例完整本地门禁、prepared-preview 部署与独立 HTTPS 验证；保留 regular CI engine 清理失败 |
| [原生页面性能验证](evidence/2026-11-03-emulator-performance/native-validation.md) | 验证证据 | `2026-11-03` | 四次同固件对照及实际帧、SCS、输入、历史和停止；不授予 browser 或物理性能 |
| [性能修复计划](plans/2026-11-03-emulator-performance.md) | 执行计划 | `2026-11-03` | 单一 QEMU 的加载、C/TCI/GPIO、轮询与精确固件执行设置；正式 guest gate 分层 |
| [浏览器启动与UIFlow工作台设计](plans/2026-11-04-uiflow-browser-workbench-design.md) | 实施计划 | `2026-11-04` | 全部19款设备的默认工作台/声明输入本地验收另见R8；本设计保留身份与行为门禁，性能、长期稳定性和正式HTTPS仍独立 |
| [Atom Matrix / StickC Plus启动调查](evidence/2026-11-04-browser-startup-investigation/README.md) | 浏览器诊断证据 | `2026-11-04` | 原正式3c两板基线、未采用的oneInsn候选与20秒早启CDP；不授予新默认工作台、全设备提速或部署 |
| [WASM host poll唤醒限定证据](evidence/2026-11-04-wasm-wakeable-poll/README.md) | 构建、SDK与两板cold/同页warm限定证据 | `2026-11-04` | fresh75原Flash Matrix15/Plus26与正常5CDP；独立cold原值保留；[后续四组](evidence/2026-11-04-wasm-wakeable-poll/warm-summary.json)完成3c/75两板cold-prime→新VM warm，75两组53.491→76.480/39.378→63.627s更慢；首3cMatrix观察器FAIL另存，纯cache收益与取消未建立；不授予新默认、全型号或线上提速 |
| [UIFlow工作台限定验收](evidence/2026-11-04-browser-uiflow-workbench/README.md) | 浏览器与组合分层证据 | `2026-11-04` | 首次signed-array FAIL保留、旧3c smoke20、新2c72 CoreS3 div8完整54；19组包装与四宽度model-only检查不授予其余18板guest或全按键 |
| [CoreS3工作台正常钟后续验收](evidence/2026-11-04-browser-uiflow-workbench-wallclock/README.md) | 精确固件浏览器证据 | `2026-11-04` | 同52f Flash/2c72 WASM的div1+oneInsn完整54与正常6CDP清理；单次10.971对27.483秒，不是重复基准，未授予其余18板或新部署 |
| [StamPLC工作台复位策略](evidence/2026-11-04-stamplc-workbench-reset/README.md) | 精确固件浏览器证据 | `2026-11-04` | 同0b2b Flash/96ea WASM/div1，原策略44项后复位PIF异常；oneInsn+0027候选完整54与正常6CDP，根因RUNTIME-07仍OPEN，完整V3矩阵与线上另验 |
| [浏览器输入专项验收](evidence/2026-11-04-browser-input-acceptance/README.md) | 输入与观察器分层证据 | `2026-11-04` | 圆屏原FAIL/修正后55、PM1默认250ms失败与显式应用配置、Card IRQ及finally/独立516；不授完整reset、全矩阵或部署 |
| [Cardputer工作台复位调查](evidence/2026-11-04-cardputer-workbench-reset/README.md) | 浏览器诊断证据 | `2026-11-04` | 原多指令策略44项后WASM OOB与fallback清场；独立未复现及观察器控制分层，RUNTIME-08 OPEN，不以诊断通过覆盖首次FAIL |
| [PaperColor帧观察器修正](evidence/2026-11-04-papercolor-frame-oracle/README.md) | 观察器与限定虚拟设备证据 | `2026-11-04` | 同V5/96ea，首轮LCD F800假设失败保留；Spectra6全帧B800/双新鲜序列、未修改默认源码两次Run及64项窄复验；后续报告控制脚本与完整矩阵另验 |
| [Paper PM1应用配置](evidence/2026-11-04-paper-pm1-application/README.md) | 精确固件输入证据 | `2026-11-04` | R6 PaperColor准备ImportError/零输入保留；两Paper显式公开I2C配置后23/19项、8/6次250ms输入与原BtnPWR通过；Mono编辑器63项独立通过，模块/物理pinmux与清场范围分开 |
| [S3工作台执行策略](evidence/2026-11-04-s3-workbench-execution-policy/README.md) | 精确镜像候选与源审查证据 | `2026-11-04` | 原AtomS3 Lite首启INT_CLR读PIF保留/09OPEN；八板各自editor+buttons及Stackbody共17候选/656检查/40输入通过，真实argv与清场逐项绑定；仅功能行推广到V6，完整60/线上另验 |
| [全19板UIFlow与输入验收](evidence/2026-11-04-browser-uiflow-all19-acceptance/README.md) | 完整本地浏览器功能证据 | `2026-11-04` | canonical V6独立60/2564、224次raw-paste/38次默认样例、200组输入与真实清场；逐板ready仅功能观察、11S3精确argv，原FAIL及07/08/09 OPEN；不授逐板性能或线上 |
| [V5 DOM/model-only边界检查](evidence/2026-11-04-browser-uiflow-all19-acceptance/dom-qa-summary.json) | 独立布局与能力边界证据 | `2026-11-04` | CoreS3四宽及两个边界型号两宽，无guest；PaperS3观察器首FAIL保留，不转授为V6新布局或guest结果 |
| [QEMU 执行优化决策](adr/0001-qemu-browser-hot-block-jit.md) | 架构决策 | `2026-11-03` | 保留原 TCI，不加入第二后端/JIT；精确 SHA/ready/patch 绑定及回调后 IRQ 新鲜度 |
| [Unit 第二批协议研究](unit-research/2026-11-02-batch2-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器表/QEMU 复用建议与 unresolved（adc_v11 快照漏调用 bug、neopixel 版本语义、多从机/双端点框架缺口）；planned，不含 runtime 声明 |
| [Unit 第三批协议研究](unit-research/2026-11-02-batch3-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器表/QEMU 复用建议与 unresolved（rfid→rfid2 复用、vmeter/env-iv 双从机、ADS1100/ADS1110 区分、SHT4x/SCD4x 快照 vs master 语义差异、PbHub 7 地址与 MCU/RGB 冲突）；planned，不含 runtime 声明 |
| [Unit 第四批协议研究](unit-research/2026-11-02-batch4-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器表/QEMU 复用建议与 unresolved（rs485-iso→rs485、co2l→co2、tof4m→tof 同族复用、HX711 位脉冲、MIDI/NMEA/JRD4035 UART 帧、SCD41/AC 市电/激光安全边界、WS2812 35-vs-70 灯冲突）；planned，不含 runtime 声明 |
| [Unit 第五批协议研究](unit-research/2026-11-02-batch5-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器表/QEMU 复用建议与 unresolved（pbhub-v11→0131 PBHUB 复用、op90→limit/pir GPIO、rgb-led-10cm→fader RMT、8angle 寄存器组、PaHub 多总线框架缺口、RTC 虚拟时钟、LoRa 页面 115200 vs 驱动 9600 冲突、Zigbee/NBIoT AT 应答器、neohex 无 unit 驱动）；planned，不含 runtime 声明 |
| [Unit 第五批首批实现状态](unit-research/2026-11-02-batch5-impl-status.md) | Unit 实现状态 | `2026-11-02` | 5 款首批 Unit（pbhub-v11/op90/rgb-led-10cm/8angle/kmeter-iso-v11）的 0137 模型、QOM fixture、smoke 19/19 与 unresolved（PORT.B 限制、op90 极性、pbhub v1/v2、8angle/kmeter 寄存器）；planned，不含 runtime 声明 |
| [Unit 第六批协议研究](unit-research/2026-11-02-batch6-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器表/QEMU 复用建议与 unresolved（mini-scales→0x26 寄存器组四方冲突、rgb-led-strip-50cm→fader RMT 30 灯、op180→limit/pir GPIO、synth→midi TX-only、mini-imu→板级 MPU6886、unit-id→ATECC 夹具扩展、thermal2 页 0x33 vs 驱动 0x32、qrcode 16-bit 地址、env-pro 0x77/0x76、uwb AT/dmx C 模块/finger FPC1020A 帧）；planned，不含 runtime 声明 |
| [Unit 第七批协议研究](unit-research/2026-11-02-batch7-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的驱动 file:line/寄存器/AT/CAN 表/QEMU 复用建议与 unresolved（Mini BPS QMP6988 页面/索引 0x56 vs 驱动 0x70、IMU-Pro BMI270 0x68+BMM150 aux 0x10+BMP280 0x76、HBridge v1.1 0x20+0x30 float 电流、CardKB original 0x5F、ToF-90 VL53L0X 0x29 四方冲突、HEX 37×SK6812 无 unit 驱动、Mini PDM SPM1423 无 Unit 驱动、CatM/CatM GNSS SIM7080 AT、LoRaWAN-CN470 STM32WLE5 vs ASR650x 驱动错配、CAN m5can/TWAI+隔离收发器）；planned，不含 runtime 声明 |
| [Unit 第八批协议研究](unit-research/2026-11-03-batch8-protocols.md) | Unit 研究 | `2026-11-03` | 12 款未登记 Unit 的驱动 file:line/命令/寄存器/AT/CAN 表/QEMU 复用建议与 unresolved（PaHub v2.1 PCA9548AP 0x70-0x77 复用 CONTROL_PAHUB；LCD U120 ST7789V2 页面 0x3E vs 驱动 0x3D + 完整 I2C 命令/flush 协议；OLED/MiniOLED/Glass2 显示组合与 0x3C/0x3D 地址冲突；GPS v1.1/SMA AT6668 页面 115200 vs 驱动 9600；NBIoT-CN SIM7020C AT；LoRaE220-920 920MHz 0xC0/C1；LoRaWAN-US915 STM32WLE5 vs ASR650x 驱动错配；Mini CAN TJA1051/TWAI；MIC 模拟+比较器无 Unit 驱动）；planned，不含 runtime 声明 |
| [Unit 第九批协议研究](unit-research/2026-11-03-batch9-protocols.md) | Unit 研究 | `2026-11-03` | 12 款剩余 Unit 的驱动-gap/组合证据、地址/协议表与 unresolved（Glass U158 0x3D SSD1309 + M5Unified unit_glass 组合（按键/蜂鸣器表不可读）；CardKB2 U215 四模式 PORT.CUSTOM G26/G25、无 driver/I2C 地址未知；8Servos2-I2C U222 0x25-0x34 八通道内部固件协议缺失；BMM350 U231 0x14、INA226-10A U200 0x41 无 driver/寄存器表；LoRaWAN-AS923/EU868 STM32WLE5 vs ASR650x 错配、AS923 无驱动类；Fingerprint2 U203 A-K323CP 115200 无 driver/帧格式；AudioPlayer U197 N9301 9600 无命令表；RF433T/R U114/U113 GPIO bitstream、RF NOT RUN；RollerCAN U188 I2C 0x64/CAN 内部固件协议未公开）；planned，不含 runtime 声明 |
| [Batch-9 剩余实现状态](unit-research/2026-11-03-batch9-impl-status.md) | Unit 研究 / 实现状态 | `2026-11-03` | batch-9 剩余 9 款：lorawan-as923/lorawan-eu868/audioplayer/fingerprint2 实现为 UART 字节层 fixture responder（0151，仅 responses-hex/tx-hex/frames-sent/frames-injected；无 AT/音频/指纹/LoRaWAN 解码，无 guest 证据）；cardkb2/8servos2-i2c/bmm350/ina226-10a/rollercan 仅登记 planned 契约 + 地址/blocker（0x14/0x25-0x34/0x41/0x64、PORT.CUSTOM G26/G25；不建模型、不猜寄存器）；catalog/profile 133→142，全部 planned；离线 QOM smoke 仅 4 款 attach/property 回读，不是 functional PASS |
| [Unit 第十批协议研究（收口）](unit-research/2026-11-03-batch10-protocols.md) | Unit 研究 | `2026-11-03` | 剩余 43 款 unit 全部分类：a 7 款（dcssr 0x50 官方 acssr 驱动/Modbus0x04；ina226-1a 0x41 ±1A/80mΩ；dof6 BMI270 0x68/0x69；dof9 +BMM350 0x14；dof10 +BMM350+SPA06 0x76；asr UART 115200 AA55 帧表；puzzle 64×WS2812E PORT.B 单线）；b 11 款（roller485/roller485-lite RS485/I2C0x64、rollercan-lite CAN/I2C0x64、byteswitch 0x46、bytebutton 0x47、step16 0x48、timerpwr 0x56、mq 0x11、8servos2-chain Chain UART、cat1-cn ML307R 115200 AT、chainbus 115200 Chain）；c 25 款（camera/vision 14、controller/PoE 4、passive 7）只写不可接入边界；a/b 写 planned catalog 草稿（18 条），预计登记 142→160、产品覆盖 184/184；未运行 QEMU、未改 catalog/runtime/测试 |
| [Batch-10 a/b 登记与最小模型状态](unit-research/2026-11-03-batch10-impl-status.md) | Unit 研究 / 实现状态 | `2026-11-03` | batch-10 a/b 18 款登记：catalog/profile 142→160，全部 planned；0152 建 6 款最小模型（dcssr=ACSSR 0x50 子集、puzzle=64×WS2812E RMT、dof6/dof9/dof10=BMI270 0x68 子集、asr=UART115200 AA55 command-id fixture responder）；ina226-1a（0x41 无 datasheet）+ b 类 11 款（roller485/roller485-lite/rollercan-lite 0x64、byteswitch 0x46、bytebutton 0x47、step16 0x48、timerpwr 0x56、mq 0x11、8servos2-chain/cat1-cn/chainbus UART）只登记 planned 契约、不建模型；无 guest 证据，QOM smoke 6/6 不是 functional PASS |
| [Unit batch12a 实现状态](unit-research/2026-11-03-batch12a-impl-status.md) | Unit 研究 / 实现状态（历史时点） | `2026-11-03` | `0158` 在时点 canonical 36 层链（至 0156）后为 batch-12a 7 款 driver-gap Unit 建寄存器文件数据面（后续 guest 证据已升 implemented；最终 canonical 41 层见 patch README）：byteswitch 0x46 / bytebutton 0x47 共享 CONTROL_BYTEUNIT（0x00 位图、0x60 单通道、0x10-0x19 LED、0x20-0x4F user RGB888、0x70/0x90 sys RGB、F0/F1/FE/FF），step16 0x48（position/led/direction/RGB）、timerpwr 0x56（Grove/backlight/trigger/schedule/LE32 V&I/charging）、mq 0x11（mode/heat/ADC8-12/valid/NTC/mV；valid 极性按驱动、与 PDF 冲突 unresolved）、8servos2-i2c 0x25-0x34（rotary 地址/8 通道 modes/ADC/servo/PWM/RGB/UID/telemetry）、cardkb2 0x5F legacy I2C 子集（raw key + 0xF1 FW）；catalog/profiles 保持 160（7 条由空契约更新为完整 planned QOM 契约，任务预期 160→167 与 base 已登记事实不符），全部 planned、无 guest 证据；离线 QOM smoke 20/20 仅属性/fixture/范围/时间/rotary 地址，不是 functional PASS；UART AA03/BLE HID/ESP-NOW 与电气/机械/光学 NOT RUN |
| [Unit batch12a 虚拟设备证据](evidence/2026-11-03-unit-batch12a-evidence/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | batch-12a 7 款无官方驱动 Unit 用 guest raw machine.I2C 探针取证（独立 8804 服务、host-image、先 ZIP 后 purge=0）：byteswitch 0x46（bitmap 0xA5/ch/FW/亮度/模式/RGB/save/IRQ 读写 + QOM 一致）、bytebutton 0x47（0x5A）、step16 0x48（position/direction/brightness/RGB/save）、timerpwr 0x56（buttons/电池 LE32 3700mV/charging/定时 12:34/背光/Grove 输出）、mq 0x11（ADC8/ADC12 2234/valid/NTC/ref，valid 极性按驱动、PDF 冲突 unresolved）、8servos2-i2c 0x28 rotary=3（UID/modes/servo/PWM/RGB）、cardkb2 0x5F（raw key 0x71 + 0xF1 FW）；0160 修复 MQ ADC12 QOM 截断；单一 QEMU 构建（…0159+0160，runtime bf304e61…）；机械/电气/光学/热学/声学、UART AA03/v2/BLE HID/ESP-NOW、各地址冲突语义 NOT RUN |
| [Unit 第十批 a 类虚拟设备证据](evidence/2026-11-03-unit-batch10/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | batch10 a 类 6 款：dcssr（官方 DCSSRUnit/ACSSR 0x50 relay/RGB/fw）、puzzle（generic RGBUnit/SK6812 64×WS2812E，driver-gap）、dof6/dof9/dof10（frozen generic BMI270 0x68 accel/gyro/temp/whoami；BMM350 0x14/SPA06 0x76 未建模 BLOCKED，不伪造磁力/气压）、asr（raw UART 115200 AA55 0x45 字节层）各一个 cores3 可见会话全 PASS；单一 QEMU 构建 canonical 75f1d24+0120–0152 33 层+0154 证据修复，运行时 bin `7e608233…`；puzzle PORT.B/asr PORT.C 用 cores3 PORT.A harness；0154 修复 BMI270 init 状态与 TEMP 0x22 小端别名；SSR 电气/LED 光学/IMU 运动/磁力/气压/语音声学 NOT RUN |
| [Unit 第十二批 c 类虚拟设备证据](evidence/2026-11-03-unit-batch12c-evidence/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | 8servos2-chain（raw UART AA55 Chain：modes/angles/ADC/RGB/current/device type 0x000C）、chainbus（ChainBus 0x0006：UID/GPIO/ADC/brightness、I2C forward fail-closed status 0）、cat1-cn（ML307R-DL AT：CPIN/CREG/CSQ/CGSN/CGMM 字节层）、mini-imu-pro（BMI270 0x68 accel/gyro/temp + BMP280 0x76 pressure）4/4 PASS；0160 修复 AA55 length=3 data-less 帧被清缓冲的 bug；canonical 39 层+0160，runtime `feec1b11…`；chain/cat1 PORT.C 用 cores3 PORT.A harness；级联/舵机/蜂窝 RF/音频/磁力/运动物理 NOT RUN；mini-bps-v11 无模型未测 |
| [Unit 第十一批虚拟设备证据](evidence/2026-11-03-unit-batch11/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | lorawan-as923/eu868（官方 LoRaWANUnit/ASR650x 字节层，CW2/CW1/DTRX）、rf433t（Pin bitbang 10101010 → bitstream/edge/bit）、rf433r（Pin 采样高低 + QOM samples）、audioplayer（raw UART 9600 7e03010203 + fixture）、fingerprint2（raw UART 115200 13B + fixture）6 款 PASS；glass BLOCKED：official GlassUnit/M5.addDisplay 返回 Display 但无模型可见 I2C commands/data（QOM commands=0/data-bytes=0），不伪造；canonical 35 层，runtime `9232cb1e…`，无 0155 模型修复；PORT.B/C 用 cores3 PORT.A harness；RF/音频/指纹/光学语义 NOT RUN |
| [Unit 第十一批 driver-gap 协议研究](unit-research/2026-11-03-batch11-driver-gap-protocols.md) | Unit 研究 | `2026-11-03` | driver-gap 17 款网络检索（2026-11-03 抓取）：官方 docs protocol 页 U222/I2C+U223/UART、11 份官方协议 PDF/MD（Roller485/485-lite I2C+RS485、RollerCAN/CAN-lite I2C+CAN、ByteSwitch、ByteButton、Step16、TimerPWR、MQ、ChainBus、CardKB2 User Manual）、OneMO ML307R AT 手册 V1.8.1、TI INA226 SBOS547C Table 7-1、Bosch BMM350 Table 8、上游 UIFlow2 master f20d5a0 的 15 款驱动 file:line；分类 a 15/b 2（cardkb2 的 v2 report/BLE/ESP-NOW 缺口、cat1-cn 的 RF/SIM/网络缺口）/c 0；含推荐实现顺序与地址冲突（0x64×4、0x41×2）；只写 docs，未改 catalog/model/test，全部仍 planned，无 QEMU/guest 证据 |
| [Unit batch-12b 实现状态](unit-research/2026-11-03-batch12b-impl-status.md) | Unit 研究 / 实现状态（历史时点） | `2026-11-03` | batch-12b 10 款 driver-gap 最小模型层（patch `0159`，时点 reconciled 39 层链；后续 batch12b 7 款 I2C 与 batch12c Chain/Cat1 已升 implemented；最终 canonical 41 层）：BMM350 0x14（Bosch Table 8 + §9.2.3 两个 dummy 读字节）、INA226 0x41 ×2（TI Table 7-1，10A 5mΩ/0x0C80 vs 1A 80mΩ/0x0800，注释 0x811 冲突记 blocker）、Roller 族 0x64 ×4（I2C 寄存器子集，RS485/CAN 帧层/FOC 物理 NOT RUN，四款互斥）、8Servos2-Chain/ChainBus AA55 帧级 responder（0x000C/0x0006，ChainBus I2C 转发 fail-closed）、Cat1-CN 最小 AT responder（RF/SIM/PDP/网络/TLS/MQTT NOT RUN）；catalog 160（108 partial/47 planned/5 simulated）不变、10 款 model_status planned→partial、profile 全部保持 planned+hosts 空（无 guest 证据不升 implemented）；离线 QOM smoke 152/152 仅属性/fixture 检查；全量测试+四 check+scope check 见 commit 报告 |
| [Unit batch-12b 7 款 I2C guest 证据](evidence/2026-11-03-unit-batch12b-evidence/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | batch-12b 7 款 driver-gap I2C Unit（bmm350 0x14、ina226-10a/ina226-1a 0x41、roller485/roller485-lite/rollercan/rollercan-lite 0x64）在 reconciled 39 层链（`0159`）上各用一个独立可见 session 采集 guest 证据：**无官方 Unit 驱动 → raw `machine.I2C` 寄存器探针**（BMM350 按 datasheet §9.2.3 读 size+2 丢 2 dummy 字节）；7/7 PASS：BMM350 CHIP_ID=0x33/MAG·TEMP raw 与 QOM fixture 反算一致（14144/-7072/3484/51453）、INA226 ID 0x5449/0x2260 + config 0x4127 + cal 0x0C80/0x0800 + shunt/bus/current/power raw 匹配、Roller 族 product id 0x01/0x02 + FW 3 + 寄存器读与 mode/target/save 写回读匹配 QOM；每例先取 evidence ZIP 再 purge=0 并核对 history；session id 仅 sha256；runtime bin `69ebd3cb…`，未发现模型 bug（无 0160 补丁）；catalog 保持 partial、7 款 profile 升 implemented+hosts cores3；磁力/heading/OTP、隔离/精度/保险/热、FOC 电机/电气、RS485/CAN 帧层 NOT RUN；0x41/0x64 地址互斥 |
| [视觉主机与 Unit 接入战役汇总](evidence/2026-11-03-visual-campaign-summary/README.md) | 战役汇总 | `2026-11-03` | 9 个独立视觉 host 完成同 guest 原厂固件路径接入，5 项 boundary-only/composition-only；Unit 160 登记（**158 implemented/partial + 2 planned DEFER**）+ 25 c 类边界，184/184 覆盖；10 个研究批 + batch11/12 解锁与证据 PR #80–#161（#149–#159 为最终解锁/证据批，#160/#161 为文档收口）；canonical 41 层链（0120–0161，41/41 replay）；列出真实模型 bug（含 unit-id ATECC wake/CRC、CAN 契约、glass REG_INDEX、MQ ADC12、AA55 Chain 帧长）、仅剩 2 项 DEFER 与 virtual-device/硬件边界 |
| [Unit CAN/LoRaWAN 虚拟设备证据](evidence/2026-11-03-unit-can-lorawan/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | `can`/`mini-can` 各一个 cores3 可见会话 PASS：guest TWAI 帧 `123#0102030405060708` 被 m5-canbus CanBusClient 观测（frames-observed=1），host fixture `456#deadbeef` 经 QOM inject-hex 注入并被 guest 收到（injected-frames=1，state RUNNING）；`lorawan-us915` 仅 UART AT 字节层 PASS（AT+CWORKMODE/AT+DTRX，frames-sent/injected=3）；Unit runtime 契约 + probe 解锁，无新增 QEMU 补丁（canonical 35 层至 0154）；CAN 电气/仲裁/隔离、US915 AT 解码/Join/RF/FCC NOT RUN；PORT.C 使用 cores3 PORT.A harness |
| [Unit Glass 解锁证据](evidence/2026-11-03-glass-unblock/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | 根因：官方 M5GFX M5UnitGLASS 用自定义 STM32 REG_INDEX 协议（0x00/0x10/0x90/0xB0/0xC0/0xD0/0xFE），旧模型误实现 SSD1309 0x00/0x40 控制字节，真实事务被忽略（commands/data=0）；0157 实现协议/QOM pages 后官方 GlassUnit/M5.addDisplay 的 fillScreen/fillRect/print PASS：commands=4366、data-bytes=13144、pages=44、command-hex=10、panel-framebuffer=8458bede；base 36 层（0120–0156），runtime `893a8d21…`；透明 OLED 光学/按键/蜂鸣器语义与 0x3D 冲突仍 NOT RUN |
| [Unit 第七批剩余 7 款实现状态](unit-research/2026-11-03-batch7-impl-status.md) | Unit 实现状态 | `2026-11-03` | 0145 在 canonical 链 0144 后实现 batch7 剩余 7 款：hex 复用 37-LED RMT（driver-gap/SK6812 unresolved）、catm/catm-gnss/lorawan-cn470 UART fixture responder（不做 AT 解码；LoRaWAN STM32WLE5 vs ASR650x 错配）、can/mini-can 绑定 cores3 m5-canbus 的 CanBusClient+inject-hex（方向/过滤/位定时/电气 NOT modeled）、mini-imu-pro BMI270 0x68+BMP280 0x76 最小复合模型（init blob 接受但不执行、aux 简化）；mini-pdm DEFER 无 Unit 模型；catalog/profile 111→118，7 条全部 planned、离线 QOM smoke 7/7 attach；不含 guest/runtime 声明 |
| [classic 主机可行性研究](plans/2026-11-02-classic-hosts.md) | 计划 | `2026-11-02` | AtomU/Atom Echo GO（官方 GitHub release UIFlow2 精确镜像）、M5Stick 条件接入（EasyLoader 工厂镜像提取；原 `d960e57e…` 提取长度已修正）、StickT2 DEFER、StickV K210 NO-GO；含固件 SHA/分区与 QEMU 复用证据 |
| [AtomS3R-CAM 相机数据面闭环](evidence/2026-11-02-atoms3r-cam-sccb/README.md) | 设备数据面 / 虚拟设备 | `2026-11-02` | 软件 SCCB 桥 dedicated-pin 修复 + N8R8 PSRAM + QVGA DVP：camera.init True、153,600 B RGB565 帧（fnv1a 42521dc5）；非 QVGA/多帧/光学 NOT RUN |
| [AtomS3R-CAM 相机几何与多帧流](evidence/2026-11-02-atoms3r-cam-geometry/README.md) | 设备数据面 / 虚拟设备 | `2026-11-02` | LCD_CAM DVP 几何跟随 GC0308 window/subsample 寄存器（0118）：QQVGA/240×240/QVGA/CIF/VGA 帧的 guest SHA-256 与宿主重建一致；QOM auto-increment 下连续 5 帧互异、各自匹配重建 scene seed 帧、无撕裂；动态改尺寸/物理光学 NOT RUN |
| [AtomS3R-M12 主机接入](evidence/2026-11-02-atoms3r-m12-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 新 machine `m5atoms3rm12` + OV3660 16-bit SCCB 模型（PID 0x3660、0x3808-0x380b 几何）：共享官方 UIFlow2 镜像（描述覆盖 AtomS3R-M12）camera.init True、QQVGA/VGA/HD 帧与宿主重建一致、5 帧流互异；社区 M12 User Demo 黑盒确认 OV3660 控制面，MJPEG/UVC/物理光学 NOT RUN |
| [M5StickT2 热成像主机接入](evidence/2026-11-02-stickt2-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 新 machine `m5stickt2` + FLIR Lepton 3.0 模型（164 字节 VoSPI 包、4×60 包/帧、16-bit CCI 命令）+ classic SPI slave 挂载 + UART TX_DONE latch 修复：探针 3 帧 digest 与宿主 oracle 一致、ST7789 截图与 encoder QOM 注入通过；官方 demo 仅到 app 启动标记，物理 LWIR/UI NOT RUN |
| [Unit 第一批协议研究](unit-research/2026-11-02-batch1-protocols.md) | Unit 研究 | `2026-11-02` | 12 款未登记 Unit 的官方驱动 file:line 证据、总线/寄存器/命令表、QEMU 复用建议与 11 条 unresolved；planned，不含 runtime 声明 |
| [Unit 第一批 A 类虚拟设备证据](evidence/2026-11-02-unit-batch1/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | `ssr`(cores3)/`earth`(atoms3r)/`hall`(sticks3)/`reflective-ir`(stopwatch)/`vibrator`(cores3) 各一个可见会话，原固件冻结驱动经真实 GPIO/ADC/LEDC 控制器产生或观测数据；`earth` 的 read_uv/humidity 与 `vibrator` 的 Haptic one-shot completion 未观测，电气/光学/机械/磁场语义均未验 |
| [Unit 第一批 B 类虚拟设备证据](evidence/2026-11-02-unit-bclass/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | `dlight`(atoms3r)/`accel`(sticks3)/`4relay`(cores3)/`weight-i2c`(stopwatch) 各一个可见会话，原固件冻结 I2C 驱动经真实 SoC I2C 控制器读写；0119 的 BH1750 命令掩码 bug 由 0120 修复后全部通过；4relay 触点/负载、dlight 光学/MTreg、accel 物理量程/DEVID、weight 校准/0x60/0x26 冲突与真机均未验 |
| [Unit 第一批 C 类虚拟设备证据](evidence/2026-11-02-unit-cclass/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | `ncir2`(atoms3r)/`extio2`(sticks3)/`hbridge`(cores3) 各一个可见会话，原固件冻结 I2C 驱动经真实 SoC I2C 控制器读写；ncir2 温度/编码上限饱和（+327.67°C）与 0x5A 冲突、extio2 ADC/舵机/RGB 单位 unresolved、hbridge 0x30 v1.1/电机电气与真机均未验 |
| [Unit 第二批前 6 款虚拟设备证据](evidence/2026-11-02-unit-batch2/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | `joystick`(cores3)/`watering`(atoms3r)/`fader`(atoms3r)/`dac`(cores3)/`bps`(sticks3)/`adc-v11`(stopwatch) 各一个可见会话，原固件冻结驱动经真实 ADC/RMT/GPIO 或 I2C 控制器读写；0125 的 MCP4725 3 字节 fast-mode bug 由 0127 修复后全部通过；joystick 原始字节/机械、watering 水泵/土壤物理、fader LED 光学、dac EEPROM/输出参考、bps QMP6988/物理气压、adc-v11 ADS1100 分歧与真机均未验 |
| [Unit 第二批后 6 款虚拟设备证据](evidence/2026-11-02-unit-batch2b/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | `env`(atoms3r)/`ameter`(sticks3)/`extencoder`(cores3)/`ain4-20ma`(stopwatch)/`acssr`(atoms3r)/`gesture`(sticks3) 各一个可见会话，原固件冻结驱动经真实 I2C 控制器读写；0126 的 AMeter 校准 EEPROM 跨距 bug 由 0128 修复、batch-2b 写偏移 off-by-one 由 0129 修复后全部通过；acssr 仅为 I2C 事务观测、绝不是 AC 市电开关模型（24–480V/10A/过零/隔离 NOT RUN）；env 变体/传感器精度、ameter 出厂校准/电流测量、extencoder 机械/ABZ、ain4-20ma 环路、gesture 光学与真机均未验 |
| [Unit 第三批 12 款虚拟设备证据](evidence/2026-11-02-unit-batch3/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | A+B 8 款（rfid/tube-pressure/laser-rx/extio/dac2/scales/vmeter/adc）与 C 4 款（env-iv/co2/pbhub/ultrasonic-io）各一个可见会话；0130/0131 并行树分别构建（2 个 runtime SHA），证据发现并修复 0132（PbHub RGB、Ultrasonic pad observer 断言、SCD40 序列号）、0133（VMeter 默认配置）、0135（EXT.IO 读回、Scales RGB）；co2 温度解码驱动 bug、pbhub IO0/IO1 折叠、dac2 tuple 通道常量、vmeter 量化、tube-pressure ADC 校准缺失均如实 blocked/NOT RUN |
| [Unit 第四批 12 款虚拟设备证据](evidence/2026-11-02-unit-batch4/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | A+B 6 款（rs485-iso UART TX/RX、laser-tx GPIO DIN、co2l CO2/RH、neco 35-LED RMT、midi MIDI 字节流、tof4m VL53L1X）与 C 6 款（weight HX711 位脉冲、bldc-driver 寄存器组、ac-measure ASCII/byte 视图、dds AD9833 分段写、gps NMEA、uhf-rfid JRD4035 帧）各一个 cores3 可见会话，单一 QEMU 构建（0134+0136+0138）；0138 修复 AC 视图/ASCII 偏移与 Weight pad-observer 断言；端口使用 cores3 PORT.A harness 替代官方 PORT.B/C；AC 市电/隔离、UHF RF/Gen2、激光光学、HX711 电气、传感器物理/精度等如实 NOT RUN |
| [Unit 第五批 12 款虚拟设备证据](evidence/2026-11-02-unit-batch5/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | A 5 款（pbhub-v11 6 通道/RGB、op90 数字电平、rgb-led-10cm 15 灯 RMT、8angle ADC/RGB、kmeter-iso-v11 温度）与 B 7 款（pahub-v20 mask-only、rtc 虚拟时钟+停止写回、tmos-pir presence/motion/raw、neohex generic WS2812 37 灯、lora/zigbee/nbiot2 UART 帧）各一个 cores3 可见会话，单一 QEMU 构建（…0139+0141）；0141 修复 op90 digital-level 属性、RTC 停止时钟写回、TMOS 状态位/页读取、KMeter fixture 同步；PORT.B/C 使用 cores3 PORT.A harness 替换；光学/热学/RF/蜂窝/市电语义如实 NOT RUN |
| [Unit 第六批首批虚拟设备证据](evidence/2026-11-02-unit-batch6/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-02` | mini-scales（0x26 ADC/weight/button/校准/滤波，0144 修复 readfrom_mem 指针相位与 button-pressed 别名）、rgb-led-strip-50cm（30×SK6812 RMT）、op180（白线数字输入）、synth（TX-only MIDI 31250，无 RX）、mini-imu（MPU6886 0x68 accel/gyro/temp + 2g/250→8g/1000 量程，0144 QOM 同步）、env-pro（BME688 0x77 identity + raw field bytes；guest 解码 T/RH/P NOT ASSERTED）各一个 cores3 可见会话，单一 QEMU 构建（…0141+0144）；PORT.B/C 使用 cores3 PORT.A harness 替换；物理/光学/音频/热学/气体语义如实 NOT RUN |
| [Unit 第六批剩余虚拟设备证据](evidence/2026-11-03-unit-batch6b/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | thermal2（0x32 中位/平均/差分 + 768B/384×u16 数组，fixture 精确）、qrcode（0x21 2B-LE 地址窗口，status=1/len=15/data fixture/clear→0）、uwb（UART AT fixture 应答器，仅字节层，tx 命令字节精确）、dmx（cdriver 可执行，write_data 后 QOM 捕获 00ff… 字节流，仅字节层）、finger（FPC1020A version gate B1.10.00 + user count/capacity=150，仅 0xF5/XOR 字节层）各一个 cores3 可见会话，单一 QEMU 构建（…0143+0144+0145）；unit-id BLOCKED（ATECC wake 写 0x00 无法被 0x35 从机接收，revision/serial/random 失败，不伪造）；PORT.C 使用 cores3 PORT.A harness 替换；RF/热成像/光学/生物识别/DMX512 电气语义 NOT RUN |
| [Unit 第八批虚拟设备证据](evidence/2026-11-03-unit-batch8/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | pahub-v21（0x70 mask select/release 0/8/40/32 + DIP 0x70）、gps-v11/gps-sma（AT6668 NMEA fixture 精确解码；9600-driver-vs-115200-page unresolved）、lcd（0152 修复 READ_ID 读事务，显式 0x3D，fillScreen/fillRect 命令/像素 QOM）、oled/mini-oled（M5.addDisplay 组合，显式 0x3D，SH1107/SSD1315）、glass2（默认 0x3C，SSD1309）、nbiot-cn（SIM7020C AT 字节）、lora-e220-920（0xC0 回显 + send 帧）、mic（machine.ADC 33832 + comparator 1，driver-gap）各一个 cores3 可见会话；mini-can（无 CAN attachment lane）与 lorawan-us915（ASR650x 驱动/产品错配，无 AT 字节到达）BLOCKED；单一 QEMU 构建（…0146+0148→0151+0152）；PORT.B/C 用 cores3 PORT.A harness 替换；显示/RF/CAN/声学物理 NOT RUN |
| [Unit ID 解锁虚拟设备证据](evidence/2026-11-03-unit-id-unblock/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | unit-id（U124 ATECC608A 0x35）一个 cores3 可见会话：冻结驱动的 0x00 wake-to-address-0 broadcast 被 ACK（wake-count=28），命令帧跨 wake 保留；guest revision=0x260、serial=101112131415161718、SHA-256 digest fixture、GEN_KEY public-key fixture 与 QOM 完全一致，randint 在范围内；0156 同时修正冻结驱动精确 CRC、READ/SHA/NONCE/GEN_KEY 响应模式与 serial/wake QOM；真实密码学/密钥/证书/key-slot/10Kb EEPROM NOT RUN |
| [Unit 第七批虚拟设备证据](evidence/2026-11-03-unit-batch7/README.md) | Unit 数据面 / 虚拟设备 | `2026-11-03` | batch7 8 款：mini-tof-90（ToFUnit/VL53L0X 0x29，range 500/QOM distance）、hbridge-v11（HbridgeUnit 0x20 direction/PWM/freq/ADC/current）、cardkb-original（CardKBUnit 0x5F keycode 113）、env-ii（ENVUnit ENV_II SHT30 0x44+BMP280 0x76 T/RH/P 31.5/45.5/1005.0）、hex（generic RGBUnit/SK6812 37 LEDs，driver-gap）、catm/catm-gnss/lorawan-cn470（UART fixture 字节层，无 RF/蜂窝/LoRaWAN 声明）各一个 cores3 可见会话；单一 QEMU 构建（canonical 75f1d24 + 0120–0147 28 层 + 0149 证据修复）；`can` BLOCKED、mini-bps-v11/mini-pdm DEFER、mini-imu-pro 不在本批；PORT.B/C 使用 cores3 PORT.A harness 替换并记录；0149 修复 batch7 UART TX 捕获后未 arm idle 响应体与 ASR650x RX 注入路由两个模型 bug |
| [M5Stick 主机接入](evidence/2026-11-02-m5stick-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5stick`：EasyLoader FactoryTest 4MB 镜像确定性 icount 启动到原生串口 `mpu9250 addr: FF`；SH1107 初始化命令流+4096 字节 GDDRAM；工厂固件 legacy I2C FIFO 未闭环，MPU9250/IP5306/GPIO35 模型由 generic MicroPython fixture 取证；AK8963/DMP、最终 UI 帧、buzzer/IR/LED 与物理行为未验 |
| [Basic v2.7 主机接入](evidence/2026-11-02-basic-v27-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5basic` 的官方 UIFlow2 v2.5.4-4MB 启动、板级识别 1、ILI9342C 320×240、QMP 注入 A/B/C、IP5306 0x75 寄存器数据面（READ4 0xff 无电芯、battery-mv fixture 映射 75%）与 I2S0 DAC 非静音 PCM；PMIC 电气/电芯、microSD、电源键、背光、Grove Unit 与模拟声学未验 |
| [AtomU 主机接入](evidence/2026-11-02-atomu-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5atomu` 的官方 UIFlow2 v2.5.4 启动、板级识别 130、GPIO27 SK6812 RMT（QOM 0x204060/5 帧）、QMP 注入 GPIO39 按键回读与 Grove G26/G32 I2C 控制器扫描；SPM1423 PDM 麦克风、IR、Grove Unit 与物理行为未验；固件为固定 SHA 官方 GitHub release 资产 |
| [Atom Echo 主机接入](evidence/2026-11-02-atom-echo-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5atomecho` 的官方 UIFlow2 v2.5.4 启动、板级识别 142、GPIO27 SK6812 RMT、QMP 注入 GPIO39 按键回读、Grove I2C 扫描、NS4168 I2S1 非静音 PCM 与 SPM1423 PDM RX 注入路径；官方板载无 ES8311/I2C codec；模拟声学、IR、Grove Unit 与物理行为未验 |
| [AtomS3R-CAM 主机接入](evidence/2026-11-02-atoms3r-cam-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5atoms3rcam` 的官方固件启动、板级识别 144、显示初始化与 GC0308 0x21 PID 0x9b；相机帧随后由同页的 SCCB 闭环证据补齐 |
| [剩余主机与 Unit 接入计划](plans/2026-11-02-remaining-visual-hosts-and-units.md) | 历史计划 | `2026-11-03` | 保留逐型号接入过程时点；页尾最终状态：9 host 接入 + 5 边界、视觉 38=33+5、Unit 160=158+2 DEFER +25 c 类、41 层、PR #80–#161；不构成能力声明 |
| [主机边界决策](plans/2026-11-02-host-boundary-decisions.md) | 计划 | `2026-11-02` | 五款剩余主机最终边界：AtomS3R-Ext/StickV 为 boundary-only，K147/K147-CAM/D062-M12 为 composition-only（复用已接入控制器 host + A149 底座，不新增 alias）；含 M5Burner/GitHub release/上游 board 检索结果与重开条件 |
| [Atom VoiceS3R 主机接入](evidence/2026-11-02-atom-echos3r-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5atomvoices3r` 的原厂 UIFlow2 v2.5.4 启动、板级识别 145、128×128 面板与 Speaker/I2S1 DMA 非静音 PCM；功放、IR、麦克风、Grove Unit 与物理声学未验 |
| [AtomS3U 主机接入](evidence/2026-11-02-atoms3u-host/README.md) | 设备接入 / 虚拟设备 | `2026-11-02` | 独立 `m5atoms3u` 板级的官方 UIFlow2 v2.5.4 启动、GPIO41 按键与 GPIO35 WS2812 RMT 限定通过；IR、SPM1423 PDM 麦克风、Grove Unit、USB CDC 与物理行为未验 |
| [AIFlow simulator skill consumer](plans/2026-10-27-aiflow-simulator-skill.md) | 调用侧历史验证 | `2026-10-27` | CoreS3/PIR 本机限定验证，远端 AIFlow 未验 |
| [通用与 AIFlow Agent Skills](plans/2026-10-29-agent-skills.md) | 调用侧分发 | `2026-10-29` | 独立 helper、配置与打包；不继承硬件 PASS |
| [文档维护指引](AGENTS.md) | 维护契约 | `2026-10-30` | 首页双语对齐、权威/历史职责、插图来源、链接检查与生成快照顺序 |
| [文档与首页整理计划](plans/2026-10-30-docs-readme-refresh.md) | 交付计划 | `2026-10-30` | 文档范围盘点、精简中文首页、英文入口、本轮截图和分层 AGENTS 的验收 |
| [首页插图来源](images/README.md) | 插图来源 | `2026-10-30` | 本轮浏览器运行与仅模型画廊的不同来源、范围、复现及视觉检查 |
| [文档整理验证](evidence/2026-10-30-docs-homepage-refresh/README.md) | 文档验证证据 | `2026-10-30` | 盘点修订、双语页面、插图、指引和离线检查；不增加硬件或完整设备 PASS |
| [工程交接总览](engineering-handoff.md) | 人读交接 | `2026-11-03` | 先按本轮 P0 区分已完成、在推进和未开始，再给出产品边界、代码盘点、成熟度、阅读顺序、工作流、下一步和文档职责；新增“本轮收口”节（158 implemented/2 DEFER/41 层/模型 bug 入口）；动态事实仍链接权威入口 |
| [工作流总台账](workstreams.md) | 工作流导航与当前在途 | `2026-11-03` | 维护已交付代码面、当前在途、推进顺序、下一验收门禁、稳定代码入口和未完成 Task ID；`UNIT-01` 标记为已完成（virtual-device），`UI-01` 外壳保真仍开放 |
| [自动项目快照](project-snapshot.md) | 生成事实 | `2026-11-03` | 分别记录 catalog 日期、当前事实复核和最新 evidence；从 profile/evidence/Backlog 自动生成设备、样本、缺口、Task、测试规模，并盘点权威页和委派文档的新鲜度 |
| [项目当前状态](project-status.md) | 当前结论 | `2026-11-03` | 唯一维护当前能力和限制，区分浏览器/原生/模型/物理边界；Unit 160=158 implemented/partial+2 DEFER、25 c 类边界、canonical 41 层链；Core2 legacy stock startup 更广 setup/REPL 与任意应用继续开放 |
| [项目 Backlog](project-backlog.md) | 待办 | `2026-11-03` | 先列出已完成里程碑和“局部完成不扩大结论”的解释，再只保留尚未达到验收条件的任务、依赖、并行条件和验收；Unit 仅剩 2 项 DEFER（mini-bps-v11/mini-pdm），`FW-03` 仍保留真实业务和更多固件族 |
| [代码与验证入口地图](code-map.md) | 实现地图 | `2026-10-30` | 当前源码、FirmwareManifest/Secure Boot、runtime priority、Core2 flash-IPC/timer/stateful-SSI/cross-core、CIDR/domain/CNAME、multicast/unicast discovery、worker-local QEMU 与 `qemu-unified` partition fencing、namespace/container-local execution、Unit、测试/evidence/文档生成入口；包含 `SVC-03` 的低风险拆分顺序 |
| [验证证据台账](validation-ledger.md) | 证据历史 | `2026-11-03` | 按日期追加当时结论、检查项和 evidence，不反向定义当前能力 |
| [GitHub issues #2–#10 顺序复测](evidence/2026-10-27-issues-2-10/README.md) | 历史证据 | `2026-10-27` | 固定最终 runtime、session、固件、串口/QOM/帧/evidence 哈希；#2/#3 失败保持 open，#4–#10 的限定虚拟设备结论不转授物理硬件 |
| [证据保留规则](evidence-retention.md) | 交付契约 | `2026-10-27` | 必要 fixture、哈希、精简总结和复现入口；历史 raw 外置，普通 CI 与显式归档审计分开 |
| [纯浏览器执行调研](browser-runtime-feasibility.md) | 架构调查 | `2026-10-28` | esp-online-tester 固定源码、体积与板级范围；独立源码构建的当前浏览器实验及不可继承边界 |
| [GitHub Pages 虚拟设备部署](pages-deployment.md) | 部署契约 | `2026-11-04` | 逐板准入、默认UIFlow源码工作台/可选旧示例、未知UART与仅模型边界；固定源码构建、完整门禁、CI串行及管理员手动main/publish流程，源码与实际线上版本分开 |
| [WASM 性能与多设备计划](plans/2026-10-29-wasm-performance-devices.md) | 本轮交付计划 | `2026-10-29` | 共享帧、宿主等待、正常时钟候选和四板逐例准入；归档、验证和 PR 交付范围 |
| [运动、电源与复位修复](plans/2026-10-29-motion-power-device-adaptation.md) | 当前交付计划 | `2026-10-29` | Arduino/UIFlow 舵机输出、板级 PMIC 与保持供电、同实例复位、剩余 Atom/Stick 接入 |
| [StackChan Arduino 浏览器兼容性](stackchan-arduino-browser.md) | 固件行为与实现边界 | `2026-10-29` | 固定 Dance 的扭矩策略、真实串口/位置诊断、S3 Flash QIOR 相位与同实例复位 |
| [Arduino NVS 与供电复测](evidence/2026-10-29-stackchan-arduino-nvs/README.md) | 限定虚拟设备证据 | `2026-10-29` | 同固件新旧 Flash 读取对照、NVS 重开/复位保留、真实 torque 与 Plus2 USB/电池供电路径 |
| [舵机命令与经典主机后续验证](evidence/2026-10-29-motion-command-followup/README.md) | 限定虚拟设备证据 | `2026-10-29` | 重复扭矩与模式恢复、新增四板浏览器准入、PM1 真实单击复位及 IRQ 模式回归 |
| [Cardputer 与 StackChan 输入修复计划](plans/2026-10-30-cardputer-stackchan-input.md) | 当前交付计划 | `2026-10-30` | 原键盘 IRQ、横竖屏与局部刷新、运动期间屏幕触摸及阻塞负控 |
| [Cardputer 与 StackChan 输入证据](evidence/2026-10-30-cardputer-stackchan-input/README.md) | 限定浏览器虚拟设备证据 | `2026-10-30` | 67-patch 新 WASM、ADV 原键盘与四旋转、StackChan 后台 UART 与真实短按、保留失败 |
| [StackChan 跳舞与 ADV 全键证据](evidence/2026-10-30-stackchan-dance-and-cardputer-all-keys/README.md) | 精确镜像虚拟设备证据 | `2026-10-30` | 跳舞 BIN app-bound div6、真实 SCS 位移、56 物理键与 55 PC code；硬件 `NOT RUN` |
| [StackChan 跳舞与 ADV 全键 Pages 部署](evidence/2026-10-30-pages-stackchan-cardputer-production/README.md) | 当前部署证据 | `2026-10-30` | prepared-site 更新正式 HTTPS；线上 manifest/WASM/profile/keymap/wrapper 回读一致，本机 StopWatch/Sticks3 与两个原镜像通过；hosted macOS CDP target 残留使 regular all-admitted 仍 `PARTIAL` |
| [StackChan 舵机展示平滑与 Pages 更新](evidence/2026-10-31-stackchan-servo-smoothing/README.md) | 当前部署证据 | `2026-10-31` | 原始 SCS/QOM 不变，3D 关节按相邻样本插值；两次同固件 12/12、线上 CoreS3 guest 30/30、engine 与 pthread target 清理通过；source-build 工作流因 TLS 超时改走 prepared-site |
| [新增主机模型接入](plans/2026-10-29-expanded-host-models.md) | 主机视觉接入计划 | `2026-10-29` | 21 款新增主机、完整 Atom/Stick 系列、型号配置、贴图、实际工作台入口与能力边界 |
| [Atom / Stick 原厂固件运行接入](evidence/2026-10-29-expanded-hosts/README.md) / [Dial 旋钮诊断](evidence/2026-10-29-expanded-hosts/dial-rotary.md) | 当轮逐板限定验证 | `2026-10-29` | 原厂固件、原生与纯浏览器、GPIO/I2C/RMT、Flash 修复及未完成边界 |
| [剩余 Xtensa 浏览器接入](plans/2026-10-29-wasm-remaining-xtensa.md) | 后续交付计划 | `2026-10-29` | 六板独立组合、矩阵键盘、EPD QUALITY 抖色与真实输入/帧/清理；新 runtime 逐板验收后才能准入 |
| [剩余 Xtensa 浏览器准入证据](evidence/2026-10-29-wasm-remaining-xtensa/README.md) | 本地浏览器证据 | `2026-10-29` | 46 层固定源码、独立 engine Worker、矩阵键盘和 TCA W1C、EPD 精确抖色、10 板 11 例最终门禁；正式部署另验 |
| [浏览器性能与板型证据](evidence/2026-10-29-wasm-performance-devices/README.md) | 本地浏览器证据 | `2026-10-29` | 同固件 CPU 对照、实际动画像素变化与剩余触摸延迟；四板五示例按两个导出清单分别取证，不冒称正式 Pages 已更新 |
| [LVGL 正常时钟候选](evidence/2026-10-29-browser-lvgl-wallclock/README.md) | 限定候选证据 | `2026-10-29` | 显式 SDK Python 调度候选在同 guest 验证时间推进、真实字形/动画/触摸/PIR 和清理；stock SDK、C Timer 第一层和硬件不继承 |
| [正式 GitHub Pages 部署](evidence/2026-10-29-github-pages-production/README.md) | 历史部署证据 | `2026-10-29` | 原仓库 Actions 构建/部署成功；正式 HTTPS 地址独立执行真实 CoreS3 C/QEMU 21 项检查，LCD/触摸/PIR/QMP/分享重开/清理通过 |
| [Cardputer-ADV 用户固件兼容](evidence/2026-10-29-cardputer-adv-user-firmware/README.md) | 当前用户固件证据 | `2026-10-29` | 同一完整 Flash 的 ADC 错误、完整原生帧、自动竖屏设备/平面帧旋转、墙钟比例和旧矩阵输入门控；物理硬件不继承 |
| [CoreS3 C/QEMU 静态网页验收](evidence/2026-10-28-qemu-wasm-pages/README.md) | 历史证据 | `2026-10-28` | 固定源码完整构建、浏览器本地组合、真实 LCD/触摸/PIR及第二场分享启动/清理，Pages 单独记录 |
| [现有C/QEMU到WASM实验](qemu-wasm-port-research.md) / [构建与浏览器宿主证据](evidence/2026-10-28-qemu-wasm-build/README.md) / [CoreS3 guest证据](evidence/2026-10-28-qemu-wasm-cores3/README.md) | 历史执行研究 | `2026-10-28` | 固定当时完整WASM/CLI/QMP、CPU栈恢复、慢时钟CoreS3帧/触摸/PIR/停止重开；当时默认时钟失败保留，后续显式正常时钟候选、公众准入和部署分别以新证据为准 |
| [公众模拟器计划](plans/2026-10-28-public-simulator.md) | 进行中计划 | `2026-10-28` | 公众首页、Unit信息层级、新模型、URL分享、静态导出与部署前门禁 |
| [舵机、电源与复位预览](evidence/2026-10-29-motion-power-preview/README.md) | 限定虚拟设备与部署证据 | `2026-10-29` | StackChan UART/QOM 关节输出、同实例复位、真实 PMIC 关机及 fork Pages；Plus2 与完整回归仍开放 |
| [公众入口证据](evidence/2026-10-28-public-simulator/README.md) | 当前浏览器证据 | `2026-10-28` | exact WASM/ROM/固件绑定、真实串口/帧/输入/暂停停止；模型与原生桥接分别验证，未部署 |
| [Unit 源码 PR 精简](plans/2026-10-27-source-pr-cleanup.md) | 收尾计划 | `2026-10-27` | 重建精简分支、去除本机和历史附件隐式依赖，执行干净检出门禁 |
| [UIFlow2 双主机审计与修复](evidence/2026-10-27-uiflow2-api-sweep/README.md) / [计划](plans/2026-10-27-uiflow2-complete-api-sweep.md) | 当前审计 | `2026-10-28` | UI/硬件/系统/HTTP 逐项状态、原厂与 SDK 候选分 lane；最终完整矩阵 68/68，模型/配置/可选外设及 stock 失败仍保留 |
| [StopWatch / StickS3 / Core2 UIFlow2 三设备复测](evidence/2026-10-28-multi-board-uiflow2-revalidation/README.md) | 当前三设备证据 | `2026-10-28` | system、协议、M5UI 和 shared SDK 候选；requests2、BLE UUID32、Modbus transform/async 与 M5UI 缺陷有候选修复，其余模型/固件边界显式保留 |
| [QRCode.setText 与 TLS epoch 三设备候选固件](evidence/2026-10-28-qrcode-tls-candidate-firmware/README.md) | 当前候选固件证据 | `2026-10-28` | StopWatch/StickS3/Core2 各自完成 stock→candidate 对照；QR 旧文本失败均转为新文本解码 PASS，TLS 证书过期均转为 5/5 mTLS HTTPS PASS；incremental relink、真机和公网 PKI NOT RUN |
| [Display.drawPixel framebuffer transaction](evidence/2026-10-28-stopwatch-drawpixel-transaction/README.md) | 当前候选固件证据 | `2026-10-28` | StopWatch preimage 的 standalone even/odd 像素均未 flush；三台候选均通过 standalone 奇偶像素、相邻像素保留和显式嵌套事务；不是 CO5300 单像素限制 |
| [StopWatch / StickS3 / Core2 UIFlow2 音频数据面](evidence/2026-10-28-three-board-audio/README.md) | 当前三设备证据 | `2026-10-28` | 六个并发可见会话验证 Mic `record`/WAV 与 Speaker raw/WAV/file；修复 ESP32-S3 I2S completion 的固定时间窗；物理声学仍 NOT RUN |
| [Core2 UIFlow2 触控条与电源键回调](evidence/2026-10-28-core2-touch-buttons/README.md) | 当前 Core2 输入证据 | `2026-10-28` | A/B/C 经 FT5x06 触控条、PWR 经 AXP2101 事件；四个回调与 remove 全通过，修复首次触控分支吞掉 `key:p` 的路由错误 |
| [Core2 pending SPI IRQ remap](evidence/2026-10-28-core2-intmatrix-pending-irq/README.md) | 当前 Core2 中断证据 | `2026-10-28` | `0064` 修复 source level 已高时映射写回不重算的 INTMATRIX 缺陷；同固件/ELF pre-fix timeout、fixed guest callback PASS，Core2 UIFlow2 设备组保持 6/6；legacy `RUNTIME-03` 仍 OPEN |
| [Core2 协作 IRQ、classic RMT 与三设备回归](evidence/2026-10-28-cooperative-highint-rmt/README.md) | 当前 Core2 运行时 / 三设备证据 | `2026-10-28` | `0065` 五轮关闭 high-priority DPORT handoff 调度死锁；`0066` 补 classic RMT 并越过 Neopixel 初始化错误，legacy 到达 `APIKEY`；normal-WDT reset、黑帧、display completion 和 setup/REPL 仍 OPEN。最终 runtime 三设备 system/候选/设备组并发回归 |
| [Core2 legacy VFS 与 WiFi fixture 校正](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md) | 当前 Core2 运行时证据 | `2026-10-28` | 通用 LittleFS 与缺 NIC 裸 QEMU 会污染 legacy 黑帧结论；matching LittleFS2 + `runtime=qemu-wifi` 120 秒已执行注入的 boot marker，但 setup/main、非空帧和 normal-WDT 仍失败，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy dual-SPI panel routing](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md) | 当前 Core2 显示证据 | `2026-10-28` | `0068` 将同一 panel sink 同时接到 HSPI/SPI2 与 VSPI/SPI3；legacy `m5stack` 绘制 probe 从 `0` 转为 `1422` nonblack pixels；原厂 startup UI 与 normal-WDT 仍 OPEN |
| [ESP-NOW loopback 与三设备接口复测](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md) | 当前三设备证据 | `2026-10-28` | `0067` 在 controller TX/RX DMA 上完成 opt-in ESP-NOW 同 guest peer loopback；三台 system/shared/17 设备组、通信、音频 wrapper 和候选 TLS/requests/Modbus 在同一 final runtime 重绑；外部/加密 peer、RF、物理硬件仍 NOT RUN |
| [三设备并发复测与 runner 竞态修复](evidence/2026-10-28-concurrent-fixture-and-ready-state/README.md) | 当前三设备证据 / 测试基础设施 | `2026-10-28` | 设备间并发完成 system/shared/协议/音频复测；`network.http_fixture=false` 消除固定端口竞争，marker action 等待 session `running` 消除首次 key 409，Core2 18 秒预算在隔离顺序复测中恢复三帧；stock HTTP/Modbus/M5UI 缺陷与真机边界保留 |
| [最新 runtime 三设备 UIFlow2 接口复测](evidence/2026-10-28-three-board-uiflow2-latest-runtime/README.md) | 当前三设备证据 | `2026-10-28` | `78555183…` 上三台 system/shared/17 设备组、socket/MQTT/network/EzData/ESP-NOW/audio 与 Device API 81 operations 通过；stock HTTP/Modbus/TLS 缺陷仍保留，requests/Modbus/TLS 候选在同一 runtime 重新 PASS |
| [StopWatch / StickS3 / Core2 UIFlow2 全接口复测](evidence/2026-10-29-three-board-uiflow2-full-retest/README.md) | 当前三设备证据 / runner 修复 | `2026-10-29` | `fccfa931…` 上完成 system/shared、通信、音频、ESP-NOW、BLE 和已选外设；StopWatch/Core2 M5UI 505 方法全量审计，stock 三缺陷与 Core2 candidate 帧路由问题保留；修复设备尺寸/旋转、Core2 预算、BLE identity 和 blocker 文案 |
| [Core2 TIMG WDTFEED 写保护语义](evidence/2026-10-28-core2-timg-wdt-feed/README.md) | 当前 Core2 运行时证据 | `2026-10-28` | `0069` 让 `WDTFEED` 在 `WDTPROTECT` 下仍可喂狗，同时保留配置写保护；同固件 60 秒正常 WDT 仍在 `17.2529 s` TG0 stage-1 reset，startup UI、setup/REPL 和应用帧仍 OPEN |
| [Core2 legacy UART 与虚拟时钟对齐](evidence/2026-10-29-core2-legacy-uart-clock/README.md) | 当前 Core2 启动证据 | `2026-10-29` | `0070` 给 opt-in UART trace 加虚拟时间戳；WDT-off 下 BOARD/APIKEY 到 `55.00 s`、boot.py 到 `77.11 s`，normal WDT 仍 `17.25 s` reset；`shift=2` 也未消除 reset，不能把 accelerator override 当修复 |
| [Core2 legacy status/CAS 关联](evidence/2026-10-29-core2-legacy-status-cas/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0075` 证明 RDSR WIP/BUSY 始终为 0，主要预算位于 `0xBB/64` 后的 scheduler/list 跨核锁竞争；failed-CAS slice yield 与原 normal-WDT 都在约 `17.249 s` 重置，`RUNTIME-03` 仍 OPEN |
| [Core2 legacy contended-CAS episodes](evidence/2026-10-29-core2-legacy-cas-episodes/README.md) | 当前 Core2 诊断证据 / 诊断修复 | `2026-10-29` | `0086` 修正 no-I/O TB 的 `Bad icount read`；热锁结构匹配到 `xTaskQueueMutex`/queue mux，failed-CAS yield 可缩短 10 秒 task-queue 等待，但 15 秒时等待转移到 queue mux 且 normal-WDT reset 不变；`RUNTIME-03` 仍 OPEN |
| [Core2 contended-CAS scheduler attribution](evidence/2026-10-29-core2-contended-cas-scheduler/README.md) | 当前 Core2 调度证据 | `2026-10-29` | `0088` 同 binary A/B 将 5 秒 CAS/contended/episode time 从 `1,070,625/984,964/2.240 s` 降到 `91,465/2,702/1.018 s`，SSI 工作近似不变；normal-WDT 仍 TG0 stage-1 reset，只证明 100 ms RR 放大 spin，不关闭 `RUNTIME-03` |
| [Core2 legacy IPC/flash handoff attribution](evidence/2026-10-29-core2-ipc-handoff-attribution/README.md) | 当前 Core2 诊断证据 / runner 控制 | `2026-10-29` | 三次 `17.2 s` normal-WDT freeze 稳定 CPU0 在 `spi_flash_op_block_func` 等待、CPU1 在 IPC/调度启动路径变化；显式 `--trace-sample` 防止跨 transaction 配对，2 秒全量控制的 13 对事务均为同步 `0 ns`；`RUNTIME-03` 仍 OPEN |
| [Core2 legacy flash handoff episode budget](evidence/2026-10-29-core2-handoff-episode-budget/README.md) | 当前 Core2 诊断证据 / 诊断修复 | `2026-10-29` | `0089` 修复 PC trace 的 `Bad icount read`；两次 normal-WDT 运行记录 reset 前约 `12.6k` 个 handoff，CPU0 block wait 累计约占 `57%`，单次最大 `<6.8 ms`；否定单次长 deadlock，启动仍在 WDT 前未完成，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy handoff issuer/phases](evidence/2026-10-29-core2-handoff-issuer-phases/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | 无 Flash issuer 的 handoff 仍约 `0.89 ms`；含一条 `0xBB/64` 和 status read 的 handoff 约 `0.86 ms`；initiator IPC 往返 source shape 独占约 `0.616 ms`。100us RR 与临时 can_start immediate-yield 均无改善，随后由 `0090` 的 per-vCPU icount budget cap 降低固定等待 |
| [Core2 per-vCPU icount fairness budget](evidence/2026-10-29-core2-icount-percpu-budget/README.md) | 当前 Core2 调度证据 / 默认修复 | `2026-10-29` | `0090` 为双 vCPU deterministic icount 增加默认 `10 us` per-vCPU budget cap；同 trace A/B 将 initiator `can_start→IPC return` 从 `563.7 us` 降到 `56.2 us`、peer block wait 从 `728.4 us` 降到 `184.7 us`，Core2 UIFlow2 设备组 `6/6 PASS`；normal WDT 仍在 `17.2429 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy boot budget 与 WiFi/UI wait](evidence/2026-10-30-core2-legacy-boot-to-ui-wait/README.md) | 当前 Core2 诊断证据 | `2026-10-30` | `shift=2` + `1 us` 在 normal WDT 下 `4.66 s` 到 BOARD/APIKEY、`8.50 s` 执行完原厂 boot.py，但仍为黑帧；WDT-off 15/20 秒双核 Waiti 且 Flash/cache 停在约 `9.36 s`，UART 诊断栈定位到 `wifiWebCfg/menu-wifi/m5stack_ui`，timing 控制不是产品修复 |
| [Core2 TIMG watchdog feed rescheduling](evidence/2026-10-30-core2-timg-feed-reschedule/README.md) | 当前 Core2 watchdog 语义修复 | `2026-10-30` | `0091` 用 `timer_mod_ns()` 替换 anticipate 语义，使 `WDTFEED` 可推迟已武装的后续阶段；重建运行得到 `3,651` nonblack pixels 的 live frame，但 TG0 stage-1 仍 reset，`RUNTIME-03` 保持 OPEN |
| [Core2 legacy menu after WiFi configuration stub](evidence/2026-10-30-core2-wifi-stub-menu/README.md) | 当前 Core2 启动诊断 | `2026-10-30` | 仅 stub `wifiWebCfg.config_by_web`，当前显示/LVGL 路径即可渲染完整 `320x240` UIFlow 菜单帧（`76,760` nonblack / `417` colors）；原厂 WiFi 配置分区仍为空，故 `RUNTIME-03` 保持 OPEN |
| [Core2 legacy deviceCfg WiFi overlay](evidence/2026-10-30-core2-legacy-wifi-config-overlay/README.md) | 当前 Core2 配置 fixture / 诊断 | `2026-10-30` | Core2 `qemu-wifi` 只对 session Flash 副本应用严格校验的 legacy `deviceCfg`，并记录 hashed SSID/base/effective SHA；同一 effective Flash 在诊断控制下显示真实 `Connecting to myssid`，默认 WDT 仍在 boot 后触发 cache panic，`RUNTIME-03` 保持 OPEN |
| [Core2 concurrent capacity boundary](evidence/2026-10-30-core2-concurrent-capacity-boundary/README.md) | 当前 Core2 容量 / 重检证据 | `2026-10-30` | 九实例两次 `9/9 PASS`、一次 `8/9` 并在 `ble_hs_hci_process_ack` panic，因此默认单设备容量保持 8；当前 tool hash 两批 `2x60s` 为 `4/4 PASS`，网络重检有限重试、PSRAM/network error 分字段，八实例 cold-start 重绑和物理/controller 边界仍 OPEN |
| [Core2 current tool-hash rebind](evidence/2026-10-30-core2-toolhash-rebind/README.md) | 当前 Core2 工具哈希回归 | `2026-10-30` | SVC-03 拆分后 `device_service` hash 更新为 `a96b1506…`；在 `origin/main@3fc436e4` 上两批独立零错峰 `2x60s` 均 `2/2 PASS`，合计 `4/4`，HLI/PSRAM/网络/GATT/frame/QOM/pcap/evidence/cleanup 全部通过；不覆盖八实例 cold-start、九实例容量或物理边界 |
| [Device Service storage/NVS parsing boundary](evidence/2026-10-30-svc03-execution-parsing/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | storage/NVS execution request parser 移至独立无状态模块，`device_service.py` 保持 same-object re-export；专向 `5/5`、Device Service `126/126`，错误码、返回结构和 API 不变 |
| [Device Service network execution parsing boundary](evidence/2026-10-30-svc03-network-execution/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | esp-emu network execution request parser 移至独立无状态模块，`device_service.py` 保持 same-object re-export；专向 `4/4`、Device Service `126/126`，profile/port/ELF/I2C 契约不变 |
| [Device Service QEMU WiFi semantic boundary](evidence/2026-10-30-svc03-qemu-wifi/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | QEMU WiFi security parser 和 runtime-env projection 移至独立模块，`device_service.py` 保持 same-object re-export；专向 `4/4`、Device Service `126/126`，open/WPA2 与 S3 trace gate 不变 |
| [Core2 WiFi IRQ cache handoff gate](evidence/2026-10-30-core2-wifi-irq-cache-gate/README.md) | 历史 Core2 中断语义修复 | `2026-10-30` | `0092` 在 instruction cache disabled 时只暂存 WiFi MAC level，cache restore 后重放；默认 budget 的同固件不再出现 cache-disabled panic，并到达 API Key 页面。该里程碑后的 TG0 WDT reset 已由 `0095` 记录解除 |
| [Core2 classic WiFi station timing and data path](evidence/2026-10-30-core2-classic-wifi-station-time/README.md) | 历史 Core2 WiFi 语义/数据面修复 | `2026-10-30` | `0093/0094` 将 classic WiFi beacon/inject/timestamp 改用 virtual time，并让 station DHCP 与双向数据使用正常 slirp 路径；stock Core2 WiFi scan→association→DHCP→HTTP `5/5 PASS`、IP `10.0.2.15`。该轮 normal-WDT reset 后由 `0095` 记录解除 |
| [Core2 legacy WDT level delivery](evidence/2026-10-30-core2-legacy-wdt-level-delivery/README.md) | 当前 Core2 watchdog/startup 修复 | `2026-10-30` | `0095` 按 `WDTCONFIG0.LEVEL_INT_EN` 修复 legacy task-WDT level delivery；同一 public SHA 三次 normal-WDT Device Service 均越过原 stage-1 reset、稳定到 guest virtual 300 秒以上并保持 API Key startup UI，Core2 设备组 `6/6 PASS` |
| [Device Service network parsing boundary](evidence/2026-10-30-svc03-network-parsing/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | network policy/CNAME parser 移到 `device_service_network.py`，`device_service.py` 保持 same-object re-export；定向与 network-focused tests PASS，不改变 HTTP/state/evidence 语义 |
| [Device Service device-spec boundary](evidence/2026-10-30-svc03-device-specs/README.md) | `SVC-03` 边界重构证据 | `2026-10-30` | `DeviceSpec`、catalog/matrix/profile 解析、backend 路径与 runtime profile 选择移到 `device_service_specs.py`；原模块 same-object re-export，定向 `5/5 PASS`，不改变 HTTP/QEMU/session/evidence 语义 |
| [Cardputer-ADV 当前参考固件 BMI270 闭环](evidence/2026-10-29-cardputer-adv-imu/README.md) | 当前设备证据 | `2026-10-29` | I2C `0x69`、CHIP_ID/INIT/data-ready 与 `0x0C..0x17` 读取可达；Device Service 注入经官方 `Imu.getAccel/getGyro` 回读，原样矩阵首轮 PASS；关闭当前参考固件 IMU 全零待办，物理精度仍 NOT RUN |
| [Core2 legacy pre-boot phase profile](evidence/2026-10-29-core2-preboot-phase-profile/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | 显式 PC/UART sampling 记录 WDT-off 80 秒的 SSI transaction/RX 聚合总量与 108 个采样 begin event；全量 command/length 分布仍未知，四类立即切核控制均无改善并丢弃，normal-WDT 仍 stage-1 reset |
| [Core2 SSI transaction profile](evidence/2026-10-29-core2-ssi-transaction-profile/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0071` 输出完整 command、RX-length、completion→next-command gap 聚合；无采样控制得到约五万组 `0x05` 与 `0xBB/64B`，`79.7/80 s` 位于相邻 command 间隔；normal-WDT 仍 `17.2537 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 SSI command correlation](evidence/2026-10-29-core2-ssi-command-correlation/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0072` 确认 `0xBB/64 -> 0x05/1 -> 0xBB/64` 主循环；`82.4%` gap 位于下一次 status read 前，平均 `1.3115 ms`；normal-WDT 仍 `17.2494 s` reset，`RUNTIME-03` 保持 OPEN |
| [Core2 SSI command issuer PC](evidence/2026-10-29-core2-ssi-command-pc/README.md) | 当前 Core2 诊断证据 | `2026-10-29` | `0073` 将 `0x05` 主要绑定到 ROM `esp_rom_spiflash_read_user_cmd` 区间的 `0x4006222c`，将 `0xBB/64` 主要绑定到应用 segment 5 的 `0x40093b57`；PC 表总数等于 `105,161` transactions，normal-WDT 仍 `17.2536 s` reset，无 matching ELF 函数名，`RUNTIME-03` 保持 OPEN |
| [Core2 M5UI panel DMA 双写修复](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md) | 当前 Core2 UIFlow2 证据 | `2026-10-29` | `0074` 修复 DMA descriptor 与 CPU data-register 对同一 panel flush 的双消费；`6400`-byte strip 从写成 `12736` bytes 变为 exact，candidate 4 个状态与 2 个 frame oracle 全部 PASS |
| [Core2 post-reset teardown](evidence/2026-10-29-core2-post-reset-teardown/README.md) | 当前 CORE2-02 teardown 证据 | `2026-10-29` | 三个 ready session 先冻结 frame/QOM/network/GATT/pcap，再执行 guest `system_reset`；同一 QEMU PID reboot-in-flight 时仍 running，随后 stop、companion/PID/lease cleanup 与下一轮恢复均 `3/3 PASS`；不关闭 controller/物理/真机边界 |
| [Core2 stock BLE via native HCI](evidence/2026-10-29-core2-stock-ble-native-hci/README.md) | 当前 Core2 BLE 证据 / runner 修正 | `2026-10-29` | stock UIFlow2 `ble-nus` 改走 `core2-native-hci` + matching ELF；三个独立 session 各 `8/8 PASS`，peer 实际收到 `ACK:M5_CORE2_UNIFIED`；StopWatch/StickS3 stock controller、安全与 RF 不继承 |
| [Device Service runtime boundary 与 Core2 unified 稳定性](evidence/2026-10-29-svc03-runtime-boundary/README.md) | 当前 service 证据 / 调度修复 | `2026-10-29` | 无状态 runtime 参数/脱敏边界独立；profile QOM 跟随 session readiness，Core2 unified 默认 180 秒；BLE peer 在订阅后等待 10 秒再写，避免慢 guest TX 未就绪；最终 firmware/ELF/QEMU 三条独立 lease 全 PASS，WiFi、公网、NUS ACK、frame/QOM、HLI、pcap、ZIP 和清理完整 |
| [Core2 `m5ble.Server.get_client` candidate](evidence/2026-10-29-m5ble-get-client-candidate/README.md) | 当前 Core2 BLE 候选证据 / teardown 时序 | `2026-10-29` | stock `m5ble-server` 保留 `21 PASS + 1 ERROR`；`0021 → 0025` 最终候选两轮均 `22/22 PASS`；并发断连后的 `deinit` 竞争以 2 秒 settle 修正，stock/candidate 复核均 PASS；真机/安全/RF NOT RUN |
| [StopWatch / StickS3 / Core2 UIFlow2 接口再次复测](evidence/2026-10-29-three-board-uiflow2-interface-retest-r2/README.md) | 当前三设备证据 / M5UI runner | `2026-10-29` | `9bf74439…` 上三台重新完成 system/shared、协议、板级接口和 ESP-NOW；StopWatch/Core2 重跑 28 类、505 个 M5UI widget 方法与两个 lifecycle 项；requests2/Modbus/TLS/M5UI 与 `0021+0025` M5BLE candidate 全部复验；stock SDK、StopWatch/StickS3 BLE 和物理边界保留 |
| [最新 QEMU 三设备 UIFlow2 接口复测](evidence/2026-10-29-three-board-uiflow2-interface-retest-r3/README.md) | 当前三设备证据 | `2026-10-29` | `05a43941…` 上三台 system/shared、协议、audio、ESP-NOW、BLE 和板级接口重跑；StopWatch/Core2 M5UI 仍 507 结果零漏测；stock SDK 缺陷和 candidate 结果保持不变；Core2 network 首轮并发扫描毛刺经隔离及 4 次并发重复控制；真机/RF/legacy 边界保留 |
| [当前 QEMU 三设备 UIFlow2 接口复测 r4](evidence/2026-10-29-three-board-uiflow2-interface-retest-r4/README.md) | 当前三设备证据 | `2026-10-29` | `dd4b1b34…` 上三台并发重跑 system/shared、协议、audio、ESP-NOW、BLE、M5UI 和板级接口；Core2 network 首次并发恢复 `14/14`；stock SDK 与 BLE 边界不变，三台协议 candidate 和 StopWatch/Core2 M5UI candidate 全部通过 |
| [ESP-NOW 外部明文 peer](evidence/2026-10-29-espnow-external-peer/README.md) | 当前 ESP-NOW 外部 peer 证据 | `2026-10-29` | `0076` 以成对 loopback UDP 端口连接两个独立 controller；StopWatch↔StickS3、Core2↔StopWatch 均经正常 TX/RX DMA 双向收到 action-frame payload；四个 session evidence/清理完整；PMK/LMK/CCMP、错误 key、lifecycle、RF 和真机仍 NOT RUN |
| [ESP-NOW external peer CCMP](evidence/2026-10-29-espnow-external-ccmp/README.md) | 当前 ESP-NOW 加密证据 | `2026-10-29` | `0077` 在 external bridge 执行 PMK-wrapped LMK、AES-CCMP/MIC 和 drop-before-DMA；正确 key 跨 StopWatch/StickS3/Core2 交付，错误 LMK 双向 `rx_packets=0`，wrong-PMK/same-LMK 按官方语义 PASS；guest key-state 传播、replay、lifecycle、RF 和真机仍 NOT RUN |
| [ESP-NOW external CCMP replay](evidence/2026-10-29-espnow-external-ccmp-replay/README.md) | 当前 ESP-NOW replay 证据 | `2026-10-29` | `0078` 对 MIC 成功的单 peer CCMP PN 执行 monotonic guard；UDP proxy 重复一帧后 receiver 记录一次 replay drop 且 guest payload 不重复；wrong-LMK 与 Core2 encrypted 回归保持；多 peer/乱序窗口、key rotation、RF 和真机仍 NOT RUN |
| [ESP-NOW native peer lifecycle](evidence/2026-10-29-espnow-peer-lifecycle/README.md) | 当前 ESP-NOW lifecycle 证据 | `2026-10-29` | stock native API 在 StopWatch/StickS3/Core2 完成 encrypted add、delete、NOT_FOUND 负控、modify、re-add 与 post-resume delivery；双向 PRE barrier 修复 Core2 首轮竞态；guest key-state 写入 bridge、key rotation、多 peer replay、RF 和真机仍 NOT RUN |
| [M5ESPNow wrapper lifecycle](evidence/2026-10-29-espnow-m5espnow-lifecycle/README.md) | 当前 ESP-NOW wrapper 证据 | `2026-10-29` | `m5espnow.M5ESPNow` 在 StopWatch/StickS3/Core2 完成 set_add_peer、peer list 清空、delete 后 send_data no-op、re-add 与 post-resume；guest key-state、key rotation、多 peer replay、RF 和真机仍 NOT RUN |
| [ESP-NOW CCMP replay window](evidence/2026-10-29-espnow-external-ccmp-window/README.md) | 当前 ESP-NOW reorder 证据 | `2026-10-29` | `0079` 提供单 peer 64-frame authenticated window；UDP ReorderProxy 交换两帧后 replay drop 为 0 且双向 payload 保持；duplicate replay 仍 drop，Core2 encrypted 回归 PASS；multi-peer window、key rotation、RF 和真机仍 NOT RUN |
| [ESP-NOW guest controller key-state](evidence/2026-10-29-espnow-guest-key-state/README.md) | 当前 ESP-NOW key lifecycle 证据 | `2026-10-29` | `0080` 将 classic ESP32/S3 crypto key store 接到 external bridge；runtime-env 不含 PMK/LMK 时，stock guest 写入 slot 24 后正控双向交付，不同 guest LMK 两端 `rx_packets=0`，delete/re-add/modify 轮换新共享 LMK 后恢复；multi-peer、PN wrap、RF 和真机仍 NOT RUN |
| [ESP-NOW 三 guest shared-LMK fabric](evidence/2026-10-29-espnow-peer-fabric/README.md) | ESP-NOW shared-LMK fabric 证据 | `2026-10-29` | `0081` 让 StopWatch/StickS3/Core2 经同一个 broker 双向三端交付；synthetic MAC 在 CCMP 前写入，replay window 按 source peer 分片 8×64；重复真实 forwarded frame 仅目标 receiver 记录一次 drop；0081 本身限定 shared LMK，per-peer routing 由后续 0082 单独验证 |
| [ESP-NOW per-peer LMK routing](evidence/2026-10-29-espnow-per-peer-key-routing/README.md) | ESP-NOW pairwise-key 证据 | `2026-10-29` | `0082` 从 stock key entry bytes `0..5` 取 peer MAC、`8..23` 取 LMK，TX/RX 按方向选 key，并为每 slot 保存独立 TX PN；三个 pairwise key 的六方向 PASS，B/A cross-wire 只使 A↔B 归零；shared-LMK 与 direct guest-key 回归保持；PN lifecycle 由后续 0083 单独验证 |
| [ESP-NOW CCMP PN exhaustion and rekey](evidence/2026-10-29-espnow-ccmp-pn-exhaustion/README.md) | 当前 ESP-NOW PN lifecycle 证据 | `2026-10-29` | `0083` 在 `0xffffffffffff` fail closed、不回绕；新 LMK 后恢复双向 payload，相同 LMK 重写保持 PN/replay 并继续 drop；shared-LMK、pairwise 正控和 cross-wire 回归 PASS；loss/retry、channel/rate、RF 和真机仍 NOT RUN |
| [ESP-NOW loss/retry, channel/rate and soak](evidence/2026-10-29-espnow-loss-channel-rate/README.md) | 当前 ESP-NOW link-condition 证据 | `2026-10-29` | `0084` 在真实 frame bridge 上传递并校验 channel/rate metadata；受控丢两帧后重试恢复，channel 6 正控 PASS、1↔6 各 40 次 drop，11/24 Mbps 混合交付，60 秒双向 soak 超千次 TX/RX 且无重复/错误；仅为 virtual link，RF、bit-exact controller 和真机仍 NOT RUN |
| [Worker claim response-loss idempotency](evidence/2026-10-29-worker-claim-idempotency/README.md) | 当前 durable queue claim 证据 | `2026-10-29` | 真实 HTTP/WorkerAgent 在首个 claim response 被丢弃后复用同 key 重试；restart 前后同 job/lease，第二 job 保持 queued，异请求 409、过期 lease fail closed，raw key 不落盘；物理跨主机、QEMU guest 和外部 side-effect fence 仍 NOT RUN |
| [Lease-bound remote evidence store](evidence/2026-10-29-lease-bound-evidence-store/README.md) | 当前 worker evidence 证据 | `2026-10-29` | 真实 HTTP WorkerAgent 上传约 2 MiB ZIP，上传 response 丢失后同 bytes 重试返回原 evidence ID；control-plane restart 后 metadata/content 一致，异 bytes 与错误 result binding 409，`0600` 文件且 raw payload 不进入 queue/log；物理跨主机和对象存储复制仍 NOT RUN |
| [Device Service runtime ACL](evidence/2026-10-29-runtime-acl/README.md) | 当前 service runtime policy 证据 | `2026-10-29` | 外部 operator JSON 按设备限制 serial/input/reset、program execute/interrupt/read、package write 和 flash read；真实 HTTP 的未授权操作在 console/QMP/flash I/O 前 403，policy hash/有效权限可审计，package deny path 不创建 revision；guest filesystem ACL、native firmware 沙箱、QEMU 和真机仍 NOT RUN |
| [Core2 for AWS ATECC608](evidence/2026-10-29-core2-atecc608/README.md) | 当前 Core2 runtime-model 证据 | `2026-10-29` | `0085` 在 `0x35` 实现 wake/Read/Info/CRC 和锁定测试 config，并修复 classic ESP32 DMA link-start/DC；公开固件三个独立 session 从 `atcab_init=f0`/abort 推进到 `atecc608: ok: 60 02` 与非空帧；生产 key、ECDSA、电气和真机不继承 |
| [Unit Relay/Relay2 hard-reset边界](evidence/2026-10-29-unit-hard-reset-output-boundary/README.md) | 当前 Unit 复位证据 | `2026-10-29` | `0087` 让共享 GPIO reset 先建立复位后电平/通知 observer，再走正常 listener；AtomS3R 同固件 A/B 中 pre-fix 单 Relay/Relay2 计数跨 reset 泄漏，fixed 在 reset 清零后分别从独立高电平重新计数；数字 GPIO only，机械/电气/其它 Unit reset 不继承 |
| [FlashLight cold-route四host](evidence/2026-10-29-flashlight-cold-route-four-host/README.md) | 当前 Unit 冷启动证据 | `2026-10-29` | `0047/e318` 在 CoreS3/AtomS3R/StickS3/StopWatch 用原厂constructor、100%/220ms Flash和Run替换，从`ready-low`到`flash-active`再回`ready-low`；actual QOM mounted replay PASS，实时Web、动态S1/PWM/光电/热/真机不继承 |
| [Device Service API](device-service-api.md) / [OpenAPI](device-service.openapi.yaml) | 契约 | `2026-10-29` | `1.51.0`；新增 operator-owned runtime ACL/执行策略，session/capacity 暴露 policy hash 与有效权限；保留 1.50 worker evidence、claim response-loss replay、Unit准入、冻结 schema、lease/evidence 及网络契约 |
| [外部 Agent Unit API](unit-agent-api.md) | 调用指南 | `2026-10-29` | UIFlow2 源码提交、caller-source pin、可见 session、Unit 配置和取证；CoreS3 选定场景的源码请求与原驱动/custom 边界，Relay/Relay2 hard-reset A/B 已限定闭环，硬件 NOT RUN |
| [统一设备运行时契约](unified-device-runtime.md) | 契约 | `2026-10-26` | 单 lease、单 guest、单固件、单 evidence bundle 的不变量和状态语义 |
| [Core2 native HCI backend](core2-native-hci-backend.md) | 设计 / 验证专题 | `2026-10-30` | native-HCI 数据面、PSRAM/MMU、长稳、重连、active-stop、post-reset stop、八实例容量和九实例 fail-closed 边界；轮次与哈希只在该专题的日期化证据中，旧失败 control 保留为历史 |
| [FirmwareManifest](firmware-manifest.md) | 契约 | `2026-10-26` | 导入、规范化、ZIP path/casefold/symlink 与资源唯一性、多 build SoC 选择、mandatory `capabilities.required/optional`、WebBurner 分段 size/digest 复算及来源展示、Secure Boot v2 签名/包内 eFuse 摘要与 anti-rollback version 对照、aggregate/image/eFuse understatement fail-closed、文件系统/许可策略、sdkconfig detected / image observed capability 和 evidence 分层 |
| [运行时模型缺口登记](runtime-model-gap-register.md) | 缺口登记 | `2026-11-04` | 每个 `RUNTIME-*` 的现象、证据、修复状态和关闭条件；`0095` 已关闭 legacy Core2 normal-WDT stock startup；RUNTIME-07/08保留StamPLC原策略复位PIF和Cardputer复位WASM越界，精确策略或诊断通过不关闭根因；Zigbee、bit-exact controller、物理 RF/电气和真机边界仍独立 |
| [网络模拟方案](network-simulation-plan.md) | 架构 / 验收专题 | `2026-10-26` | 网络模式、有界 CIDR egress、domain/CNAME、multicast/unicast discovery、worker process/QEMU 与 `qemu-unified` companion partition fencing、namespace/container-local execution、同 guest 网络生命周期和证据要求；运行比例转交验证台账 |
| [网络诊断 lane](network-lane.md) | 专题 | `2026-10-26` | 只描述诊断/Provisioning，不混同 unified 验收；Linux namespace IPv6 guest 生命周期已 PASS |
| [虚拟主机矩阵](qemu-device-adaptation-matrix.md) | 当前事实 | `2026-10-26` | 当前登记设备与各 QEMU/Tab5/Linux 后端、稳定运行时映射和能力边界；设备数量与运行比例分别转交自动快照和验证台账 |
| [UIFlow2 外设矩阵](uiflow2-peripheral-test-matrix.md) | 当前事实 | `2026-10-26` | 外设数据面和 runner 语义；主线完整矩阵基线由 `0036` stateful SSI 重建定义，`0038` 为 exact-time 诊断加定向回归；Unit 扩展 runtime 的完整门禁分别核验，不跨 binary 拼接；轮次和 case/check 数量只查验证台账与 evidence |
| [Tab5 暂缓项](tab5-deferred-backlog.md) | 专项 Backlog | `2026-10-26` | 能力仍以 2026-10-22 定向证据为基线；后来的 S3/C6/Core2 无线工作不继承给 P4 |
| [设备视觉保真](device-visual-fidelity-backlog.md) | 专项 Backlog | `2026-10-26` | StopWatch 是唯一参考质量外壳；后续功能验证不代表视觉模型已升级 |
| [Core2 cache/WDT 调查](core2-cache-panic-investigation.md) | 历史根因 | `2026-10-30` | 保留旧命名和复现、TCG translation-buffer 归因与 UIFlow2 门禁；补充 timer/WDT-mask、stateful SSI、统一 timeline、WDT-disabled 对照、public BIN/local ELF 字节审计、exact-time SIGSTOP freeze 和三次 WDT liveness 对账。历史 `800 ms` 现象未在当前配置复现；后续 `0095` 关闭 virtual stock startup，setup/REPL 与任意应用另验 |
| [跨设备回归审计](uiflow2-cross-device-regression-audit.md) | 历史证据 | `2026-10-21` | 固定在当轮修复和截图 |
| [StopWatch QEMU 启动](stopwatch-uiflow2-qemu.md) | 历史证据 | `2026-10-20` | 解释初轮启动链，不描述后续 multi-board 能力 |
| [部署与运行时资产](deployment.md) | 运维指南 | `2026-11-03` | 区分目录/浏览器导出/原生服务资产，解释匹配源码与主机架构、历史运行时包和隔离权限的边界；已核对当前 inventory（Unit 160=158+2、41 层） |
| [设备中心接入契约](device-center-adapter.md) | 接口契约 | `2026-10-26` | 目录、外设接口、设备状态、worker lifecycle 与页面消息 |
| [虚拟设备功能测试工作流](device-functional-test-workflow.md) | 工作流契约 | `2026-10-30` | 原生功能测试使用可观察 Device Service 会话；显式浏览器验证另保留同实例输入/帧与清理，不混用证据 |
| [固件审查与仿真工作流](firmware-review-and-simulation-workflow.md) | 工作流契约 | `2026-10-26` | 审查方法和证据分层、Secure Boot v2/包内 eFuse 摘要与 anti-rollback version 对照、公开 BIN 刷新/SHA 绑定、运行路径和发布门禁；当前进度回权威状态页 |
| [外设仿真架构](peripheral-simulation-architecture.md) | 实现专题 | `2026-10-26` | catalog、runtime coverage、S3 WPA2/Core2 native-HCI 边界和后端数据面 |
| [P4 外设后端要求](p4-peripheral-backend-requirements.md) | 专项设计 | `2026-10-26` | Tab5 缺失的 P4 控制器、DMA 和端点；仍以 2026-10-22 focused probe 为能力基线 |
| [模拟器服务架构](simulator-service-architecture.md) | 设计 / 运维 | `2026-11-03` | 单机模块化单体、control/runtime 分离、multicast/unicast discovery、network-partition fence、双 namespace worker-local QEMU、companion recovery 和 warm-pool 边界；2026-11-03 核对 serve.py 入口/默认端口与 CLI 示例一致 |
| [热门用户固件矩阵](user-firmware-simulation-matrix.md) | 验证工具与历史基线 | `2026-10-30` | 历史哈希绑定结果、公开 CDN 强制刷新、四个刷新样本、SD/NVS fixture、OpenAI 首次启动对照；Core2 2026-10-26 基线之后由 `0095` 关闭 virtual stock startup，setup/REPL 与任意应用仍另验 |
| [CoreS3 图像边界](cores3-image-rendering-boundary.md) | 已知差异 | `2026-10-26` | 仍固定在 2026-10-22 透明度/调色板图像分析，状态保持 `OPEN` |
| [CoreS3 三渲染器](cores3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [StickS3 三渲染器](sticks3-three-renderer.md) | 历史证据 | `2026-10-22` | 固定三种渲染路径的对比 |
| [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md) | 历史设计 | `2026-10-20` | 早期后端和能力分层，不代表当前设备状态 |
| [Unit 集成计划](plans/2026-10-25-unit-runtime-integration.md) | 历史实现设计 | `2026-11-03` | 保留同guest程序/共享采样等设计时点；页首已标记 UNIT-01 收口（158 implemented+2 DEFER、41 层）；当前能力见状态页/战役汇总，正文不再作为活动队列 |
| [Unit 接入问题](unit-integration-host-issues.md) | 历史参考记录 | `2026-11-03` | 接入期间发现的主机问题与处理边界；页首注明 UNIT-01 已收口，当前能力见状态页/战役汇总；UNIT-HOST-36 以数字 Relay/Relay2 A/B 关闭 |
| [AIFlow实时预览API评估计划](plans/2026-10-26-aiflow-live-preview-api.md) | 实现/设计 | `2026-10-27` | UIFlow同guest程序、QEMU按需共享帧和1.42 Preview/Run基础已实现；限定Web托管消费者已验，SSE与AIFlow完整接入仍待做，继承Unit/服务Backlog |
| [同VM Preview/Run控制面](plans/2026-10-27-preview-run-control.md) | 实施计划 | `2026-10-27` | 持久化身份/幂等/latest-wins、真实prompt取消、managed session与输入/帧fence；CoreS3 PIR/Relay限定实际会话与宿主负控已验，PIR部署事务取消已验，AIFlow/其它Web组合/GC仍开放 |
| [Preview Web消费者](plans/2026-10-27-preview-web-consumer.md) | 实施计划 | `2026-10-27` | 共享Preview身份、完整包保留编辑、主机/Unit输入、Run帧与生命周期；CoreS3 PIR/Relay限定真实Web验收完成，AIFlow/SSE仍开放；构图限定修复见下一块 |
| [Preview 控制组与 2Relay](plans/2026-10-27-preview-controls-and-2relay.md) | 实施计划 | `2026-10-27` | 四主机同VM丰富HUB控制组、U131双GPIO/蓝灯和限定窄屏/长dt相机已验；新运行时定向7PASS、完整矩阵66/67，边界保留 |
| [二进制checkpoint与Unit协议](plans/2026-10-27-binary-checkpoint-and-unit-protocols.md) | 实施计划 | `2026-10-27` | 分开不可变二进制包存储与固件loader能力，先验证旧Run不被不支持入口打断；兼容固件隔离构建与4Relay/FlashLight协议核对进行中 |
| [FlashLight与显式UIFlow base](plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md) | 实施计划 | `2026-10-27` | 本块完成严格base、候选loader诊断与FlashLight限定GPIO/Web验收；公共main.mpy、动态route历史与AIFlow继续 |
| [公共main.mpy实时入口](plans/2026-10-27-public-main-mpy-runtime.md) | 实施计划 | `2026-10-27` | 真实bytecode canary、会话身份绑定、显式base Preview与同VM import派发/恢复；stock能力保持分层 |
| [FlashLight路由历史](plans/2026-10-27-flashlight-route-history.md) | 实施计划 | `2026-10-27` | UNIT-HOST-38真实GPIO路由生命周期、旧资格失效与新EN复位恢复；冷route/PWM/S1保持独立 |
| [FlashLight冷pad观察](plans/2026-10-27-flashlight-cold-pad-observation.md) | 实施计划 | `2026-10-29` | UNIT-HOST-37真实GPIO/IOMUX/OE/来源事件、无边沿连续低基线与原驱动自然复位；新四host原厂constructor/API和QOM Web replay已闭合cold baseline，实时Web/动态S1/PWM仍独立 |
| [Core2 首帧与网络修复](plans/2026-10-27-core2-startup-issues.md) | 实施计划 | `2026-10-27` | issues #2/#3 的固件身份核对、离线 WLAN 控制器与 UIFlow2 LVGL 实际画面验证；不继承 legacy LVGL7 结论 |
| [Core2 启动修复验收](evidence/2026-10-27-core2-startup/README.md) | 历史证据 | `2026-10-27` | 固定 UIFlow2 v2.5.3 的离线 WLAN、实际 LVGL 画面及运行时/历史保留门禁；原始私有归档与硬件边界分开 |
| [Unit 官方协议](unit-research/official-protocols.md) | 参考依据 | `2026-10-26` | 官方芯片、驱动、物理端口、版本冲突与离线参考；不是 runtime PASS |
| [Scroll与Roller485官方协议审计](unit-research/scroll-roller485.md) | 参考依据 | `2026-10-26` | 固定官方驱动/内部固件；Scroll独立partial模型与RGB队列/回绕/bootloader缺口，Roller485仍visual-only；来源存在不替代逐主机验证 |
| [Encoder 协议冲突](unit-research/encoder-protocol-conflicts.md) | 参考依据 | `2026-10-26` | 官方文字与 executable driver 的按压极性冲突；保留原证据并按驱动路径验证 |
| [S3 ADC 合成校准](unit-research/esp32s3-adc-calibration.md) | 参考依据 | `2026-10-26` | 固定 IDF/app 字节、17字段白名单、整数 oracle 和虚拟 eFuse fixture；不是物理精度 |
| [Unit 视觉绑定边界](unit-research/visual-bindings-and-component-gaps.md) | 参考依据 | `2026-10-26` | 官方链顺序与物理位置区分、组件缺口、读回色块和 Fan 定性活动；不推断 RPM 或缺少依据的姿态映射 |
| [Unit 主机兼容性研究](unit-research/host-runtime-compatibility.md) | 参考依据 | `2026-10-26` | S3 端口、ADC、console/VFS 与板内共享总线冲突，其他后端的明确控制器门槛；不是跨主机 PASS |

当前入口出现冲突时先修 `project-status.md`、Backlog、代码地图和契约页；
历史页只允许补充“被哪一页取代”，不能反向把旧结论写回当前入口。

## 委派文档怎么读

新鲜度台账只登记需要人工维护当前结论的页面。设备档案、测试/用例 README、
补丁说明、平台目录说明和仓内历史记录属于**委派文档**：它们负责
局部实现、运行方式和当时证据，不应复制一份新的项目总状态。自动项目快照会
盘点全部 Markdown 页面，并单列“带显式旧复核日期的委派文档”；进入这类
页面时，结论顺序始终是：

1. 相邻总索引（`devices/README.md`、`tests/README.md`、
   `tests/network/README.md`、`patches/README.md`、`platform/README.md`）；
2. [项目当前状态](project-status.md)；
3. [项目 Backlog](project-backlog.md)；
4. 页内引用的 evidence 和代码入口。

委派页面的旧日期表示“最后一次局部复核”，不自动证明今天已经失效；但如果
它把已完成项写成待办、把 `runtime_model_gap` 写成固件 FAIL，或与权威页
冲突，就必须修改局部页或明确标为历史。机器生成设备 README 只保留硬件档案、
验证状态和 blocker，详细运行流水统一放在验证台账和专题页。

用例 README 中的 `Status: PASS`、固件 SHA、案例计数和截图都表示**该用例
最后一次 evidence**，不是今天的产品总状态。看到 `current`、`latest` 或
`canonical` 时，应同时确认它指向的 profile/commit 是否仍是
`project-status.md` 中的规范路径；被新路径取代的诊断 lane 必须明确标成
`historical` 或 `diagnostic`。

## 入口索引

### 状态、计划与维护


- [UIFlow2 全接口双主机验证](plans/2026-10-27-uiflow2-complete-api-sweep.md)
- [Unit 外设与视觉模型集成计划](plans/2026-10-25-unit-runtime-integration.md)
- [Unit 接入期间的主机问题](unit-integration-host-issues.md)
- [Unit 官方芯片与协议研究](unit-research/official-protocols.md)
- [GitHub issues #2–#10 顺序复测](evidence/2026-10-27-issues-2-10/README.md)
- [Core2 首帧、离线 WLAN 与 LVGL 修复](evidence/2026-10-27-core2-startup/README.md)
- [Cardputer-ADV BMI270 当前参考固件闭环](evidence/2026-10-29-cardputer-adv-imu/README.md)
- [Cardputer-ADV 用户固件显示、时钟与输入兼容](evidence/2026-10-29-cardputer-adv-user-firmware/README.md)
- [Core2 legacy pre-boot phase profile](evidence/2026-10-29-core2-preboot-phase-profile/README.md)
- [固定版本外壳浏览器集成证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-visual-model-integration/README.md)
- [Encoder 官方协议冲突](unit-research/encoder-protocol-conflicts.md)
- [Unit 首批控制器运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-runtime/README.md)
- [S3 ADC 合成校准依据](unit-research/esp32s3-adc-calibration.md)
- [Unit 视觉绑定与组件缺口](unit-research/visual-bindings-and-component-gaps.md)
- [Unit 首轮控制类运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-controls-service/README.md)
- [Unit I/O 与 IR 分层运行证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-io-final/README.md)
- [Unit 控制类冻结运行复跑](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-controls-final/README.md)
- [Unit 真实浏览器同会话证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-browser-final/README.md)
- [Unit 主机兼容性与扩展门槛](unit-research/host-runtime-compatibility.md)
- [Core2 SoftI2C 接管 A/B 与回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-core2-soft-i2c-handoff/README.md)
- [Unit 全型号真实 Web 同会话取证](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-live-final/README.md)
- [a8fe Unit Web 原轮与失败边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-cohort-a8fe/README.md)
- [Unit Web 就绪与进程证明回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-readiness-regression/README.md)
- [QMP 启动连接竞态与清理修复](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-qmp-startup-connection/README.md)
- [QMP 原失败调查时间线](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-qmp-startup-connection/review-summary.md)
- [Unit 严格显式选择与固件身份](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-final-selection-a8fe/README.md)
- [Unit gen8 逐型号补证](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-supplement-gen8-a8fe/README.md)
- [Unit 自然冷写入生命周期](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-flashing-gen8-a8fe/README.md)
- [Unit 窄屏键名与截图滚动回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-panel-readability-capture-regression/README.md)
- [Unit 三主机九组合与视觉边界](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host-web-gen9-a8fe/README.md)
- [Unit 九组合独立选择与配置晋级](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-host9-selection-a8fe/README.md)
- [前端异步与松开故障回归](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-frontend-recovery-regression/README.md)
- [Unit 真实会话故障恢复](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-26-unit-web-recovery-a8fe/README.md)

- [工程交接总览](engineering-handoff.md)
- [自动项目快照](project-snapshot.md)
- [工作流总台账](workstreams.md)
- [项目当前状态](project-status.md)
- [项目 Backlog](project-backlog.md)
- [代码与验证入口地图](code-map.md)
- [验证证据台账](validation-ledger.md)
- [部署与运行时资产](deployment.md)
- [仓库维护规则](../AGENTS.md)
- [测试入口与 evidence 规则](../tests/README.md)
- [QEMU / 固件补丁总索引](../patches/README.md)

### Device Service 与固件

- [Device Service API](device-service-api.md)
- [OpenAPI 3.1](device-service.openapi.yaml)
- [WebBurner 浏览器固件导入](../platform/web/firmware.html)
- [Device Center adapter](device-center-adapter.md)
- [服务架构与 worker 路线](simulator-service-architecture.md)
- [虚拟设备功能测试工作流](device-functional-test-workflow.md)
- [固件审查与仿真测试工作流](firmware-review-and-simulation-workflow.md)
- [FirmwareManifest 与 WebBurner 导入](firmware-manifest.md)
- [运行时模型缺口登记](runtime-model-gap-register.md)
- [固件验证 evidence 目录](../tests/firmware/README.md)

### 设备、外设与运行时

- [设备档案矩阵](../devices/README.md)
- [虚拟主机适配矩阵](qemu-device-adaptation-matrix.md)
- [UIFlow2 外设测试矩阵](uiflow2-peripheral-test-matrix.md)
- [外设仿真架构](peripheral-simulation-architecture.md)
- [统一设备运行时契约](unified-device-runtime.md)
- [热门用户固件仿真矩阵](user-firmware-simulation-matrix.md)

### 网络与 BLE

- [网络模拟方案](network-simulation-plan.md)
- [网络诊断 lane](network-lane.md)
- [Linux 隔离测试](../tests/network/linux_isolation/README.md)
- [断线重连探针](../tests/network/reconnect_probe/README.md)
- [错误密码负向回归](../tests/network/wrong_password/README.md)
- [TLS Host allowlist 探针](../tests/network/tls_allowlist/README.md)
- [Controlled DNS CNAME chain](../tests/network/dns_cname_chain/README.md)
- [Firmware guest CNAME lifecycle](../tests/network/cname_guest_lifecycle/README.md)
- [精确 IP/端口 egress allowlist](../tests/network/egress_allowlist/README.md)
- [DNS/UDP 数据面探针](../tests/network/idf_dns_udp/README.md)
- [DHCP renewal probe](../tests/network/idf_dhcp_renewal/README.md)
- [UIFlow2 guest IPv6 TCP/HTTP test build](../tests/network/ipv6_end_to_end/README.md)
- [双设备私有 lab fabric](../tests/network/lab_fabric/README.md)
- [本地 worker drain/restart lifecycle](../tests/network/worker_lifecycle/README.md)
- [远程 durable job queue 与 lease supervisor](../tests/network/worker_queue/README.md)
- [Worker claim response-loss idempotency](../tests/network/worker_claim_idempotency/README.md)
- [Lease-bound remote evidence persistence](../tests/network/evidence_store/README.md)
- [HTTP-only worker executor](../tests/network/worker_executor/README.md)
- [Worker HTTPS/mTLS transport](../tests/network/worker_tls/README.md)
- [Authenticated worker discovery](../tests/network/worker_discovery/README.md)
- [Worker control-plane restart continuity](../tests/network/worker_control_restart/README.md)
- [Worker runtime-service restart continuity](../tests/network/worker_runtime_restart/README.md)
- [Idempotent session creation](../tests/network/session_idempotency/README.md)
- [本地 QEMU PID/QMP restart re-attach](../tests/network/worker_reattach/README.md)
- [Cross-network-namespace worker control plane](../tests/network/worker_cross_netns/README.md)
- [Cross-container worker QEMU execution](../tests/network/worker_cross_container/README.md)
- [Core2 stock VHCI BLE（legacy GDB 诊断）](../tests/uiflow2/core2_native_vhci/README.md)
- [Core2 native HCI backend](core2-native-hci-backend.md)

### 专项 Backlog

- [Tab5 暂缓项](tab5-deferred-backlog.md)
- [设备视觉保真](device-visual-fidelity-backlog.md)
- [P4 外设后端要求](p4-peripheral-backend-requirements.md)

### 历史调查和阶段性方案

- [StopWatch UIFlow2 QEMU](stopwatch-uiflow2-qemu.md)
- [Core2 cache/panic 调查](core2-cache-panic-investigation.md)
- [CoreS3 图像渲染边界](cores3-image-rendering-boundary.md)
- [CoreS3 三渲染器对比](cores3-three-renderer.md)
- [StickS3 三渲染器对比](sticks3-three-renderer.md)
- [跨设备回归审计](uiflow2-cross-device-regression-audit.md)
- [多设备模拟器设计](plans/2026-10-20-multi-device-emulator-design.md)

历史页可以解释“为什么这样实现”，但更新当前能力时必须回到
`project-status.md`，更新待办时必须回到 `project-backlog.md`。

## 更新规则

- 项目级当前能力以 `project-status.md` 为准；设备矩阵只提供该页引用的设备
  明细。README 和本页只做摘要，工作流页只维护工作流级索引和下一步，不复制
  逐设备验证明细。
- 能力变化：同步 `README.md`、`project-status.md` 和对应专题页。
- 计划变化：只改 `project-backlog.md` 或专项 backlog。
- API 变化：同步 Markdown、OpenAPI、服务实现和契约测试。
- 设备/外设变化：同步源 catalog、生成目录、peripheral catalog、runtime
  coverage、profile、设备级用例和矩阵文档。
- 新验证：保存 evidence，必要时写入 `agent-work-logs`；不要把聊天摘要当作证据。
- 新验证记录：追加到 `validation-ledger.md`，并回查它是否改变
  `project-status.md` 或 `project-backlog.md`。
- 设备、profile、固件矩阵或 Backlog Task 板变化后运行
  `python3 platform/tools/project_snapshot.py --write`，并让 `--check` 通过。
- 新增或关闭 `runtime_model_gap`：同步
  `runtime-model-gap-register.md` 和 Backlog；分类证据与修复证据分开保存。
- 历史页保留原日期；若结论被推翻，在页首加“已由某页取代”，不要静默改写成
  好像当时就知道后来结果。
- 非历史页复核后更新本页新鲜度表；自动快照会列出复核日期早于当前事实日期的
  页面，CI 不把历史固定页误报为过期。
- 同一证据的 SHA、测试数、Task 状态不要复制到历史页或设计页；应链接当前
  状态/Backlog，减少多处数字漂移。
- PASS/FAIL 比例、轮次、资源数值、固件/工具哈希和逐项检查数只维护在
  `validation-ledger.md`、专题日期化证据或 evidence JSON。README、当前状态、
  Backlog、交接页和工作流页只描述稳定结论与不可继承边界；需要量化时链接
  台账，避免一次新运行迫使多个入口同步改写。

文档一致性由五个 `platform/tests/test_docs_*_contract.py` 模块分域检查，
覆盖导航/链接、当前状态、Core2、固件安全和网络/worker；
`platform/tests/test_docs_consistency.py` 只保留兼容入口。检查内容包括关键
文件、相对链接、API 版本、设备计数和已知过期陈述；退役说法存放在
`platform/tests/fixtures/stale_doc_claims.json`；目录级字段列权威文档路径，
每条 claim 包含稳定 ID、禁止文本和退役原因。

设备本地 case README 只说明该 case 的运行方式和当时边界，不是当前能力
来源。查当前状态先读 `project-status.md`，查动态设备/Task 计数先读
`project-snapshot.md`，查测试归属先读 `tests/README.md`。

## Agent Skills 调用侧资料

- [通用与 AIFlow Skill 分发](plans/2026-10-29-agent-skills.md)
- [AIFlow consumer 历史验证](plans/2026-10-27-aiflow-simulator-skill.md)
- [安装与打包](../skills/README.md)
